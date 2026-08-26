"""The suite's job is to make a dishonest measurement hard to express.

Most of these tests are about refusals rather than results: a reading with no
samples, a bench that vanished instead of explaining itself, a comparison that
counted only the metrics it happened to have both halves of. Each of those is a
way a measurement flatters itself, and each has a counterpart in this file.
"""

from __future__ import annotations

import json

import pytest

from fpstune.benchmark.suite import (
    MINIMUM_REPEATS,
    NO_AFTER,
    NO_BEFORE,
    NO_DIRECTION,
    Bench,
    BenchReading,
    BenchResult,
    SuiteRun,
    compare_runs,
    run_suite,
)


class FakeBench:
    """A bench under our control, so the suite is what is being tested."""

    def __init__(
        self,
        key: str = "fake",
        *,
        available: bool = True,
        why: str = "",
        readings: dict[str, list[float]] | None = None,
        unit: str = "ms",
        explodes: bool = False,
    ) -> None:
        self.key = key
        self.label = f"Fake {key}"
        self.requires = "nothing at all"
        self._available = available
        self._why = why
        self._readings = readings if readings is not None else {"latency_ms": [10.0, 11.0, 10.5]}
        self._unit = unit
        self._explodes = explodes
        self.repeats_seen: int | None = None

    def is_available(self) -> tuple[bool, str]:
        return self._available, self._why

    def run(self, repeats: int) -> BenchResult:
        self.repeats_seen = repeats
        if self._explodes:
            raise RuntimeError("the disk went away")
        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                metric: BenchReading(metric=metric, samples=samples, unit=self._unit)
                for metric, samples in self._readings.items()
            },
            detail={"note": "synthetic"},
        )


class TestAReadingIsSamples:
    def test_a_reading_with_no_samples_is_refused(self) -> None:
        """The alternative is a bench that "measured" something and reports a
        median of nothing, which reads as a result all the way to the screen."""
        with pytest.raises(ValueError, match="no samples"):
            BenchReading(metric="latency_ms", samples=[])

    def test_one_sample_has_unknown_noise_so_nothing_can_beat_it(self) -> None:
        reading = BenchReading(metric="latency_ms", samples=[12.0])
        assert reading.noise == float("inf")

    def test_the_median_is_what_the_reading_stands_for(self) -> None:
        """Mean would let one stalled run own the number it is supposed to summarise."""
        reading = BenchReading(metric="latency_ms", samples=[10.0, 11.0, 90.0])
        assert reading.median == 11.0

    def test_direction_comes_from_the_claim_verifier_by_default(self) -> None:
        """Two sources for "which way is better" is how a win becomes a regression."""
        assert BenchReading(metric="latency_ms", samples=[1.0, 2.0]).improves_upward is False
        assert BenchReading(metric="fps", samples=[1.0, 2.0]).improves_upward is True

    def test_a_metric_nobody_knows_gets_no_direction_rather_than_a_guess(self) -> None:
        reading = BenchReading(metric="frame_time_p999", samples=[1.0, 2.0])
        assert reading.improves_upward is None

    def test_a_bench_may_declare_a_direction_the_verifier_does_not_know(self) -> None:
        reading = BenchReading(metric="frame_time_p999", samples=[1.0, 2.0], higher_is_better=False)
        assert reading.improves_upward is False

    def test_a_bench_may_not_contradict_the_claim_verifier(self) -> None:
        """`fps` is higher-is-better there; a bench saying otherwise would make
        the same measurement a win on one screen and a loss on the next."""
        with pytest.raises(ValueError, match="verify_round says the opposite"):
            BenchReading(metric="fps", samples=[1.0, 2.0], higher_is_better=False)


