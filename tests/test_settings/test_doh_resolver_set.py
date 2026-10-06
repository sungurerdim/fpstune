"""network:dns_over_https detect and apply ask one question over one resolver set.

Issue #104 class C. Measured 2026-10-06 on Windows 11 26200: bulk apply failed
"no DoH template known for the configured resolvers" while detect, which read only
the primary IPv4 resolver, had shown the row as actionable. Three defects:

1. detect and apply walked different resolver sets (primary IPv4 vs every v4+v6);
2. the template came from fpstune's own table only, never from Windows' own
   ``Get-DnsClientDohServerAddress``;
3. "no configured resolver has a template" was an apply failure the row gave no
   warning of. First moved into detection as an ABSENT_READINGS value, which hid the
   row from "apply all" (it takes only applicable, suboptimal rows) so DoH surfaced
   after ``network:dns_security`` as a second click. DoH is always reachable -- that
   setting installs templated resolvers and the bulk plan runs it first -- so the
   row reads ``disabled`` and its apply names the prerequisite. ``not_supported`` is
   left for a machine with no physical adapter at all.

The scripts are PowerShell text, so these tests run the real text under the real
runner (`run_powershell`) with the network cmdlets replaced by functions (a
function shadows a cmdlet of the same name), which makes the machine's own DNS
irrelevant. Windows-only for that reason: there is no PowerShell to run elsewhere.
"""

from __future__ import annotations

import json
import re
import sys

import pytest

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.definitions import network as network_module
from fpstune.settings.definitions.network import DNS_OVER_HTTPS, DNS_SECURITY
from fpstune.utils.powershell import run_powershell

GUID = "{11111111-2222-3333-4444-555555555555}"
KEY_ROOT = (
    "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Dnscache\\InterfaceSpecificParameters\\"
    + GUID
    + "\\DohInterfaceSettings\\"
)

ROUTER_V4 = "192.168.1.1"
ROUTER_V6 = "fe80::1"
QUAD9_V4 = "9.9.9.9"
QUAD9_V6 = "2620:fe::fe"
# Cloudflare's filtered pair: Windows does not ship a template, fpstune's table has one.
CLOUDFLARE_SECURITY = "1.1.1.2"
# A resolver only Windows knows (registered through its own Settings UI): the table has none.
WINDOWS_ONLY = "203.0.113.7"
WINDOWS_ONLY_TEMPLATE = "https://doh.example.net/dns-query"


def _key(server: str) -> str:
    return KEY_ROOT + ("Doh6" if ":" in server else "Doh") + "\\" + server


def _ps_list(items: list[str]) -> str:
    return "@(" + ", ".join(f"'{item}'" for item in items) + ")"


