"""What get_monitors() makes of the detection script's report.

The defect this file exists for: ``IsActive=True`` was a hardcoded literal in
the emit line, so the parser's disconnected branch — a monitor with no current
mode but a known native resolution — was unreachable dead code, and a present-
but-inactive panel never produced a row at all. The script now emits inactive
rows; these tests pin what the parser does with them.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from types import SimpleNamespace

import pytest

from fpstune.utils.detect import get_monitors
from tests.test_utils.edid_builder import build_edid

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

ACTIVE = (
    "Monitor=\\\\.\\DISPLAY5|Width=2560|Height=1440|Refresh=300|Primary=True"
    "|NativeW=2560|NativeH=1440|NativeRefresh=300|MaxRefresh=300"
    "|FriendlyName=AW2725DF|MonitorId=CCC0003|SupportsVRR=True|IsActive=True"
)
INACTIVE_WITH_NATIVE = (
    "Monitor=AAA0001|Width=0|Height=0|Refresh=0|Primary=False"
    "|NativeW=1920|NativeH=1200|NativeRefresh=0|MaxRefresh=0"
    "|FriendlyName=Internal Panel|MonitorId=AAA0001|SupportsVRR=False|IsActive=False"
)
INACTIVE_ID_ONLY = (
    "Monitor=BBB0002|Width=0|Height=0|Refresh=0|Primary=False"
    "|NativeW=0|NativeH=0|NativeRefresh=0|MaxRefresh=0"
    "|FriendlyName=BBB0002|MonitorId=BBB0002|SupportsVRR=False|IsActive=False"
)


def _detect(monkeypatch: pytest.MonkeyPatch, *lines: str) -> list:
    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="\n".join(lines) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return get_monitors()


class TestTheDisconnectedBranchIsReal:
    def test_an_inactive_panel_with_a_native_resolution_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The branch that was dead under the hardcoded IsActive=True literal."""
        monitors = _detect(monkeypatch, ACTIVE, INACTIVE_WITH_NATIVE)
        assert len(monitors) == 2
        inactive = monitors[1]
        assert inactive.is_active is False
        assert inactive.native_width == 1920
        # The parser presents native as the size when there is no current mode.
        assert inactive.width == 1920
        # No mode data was read, and none may be invented (panel.py's rule).
        assert inactive.refresh_rate_hz == 0
        assert inactive.max_refresh_rate_hz == 0

    def test_a_panel_with_only_an_identity_still_reaches_the_report(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WMI naming a panel is a fact; reporting no modes does not erase it."""
        monitors = _detect(monkeypatch, INACTIVE_ID_ONLY)
        assert len(monitors) == 1
        assert monitors[0].hardware_id == "BBB0002"
        assert monitors[0].is_active is False

    def test_an_active_panel_parses_as_before(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitors = _detect(monkeypatch, ACTIVE)
        assert len(monitors) == 1
        active = monitors[0]
        assert active.is_active is True
        assert active.is_primary is True
        assert active.max_refresh_rate_hz == 300
        assert active.hardware_id == "CCC0003"


class TestTheEdidIsTheOnlySourceOfNativeRefreshAndVrr:
    def test_native_refresh_can_differ_from_the_mode_list_maximum(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The A4 gate: the two fields answer different questions.

        The mode list reaches 300 through an overclocked mode; the panel's own
        preferred timing says 144. Before this change the native field was
        assigned the max, so this difference could never exist.
        """
        edid = base64.b64encode(
            build_edid(width=2560, height=1440, refresh=144, freesync_block=True)
        ).decode()
        line = ACTIVE + f"|Edid={edid}"
        monitor = _detect(monkeypatch, line)[0]
        assert monitor.native_refresh_rate_hz == 144
        assert monitor.max_refresh_rate_hz == 300
        assert monitor.supports_vrr is True

    def test_no_edid_means_unknown_never_a_copy_of_max(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monitor = _detect(monkeypatch, ACTIVE)[0]
        assert monitor.native_refresh_rate_hz == 0  # serialized as None
        # The fixture line still carries the old SupportsVRR=True key; the
        # parser must not read the deleted guess.
        assert monitor.supports_vrr is None

    def test_a_corrupt_edid_means_unknown_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monitor = _detect(monkeypatch, ACTIVE + "|Edid=not-base64!!")[0]
        assert monitor.native_refresh_rate_hz == 0
        assert monitor.supports_vrr is None


class TestOptimalJudgesAgainstTheCeiling:
    def test_a_panel_below_its_mode_list_max_is_not_optimal(self) -> None:
        """The dev machine's real state: a 300 Hz panel driven at 120, whose
        EDID *prefers* 60. Judged against the preferred rate, 120 >= 60 reads
        as optimal and the product stops offering the panel's own 300."""
        from fpstune.utils.detect import MonitorInfo

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