class TestABenchThatCannotRunSaysSo:
    def test_not_running_without_a_reason_is_refused(self) -> None:
        with pytest.raises(ValueError, match="has to say why"):
            BenchResult(bench="fake", label="Fake", ran=False)

    def test_running_with_nothing_to_show_is_refused(self) -> None:
        """`ran=True` and no readings is the shape of a silent failure: it
        counts toward "all benches ran" and contributes nothing."""
        with pytest.raises(ValueError, match="ran=True with no readings"):
            BenchResult(bench="fake", label="Fake", ran=True)

    def test_an_unavailable_bench_still_appears_in_the_run(self) -> None:
        """Asked for two, told about two. A bench that drops out of the list
        reads as one that was never requested."""
        run = run_suite(
            [
                FakeBench("ok"),
                FakeBench("nope", available=False, why="no game is running"),
            ],
            "before",
        )

        assert len(run.results) == 2
        assert [r.bench for r in run.skipped] == ["nope"]
        assert run.skipped[0].reason == "no game is running"

    def test_a_bench_that_raises_does_not_take_the_suite_with_it(self) -> None:
        """Measured behaviour of the old benches: one PowerShell timeout ended
        the whole run and the results that had already been taken went with it."""
        run = run_suite([FakeBench("boom", explodes=True), FakeBench("fine")], "before")

        assert [r.bench for r in run.ran] == ["fine"]
        assert "the disk went away" in run.skipped[0].reason

    def test_the_summary_leads_with_what_did_not_run(self) -> None:
        run = run_suite(
            [FakeBench("ok"), FakeBench("nope", available=False, why="no adapter")],
            "before",
        )
        assert run.summary == "1 of 2 benches ran; 1 could not"

    def test_too_few_repeats_is_refused_before_anything_runs(self) -> None:
        """One reading has infinite noise, so a suite run at repeats=1 spends
        the machine's time to produce something no verdict can be drawn from."""
        bench = FakeBench()
        with pytest.raises(ValueError, match="noise floor"):
            run_suite([bench], "before", repeats=MINIMUM_REPEATS - 1)
        assert bench.repeats_seen is None

    def test_the_protocol_is_satisfied_by_the_shape_alone(self) -> None:
        """Benches are adapters around tools that were here first, so requiring
        them to inherit anything would mean rewriting each one to join."""
        assert isinstance(FakeBench(), Bench)


class TestComparingTwoRuns:
    def _run(self, label: str, readings: dict[str, list[float]]) -> SuiteRun:
        return run_suite([FakeBench("fake", readings=readings)], label)

    def test_a_metric_both_runs_measured_is_compared(self) -> None:
        before = self._run("before", {"latency_ms": [20.0, 21.0, 20.5]})
        after = self._run("after", {"latency_ms": [10.0, 11.0, 10.5]})

        comparison = compare_runs(before, after)

        assert [m.metric for m in comparison.measurements] == ["latency_ms"]
        assert comparison.measurements[0].delta == pytest.approx(-10.0)
        assert comparison.moved == comparison.measurements

    def test_a_change_inside_the_noise_floor_is_not_called_a_change(self) -> None:
        """The single most flattering mistake available: an idle machine varies,
        and reporting that variation as an improvement is free and wrong."""
        before = self._run("before", {"latency_ms": [10.0, 14.0, 12.0]})
        after = self._run("after", {"latency_ms": [11.0, 13.0, 11.5]})

        comparison = compare_runs(before, after)

        assert comparison.measurements[0].exceeds_noise is False
        assert comparison.moved == []
        assert "none moved by more than noise" in comparison.summary

    def test_a_metric_only_the_before_run_has_is_reported_not_dropped(self) -> None:
        before = self._run("before", {"latency_ms": [1.0, 2.0], "jitter_ms": [1.0, 2.0]})
        after = self._run("after", {"latency_ms": [1.0, 2.0]})

        comparison = compare_runs(before, after)

        assert comparison.unpaired == [("jitter_ms", NO_AFTER)]

    def test_a_metric_only_the_after_run_has_is_reported_not_dropped(self) -> None:
        before = self._run("before", {"latency_ms": [1.0, 2.0]})
        after = self._run("after", {"latency_ms": [1.0, 2.0], "jitter_ms": [1.0, 2.0]})

        comparison = compare_runs(before, after)

        assert comparison.unpaired == [("jitter_ms", NO_BEFORE)]

    def test_a_metric_with_no_known_direction_is_not_scored(self) -> None:
        """It was measured on both sides and still cannot be a verdict, because
        nothing here knows whether up is better. That is a third answer, and it
        has to survive as one."""
        before = self._run("before", {"frame_time_p999": [1.0, 2.0]})
        after = self._run("after", {"frame_time_p999": [3.0, 4.0]})

        comparison = compare_runs(before, after)

        assert comparison.measurements == []
        assert comparison.unpaired == [("frame_time_p999", NO_DIRECTION)]

    def test_the_summary_counts_what_could_not_be_compared(self) -> None:
        before = self._run("before", {"latency_ms": [20.0, 21.0], "jitter_ms": [1.0, 2.0]})
        after = self._run("after", {"latency_ms": [10.0, 11.0]})

        assert compare_runs(before, after).summary == (
            "1 of 1 metrics moved by more than noise; 1 could not be compared"
        )

    def test_two_empty_runs_say_so_rather_than_reporting_success(self) -> None:
        empty_before = SuiteRun(label="before", started_at=0.0)
        empty_after = SuiteRun(label="after", started_at=1.0)

        assert compare_runs(empty_before, empty_after).summary == "Neither run measured anything"


