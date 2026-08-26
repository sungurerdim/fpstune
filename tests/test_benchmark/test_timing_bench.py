"""The timing adapter must stay an adapter.

`dpc.py` already measures timer resolution, sleep accuracy and jitter, and it
measures them correctly. The only thing added here is repetition and the suite's
shape, so the tests that matter are the ones that catch this drifting into a
second implementation: every value has to come out of `DpcBenchmark`, and
`latency_spike_ms` has to stay the name `sources.py` already maps.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpstune.benchmark.sources import source_for
from fpstune.benchmark.suite import Bench, run_suite
from fpstune.benchmark.timing_bench import TimingBench


@dataclass
class _Stats:
    timer_resolution_ns: float = 500_000.0
    timer_resolution_ms: float = 0.5
    sample_count: int = 100
    sleep_accuracy_avg_us: float = 500.0
    sleep_accuracy_max_us: float = 900.0
    sleep_accuracy_stdev_us: float = 40.0
    timing_jitter_avg_us: float = 0.05
    timing_jitter_max_us: float = 0.3
    qpc_resolution_ns: float = 100.0


@dataclass
class _Result:
    stats: _Stats


class _FakeDpc:
    """Stands in for the real one so the tests do not sleep for a second each."""

    def __init__(self, results: list[_Result | None] | None = None) -> None:
        self.results = results
        self.calls = 0

    def run_benchmark(self, **_kwargs: object) -> _Result | None:
        index = self.calls
        self.calls += 1
        if self.results is None:
            return _Result(_Stats())
        return self.results[index]


class TestItStaysAnAdapter:
    def test_every_reading_comes_from_the_underlying_benchmark(self) -> None:
        """Not recomputed here. Two places measuring "timing jitter" would
        eventually disagree about what it is."""
        fake = _FakeDpc()
        readings = TimingBench(benchmark=fake).run(2).readings  # type: ignore[arg-type]

        assert readings["latency_spike_ms"].samples == [0.3, 0.3]
        assert readings["timing_jitter_avg_us"].samples == [0.05, 0.05]
        assert readings["sleep_accuracy_avg_us"].samples == [500.0, 500.0]
        assert readings["timer_resolution_ms"].samples == [0.5, 0.5]

    def test_it_calls_the_benchmark_once_per_repeat(self) -> None:
        fake = _FakeDpc()
        TimingBench(benchmark=fake).run(3)  # type: ignore[arg-type]

        assert fake.calls == 3

    def test_it_names_the_metric_sources_already_maps(self) -> None:
        """`sources.py` routes the claim `latency_spike_ms` to the dpc source.
        Renaming it here would quietly unmeasure every setting claiming one."""
        assert source_for("latency_spike_ms") is not None

        readings = TimingBench(benchmark=_FakeDpc()).run(2).readings  # type: ignore[arg-type]
        assert "latency_spike_ms" in readings

    def test_it_names_where_the_numbers_came_from(self) -> None:
        detail = TimingBench(benchmark=_FakeDpc()).run(2).detail  # type: ignore[arg-type]

        assert detail["source"] == "fpstune.benchmark.dpc.DpcBenchmark"


class TestWhenTheMeasurementFails:
    def test_a_failed_repeat_makes_the_whole_bench_decline(self) -> None:
        """Not a partial result. A run that produced nothing has nothing to be
        averaged with the runs that did, and averaging around the hole would
        report a noise floor computed from fewer samples than it claims."""
        fake = _FakeDpc([_Result(_Stats()), None, _Result(_Stats())])

        result = TimingBench(benchmark=fake).run(3)  # type: ignore[arg-type]

        assert result.ran is False
        assert "returned nothing" in result.reason
        assert result.readings == {}

    def test_the_suite_reports_the_decline_rather_than_dropping_it(self) -> None:
        fake = _FakeDpc([None])
        run = run_suite([TimingBench(benchmark=fake)], "before", repeats=2)  # type: ignore[arg-type]

        assert len(run.results) == 1
        assert run.skipped[0].bench == "timing"


class TestTheShape:
    def test_it_runs_anywhere(self) -> None:
        assert TimingBench(benchmark=_FakeDpc()).is_available() == (True, "")  # type: ignore[arg-type]

    def test_it_satisfies_the_suite_protocol(self) -> None:
        assert isinstance(TimingBench(benchmark=_FakeDpc()), Bench)  # type: ignore[arg-type]

    def test_lower_is_better_for_every_metric_it_reports(self) -> None:
        """Jitter, sleep error and timer period are all costs. One of them
        pointing the other way would report a coarser timer as an improvement."""
        readings = TimingBench(benchmark=_FakeDpc()).run(2).readings  # type: ignore[arg-type]

        for reading in readings.values():
            assert reading.improves_upward is False


class TestAgainstTheRealThing:
    def test_it_produces_readings_on_this_machine(self) -> None:
        """The adapter is only worth anything if the real benchmark still has
        the field names it reads — a rename in `dpc.py` would surface here."""
        result = TimingBench(sleep_samples=10, jitter_samples=10).run(2)

        assert result.ran, result.reason
        assert result.readings["timer_resolution_ms"].median > 0
