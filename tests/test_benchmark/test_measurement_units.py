"""Two measurement bugs the PC-Check survey found, pinned so they cannot return.

Both are C11 failures of the quietest kind: a number that reaches the user
looking exactly like a measurement, because it *is* one — of the wrong thing,
or in the wrong unit.

*The unit bug.* `timing_bench.py` published `stats.timing_jitter_max_us` under
the claim metric `latency_spike_ms`. Percent comparisons survive a consistent
scale error, so `compare_runs` never noticed; the before/after numbers a user
reads were off by 1000x, and so was every verdict `judge` reached against a
claim like power.py's "20-100 [ms] eliminated" — 40 microseconds of timer jitter
scored as 40 milliseconds of spike.

*The unmapped metric.* `FrameTimeStats` has computed `fps_0_1_percent_low` since
PresentMon parsing was written, and `SOURCES` never listed it, so no claim could
ever be judged against 0.1% lows even though the instrument produced them. That
is C11 rule 5's silent third state: neither a source nor a named gap.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.benchmark.dpc import DpcBenchmark, DpcBenchmarkResult, DpcStats
from fpstune.benchmark.sources import NO_INSTRUMENT, NOT_JUDGEABLE, SOURCES, source_for
from fpstune.benchmark.timing_bench import TimingBench
from fpstune.benchmark.verify_round import direction_of


class _FixedDpc(DpcBenchmark):
    """A DPC benchmark that reports one known jitter maximum, in microseconds."""

    def __init__(self, jitter_max_us: float) -> None:
        super().__init__()
        self._jitter_max_us = jitter_max_us

    def run_benchmark(self, **_kwargs: object) -> DpcBenchmarkResult:
        return DpcBenchmarkResult(
            name="unit-test",
            timestamp="2026-09-11T10:00:00",
            stats=DpcStats(
                timing_jitter_avg_us=self._jitter_max_us / 4,
                timing_jitter_max_us=self._jitter_max_us,
                sleep_accuracy_avg_us=250.0,
                sleep_accuracy_max_us=900.0,
                timer_resolution_ms=0.5,
            ),
        )


class TestLatencySpikeIsPublishedInMilliseconds:
    """`latency_spike_ms` is a claim in milliseconds, so its samples are too."""

    def test_a_microsecond_jitter_maximum_becomes_milliseconds(self) -> None:
        """1500 us of timer jitter is 1.5 ms of spike, never 1500 ms.

        1500 ms would be a machine that stopped responding for a second and a
        half; the reading it came from is a routine scheduling wobble.
        """
        bench = TimingBench(benchmark=_FixedDpc(1500.0))

        reading = bench.run(2).readings["latency_spike_ms"]

        assert reading.samples == [1.5, 1.5]
        assert reading.median == 1.5

    def test_the_reading_declares_the_unit_its_name_promises(self) -> None:
        bench = TimingBench(benchmark=_FixedDpc(1500.0))

        assert bench.run(2).readings["latency_spike_ms"].unit == "ms"

    def test_the_microsecond_reading_beside_it_is_left_in_microseconds(self) -> None:
        """Only the metric whose *name* carries a unit is converted.

        `timing_jitter_avg_us` says microseconds and means them; rescaling it
        would trade one unit bug for another.
        """
        bench = TimingBench(benchmark=_FixedDpc(1600.0))

        readings = bench.run(2).readings
        assert readings["timing_jitter_avg_us"].samples == [400.0, 400.0]
        assert readings["timing_jitter_avg_us"].unit == "us"

    def test_the_sampled_route_converts_the_same_reading_the_same_way(self) -> None:
        """`/verify/sample` maps the instrument's own field to the claim metric.

        It read `timing_jitter_max_us` and published it under `latency_spike_ms`
        untouched, so the two paths into `judge` disagreed by 1000x about what
        the same machine had just done.
        """
        from fpstune.api.routes import benchmark as routes

        client = TestClient(create_app(), raise_server_exceptions=False)
        original = routes._sample_dpc
        routes._sample_dpc = lambda: {  # type: ignore[assignment]
            "timing_jitter_max_us": 1500.0,
            "timer_resolution_ms": 0.5,
        }
        try:
            payload = client.post("/api/benchmark/verify/sample", json={"instrument": "dpc"}).json()
        finally:
            routes._sample_dpc = original  # type: ignore[assignment]

        assert payload["metrics"] == {"latency_spike_ms": 1.5}

    def test_the_two_paths_agree_on_the_same_machine_reading(self) -> None:
        """The bench and the sample route are the two ways one claim gets judged."""
        from fpstune.api.routes.benchmark import scaled_metrics

        bench_samples = TimingBench(benchmark=_FixedDpc(880.0)).run(2)
        via_bench = bench_samples.readings["latency_spike_ms"].median
        via_source = scaled_metrics(
            source_for("latency_spike_ms"), {"timing_jitter_max_us": 880.0}
        )["latency_spike_ms"]

        assert via_bench == via_source


class TestZeroPointOnePercentLowsAreMappedToTheirInstrument:
    """PresentMon computes them; until now nothing could be judged against them."""

    def test_the_metric_has_a_source(self) -> None:
        source = source_for("fps_0_1_percent_low")

        assert source is not None
        assert source.name == "presentmon"

    def test_it_shares_the_instrument_that_measures_one_percent_lows(self) -> None:
        """Same capture, same parse, one worse percentile — same source or none."""
        one_percent = source_for("fps_1_percent_low")
        tenth_percent = source_for("fps_0_1_percent_low")

        assert one_percent is not None and tenth_percent is not None
        assert one_percent.name == tenth_percent.name

    def test_a_worse_percentile_is_still_better_when_it_is_higher(self) -> None:
        """Without a direction the mapping is a trap: measurable, never judgeable.

        `direction_of` answers "is lower better", so a frame rate answers False —
        and the same False the 1% low already answers, since a 0.1% low that
        moved up moved the same way for the same reason.
        """
        assert direction_of("fps_0_1_percent_low") is False
        assert direction_of("fps_0_1_percent_low") == direction_of("fps_1_percent_low")

    def test_it_is_no_longer_in_any_of_the_unmeasurable_lists(self) -> None:
        assert "fps_0_1_percent_low" not in NO_INSTRUMENT
        assert "fps_0_1_percent_low" not in NOT_JUDGEABLE

    def test_exactly_one_instrument_claims_it(self) -> None:
        owners = [s.name for s in SOURCES if "fps_0_1_percent_low" in s.fields]

        assert owners == ["presentmon"]
