"""The link-capability advisory must derive a ceiling or say it cannot.

`*SpeedDuplex` is the only per-adapter source for "what is this NIC capable of",
and reading it has two traps that a copy of the logic in a test would never
expose. Both were measured on the dev machine before this file existed:

* `ValidDisplayValues` is localised. On this Turkish install it reads
  "1.0 Gbps Tam İkili", so the human-readable list cannot be parsed by anything.
  Only `ValidRegistryValues` is stable across locales.
* That numeric enum is vendor-extended. NDIS documents 0-7; this Realtek publishes
  `0,1,2,3,4,6,2500`, using a literal 2500 for 2.5 Gbps. A ceiling derived from an
  unrecognised value would tell a user with a perfectly good link that it is
  capped — so an unrecognised value has to produce `not_available`, not a guess.

These run the shipped `detect_command` verbatim against synthetic adapters, for
the reason the rest of this directory exists: a copied comparison only ever proves
the copy works.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command, run_shipped_script

from fpstune.settings.definitions.network import create_link_capability_setting
from fpstune.settings.executors.powershell import _split_detect_output
from fpstune.settings.executors.ps_batch import command_is_batchable
from fpstune.utils.powershell import substitute_placeholders

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Runs the shipped PowerShell detect command"
)

# Shadows the two cmdlets the command calls. `substitute_placeholders` rewrites
# `Get-NetAdapterAdvancedProperty -InterfaceIndex` into `-Name $fpstuneAdapterName`
# with a preamble, so the shadow has to accept -Name and the preamble's
# Get-NetAdapter call has to answer too — which is itself worth exercising, since
# that rewrite is what #40 was about.
_HARNESS = """
$ErrorActionPreference = 'Stop'
$fake = Get-Content -LiteralPath $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-NetAdapter {
    param([Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    if ($null -eq $fake.adapter) { return $null }
    [pscustomobject]@{
        Name   = $fake.adapter.Name
        Status = $fake.adapter.Status
        Speed  = $fake.adapter.Speed
    }
}

function Get-NetAdapterAdvancedProperty {
    param([Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    if ($null -eq $fake.valid) { return $null }
    [pscustomobject]@{ ValidRegistryValues = @($fake.valid) }
}

"""


def _detect(
    *,
    speed_bps: int | None = 1_000_000_000,
    status: str = "Up",
    valid: list[int] | None = None,
    name: str = "Ethernet",
) -> str:
    setting = create_link_capability_setting(17, name)
    command = substitute_placeholders(setting.detect_command, **setting.detect_args)
    payload: dict[str, object] = {
        "adapter": None
        if speed_bps is None and status == "absent"
        else {"Name": name, "Status": status, "Speed": speed_bps},
        "valid": valid,
    }
    answer = run_shipped_command(_HARNESS + command, payload)
    # The command prints its diagnostic before the value; the executor strips
    # FPSTUNE_WARN lines and reads the last one, which is what the harness returns.
    return answer


# This Realtek's real list, read off the adapter rather than invented.
REALTEK_2_5G = [0, 1, 2, 3, 4, 6, 2500]
GIGABIT = [0, 1, 2, 3, 4, 5, 6]


def test_a_link_below_the_adapters_ceiling_is_reported() -> None:
    """The dev machine's exact state: 100 Mbps negotiated on a 2.5 GbE adapter."""
    assert _detect(speed_bps=100_000_000, valid=REALTEK_2_5G) == "below_capability"


def test_a_link_at_the_ceiling_is_clean() -> None:
    assert _detect(speed_bps=2_500_000_000, valid=REALTEK_2_5G) == "at_capability"


def test_a_gigabit_adapter_linked_at_gigabit_is_clean() -> None:
    """The ceiling is the adapter's own maximum, not the fastest Ethernet ever made."""
    assert _detect(speed_bps=1_000_000_000, valid=GIGABIT) == "at_capability"


def test_a_faster_link_than_the_enum_knows_is_not_flagged() -> None:
    """Negotiating above the derived ceiling is not a fault to report."""
    assert _detect(speed_bps=2_500_000_000, valid=GIGABIT) == "at_capability"


def test_an_unrecognised_vendor_value_refuses_to_guess() -> None:
    """A wrong ceiling means telling a user their healthy link is capped.

    9999 is not an NDIS member and not a real Ethernet rate, so there is no honest
    reading of it — and answering `below_capability` here would be the invented
    specific this project keeps removing.
    """
    assert _detect(speed_bps=1_000_000_000, valid=[0, 1, 2, 9999]) == "not_available"


def test_an_adapter_with_no_speed_duplex_keyword_is_not_judged() -> None:
    """Most Intel and every Wi-Fi adapter publishes no such keyword."""
    assert _detect(speed_bps=1_000_000_000, valid=None) == "not_available"


def test_a_down_adapter_is_not_judged() -> None:
    """A disconnected NIC has no negotiated speed to be below anything."""
    assert _detect(speed_bps=0, status="Disconnected", valid=REALTEK_2_5G) == "not_available"


def test_auto_negotiation_alone_gives_no_ceiling() -> None:
    """Value 0 is 'negotiate', not a speed — a list holding only it says nothing."""
    assert _detect(speed_bps=1_000_000_000, valid=[0]) == "not_available"


def test_the_command_survives_a_shared_detect_session() -> None:
    """Its diagnostic goes through the pipeline, so it can be batched.

    Write-Host would bypass `| Out-String` and cost every setting in its group a
    live subprocess — measured at two commands taking down a group of twelve. This
    pins the choice rather than trusting it to stay right.
    """
    setting = create_link_capability_setting(17, "Ethernet")
    assert command_is_batchable(setting.detect_command)


def _detect_with_finding(speed_bps: int, valid: list[int]) -> tuple[str | None, dict | None]:
    """The value and the finding, split exactly the way the executor splits them."""
    setting = create_link_capability_setting(17, "Ethernet")
    command = substitute_placeholders(setting.detect_command, **setting.detect_args)
    payload = {"adapter": {"Name": "Ethernet", "Status": "Up", "Speed": speed_bps}, "valid": valid}
    lines, finding = _split_detect_output(
        setting.id, run_shipped_script(_HARNESS + command, payload)
    )
    return (lines[-1] if lines else None), finding


def test_the_numbers_travel_with_the_word_from_real_powershell() -> None:
    """ConvertTo-Json's actual output parses back into the two integers the UI phrases."""
    value, finding = _detect_with_finding(100_000_000, REALTEK_2_5G)
    assert value == "below_capability"
    assert finding == {"kind": "link_speed", "linked_mbps": 100, "ceiling_mbps": 2500}


def test_a_clean_link_still_reports_what_it_measured() -> None:
    value, finding = _detect_with_finding(1_000_000_000, GIGABIT)
    assert value == "at_capability"
    assert finding == {"kind": "link_speed", "linked_mbps": 1000, "ceiling_mbps": 1000}


def test_a_refused_ceiling_carries_no_finding() -> None:
    """No ceiling, no numbers: a finding with an invented ceiling is the bug this guards."""
    value, finding = _detect_with_finding(1_000_000_000, [0, 1, 2, 9999])
    assert value == "not_available"
    assert finding is None
