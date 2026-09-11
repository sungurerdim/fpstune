"""The timer benchmark, wearing the suite's shape.

`dpc.py` has measured timer resolution, sleep accuracy and timing jitter since
long before the suite existed, and it measures them well. What it could not do
was take part in a before/after run: it returns its own result type, one reading
per call, with no notion of repeats or of a noise floor. So the numbers it
produced were shown and never compared.

This is an adapter, not a second implementation. Every value still comes out of
`DpcBenchmark.run_benchmark`; what is added is calling it `repeats` times and
handing the samples over in the shape `measure_pair` consumes. Rewriting the
measurement would have meant two places that disagree about what timing jitter
is, which is the failure this whole suite exists to avoid.

`latency_spike_ms` keeps the name `sources.py` already maps it to, so a setting
claiming a latency spike is judged against the same field it was always judged
against. It does **not** keep the underlying field's unit: `DpcStats` reports
jitter in microseconds and the claim is in milliseconds, so the samples are
divided here. Shipped the other way for one release — `BenchReading(...,
jitter_max, "us")` under a metric named `_ms` — and a consistent scale error is
invisible to a percent comparison, so `compare_runs` never flagged it while
every absolute number a user read was 1000x too large. The rest are new names
because nothing claimed them before, and they carry their own unit in the name.
"""

from __future__ import annotations

import time

from fpstune.benchmark.dpc import DpcBenchmark
from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for

_MEASUREMENT_FAILED = "the timer benchmark returned nothing on this machine"

_SLOW_SAMPLE_SECONDS = 0.02
"""One sample's sleep plus the worst scheduling delay a loaded machine adds.

Generous by design: scheduling delay is the quantity this bench measures, so a
deadline tight enough to trip on a bad answer would delete the reading that
answer was about.
"""


US_PER_MS = 1000.0
"""What separates `DpcStats`'s microseconds from the `latency_spike_ms` claim.

Named rather than inlined because `sources.py` applies the same conversion on
the other path into `judge` (`/verify/sample`), and the two agreeing is the
whole point — a scale that lives in one path only is the bug wearing a fix.
"""


class TimingBench:
    """Timer resolution, sleep accuracy and timing jitter, made comparable."""

    key = "timing"
    label = "Timer and scheduling accuracy"
    requires = "nothing — it measures the machine as it is"

    def __init__(
        self,
        *,
        sleep_samples: int = 100,
        jitter_samples: int = 100,
        benchmark: DpcBenchmark | None = None,
    ) -> None:
        self.sleep_samples = sleep_samples
        self.jitter_samples = jitter_samples
        self._benchmark = benchmark or DpcBenchmark()

    def timeout_seconds(self, repeats: int) -> float:
        """Derived from the samples it takes, each one a short sleep.

        `_SLOW_SAMPLE_SECONDS` is the sleep plus the worst scheduling delay a
        loaded machine adds to it — which is the very thing this bench measures,
        so it has to allow for a bad answer without calling it a hang.
        """
        per_repeat = (self.sleep_samples + self.jitter_samples) * _SLOW_SAMPLE_SECONDS
        return deadline_for(per_repeat, repeats)

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        jitter_avg: list[float] = []
        jitter_max: list[float] = []
        sleep_avg: list[float] = []
        sleep_max: list[float] = []
        resolution: list[float] = []

        for _ in range(repeats):
            result = self._benchmark.run_benchmark(
                name="suite",
                sleep_samples=self.sleep_samples,
                jitter_samples=self.jitter_samples,
            )
            if result is None:
                # Not a partial result: a run that produced nothing has nothing
                # to average with the runs that did.
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=_MEASUREMENT_FAILED,
                    duration_seconds=time.perf_counter() - started,
                )

            stats = result.stats
            jitter_avg.append(stats.timing_jitter_avg_us)
            # `sources.py` already maps the claim `latency_spike_ms` onto this
            # field, so it keeps that name rather than gaining a second spelling
            # nothing else knows — converted into the unit that name promises.
            jitter_max.append(stats.timing_jitter_max_us / US_PER_MS)
            sleep_avg.append(stats.sleep_accuracy_avg_us)
            sleep_max.append(stats.sleep_accuracy_max_us)
            resolution.append(stats.timer_resolution_ms)

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                "latency_spike_ms": BenchReading("latency_spike_ms", jitter_max, "ms"),
                "timing_jitter_avg_us": BenchReading(
                    "timing_jitter_avg_us", jitter_avg, "us", higher_is_better=False
                ),
                "sleep_accuracy_avg_us": BenchReading(
                    "sleep_accuracy_avg_us", sleep_avg, "us", higher_is_better=False
                ),
                "sleep_accuracy_max_us": BenchReading(
                    "sleep_accuracy_max_us", sleep_max, "us", higher_is_better=False
                ),
                # The one metric here a tweak sets directly rather than
                # influences: a machine at 15.6 ms and one at 0.5 ms are the two
                # ends of what the timer-resolution setting does.
                "timer_resolution_ms": BenchReading(
                    "timer_resolution_ms", resolution, "ms", higher_is_better=False
                ),
            },
            detail={
                "sleep_samples": self.sleep_samples,
                "jitter_samples": self.jitter_samples,
                "source": "fpstune.benchmark.dpc.DpcBenchmark",
            },
            duration_seconds=time.perf_counter() - started,
        )
