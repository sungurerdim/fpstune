"""A sentinel is the absence of a value, so it can never be one of the choices.

`ABSENT_READINGS` is the project's single set of spellings meaning "this is not
on this machine", and `detection.py` turns every one of them into
`is_applicable=False` with the value cleared. A setting that also lists the same
string in its own `choices` says the opposite: that "not installed" is a state
the user can be in, look at, and pick.

Both cannot be true, and the disagreement is not academic. It cost a release:
`test_detected_values.py` asserts that no reading falls outside its setting's
`choices`, and a sentinel listed as a choice satisfies that assertion while
being exactly the defect it was written to catch. Eighteen game settings passed
that test on every machine with the game installed and failed it on CI, and the
reason they could ever pass is that some of their siblings had quietly declared
the sentinel legal.

Downstream the same string reaches `apply_value_map`, `value_hints` and the UI's
choice list, where it means "apply not_installed" — an operation with no
meaning that the API has to special-case at the boundary.
"""

from __future__ import annotations

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, is_absent_reading
from fpstune.settings.registry import SettingsRegistry


@pytest.fixture(scope="module")
def static_settings():
    return SettingsRegistry(discover_dynamic=False).get_all()


@pytest.fixture(scope="module")
def dynamic_settings():
    return SettingsRegistry(discover_dynamic=True).get_all()


def _sentinels_in_choices(settings) -> list[str]:
    return [
        f"{s.id}: {choice!r} in choices={s.choices}"
        for s in settings
        for choice in s.choices
        if is_absent_reading(choice)
    ]


def _sentinels_in_apply_map(settings) -> list[str]:
    return [
        f"{s.id}: apply_value_map[{key!r}]"
        for s in settings
        for key in s.apply_value_map
        if is_absent_reading(key)
    ]


def test_no_setting_offers_a_sentinel_as_a_choice(static_settings) -> None:
    offenders = _sentinels_in_choices(static_settings)
    assert offenders == [], (
        f"{len(offenders)} setting(s) list an absent reading among their own choices. "
        "Detection already turns these into is_applicable=False with the value "
        "cleared, so listing one lets the contract test pass on a sentinel it "
        "exists to reject:\n  " + "\n  ".join(offenders)
    )


def test_no_per_adapter_setting_offers_one_either(dynamic_settings) -> None:
    """The half a static-only audit cannot see.

    Per-adapter settings are instantiated at runtime, one set per NIC, so they
    are absent from the static registry entirely — the same blind spot that let
    twenty-nine C1 violations hide behind a static count of eight.
    """
    offenders = _sentinels_in_choices(dynamic_settings)
    assert offenders == [], "\n  ".join(offenders)


def test_no_setting_can_be_asked_to_apply_a_sentinel(dynamic_settings) -> None:
    """ "Apply not_installed" is not an operation.

    A sentinel key in `apply_value_map` makes the absence look writable, which is
    why `settings.py` has to reject it again at the API boundary.
    """
    offenders = _sentinels_in_apply_map(dynamic_settings)
    assert offenders == [], "\n  ".join(offenders)


def test_a_recommendation_is_never_an_absence(dynamic_settings) -> None:
    """Recommending a sentinel would make "optimize everything" write one."""
    offenders = [
        s.id
        for s in dynamic_settings
        if is_absent_reading(s.recommended_value) or is_absent_reading(s.default_value)
    ]
    assert offenders == [], offenders


@pytest.mark.parametrize("sentinel", sorted(ABSENT_READINGS))
def test_the_guard_actually_fires(sentinel: str) -> None:
    """A gate that cannot fail is indistinguishable from a gate that passes."""
    from types import SimpleNamespace

    offending = SimpleNamespace(
        id="fake:setting", choices=("enabled", sentinel), apply_value_map={}
    )
    assert _sentinels_in_choices([offending]) == [
        f"fake:setting: {sentinel!r} in choices=('enabled', {sentinel!r})"
    ]

    clean = SimpleNamespace(id="fake:setting", choices=("enabled", "disabled"), apply_value_map={})
    assert _sentinels_in_choices([clean]) == []
    assert _sentinels_in_apply_map([SimpleNamespace(id="f:s", apply_value_map={sentinel: 1})]) == [
        f"f:s: apply_value_map[{sentinel!r}]"
    ]
