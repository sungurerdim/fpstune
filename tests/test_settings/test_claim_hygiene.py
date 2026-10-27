"""A claim has to say what the change buys, and a guard must not sell a gain.

C2 used to pass any row with one non-``stability`` key, including a row whose only
number was zero. C11 rule 1 is the stricter rule the UI depends on: a row that
changes a value must claim a benefit, and a drift guard (recommended == default)
must not present a restoration as a performance gain.

The parser deliberately accepts a qualitative benefit ("improved", "reduced",
"fixes", ...) because C11 rule 4 recognises claims no benchmark can adjudicate.
What it rejects is a non-guard row whose every claim is zero/neutral, and a guard
whose only non-zero number is a gain-shaped one with no drift label.
"""

from __future__ import annotations

from fpstune.settings.base import SettingCategory, SettingExecutor
from tests.test_settings.dynamic_rows import all_settings

# Claims that are benefits even when they carry no number. The UI treats these as
# their own class (C11 rule 4); do not force a fake measurement into them.
_QUALITATIVE_BENEFIT_KEYS = {
    "ability_readability",
    "driver_stability",
    "footstep_clarity",
    "frame_consistency",
    "frame_time_consistency",
    "frametime_consistency",
    "gpu_load",
    "input_precision",
    "network_consistency",
    "packet_loss",
    "privacy",
    "security",
    "startup_time",
    "stutter_reduction",
    "system_integrity",
    "target_clarity",
    "target_visibility",
    "throughput",
    "ux",
    "visual_quality",
}

_BENEFIT_WORDS = (
    "improved",
    "reduced",
    "lower",
    "better",
    "fixed",
    "fixes",
    "removes",
    "restored",
    "protected",
    "kept",
    "high",
)

_NEUTRAL_WORDS = (
    "preserved",
    "maintained",
    "unaffected",
    "no ceiling",
    "marginal",
    "unbound",
)

_DRIFT_WORDS = (
    "removed",
    "restored",
    "preserved",
    "maintained",
    "ceiling",
    "retained",
    "unbound",
    "longevity",
    "cap",
)


def _zero(value: object) -> bool:
    text = str(value).strip().lower()
    if text in {"", "0", "0.0", "0%", "+0", "+0.0", "-0", "-0.0", "0 to 0", "0-0"}:
        return True
    return text.startswith("0 ") and "to 0" in text


def _benefit(setting: SettingExecutor) -> bool:
    for key, value in setting.impact_scores.items():
        if key == "stability" or _zero(value):
            continue
        text = str(value).strip().lower()
        if text in _NEUTRAL_WORDS:
            continue
        if key in _QUALITATIVE_BENEFIT_KEYS and any(word in text for word in _BENEFIT_WORDS):
            return True
        if any(word in text for word in _BENEFIT_WORDS):
            return True
        if text.startswith(("+", "-")) or text[:1].isdigit():
            return True
    return False


def test_a_non_guard_row_claims_a_benefit() -> None:
    offenders = sorted(
        setting.id
        for setting in all_settings()
        if not setting.is_action
        and not setting.is_readonly
        and setting.recommended_value != setting.default_value
        and not _benefit(setting)
    )
    assert not offenders, "a change with no claimed benefit is not a tweak: " + ", ".join(offenders)


def _positive_number(value: object) -> bool:
    text = str(value).strip().lower().replace("%", "")
    try:
        return float(text.split(" to ")[0].split("-")[0]) > 0
    except ValueError:
        return False


def _guard_gain(setting: SettingExecutor) -> str | None:
    if setting.is_action or setting.is_readonly:
        return None
    if setting.recommended_value != setting.default_value:
        return None
    for key, value in setting.impact_scores.items():
        if key == "stability" or not _positive_number(value):
            continue
        if any(word in key.lower() or word in str(value).lower() for word in _DRIFT_WORDS):
            continue
        # A temperature or power cost is not a gain; it is a cost the guard
        # exists to undo. The label rule applies to benefit-shaped metrics.
        if key in {"gpu_temp_c", "cpu_temp_c", "power_w"}:
            continue
        return f"{setting.id}:{key}={value!r}"
    return None


def test_a_guard_does_not_claim_a_gain_without_a_drift_label() -> None:
    offenders = sorted(
        finding for setting in all_settings() if (finding := _guard_gain(setting)) is not None
    )
    assert not offenders, "guard rows claim a gain without a drift label: " + ", ".join(offenders)


def _sample(**overrides: object) -> SettingExecutor:
    fields: dict[str, object] = {
        "id": "test:sample",
        "category": SettingCategory.CORE,
        "display_name": "Sample",
        "description": "Sample.",
        "choices": ("off", "on"),
        "default_value": "off",
        "recommended_value": "on",
        "impact_scores": {"latency_ms": 0.0, "stability": "high"},
    }
    return SettingExecutor(**(fields | overrides))


def test_the_gate_rejects_a_non_guard_that_claims_nothing() -> None:
    assert _benefit(_sample()) is False


def test_the_gate_rejects_a_guard_that_claims_a_gain() -> None:
    finding = _guard_gain(
        _sample(
            default_value="on",
            recommended_value="on",
            impact_scores={"fps": "+10%", "stability": "high"},
        )
    )
    assert finding is not None
    assert "fps='+10%'" in finding


def test_the_parser_reads_the_shipped_claim_forms() -> None:
    assert _benefit(_sample(impact_scores={"fps": "+3-5%", "stability": "high"})) is True
    assert _benefit(_sample(impact_scores={"latency_ms": -15.0, "stability": "high"})) is True
    assert _benefit(_sample(impact_scores={"ram_saved": "50-150MB", "stability": "high"})) is True
    assert _benefit(_sample(impact_scores={"fps": "0 to -3%", "stability": "high"})) is True
    assert _benefit(_sample(impact_scores={"fps": "0%", "stability": "high"})) is False
    assert _positive_number("+3-5%") is True
    assert _positive_number("50-150MB") is True
    assert _positive_number("-15.0") is False
    assert _positive_number("0 to -3%") is False


def test_the_gate_accepts_a_labeled_drift_removal() -> None:
    # The value itself names the drift, so a guard may carry it.
    finding = _guard_gain(
        _sample(
            default_value="on",
            recommended_value="on",
            impact_scores={"fps": "ceiling removed", "stability": "high"},
        )
    )
    assert finding is None
