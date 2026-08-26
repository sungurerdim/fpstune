"""What the machine costs when nothing is asking it for anything.

Heat is not a comfort metric here. A CPU held at its maximum multiplier through
an idle desktop arrives at the next match already near the temperature where it
throttles, and a frame rate that decays in minute forty is indistinguishable —
to the user, and to almost every benchmark — from a machine that was never tuned
at all. That failure is slow, invisible at the moment of the tweak, and it is
exactly what the most widely repeated "gaming optimizations" cause.

So these tests guard the half of the design that has no immediate symptom:

* nothing fpstune recommends may pin the machine at full power while idle
* nothing may cap it below full power while busy
* coming back up must never be slower than going down
* and the numbers must be ones Windows will actually accept on this machine

The last one is the C1 rule with teeth. Every range below was read off Windows'
own setting catalogue rather than recalled, because a recommendation outside the
range powercfg publishes is a setting that silently never applies.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions.power import POWER_SETTINGS
from fpstune.settings.impact_categories import derive_impact_categories

# The block added for idle behaviour. Named rather than derived so that deleting
# one of them fails a test instead of quietly shrinking the suite.
IDLE_BEHAVIOUR_IDS = (
    "power:cpu_min_state",
    "power:cpu_max_state",
    "power:cpu_idle_states",
    "power:cpu_perf_check_interval",
    "power:cpu_decrease_time",
    "power:cpu_increase_time",
    "power:cpu_latency_hint_unpark",
    "power:cpu_latency_hint_perf",
    "power:cpu_parking_increase_policy",
    "power:cpu_parking_increase_time",
)

BY_ID: dict[str, SettingExecutor] = {s.id: s for s in POWER_SETTINGS}


def _setting(setting_id: str) -> SettingExecutor:
    setting = BY_ID.get(setting_id)
    assert setting is not None, f"{setting_id} is not registered in POWER_SETTINGS"
    return setting


class TestNothingRecommendsBurningPowerForNothing:
    """The three settings whose wrong value costs heat and buys no frames."""

    def test_idle_cores_are_allowed_to_clock_down(self) -> None:
        """ "Set minimum processor state to 100" is the advice this undoes.

        At 100 every core holds its maximum multiplier at an idle desktop. The
        frame rate is identical — clock-up is already immediate via the scale-up
        policy — and the thermal budget is spent before the match begins.
        """
        assert _setting("power:cpu_min_state").recommended_value == 5

    def test_cores_are_allowed_to_rest(self) -> None:
        """`Processor idle disable = 1` forbids every C-state, permanently.

        Continuous heat, measurably shorter part life, and not one extra frame.
        """
        assert _setting("power:cpu_idle_states").recommended_value == "enabled"

    def test_full_speed_is_still_available_when_it_is_wanted(self) -> None:
        """The mirror image: 99 is advised as a cooling trick and kills turbo.

        Guarded alongside the two above because the honest position is symmetric.
        Refusing to waste power at idle is only defensible if the machine is
        still allowed everything it has under load.
        """
        assert _setting("power:cpu_max_state").recommended_value == 100

    def test_a_latency_sensitive_workload_gets_the_whole_machine(self) -> None:
        """What makes resting safe: a game wakes everything at once, not by half.

        Without this, letting cores idle is a real trade. With it, it is not.
        """
        assert _setting("power:cpu_latency_hint_unpark").recommended_value == 100
        assert _setting("power:cpu_latency_hint_perf").recommended_value == 100


class TestComingBackIsNeverSlowerThanLettingGo:
    def test_clock_up_waits_less_than_clock_down(self) -> None:
        """The asymmetry is the whole design, so it is asserted and not assumed.

        Symmetric timings give a clock that yo-yos: a quiet interval between two
        frames drops it, and the next frame pays to bring it back.
        """
        up = _setting("power:cpu_increase_time").recommended_value
        down = _setting("power:cpu_decrease_time").recommended_value
        assert isinstance(up, int) and isinstance(down, int)
        assert up < down, f"clock-up waits {up} checks, clock-down waits {down}"

    def test_parked_cores_return_at_the_first_sign_of_load(self) -> None:
        assert _setting("power:cpu_parking_increase_time").recommended_value == 1
        assert _setting("power:cpu_parking_increase_policy").recommended_value == "all"

    def test_load_is_re_checked_at_least_as_often_as_windows_does(self) -> None:
        """The interval bounds how long a core sits at the wrong speed.

        Raising it would slow every other setting in this block at once, so the
        direction is pinned rather than just the number.
        """
        setting = _setting("power:cpu_perf_check_interval")
        assert setting.recommended_value <= setting.default_value


class TestTheNumbersAreOnesWindowsAccepts:
    """C1: a value outside the published range is a tweak that never applies."""

    @pytest.mark.parametrize("setting_id", IDLE_BEHAVIOUR_IDS)
    def test_recommended_and_default_sit_inside_the_declared_range(self, setting_id: str) -> None:
        setting = _setting(setting_id)
        if setting.choices:
            assert setting.recommended_value in setting.choices
            assert setting.default_value in setting.choices
            return
        assert setting.min_value is not None and setting.max_value is not None
        for label, value in (
            ("recommended", setting.recommended_value),
            ("default", setting.default_value),
        ):
            assert setting.min_value <= value <= setting.max_value, (
                f"{setting_id} {label}={value} is outside {setting.min_value}..{setting.max_value}"
            )

    @pytest.mark.parametrize("setting_id", IDLE_BEHAVIOUR_IDS)
    def test_every_choice_setting_can_read_back_what_it_writes(self, setting_id: str) -> None:
        """C6: detection must never produce a value outside `choices`.

        The round trip is display -> raw -> display, which is the path an apply
        followed by a verify actually takes.
        """
        setting = _setting(setting_id)
        if not setting.choices:
            return
        for choice in setting.choices:
            raw = setting.apply_value_map[choice]
            assert setting.value_map[raw] == choice


class TestTheyAreClassifiedAsWhatTheyDeliver:
    def test_heat_settings_are_tagged_as_heat_settings(self) -> None:
        """Filed under "fps" they would claim a frame rate they do not raise.

        The same mistake the two idle frame caps carried before they moved to
        the thermal category.
        """
        for setting_id in ("power:cpu_min_state", "power:cpu_idle_states"):
            assert derive_impact_categories(_setting(setting_id).impact_scores) == ["thermal"]

    @pytest.mark.parametrize("setting_id", IDLE_BEHAVIOUR_IDS)
    def test_c2_every_setting_carries_a_non_stability_metric(self, setting_id: str) -> None:
        scores = _setting(setting_id).impact_scores
        assert any(key != "stability" for key in scores), setting_id

    @pytest.mark.parametrize("setting_id", IDLE_BEHAVIOUR_IDS)
    def test_a_drift_guard_scores_zero_rather_than_an_invented_number(
        self, setting_id: str
    ) -> None:
        """Half of these change nothing on a clean machine, and say so.

        A guard whose value depends entirely on how wrong the machine was cannot
        state a gain without inventing one. Scoring 0.0 is the honest answer and
        this pins it, because a later edit that "fills in" a plausible number
        would be fabricating data the tool has no way to support.
        """
        setting = _setting(setting_id)
        if setting.recommended_value != setting.default_value:
            return
        numeric = [v for k, v in setting.impact_scores.items() if k != "stability"]
        assert numeric and all(v == 0.0 for v in numeric), (
            f"{setting_id} recommends its own default but claims {numeric}"
        )
