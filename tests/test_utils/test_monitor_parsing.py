"""What get_monitors() makes of a report row.

The defect this file exists for: ``IsActive=True`` was a hardcoded literal in
the emit line, so the parser's disconnected branch — a monitor with no current
mode but a known native resolution — was unreachable dead code, and a present-
but-inactive panel never produced a row at all. Rows now come from
``monitor_topology.build_monitor_rows`` and ``_monitor_from_row`` turns each into
a MonitorInfo; these tests pin what it does with the inactive ones, and that the
EDID is the only source of the native refresh rate and VRR support.
"""

from __future__ import annotations

import base64

from fpstune.utils.detect import MonitorInfo, _monitor_from_row
from fpstune.utils.monitor_topology import MonitorRow
from tests.test_utils.edid_builder import build_edid


def _row(**overrides: object) -> MonitorRow:
    base: dict[str, object] = {
        "name": r"\\.\DISPLAY5",
        "width": 2560,
        "height": 1440,
        "refresh_hz": 300,
        "primary": True,
        "native_width": 2560,
        "native_height": 1440,
        "max_refresh_hz": 300,
        "friendly_name": "AW2725DF",
        "hardware_id": "CCC0003",
        "is_active": True,
        "edid_b64": "",
    }
    base.update(overrides)
    return MonitorRow(**base)  # type: ignore[arg-type]


ACTIVE = _row()
INACTIVE_WITH_NATIVE = _row(
    name="AAA0001",
    width=0,
    height=0,
    refresh_hz=0,
    primary=False,
    native_width=1920,
    native_height=1200,
    max_refresh_hz=0,
    friendly_name="Internal Panel",
    hardware_id="AAA0001",
    is_active=False,
)
INACTIVE_ID_ONLY = _row(
    name="BBB0002",
    width=0,
    height=0,
    refresh_hz=0,
    primary=False,
    native_width=0,
    native_height=0,
    max_refresh_hz=0,
    friendly_name="BBB0002",
    hardware_id="BBB0002",
    is_active=False,
)


class TestTheDisconnectedBranchIsReal:
    def test_an_inactive_panel_with_a_native_resolution_is_reported(self) -> None:
        """The branch that was dead under the hardcoded IsActive=True literal."""
        inactive = _monitor_from_row(INACTIVE_WITH_NATIVE)
        assert inactive is not None
        assert inactive.is_active is False
        assert inactive.native_width == 1920
        # Native is presented as the size when there is no current mode.
        assert inactive.width == 1920
        # No mode data was read, and none may be invented (panel.py's rule).
        assert inactive.refresh_rate_hz == 0
        assert inactive.max_refresh_rate_hz == 0

    def test_a_panel_with_only_an_identity_still_reaches_the_report(self) -> None:
        """WMI naming a panel is a fact; reporting no modes does not erase it."""
        monitor = _monitor_from_row(INACTIVE_ID_ONLY)
        assert monitor is not None
        assert monitor.hardware_id == "BBB0002"
        assert monitor.is_active is False

    def test_a_row_with_neither_size_nor_identity_is_nothing(self) -> None:
        """A head with no mode, no native size and no panel id has nothing to say."""
        assert (
            _monitor_from_row(
                _row(width=0, height=0, native_width=0, native_height=0, hardware_id="")
            )
            is None
        )

    def test_an_active_panel_parses_as_before(self) -> None:
        active = _monitor_from_row(ACTIVE)
        assert active is not None
        assert active.is_active is True
        assert active.is_primary is True
        assert active.max_refresh_rate_hz == 300
        assert active.hardware_id == "CCC0003"


class TestTheEdidIsTheOnlySourceOfNativeRefreshAndVrr:
    def test_native_refresh_can_differ_from_the_mode_list_maximum(self) -> None:
        """The A4 gate: the two fields answer different questions.

        The mode list reaches 300 through an overclocked mode; the panel's own
        preferred timing says 144. Before this change the native field was
        assigned the max, so this difference could never exist.
        """
        edid = base64.b64encode(
            build_edid(width=2560, height=1440, refresh=144, freesync_block=True)
        ).decode()
        monitor = _monitor_from_row(_row(edid_b64=edid))
        assert monitor is not None
        assert monitor.native_refresh_rate_hz == 144
        assert monitor.max_refresh_rate_hz == 300
        assert monitor.supports_vrr is True

    def test_no_edid_means_unknown_never_a_copy_of_max(self) -> None:
        monitor = _monitor_from_row(ACTIVE)
        assert monitor is not None
        assert monitor.native_refresh_rate_hz == 0  # serialized as None
        assert monitor.supports_vrr is None

    def test_a_corrupt_edid_means_unknown_too(self) -> None:
        monitor = _monitor_from_row(_row(edid_b64="not-base64!!"))
        assert monitor is not None
        assert monitor.native_refresh_rate_hz == 0
        assert monitor.supports_vrr is None


class TestOptimalJudgesAgainstTheCeiling:
    def test_a_panel_below_its_mode_list_max_is_not_optimal(self) -> None:
        """The dev machine's real state: a 300 Hz panel driven at 120, whose
        EDID *prefers* 60. Judged against the preferred rate, 120 >= 60 reads
        as optimal and the product stops offering the panel's own 300."""
        misdriven = MonitorInfo(
            name=r"\\.\DISPLAY5",
            width=2560,
            height=1440,
            refresh_rate_hz=120,
            is_primary=True,
            native_refresh_rate_hz=60,
            max_refresh_rate_hz=300,
        )
        assert misdriven.is_refresh_optimal is False
