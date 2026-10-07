"""Hardware is told from software by the driver's numbers, on a Windows that is not English.

The adapter filters used to refuse "Virtual", "Miniport", "Hyper-V", "Bluetooth" and
friends by matching a word in `InterfaceDescription` / `FriendlyName`. Windows
translates those descriptions (a Turkish Windows prints "Kisisel Alan Agi" for the
Bluetooth PAN and "Sanal" for virtual), so on every language but English the filter
quietly stops filtering. `HardwareInterface`, `Virtual` and `NdisPhysicalMedium` are
a boolean, a boolean and an enum: nothing to translate.

Each test runs the PowerShell fpstune ships (the three inventory/probe/DNS entry
points) against a fake `Get-NetAdapter` whose rows carry Turkish names, and asserts
which adapters come out. Nothing here names an adapter by its words; the names are
there to prove they no longer matter.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from tests.test_windows_contract.conftest import fake_adapters, run_shipped_script

from fpstune.settings.discovery.probes import HardwareProbes
from fpstune.utils.adapter_filter import PHYSICAL_ADAPTER

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

# Names a Turkish Windows prints. None of them contains a word the old filters knew
# ("Virtual", "Miniport", "Hyper-V", "Bluetooth", "Loopback", "Wi-Fi Direct"), which is
# the point: only the driver's flags and medium can classify these.
PHYSICAL_NIC = {
    "ifIndex": 4,
    "name": "Ethernet",
    "description": "Realtek PCIe GbE Aile Denetleyicisi",
}
HYPER_V_SWITCH = {
    "ifIndex": 7,
    "name": "vEthernet (Varsayılan Anahtar)",
    "description": "Sanal Ethernet Bağdaştırıcısı",
    "virtual": True,
}
BLUETOOTH_PAN = {
    "ifIndex": 9,
    "name": "Bluetooth Ağ Bağlantısı",
    "description": "Kişisel Alan Ağı Aygıtı",
    "medium": 10,  # NdisPhysicalMediumBluetooth: hardware-backed, Virtual = False
}
FLAGLESS_SOFTWARE_ADAPTER = {
    "ifIndex": 12,
    "name": "Köprü",
    "description": "Ağ Köprüsü Bağdaycısı",
    "hardware": False,  # a software adapter whose NDIS virtual flag is not set
}

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw -Encoding UTF8 | ConvertFrom-Json
function Get-NetAdapter {
    [CmdletBinding()] param([switch]$IncludeHidden)
    foreach ($a in $FpsFake.adapters) {
        [pscustomobject]@{
            Name = $a.Name; ifIndex = $a.ifIndex; InterfaceIndex = $a.ifIndex
            InterfaceDescription = $a.InterfaceDescription; PnPDeviceID = ''
            MediaType = '802.3'; Virtual = $a.Virtual
            InterfaceOperationalStatus = $a.InterfaceOperationalStatus
            HardwareInterface = $a.HardwareInterface; NdisPhysicalMedium = $a.NdisPhysicalMedium
        }
    }
}
"""


def _kept(command: str, *adapters: dict[str, Any]) -> list[int]:
    """The interface indexes `command` lets through, one per output line."""
    payload = {"adapters": fake_adapters(*adapters)}
    output = run_shipped_script(_PRELUDE + command, payload)
    return sorted(int(line.split("|")[0]) for line in output.splitlines() if line.strip())


def _probe_command() -> str:
    """The PowerShell argument `HardwareProbes` hands to powershell.exe, verbatim."""
    captured: list[list[str]] = []

    def fake_run(argv: list[str], *_args: Any, **_kwargs: Any) -> SimpleNamespace:
        captured.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("fpstune.settings.discovery.probes.process_watch.run", fake_run):
        HardwareProbes()._query_active_adapters()
    assert captured, "the probe never ran its command"
    return captured[0][-1]


ADAPTERS = (PHYSICAL_NIC, HYPER_V_SWITCH, BLUETOOTH_PAN, FLAGLESS_SOFTWARE_ADAPTER)


class TestTheSharedPredicate:
    def test_only_the_physical_nic_passes_with_every_name_turkish(self) -> None:
        command = f'Get-NetAdapter | Where-Object {{ {PHYSICAL_ADAPTER} }} | ForEach-Object {{ "$($_.ifIndex)|" }}'
        assert _kept(command, *ADAPTERS) == [PHYSICAL_NIC["ifIndex"]]

    def test_a_usb_dock_nic_with_a_translated_name_is_still_physical(self) -> None:
        """The reason the filter is not `-Physical` + name checks: a dock is hardware."""
        dock = {"ifIndex": 15, "name": "Ethernet 2", "description": "USB GbE Aile Denetleyicisi"}
        command = f'Get-NetAdapter | Where-Object {{ {PHYSICAL_ADAPTER} }} | ForEach-Object {{ "$($_.ifIndex)|" }}'
        assert _kept(command, dock, HYPER_V_SWITCH) == [15]


class TestEntryPointsClassifyTheSame:
    def test_the_adapter_probe_keeps_only_the_physical_nic(self) -> None:
        """`HardwareProbes._query_active_adapters` feeds per-adapter settings; a Bluetooth PAN
        or a software bridge in it would be offered tweaks it cannot take."""
        assert _kept(_probe_command(), *ADAPTERS) == [PHYSICAL_NIC["ifIndex"]]

    def test_the_probe_command_carries_no_adapter_name_filter(self) -> None:
        assert "-notlike" not in _probe_command()
