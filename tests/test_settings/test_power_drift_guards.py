"""A setting that recommends Windows' own value cannot claim a gain.

Three power settings turned into drift guards the moment their `default_value`
was derived from this machine instead of recalled: `cpu_min_parking` (Windows
ships 100 on mains here), `thermal_cooling` (Active) and `wlan_power_saving`
(Maximum Performance). Their recommendation now equals their default, which is
the consequence-2 shape — fpstune puts the value back when another optimizer, a
guide or an older fpstune release moved it — but their copy and their
`impact_scores` still promised the gain of *changing* it: `fps_cpu_bound
"+0-15%"` for a cooling policy the machine already has, `latency_spike_ms
"20-100 eliminated"` for a radio that was never asleep.

That is a C11 rule-1 claim with nothing behind it: on a machine at stock the
apply changes nothing, so the honest score is zero and the honest sentence says
what it guards rather than what it buys. The existing guards in this module
already do exactly that — `cpu_min_state` carries `power_watts: 0.0`,
`cpu_max_state` carries `fps_cpu_bound: 0.0` — so the rule is a generalisation
of what the file already knew.

`cpu_boost` is the same question from the other side: Windows ships Aggressive,
fpstune recommends Efficient Aggressive, and Microsoft's own table says index 4
behaves as index 2. Same boost ceiling, chosen with efficiency in mind — so what
it buys is heat, not frames, and consequence 4 files heat under `thermal`.
"""

from __future__ import annotations

import re

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.definitions.power import POWER_CPU_BOOST, POWER_SETTINGS
from fpstune.settings.impact_categories import derive_impact_categories

# A claim has a magnitude when it says a number: "+0-15%", -0.5, "20-100
# eliminated". "high", "improved" and "marginal" say none, and C2 does not count
# them as performance metrics either.
_HAS_A_NUMBER = re.compile(r"\d")


def _drift_guards() -> list[SettingExecutor]:
    """Every power setting whose recommendation is the value Windows ships here."""
    return [
        setting
        for setting in POWER_SETTINGS
        if setting.detect_type is DetectType.POWERCFG
        and setting.recommended_value is not None
        and values_equal(setting.recommended_value, setting.default_value)
    ]


def _claims_a_magnitude(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return bool(_HAS_A_NUMBER.search(str(value)))


def test_there_are_drift_guards_to_check() -> None:
    """Positive control: an empty list would make every test below vacuous."""
    ids = {s.id for s in _drift_guards()}
    assert {
        "power:cpu_min_parking",
        "power:thermal_cooling",
        "power:wlan_power_saving",
    } <= ids, f"expected the three derived guards among {sorted(ids)}"


@pytest.mark.parametrize("setting", _drift_guards(), ids=lambda s: s.id)
def test_a_guard_claims_no_gain_the_stock_value_already_has(setting: SettingExecutor) -> None:
    claimed = {
        key: value for key, value in setting.impact_scores.items() if _claims_a_magnitude(value)
    }
    assert not claimed, (
        f"{setting.id} recommends {setting.recommended_value!r}, which is already Windows' own "
        f"value on this machine, yet claims {claimed}. Applying it changes nothing on a stock "
        "machine, so the number is a claim no instrument can produce (C11)."
    )


# The guards this pass created, by deriving `default_value` from the machine.
# The four written as guards from the start — cpu_min_state, cpu_max_state,
# cpu_idle_states, cpu_increase_time — already argue their case in their own
# words, and re-phrasing them to satisfy a keyword would be churn, not honesty.
_DERIVED_GUARDS = (
    "power:cpu_min_parking",
    "power:thermal_cooling",
    "power:wlan_power_saving",
    "power:cpu_decrease_threshold",
)


@pytest.mark.parametrize("setting_id", _DERIVED_GUARDS)
def test_a_derived_guard_says_it_is_windows_own_value(setting_id: str) -> None:
    """The user reads why applying it may change nothing — consequence 2."""
    setting = next(s for s in _drift_guards() if s.id == setting_id)
    copy = f"{setting.description} {setting.recommended_impact} {setting.effect}".lower()
    assert "windows" in copy, (
        f"{setting.id} is a drift guard, but its copy never says the value it restores is "
        "Windows' own — so a row that changes nothing reads as a tweak that failed."
    )


class TestBoostModeIsAThermalClaim:
    def test_it_claims_heat_rather_than_frames(self) -> None:
        categories = derive_impact_categories(POWER_CPU_BOOST.impact_scores)
        assert "thermal" in categories, (
            f"cpu_boost claims {POWER_CPU_BOOST.impact_scores}, which derives {categories}. "
            "Efficient Aggressive reaches the same boost ceiling as the Aggressive Windows "
            "ships here, so what it saves is heat (consequence 4)."
        )
        assert "fps" not in categories and "latency" not in categories, (
            "the same ceiling cannot also be more frames"
        )

    def test_the_copy_does_not_promise_frames(self) -> None:
        copy = f"{POWER_CPU_BOOST.description} {POWER_CPU_BOOST.recommended_impact}".lower()
        for promise in ("fps", "faster", "near-maximum"):
            assert promise not in copy, (
                f"cpu_boost copy still promises {promise!r} over a mode with the same ceiling"
            )
