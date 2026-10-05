"""Every monitor at its own native mode, the primary recommended, the rest optional.

The fix used to be a Hardware-panel button only: Home never listed a secondary
monitor left at 60 Hz, nothing put it in a bulk apply, nothing recorded it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.settings import display_mode
from fpstune.settings.base import Reading, SettingScope
from fpstune.settings.display_mode import (
    DM_DISPLAYFREQUENCY,
    DM_PELSHEIGHT,
    DM_PELSWIDTH,
    monitor_key,
    plan_for,
)
from fpstune.utils.detect import MonitorInfo
from fpstune.utils.winapi.display import DisplayMode


def _monitor(**overrides) -> MonitorInfo:
    values = {
        "name": "\\\\.\\DISPLAY1",
        "width": 2560,
        "height": 1440,
        "refresh_rate_hz": 165,
        "is_primary": True,
        "friendly_name": "Primary Panel",
        "native_width": 2560,
        "native_height": 1440,
        "native_refresh_rate_hz": 60,
        "max_refresh_rate_hz": 165,
        "hardware_id": "ABC1234",
    }
    values.update(overrides)
    return MonitorInfo(**values)


@pytest.fixture(autouse=True)
def _no_stray_reverts():
    yield
    with display_mode._pending_lock:
        for pending in display_mode._pending_reverts.values():
            pending["timer"].cancel()
        display_mode._pending_reverts.clear()


class TestOnlyWhatIsWrongIsWritten:
    def test_a_low_refresh_writes_only_the_refresh(self) -> None:
        plan = plan_for(_monitor(refresh_rate_hz=60))
        assert plan.fields == DM_DISPLAYFREQUENCY
        assert plan.refresh == 165, "the mode-list ceiling, not the EDID's preferred 60"

    def test_a_lowered_resolution_writes_only_the_resolution(self) -> None:
        plan = plan_for(_monitor(width=1920, height=1080))
        assert plan.fields == DM_PELSWIDTH | DM_PELSHEIGHT

    def test_a_native_monitor_needs_nothing(self) -> None:
        assert not plan_for(_monitor()).needed


class TestIdentity:
    def test_two_identical_models_get_two_keys(self) -> None:
        a = _monitor(name="\\\\.\\DISPLAY1")
        b = _monitor(name="\\\\.\\DISPLAY2", is_primary=False)
        assert monitor_key(a, [a, b]) != monitor_key(b, [a, b])

    def test_the_key_does_not_follow_windows_renumbering(self) -> None:
        """DISPLAY1 can become DISPLAY3 after a cable change; the key must not."""
        before = _monitor(name="\\\\.\\DISPLAY1")
        after = _monitor(name="\\\\.\\DISPLAY3")
        assert monitor_key(before, [before]) == monitor_key(after, [after])


class TestOneSettingPerMonitor:
    def _register(self, monitors: list[MonitorInfo]) -> dict:
        from fpstune.settings.discovery.display import discover_monitor_modes
        from fpstune.settings.registry import SettingsRegistry

        registry = SettingsRegistry(discover_dynamic=False)
        with patch(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            return_value=monitors,
        ):
            discover_monitor_modes(registry, None)  # type: ignore[arg-type]
        return {s.subject: s for s in registry.get_all() if s.id.endswith(":mode")}

    def test_the_primary_is_recommended_and_every_other_monitor_optional(self) -> None:
        primary = _monitor()
        side = _monitor(
            name="\\\\.\\DISPLAY2",
            is_primary=False,
            friendly_name="Side Panel",
            hardware_id="XYZ9876",
            refresh_rate_hz=60,
            max_refresh_rate_hz=144,
        )
        rows = self._register([primary, side])
        assert rows["Primary Panel"].scope is SettingScope.RECOMMENDED
        assert rows["Side Panel"].scope is SettingScope.COMPLETE
        # The claim is the panel's own frame interval: 16.7 ms at 60 Hz, 6.9 at 144.
        assert rows["Side Panel"].impact_scores["latency_ms"] == pytest.approx(-9.7)

    def test_a_monitor_whose_native_mode_is_unknown_gets_no_setting(self) -> None:
        unknown = _monitor(native_width=0, native_height=0)
        assert self._register([unknown]) == {}


class TestDetectAndApply:
    def test_the_reading_carries_the_numbers_the_row_explains(self) -> None:
        reading = display_mode.mode_reading(_monitor(refresh_rate_hz=60))
        assert isinstance(reading, Reading)
        assert reading.value == "not_native"
        assert reading.finding is not None
        assert (reading.finding["refresh_hz"], reading.finding["max_refresh_hz"]) == (60, 165)

    def test_only_the_native_mode_can_be_written(self) -> None:
        with patch.object(display_mode.sys, "platform", "win32"):
            ok, error = display_mode.display_mode_native({"monitor": "x", "value": "not_native"})
        assert ok is False and "native" in (error or "")

    def test_a_mode_the_driver_rejects_is_never_written(self) -> None:
        calls: list[bool] = []

        def change_mode(*_a, test_only):
            calls.append(test_only)
            return -2 if test_only else 0

        with (
            patch(
                "fpstune.utils.winapi.display.current_mode",
                return_value=DisplayMode(2560, 1440, 60),
            ),
            patch("fpstune.utils.winapi.display.change_mode", change_mode),
        ):
            outcome = display_mode.write_native(_monitor(refresh_rate_hz=60))
        assert outcome.kind == "testfail" and "CDS_TEST" in outcome.message
        assert calls == [True], "nothing but the test may reach the driver"

    def test_a_written_mode_reverts_unless_kept(self) -> None:
        with (
            patch(
                "fpstune.utils.winapi.display.current_mode",
                return_value=DisplayMode(2560, 1440, 60),
            ),
            patch("fpstune.utils.winapi.display.change_mode", return_value=0),
        ):
            outcome = display_mode.write_native(_monitor(refresh_rate_hz=60), "display:k:mode")
            assert outcome.kind == "written"
            assert display_mode.pending_devices() == ["\\\\.\\DISPLAY1"]
            assert display_mode.keep_all() == ["\\\\.\\DISPLAY1"]
            assert display_mode.pending_devices() == []
