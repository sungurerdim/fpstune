"""A machine fpstune has never seen answers exactly like the one it was written on.

#83 Phase 2, the device host: the same shipped commands, run against hosts whose
hardware is arranged differently from the developer's — adapter indices that do
not start at 1, a disk layout with no NVMe or with nothing but NVMe. Each test says
what would have gone wrong on that host if the command keyed on position, order or
a name instead of on the device's own identity (C5, C9). The integrated-GPU-first
host of the MSI row is in ``tests/test_executors/test_msi_mode.py``, since that row
is a Python action and no longer a shipped script.
"""

from __future__ import annotations

import json
import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command, run_shipped_script

from fpstune.api.hardware import storage
from fpstune.settings.definitions.network import create_interrupt_moderation_setting
from fpstune.utils.powershell import substitute_placeholders

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


_FAKE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
"""


# --- an adapter is addressed by its own index, whatever the order or the numbering ----

_ADAPTER_PRELUDE = (
    _FAKE
    + r"""
function Get-NetAdapter {
    [CmdletBinding()] param([int]$InterfaceIndex, [switch]$IncludeHidden, [switch]$Physical)
    foreach ($a in $FpsFake.adapters) {
        if (-not $PSBoundParameters.ContainsKey('InterfaceIndex') -or $a.ifIndex -eq $InterfaceIndex) {
            [pscustomobject]@{ Name = $a.Name; ifIndex = $a.ifIndex; InterfaceIndex = $a.ifIndex }
        }
    }
}
function Get-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([string]$Name, [string[]]$RegistryKeyword)
    foreach ($a in $FpsFake.adapters) {
        if ($a.Name -eq $Name) {
            return [pscustomobject]@{ Name = $Name; RegistryKeyword = $RegistryKeyword[0]; RegistryValue = @($a.moderation) }
        }
    }
    throw "no adapter named '$Name' on this host"
}
"""
)

SHUFFLED_ADAPTERS = [
    {"Name": "Ethernet 3", "ifIndex": 23, "moderation": "1"},
    {"Name": "Wi-Fi", "ifIndex": 4, "moderation": "0"},
    {"Name": "Ethernet", "ifIndex": 17, "moderation": "0"},
]


class TestAdaptersAreAddressedByIndex:
    @pytest.mark.parametrize(
        ("index", "expected"),
        [(23, "Enabled"), (4, "Disabled"), (17, "Disabled")],
    )
    def test_each_index_reads_its_own_adapter(self, index: int, expected: str) -> None:
        """Three adapters, indices out of order and not starting at 1. The command
        for index 23 must read adapter 23's value even though it is listed first
        and its neighbours disagree with it."""
        setting = create_interrupt_moderation_setting(index, "Test adapter")
        command = substitute_placeholders(setting.detect_command, **setting.detect_args)
        raw = run_shipped_command(_ADAPTER_PRELUDE + command, {"adapters": SHUFFLED_ADAPTERS})
        assert setting.value_map[raw] == expected

    def test_an_index_no_adapter_has_is_the_sentinel(self) -> None:
        """A stale index (the adapter was unplugged) is 'not supported', not a crash
        and not the value of whichever adapter happens to be first."""
        setting = create_interrupt_moderation_setting(99, "Gone")
        command = substitute_placeholders(setting.detect_command, **setting.detect_args)
        assert (
            run_shipped_command(_ADAPTER_PRELUDE + command, {"adapters": SHUFFLED_ADAPTERS})
            == "not_supported"
        )


# --- storage: NVMe only, SATA only, and one disk that is not a list ---------------------

_STORAGE_PRELUDE = (
    _FAKE
    + r"""
