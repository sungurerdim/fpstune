"""What a cleanup freed is measured around its own command, or not reported.

The figure the UI showed was assembled from two things that were never a pair:
a cached size up to five minutes old, rounded to whole MB out of a display
string, minus whatever a background re-scan happened to report some seconds
after the run. Nothing bracketed the command, so a folder that grew between the
scan and the run, or a scan that had not landed yet, produced a number with no
referent -- exactly what C11 exists to stop.

What replaces it is one instrument run twice: the shipped ``Get-CleanupStatus``
script for this cleanup's own type, immediately before the command and
immediately after it. These tests pin the three things that makes true.

  1. ``freed_bytes`` is the difference between those two readings, and exists
     only when both of them are sizes.
  2. Both routes report it -- the quiet ``POST /apply`` and the ``applied`` SSE
     event -- because both come off the same ApplyResponse.
  3. The after reading lands in the cleanup size cache, so the row shows what is
     left the moment the apply returns instead of waiting for a re-scan.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.cleanup_cache import CleanupSizeCache

MB = 1024 * 1024


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def cache() -> CleanupSizeCache:
    """A cache of this test's own, so nothing leaks between tests or into the app."""
    return CleanupSizeCache()


def _cleanup_setting(
    setting_id: str = "cleanup:dism_cleanup", cleanup_type: str = "dism"
) -> SettingExecutor:
    """A cleanup action shaped like the shipped ones: sized by its detect side.

    The type is `dism` because these tests script the *instrument*, and the one
    they can script is the PowerShell session. A cleanup whose target is a folder
    is walked in this process instead — that path has its own tests, and it is
    exercised end to end against real directories in
    `tests/test_windows_contract/test_bulk_deletes.py`.
    """
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
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command="dism_cleanup",
    )


def _registry_setting() -> SettingExecutor:
    """A setting with nothing to size: no cleanup detect, so no measurement."""
    return SettingExecutor(
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
        apply_command="Set-Something -Value '%value%'",
    )


_NOT_STUBBED = object()


@contextmanager
def _run(
    setting: SettingExecutor,
    cache: CleanupSizeCache,
    readings: list[str],
    *,
    apply_result: tuple[bool, str | None] = (True, None),
    detected: Any = _NOT_STUBBED,
) -> Iterator[SimpleNamespace]:
    """Patch a run whose size instrument answers `readings`, one call at a time.

    The seam is ``_fetch_cleanup_sizes`` — the same one PowerShell session the
    scan uses — so what these tests exercise is the real measurement path with a
    scripted instrument, not a second implementation of it. The post-apply
    detect is deliberately left real for the cleanup cases: that it reads the
    after size out of the cache is half of what is being tested. `detected`
    stubs it for the cases that are not about a cleanup at all, so a
    non-existent PowerShell command is not run to learn nothing.

    Yields the size instrument and the background re-scan, so a test can say
    both what was measured and what fpstune fell back to.
    """
    registry = MagicMock()
    registry.get.return_value = setting
    cleanup_type = str(setting.detect_args.get("type", ""))
    sizes = MagicMock(side_effect=[{cleanup_type: r} for r in readings])
    # The fallback a cleanup detect starts on a cache miss. Stubbed because the
    # real one launches PowerShell in a daemon thread; that it was started is
    # the observable behaviour a test wants.
    rescan = MagicMock()
    detect_stub = (
        contextlib.nullcontext()
        if detected is _NOT_STUBBED
        else patch(
            "fpstune.api.routes.settings.DetectionEngine.detect_one",
            return_value=SimpleNamespace(value=detected),
        )
    )

    with (
        detect_stub,
        patch("fpstune.api.routes.settings._get_registry", return_value=registry),
        patch("fpstune.api.routes.settings_stream._get_registry", return_value=registry),
        patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
        patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
        patch("fpstune.api.routes.settings._create_restore_point_async"),
        patch("fpstune.api.routes.settings_stream._create_restore_point_async"),
        patch("fpstune.utils.self_check.ensure_checked_before_first_apply"),
        patch("fpstune.settings.executors.powershell.sys.platform", "win32"),
        patch("fpstune.settings.cleanup_cache.cleanup_size_cache", cache),
        patch("fpstune.settings.executors.ps_batch._fetch_cleanup_sizes", sizes),
        patch("fpstune.settings.executors.powershell._start_bg_cleanup_detection", rescan),
        patch(
            "fpstune.api.routes.settings_apply.CommandExecutor.apply",
            return_value=apply_result,
        ),
    ):
        yield SimpleNamespace(sizes=sizes, rescan=rescan)


def _apply(client: TestClient, setting: SettingExecutor, value: Any = True) -> dict[str, Any]:
    result = client.post(f"/api/settings/{setting.id}/apply", json={"value": value})
    assert result.status_code == 200, result.text
    body: dict[str, Any] = result.json()
    return body


