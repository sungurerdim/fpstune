"""Secure DNS must observe every adapter it writes, not just the first one.

`network:dns_security` applies to every active physical adapter in a loop, but
detection used to read `Select-Object -First 1` and then compare only
`ServerAddresses[0]`. Two states therefore reported success while the system was
not in the requested state:

* one adapter drifting -- Wi-Fi still on ISP DNS while Ethernet was on Cloudflare
* a resolver appended after apply -- the dev machine's Ethernet held
  {1.1.1.2, 1.0.0.2, 192.168.1.1} and this reported `cloudflare_security`, even
  though any fallback to that third entry is both unfiltered and unencrypted

Same class as #31 and #40: the observation is narrower than the action, so
verification passes over a state that was never reached.

These tests run **the shipped `detect_command` verbatim** against synthetic
adapters, by shadowing `Get-NetAdapter` and `Get-DnsClientServerAddress` with
functions in the same PowerShell session. Copying the comparison logic into the
test would only prove the copy works -- which is exactly how the original defects
survived a green suite.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import (
    fake_adapters,
    loud_catch,
    run_shipped_command,
)

from fpstune.settings.definitions.network import DNS_SECURITY

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Runs the shipped PowerShell detect command"
)

# Shadows the two cmdlets the detect command calls. A function takes precedence
# over a cmdlet of the same name, so the real command runs unmodified against
# whatever hardware the test describes.
_HARNESS = """
$ErrorActionPreference = 'Stop'
$fake = Get-Content -LiteralPath $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-NetAdapter {
    param([Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    $fake.adapters
}

function Get-DnsClientServerAddress {
    # -ErrorAction must NOT be declared here: the [Parameter()] attribute makes
    # this an advanced function, so PowerShell adds the common parameters itself
    # and an explicit one collides ("defined multiple times"). That collision threw
    # inside the command's own try/catch, which answered 'isp' -- making every
    # negative case pass for the wrong reason. Hence the guard in _detect below.
    param(
        $InterfaceIndex,
        $AddressFamily,
        [Parameter(ValueFromRemainingArguments = $true)] $Ignored
    )
    $servers = $fake.dns."$InterfaceIndex"
    if ($null -eq $servers) { $servers = @() }
    [pscustomobject]@{ ServerAddresses = @($servers) }
}

"""

_SHIPPED_CATCH = "catch { 'isp' }"


def _detect(adapters: list[dict[str, object]], dns: dict[str, list[str]]) -> str:
    """Run the real detect command against a described host and return its answer."""
    command = loud_catch(DNS_SECURITY.detect_command, _SHIPPED_CATCH)
    payload = {"adapters": fake_adapters(*adapters), "dns": dns}
    return run_shipped_command(_HARNESS + command, payload)


ETHERNET = {"ifIndex": 19, "name": "Ethernet"}
WIFI = {"ifIndex": 4, "name": "Wi-Fi", "description": "Intel Wi-Fi 6 AX201"}

SECURITY_PAIR = ["1.1.1.2", "1.0.0.2"]
FAMILY_PAIR = ["1.1.1.3", "1.0.0.3"]
PLAIN_PAIR = ["1.1.1.1", "1.0.0.1"]
ROUTER = "192.168.1.1"


def test_a_clean_single_adapter_is_recognised() -> None:
    assert _detect([ETHERNET], {"19": SECURITY_PAIR}) == "cloudflare_security"


def test_an_appended_resolver_is_not_reported_as_applied() -> None:
    """The dev machine's exact state, which the old detect called applied.

    A third entry pointing at the router is an unfiltered, unencrypted fallback.
    Reading only ServerAddresses[0] could never see it.
    """
    assert _detect([ETHERNET], {"19": [*SECURITY_PAIR, ROUTER]}) == "isp"


def test_one_drifting_adapter_is_not_reported_as_applied() -> None:
    """Apply writes both adapters, so detection has to agree about both."""
    answer = _detect(
        [ETHERNET, WIFI],
        {"19": SECURITY_PAIR, "4": [ROUTER]},
    )
    assert answer == "isp"


def test_every_adapter_matching_is_reported_as_applied() -> None:
    answer = _detect(
        [ETHERNET, WIFI],
        {"19": SECURITY_PAIR, "4": SECURITY_PAIR},
    )
    assert answer == "cloudflare_security"


def test_resolver_order_does_not_matter() -> None:
    """Primary/secondary order is not what the setting is about.

    Apply writes them in a fixed order, but a user who reversed them still has
    exactly the configured resolvers, and calling that unapplied would make the
    setting nag forever.
    """
    assert _detect([ETHERNET], {"19": list(reversed(SECURITY_PAIR))}) == "cloudflare_security"


def test_partial_pair_is_not_enough() -> None:
    assert _detect([ETHERNET], {"19": ["1.1.1.2"]}) == "isp"


@pytest.mark.parametrize(
    ("servers", "expected"),
    [
        (FAMILY_PAIR, "cloudflare_family"),
        (PLAIN_PAIR, "cloudflare"),
    ],
)
def test_the_other_choices_are_still_distinguished(servers: list[str], expected: str) -> None:
    """Tightening the comparison must not collapse the choices into each other."""
    assert _detect([ETHERNET], {"19": servers}) == expected


def test_no_dns_configured_reads_as_isp() -> None:
    assert _detect([ETHERNET], {}) == "isp"


def test_no_matching_adapter_reads_as_isp() -> None:
    """Adapters apply would skip must not be able to decide the answer."""
    assert _detect([{**ETHERNET, "status": 2}], {"19": SECURITY_PAIR}) == "isp"


def test_virtual_adapters_are_excluded_from_the_verdict() -> None:
    """The filter has to stay identical to apply's, or the two disagree again.

    A Hyper-V switch carrying different DNS must not make a correctly configured
    physical adapter read as unapplied.
    """
    answer = _detect(
        [ETHERNET, {"ifIndex": 7, "name": "vEthernet", "description": "Hyper-V Virtual Switch"}],
        {"19": SECURITY_PAIR, "7": [ROUTER]},
    )
    assert answer == "cloudflare_security"
