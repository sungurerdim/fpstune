"""The executable replaces itself only with a download its checksum vouches for."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from fpstune.utils import updates
from fpstune.utils.updates import UpdateCheck, install_update, remove_replaced_executable

NEW = b"MZ new fpstune build"


def _check() -> UpdateCheck:
    return UpdateCheck(
        current="0.1.0",
        latest="0.2.0",
        exe_url="https://example.invalid/fpstune.exe",
        sha256_url="https://example.invalid/fpstune.exe.sha256",
    )


def _fetch_with(checksum: str):
    def fetch(url: str, _limit: int) -> bytes:
        return (f"{checksum}  fpstune.exe".encode()) if url.endswith(".sha256") else NEW

    return fetch


def test_a_verified_download_takes_the_executables_place(tmp_path: Path) -> None:
    exe = tmp_path / "fpstune.exe"
    exe.write_bytes(b"MZ old build")

    with patch.object(updates, "_fetch", _fetch_with(hashlib.sha256(NEW).hexdigest())):
        installed, message = install_update(_check(), executable=exe)

    assert installed, message
    assert exe.read_bytes() == NEW
    assert (tmp_path / "fpstune.exe.old").read_bytes() == b"MZ old build"


def test_a_checksum_mismatch_changes_nothing(tmp_path: Path) -> None:
    exe = tmp_path / "fpstune.exe"
    exe.write_bytes(b"MZ old build")

    with patch.object(updates, "_fetch", _fetch_with("0" * 64)):
        installed, message = install_update(_check(), executable=exe)

    assert installed is False
    assert "checksum" in message
    assert exe.read_bytes() == b"MZ old build"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fpstune.exe"]


def test_a_release_without_a_checksum_is_refused(tmp_path: Path) -> None:
    check = UpdateCheck(current="0.1.0", latest="0.2.0", exe_url="https://x/fpstune.exe")

    installed, _message = install_update(check, executable=tmp_path / "fpstune.exe")

    assert installed is False


def test_nothing_newer_installs_nothing(tmp_path: Path) -> None:
    check = UpdateCheck(current="0.2.0", latest="0.2.0", exe_url="a", sha256_url="b")

    assert install_update(check, executable=tmp_path / "fpstune.exe")[0] is False


def test_the_next_start_removes_the_replaced_copy(tmp_path: Path) -> None:
    exe = tmp_path / "fpstune.exe"
    exe.write_bytes(NEW)
    (tmp_path / "fpstune.exe.old").write_bytes(b"old")

    remove_replaced_executable(exe)

    assert not (tmp_path / "fpstune.exe.old").exists()
