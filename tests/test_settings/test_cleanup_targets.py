"""The in-process sizer: one path list, one walk, and no number nobody took.

Every case here is a defect the audit of 2026-09-10 measured on a real machine
rather than a property invented for a test:

  * `%TEMP%` and `%LOCALAPPDATA%\\Temp` are one folder, and walking both reported
    109 MB where 54 MB was there — doubling the freed figure with it;
  * one `try` around a recursive enumeration stopped at the first denied
    subdirectory, reporting 0 B for a folder a per-directory walk read as 446 MB;
  * five targets answered `0 MB` or `not_installed` unelevated for folders that
    were plainly there;
  * a cleanup that removes its own directory looked uninstalled the moment it
    succeeded, so the row lost its freed figure entirely.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fpstune.settings.cleanup_targets import (
    CLEANUP_TARGETS,
    DIRECTORY,
    TOP_FILES,
    CleanupTarget,
    resolved_paths,
    size_target,
    size_types,
)


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _target(paths, **kwargs) -> CleanupTarget:
    return CleanupTarget("test_target", lambda: [str(p) for p in paths], **kwargs)


class TestOnePathListForBothHalves:
    """What the sizer counts is what the delete is handed — the same list."""

    def test_the_same_folder_reached_two_ways_is_counted_once(self, tmp_path: Path) -> None:
        """`%TEMP%` and `%LOCALAPPDATA%\\Temp` are one folder on a stock profile.

        Walking both read 109 MB against the 54 MB that was there, and freed
        doubled with the size, because both halves of the subtraction doubled.
        """
        real = tmp_path / "Temp"
        _write(real / "installer.log", 4096)
        # The second spelling of the same folder: a trailing separator, a `.`
        # segment and a different case all name it, exactly as the three
        # environment variables do on a machine where TEMP is not redirected.
        aliases = [real, Path(str(real) + os.sep), real / ".", Path(str(real).upper())]

        target = _target(aliases, absent_is_not_installed=False)

        assert len(resolved_paths(target)) == 1
        assert size_target(target) == ("ready", 4096)

    def test_a_path_inside_another_is_not_counted_twice(self, tmp_path: Path) -> None:
        """A nested pair would add the child's bytes to its parent's walk."""
        _write(tmp_path / "cache" / "sub" / "blob.bin", 8192)

        target = _target([tmp_path / "cache", tmp_path / "cache" / "sub"])

        assert resolved_paths(target) == [str(tmp_path / "cache")]
        assert size_target(target) == ("ready", 8192)


class TestADeniedFolderIsNotAnEmptyOne:
    """C11 rule 3, applied to a walk: "cannot read" is never reported as 0."""

    def test_a_denied_subdirectory_costs_that_subdirectory_and_not_the_walk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Defender case: 0 B reported for a tree holding 446 MB.

        The old helper wrapped one recursive enumeration in one `try`, so the
        first denial ended the walk and the partial sum — nothing, when the
        denial came early — was returned as the answer.
        """
        # Named so the denied directory is reached first: the old walk returned
        # whatever it had summed when the denial arrived, which for a denial that
        # arrives first is nothing at all.
        _write(tmp_path / "a_readable" / "one.bin", 1000)
        _write(tmp_path / "z_locked" / "two.bin", 2000)
        _write(tmp_path / "a_readable" / "deep" / "three.bin", 3000)
        real_scandir = os.scandir

        def deny_locked(path):
            if str(path).endswith("z_locked"):
                raise PermissionError(13, "Access is denied")
            return real_scandir(path)

        monkeypatch.setattr("fpstune.settings.cleanup_targets.os.scandir", deny_locked)

        assert size_target(_target([tmp_path])) == ("ready", 4000)

    def test_a_top_level_path_that_cannot_be_listed_is_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unelevated, Prefetch answered `0 MB` for a folder full of files."""
        (tmp_path / "Prefetch").mkdir()

        def deny(path):  # noqa: ARG001 - the signature os.scandir is called with
            raise PermissionError(13, "Access is denied")

        monkeypatch.setattr("fpstune.settings.cleanup_targets.os.scandir", deny)

        reading = size_target(_target([tmp_path / "Prefetch"], absent_is_not_installed=False))
        assert reading == ("unavailable", None)

    def test_a_path_whose_own_metadata_is_denied_is_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defender's scan history: `os.path.exists` answers False when denied.

        Collapsing "refused to say" into "not here" is what let four folders that
        exist be reported as a measured zero.
        """
        real_stat = os.stat

        def deny_scans(path, *args, **kwargs):
            if "Scans" in str(path):
                raise PermissionError(13, "Access is denied")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr("fpstune.settings.cleanup_targets.os.stat", deny_scans)

        target = _target([tmp_path / "Scans" / "History"], absent_is_not_installed=False)
        assert size_target(target) == ("unavailable", None)

    def test_nothing_there_at_all_is_still_a_measured_zero_where_it_should_be(
        self, tmp_path: Path
    ) -> None:
        """An OS folder that simply holds nothing is not an uninstalled product."""
        target = _target([tmp_path / "never-created"], absent_is_not_installed=False)
        assert size_target(target) == ("ready", 0)

    def test_absent_software_is_hidden_rather_than_shown_as_empty(self, tmp_path: Path) -> None:
        target = _target([tmp_path / "no-such-launcher"])
        assert size_target(target) == ("not_installed", None)


