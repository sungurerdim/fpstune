"""Sizing a cleanup's target, and what the pair of readings around a command says.

The freed figure the UI used to show was a cached size up to five minutes old
minus whatever a background re-scan reported some seconds after the run — two
readings that never bracketed anything. This module is the instrument that
replaces it, and these tests pin the properties that make its output a
measurement rather than an estimate:

  * one parse behind every reader, so the cache and the apply cannot disagree
    about what "unavailable" or "1234 MB" means for the same line;
  * None wherever a size was not read, never a 0 standing in for it;
  * a difference only where both halves are sizes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.settings import cleanup_measure
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.cleanup_cache import CleanupSizeCache
from fpstune.settings.cleanup_measure import CleanupSize, freed_after_cleanup
from fpstune.settings.executors import ps_batch

MB = 1024 * 1024


def _cleanup(
    setting_id: str = "cleanup:dism_cleanup", cleanup_type: str = "dism"
) -> SettingExecutor:
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.MAINTENANCE,
        display_name="Component Store",
        description="Superseded update backups Windows keeps. Removing them returns the space.",
        value_type=SettingValueType.BOOL,
        choices=(),
        default_value=False,
        recommended_value=True,
        is_action=True,
        detect_type=DetectType.POWERSHELL,
        detect_command="cleanup_status",
        detect_args={"type": cleanup_type},
        apply_type=DetectType.POWERSHELL,
        apply_command="dism_cleanup",
    )


class TestMeasuringOneCleanupAroundItsOwnCommand:
    """The apply-time measurement, for the readings PowerShell still takes.

    A cleanup whose target is a folder is walked in this process (see
    `TestMeasuringAFolderTargetInProcess`); what is left here is the handful that
    needs the component store, a docker daemon, the shadow storage allocation or
    the event log service - so the type these use is `dism` rather than a folder.


    The freed figure the UI used to show was a cached size minus a later
    background re-scan — two readings that never bracketed anything. This is the
    instrument that replaces it, and these pin the two properties that make its
    output a measurement: it reads through the one parse the cache uses, and it
    answers None rather than a number whenever it did not read a size.
    """

    @pytest.fixture
    def setting(self):
        from fpstune.settings.base import (
            DetectType,
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )

        return SettingExecutor(
            id="cleanup:dism_cleanup",
            category=SettingCategory.MAINTENANCE,
            display_name="Component Store",
            description="Superseded update backups Windows keeps. Removing them returns the space.",
            value_type=SettingValueType.BOOL,
            choices=(),
            default_value=False,
            recommended_value=True,
            is_action=True,
            detect_type=DetectType.POWERSHELL,
            detect_command="cleanup_status",
            detect_args={"type": "dism"},
            apply_type=DetectType.POWERSHELL,
            apply_command="dism_cleanup",
        )

    @staticmethod
    def _measure(setting, cache: CleanupSizeCache, reading: str, **kwargs):

        with (
            patch("fpstune.settings.cleanup_cache.cleanup_size_cache", cache),
            patch.object(cleanup_measure.sys, "platform", "win32"),
            patch.object(ps_batch, "_fetch_cleanup_sizes", lambda t: {t[0]: reading}),
        ):
            return cleanup_measure.measure_cleanup_size(setting, **kwargs)

    @pytest.mark.parametrize(
        ("reading", "status", "size_bytes"),
        [
            ("ready|56 MB", "ready", 56 * 1024 * 1024),
            # An emptied folder is a real reading of zero, not a failure to read.
            ("ready|0 MB", "ready", 0),
            ("ready|unavailable", "unavailable", None),
            ("ready|not_installed", "not_installed", None),
            # A warning line rides along with the value and must not become it.
            ("FPSTUNE_WARN: du refused a path\nready|56 MB", "ready", 56 * 1024 * 1024),
        ],
    )
    def test_it_reads_a_line_exactly_as_the_cache_does(
        self, setting, reading: str, status: str, size_bytes: int | None
    ) -> None:
        """One parse behind both, so a size the cache stores and a size the apply
        reports can never be two different readings of the same line."""

        measured = self._measure(setting, CleanupSizeCache(), reading)
        assert measured is not None
        assert (measured.status, measured.size_bytes) == (status, size_bytes)

        stored = CleanupSizeCache()
        with patch("fpstune.settings.cleanup_cache.cleanup_size_cache", stored):
            assert cleanup_measure.store_cleanup_reading(setting.id, reading) is True
        entry = stored.get(setting.id)
        assert entry is not None
        assert entry["status"] == status
        assert entry["bytes"] == (size_bytes or 0)

    @pytest.mark.parametrize("reading", ["", "ready|? MB", "Get-CleanupStatus : denied"])
    def test_a_line_it_cannot_read_is_no_reading_at_all(self, setting, reading: str) -> None:
        """Never a 0: "we could not size it" and "there is nothing there" are
        different answers, and only one of them was observed (C11 rule 3)."""
        assert self._measure(setting, CleanupSizeCache(), reading) is None

    def test_remembering_puts_the_reading_where_the_row_reads_it(self, setting) -> None:
        cache = CleanupSizeCache()
        self._measure(setting, cache, "ready|96 MB", remember=True)

        entry = cache.get(setting.id)
        assert entry is not None
        assert (entry["status"], entry["bytes"]) == ("ready", 96 * 1024 * 1024)

    def test_a_measurement_that_failed_drops_the_stale_entry(self, setting) -> None:
        """The pre-command size is wrong the moment the command has run."""
        cache = CleanupSizeCache()
        cache.set_result(setting.id, 1240 * 1024 * 1024)

        self._measure(setting, cache, "", remember=True)

        assert cache.get(setting.id) is None

    def test_a_plain_measurement_leaves_the_cache_alone(self, setting) -> None:
        """The before reading must not overwrite what the row is showing."""
        cache = CleanupSizeCache()
        cache.set_result(setting.id, 1240 * 1024 * 1024)

        self._measure(setting, cache, "ready|96 MB")

        entry = cache.get(setting.id)
        assert entry is not None
        assert entry["bytes"] == 1240 * 1024 * 1024

    def test_a_setting_that_sizes_nothing_starts_no_powershell(self) -> None:
        """Only a cleanup has a target to size, and the detect side says so."""
        from fpstune.settings.base import (
            DetectType,
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )

        setting = SettingExecutor(
            id="system:mouse_acceleration",
            category=SettingCategory.SYSTEM,
            display_name="Mouse Acceleration",
            description="Pointer precision scaling. Off keeps aim one-to-one with the mouse.",
            value_type=SettingValueType.CHOICE,
            choices=("off", "on"),
            default_value="on",
            recommended_value="off",
            detect_type=DetectType.POWERSHELL,
            detect_command="Get-Something",
            apply_type=DetectType.POWERSHELL,
            apply_command="Set-Something",
        )
        called = []
        with (
            patch.object(cleanup_measure.sys, "platform", "win32"),
            patch.object(ps_batch, "_fetch_cleanup_sizes", lambda t: called.append(t) or {}),
        ):
            assert cleanup_measure.measure_cleanup_size(setting) is None
        assert called == []

    def test_off_windows_it_measures_nothing(self, setting) -> None:
        """No Get-CleanupStatus to run, so no reading and nothing claimed."""

        called = []
        with (
            patch.object(cleanup_measure.sys, "platform", "linux"),
            patch.object(ps_batch, "_fetch_cleanup_sizes", lambda t: called.append(t) or {}),
        ):
            assert cleanup_measure.measure_cleanup_size(setting) is None
        assert called == []


class TestThePairOfReadingsAroundACommand:
    """`freed_after_cleanup`: the after reading, and the difference, or neither."""

    @staticmethod
    def _freed(setting, cache: CleanupSizeCache, before: CleanupSize | None, after: str):
        with (
            patch("fpstune.settings.cleanup_cache.cleanup_size_cache", cache),
            patch.object(cleanup_measure.sys, "platform", "win32"),
            patch.object(ps_batch, "_fetch_cleanup_sizes", lambda t: {t[0]: after}),
        ):
            return freed_after_cleanup(setting, before)

    def test_two_sizes_give_the_difference_and_the_remainder(self) -> None:
        freed = self._freed(
            _cleanup(), CleanupSizeCache(), CleanupSize("ready", 1240 * MB, ""), "ready|96 MB"
        )

        assert freed.freed_bytes == (1240 - 96) * MB
        assert freed.size_after_bytes == 96 * MB

    def test_a_target_that_grew_freed_nothing_rather_than_a_negative_amount(self) -> None:
        """A process writes into %TEMP% while the cleanup deletes from it."""
        freed = self._freed(
            _cleanup(), CleanupSizeCache(), CleanupSize("ready", 100 * MB, ""), "ready|140 MB"
        )

        assert freed.freed_bytes == 0
        assert freed.size_after_bytes == 140 * MB

    def test_a_missing_before_reading_gives_no_difference(self) -> None:
        """A subtraction with one operand is not a measurement (C11 rule 3)."""
        freed = self._freed(_cleanup(), CleanupSizeCache(), None, "ready|96 MB")

        assert freed.freed_bytes is None
        assert freed.size_after_bytes == 96 * MB

    def test_an_unreadable_after_reading_gives_no_numbers_at_all(self) -> None:
        freed = self._freed(_cleanup(), CleanupSizeCache(), CleanupSize("ready", 1240 * MB, ""), "")

        assert freed == cleanup_measure.NOTHING_MEASURED

    def test_the_docker_sibling_is_dropped_rather_than_guessed(self) -> None:
        """docker_prune and docker_prune_all read the same reclaimable figure.

        Running one changes the other, and nothing sized the other around this
        command — so its entry goes and its next detect scans.
        """
        cache = CleanupSizeCache()
        cache.set_result("cleanup:docker_prune_all", 8000 * MB)

        self._freed(
            _cleanup("cleanup:docker_prune", "docker"),
            cache,
            CleanupSize("ready", 5000 * MB, ""),
            "ready|120 MB",
        )

        assert cache.get("cleanup:docker_prune_all") is None
        assert cache.get("cleanup:docker_prune") is not None, (
            "the cleanup that was measured keeps its fresh reading; only the "
            "sibling nobody measured loses its stale one"
        )


class TestMeasuringAFolderTargetInProcess:
    """The instrument for a cleanup whose target is a folder: a walk, no process.

    Measured on 2026-09-10: the one-session PowerShell batch answered for 17
    types in 13 406-16 991 ms under game load, and a walk of the same targets in
    this process answered in 209-525 ms. What that removes from a cleanup Run is
    two of its three PowerShell processes, since the before and after readings
    were two of them.
    """

    @staticmethod
    def _setting(cleanup_type: str = "pip_cache"):
        return _cleanup(f"cleanup:{cleanup_type}", cleanup_type)

    def test_it_walks_the_folder_instead_of_starting_powershell(self, tmp_path, monkeypatch):
        from fpstune.settings.cleanup_targets import CLEANUP_TARGETS, CleanupTarget

        cache_dir = tmp_path / "Cache"
        cache_dir.mkdir()
        (cache_dir / "wheel.whl").write_bytes(b"x" * 3000)
        monkeypatch.setitem(
            CLEANUP_TARGETS, "pip_cache", CleanupTarget("pip_cache", lambda: [str(cache_dir)])
        )
        started: list[tuple] = []

        with (
            patch.object(cleanup_measure.sys, "platform", "win32"),
            patch.object(ps_batch, "_fetch_cleanup_sizes", lambda t: started.append(t) or {}),
        ):
            measured = cleanup_measure.measure_cleanup_size(self._setting())

        assert measured is not None
        assert (measured.status, measured.size_bytes) == ("ready", 3000)
        assert started == [], "a folder target must not start PowerShell"

    def test_the_cache_keeps_exact_bytes_while_the_row_shows_megabytes(self, tmp_path, monkeypatch):
        """Rounding on the way in makes a 512 KB cache "0 MB", and makes a freed
        figure the subtraction of two roundings rather than of two measurements.
        """
        from fpstune.settings.cleanup_targets import CLEANUP_TARGETS, CleanupTarget

        cache_dir = tmp_path / "Cache"
        cache_dir.mkdir()
        (cache_dir / "wheel.whl").write_bytes(b"x" * (3 * 1024 * 1024 + 271))
        monkeypatch.setitem(
            CLEANUP_TARGETS, "pip_cache", CleanupTarget("pip_cache", lambda: [str(cache_dir)])
        )
        cache = CleanupSizeCache()

        with (
            patch("fpstune.settings.cleanup_cache.cleanup_size_cache", cache),
            patch.object(cleanup_measure.sys, "platform", "win32"),
        ):
            measured = cleanup_measure.measure_cleanup_size(self._setting(), remember=True)

        assert measured is not None
        assert measured.size_bytes == 3 * 1024 * 1024 + 271
        assert measured.reading == "ready|3 MB"
        entry = cache.get("cleanup:pip_cache")
        assert entry is not None
        assert entry["bytes"] == 3 * 1024 * 1024 + 271

    def test_a_measured_size_that_is_not_a_promise_shows_none_and_still_counts(self):
        """`wsl_compact`: the virtual disk file is 96 MB and a compact returns
        the slack inside it, which nothing outside the VM can read.

        So the row advertises no reclaimable size, and the pair of readings
        around the run still measures what the run reclaimed — audit finding 4.
        """
        from fpstune.settings.cleanup_targets import SizeReading

        reading = cleanup_measure.as_reading(SizeReading("not_estimated", 96 * MB))

        assert reading.status == "not_estimated"
        assert reading.reading == "ready|unavailable"

        cache = CleanupSizeCache()
        with patch("fpstune.settings.cleanup_cache.cleanup_size_cache", cache):
            cleanup_measure.store_measurement("cleanup:wsl_compact", reading)
        entry = cache.get("cleanup:wsl_compact")
        assert entry is not None and entry["status"] == "unavailable"

        freed = cleanup_measure._measured_bytes(reading)
        assert freed == 96 * MB

    def test_a_folder_that_could_not_be_read_is_not_a_folder_that_was_empty(
        self, tmp_path, monkeypatch
    ):
        """C11 rule 3, end to end: unelevated, five targets said `0 MB`."""
        from fpstune.settings.cleanup_targets import CLEANUP_TARGETS, CleanupTarget

        denied = tmp_path / "Prefetch"
        denied.mkdir()
        monkeypatch.setitem(
            CLEANUP_TARGETS,
            "pip_cache",
            CleanupTarget("pip_cache", lambda: [str(denied)], absent_is_not_installed=False),
        )

        def refuse(_path):
            raise PermissionError(13, "Access is denied")

        with (
            patch("fpstune.settings.cleanup_targets.os.scandir", refuse),
            patch.object(cleanup_measure.sys, "platform", "win32"),
        ):
            measured = cleanup_measure.measure_cleanup_size(self._setting())

        assert measured is not None
        assert (measured.status, measured.size_bytes) == ("unavailable", None)
