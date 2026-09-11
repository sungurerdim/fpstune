"""The shipped prefetch cleanup empties the folder in one call, top level only.

Reported on 2026-09-02, from a real run:

    [FAIL] cleanup:prefetch -> PowerShell failed: PowerShell command timed out after 30s

The script deleted one file per `Remove-Item` call, so a folder with a few
thousand `.pf` entries paid a cmdlet dispatch per entry and ran past the apply
timeout. What the user saw was a timeout, not a refusal, and nothing was cleaned.

The audit of 2026-09-10 added the second half of the contract. The command
enumerates the top level *without* `-Recurse`, so a subdirectory — `ReadyBoot` on
a real machine — is never removed, while the sizer walked the whole tree and
counted it. A folder that is counted and cannot be deleted is a promise the run
cannot keep, so the walk stops at the top level too.

These tests run the shipped script against a directory the test owns, with the
same path list the sizer resolves.
"""

from __future__ import annotations

import sys
import time

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.settings.cleanup_targets import (
    CLEANUP_TARGETS,
    TOP_FILES,
    delete_arguments,
    size_target,
)
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.utils.powershell import substitute_placeholders

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs real powershell.exe")

TARGET = CLEANUP_TARGETS["prefetch"]


def _run() -> str:
    script = substitute_placeholders(
        ACTION_COMMANDS["prefetch_cleanup"], **delete_arguments(TARGET)
    )
    return run_shipped_script(script, {})


def _make_prefetch(tmp_path, monkeypatch, *, files: int, size_bytes: int):
    windir = tmp_path / "fakewindir"
    prefetch = windir / "Prefetch"
    prefetch.mkdir(parents=True)
    for index in range(files):
        (prefetch / f"APP{index}.EXE-0000{index}.pf").write_bytes(b"\0" * size_bytes)
    monkeypatch.setenv("windir", str(windir))
    return prefetch


def test_it_empties_the_folder_and_the_pair_of_readings_agrees(tmp_path, monkeypatch) -> None:
    prefetch = _make_prefetch(tmp_path, monkeypatch, files=8, size_bytes=256 * 1024)  # 2 MB

    before = size_target(TARGET)
    _run()
    after = size_target(TARGET)

    assert (before.status, before.size_bytes) == ("ready", 2 * 1024 * 1024)
    assert (after.status, after.size_bytes) == ("ready", 0)
    assert list(prefetch.iterdir()) == []
    # The folder itself survives: Windows writes new .pf files into it, and a
    # removed Prefetch directory is a different, worse state than an empty one.
    assert prefetch.is_dir()


def test_a_subdirectory_is_neither_counted_nor_removed(tmp_path, monkeypatch) -> None:
    """`ReadyBoot` sits inside Prefetch and the command does not recurse.

    Counting it promised bytes the run could never return — audit finding 13.
    """
    prefetch = _make_prefetch(tmp_path, monkeypatch, files=1, size_bytes=1024)
    ready_boot = prefetch / "ReadyBoot"
    ready_boot.mkdir()
    (ready_boot / "Trace1.fx").write_bytes(b"\0" * 90000)

    before = size_target(TARGET)
    _run()

    assert TARGET.delete_mode == TOP_FILES
    assert before.size_bytes == 1024
    assert (ready_boot / "Trace1.fx").exists()


def test_a_thousand_entries_finish_well_inside_the_apply_timeout(tmp_path, monkeypatch) -> None:
    """The regression: a per-file delete loop is what ran past 30 seconds.

    The harness caps PowerShell at 120 s, so a script that reverts to per-file
    deletion fails here by timing out rather than by a wrong number.
    """
    prefetch = _make_prefetch(tmp_path, monkeypatch, files=1000, size_bytes=1024)

    started = time.monotonic()
    _run()
    elapsed = time.monotonic() - started

    assert list(prefetch.iterdir()) == []
    assert elapsed < 30, f"the delete took {elapsed:.1f}s for 1000 entries"


def test_an_empty_folder_is_a_measured_zero_rather_than_a_failure(tmp_path, monkeypatch) -> None:
    _make_prefetch(tmp_path, monkeypatch, files=0, size_bytes=0)
    _run()
    assert size_target(TARGET) == ("ready", 0)


def test_a_missing_folder_is_not_an_error(tmp_path, monkeypatch) -> None:
    """Prefetch is absent on a machine where superfetch never ran."""
    windir = tmp_path / "no-prefetch-here"
    windir.mkdir()
    monkeypatch.setenv("windir", str(windir))

    _run()

    assert size_target(TARGET) == ("ready", 0)
