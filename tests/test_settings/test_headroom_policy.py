"""The measured band and the measured bottleneck have to change something.

Before this, only `met` acted: `critical`, `short` and `near` were identical to
the engine, and the bottleneck reached the user's screen and moved nothing. A
measurement nothing acts on is a number, not a decision — and this product's
whole argument is that a number nobody acts on is the same as no number.

Two properties are pinned here, and they are different promises:

* **What each band does.** `met` raises the value D1b lowered; `short` and
  `critical` move a frame-buying setting out of `complete`; `near` and `unknown`
  change nothing at all.
* **That the values are real.** Every `quality_when_met` must be one of the
  setting's own choices, or the band would recommend something the game cannot
  take (C6) and the UI cannot render.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.settings.base import SettingScope
from fpstune.settings.discovery.headroom import apply_headroom_bands
from fpstune.settings.headroom_policy import (
    GAME_RULES,
    SIDE_CPU,
    SIDE_GPU,
    quality_value,
    rules_for,
    should_promote,
)
from fpstune.settings.performance_headroom import (
    TIER_CRITICAL,
    TIER_MET,
    TIER_NEAR,
    TIER_SHORT,
    TIER_UNKNOWN,
    PerformanceHeadroom,
)
from fpstune.settings.registry import SettingsRegistry


def _headroom(tier: str, bottleneck: str = "gpu") -> PerformanceHeadroom:
    """A measurement that lands in the requested band, against a 300 fps target."""
    ratio = {
        TIER_MET: 1.0,
        TIER_NEAR: 0.9,
        TIER_SHORT: 0.6,
        TIER_CRITICAL: 0.2,
    }[tier]
    return PerformanceHeadroom(
        game="mw4",
        measured_fps=300 * ratio,
        target_fps=300,
        bottleneck=bottleneck,
    )


class TestTheRulesDescribeSettingsThatExist:
    """A rule about a setting nobody ships is a rule that can never fire."""

    def test_every_rule_names_a_registered_setting(self) -> None:
        registry = SettingsRegistry(discover_dynamic=False)
        for game, rules in GAME_RULES.items():
            for rule in rules:
                assert registry.get(rule.setting_id) is not None, (
                    f"{game}: {rule.setting_id} has a band rule but is not registered"
                )

    def test_every_quality_value_is_one_the_game_allows(self) -> None:
        """C6: a recommendation outside `choices` is one nothing can pick."""
        registry = SettingsRegistry(discover_dynamic=False)
        for rules in GAME_RULES.values():
            for rule in rules:
                if rule.quality_when_met is None:
                    continue
                setting = registry.get(rule.setting_id)
                assert setting is not None
                assert rule.quality_when_met in setting.choices, (
                    f"{rule.setting_id}: {rule.quality_when_met!r} not in {setting.choices}"
                )

    def test_a_promoted_rule_is_one_that_sits_behind_an_opt_in(self) -> None:
        """Promoting a setting already in `recommended` would be a no-op rule."""
        registry = SettingsRegistry(discover_dynamic=False)
        for rules in GAME_RULES.values():
            for rule in rules:
                if not rule.promote_when_short:
                    continue
                setting = registry.get(rule.setting_id)
                assert setting is not None
                assert setting.scope is SettingScope.COMPLETE, (
                    f"{rule.setting_id} is promoted below target but already recommended"
                )


class TestWhatEachBandDoes:
    @pytest.mark.parametrize("tier", [TIER_NEAR, TIER_UNKNOWN])
    def test_a_band_with_nothing_to_say_says_nothing(self, tier: str) -> None:
        rule = next(r for r in rules_for("mw4") if r.promote_when_short)
        assert should_promote(rule, tier, "gpu") is False
        assert quality_value(rule, tier) is None

    def test_only_met_raises_a_value(self) -> None:
        rule = next(r for r in rules_for("mw4") if r.quality_when_met)
        assert quality_value(rule, TIER_MET) == rule.quality_when_met
        for tier in (TIER_NEAR, TIER_SHORT, TIER_CRITICAL, TIER_UNKNOWN):
            assert quality_value(rule, tier) is None

    def test_short_promotes_only_the_side_that_is_the_wall(self) -> None:
        """A GPU-bound machine has graphics settings to give; dropping an upscaler
        tier on a CPU-bound one costs image quality and buys nothing."""
        gpu_rule = next(r for r in rules_for("mw4") if r.promote_when_short and r.side == SIDE_GPU)

        assert should_promote(gpu_rule, TIER_SHORT, "gpu") is True
        assert should_promote(gpu_rule, TIER_SHORT, "cpu") is False

    def test_a_cpu_bound_machine_is_offered_nothing_rather_than_something_wrong(self) -> None:
        """MW4 has no CPU-side setting in `complete` that costs the player nothing.

        Every candidate — `marks_player_only` being the clearest — removes
        information the player reads. So on a CPU-bound machine the bottleneck's
        whole effect is to withhold the GPU-side promotions, and this pins that
        the answer is silence rather than a trade that does not help.
        """
        assert not [
            rule for rule in rules_for("mw4") if rule.promote_when_short and rule.side == SIDE_CPU
        ]
        promoted = [rule for rule in rules_for("mw4") if should_promote(rule, TIER_SHORT, SIDE_CPU)]
        assert promoted == []

    @pytest.mark.parametrize("bottleneck", ["both", "unknown"])
    def test_a_machine_saturated_on_both_sides_spends_both(self, bottleneck: str) -> None:
        for rule in rules_for("mw4"):
            if not rule.promote_when_short:
                continue
            assert should_promote(rule, TIER_SHORT, bottleneck) is True

    def test_critical_stops_filtering_by_bottleneck(self) -> None:
        """Below half the target neither side has room, so neither is a filter."""
        for rule in rules_for("mw4"):
            if not rule.promote_when_short:
                continue
            for bottleneck in ("gpu", "cpu", "both", "unknown"):
                assert should_promote(rule, TIER_CRITICAL, bottleneck) is True


class TestTheRegistryAppliesIt:
    """The end of the wire: what a user's scope selector actually contains."""

    def _registry(self, headroom: PerformanceHeadroom | None) -> SettingsRegistry:
        unmeasured = PerformanceHeadroom(game="unmeasured")

        # `now` is accepted and ignored: the real reader takes it for the
        # staleness rule, and a stub with a narrower signature would pass here
        # and fail the moment the caller starts passing one.
        def read(game: str, now: float | None = None) -> PerformanceHeadroom:  # noqa: ARG001
            if headroom is not None and game == headroom.game:
                return headroom
            return unmeasured

        registry = SettingsRegistry(discover_dynamic=False)
        with patch("fpstune.settings.performance_headroom.read_headroom", side_effect=read):
            apply_headroom_bands(registry, registry._probes)
        return registry

    def test_at_target_the_quality_tier_becomes_the_recommendation(self) -> None:
        registry = self._registry(_headroom(TIER_MET))

        upscaler = registry.get("game_config:mw4:dlss_perf_mode")
        assert upscaler is not None
        assert upscaler.recommended_value == "Maximum Quality"
        assert upscaler.scope is SettingScope.RECOMMENDED

        # And a channel D1b lowered without moving its scope is raised too.
        shadows = registry.get("game_config:mw4:shadow_quality")
        assert shadows is not None
        assert shadows.recommended_value == "Medium"

    def test_below_target_the_value_stays_frames_first(self) -> None:
        registry = self._registry(_headroom(TIER_CRITICAL, "both"))

        upscaler = registry.get("game_config:mw4:dlss_perf_mode")
        assert upscaler is not None
        # Only the scope moved: the frames-first value is still the answer.
        assert upscaler.recommended_value == "Balanced"
        assert upscaler.scope is SettingScope.RECOMMENDED

    def test_a_cpu_bound_machine_is_not_offered_a_gpu_side_trade(self) -> None:
        """The upscaler tier is bought with GPU time. On a machine whose CPU is
        the wall it buys nothing, so it stays where the user has to ask for it."""
        cpu_bound = self._registry(_headroom(TIER_SHORT, "cpu")).get("game_config:mw4:xess_quality")
        gpu_bound = self._registry(_headroom(TIER_SHORT, "gpu")).get("game_config:mw4:xess_quality")

        assert cpu_bound is not None and gpu_bound is not None
        assert cpu_bound.scope is SettingScope.COMPLETE
        assert gpu_bound.scope is SettingScope.RECOMMENDED

    def test_an_unmeasured_game_is_left_exactly_as_it_shipped(self) -> None:
        """Silence is not evidence: nothing about the static answer moves."""
        baseline = SettingsRegistry(discover_dynamic=False)
        registry = self._registry(None)

        for rules in GAME_RULES.values():
            for rule in rules:
                before = baseline.get(rule.setting_id)
                after = registry.get(rule.setting_id)
                assert before is not None and after is not None
                assert after.scope is before.scope
                assert after.recommended_value == before.recommended_value

    def test_one_game_s_measurement_never_moves_another_s(self) -> None:
        """Per game, because a machine holding 300 fps here holds 60 there."""
        registry = self._registry(_headroom(TIER_MET))

        mw3 = registry.get("game_config:mw3:dlss_perf_mode")
        baseline = SettingsRegistry(discover_dynamic=False).get("game_config:mw3:dlss_perf_mode")
        assert mw3 is not None and baseline is not None
        assert mw3.recommended_value == baseline.recommended_value