def _harness(
    script: str, *, servers: list[str], windows: dict[str, str], flagged: list[str]
) -> str:
    """The script under test, run against one stubbed adapter.

    The stubs record every write into ``$global:calls`` and the harness answers
    ``{"result": ..., "calls": [...]}``. A raise inside the script is let through:
    that is the failed-read path and must reach the runner as a failure.
    """
    windows_table = "; ".join(f"'{ip}' = '{tpl}'" for ip, tpl in windows.items())
    flagged_keys = _ps_list([_key(s) for s in flagged])
    return (
        "$global:calls = @(); "
        f"$global:windowsKnown = @{{ {windows_table} }}; "
        f"$global:flagged = {flagged_keys}; "
        "function Get-NetAdapter { [CmdletBinding()] param() "
        "[pscustomobject]@{ ifIndex = 7; InterfaceGuid = '" + GUID + "'; "
        "InterfaceOperationalStatus = 1; Virtual = $false; "
        "InterfaceDescription = 'Intel(R) Ethernet Controller' } }; "
        "function Get-DnsClientServerAddress { [CmdletBinding()] param($InterfaceIndex) "
        f"[pscustomobject]@{{ ServerAddresses = {_ps_list(servers)} }} }}; "
        "function Get-DnsClientDohServerAddress { [CmdletBinding()] param($ServerAddress) "
        "if ($global:windowsKnown.ContainsKey($ServerAddress)) { "
        "[pscustomobject]@{ ServerAddress = $ServerAddress; "
        "DohTemplate = $global:windowsKnown[$ServerAddress] } } }; "
        "function Add-DnsClientDohServerAddress { [CmdletBinding()] "
        "param($ServerAddress, $DohTemplate, $AllowFallbackToUdp, $AutoUpgrade) "
        "$global:calls += ('add ' + $ServerAddress + ' ' + $DohTemplate) }; "
        "function Test-Path { [CmdletBinding()] param($LiteralPath) "
        "$global:flagged -contains $LiteralPath }; "
        "function Get-ItemProperty { [CmdletBinding()] param($LiteralPath, $Name) "
        "[pscustomobject]@{ DohFlags = 2 } }; "
        "function New-Item { [CmdletBinding()] param($Path, [switch]$Force) "
        "$global:calls += ('key ' + $Path) }; "
        "function New-ItemProperty { [CmdletBinding()] "
        "param($Path, $Name, $Value, $PropertyType, [switch]$Force) "
        "$global:calls += ('flag ' + $Path + ' ' + $Value) }; "
        "function Remove-Item { [CmdletBinding()] "
        "param($LiteralPath, [switch]$Recurse, [switch]$Force) "
        "$global:calls += ('remove ' + $LiteralPath) }; "
        "function Clear-DnsClientCache { [CmdletBinding()] param() }; "
        f"$r = & {{ {script} }}; "
        "[pscustomobject]@{ result = [string]$r; calls = @($global:calls) } "
        "| ConvertTo-Json -Compress"
    )


def _run(
    script: str,
    *,
    servers: list[str],
    windows: dict[str, str] | None = None,
    flagged: list[str] | None = None,
) -> tuple[bool, str, list[str]]:
    ok, output = run_powershell(
        _harness(script, servers=servers, windows=windows or {}, flagged=flagged or [])
    )
    if not ok:
        return False, output, []
    payload = json.loads(output.strip().splitlines()[-1])
    calls = payload["calls"]
    return True, str(payload["result"]).strip(), [calls] if isinstance(calls, str) else calls


def _apply(value: str) -> str:
    return DNS_OVER_HTTPS.apply_command.replace("%value%", value)


pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="runs the shipped PowerShell text; there is none elsewhere"
)


class TestOneQuestionOneResolverSet:
    """The two scripts cannot drift because they are built from one fragment."""

    def test_detect_and_apply_embed_the_same_resolver_scan(self) -> None:
        fragment = network_module._DOH_RESOLVER_SCAN_PS
        assert fragment in DNS_OVER_HTTPS.detect_command
        assert fragment in DNS_OVER_HTTPS.apply_command

    def test_the_scan_walks_both_families_and_not_just_the_first_resolver(self) -> None:
        fragment = network_module._DOH_RESOLVER_SCAN_PS
        assert "-AddressFamily" not in fragment  # no v4-only read
        assert "$servers[0]" not in DNS_OVER_HTTPS.detect_command
        assert "foreach ($server in $servers)" in fragment

    def test_windows_own_template_is_asked_before_the_table(self) -> None:
        fragment = network_module._DOH_RESOLVER_SCAN_PS
        assert fragment.index("Get-DnsClientDohServerAddress") < fragment.index(
            "$templates[$server]"
        )