class TestSerialisation:
    def test_a_run_round_trips_into_something_an_api_can_send(self) -> None:
        payload = run_suite([FakeBench("fake")], "before").to_dict()

        assert payload["label"] == "before"
        reading = payload["results"][0]["readings"]["latency_ms"]
        assert reading["samples"] == [10.0, 11.0, 10.5]
        assert reading["median"] == 10.5
        assert reading["improves_upward"] is False

    def test_an_unknown_noise_floor_goes_out_as_null_not_as_infinity(self) -> None:
        """`json.dumps(float("inf"))` writes the bare token `Infinity`, which is
        not JSON and which every strict parser on the other end rejects. A
        single-sample reading is legal, so this would have been a live endpoint
        failure the first time one reached the UI."""
        payload = BenchReading(metric="latency_ms", samples=[1.0]).to_dict()

        assert payload["noise"] is None
        assert "Infinity" not in json.dumps(payload)

    def test_a_run_survives_being_written_out_and_read_back(self) -> None:
        """The client holds a "before" run for minutes while the user applies
        settings, so a run that cannot round-trip is a run that cannot be
        compared. Nothing is stored server-side — this is the whole contract."""
        original = run_suite([FakeBench("fake")], "before", repeats=2)

        restored = SuiteRun.from_dict(json.loads(json.dumps(original.to_dict())))

        assert restored.label == original.label
        assert restored.metrics == original.metrics
        assert restored.reading("latency_ms").samples == original.reading("latency_ms").samples

    def test_a_restored_run_compares_against_a_fresh_one(self) -> None:
        original = run_suite([FakeBench("fake")], "before", repeats=2)
        restored = SuiteRun.from_dict(json.loads(json.dumps(original.to_dict())))

        comparison = compare_runs(restored, original)

        assert comparison.measurements[0].delta == 0
        assert comparison.unpaired == []

    def test_a_direction_the_verifier_knows_is_not_frozen_into_the_payload(self) -> None:
        """`to_dict` writes the resolved direction, which for a claim metric is
        `verify_round`'s. Reading it back as an override would pin a copy of it,
        so a later correction there would apply to fresh readings and not to
        reloaded ones."""
        restored = BenchReading.from_dict(
            BenchReading(metric="latency_ms", samples=[1.0, 2.0]).to_dict()
        )

        assert restored.higher_is_better is None
        assert restored.improves_upward is False

    def test_a_direction_only_the_bench_knows_does_survive(self) -> None:
        restored = BenchReading.from_dict(
            BenchReading(
                metric="frame_time_p999_ms", samples=[1.0, 2.0], higher_is_better=False
            ).to_dict()
        )

        assert restored.improves_upward is False

    def test_a_payload_that_is_not_a_run_is_refused(self) -> None:
        """With defaults it rebuilt into an empty run, and two of those compared
        to a cheerful "neither run measured anything" — a wrong shape answered
        plausibly instead of rejected."""
        with pytest.raises(KeyError):
            SuiteRun.from_dict({"nope": 1})

    def test_a_comparison_carries_the_same_null(self) -> None:
        before = run_suite([FakeBench("fake", readings={"latency_ms": [10.0, 11.0]})], "before")
        after = run_suite([FakeBench("fake", readings={"latency_ms": [10.0, 11.0]})], "after")

        payload = compare_runs(before, after).to_dict()

        assert "Infinity" not in json.dumps(payload)
