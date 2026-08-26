"""The evidence engine's job is knowing what it is not entitled to say.

Every setting carries an `impact_scores` claim, and none of those numbers came
from the user's machine. This module compares them to it. Almost every test here
is about a way that comparison could flatter the tool, because producing a
bigger number is easy and the only thing that makes the result worth anything is
that it could have come out badly.

Four ways it could lie, one class each:

* crediting one setting with what forty did together
* calling noise an improvement
* reporting "we could not check" as "no effect"
* getting the direction backwards, so a regression reads as a win
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpstune.benchmark.verify_round import (
    Claim,
    Measurement,
    Status,
    claims_of,
    direction_of,
    judge,
    measure_pair,
    noise_floor,
    parse_claim,
    run_round,
)


def _setting(setting_id: str = "test:one", **impact: object) -> SimpleNamespace:
    return SimpleNamespace(id=setting_id, impact_scores=dict(impact))


def _claim(metric: str = "latency_ms", raw: object = -15.0) -> Claim:
    return parse_claim("test:one", metric, raw)


class TestReadingWhatASettingClaims:
    """The shapes the shipped registry actually uses."""

    @pytest.mark.parametrize(
        ("raw", "low", "high", "percent"),
        [
            ("+3-5%", 3.0, 5.0, True),
            ("-15%", 15.0, 15.0, True),
            ("50-150MB", 50.0, 150.0, False),
            ("4-16GB", 4.0, 16.0, False),
            ("-0.1-0.5ms", 0.1, 0.5, False),
            (-15.0, 15.0, 15.0, False),
            (-0.5, 0.5, 0.5, False),
            ("0%", 0.0, 0.0, True),
        ],
    )
    def test_it_reads_the_registry_shapes(
        self, raw: object, low: float, high: float, percent: bool
    ) -> None:
        claim = parse_claim("s:x", "fps", raw)
        assert (claim.low, claim.high, claim.is_percentage) == (low, high, percent)

    def test_a_range_keeps_its_bounds_in_order(self) -> None:
        assert parse_claim("s:x", "fps", "5-3%").low == 3.0

    def test_a_claim_with_no_number_is_not_quantified(self) -> None:
        """`{"stability": "high"}` is a real statement and not a measurable one."""
        assert parse_claim("s:x", "ux", "improved").is_quantified is False

    def test_stability_is_never_collected_as_a_claim(self) -> None:
        """C2 refuses to count it as a performance metric, so nor does this."""
        claims = claims_of(_setting(stability="high", fps="+3%"))
        assert [c.metric for c in claims] == ["fps"]


class TestKnowingWhichWayIsBetter:
    def test_latency_improves_downward(self) -> None:
        assert direction_of("latency_ms") is True

    def test_frame_rate_improves_upward(self) -> None:
        assert direction_of("fps") is False

    def test_an_unfamiliar_metric_has_no_direction(self) -> None:
        """None is an answer. Guessing is how a regression reads as a win."""
        assert direction_of("something_nobody_defined") is None

    @pytest.mark.parametrize(
        "ceiling", ["fps_cap_removed", "fps_menu_ceiling", "fps_unfocused_ceiling"]
    )
    def test_a_ceiling_is_not_treated_as_a_gain(self, ceiling: str) -> None:
        """These carry a limit — "30", "90" — not an improvement.

        Reading them as gains would report the largest wins in the registry for
        settings whose entire purpose is to cap something.
        """
        assert direction_of(ceiling) is None

    @pytest.mark.parametrize("metric", ["gpu_temp_c", "power_watts"])
    def test_the_heat_a_cap_avoids_is_measurable_even_when_the_cap_is_not(
        self, metric: str
    ) -> None:
        """Unscorable number, measurable effect — and the two got conflated once.

        An idle frame cap has no verifiable *number*, so the round says nothing
        about its ceiling. It does not follow that the setting does nothing: the
        heat it avoids is a real quantity moving in a known direction, and a
        thermal round can check it.
        """
        assert direction_of(metric) is True

    @pytest.mark.parametrize("qualitative", ["privacy", "security", "ux", "visual_quality"])
    def test_claims_a_stopwatch_cannot_see_stay_unverifiable(self, qualitative: str) -> None:
        assert direction_of(qualitative) is None


class TestNoise:
    def test_the_floor_is_what_the_metric_did_on_its_own(self) -> None:
        assert noise_floor([10.0, 10.4, 10.2]) == pytest.approx(0.4)

    def test_a_single_reading_has_unknown_noise(self) -> None:
        """And unknown noise must beat everything, or one reading proves anything."""
        assert noise_floor([10.0]) == float("inf")
        assert noise_floor([]) == float("inf")

    def test_a_change_inside_the_noise_is_not_a_result(self) -> None:
        measurement = Measurement("latency_ms", before=10.0, after=9.8, noise=0.5)
        assert measurement.exceeds_noise is False

    def test_a_change_beyond_the_noise_is(self) -> None:
        measurement = Measurement("latency_ms", before=10.0, after=8.0, noise=0.5)
        assert measurement.exceeds_noise is True

    def test_the_noisier_side_sets_the_bar(
        self,
    ) -> None:
        """If the machine got noisier after the change, that is the noise to beat."""
        pair = measure_pair("fps", [100.0, 100.1], [120.0, 128.0])
        assert pair.noise == pytest.approx(8.0)

    def test_measuring_needs_both_sides(self) -> None:
        with pytest.raises(ValueError, match="both sides"):
            measure_pair("fps", [], [120.0])


class TestOneSettingAtATime:
    """A shared measurement cannot be credited to a single setting."""

    def test_a_batch_change_is_not_evidence_about_any_one_setting(self) -> None:
        measurement = Measurement("latency_ms", before=10.0, after=5.0, noise=0.2)
        verdict = judge(_claim(), measurement, settings_changed=40)

        assert verdict.status is Status.NOT_ATTRIBUTABLE
        assert "40 settings" in verdict.reason
        assert verdict.is_evidence is False

    def test_the_measurement_is_still_reported(self) -> None:
        """Not attributable is not the same as not measured."""
        measurement = Measurement("latency_ms", before=10.0, after=5.0, noise=0.2)
        verdict = judge(_claim(), measurement, settings_changed=40)
        assert verdict.measurement is measurement

    def test_a_single_change_can_be_credited(self) -> None:
        measurement = Measurement("latency_ms", before=10.0, after=5.0, noise=0.2)
        assert judge(_claim(), measurement, settings_changed=1).status is Status.VERIFIED

    def test_a_round_over_many_settings_says_so_in_its_summary(self) -> None:
        settings = [_setting(f"test:{i}", latency_ms=-5.0) for i in range(40)]
        round_ = run_round(
            settings, {"latency_ms": Measurement("latency_ms", 10.0, 5.0, noise=0.1)}
        )

        assert round_.verified == []
        assert "none of the 40 claims can be credited individually" in round_.summary


class TestTheFourVerdicts:
    def test_moving_the_claimed_way_beyond_noise_is_verified(self) -> None:
        verdict = judge(
            _claim("latency_ms", -15.0), Measurement("latency_ms", 20.0, 10.0, noise=1.0)
        )
        assert verdict.status is Status.VERIFIED
        assert verdict.is_evidence

    def test_moving_the_other_way_beyond_noise_is_contradicted(self) -> None:
        """The result that makes the whole exercise worth doing."""
        verdict = judge(
            _claim("latency_ms", -15.0), Measurement("latency_ms", 10.0, 20.0, noise=1.0)
        )
        assert verdict.status is Status.CONTRADICTED
        assert verdict.is_evidence
        assert "wrong way" in verdict.reason

    def test_a_higher_is_better_metric_is_judged_the_other_way_round(self) -> None:
        assert judge(_claim("fps", "+5%"), Measurement("fps", 100.0, 110.0, noise=1.0)).status is (
            Status.VERIFIED
        )
        assert judge(_claim("fps", "+5%"), Measurement("fps", 110.0, 100.0, noise=1.0)).status is (
            Status.CONTRADICTED
        )

    def test_a_change_within_noise_is_inconclusive(self) -> None:
        verdict = judge(_claim(), Measurement("latency_ms", 10.0, 9.9, noise=0.5))
        assert verdict.status is Status.INCONCLUSIVE
        assert "within" in verdict.reason
        assert verdict.is_evidence is False

    def test_nothing_measured_is_unmeasured_not_ineffective(self) -> None:
        """The distinction the report has to keep: "we did not check" is not
        "it did nothing"."""
        verdict = judge(_claim(), None)
        assert verdict.status is Status.UNMEASURED
        assert verdict.is_evidence is False

    def test_an_unquantified_claim_cannot_be_checked(self) -> None:
        assert judge(_claim("ux", "improved"), None).status is Status.UNMEASURED

    def test_a_metric_with_no_known_direction_is_not_guessed_at(self) -> None:
        verdict = judge(
            _claim("mystery_metric", 5.0), Measurement("mystery_metric", 10.0, 1.0, noise=0.1)
        )
        assert verdict.status is Status.UNMEASURED
        assert "which direction" in verdict.reason


class TestTheSummaryDoesNotFlatter:
    def test_verifying_nothing_says_so_plainly(self) -> None:
        settings = [_setting("test:one", latency_ms=-15.0)]
        round_ = run_round(
            settings, {"latency_ms": Measurement("latency_ms", 10.0, 9.99, noise=1.0)}
        )

        assert "None of the" in round_.summary
        assert round_.verified == []

    def test_a_contradiction_is_never_left_out(self) -> None:
        settings = [_setting("test:one", latency_ms=-15.0)]
        round_ = run_round(
            settings, {"latency_ms": Measurement("latency_ms", 10.0, 30.0, noise=1.0)}
        )

        assert "contradicted" in round_.summary

    def test_an_empty_round_claims_nothing(self) -> None:
        assert run_round([], {}).summary == "Nothing was checked"

    def test_unchecked_claims_stay_in_the_report(self) -> None:
        """Dropping them would make a round of one verified claim out of sixty
        read as a clean sweep."""
        settings = [_setting("test:one", latency_ms=-15.0, fps="+3-5%", privacy="improved")]
        round_ = run_round(
            settings, {"latency_ms": Measurement("latency_ms", 20.0, 10.0, noise=1.0)}
        )

        assert len(round_.verdicts) == 3
        assert len(round_.verified) == 1
        assert len(round_.unverified) == 2
        assert round_.to_dict()["unverified"] == 2


class TestAgainstTheRealRegistry:
    def test_every_shipped_claim_parses_without_raising(self) -> None:
        from fpstune.settings.registry import SettingsRegistry

        for setting in SettingsRegistry(discover_dynamic=False).get_all():
            claims_of(setting)

    def test_most_shipped_claims_are_quantified(self) -> None:
        """C2 requires a numeric metric, so a low number here means C2 has slipped."""
        from fpstune.settings.registry import SettingsRegistry

        claims = [
            c for s in SettingsRegistry(discover_dynamic=False).get_all() for c in claims_of(s)
        ]
        quantified = [c for c in claims if c.is_quantified]

        assert len(quantified) > len(claims) * 0.75, (
            f"only {len(quantified)} of {len(claims)} shipped claims state a number"
        )