class TestDetect:
    def test_no_resolver_with_a_template_reads_disabled_not_absent(self) -> None:
        # Issue #104: an absent reading hid the row from "apply all", so DoH came
        # back as a new pending item after dns_security had run. DoH is reachable
        # (dns_security installs templated resolvers), so the row stays actionable.
        ok, result, _ = _run(DNS_OVER_HTTPS.detect_command, servers=[ROUTER_V4, ROUTER_V6])
        assert ok
        assert result == "disabled"
        assert not is_absent_reading(result)

    def test_no_physical_adapter_at_all_is_not_supported_and_absent(self) -> None:
        no_adapter = "function Get-NetAdapter { [CmdletBinding()] param() }; "
        ok, result, _ = _run(no_adapter + DNS_OVER_HTTPS.detect_command, servers=[ROUTER_V4])
        assert ok
        assert result == "not_supported"
        assert is_absent_reading(result)

    def test_a_resolver_only_windows_knows_makes_the_row_applicable(self) -> None:
        ok, result, _ = _run(
            DNS_OVER_HTTPS.detect_command,
            servers=[ROUTER_V4, WINDOWS_ONLY],
            windows={WINDOWS_ONLY: WINDOWS_ONLY_TEMPLATE},
        )
        assert ok
        assert not is_absent_reading(result)
        assert result == "disabled"

    def test_a_secondary_resolver_without_its_flag_reads_disabled(self) -> None:
        # The primary carries the flag, the IPv6 secondary does not: apply would
        # write it, so detect must not call the setting done.
        ok, result, _ = _run(
            DNS_OVER_HTTPS.detect_command,
            servers=[QUAD9_V4, QUAD9_V6],
            flagged=[QUAD9_V4],
        )
        assert ok
        assert result == "disabled"

    def test_every_templated_resolver_flagged_reads_enabled_and_router_dns_is_ignored(
        self,
    ) -> None:
        ok, result, _ = _run(
            DNS_OVER_HTTPS.detect_command,
            servers=[ROUTER_V4, QUAD9_V4, QUAD9_V6],
            flagged=[QUAD9_V4, QUAD9_V6],
        )
        assert ok
        assert result == "enabled"

    def test_a_failed_read_raises_and_is_neither_a_value_nor_an_absent_reading(self) -> None:
        script = (
            "function Get-DnsClientServerAddress { [CmdletBinding()] param($InterfaceIndex) "
            "throw 'the DNS client service did not answer' }; " + DNS_OVER_HTTPS.detect_command
        )
        ok, output, _ = _run(script, servers=[QUAD9_V4])
        assert not ok, output
        assert not is_absent_reading(output)


