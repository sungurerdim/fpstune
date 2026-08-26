"""Advanced-property applies pick the spelling the driver exposes, and
flow control checks the driver's own value list before writing.

The defects this file exists for: the '*' prefix marks a standardised NDIS
keyword and vendor keywords are bare — Intel publishes ``*AdvancedEEE`` while
Realtek publishes ``AdvancedEEE`` — and an apply written for one spelling
fails (or silently misses) on adapters using the other. ``advanced_eee``
learned this first; ``interrupt_moderation`` and ``flow_control`` still probed
one spelling with ``-ErrorAction Stop``. Flow control additionally assumed
Microsoft's 0..3 map without asking the driver's own ``ValidRegistryValues``.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.definitions.network import (
    create_flow_control_setting,
    create_interrupt_moderation_setting,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([int]$InterfaceIndex, [string]$RegistryKeyword, [switch]$AllProperties)
    $exposed = [string]$FpsFake.keyword
    if ($AllProperties) {
        return [pscustomobject]@{
            RegistryKeyword = $exposed
            ValidRegistryValues = $FpsFake.valid
        }
    }
    if ($RegistryKeyword -ne $exposed) {
        throw 'No matching MSFT_NetAdapterAdvancedPropertySettingData objects found'
    }
    [pscustomobject]@{ RegistryKeyword = $exposed; ValidRegistryValues = $FpsFake.valid }
}

function Set-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([int]$InterfaceIndex, [string]$RegistryKeyword, $RegistryValue)
    Write-Output "WROTE=$RegistryKeyword=$RegistryValue"
}
"""

# The interrupt-moderation apply as it shipped, kept verbatim: one spelling,
# probed with -ErrorAction Stop.
_PREVIOUS_APPLY = r"""
try {
$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex 5 -RegistryKeyword '*InterruptModeration' -ErrorAction Stop
Set-NetAdapterAdvancedProperty -InterfaceIndex 5 -RegistryKeyword '*InterruptModeration' -RegistryValue 0 -ErrorAction Stop
'ok'
} catch { 'error:' + $_.Exception.Message }
"""


def _apply(factory, raw_value: int, host: dict) -> str:
    command = (
        factory(5, "Ethernet")
        .apply_command.replace("%value%", str(raw_value))
        .replace("%ifindex%", "5")
    )
    joined = run_shipped_command(
        _PRELUDE + "$lines = @(" + command + "); Write-Output ($lines -join ';')", host
    )
    return joined


REALTEK_BARE = {"keyword": "InterruptModeration", "valid": ["0", "1"]}


class TestTheSpellingIsTheAdaptersOwn:
    def test_a_bare_spelling_adapter_still_gets_the_write(self) -> None:
        """The gate: a renamed keyword is still found."""
        answer = _apply(create_interrupt_moderation_setting, 0, REALTEK_BARE)
        assert "WROTE=InterruptModeration=0" in answer
        assert answer.endswith("ok")

    def test_a_starred_spelling_adapter_is_unchanged(self) -> None:
        host = {"keyword": "*InterruptModeration", "valid": ["0", "1"]}
        answer = _apply(create_interrupt_moderation_setting, 0, host)
        assert "WROTE=*InterruptModeration=0" in answer

    def test_the_previous_command_failed_on_the_bare_spelling(self) -> None:
        """Same host, same harness — only the command differs."""
        answer = run_shipped_command(_PRELUDE + _PREVIOUS_APPLY, REALTEK_BARE)
        assert answer.startswith("error:")

    def test_an_adapter_without_the_feature_says_not_supported(self) -> None:
        host = {"keyword": "SomethingElse", "valid": []}
        answer = _apply(create_interrupt_moderation_setting, 0, host)
        assert answer == "not_supported"


class TestFlowControlAsksTheDriversOwnList:
    def test_a_value_the_driver_accepts_is_written(self) -> None:
        host = {"keyword": "*FlowControl", "valid": ["0", "1", "2", "3"]}
        answer = _apply(create_flow_control_setting, 0, host)
        assert "WROTE=*FlowControl=0" in answer

    def test_a_value_outside_the_drivers_list_is_refused_with_the_list(self) -> None:
        """The escape hatch: refuse loudly, quoting the driver's own answer."""
        host = {"keyword": "*FlowControl", "valid": ["1", "3"]}
        answer = _apply(create_flow_control_setting, 0, host)
        assert answer.startswith("error:")
        assert "1,3" in answer
        assert "WROTE" not in answer

    def test_a_driver_publishing_no_list_is_not_blocked(self) -> None:
        """No list is no evidence of rejection — the write proceeds."""
        host = {"keyword": "*FlowControl", "valid": []}
        answer = _apply(create_flow_control_setting, 0, host)
        assert "WROTE=*FlowControl=0" in answer

    def test_the_bare_spelling_works_here_too(self) -> None:
        host = {"keyword": "FlowControl", "valid": ["0", "1", "2", "3"]}
        answer = _apply(create_flow_control_setting, 0, host)
        assert "WROTE=FlowControl=0" in answer
