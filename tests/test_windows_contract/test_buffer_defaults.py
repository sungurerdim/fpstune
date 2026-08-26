"""Reset writes the driver's stock buffer count, never a constant.

The defect this file exists for: the buffer settings' "default" choice wrote
``max(NumericParameterMinValue, 256)`` — a third thing, neither this driver's
default nor its maximum, so reset put the machine into a state it never held.
C6's split is reset = curated stock, undo = this machine's own prior value;
a constant is neither. The shipped command now writes the driver's own
``DefaultRegistryValue`` and fails loudly on a driver that publishes none —
an invented stock value must not pass as a reset.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.definitions.network import (
    create_receive_buffers_setting,
    create_transmit_buffers_setting,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([int]$InterfaceIndex, [string]$RegistryKeyword)
    [pscustomobject]@{
        RegistryValue = @([string]$FpsFake.current)
        NumericParameterMinValue = [int]$FpsFake.min
        NumericParameterMaxValue = [int]$FpsFake.max
        DefaultRegistryValue = $FpsFake.default
    }
}

function Set-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([int]$InterfaceIndex, [string]$RegistryKeyword, $RegistryValue)
    Write-Output "WROTE=$RegistryValue"
}
"""

# The apply command as it shipped, kept verbatim so the fix can be shown to
# change the answer: max(min, 256) is a constant wearing a derivation's hat.
_PREVIOUS_DEFAULT = r"""
$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex 5 -RegistryKeyword '*ReceiveBuffers' -ErrorAction Stop
$val = [Math]::Max([int]$prop.NumericParameterMinValue, 256)
Set-NetAdapterAdvancedProperty -InterfaceIndex 5 -RegistryKeyword '*ReceiveBuffers' -RegistryValue $val -ErrorAction Stop
"""


def _apply(factory, value: str, host: dict) -> str:
    command = (
        factory(5, "Ethernet").apply_command.replace("%value%", value).replace("%ifindex%", "5")
    )
    return run_shipped_command(_PRELUDE + command, host)


DRIVER_512_DEFAULT = {"current": "1024", "min": 64, "max": 4096, "default": 512}


@pytest.mark.parametrize(
    "factory", [create_receive_buffers_setting, create_transmit_buffers_setting]
)
class TestResetWritesTheDriversOwnStock:
    def test_default_writes_the_published_default_not_256(self, factory) -> None:
        """The gate: a driver whose stock is 512 gets 512 back, never 256."""
        answer = _apply(factory, "default", DRIVER_512_DEFAULT)
        assert answer == "ok"
        # Set- echoes what it wrote; the write precedes the final 'ok'.
        full = run_shipped_command(
            _PRELUDE
            + "$lines = @("
            + factory(5, "E").apply_command.replace("%value%", "default").replace("%ifindex%", "5")
            + "); Write-Output ($lines -join ';')",
            DRIVER_512_DEFAULT,
        )
        assert "WROTE=512" in full
        assert "WROTE=256" not in full

    def test_maximum_still_writes_the_adapters_own_ceiling(self, factory) -> None:
        full = run_shipped_command(
            _PRELUDE
            + "$lines = @("
            + factory(5, "E").apply_command.replace("%value%", "maximum").replace("%ifindex%", "5")
            + "); Write-Output ($lines -join ';')",
            DRIVER_512_DEFAULT,
        )
        assert "WROTE=4096" in full

    def test_a_driver_with_no_published_default_fails_loudly(self, factory) -> None:
        """No stock value on record means no reset — never an invented one."""
        host = {"current": "1024", "min": 64, "max": 4096, "default": None}
        answer = _apply(factory, "default", host)
        assert answer.startswith("error:")
        assert "does not publish a default" in answer


def test_the_previous_command_wrote_the_constant() -> None:
    """Same host, same harness — the shipped rule chose 256 over the 512 stock."""
    answer = run_shipped_command(_PRELUDE + _PREVIOUS_DEFAULT, DRIVER_512_DEFAULT)
    assert answer == "WROTE=256"
