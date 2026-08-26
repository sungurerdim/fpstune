"""What get_monitors() makes of the detection script's report.

The defect this file exists for: ``IsActive=True`` was a hardcoded literal in
the emit line, so the parser's disconnected branch — a monitor with no current
mode but a known native resolution — was unreachable dead code, and a present-
but-inactive panel never produced a row at all. The script now emits inactive
rows; these tests pin what the parser does with them.
"""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from fpstune.utils.detect import get_monitors

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
