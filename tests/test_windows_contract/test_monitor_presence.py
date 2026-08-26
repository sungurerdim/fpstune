"""Which panels exist, which are on the desktop, and which is primary.

The defect this file exists for: presence used to be AllScreens' answer and
activity a hardcoded ``IsActive=True``, so a panel that was present but not on
the desktop either vanished from the report entirely or — worse, through the
deleted index-zip — shifted every other panel's identity by one. WMI cannot
arbitrate: it reports ``Active=True`` for a panel that is not on the desktop
(measured on the dev machine, whose internal panel WMI lists as active while
``EnumDisplayDevices`` reports StateFlags 0x0 for its head).

``Split-MonitorPresence`` decides from StateFlags — bit 0 attachment, bit 2
primary, bit 3 a mirroring pseudo-device that renders nothing — and reports a
panel WMI knows but no attached head carries as present-but-inactive, never
silently dropping it.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.utils.detect import _CORRELATE_MONITORS_PS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

INTERNAL = {"uid": "1001", "hwId": "AAA0001"}
EXTERNAL_144 = {"uid": "5002", "hwId": "BBB0002"}
EXTERNAL_300 = {"uid": "9003", "hwId": "CCC0003"}

_GUID = "{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"

# stateFlags: 5 = attached | primary, 1 = attached, 0 = present but not on the
# desktop, 9 = attached | mirroring driver.
RECORDS = [
    rf"\\.\DISPLAY1|1|\\?\DISPLAY#BBB0002#4&1b2c3d4e&0&UID5002#{_GUID}",
    rf"\\.\DISPLAY5|5|\\?\DISPLAY#CCC0003#4&1b2c3d4e&0&UID9003#{_GUID}",
    rf"\\.\DISPLAY2|0|\\?\DISPLAY#AAA0001#4&1b2c3d4e&0&UID1001#{_GUID}",
]

_DRIVER = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
$uidToHwId = @{}
foreach ($m in $FpsFake.wmi) { $uidToHwId[[string]$m.uid] = [string]$m.hwId }
"""

_CALL_AND_EMIT = r"""
$p = Split-MonitorPresence -adapterRecords ([string[]]$FpsFake.records) `
    -uidToHwId $uidToHwId `
    -wmiAllHwIds ([string[]]($FpsFake.wmi | ForEach-Object { [string]$_.hwId }))
$a = (@($p.Attached) | Sort-Object {$_.Name} | ForEach-Object { "$($_.Name)=$($_.HwId),$($_.Primary)" }) -join ';'
$i = (@($p.Inactive) | Sort-Object {$_.Name} | ForEach-Object { "$($_.Name)=$($_.HwId)" }) -join ';'
Write-Output "A[$a] I[$i]"
"""


def _presence(wmi: list[dict[str, str]], records: list[str]) -> str:
    script = _DRIVER + _CORRELATE_MONITORS_PS + _CALL_AND_EMIT
    return run_shipped_command(script, {"wmi": wmi, "records": records})


class TestAttachmentIsStateFlagsAnswer:
    def test_a_non_attached_head_is_inactive_not_active(self) -> None:
        """The gate: flags 0x0 is excluded from the active list and reported."""
        answer = _presence([INTERNAL, EXTERNAL_144, EXTERNAL_300], RECORDS)
        assert answer == (
            r"A[\\.\DISPLAY1=BBB0002,False;\\.\DISPLAY5=CCC0003,True]"
            r" I[\\.\DISPLAY2=AAA0001]"
        )

    def test_primary_comes_from_bit_two_not_from_position(self) -> None:
        """DISPLAY5 is primary here — any first-entry assumption reads DISPLAY1."""
        answer = _presence([EXTERNAL_144, EXTERNAL_300], RECORDS[:2])
        assert "DISPLAY5=CCC0003,True" in answer
        assert "DISPLAY1=BBB0002,False" in answer

    def test_a_mirroring_driver_is_no_panel(self) -> None:
        """Bit 3 marks a pseudo-device; attached or not, no user sees it."""
        mirror = [rf"\\.\DISPLAYV1|9|\\?\DISPLAY#BBB0002#4&1b2c3d4e&0&UID5002#{_GUID}"]
        assert _presence([EXTERNAL_144], mirror) == "A[] I[BBB0002=BBB0002]"


class TestNothingPresentIsDropped:
    def test_a_wmi_only_panel_is_reported_present_but_inactive(self) -> None:
        """A panel WMI names with no head record at all still reaches the report."""
        answer = _presence([INTERNAL, EXTERNAL_144], RECORDS[:1])
        assert answer == r"A[\\.\DISPLAY1=BBB0002,False] I[AAA0001=AAA0001]"

    def test_an_attached_head_the_join_cannot_place_keeps_an_empty_hwid(self) -> None:
        """Correlation failure on an attached screen stays visible, never guessed."""
        stray = [rf"\\.\DISPLAY7|1|\\?\DISPLAY#ZZZ9999#4&1b2c3d4e&0&UID7777#{_GUID}"]
        answer = _presence([INTERNAL], stray)
        assert answer == r"A[\\.\DISPLAY7=,False] I[AAA0001=AAA0001]"


class TestOnePanelIsOnePanel:
    def test_several_detached_heads_carrying_one_panel_are_one_row(self) -> None:
        """Measured: an internal panel's UID shows up on every unused GPU head."""
        heads = [
            rf"\\.\DISPLAY2|0|\\?\DISPLAY#AAA0001#4&1b2c3d4e&0&UID1001#{_GUID}",
            rf"\\.\DISPLAY3|0|\\?\DISPLAY#AAA0001#4&1b2c3d4e&0&UID1001#{_GUID}",
            rf"\\.\DISPLAY4|0|\\?\DISPLAY#AAA0001#4&1b2c3d4e&0&UID1001#{_GUID}",
        ]
        assert _presence([INTERNAL], heads) == r"A[] I[\\.\DISPLAY2=AAA0001]"

    def test_a_stale_head_cannot_demote_a_panel_that_is_live_elsewhere(self) -> None:
        """A detached head keeps the last-known path of whatever was once on it;
        the panel it names may be rendering right now on another head."""
        records = [
            rf"\\.\DISPLAY9|0|\\?\DISPLAY#BBB0002#4&1b2c3d4e&0&UID5002#{_GUID}",
            RECORDS[0],  # the same panel, attached on DISPLAY1
        ]
        assert _presence([EXTERNAL_144], records) == r"A[\\.\DISPLAY1=BBB0002,False] I[]"
