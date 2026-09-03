"""Every bulk delete finishes in one call and reports what it actually freed.

Two defects, one shape. `cleanup:prefetch` was reported failing with

    [FAIL] cleanup:prefetch -> PowerShell failed: PowerShell command timed out after 30s

because it called `Remove-Item` once per file; `temp_cleanup` had the identical
loop over a folder measured at 12719 files on the reporting machine, and
`thumbnail_cache_cleanup` had it over the cache databases. All three also
reported the size they *found* as the size they *freed*, which is wrong
wherever a file is open — and in Temp and the thumbnail cache, files are
always open.

These tests run the shipped scripts, not copies, against directories the test
owns, and hold both halves: the delete is one piped `Remove-Item`, and the
megabytes reported are the megabytes that actually went away.
"""

from __future__ import annotations

import re
import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs real powershell.exe")

MB = 1024 * 1024


def _cleaned_mb(output: str) -> float:
    match = re.search(r"Cleaned ([\d.]+) MB", output)
    assert match, f"script did not report a cleaned figure: {output!r}"
    return float(match.group(1))


def _fill(directory, *, files: int, size_bytes: int, prefix: str = "f") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (directory / f"{prefix}{index}.tmp").write_bytes(b"\0" * size_bytes)


# --------------------------------------------------------------------------
# temp_cleanup
# --------------------------------------------------------------------------
TEMP_SCRIPT = ACTION_COMMANDS["temp_cleanup"]


def _run_temp(*, user_temp, local_appdata, windir) -> str:
    prelude = (
        f'$env:TEMP = "{user_temp}"\n'
        f'$env:LOCALAPPDATA = "{local_appdata}"\n'
        f'$env:windir = "{windir}"\n'
    )
    return run_shipped_script(prelude + TEMP_SCRIPT, {})


