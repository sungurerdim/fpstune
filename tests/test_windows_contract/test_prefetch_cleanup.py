"""The shipped prefetch cleanup empties the folder and reports what it freed.

Reported on 2026-09-02, from a real run:

    [FAIL] cleanup:prefetch -> PowerShell failed: PowerShell command timed out after 30s

The script deleted one file per `Remove-Item` call, so a folder with a few
thousand `.pf` entries paid a cmdlet dispatch per entry and ran past the apply
timeout. What the user saw was a timeout, not a refusal, and nothing was
cleaned. These tests run the shipped script — not a copy — against a fake
Windows directory, and hold both halves of the contract: the folder is emptied
in one call, and the megabytes reported are the ones that were there.
"""

from __future__ import annotations

import re
import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs real powershell.exe")

SCRIPT = ACTION_COMMANDS["prefetch_cleanup"]


def _run(prefetch_dir: str) -> str:
    """Run the shipped script with $env:windir pointed at a directory we own."""
    prelude = f'$env:windir = "{prefetch_dir}"\n'
    return run_shipped_script(prelude + SCRIPT, {})


def _make_prefetch(tmp_path, *, files: int, size_bytes: int) -> str:
    windir = tmp_path / "fakewindir"
    prefetch = windir / "Prefetch"
    prefetch.mkdir(parents=True)
    for index in range(files):
        (prefetch / f"APP{index}.EXE-0000{index}.pf").write_bytes(b"\0" * size_bytes)
    return str(windir)


def test_it_empties_the_folder_and_reports_the_megabytes(tmp_path) -> None:
    windir = _make_prefetch(tmp_path, files=8, size_bytes=256 * 1024)  # 2 MB total
    prefetch = tmp_path / "fakewindir" / "Prefetch"

    output = _run(windir)

    assert "Cleaned 2 MB" in output, output
    assert list(prefetch.iterdir()) == []
    # The folder itself survives: Windows writes new .pf files into it, and a
    # removed Prefetch directory is a different, worse state than an empty one.
    assert prefetch.is_dir()


def test_a_thousand_entries_finish_well_inside_the_apply_timeout(tmp_path) -> None:
    """The regression: a per-file delete loop is what ran past 30 seconds.

    The harness caps PowerShell at 120 s, so a script that reverts to per-file
    deletion fails here by timing out rather than by a wrong number.
    """
    windir = _make_prefetch(tmp_path, files=1000, size_bytes=1024)
    prefetch = tmp_path / "fakewindir" / "Prefetch"

    output = _run(windir)

    assert "Cleaned" in output, output
    assert list(prefetch.iterdir()) == []


def test_an_empty_folder_reports_zero_rather_than_failing(tmp_path) -> None:
    windir = _make_prefetch(tmp_path, files=0, size_bytes=0)
    assert "Cleaned 0 MB" in _run(windir)


def test_a_missing_folder_is_not_an_error(tmp_path) -> None:
    """Prefetch is absent on a machine where superfetch never ran."""
    windir = tmp_path / "no-prefetch-here"
    windir.mkdir()
    assert "Cleaned 0 MB" in _run(str(windir))


def test_the_script_deletes_the_contents_in_one_call() -> None:
    """The shape the timeout came from: one Remove-Item, not one per file."""
    assert len(re.findall(r"Remove-Item", SCRIPT)) == 1
    assert "foreach" not in SCRIPT
