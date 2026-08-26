"""Switching the Wi-Fi radio off must not make fpstune blind to it.

A user hit `VERIFY FAILED Wi-Fi Radio While Wired: expected='radio_off',
detected='not_applicable'` — after an apply that had worked. Measured on that host:
once `Disable-NetAdapter` has run, the adapter reports `Status = 'Not Present'` and
`Get-NetAdapter -Physical` stops returning it at all, `-IncludeHidden` included. So
the setting was blind to the exact state it creates:

* detect saw no Wi-Fi adapter and answered `not_applicable`, so a successful apply
  could never verify
* and apply's enable branch answered "no Wi-Fi adapter on this machine", so fpstune
  could switch the radio off and then could not switch it back on

The second is the serious one. A tweak that cannot be undone by the tool that
applied it is a one-way door, and the setting is filtered out of the UI once it
reads `not_applicable`, so the user had no row left to press either.

`test_reset_turns_the_radio_back_on` passed through all of it, because it asserted
that the string `Enable-NetAdapter` appears in the command. It does. It just could
never reach an adapter. These tests run the shipped commands against described
hardware instead.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.definitions.network import _WIFI_ADAPTERS
from fpstune.settings.definitions.network import (
    NETWORK_WIFI_RADIO_WHEN_WIRED as WIFI_RADIO,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Runs the shipped PowerShell detect command"
)

# One shadow for Get-NetAdapter. It takes no parameters on purpose: the shipped
# command must not be passing -Physical, and a shadow that quietly accepted and
# ignored it would hide exactly the defect this file is about.
_HARNESS = """
$ErrorActionPreference = 'Stop'
$fake = Get-Content -LiteralPath $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-NetAdapter {
    param([Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    if ($Ignored -contains '-Physical') {
        throw 'the command passed -Physical, which cannot see a disabled adapter'
    }
    $fake.adapters
}

"""


def _adapter(
    name: str,
    media: str,
    *,
    status: str,
    admin: str,
    virtual: bool = False,
    hardware: bool = True,
) -> dict[str, object]:
    return {
        "Name": name,
        "PhysicalMediaType": media,
        "Status": status,
        "AdminStatus": admin,
        "Virtual": virtual,
        "HardwareInterface": hardware,
    }


# The three states this machine actually produced, read off the host.
WIFI_OFF = _adapter("Wi-Fi", "Native 802.11", status="Not Present", admin="Down")
WIFI_IDLE = _adapter("Wi-Fi", "Native 802.11", status="Disconnected", admin="Up")
WIFI_CONNECTED = _adapter("Wi-Fi", "Native 802.11", status="Up", admin="Up")
ETHERNET_UP = _adapter("Ethernet", "802.3", status="Up", admin="Up")
ETHERNET_DOWN = _adapter("Ethernet", "802.3", status="Disconnected", admin="Down")
WIFI_DIRECT = _adapter(
    "Local Area Connection* 9",
    "Native 802.11",
    status="Disconnected",
    admin="Up",
    virtual=True,
)


def _detect(*adapters: dict[str, object]) -> str:
    return run_shipped_command(_HARNESS + WIFI_RADIO.detect_command, {"adapters": list(adapters)})


def test_a_radio_that_was_switched_off_reads_as_switched_off() -> None:
    """The exact regression: this used to answer `not_applicable`.

    `Status` is 'Not Present' rather than 'Disabled' on a disabled adapter, which is
    why reading Status would have called it `radio_on` even once it could see it.
    """
    assert _detect(WIFI_OFF, ETHERNET_UP) == "radio_off"


def test_an_idle_radio_reads_as_on() -> None:
    """Enabled but unconnected is the case the setting exists for.

    That adapter is scanning on a timer, which is the kernel work being removed, so
    calling it `radio_off` because nothing is connected would report the tweak as
    applied while the scans continue.
    """
    assert _detect(WIFI_IDLE, ETHERNET_UP) == "radio_on"


def test_a_connected_radio_reads_as_on() -> None:
    assert _detect(WIFI_CONNECTED, ETHERNET_UP) == "radio_on"


def test_no_wired_link_makes_the_recommendation_meaningless() -> None:
    assert _detect(WIFI_IDLE, ETHERNET_DOWN) == "not_applicable"


def test_a_machine_with_no_wifi_is_not_judged() -> None:
    assert _detect(ETHERNET_UP) == "not_applicable"


def test_a_virtual_wifi_adapter_is_not_a_radio() -> None:
    """Wi-Fi Direct publishes 802.11 media on a virtual adapter.

    Counting it would report `radio_on` forever, because disabling the physical
    radio does not touch it — the setting could then never reach its own target.
    """
    assert _detect(WIFI_OFF, WIFI_DIRECT, ETHERNET_UP) == "radio_off"


def test_one_radio_still_on_decides_the_answer() -> None:
    """A laptop with a second wireless card must not read as done while it scans."""
    second = _adapter("Wi-Fi 2", "Native 802.11", status="Disconnected", admin="Up")
    assert _detect(WIFI_OFF, second, ETHERNET_UP) == "radio_on"


def test_both_commands_find_adapters_the_same_way() -> None:
    """Detect and apply share one lookup, so enable can reach what disable created.

    Two spellings of "which adapters count" in one setting is how they drift apart,
    and here the drift was fatal in one direction: apply could disable a radio that
    it could then no longer find to enable.
    """
    assert _WIFI_ADAPTERS in WIFI_RADIO.detect_command
    assert _WIFI_ADAPTERS in WIFI_RADIO.apply_command


def test_neither_command_uses_physical() -> None:
    """`-Physical` is what hid the disabled adapter. Pinned so it cannot come back."""
    for command in (WIFI_RADIO.detect_command, WIFI_RADIO.apply_command):
        assert "-Physical" not in command
