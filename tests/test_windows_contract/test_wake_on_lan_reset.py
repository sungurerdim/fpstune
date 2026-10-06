"""Wake-on-LAN reset restores each keyword to the driver's own default.

The setting spans two keywords, ``*WakeOnMagicPacket`` and ``*WakeOnPattern``, and
reads as Disabled only when both are 0. A driver may ship them in different
states (magic packet on, pattern match off). Reset used to write one raw value to
both, so such a machine came back with the pattern wake the driver had off. The
shipped apply command runs against fake cmdlets that record every write.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import HARNESS_ERROR, loud_catch, run_shipped_command

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions.network import create_wake_on_lan_setting
from fpstune.settings.discovery.network import with_driver_default
from fpstune.utils.powershell import substitute_placeholders

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'

# The shipped command addresses the adapter by name (substitute_placeholders turns
# -InterfaceIndex into a -Name lookup), so the fakes answer to that spelling.
function Get-NetAdapter {
    [CmdletBinding()] param([int]$InterfaceIndex)
    [pscustomobject]@{ Name = 'Ethernet' }
}

function Set-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([string]$Name, [string]$RegistryKeyword, $RegistryValue, [switch]$NoRestart)
    Write-Output "WROTE=$RegistryKeyword=$RegistryValue"
}
"""

MIXED = {"*wakeonmagicpacket": "1", "*wakeonpattern": "0"}


def _run(setting: SettingExecutor, value: str) -> str:
    command = substitute_placeholders(setting.apply_command, **setting.apply_args, value=value)
    command = loud_catch(command, "catch { }")
    answer = run_shipped_command(_PRELUDE + "$lines = @(" + command + "); $lines -join ';'", {})
    assert HARNESS_ERROR not in answer, answer
    return answer


def _writes(answer: str) -> dict[str, str]:
    pairs = (
        part.removeprefix("WROTE=").split("=") for part in answer.split(";") if "WROTE=" in part
    )
    return dict(pairs)


class TestResetRestoresEachKeyword:
    def test_keywords_in_different_states_go_back_to_their_own_default(self) -> None:
        setting = with_driver_default(create_wake_on_lan_setting(14, "Ethernet"), MIXED)
        assert setting.default_value == "Enabled"
        answer = _run(setting, setting.default_value)
        assert _writes(answer) == {"*WakeOnMagicPacket": "1", "*WakeOnPattern": "0"}
        assert answer.endswith("ok")

    def test_the_reverse_split_is_restored_just_the_same(self) -> None:
        reverse = {"*wakeonmagicpacket": "0", "*wakeonpattern": "1"}
        setting = with_driver_default(create_wake_on_lan_setting(14, "Ethernet"), reverse)
        assert _writes(_run(setting, setting.default_value)) == {
            "*WakeOnMagicPacket": "0",
            "*WakeOnPattern": "1",
        }

    def test_applying_the_recommendation_still_turns_both_off(self) -> None:
        """Only the stock value restores per keyword; Disabled is not the stock here."""
        setting = with_driver_default(create_wake_on_lan_setting(14, "Ethernet"), MIXED)
        assert _writes(_run(setting, "Disabled")) == {
            "*WakeOnMagicPacket": "0",
            "*WakeOnPattern": "0",
        }

    def test_a_driver_with_both_on_writes_both_on(self) -> None:
        both_on = {"*wakeonmagicpacket": "1", "*wakeonpattern": "1"}
        setting = with_driver_default(create_wake_on_lan_setting(14, "Ethernet"), both_on)
        assert _writes(_run(setting, setting.default_value)) == {
            "*WakeOnMagicPacket": "1",
            "*WakeOnPattern": "1",
        }

    def test_a_driver_publishing_nothing_keeps_the_uniform_write(self) -> None:
        setting = with_driver_default(create_wake_on_lan_setting(14, "Ethernet"), {})
        assert _writes(_run(setting, setting.default_value)) == {
            "*WakeOnMagicPacket": "1",
            "*WakeOnPattern": "1",
        }

    def test_a_default_that_is_not_a_number_invents_no_split(self) -> None:
        garbled = {"*wakeonmagicpacket": "1", "*wakeonpattern": "n/a"}
        setting = with_driver_default(create_wake_on_lan_setting(14, "Ethernet"), garbled)
        assert _writes(_run(setting, setting.default_value)) == {
            "*WakeOnMagicPacket": "1",
            "*WakeOnPattern": "1",
        }