class TestADeletedDirectoryIsZeroAndNotUninstalled:
    """Audit finding 5: the row lost its freed figure the moment the run worked."""

    def test_the_cache_going_away_leaves_a_measured_zero(self, tmp_path: Path) -> None:
        """The game is still installed; only its shader cache was removed.

        With the cache directory itself as the only evidence of installation, a
        successful run reported `not_installed`, which made the setting
        not-applicable and dropped the freed figure off the row.
        """
        game_root = tmp_path / "Call of Duty MWIII"
        crashes = game_root / "crashes"
        _write(crashes / "dump.txt", 512)

        target = CleanupTarget(
            "test_target",
            lambda: [str(crashes)],
            delete_mode=DIRECTORY,
            installed=lambda: [str(game_root)],
        )
        assert size_target(target) == ("ready", 512)

        # What the delete does: the directory itself goes.
        for child in crashes.iterdir():
            child.unlink()
        crashes.rmdir()

        assert size_target(target) == ("ready", 0)

    def test_the_game_being_gone_is_still_not_installed(self, tmp_path: Path) -> None:
        target = CleanupTarget(
            "test_target",
            lambda: [str(tmp_path / "game" / "crashes")],
            delete_mode=DIRECTORY,
            installed=lambda: [str(tmp_path / "game")],
        )
        assert size_target(target) == ("not_installed", None)


class TestCountingOnlyWhatTheDeleteWouldTake:
    """The filter is one filter: what is counted is what would go."""

    def test_a_top_level_delete_does_not_count_subdirectories(self, tmp_path: Path) -> None:
        """Prefetch: the command enumerates the top level without `-Recurse`.

        A ReadyBoot subdirectory would be counted and never deleted, so the row
        would promise bytes the run could not return.
        """
        _write(tmp_path / "APP.EXE-1234.pf", 700)
        _write(tmp_path / "ReadyBoot" / "trace.fx", 90000)

        target = _target([tmp_path], delete_mode=TOP_FILES, absent_is_not_installed=False)
        assert size_target(target) == ("ready", 700)

    def test_only_the_named_files_are_counted(self, tmp_path: Path) -> None:
        """The thumbnail cache command names its two file patterns."""
        _write(tmp_path / "thumbcache_256.db", 300)
        _write(tmp_path / "IconCache.db", 200)
        _write(tmp_path / "explorer-state.bin", 999999)

        target = _target(
            [tmp_path],
            delete_mode=TOP_FILES,
            name_globs=("thumbcache_*.db", "IconCache.db"),
            absent_is_not_installed=False,
        )
        assert size_target(target) == ("ready", 500)

    def test_a_junction_is_stepped_over_rather_than_followed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reparse point counts a tree the delete does not descend into."""
        _write(tmp_path / "cache" / "real.bin", 1234)
        _write(tmp_path / "elsewhere" / "big.bin", 500000)

        real_scandir = os.scandir

        class _FakeJunction:
            def __init__(self, entry) -> None:
                self._entry = entry
                self.path = entry.path
                self.name = entry.name

            def is_symlink(self) -> bool:
                return False

            def is_junction(self) -> bool:
                return self.name == "link"

            def is_dir(self, follow_symlinks: bool = True) -> bool:
                return self._entry.is_dir(follow_symlinks=follow_symlinks)

            def stat(self, follow_symlinks: bool = True):
                return self._entry.stat(follow_symlinks=follow_symlinks)

        class _Scan:
            def __init__(self, path) -> None:
                self._inner = real_scandir(path)

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> None:
                self._inner.close()

            def __iter__(self):
                for entry in self._inner:
                    yield _FakeJunction(entry)

        # The junction is a directory named `link` pointing at `elsewhere`.
        (tmp_path / "cache" / "link").mkdir()
        _write(tmp_path / "cache" / "link" / "shadow.bin", 500000)
        monkeypatch.setattr("fpstune.settings.cleanup_targets.os.scandir", _Scan)

        assert size_target(_target([tmp_path / "cache"])) == ("ready", 1234)


class TestTheShippedTable:
    """The table is what the registry's cleanup types are actually sized by."""

    def test_every_target_resolves_its_paths_without_naming_this_machine(self) -> None:
        """C9: a path comes from the environment, never from the source."""
        for name, target in CLEANUP_TARGETS.items():
            paths = resolved_paths(target)
            assert isinstance(paths, list), name
            assert all(os.path.isabs(p) for p in paths), name

    def test_sizing_many_types_answers_for_each_of_them(self) -> None:
        names = ("pip_cache", "npm_cache", "directx_shader")
        readings = size_types(names)
        assert set(readings) == set(names)
        for name, reading in readings.items():
            assert reading.status in {"ready", "unavailable", "not_installed"}, name
            if reading.status == "ready":
                assert reading.size_bytes is not None and reading.size_bytes >= 0

    def test_an_unknown_type_is_simply_not_ours(self) -> None:
        assert size_types(("dism", "docker_prune")) == {}

    def test_the_wsl_disk_states_no_reclaimable_size(self) -> None:
        """Audit finding 4: the whole virtual disk was offered as reclaimable.

        A compact returns the slack inside a sparse disk, which nothing outside
        the VM can read — so the bytes are reported as measured-but-not-a-promise
        and the row's freed figure comes from the run's own before/after.
        """
        assert CLEANUP_TARGETS["wsl_compact"].estimates_reclaim is False
