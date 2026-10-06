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

Two more rules hold the same row to what it actually does.

*The state a lead names.* A choice that is not a plain enabled/disabled pair
("default" / "immediate", "ideal" / "rocket") is judged the same way: the lead of
``recommended_impact`` is resolved against the row's own choices and their display
hints (``value_hints``), never against a table of rows kept here, and when it names a
choice that is not ``recommended_value`` the copy argues for the other state.
``network:tcp_ack_frequency`` recommended ``default`` while its impact read
"Immediate (1)". ``current_impact`` is not judged: it describes the state the player
is in, which on a "keep it" row *is* the recommended one.

*The gain a score claims.* A guard puts back, or keeps, a state the machine already
had, so ``impact_scores`` may say it changes nothing or that it restores something,
and nothing else (``network:nagle_algorithm``: ``latency_ms`` 0, ``download_throughput``
"restored"). A figure that reaches a gain in its metric's own direction (negative
latency, positive fps, RAM or startup time saved) is the effect of the *opposite*
action, claimed by the row that undoes it (``network:tcp_ack_frequency``: latency "0 to
-2" while recommending the Windows default). A cost may be stated; a gain may not.
"""

from __future__ import annotations

import inspect
import re

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


def _per_adapter_settings() -> list[SettingExecutor]:
    """Per-adapter rows are built per machine; the factories that take only an adapter."""
    from fpstune.settings.definitions import network

    rows: list[SettingExecutor] = []
    for name, factory in vars(network).items():
        if not (name.startswith("create_") and name.endswith("_setting")):
            continue
        if list(inspect.signature(factory).parameters) == ["interface_index", "display_name"]:
            rows.append(factory(7, "Test adapter"))
    return rows


def _guards() -> list[SettingExecutor]:
    return [
        s
        for s in [*get_all_static_settings(), *_per_adapter_settings()]
        if s.recommended_value == s.default_value and not s.is_readonly and not s.is_action
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


# ---------------------------------------------------------------------------
# The state a lead names, for choices that are not an enabled/disabled pair.
# ---------------------------------------------------------------------------


def _words(text: str) -> str:
    """A state as a reader sees it: no parenthetical, no underscores, one case."""
    text = re.sub(r"\([^)]*\)", " ", text.replace("_", " "))
    return " ".join(text.lower().split())


def _named_choices(setting: SettingExecutor, impact: str) -> set[str]:
    """The choices the lead of an impact string names; empty when it names none.

    A lead names a choice when it equals the choice's own words or the display hint the
    row carries for it, or is the first words of them ("Medium" for "Medium Quality").
    "Windows' own value" or "Keep enabled" name no choice and so can never contradict.
    """
    state, colon, _ = impact.partition(":")
    lead = _words(state) if colon else ""
    if not lead:
        return set()
    named: set[str] = set()
    for choice in setting.choices:
        for label in (choice, setting.value_hints.get(choice, "")):
            name = _words(label)
            if name and (name == lead or name.startswith(f"{lead} ")):
                named.add(choice)
    return named


def _argues_for_another_choice(setting: SettingExecutor) -> bool:
    named = _named_choices(setting, setting.recommended_impact or "")
    return bool(named) and str(setting.recommended_value) not in named


def test_no_guard_row_leads_its_recommended_impact_with_a_different_choice() -> None:
    offenders = sorted(s.id for s in _guards() if _argues_for_another_choice(s))

    assert not offenders, (
        "recommended_impact leads with a choice other than recommended_value on a guard row: "
        f"{offenders}"
    )


def _choice_row(
    recommended: str, impact: str, choices: tuple[str, ...], hints: dict[str, str] | None = None
) -> SettingExecutor:
    setting = SettingExecutor.__new__(SettingExecutor)
    object.__setattr__(setting, "recommended_value", recommended)
    object.__setattr__(setting, "recommended_impact", impact)
    object.__setattr__(setting, "choices", choices)
    object.__setattr__(setting, "value_hints", hints or {})
    return setting


@pytest.mark.parametrize(
    ("recommended", "impact", "choices", "hints", "expected"),
    [
        ("default", "Immediate (1): Acks at once", ("default", "immediate"), {}, True),
        ("ideal", "Rocket: Clocks jump", ("ideal", "single", "rocket"), {}, True),
        ("aggressive", "Efficient Aggressive: x", ("aggressive", "efficient_aggressive"), {}, True),
        ("default", "Optimized: x", ("default", "optimized"), {"optimized": "64"}, True),
        ("default", "64: x", ("default", "optimized"), {"optimized": "64"}, True),
        ("default", "Default (2): Windows acks", ("default", "immediate"), {}, False),
        ("Medium Quality", "Medium: x", ("Low Quality", "Medium Quality"), {}, False),
        ("default", "Windows' own value: x", ("default", "immediate"), {}, False),
        ("default", "Immediate (1) has no colon", ("default", "immediate"), {}, False),
        ("100", "100% (Windows default): x", (), {}, False),
    ],
)
def test_the_choice_rule_resolves_a_lead_against_the_rows_own_choices(
    recommended: str,
    impact: str,
    choices: tuple[str, ...],
    hints: dict[str, str],
    expected: bool,
) -> None:
    """Pins the rule, so a loosened match cannot quietly stop the guard above firing."""
    assert _argues_for_another_choice(_choice_row(recommended, impact, choices, hints)) is expected


# ---------------------------------------------------------------------------
# The gain a score claims.
# ---------------------------------------------------------------------------

# Metrics where a smaller number is the gain; a negative figure reaches it.
_LOWER_IS_BETTER = frozenset(
    {
        "latency_ms",
        "latency_spike_ms",
        "jitter_ms",
        "cpu_usage",
        "gpu_temp_c",
        "power_watts",
        "vram_mb",
    }
)
# Metrics where a larger number is the gain; a positive figure reaches it.
_HIGHER_IS_BETTER = frozenset(
    {
        "fps",
        "fps_gpu_bound",
        "fps_cpu_bound",
        "fps_1_percent_low",
        "throughput",
        "download_throughput",
        "ram_saved",
        "ram_freed",
        "disk_freed",
        "startup_speed",
    }
)
# A cap's own value or a state, not a gain: "30" is the cap, "removed" is what the row does.
_STATE_KEYS = frozenset(
    {
        "fps_cap_removed",
        "fps_menu_ceiling",
        "fps_unfocused_ceiling",
        "fps_battery_ceiling",
        "fps_retained",
    }
)
# What a guard may say in words: nothing changes, or something is back.
_KEPT_WORDS = frozenset(
    {
        "preserved",
        "unaffected",
        "maintained",
        "restored",
        "protected",
        "verified",
        "neutral",
        "unchanged",
        "no ceiling",
    }
)
_FIGURE = re.compile(r"([+-]?)\s*(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?")


def _reach(value: str | float) -> tuple[float, float] | None:
    """The lowest and highest figure a score states, ``None`` when it states none.

    ``"+25-45%"`` is 25 to 45, ``"-35-47%"`` is -47 to -35, ``"0 to -2"`` is -2 to 0: a sign
    belongs to the whole range it leads.
    """
    if isinstance(value, int | float):
        return (float(value), float(value))
    figures: list[float] = []
    for sign, low, high in _FIGURE.findall(value):
        factor = -1.0 if sign == "-" else 1.0
        figures += [factor * float(low)] + ([factor * float(high)] if high else [])
    return (min(figures), max(figures)) if figures else None


def _claims_a_gain(key: str, value: str | float) -> bool:
    if key in _STATE_KEYS:
        return False
    if key == "stability":
        return str(value).lower() == "improved"
    reach = _reach(value)
    if reach is None:
        return str(value).strip().lower() not in _KEPT_WORDS
    low, high = reach
    if key in _LOWER_IS_BETTER:
        return low < 0
    if key in _HIGHER_IS_BETTER:
        return high > 0
    return low != 0 or high != 0  # a metric whose direction is not classified here


def _gain_claims(setting: SettingExecutor) -> dict[str, str | float]:
    return {k: v for k, v in setting.impact_scores.items() if _claims_a_gain(k, v)}


def test_no_guard_row_scores_a_gain_from_the_action_it_undoes() -> None:
    offenders = {s.id: _gain_claims(s) for s in _guards() if _gain_claims(s)}

    assert not offenders, (
        "a guard keeps or restores a state: its impact_scores may say 0 or 'preserved'/'restored' "
        "(network:nagle_algorithm), never a gain. Unclassified metric? Add it to "
        "_LOWER_IS_BETTER or _HIGHER_IS_BETTER.\n"
        + "\n".join(f"  {sid}: {claims}" for sid, claims in sorted(offenders.items()))
    )


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("latency_ms", "0 to -2 (TCP titles only)", True),
        ("latency_ms", -0.5, True),
        ("latency_ms", 0.0, False),
        ("latency_ms", 3, False),  # a cost is a statement, not a gain
        ("fps", "+25-45%", True),
        ("fps", "0 to +5%", True),
        ("fps", "+0-1%", True),
        ("fps", "0%", False),
        ("fps", "0 to -3%", False),
        ("fps", "-35-47%", False),
        ("ram_saved", "5-15MB", True),
        ("ram_saved", "0-500MB kept resident", True),
        ("ram_saved", 0.0, False),
        ("startup_speed", "+3-8s", True),
        ("vram_mb", -1536, True),
        ("download_throughput", "restored", False),
        ("download_throughput", "reduced", True),
        ("throughput", "high", True),
        ("network_consistency", "improved", True),
        ("target_visibility", "preserved", False),
        ("stability", "high", False),
        ("stability", "improved", True),
        ("fps_unfocused_ceiling", 30, False),
        ("some_new_metric", 4, True),
        ("some_new_metric", 0, False),
    ],
)
def test_the_gain_rule_reads_a_score_in_its_metrics_own_direction(
    key: str, value: str | float, expected: bool
) -> None:
    """Pins the rule, so a loosened parse cannot quietly stop the guard above firing."""
    assert _claims_a_gain(key, value) is expected
