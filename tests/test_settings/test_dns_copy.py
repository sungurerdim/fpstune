"""The Secure DNS copy claims only what its resolver does.

Quad9's own service table (quad9.net/service/service-addresses-and-features):
9.9.9.9 / 149.112.112.112 are the no-ECS service; only 9.9.9.11 / 149.112.112.11
send EDNS Client Subnet. The shipped description used to promise the
client-subnet hint for 9.9.9.9, and ``recommended_impact`` carried "median
lookup 7 ms" — a measurement from the developer's line shown to every user as if
it were theirs (C11). Both are gone; this pins them gone.
"""

from __future__ import annotations

import re

import pytest

from fpstune.settings.registry import SettingsRegistry


@pytest.fixture(scope="module")
def dns_security():
    setting = SettingsRegistry(discover_dynamic=False).get("network:dns_security")
    assert setting is not None
    return setting


def test_no_ecs_is_claimed_for_the_recommended_resolver(dns_security) -> None:
    """If the copy mentions the client-subnet hint at all, it says nobody offered sends it."""
    copy = f"{dns_security.description} {dns_security.recommended_impact}"
    if "client-subnet" in copy:
        assert "none of the resolvers offered here sends the client-subnet hint" in copy
    assert "ECS" not in dns_security.recommended_impact


def test_no_millisecond_figure_is_shown_as_a_fact_about_the_users_line(dns_security) -> None:
    assert not re.search(r"\d+\s*ms", dns_security.recommended_impact)
    assert not re.search(r"\d+\s*ms", dns_security.current_impact)
