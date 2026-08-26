"""The DeviceName → monitor-hwId correlation — the map every ceiling hangs from.

The defect this file exists for: the shipped correlation had two methods. Method 1
called ``EnumDisplayDevices`` from PowerShell with ``[ref]`` and returned nothing
on every machine — probed live, the identical Win32 call returns every adapter
from a loop inside the C# class and returns ``False`` with an empty name through
PowerShell's ``[ref]`` binding, so the method was dead code from the day it
shipped. Method 2 then zipped screens sorted by DISPLAY number against WMI ids
sorted by UID — order-based, and wrong the moment a laptop's internal panel
carries the lowest UID (the common case): every entry shifts by one, a 300 Hz
panel is handed its 144 Hz neighbour's identity, ``Get-MaxHz`` runs against the
wrong mode table, and every downstream cap follows. A ceiling loss reported as
success.

The fix moves the enumeration loop inside the C# class and deletes the fallback
entirely — a map the join cannot build stays empty, which is visible, where a
plausible wrong map reports success. These tests run the shipped
``Build-DeviceHwIdMap`` verbatim against described hosts, and keep the old zip
in the file to show it got the same host wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

import fpstune.utils.detect
from fpstune.utils.detect import _CORRELATE_MONITORS_PS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

# A laptop-shaped host. The internal panel carries the LOWEST UID and is not
# attached to the desktop (stateFlags 0); the 300 Hz external is the primary
# (flags 5 = attached | primary), the 144 Hz external is plain attached (1).
INTERNAL = {"uid": "1001", "hwId": "AAA0001"}
EXTERNAL_144 = {"uid": "5002", "hwId": "BBB0002"}
EXTERNAL_300 = {"uid": "9003", "hwId": "CCC0003"}

_GUID = "{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"

# What DisplayDevices.EnumerateAdapters() emits: "deviceName|stateFlags|interfacePath".
RECORDS = [
    rf"\\.\DISPLAY1|1|\\?\DISPLAY#BBB0002#4&1b2c3d4e&0&UID5002#{_GUID}",
    rf"\\.\DISPLAY5|5|\\?\DISPLAY#CCC0003#4&1b2c3d4e&0&UID9003#{_GUID}",
    rf"\\.\DISPLAY2|0|\\?\DISPLAY#AAA0001#4&1b2c3d4e&0&UID1001#{_GUID}",
]

# The join is by identity, so this is the answer for every input order.
EXPECTED = r"\\.\DISPLAY1=BBB0002;\\.\DISPLAY2=AAA0001;\\.\DISPLAY5=CCC0003"

_DRIVER = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
$uidToHwId = @{}
foreach ($m in $FpsFake.wmi) { $uidToHwId[[string]$m.uid] = [string]$m.hwId }
"""

_EMIT = r"""
$out = ($map.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ';'
if (-not $out) { $out = 'EMPTY' }
Write-Output $out
"""

_CALL_SHIPPED = (
    "\n$map = Build-DeviceHwIdMap -adapterRecords ([string[]]$FpsFake.records) "
    "-uidToHwId $uidToHwId\n"
)

# The fallback as it shipped, kept so the fix can be shown to change the answer
# rather than merely to pass. Adapted only in its input: AllScreens is a .NET
# static the harness cannot shadow, so the described host supplies the attached
# screen names — the sort and the zip are the shipped lines.
_PREVIOUS_FALLBACK = r"""
$wmiHwIds = @($FpsFake.wmi | Sort-Object {[int]$_.uid} | ForEach-Object { $_.hwId })
$screensByNum = @($FpsFake.screens |
    Sort-Object @{Expression={
        if ($_ -match 'DISPLAY(\d+)') { [int]$Matches[1] } else { 0 }
    }})
$map = @{}
for ($i = 0; $i -lt $screensByNum.Count -and $i -lt $wmiHwIds.Count; $i++) {
    $sDevName = $screensByNum[$i].TrimEnd([char]0, ' ')
    if (-not $map.ContainsKey($sDevName)) {
        $map[$sDevName] = $wmiHwIds[$i]
    }
}
"""


def _correlate(wmi_order: list[dict[str, str]], records: list[str]) -> str:
    script = _DRIVER + _CORRELATE_MONITORS_PS + _CALL_SHIPPED + _EMIT
    return run_shipped_command(script, {"wmi": wmi_order, "records": records})


class TestTheJoinIsByIdentity:
    def test_every_screen_maps_to_its_own_panel(self) -> None:
        assert _correlate([INTERNAL, EXTERNAL_144, EXTERNAL_300], RECORDS) == EXPECTED

    def test_wmi_order_cannot_change_the_map(self) -> None:
        """The gate: the exact property the deleted fallback violated."""
        orders = (
            [EXTERNAL_300, EXTERNAL_144, INTERNAL],
            [EXTERNAL_144, INTERNAL, EXTERNAL_300],
        )
        for order in orders:
            assert _correlate(order, RECORDS) == EXPECTED

    def test_screen_order_cannot_change_the_map_either(self) -> None:
        shuffled = [RECORDS[2], RECORDS[0], RECORDS[1]]
        assert _correlate([INTERNAL, EXTERNAL_144, EXTERNAL_300], shuffled) == EXPECTED


class TestThePreviousFallbackGotThisHostWrong:
    def test_the_internal_panel_shifts_every_external_by_one(self) -> None:
        """Same host, described the way the old zip consumed it.

        AllScreens carried only the two attached externals; WMI carried all
        three panels sorted by UID with the internal first. The zip hands
        DISPLAY1 the internal's identity and DISPLAY5 — the 300 Hz panel — its
        144 Hz neighbour's, which is the mode table Get-MaxHz then reads.
        """
        answer = run_shipped_command(
            _DRIVER + _PREVIOUS_FALLBACK + _EMIT,
            {
                "wmi": [INTERNAL, EXTERNAL_144, EXTERNAL_300],
                "screens": [r"\\.\DISPLAY1", r"\\.\DISPLAY5"],
            },
        )
        assert answer == r"\\.\DISPLAY1=AAA0001;\\.\DISPLAY5=BBB0002"


class TestFailureStaysVisible:
    def test_an_unknown_uid_stays_unmapped(self) -> None:
        """A UID WMI never reported is a correlation failure, not a guess."""
        stray = [rf"\\.\DISPLAY7|1|\\?\DISPLAY#ZZZ9999#4&1b2c3d4e&0&UID7777#{_GUID}"]
        assert _correlate([INTERNAL], stray) == "EMPTY"

    def test_an_adapter_without_a_monitor_stays_unmapped(self) -> None:
        """An adapter head with nothing plugged in emits no interface path."""
        headless = [r"\\.\DISPLAY3|0|"]
        assert _correlate([INTERNAL], headless) == "EMPTY"


class TestTheShippedScriptHasNoPositionalPath:
    def test_the_zip_and_its_inputs_are_gone(self) -> None:
        """The fallback must not return: a wrong map is worse than an empty one."""
        source = Path(fpstune.utils.detect.__file__).read_text(encoding="utf-8")
        assert "$wmiHwIds" not in source
        assert "$screensByNum" not in source

    def test_the_enumeration_loop_is_not_called_through_the_ref_binder(self) -> None:
        """PowerShell's [ref] binding of DISPLAY_DEVICE is the proven failure."""
        source = Path(fpstune.utils.detect.__file__).read_text(encoding="utf-8")
        assert "[ref]$ad" not in source
        assert "[ref]$mo" not in source
        assert "EnumerateAdapters" in source
        assert "Build-DeviceHwIdMap" in source
