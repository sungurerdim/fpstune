"""Every bulk delete takes the sizer's own list, and the two figures reconcile.

Two defects, one shape. `cleanup:prefetch` was reported failing with

    [FAIL] cleanup:prefetch -> PowerShell failed: PowerShell command timed out after 30s

because it called `Remove-Item` once per file; `temp_cleanup` had the identical
loop over a folder measured at 12 719 files on the reporting machine, and
`thumbnail_cache_cleanup` had it over the cache databases. All three also
reported the size they *found* as the size they *freed*, which is wrong wherever
a file is open — and in Temp and the thumbnail cache, files are always open.

The second half is now somebody else's job, and that is the change these tests
were rewritten for. The delete no longer counts anything: `cleanup_targets` walks
the paths immediately before and immediately after it, and the difference is the
freed figure. So each test here runs the shipped script against directories it
owns and holds three things together — the right files went, the shown size was a
measurement of those files, and the freed figure is what actually left the disk.

The audit of 2026-09-10 is why the list is passed in rather than rebuilt: on that
machine `%TEMP%` and `%LOCALAPPDATA%\\Temp` were one folder, the sizer walked both
and the delete deduped them, and the row read 109 MB where 54 MB was there.
"""

from __future__ import annotations

import re
import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.settings.cleanup_targets import CLEANUP_TARGETS, delete_arguments, size_target
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.utils.powershell import substitute_placeholders

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs real powershell.exe")

MB = 1024 * 1024


def _fill(directory, *, files: int, size_bytes: int, prefix: str = "f") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (directory / f"{prefix}{index}.tmp").write_bytes(b"\0" * size_bytes)


def _run_delete(cleanup_type: str, action_key: str) -> str:
    """Run the shipped delete over the shipped target's own resolved paths."""
    target = CLEANUP_TARGETS[cleanup_type]
    script = substitute_placeholders(ACTION_COMMANDS[action_key], **delete_arguments(target))
    return run_shipped_script(script, {})


def _shown_then_freed(cleanup_type: str, action_key: str) -> tuple[int, int]:
    """(what the row showed, what the run actually freed), both in bytes.

    The whole point of the rewrite in one function: the number offered to the
    user and the number reported afterwards come from the same instrument over
    the same paths, so a test can assert they reconcile.
    """
    target = CLEANUP_TARGETS[cleanup_type]
    before = size_target(target)
    _run_delete(cleanup_type, action_key)
    after = size_target(target)
    assert before.size_bytes is not None and after.size_bytes is not None
    return before.size_bytes, before.size_bytes - after.size_bytes


# --------------------------------------------------------------------------
# temp
# --------------------------------------------------------------------------


@pytest.fixture
def temp_dirs(tmp_path, monkeypatch):
    """The three folders the temp cleanup names, each one the test's own."""
    user_temp = tmp_path / "user" / "Temp"
    local = tmp_path / "local"
    windir = tmp_path / "win"
    monkeypatch.setenv("TEMP", str(user_temp))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("windir", str(windir))
    return user_temp, local, windir