class TestApply:
    def test_enabling_with_only_router_dns_names_the_prerequisite_by_its_label(self) -> None:
        ok, result, calls = _run(_apply("enabled"), servers=[ROUTER_V4, ROUTER_V6])
        assert ok
        assert result == (
            "error:No configured DNS server has a known encrypted endpoint; apply "
            f"{DNS_SECURITY.display_name} first."
        )
        assert calls == []

    def test_disabling_with_only_router_dns_has_nothing_to_undo_and_succeeds(self) -> None:
        ok, result, calls = _run(_apply("disabled"), servers=[ROUTER_V4, ROUTER_V6])
        assert ok
        assert result == "ok"
        assert calls == []

    def test_enabling_with_no_physical_adapter_says_so(self) -> None:
        no_adapter = "function Get-NetAdapter { [CmdletBinding()] param() }; "
        ok, result, _ = _run(no_adapter + _apply("enabled"), servers=[ROUTER_V4])
        assert ok
        assert result == "error:no applicable adapter found"

    def test_a_resolver_windows_already_knows_is_flagged_without_re_registering_it(self) -> None:
        ok, result, calls = _run(
            _apply("enabled"),
            servers=[ROUTER_V4, WINDOWS_ONLY],
            windows={WINDOWS_ONLY: WINDOWS_ONLY_TEMPLATE},
        )
        assert ok
        assert result == "ok"
        assert not any(call.startswith("add ") for call in calls), calls
        assert f"flag {_key(WINDOWS_ONLY)} 2" in calls

    def test_a_resolver_only_the_table_knows_is_registered_with_the_table_template(self) -> None:
        ok, result, calls = _run(_apply("enabled"), servers=[CLOUDFLARE_SECURITY])
        assert ok
        assert result == "ok"
        assert f"add {CLOUDFLARE_SECURITY} https://security.cloudflare-dns.com/dns-query" in calls
        assert f"flag {_key(CLOUDFLARE_SECURITY)} 2" in calls

    def test_both_families_are_flagged(self) -> None:
        ok, result, calls = _run(_apply("enabled"), servers=[QUAD9_V4, QUAD9_V6])
        assert ok
        assert result == "ok"
        assert f"flag {_key(QUAD9_V4)} 2" in calls
        assert f"flag {_key(QUAD9_V6)} 2" in calls
        assert "\\Doh6\\" in _key(QUAD9_V6)

    def test_disabling_removes_each_flag_it_finds(self) -> None:
        ok, result, calls = _run(
            _apply("disabled"),
            servers=[QUAD9_V4, QUAD9_V6],
            flagged=[QUAD9_V4, QUAD9_V6],
        )
        assert ok
        assert result == "ok"
        assert sorted(c for c in calls if c.startswith("remove ")) == sorted(
            f"remove {_key(s)}" for s in (QUAD9_V4, QUAD9_V6)
        )

    def test_a_detect_that_says_applicable_is_one_apply_can_act_on(self) -> None:
        # The pair that shipped broken: the row was shown as actionable, then
        # failed. An applicable value with a templated resolver in place is one
        # apply acts on; without one the row is still applicable (dns_security
        # makes it reachable) and apply refuses with the prerequisite's name.
        for servers, windows, reachable in (
            ([ROUTER_V4], {}, False),
            ([ROUTER_V4, WINDOWS_ONLY], {WINDOWS_ONLY: WINDOWS_ONLY_TEMPLATE}, True),
            ([QUAD9_V4, QUAD9_V6], {}, True),
        ):
            _, detected, _ = _run(DNS_OVER_HTTPS.detect_command, servers=servers, windows=windows)
            _, applied, calls = _run(_apply("enabled"), servers=servers, windows=windows)
            assert not is_absent_reading(detected), (servers, detected)
            if reachable:
                assert applied == "ok", (servers, applied)
                assert calls, servers
            else:
                assert applied.startswith("error:"), (servers, applied)
                assert DNS_SECURITY.display_name in applied, (servers, applied)


class TestDohIsReachableThroughDnsSecurity:
    """The claim that makes ``disabled`` honest on a machine with ISP DNS: applying
    ``network:dns_security`` leaves a templated resolver on every adapter. Were a
    choice ever to write an address ``_DOH_TEMPLATES`` lacks, the row would be
    shown as actionable and still fail after dns_security ran."""

    @staticmethod
    def _written_by(choice: str) -> set[str]:
        branch = re.search(
            rf"'%value%' -eq '{choice}'\) \{{ (.*?)\$changed\+\+", DNS_SECURITY.apply_command
        )
        assert branch, f"apply_command has no branch for {choice!r}"
        return set(re.findall(r"'([0-9a-f.:]+)'", branch.group(1)))

    def test_every_non_default_choice_writes_resolvers_that_all_have_a_template(self) -> None:
        choices = [c for c in DNS_SECURITY.choices if c != DNS_SECURITY.default_value]
        assert DNS_SECURITY.recommended_value in choices
        for choice in choices:
            written = self._written_by(choice)
            assert len(written) == 4, (choice, written)  # an IPv4 pair and an IPv6 pair
            missing = written - set(network_module._DOH_TEMPLATES)
            assert not missing, f"{choice} writes {sorted(missing)} with no DoH template"

    def test_the_default_choice_writes_no_resolver_so_there_is_nothing_to_template(self) -> None:
        assert DNS_SECURITY.default_value not in {
            c for c in DNS_SECURITY.choices if f"'%value%' -eq '{c}'" in DNS_SECURITY.apply_command
        }

    def test_dns_over_https_runs_after_dns_security_on_the_same_resource(self) -> None:
        assert "network:dns_security" in DNS_OVER_HTTPS.apply_after
        assert DNS_OVER_HTTPS.resource == DNS_SECURITY.resource