class TestFreedIsTheDifferenceBetweenTwoReadings:
    """The number the user sees is the one the instrument produced, twice."""

    def test_the_two_readings_around_the_command_are_what_is_reported(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        setting = _cleanup_setting()

        with _run(setting, cache, ["ready|1240 MB", "ready|96 MB"]) as run:
            body = _apply(client, setting)

        assert body["success"] is True
        assert body["freed_bytes"] == (1240 - 96) * MB
        assert body["size_after_bytes"] == 96 * MB
        # Once before the command and once after it, each asking about this
        # cleanup's own type and nothing else.
        assert [call.args[0] for call in run.sizes.call_args_list] == [("dism",), ("dism",)]

    def test_a_target_that_grew_during_the_run_reports_nothing_freed(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """A running process writes into %TEMP% while the cleanup deletes from it.

        Both readings are real, so the answer is measured: this run freed
        nothing the disk kept. It is never a negative figure presented as a gain.
        """
        setting = _cleanup_setting()

        with _run(setting, cache, ["ready|100 MB", "ready|140 MB"]):
            body = _apply(client, setting)

        assert body["freed_bytes"] == 0
        assert body["size_after_bytes"] == 140 * MB

    def test_an_unavailable_reading_reports_no_number_at_all(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """Docker's engine is down, so nothing sized the target. C11 rule 3:
        "could not be measured" is said, never rendered as 0."""
        setting = _cleanup_setting("cleanup:docker_prune", "docker")

        with _run(setting, cache, ["ready|unavailable", "ready|unavailable"]):
            body = _apply(client, setting)

        assert body["success"] is True
        assert body["freed_bytes"] is None
        assert body["size_after_bytes"] is None

    def test_one_missing_half_of_the_pair_reports_no_difference(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """A subtraction with one operand is not a measurement.

        The after reading is still a size, so it is reported on its own; the
        difference is not, because nothing was read to subtract from.
        """
        setting = _cleanup_setting()

        with _run(setting, cache, ["", "ready|96 MB"]):
            body = _apply(client, setting)

        assert body["freed_bytes"] is None
        assert body["size_after_bytes"] == 96 * MB

    def test_a_setting_with_nothing_to_size_is_never_sized(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """The measurement costs a PowerShell session and up to 42 s. A registry
        tweak must not pay either, and must not report a disk figure."""
        setting = _registry_setting()

        with _run(setting, cache, [], detected="off") as run:
            body = _apply(client, setting, "off")

        assert body["freed_bytes"] is None
        assert body["size_after_bytes"] is None
        run.sizes.assert_not_called()

    def test_a_failed_command_is_not_sized_afterwards(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """Nothing ran, so there is nothing to report and nothing to re-read."""
        setting = _cleanup_setting()

        with _run(
            setting,
            cache,
            ["ready|1240 MB"],
            apply_result=(False, "PowerShell failed: access denied"),
        ) as run:
            body = _apply(client, setting)

        assert body["success"] is False
        assert body["freed_bytes"] is None
        assert body["size_after_bytes"] is None
        assert run.sizes.call_count == 1

    def test_a_cleanup_told_not_to_run_is_never_sized(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """A cleanup's reset writes False, which an action reads as "do not run".

        Sizing a folder twice around a command that never happens costs two
        scans -- up to 42 s each -- to report that nothing was freed, which is
        both a lie and the slowest possible way to tell it.
        """
        setting = _cleanup_setting()
        cache.set_result(setting.id, 500 * MB)

        with _run(setting, cache, []) as run:
            result = client.post(f"/api/settings/{setting.id}/reset")

        assert result.status_code == 200
        body = result.json()
        assert body["success"] is True
        assert body["freed_bytes"] is None
        assert body["size_after_bytes"] is None
        run.sizes.assert_not_called()
        # Nothing ran, so what the row shows is still true.
        entry = cache.get(setting.id)
        assert entry is not None
        assert entry["bytes"] == 500 * MB


class TestTheAfterReadingIsWhatTheRowThenShows:
    """The size the command left behind, without waiting for a re-scan."""

    def test_the_cache_carries_the_after_reading(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        setting = _cleanup_setting()

        with _run(setting, cache, ["ready|1240 MB", "ready|96 MB"]):
            body = _apply(client, setting)

        entry = cache.get(setting.id)
        assert entry is not None, "the entry was dropped, so the row spins on a re-scan"
        assert entry["status"] == "ready"
        assert entry["bytes"] == 96 * MB
        # And the post-apply detect served it, so the row updates on the response.
        # Lower-cased on the way out by the detection engine's own
        # normalisation; the size is the after reading either way.
        assert str(body["new_value"]).lower() == "ready|96 mb"

    def test_an_unreadable_after_measurement_drops_the_stale_size(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """The pre-cleanup figure is wrong the moment the command succeeds.

        Keeping it would have the row claim space that has already gone, which
        is worse than the spinner a dropped entry produces.
        """
        setting = _cleanup_setting()
        cache.set_result(setting.id, 1240 * MB)

        with _run(setting, cache, ["ready|1240 MB", ""]) as run:
            _apply(client, setting)

        entry = cache.get(setting.id)
        assert entry is None or entry["status"] != "ready" or entry["bytes"] != 1240 * MB
        # And the row falls back to what it did before: a fresh background scan.
        run.rescan.assert_called_once()

    def test_the_docker_sibling_is_dropped_rather_than_guessed(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """docker_prune and docker_prune_all read the same reclaimable figure.

        Running one changes the other, and nothing measured the other around
        this command -- so its entry goes, and its next detect scans.
        """
        setting = _cleanup_setting("cleanup:docker_prune", "docker")
        cache.set_result("cleanup:docker_prune_all", 8000 * MB)

        with _run(setting, cache, ["ready|5000 MB", "ready|120 MB"]):
            body = _apply(client, setting)

        assert body["freed_bytes"] == (5000 - 120) * MB
        assert cache.get("cleanup:docker_prune_all") is None


class TestTheStreamReportsTheSameNumbers:
    """A bulk run must not report something different from a single apply."""

    def _events(self, client: TestClient, setting: SettingExecutor) -> list[dict[str, Any]]:
        response = client.post("/api/settings/bulk/stream-apply", json={"ids": [setting.id]})
        assert response.status_code == 200
        events = []
        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                with contextlib.suppress(json.JSONDecodeError):
                    events.append(json.loads(line[len("data:") :].strip()))
        return events

    def test_the_applied_event_carries_the_measured_pair(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        setting = _cleanup_setting()

        with _run(setting, cache, ["ready|1240 MB", "ready|96 MB"]):
            events = self._events(client, setting)

        applied = next(e for e in events if e.get("event") == "applied")
        assert applied["freed_bytes"] == (1240 - 96) * MB
        assert applied["size_after_bytes"] == 96 * MB

    def test_the_keys_are_present_and_null_when_nothing_was_measured(
        self, client: TestClient, cache: CleanupSizeCache
    ) -> None:
        """The client reads the keys unconditionally; a missing key is not the
        same shape as a null one."""
        setting = _registry_setting()

        with _run(setting, cache, [], detected="off"):
            events = self._events(client, setting)

        applied = next(e for e in events if e.get("event") == "applied")
        assert applied["freed_bytes"] is None
        assert applied["size_after_bytes"] is None


class TestTheBulkRunWaitsLongEnoughForWhatItStarted:
    """A cap shorter than the work is a run abandoned while it is succeeding.

    `/bulk/apply` waited a flat 300 s for anything containing an action. On this
    machine one DISM cleanup is 43.0 s of component store analysis, the cleanup
    itself (the user timed the whole thing at about 108 s elevated, and the
    setting's own timeout is 900 s), then 34.7 s more to measure what it freed —
    so the setting most likely to need the budget was the one guaranteed not to
    get it.
    """

    def test_the_budget_covers_the_command_and_both_readings(self) -> None:
        from fpstune.api.routes.settings_apply import apply_budget_seconds

        # The command's own allowance, plus one reading either side of it. The
        # local fixture declares no per-setting timeout, so it takes the
        # known-slow default; the shipped row asks for 900 s of its own.
        assert apply_budget_seconds(_cleanup_setting()) >= 300 + 2 * 120

        from fpstune.settings.definitions import get_all_static_settings

        shipped = next(s for s in get_all_static_settings() if s.id == "cleanup:dism_cleanup")
        assert apply_budget_seconds(shipped) >= 900 + 2 * 120

    def test_a_folder_cleanup_is_not_charged_for_readings_it_no_longer_takes(self) -> None:
        """A walk of a folder costs well under a second and starts no process."""
        from fpstune.api.routes.settings_apply import apply_budget_seconds

        walked = _cleanup_setting("cleanup:pip_cache", "pip_cache")
        scripted = _cleanup_setting()

        assert apply_budget_seconds(walked) < apply_budget_seconds(scripted)

    def test_the_cap_is_derived_from_the_set_rather_than_fixed(self) -> None:
        from fpstune.api.routes.settings_apply import bulk_apply_timeout

        assert bulk_apply_timeout([]) == 60
        one_slow = bulk_apply_timeout([_cleanup_setting()])
        assert one_slow > 300, "the flat cap was shorter than one DISM cleanup"
        # A set is at least as long as its slowest member.
        mixed = bulk_apply_timeout([_cleanup_setting(), _registry_setting()])
        assert mixed >= one_slow
