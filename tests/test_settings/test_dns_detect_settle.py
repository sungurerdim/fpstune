"""DNS detection must not read "no adapter is up" as "the ISP resolver is set".

A NIC restart takes the interface down for a moment. The old DNS command saw zero
adapters and left its default answer `isp` in place; the old DoH command saw zero
pairs and answered `not_supported`. Both are false readings that make a correct
apply look undone (the #123 failure). The shared filter now waits for an up
adapter, and DNS answers `not_available` only when none comes back.
"""

from __future__ import annotations

from fpstune.settings.definitions.network import DNS_OVER_HTTPS, DNS_SECURITY


def test_dns_security_waits_for_an_up_adapter() -> None:
    command = DNS_SECURITY.detect_command
    assert "AddSeconds(10)" in command
    assert "Start-Sleep -Milliseconds 500" in command
    assert "not_available" in command


def test_dns_over_https_uses_the_same_wait() -> None:
    command = DNS_OVER_HTTPS.detect_command
    assert "AddSeconds(10)" in command
    # No up adapter is still "not_supported" for DoH: it is an applicability
    # result, not the false `disabled` the row would otherwise show.
    assert "not_supported" in command


def test_dns_security_has_no_false_isp_fallthrough() -> None:
    command = DNS_SECURITY.detect_command
    # `isp` is the legitimate configured answer, but it must not be the answer
    # when the adapter list is empty (the old `if count > 0` with no else).
    assert "if ($adapters.Count -eq 0) { $result = 'not_available' }" in command
    assert "catch { throw }" in command
