"""CPU facts: every socket counted, one clock reported, topology read not guessed.

The defects this file exists for: ``Select-Object -First 1`` silently halved a
dual-socket machine, and ``BaseClock`` and ``MaxClock`` were both assigned
``MaxClockSpeed`` — one WMI field wearing two names (live: base=2304, max=2304
on a CPU whose boost is 4.6 GHz). The max field is deleted rather than fixed:
WMI has no boost figure, and a field that cannot be true is worse than absent.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.utils.detect import _CPU_DETECT_PS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-CimInstance {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$ClassName)
    foreach ($c in $FpsFake.cpus) {
        [pscustomobject]@{
            Name = $c.name
            NumberOfCores = [int]$c.cores
            NumberOfLogicalProcessors = [int]$c.logical
            MaxClockSpeed = [int]$c.clock
            L3CacheSize = [int]$c.l3
        }
    }
}
"""


def _detect(cpus: list[dict]) -> dict[str, str]:
    # The harness hands back the last stdout line, and the topology summary is
    # one multi-line string — flatten before joining so nothing is lost.
    joined = run_shipped_command(
        _PRELUDE
        + "$lines = @("
        + _CPU_DETECT_PS
        + ") | ForEach-Object { $_ -split [char]10 }; Write-Output ($lines -join ';')",
        {"cpus": cpus},
    )
    return dict(p.split("=", 1) for p in joined.split(";") if "=" in p)


XEON = {"name": "Xeon Gold 6338", "cores": 32, "logical": 64, "clock": 2000, "l3": 49152}


class TestEverySocketCounts:
    def test_a_dual_socket_machine_reports_both(self) -> None:
        """The gate: -First 1 read this host as half the machine it is."""
        fields = _detect([XEON, XEON])
        assert fields["Sockets"] == "2"
        assert fields["PhysicalCores"] == "64"
        assert fields["LogicalCores"] == "128"

    def test_a_single_socket_machine_is_unchanged(self) -> None:
        fields = _detect([XEON])
        assert fields["Sockets"] == "1"
        assert fields["PhysicalCores"] == "32"


class TestOneClockOneName:
    def test_no_maxclock_line_is_emitted(self) -> None:
        """The deleted duplicate must not come back under its old name."""
        fields = _detect([XEON])
        assert fields["BaseClock"] == "2000"
        assert "MaxClock" not in fields
        assert "MaxClock=" not in _CPU_DETECT_PS


class TestTopologyIsReadFromTheKernel:
    def test_the_real_machine_reports_a_coherent_split(self) -> None:
        """kernel32 cannot be shadowed, so the C# walk runs for real here: the
        split must exist and add up, whatever machine runs the suite."""
        fields = _detect([XEON])
        assert "PCores" in fields and "ECores" in fields and "Hybrid" in fields
        p, e = int(fields["PCores"]), int(fields["ECores"])
        assert p >= 1 and e >= 0
        assert fields["Hybrid"] == ("True" if e > 0 else "False")
