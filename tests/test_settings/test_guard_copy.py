"""A guard row's copy argues for the state it keeps, never against it.

A *guard* is a row whose ``recommended_value`` equals its ``default_value``
(Product Goal consequence 2 and 6): it keeps a stock state, or puts it back. Its
``recommended_impact`` is "State: benefit" (C3) for the *recommended* state, so
the state it names has to be that one. ``services:UCPD`` shipped recommending
``enabled`` while its recommended impact read "Disabled: Full control ..." and
its effect said "Disables UCPD" — the row guarded the mitigation and the player
read an argument for switching it off.

The rule is mechanical on purpose: only an unambiguous polarity pair (enabled /
disabled, on / off) is judged. A recommended value such as ``stock`` or ``100``
names no polarity, and a lead word such as "Windows default" names none either,
so neither can contradict anything; guessing at them would produce false alarms.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions import get_all_static_settings

# word -> True when it names the "on" side
_POLARITY = {"enabled": True, "on": True, "disabled": False, "off": False}


def _lead_state(impact: str) -> str:
    """The state word of a C3 ``State: consequence`` string, lower-cased; ``""`` when none."""
    state, colon, _ = impact.partition(":")
    words = state.split()
    return words[0].lower() if colon and words else ""


def _contradicts_recommendation(setting: SettingExecutor) -> bool:
    recommended = _POLARITY.get(str(setting.recommended_value).lower())
    stated = _POLARITY.get(_lead_state(setting.recommended_impact or ""))
    return recommended is not None and stated is not None and recommended != stated


def _guards() -> list[SettingExecutor]:
    return [
        s
        for s in get_all_static_settings()
        if s.recommended_value == s.default_value and not s.is_readonly
    ]


def test_no_guard_row_recommends_one_state_and_argues_for_the_other() -> None:
    offenders = sorted(s.id for s in _guards() if _contradicts_recommendation(s))

    assert not offenders, (
        "recommended_impact names the opposite state to recommended_value on a guard row: "
        f"{offenders}"
    )


@pytest.mark.parametrize(
    ("recommended", "impact", "expected"),
    [
        ("enabled", "Disabled: Full control over default app associations", True),
        ("disabled", "Enabled: Blocks registry changes", True),
        ("off", "On: Keeps the thing running", True),
        ("enabled", "Enabled: Keeps the mitigation on", False),
        ("enabled", "Enabled (Windows' own value): Stock behaviour", False),
        ("stock", "Disabled: not judged, the value names no polarity", False),
        ("enabled", "Windows default: names no polarity", False),
        ("enabled", "Disabled without a colon argues nothing the rule can read", False),
        ("enabled", "", False),
    ],
)
def test_the_rule_itself_judges_only_an_unambiguous_polarity_pair(
    recommended: str, impact: str, expected: bool
) -> None:
    """Pins the rule, so a loosened lead-word parse cannot quietly stop the guard above firing."""
    setting = SettingExecutor.__new__(SettingExecutor)
    object.__setattr__(setting, "recommended_value", recommended)
    object.__setattr__(setting, "recommended_impact", impact)

    assert _contradicts_recommendation(setting) is expected