def test_temp_empties_every_folder_including_subtrees(temp_dirs) -> None:
    user_temp, local, windir = temp_dirs
    _fill(user_temp, files=4, size_bytes=MB // 4)  # 1 MB
    _fill(user_temp / "nested" / "deeper", files=4, size_bytes=MB // 4)  # 1 MB
    _fill(local / "Temp", files=2, size_bytes=MB // 2)  # 1 MB
    _fill(windir / "Temp", files=2, size_bytes=MB // 2)  # 1 MB

    shown, freed = _shown_then_freed("temp", "temp_cleanup")

    assert (shown, freed) == (4 * MB, 4 * MB)
    for folder in (user_temp, local / "Temp", windir / "Temp"):
        assert list(folder.iterdir()) == []
        assert folder.is_dir()  # the folder itself must survive


def test_temp_frees_only_what_it_could_delete(temp_dirs) -> None:
    """A file another process holds open survives, and is not reported as freed.

    This is the honesty half, and it has moved: the delete no longer claims
    anything, so what proves it is the pair of readings around it.
    """
    user_temp, local, windir = temp_dirs
    _fill(user_temp, files=2, size_bytes=MB)  # 2 MB, deletable
    (local / "Temp").mkdir(parents=True)
    (windir / "Temp").mkdir(parents=True)
    locked_path = user_temp / "held-open.tmp"
    locked_path.write_bytes(b"\0" * MB)

    with open(locked_path, "rb"):  # Windows refuses the delete while this is open
        shown, freed = _shown_then_freed("temp", "temp_cleanup")

    assert shown == 3 * MB
    assert freed == 2 * MB
    assert locked_path.exists()
    assert locked_path.stat().st_size == MB


def test_temp_skips_folders_that_are_not_there(tmp_path, monkeypatch) -> None:
    """%windir%\\Temp is absent on some machines; that is not an error."""
    user_temp = tmp_path / "user" / "Temp"
    _fill(user_temp, files=1, size_bytes=MB)
    monkeypatch.setenv("TEMP", str(user_temp))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no-local"))
    monkeypatch.setenv("windir", str(tmp_path / "no-win"))

    assert _shown_then_freed("temp", "temp_cleanup") == (MB, MB)


def test_temp_walks_one_folder_once_when_two_variables_name_it(tmp_path, monkeypatch) -> None:
    """%TEMP% and %LOCALAPPDATA%\\Temp are the same folder on a stock profile.

    Measured on 2026-09-10: 109 MB shown against 54 MB present, because the walk
    counted the folder twice — and the freed figure doubled with it, since both
    halves of the subtraction did.
    """
    local = tmp_path / "local"
    user_temp = local / "Temp"
    _fill(user_temp, files=2, size_bytes=MB)
    monkeypatch.setenv("TEMP", str(user_temp))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("windir", str(tmp_path / "absent"))

    shown, freed = _shown_then_freed("temp", "temp_cleanup")

    assert (shown, freed) == (2 * MB, 2 * MB)
    assert list(user_temp.iterdir()) == []


# --------------------------------------------------------------------------
# thumbnail cache
# --------------------------------------------------------------------------


@pytest.fixture
def explorer_dir(tmp_path, monkeypatch):
    folder = tmp_path / "local" / "Microsoft" / "Windows" / "Explorer"
    folder.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return folder


def test_thumbnails_removes_the_caches_and_nothing_else(explorer_dir) -> None:
    """Explorer keeps its own state in this folder; only the caches may go."""
    (explorer_dir / "thumbcache_32.db").write_bytes(b"\0" * MB)
    (explorer_dir / "thumbcache_1024.db").write_bytes(b"\0" * MB)
    (explorer_dir / "IconCache.db").write_bytes(b"\0" * MB)
    keep = explorer_dir / "ExplorerStartupLog.etl"
    keep.write_bytes(b"\0" * MB)

    shown, freed = _shown_then_freed("thumbnail_cache", "thumbnail_cache_cleanup")

    assert (shown, freed) == (3 * MB, 3 * MB)
    assert keep.exists()
    assert explorer_dir.is_dir()


def test_thumbnails_frees_only_what_it_could_delete(explorer_dir) -> None:
    """Explorer usually holds these open, which is exactly when the old figure lied."""
    (explorer_dir / "thumbcache_32.db").write_bytes(b"\0" * MB)
    locked_path = explorer_dir / "thumbcache_1024.db"
    locked_path.write_bytes(b"\0" * MB)

    with open(locked_path, "rb"):
        _, freed = _shown_then_freed("thumbnail_cache", "thumbnail_cache_cleanup")

    assert freed == MB
    assert locked_path.exists()


def test_thumbnails_on_a_folder_that_is_not_there(tmp_path, monkeypatch) -> None:
    """An absent Explorer folder is an OS folder holding nothing, not a missing
    product: a measured zero rather than a hidden row."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nothing-here"))
    assert _shown_then_freed("thumbnail_cache", "thumbnail_cache_cleanup") == (0, 0)


# --------------------------------------------------------------------------
# the shape every path cleanup shares
# --------------------------------------------------------------------------
SHARED_DELETES = [
    ("temp_cleanup", "temp"),
    ("prefetch_cleanup", "prefetch"),
    ("thumbnail_cache_cleanup", "thumbnail_cache"),
]


@pytest.mark.parametrize(("action_key", "cleanup_type"), SHARED_DELETES)
def test_the_delete_never_enumerates_a_tree(action_key: str, cleanup_type: str) -> None:
    """The timeout came from a per-file `Remove-Item`; no script may bring one back.

    Comment lines are dropped first: what this reads is what the script *does*,
    and a comment naming a cmdlet is not an invocation of it.
    """
    code = "\n".join(
        line
        for line in ACTION_COMMANDS[action_key].splitlines()
        if not line.strip().startswith("#")
    )
    for line in code.splitlines():
        if "Get-ChildItem" in line:
            assert "-Recurse" not in line, f"{cleanup_type}: {line.strip()}"
    assert not re.search(r"Remove-Item[^\n]*\$\w+\.FullName", code), cleanup_type


@pytest.mark.parametrize(("action_key", "cleanup_type"), SHARED_DELETES)
def test_the_delete_counts_nothing(action_key: str, cleanup_type: str) -> None:
    """A figure the script computes is a second measurement, and it disagreed.

    It also cost the most of any way of taking it: `Get-ChildItem -Recurse |
    Measure-Object` measured 3 229-4 698 ms over a 229 MB tree where the walk it
    imitated took 584-702 ms, and `temp`, `prefetch` and `thumbnail_cache` each
    paid it twice — once before the delete and once after.
    """
    script = ACTION_COMMANDS[action_key]
    assert "Measure-Object" not in script, cleanup_type
    assert "Cleaned" not in script, cleanup_type


@pytest.mark.parametrize(("action_key", "cleanup_type"), SHARED_DELETES)
def test_the_delete_is_given_the_list_it_must_not_rebuild(
    action_key: str, cleanup_type: str
) -> None:
    script = ACTION_COMMANDS[action_key]
    assert "%paths%" in script, cleanup_type
    # No environment variable is read inside the script: resolving a path there
    # is the second list, and the second list is what drifted.
    assert "$env:" not in script, cleanup_type