def test_temp_empties_every_folder_including_subtrees(tmp_path) -> None:
    user_temp = tmp_path / "user" / "Temp"
    local = tmp_path / "local"
    windir = tmp_path / "win"
    _fill(user_temp, files=4, size_bytes=MB // 4)  # 1 MB
    _fill(user_temp / "nested" / "deeper", files=4, size_bytes=MB // 4)  # 1 MB
    _fill(local / "Temp", files=2, size_bytes=MB // 2)  # 1 MB
    _fill(windir / "Temp", files=2, size_bytes=MB // 2)  # 1 MB

    output = _run_temp(user_temp=user_temp, local_appdata=local, windir=windir)

    assert _cleaned_mb(output) == 4.0, output
    for folder in (user_temp, local / "Temp", windir / "Temp"):
        assert list(folder.iterdir()) == []
        assert folder.is_dir()  # the folder itself must survive


def test_temp_counts_only_what_it_could_delete(tmp_path) -> None:
    """A file another process holds open survives, and is not claimed as freed.

    This is the honesty half. The old script summed every file it enumerated,
    so a Temp full of open handles reported megabytes it never freed.
    """
    user_temp = tmp_path / "user" / "Temp"
    local = tmp_path / "local"
    windir = tmp_path / "win"
    _fill(user_temp, files=2, size_bytes=MB)  # 2 MB, deletable
    (local / "Temp").mkdir(parents=True)
    (windir / "Temp").mkdir(parents=True)
    locked_path = user_temp / "held-open.tmp"
    locked_path.write_bytes(b"\0" * MB)

    with open(locked_path, "rb"):  # Windows refuses the delete while this is open
        output = _run_temp(user_temp=user_temp, local_appdata=local, windir=windir)

    assert _cleaned_mb(output) == 2.0, output
    assert locked_path.exists()
    assert locked_path.stat().st_size == MB


def test_temp_skips_folders_that_are_not_there(tmp_path) -> None:
    """%windir%\\Temp is absent on some machines; that is not an error."""
    user_temp = tmp_path / "user" / "Temp"
    _fill(user_temp, files=1, size_bytes=MB)

    output = _run_temp(
        user_temp=user_temp,
        local_appdata=tmp_path / "no-local",
        windir=tmp_path / "no-win",
    )

    assert _cleaned_mb(output) == 1.0, output


def test_temp_walks_one_folder_once_when_two_variables_name_it(tmp_path) -> None:
    """%TEMP% and %LOCALAPPDATA%\\Temp are the same folder on a stock profile.

    Counted twice, the second pass finds an empty folder and adds nothing — so
    the figure was always right and the work was always double.
    """
    local = tmp_path / "local"
    user_temp = local / "Temp"
    _fill(user_temp, files=2, size_bytes=MB)

    output = _run_temp(user_temp=user_temp, local_appdata=local, windir=tmp_path / "absent")

    assert _cleaned_mb(output) == 2.0, output
    assert list(user_temp.iterdir()) == []


# --------------------------------------------------------------------------
# prefetch_cleanup
# --------------------------------------------------------------------------
PREFETCH_SCRIPT = ACTION_COMMANDS["prefetch_cleanup"]


def _run_prefetch(windir) -> str:
    return run_shipped_script(f'$env:windir = "{windir}"\n' + PREFETCH_SCRIPT, {})


def test_prefetch_counts_only_what_it_could_delete(tmp_path) -> None:
    """Windows keeps some .pf files open; those are not freed and are not claimed."""
    windir = tmp_path / "win"
    prefetch = windir / "Prefetch"
    _fill(prefetch, files=2, size_bytes=MB, prefix="APP")
    locked_path = prefetch / "HELD.EXE-00000000.pf"
    locked_path.write_bytes(b"\0" * MB)

    with open(locked_path, "rb"):
        output = _run_prefetch(windir)

    assert _cleaned_mb(output) == 2.0, output
    assert locked_path.exists()


# --------------------------------------------------------------------------
# thumbnail_cache_cleanup
# --------------------------------------------------------------------------
THUMB_SCRIPT = ACTION_COMMANDS["thumbnail_cache_cleanup"]


def _run_thumbs(local_appdata) -> str:
    return run_shipped_script(f'$env:LOCALAPPDATA = "{local_appdata}"\n' + THUMB_SCRIPT, {})


def _explorer_dir(tmp_path):
    folder = tmp_path / "local" / "Microsoft" / "Windows" / "Explorer"
    folder.mkdir(parents=True)
    return folder


def test_thumbnails_removes_the_caches_and_nothing_else(tmp_path) -> None:
    """Explorer keeps its own state in this folder; only the caches may go."""
    folder = _explorer_dir(tmp_path)
    (folder / "thumbcache_32.db").write_bytes(b"\0" * MB)
    (folder / "thumbcache_1024.db").write_bytes(b"\0" * MB)
    (folder / "IconCache.db").write_bytes(b"\0" * MB)
    keep = folder / "ExplorerStartupLog.etl"
    keep.write_bytes(b"\0" * MB)

    output = _run_thumbs(tmp_path / "local")

    assert _cleaned_mb(output) == 3.0, output
    assert keep.exists()
    assert folder.is_dir()


def test_thumbnails_counts_only_what_it_could_delete(tmp_path) -> None:
    """Explorer usually holds these open, which is exactly when the old figure lied."""
    folder = _explorer_dir(tmp_path)
    (folder / "thumbcache_32.db").write_bytes(b"\0" * MB)
    locked_path = folder / "thumbcache_1024.db"
    locked_path.write_bytes(b"\0" * MB)

    with open(locked_path, "rb"):
        output = _run_thumbs(tmp_path / "local")

    assert _cleaned_mb(output) == 1.0, output
    assert locked_path.exists()


def test_thumbnails_on_a_folder_that_is_not_there(tmp_path) -> None:
    assert _cleaned_mb(_run_thumbs(tmp_path / "nothing-here")) == 0.0


# --------------------------------------------------------------------------
# the shape all three share
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "script"),
    [
        ("temp_cleanup", TEMP_SCRIPT),
        ("prefetch_cleanup", PREFETCH_SCRIPT),
        ("thumbnail_cache_cleanup", THUMB_SCRIPT),
    ],
)
def test_the_delete_is_one_piped_call_not_one_per_file(name: str, script: str) -> None:
    """The timeout came from a per-file `Remove-Item`; no script may reintroduce one.

    Comment lines are dropped first: what this counts is how many times the
    cmdlet is *invoked*, and a comment naming it is not an invocation.
    """
    code = "\n".join(line for line in script.splitlines() if not line.strip().startswith("#"))
    assert len(re.findall(r"Remove-Item", code)) == 1, name
    assert not re.search(r"Remove-Item[^\n]*\$\w+\.FullName", code), name


@pytest.mark.parametrize(
    ("name", "script"),
    [
        ("temp_cleanup", TEMP_SCRIPT),
        ("prefetch_cleanup", PREFETCH_SCRIPT),
        ("thumbnail_cache_cleanup", THUMB_SCRIPT),
    ],
)
def test_the_freed_figure_is_a_difference_not_a_sum(name: str, script: str) -> None:
    """`$before - (Get-...)` is what makes the number a measurement (C11)."""
    assert re.search(r"\$before - \(Get-\w+", script), name


def test_temp_cleanup_is_given_more_than_the_default_apply_timeout() -> None:
    """Two recursive sizing passes over a real Temp measured 2.8 s each.

    Asked of the resolver rather than of the source text: the table stopped being
    a local variable when the streamed and quiet runs came to share one timeout
    resolution, and reading it out of the file was only ever a way to reach a
    local.
    """
    from fpstune.settings.definitions.system import CLEANUP_TEMP
    from fpstune.settings.executors.powershell import _apply_timeout

    assert _apply_timeout(CLEANUP_TEMP, "temp_cleanup") > 30
