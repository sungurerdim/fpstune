"""VRAM is the driver's own answer, never Win32_VideoController.AdapterRAM.

The defect this file exists for: ``AdapterRAM`` is a 32-bit field that clamps
at 4 GB. Live on the dev machine, a card with 8192 MB reported ``4293918720``
(4095 MB). NVIDIA was rescued by nvidia-smi; AMD and Intel were not — the
clamped figure flowed into the MW3 VRAM scale, where ``gb = 3.999`` chose the
8-GB tier (scale 0.70) on any 16 or 24 GB card while the copy told the user
"The card detected here has 4 GB." The docstring there forbids fabricating a
VRAM figure; the input was fabricated upstream instead. The old pick —
``Sort-Object AdapterRAM`` — was also undefined the moment two cards clamp to
the same value.

The shipped command reads ``HardwareInformation.qwMemorySize`` (a QWORD)
through each device's own Enum → Driver → Class binding, and picks the adapter
with the most driver-reported memory.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.utils.detect import _GPU_DETECT_PS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

GB = 1024**3

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-CimInstance {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$ClassName)
    foreach ($g in $FpsFake.gpus) {
        [pscustomobject]@{
            Name = $g.name; DriverVersion = $g.driver
            AdapterRAM = [int64]$g.adapterRam; PNPDeviceID = $g.pnp
        }
    }
}

function Get-ItemProperty {
    [CmdletBinding()] param([string]$Path, [string]$Name)
    foreach ($g in $FpsFake.gpus) {
        if ($Path -like "*\Enum\$($g.pnp)") {
            return [pscustomobject]@{ Driver = $g.driverKey }
        }
        if ($g.driverKey -and $Path -like "*\Control\Class\$($g.driverKey)" -and $g.qw -gt 0) {
            return [pscustomobject]@{ 'HardwareInformation.qwMemorySize' = [int64]$g.qw }
        }
    }
    return $null
}
"""

# The command as it shipped, kept verbatim so the fix can be shown to change
# the answer rather than merely to pass.
_PREVIOUS_DETECT = (
    "Get-CimInstance -ClassName Win32_VideoController | "
    "Sort-Object -Property AdapterRAM -Descending | "
    "Select-Object -First 1 Name, DriverVersion, AdapterRAM, PNPDeviceID | "
    'ForEach-Object { "Name=$($_.Name)"; "Driver=$($_.DriverVersion)"; '
    '"VRAM=$($_.AdapterRAM)"; "PNP=$($_.PNPDeviceID)" }'
)

CLAMP = 4293918720  # what AdapterRAM reports for anything >= 4 GB


def _gpu(
    name: str, pnp: str, key: str, qw: int, adapter_ram: int = CLAMP, driver: str = "1.0"
) -> dict:
    return {
        "name": name,
        "pnp": pnp,
        "driverKey": key,
        "qw": qw,
        "adapterRam": adapter_ram,
        "driver": driver,
    }


def _detect(gpus: list[dict]) -> dict[str, str]:
    # The harness returns the last stdout line, so the shipped command's lines
    # are collected into one (@() takes a statement list) — the command itself
    # runs verbatim inside it.
    joined = run_shipped_command(
        _PRELUDE + "$lines = @(" + _GPU_DETECT_PS + "); Write-Output ($lines -join ';')",
        {"gpus": gpus},
    )
    return dict(p.split("=", 1) for p in joined.split(";") if "=" in p)


class TestVramIsTheDriversAnswer:
    def test_a_16gb_card_never_reports_4095(self) -> None:
        """The gate: the clamp cannot reach the user."""
        card = _gpu("Radeon RX 7800 XT", r"PCI\VEN_1002&DEV_747E", "0000", 16 * GB)
        fields = _detect([card])
        assert fields["VramBytes"] == str(16 * GB)
        assert int(fields["VramBytes"]) // (1024 * 1024) == 16384  # not 4095

    def test_the_previous_command_reported_the_clamp(self) -> None:
        """Same host, same harness — only the command differs."""
        card = _gpu("Radeon RX 7800 XT", r"PCI\VEN_1002&DEV_747E", "0000", 16 * GB)
        joined = run_shipped_command(
            _PRELUDE + "$lines = @(" + _PREVIOUS_DETECT + "); Write-Output ($lines -join ';')",
            {"gpus": [card]},
        )
        fields = dict(p.split("=", 1) for p in joined.split(";") if "=" in p)
        assert fields["VRAM"] == str(CLAMP)  # 4095 MB on a 16 GB card

    def test_the_pick_is_defined_when_two_cards_clamp(self) -> None:
        """Sort-Object AdapterRAM was undefined here: both cards read 4095."""
        igpu = _gpu("Intel(R) UHD Graphics", r"PCI\VEN_8086&DEV_9A60", "0001", 2 * GB)
        dgpu = _gpu("Radeon RX 7900 XTX", r"PCI\VEN_1002&DEV_744C", "0000", 24 * GB)
        fields = _detect([igpu, dgpu])
        assert fields["Name"] == "Radeon RX 7900 XTX"
        assert fields["VramBytes"] == str(24 * GB)

    def test_no_driver_figure_means_unknown_not_a_guess(self) -> None:
        """A machine where no driver reports memory leaves VRAM absent (0)."""
        silent = _gpu("Some Adapter", r"PCI\VEN_0000&DEV_0000", "0000", 0)
        fields = _detect([silent])
        assert "VramBytes" not in fields
        assert fields["Name"] == "Some Adapter"
