"""C1: an unproven benefit must state what applying it costs.

The rule in CLAUDE.md is `evidence_level="experimental"` implies
`risk_level="advanced"` plus a non-None `risk_warning`.

This file exists because the first audit of the rule counted only the static
registry and reported eight violations, while the per-adapter settings —
instantiated at runtime, one set per NIC — held twenty-nine more. A gate that
measures the easy half of the registry reads as compliance and is not.
"""

from __future__ import annotations

import pytest

from fpstune.settings.registry import SettingsRegistry


@pytest.fixture(scope="module")
def static_settings():
    return SettingsRegistry(discover_dynamic=False).get_all()


def _violations(settings) -> list[str]:
    return [
        s.id
        for s in settings
        if s.evidence_level == "experimental" and (s.risk_level != "advanced" or not s.risk_warning)
    ]


@pytest.fixture(scope="module")
def dynamic_settings():
    return SettingsRegistry(discover_dynamic=True).get_all()


def test_dynamic_registry_is_c1_clean(dynamic_settings) -> None:
    """The half the first audit could not see.

    Per-adapter settings are instantiated at runtime, one set per NIC, so they
    are absent from the static registry entirely. Twenty-nine violations lived
    here while the static count read eight.
    """
    offenders = _violations(dynamic_settings)
    assert offenders == [], offenders


def test_every_advanced_setting_says_what_it_costs(dynamic_settings) -> None:
    """The taxonomy's own rule: advanced risk requires a stated cost."""
    offenders = [
        s.id for s in dynamic_settings if s.risk_level == "advanced" and not s.risk_warning
    ]
    assert offenders == [], offenders


def test_static_registry_is_c1_clean(static_settings) -> None:
    offenders = _violations(static_settings)
    assert offenders == [], (
        "experimental evidence without advanced risk + a risk_warning. Either the "
        f"benefit is better supported than 'experimental', or say what it costs: {offenders}"
    )


def test_a_setting_that_recommends_its_own_default_is_not_experimental(
    static_settings,
) -> None:
    """ "Leave this alone" is a claim, and a well-supported one.

    Five settings recommended the Windows default *and* graded their evidence as
    experimental, which reads as "we are unsure this unproven tweak helps" when
    the actual claim is "the vendor default is already right". The grade applies
    to the benefit, so a drift guard cannot be experimental about it.
    """
    offenders = [
        s.id
        for s in static_settings
        if s.recommended_value is not None
        and s.default_value is not None
        and str(s.recommended_value) == str(s.default_value)
        and s.evidence_level == "experimental"
    ]
    assert offenders == [], offenders


def test_the_check_actually_fires() -> None:
    """A gate that cannot fail is indistinguishable from a gate that passes."""

    from types import SimpleNamespace

    unguarded = SimpleNamespace(
        id="fake:setting",
        evidence_level="experimental",
        risk_level="low",
        risk_warning=None,
    )
    assert _violations([unguarded]) == ["fake:setting"]

    guarded = SimpleNamespace(
        id="fake:setting",
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning="costs something",
    )
    assert _violations([guarded]) == []
