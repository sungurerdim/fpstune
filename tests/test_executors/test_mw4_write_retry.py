"""A config replace that Windows refuses is retried, then explained.

The shipped apply of ``game_config:mw4:dof_weapon`` failed on 2026-09-02 with
``[WinError 5] Erişim engellendi: '...fpstune-tmp' -> '...s.1.1.bt.cod26.txt'``:
``os.replace`` while another process held the target open, and the OS text in
the system language as the whole message. The game was not running and the file
was not read-only, so the holder was transient — the shape an antivirus scan or a
sync client produces. A retry absorbs that; a holder that stays gets a sentence
the user can act on instead of a localized error code.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fpstune.settings.executors import mw4_config
from fpstune.settings.executors.mw4_config import _REPLACE_ATTEMPTS, _write_atomically


@pytest.fixture
def quiet_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the backoff instead of waiting through it."""
    slept: list[float] = []
    monkeypatch.setattr(mw4_config.time, "sleep", slept.append)
    return slept


def _refusing_replace(monkeypatch: pytest.MonkeyPatch, refusals: int):
    """An os.replace that answers WinError 5 the first `refusals` times."""
    real = os.replace
    calls = {"n": 0}

    def replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        calls["n"] += 1
        if calls["n"] <= refusals:
            raise PermissionError(5, "Access is denied")
        real(src, dst)

    monkeypatch.setattr(mw4_config.os, "replace", replace)
    return calls


def test_a_transient_holder_is_outwaited(tmp_path: Path, monkeypatch, quiet_sleep) -> None:
    target = tmp_path / "s.1.1.bt.cod26.txt"
    target.write_bytes(b"DofWeapon@0 = 1 // 0 or 1\n")
    calls = _refusing_replace(monkeypatch, refusals=2)

    _write_atomically(target, b"DofWeapon@0 = 0 // 0 or 1\n")

    assert target.read_bytes() == b"DofWeapon@0 = 0 // 0 or 1\n"
    assert calls["n"] == 3
    assert quiet_sleep == [0.15, 0.30]
    assert list(tmp_path.glob("*.fpstune-tmp")) == []


def test_a_holder_that_stays_is_named_in_the_users_terms(
    tmp_path: Path, monkeypatch, quiet_sleep
) -> None:
    target = tmp_path / "s.1.1.bt.cod26.txt"
    target.write_bytes(b"DofWeapon@0 = 1\n")
    _refusing_replace(monkeypatch, refusals=_REPLACE_ATTEMPTS + 1)

    with pytest.raises(PermissionError) as caught:
        _write_atomically(target, b"DofWeapon@0 = 0\n")

    message = str(caught.value)
    assert "s.1.1.bt.cod26.txt is held open by another program" in message
    assert "Close it and apply again" in message
    assert "WinError" not in message
    # The original OS error stays reachable for the log, never for the user.
    assert isinstance(caught.value.__cause__, PermissionError)
    assert target.read_bytes() == b"DofWeapon@0 = 1\n", "the target must not be half-written"
    assert list(tmp_path.glob("*.fpstune-tmp")) == [], "the temp file is cleaned up"
    assert len(quiet_sleep) == _REPLACE_ATTEMPTS - 1


def test_other_errors_are_not_retried(tmp_path: Path, monkeypatch, quiet_sleep) -> None:
    """Only a denied replace is a wait-and-retry; anything else is reported at once."""
    target = tmp_path / "s.1.1.bt.cod26.txt"
    target.write_bytes(b"x")

    def replace(_src: object, _dst: object) -> None:
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr(mw4_config.os, "replace", replace)
    with pytest.raises(FileNotFoundError):
        _write_atomically(target, b"y")
    assert quiet_sleep == []
    assert list(tmp_path.glob("*.fpstune-tmp")) == []
