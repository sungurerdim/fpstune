"""Encrypted DNS must be judged by the interface flag, not by the template table.

The state this setting exists to fix was measured on the dev machine: sixteen DoH
templates registered by `netsh dns add encryption`, and DNS still leaving as
plaintext, because no adapter carried an entry under

    Dnscache\\InterfaceSpecificParameters\\<GUID>\\DohInterfaceSettings\\Doh\\<ip>

A detect that reported on the template table would have called that configuration
"enabled". So these tests pin the opposite: registered-but-not-attached reads as
disabled.

`DohFlags = 2` is the value Windows itself wrote once DoH was enabled through the
Settings UI with the automatic template and plaintext fallback off, confirmed
active. It is measured, not taken from a guide — the bar #26 set when
`DevicePriority` was left out for want of a trustworthy value.

As everywhere in this directory, the shipped `detect_command` runs verbatim; only
the cmdlets it calls are shadowed.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import (
    fake_adapters,
    loud_catch,
    run_shipped_command,
)

from fpstune.settings.definitions.network import DNS_OVER_HTTPS, DNS_SECURITY

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Runs the shipped PowerShell detect command"
)

_SHIPPED_CATCH = "catch { 'disabled' }"

# Shadows the four cmdlets the detect command uses. Test-Path and Get-ItemProperty
# are answered from the fake registry so no real key is read or written.
_HARNESS = """
$ErrorActionPreference = 'Stop'
$fake = Get-Content -LiteralPath $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-NetAdapter {
    param([Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    $fake.adapters
}

function Get-DnsClientServerAddress {
    param($InterfaceIndex, $AddressFamily, [Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    $servers = $fake.dns."$InterfaceIndex"
    if ($null -eq $servers) { $servers = @() }
    [pscustomobject]@{ ServerAddresses = @($servers) }
}

function Test-Path {
    param($LiteralPath, [Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    $null -ne $fake.registry."$LiteralPath"
}

function Get-ItemProperty {
    param($LiteralPath, $Name, [Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    $entry = $fake.registry."$LiteralPath"
    if ($null -eq $entry) { return $null }
    [pscustomobject]@{ DohFlags = $entry.DohFlags }
}

"""

ETHERNET = {"ifIndex": 19, "name": "Ethernet", "guid": "{eth-guid}"}
WIFI = {"ifIndex": 4, "name": "Wi-Fi", "guid": "{wifi-guid}", "description": "Intel Wi-Fi 6 AX201"}

SECURITY_PAIR = ["1.1.1.2", "1.0.0.2"]


def _doh_key(guid: str, server: str) -> str:
    return (
        "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Dnscache"
        f"\\InterfaceSpecificParameters\\{guid}\\DohInterfaceSettings\\Doh\\{server}"
    )


def _detect(
    adapters: list[dict[str, object]],
    dns: dict[str, list[str]],
    registry: dict[str, dict[str, int]] | None = None,
) -> str:
    command = loud_catch(DNS_OVER_HTTPS.detect_command, _SHIPPED_CATCH)
    payload = {
        "adapters": fake_adapters(*adapters),
        "dns": dns,
        "registry": registry or {},
    }
    return run_shipped_command(_HARNESS + command, payload)


def test_flag_on_the_primary_resolver_reads_as_enabled() -> None:
    """What Windows itself writes: one entry, for the primary address only."""
    answer = _detect(
        [ETHERNET],
        {"19": SECURITY_PAIR},
        {_doh_key("{eth-guid}", "1.1.1.2"): {"DohFlags": 2}},
    )
    assert answer == "enabled"


def test_registered_template_without_an_interface_entry_reads_as_disabled() -> None:
    """The dev machine's exact state, and the reason this setting exists.

    `netsh dns add encryption` had succeeded for sixteen servers and DNS was still
    plaintext. A detect that consulted the template table would call this enabled.
    """
    assert _detect([ETHERNET], {"19": SECURITY_PAIR}, {}) == "disabled"


def test_one_adapter_without_the_flag_reads_as_disabled() -> None:
    """Apply writes every adapter, so detect has to agree about every adapter."""
    answer = _detect(
        [ETHERNET, WIFI],
        {"19": SECURITY_PAIR, "4": SECURITY_PAIR},
        {_doh_key("{eth-guid}", "1.1.1.2"): {"DohFlags": 2}},
    )
    assert answer == "disabled"


def test_every_adapter_flagged_reads_as_enabled() -> None:
    answer = _detect(
        [ETHERNET, WIFI],
        {"19": SECURITY_PAIR, "4": SECURITY_PAIR},
        {
            _doh_key("{eth-guid}", "1.1.1.2"): {"DohFlags": 2},
            _doh_key("{wifi-guid}", "1.1.1.2"): {"DohFlags": 2},
        },
    )
    assert answer == "enabled"


def test_a_flag_on_the_secondary_only_is_not_enough() -> None:
    """Documents the rule rather than leaving it implicit.

    Windows attaches the flag to the primary resolver, so the primary is what
    decides. An entry for the secondary alone means the address actually queried
    first is still unencrypted.
    """
    answer = _detect(
        [ETHERNET],
        {"19": SECURITY_PAIR},
        {_doh_key("{eth-guid}", "1.0.0.2"): {"DohFlags": 2}},
    )
    assert answer == "disabled"


def test_a_zero_flag_reads_as_disabled() -> None:
    """A present key with a falsy flag is off, not on.

    The key can survive after DoH is turned off, so its mere existence must not
    count as enabled.
    """
    answer = _detect(
        [ETHERNET],
        {"19": SECURITY_PAIR},
        {_doh_key("{eth-guid}", "1.1.1.2"): {"DohFlags": 0}},
    )
    assert answer == "disabled"


def test_an_adapter_with_no_dns_configured_reads_as_disabled() -> None:
    assert _detect([ETHERNET], {}, {}) == "disabled"


def test_no_matching_adapter_reads_as_disabled() -> None:
    """An adapter apply would skip must not be able to decide the answer."""
    answer = _detect(
        [{**ETHERNET, "status": 2}],
        {"19": SECURITY_PAIR},
        {_doh_key("{eth-guid}", "1.1.1.2"): {"DohFlags": 2}},
    )
    assert answer == "disabled"


def test_virtual_adapters_do_not_decide_the_verdict() -> None:
    """The filter must stay identical to dns_security's, or the two disagree."""
    answer = _detect(
        [ETHERNET, {"ifIndex": 7, "guid": "{hv}", "description": "Hyper-V Virtual Switch"}],
        {"19": SECURITY_PAIR, "7": ["192.168.1.1"]},
        {_doh_key("{eth-guid}", "1.1.1.2"): {"DohFlags": 2}},
    )
    assert answer == "enabled"


def test_the_two_dns_settings_share_one_adapter_filter() -> None:
    """Pins the fix for the defect one setting over.

    `dns_security` reported success over a wrong state because its detect looked at
    a narrower set of adapters than its apply wrote. If these two settings drift
    apart on which adapters count, encrypted DNS can be reported enabled for a set
    that does not match the resolvers actually configured.
    """
    filter_text = (
        "[int]$_.InterfaceOperationalStatus -eq 1 -and "
        "-not $_.Virtual -and "
        "$_.InterfaceDescription -notlike '*Virtual*' -and "
        "$_.InterfaceDescription -notlike '*Hyper-V*' -and "
        "$_.InterfaceDescription -notlike '*VPN*' -and "
        "$_.InterfaceDescription -notlike '*Tunnel*'"
    )
    for command in (
        DNS_OVER_HTTPS.detect_command,
        DNS_OVER_HTTPS.apply_command,
        DNS_SECURITY.detect_command,
        DNS_SECURITY.apply_command,
    ):
        assert filter_text in command, f"adapter filter drifted in: {command[:120]}"
