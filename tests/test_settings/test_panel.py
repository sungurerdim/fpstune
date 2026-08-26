"""The one panel derivation, now that inactive panels reach the monitor list.

The defect this file exists for: ``primary_monitor``'s fallback was
``monitors[0]``, written when every entry in the list was on the desktop. The
detection now reports present-but-inactive panels too, and a panel that is not
rendering anything must never become the thing frame caps are derived from —
a laptop's parked internal 60 Hz panel chosen as "the" panel would cap a
300 Hz external at a fifth of its ceiling.
"""

from __future__ import annotations

from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz
from fpstune.utils.detect import MonitorInfo


def _monitor(**overrides: object) -> MonitorInfo:
    fields: dict = {
        "name": r"\\.\DISPLAY1",
        "width": 2560,
        "height": 1440,
        "refresh_rate_hz": 300,
        "is_primary": False,
        "native_width": 2560,
        "native_height": 1440,
        "native_refresh_rate_hz": 300,
        "max_refresh_rate_hz": 300,
        "is_active": True,
        "hardware_id": "CCC0003",
    }
    fields.update(overrides)
    return MonitorInfo(**fields)


class TestInactivePanelsAreFactsNotTargets:
    def test_an_inactive_panel_is_never_the_primary(self) -> None:
        """First in the list and flagged primary — still not a rendering target."""
        parked = _monitor(name="AAA0001", is_active=False, is_primary=True, hardware_id="AAA0001")
        active = _monitor(name=r"\\.\DISPLAY5")
        chosen = primary_monitor([parked, active])
        assert chosen is active

    def test_only_inactive_panels_means_no_panel(self) -> None:
        """Nothing is rendering, so there is nothing to derive from — not 60."""
        parked = _monitor(name="AAA0001", is_active=False, hardware_id="AAA0001")
        assert primary_monitor([parked]) is None

    def test_the_flag_still_decides_among_active_panels(self) -> None:
        second = _monitor(name=r"\\.\DISPLAY5", is_primary=True)
        assert primary_monitor([_monitor(), second]) is second

    def test_the_fallback_is_the_first_active_entry(self) -> None:
        first_active = _monitor(name=r"\\.\DISPLAY1")
        assert primary_monitor([first_active, _monitor(name=r"\\.\DISPLAY5")]) is first_active


class TestAnUnknownRateStaysZero:
    def test_a_panel_that_reported_nothing_yields_zero(self) -> None:
        silent = _monitor(max_refresh_rate_hz=0, native_refresh_rate_hz=0)
        assert refresh_ceiling_hz(silent) == 0