function Get-PhysicalDisk {
    foreach ($d in $FpsFake.disks) {
        [pscustomobject]@{
            DeviceId = $d.DeviceId; FriendlyName = $d.FriendlyName; MediaType = $d.MediaType
            BusType = $d.BusType; UniqueId = $d.UniqueId
        }
    }
}
function Get-Partition {
    [CmdletBinding()] param([string]$DiskNumber)
    foreach ($p in $FpsFake.partitions) {
        if ("$($p.DiskNumber)" -eq $DiskNumber) {
            [pscustomobject]@{ DriveLetter = $p.DriveLetter; Size = [int64]$p.Size }
        }
    }
}
function Get-Volume {
    [CmdletBinding()] param([string]$DriveLetter)
    [pscustomobject]@{ SizeRemaining = [int64]$FpsFake.free.$DriveLetter }
}
"""
)

GB = 1024**3

NVME = {
    "DeviceId": 0,
    "FriendlyName": "Samsung SSD 990 PRO 2TB",
    "MediaType": "SSD",
    "BusType": "NVMe",
    "UniqueId": "eui.0025385B31423456",
}
SATA_HDD = {
    "DeviceId": 0,
    "FriendlyName": "WDC WD40EZAZ-00SF3B0",
    "MediaType": "HDD",
    "BusType": "SATA",
    "UniqueId": "5000CCA0BCD12345",
}
SATA_SSD = {
    "DeviceId": 1,
    "FriendlyName": "Crucial MX500 1TB",
    "MediaType": "SSD",
    "BusType": "SATA",
    "UniqueId": "500A0751E12A3456",
}


def _drives(monkeypatch: pytest.MonkeyPatch, host: dict, trim: bool | None = True):
    def fake_run(_script: str, *_a: object, **_k: object) -> tuple[bool, str]:
        return True, run_shipped_script(_STORAGE_PRELUDE + storage._STORAGE_SCRIPT, host)

    monkeypatch.setattr(storage, "run_powershell", fake_run)
    monkeypatch.setattr(storage, "_trim_is_enabled", lambda: trim)
    return storage.get_detailed_storage_drives()


class TestStorageOnMachinesUnlikeThisOne:
    def test_an_nvme_only_machine(self, monkeypatch) -> None:
        host = {
            "disks": [NVME],
            "partitions": [
                {"DiskNumber": 0, "DriveLetter": None, "Size": 100 * 1024**2},  # EFI, no letter
                {"DiskNumber": 0, "DriveLetter": "C", "Size": 1900 * GB},
            ],
            "free": {"C": 700 * GB},
        }
        drives = _drives(monkeypatch, host)
        assert [(d.drive_letter, d.bus_type, d.media_type, d.trim_enabled) for d in drives] == [
            ("C", "NVMe", "SSD", True)
        ]
        assert drives[0].unique_id == NVME["UniqueId"]
        assert (drives[0].size_gb, drives[0].free_gb) == (1900, 700)

    def test_a_sata_only_machine_with_a_spinning_disk(self, monkeypatch) -> None:
        """TRIM is an SSD fact: on the HDD it is not applicable, never 'off'."""
        host = {
            "disks": [SATA_HDD, SATA_SSD],
            "partitions": [
                {"DiskNumber": 0, "DriveLetter": "D", "Size": 3726 * GB},
                {"DiskNumber": 1, "DriveLetter": "C", "Size": 931 * GB},
            ],
            "free": {"D": 1200 * GB, "C": 300 * GB},
        }
        drives = _drives(monkeypatch, host)
        by_letter = {d.drive_letter: d for d in drives}
        assert by_letter["D"].media_type == "HDD"
        assert by_letter["D"].trim_enabled is None
        assert by_letter["C"].media_type == "SSD"
        assert by_letter["C"].trim_enabled is True
        assert {d.bus_type for d in drives} == {"SATA"}

    def test_one_disk_is_a_json_object_not_an_array_and_still_parses(self, monkeypatch) -> None:
        """ConvertTo-Json drops the array around a single element; the parser
        must not lose the only drive a one-disk laptop has."""
        host = {
            "disks": [NVME],
            "partitions": [{"DiskNumber": 0, "DriveLetter": "C", "Size": 476 * GB}],
            "free": {"C": 90 * GB},
        }
        raw = run_shipped_script(_STORAGE_PRELUDE + storage._STORAGE_SCRIPT, host)
        assert isinstance(json.loads(raw), dict)
        assert [d.drive_letter for d in _drives(monkeypatch, host)] == ["C"]

    def test_an_unreadable_trim_state_stays_unknown_on_the_ssd(self, monkeypatch) -> None:
        host = {
            "disks": [NVME],
            "partitions": [{"DiskNumber": 0, "DriveLetter": "C", "Size": 476 * GB}],
            "free": {"C": 90 * GB},
        }
        assert _drives(monkeypatch, host, trim=None)[0].trim_enabled is None
