"""One shape for every measurement fpstune takes.

The benchmarks in this package grew one at a time and each invented its own
result type: `NetworkBenchmarkResult`, `DpcBenchmarkResult`, `FurMarkResult`,
`BenchmarkResult`. They are not interchangeable, so nothing could ask "run
everything this machine can run and tell me what moved" — and a product whose
argument is *measure, do not assume* could not answer its own question.

This module is that shape. A `Bench` produces a `BenchResult`; a `BenchResult`
carries `BenchReading`s; a `SuiteRun` is a set of results taken under one label.
Two runs compare through `verify_round.measure_pair`, which is the same
comparison the claim verifier uses, so a bench and a claim are judged by one
standard rather than two.

Three rules the shape enforces rather than documents, all of them C11:

*A reading is samples, not a number.* `BenchReading.samples` is a list and
cannot be empty. Repeating a measurement is the only way to know what the
machine does on its own, and a difference smaller than that is not a difference
— `noise` comes free with every reading and `measure_pair` refuses to call
anything smaller than it a change.

*A bench that cannot run says so.* `is_available()` returns a reason alongside
its answer and `run_suite` turns both an unavailable bench and a crashing one
into `ran=False` with the reason attached. Nothing drops out of a suite
quietly; a run of eight benches always reports eight results.

*A metric measured on one side only is not compared.* `compare_runs` pairs what
it can and returns the rest as `unpaired`, with why. Silently dropping the
half that has no partner is how a comparison flatters itself.

Deliberately not built on `compare.py`. That one assumes a single reading per
metric and predates the noise floor; rewriting it would change what the existing
`/benchmark/compare` endpoint answers. It keeps its callers, this keeps the
suite.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from fpstune.benchmark.verify_round import Measurement, direction_of, measure_pair, noise_floor
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_REPEATS = 3
"""How many times a bench runs when the caller does not say.

Two is the floor at which `noise_floor` returns a real number rather than
infinity, so two is the floor at which any verdict is possible at all. Three
buys a median that one outlier cannot own, which is what `measure_pair`
compares.
"""

MINIMUM_REPEATS = 2
"""Below this, nothing can be concluded — a single reading has unknown noise."""


def _json_safe(value: float) -> float | None:
    """An unknown noise floor serialises as null, not as `Infinity`.

    `noise_floor` returns infinity for a single sample on purpose — nothing
    beats infinity, so nothing gets called a change. That value is correct in
    Python and is not JSON: `json.dumps(float("inf"))` writes the bare token
    `Infinity`, which every strict parser on the other end rejects. `null` says
    the same thing in a form the wire can carry.
    """
    return None if value == float("inf") else round(value, 6)


def _declared_direction(payload: dict[str, Any]) -> bool | None:
    """The `higher_is_better` override a rebuilt reading needs, or None.

    `to_dict` writes the *resolved* direction, which for a metric in the claim
    vocabulary is `verify_round`'s and not the bench's. Passing that back as an
    override would freeze a copy of it into the payload, so a later correction in
    `verify_round` would apply to fresh readings and not to reloaded ones. Only a
    direction `verify_round` does not know is carried across.
    """
    if direction_of(str(payload["metric"])) is not None:
        return None
    declared = payload.get("improves_upward")
    return None if declared is None else bool(declared)


@dataclass(frozen=True)
class BenchReading:
    """One metric, measured several times, from one bench.

    `metric` is a claim metric name wherever one fits — `latency_ms`,
    `fps_1_percent_low` — so a reading can be handed straight to
    `verify_round.judge` without a translation table in between. Benches also
    measure things no setting claims (`frame_time_p999`), and those name
    themselves.
    """

    metric: str
    samples: list[float]
    unit: str = ""
    higher_is_better: bool | None = None
    """Only when `verify_round` does not already know the metric's direction.

    Left as None for anything in the claim vocabulary, so the two cannot drift
    apart — a bench declaring the opposite direction to the claim verifier would
    report a regression as a win on one screen and a win as a regression on the
    other.
    """

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError(
                f"{self.metric}: a reading with no samples is not a reading — "
                "a bench that measured nothing returns ran=False with a reason"
            )
        if self.higher_is_better is None:
            return
        known = direction_of(self.metric)
        if known is not None and known is self.higher_is_better:
            raise ValueError(
                f"{self.metric}: this bench says higher_is_better="
                f"{self.higher_is_better}, verify_round says the opposite. "
                "Drop the override, or fix the direction in verify_round"
            )

    @property
    def improves_upward(self) -> bool | None:
        """True when a larger sample is a better one; None when nothing knows.

        None is a real answer: an unfamiliar metric gets no verdict rather than
        a guessed direction, which is how a regression gets reported as a win.
        """
        if self.higher_is_better is not None:
            return self.higher_is_better
        lower_is_better = direction_of(self.metric)
        return None if lower_is_better is None else not lower_is_better

    @property
    def median(self) -> float:
        """The value this reading stands for — median, so one outlier cannot own it."""
        return statistics.median(self.samples)

    @property
    def noise(self) -> float:
        """The spread of this reading's own samples.

        Infinite on a single sample, deliberately: nothing beats infinity, so
        nothing gets called a change on one reading.
        """
        return noise_floor(self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "samples": [round(sample, 6) for sample in self.samples],
            "median": round(self.median, 6),
            "noise": _json_safe(self.noise),
            "unit": self.unit,
            "improves_upward": self.improves_upward,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BenchReading:
        """Rebuild from `to_dict`, samples and all.

        `median` and `noise` are recomputed rather than read back: they are
        derived from the samples, and a payload where they disagree is one where
        somebody edited a number. Trusting the samples means the worst an edited
        payload can do is be wrong about its own inputs.
        """
        return cls(
            metric=str(payload["metric"]),
            samples=[float(sample) for sample in payload["samples"]],
            unit=str(payload.get("unit", "")),
            higher_is_better=_declared_direction(payload),
        )


@dataclass(frozen=True)
class BenchResult:
    """What one bench produced, including when it produced nothing."""

    bench: str
    """The bench's `key` — stable, used to pair a before with an after."""

    label: str
    """The bench's human name, so a UI does not have to own a lookup table."""

    ran: bool
    reason: str = ""
    """Why it did not run. Empty when it did, and required when it did not."""

    readings: dict[str, BenchReading] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    """Anything the bench wants on the record that is not a comparable metric —
    the host it pinged, the file size it wrote, the preset it rendered at."""

    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.ran and not self.reason:
            raise ValueError(
                f"{self.bench}: a bench that did not run has to say why — "
                "an empty reason is how a gap stops being visible"
            )
        if self.ran and not self.readings:
            raise ValueError(
                f"{self.bench}: ran=True with no readings. If it produced "
                "nothing, that is ran=False and a reason"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bench": self.bench,
            "label": self.label,
            "ran": self.ran,
            "reason": self.reason,
            "readings": {name: reading.to_dict() for name, reading in self.readings.items()},
            "detail": self.detail,
            "duration_seconds": round(self.duration_seconds, 3),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BenchResult:
        return cls(
            bench=str(payload["bench"]),
            label=str(payload.get("label", payload["bench"])),
            ran=bool(payload["ran"]),
            reason=str(payload.get("reason", "")),
            readings={
                name: BenchReading.from_dict(reading)
                for name, reading in (payload.get("readings") or {}).items()
            },
            detail=dict(payload.get("detail") or {}),
            duration_seconds=float(payload.get("duration_seconds", 0.0)),
        )


@runtime_checkable
class Bench(Protocol):
    """Anything the suite can run.

    Implemented by our own benches (frame pacing, disk, memory) and by adapters
    around the tools that were here first (PresentMon, network, DPC). The
    adapter is what keeps "the instrument is fixed, the load varies" true: a
    real game and a scene we draw ourselves arrive here in the same vocabulary.
    """

    key: str
    label: str
    requires: str
    """What has to be true for this to produce a reading, in a user's words.

    Shown before anything runs, so "a game running and rendering frames" is an
    instruction rather than an error message after a wasted minute.
    """

    def is_available(self) -> tuple[bool, str]:
        """Whether it can run here, and if not, why not in one sentence."""
        ...

    def run(self, repeats: int) -> BenchResult:
        """Measure `repeats` times and return every sample, not a summary."""
        ...


@dataclass
class SuiteRun:
    """Every bench that was asked to run, under one label."""

    label: str
    """What this run is: "before", "after", or whatever the caller called it."""

    started_at: float
    results: list[BenchResult] = field(default_factory=list)

    @property
    def ran(self) -> list[BenchResult]:
        return [result for result in self.results if result.ran]

    @property
    def skipped(self) -> list[BenchResult]:
        return [result for result in self.results if not result.ran]

    @property
    def summary(self) -> str:
        """Leads with the shortfall, because the shortfall is the honest part."""
        if not self.results:
            return "No benches were asked to run"
        if not self.ran:
            return f"None of the {len(self.results)} benches could run on this machine"
        if not self.skipped:
            return f"All {len(self.ran)} benches ran"
        return f"{len(self.ran)} of {len(self.results)} benches ran; {len(self.skipped)} could not"

    def reading(self, metric: str) -> BenchReading | None:
        """The first reading of this metric across every bench that ran.

        First rather than merged: two benches measuring the same metric are
        measuring it two different ways, and averaging those would invent a
        number neither of them took.
        """
        for result in self.ran:
            if metric in result.readings:
                return result.readings[metric]
        return None

    @property
    def metrics(self) -> list[str]:
        """Every metric this run has a reading for, in bench order."""
        seen: list[str] = []
        for result in self.ran:
            for metric in result.readings:
                if metric not in seen:
                    seen.append(metric)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "started_at": self.started_at,
            "summary": self.summary,
            "results": [result.to_dict() for result in self.results],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SuiteRun:
        """Rebuild a run the caller is handing back.

        Runs are not stored here. A comparison needs two of them and the "before"
        one was taken minutes ago, so the client keeps both and posts them back —
        which is the same decision `headroom.json` made about archives, for the
        same reason: a benchmark history nobody reads is a directory that grows.

        `label` and `results` are required rather than defaulted. With defaults,
        any dictionary at all rebuilt into an empty run, and a comparison of two
        of them returned a cheerful "neither run measured anything" — a caller
        posting the wrong shape got a plausible answer instead of an error, which
        is the silent failure this module is otherwise built to refuse.
        """
        return cls(
            label=str(payload["label"]),
            started_at=float(payload.get("started_at", 0.0)),
            results=[BenchResult.from_dict(result) for result in payload["results"]],
        )


def run_suite(
    benches: list[Bench],
    label: str,
    *,
    repeats: int = DEFAULT_REPEATS,
    started_at: float | None = None,
) -> SuiteRun:
    """Run every bench given and return one result per bench, always.

    A bench that cannot run, and a bench that raises while running, both come
    back as `ran=False` with the reason. Neither takes the suite down and
    neither disappears from it: a caller that asked for eight benches gets eight
    results, and the difference between "measured nothing" and "was never asked"
    stays visible.
    """
    if repeats < MINIMUM_REPEATS:
        raise ValueError(
            f"repeats={repeats} cannot produce a noise floor, so nothing measured "
            f"this way could ever be called a change (minimum {MINIMUM_REPEATS})"
        )

    run = SuiteRun(label=label, started_at=started_at if started_at is not None else time.time())

    for bench in benches:
        available, why = bench.is_available()
        if not available:
            run.results.append(
                BenchResult(bench=bench.key, label=bench.label, ran=False, reason=why)
            )
            continue

        started = time.perf_counter()
        try:
            run.results.append(bench.run(repeats))
        except Exception as exc:  # noqa: BLE001 — one bench must not end the suite
            logger.warning("Bench %s failed: %s", bench.key, exc)
            run.results.append(
                BenchResult(
                    bench=bench.key,
                    label=bench.label,
                    ran=False,
                    reason=f"the measurement failed partway through: {exc}",
                    duration_seconds=time.perf_counter() - started,
                )
            )

    return run


NO_BEFORE = "measured after the change but not before, so there is nothing to compare"
NO_AFTER = "measured before the change but not after, so there is nothing to compare"
NO_DIRECTION = "nothing here knows which direction is better for this metric"


@dataclass(frozen=True)
class SuiteComparison:
    """What two runs together are entitled to say."""

    before_label: str
    after_label: str
    measurements: list[Measurement] = field(default_factory=list)
    unpaired: list[tuple[str, str]] = field(default_factory=list)
    """Metric and why it could not be compared. Never silently dropped."""

    @property
    def moved(self) -> list[Measurement]:
        """The measurements that beat this machine's own variation."""
        return [m for m in self.measurements if m.exceeds_noise]

    @property
    def summary(self) -> str:
        if not self.measurements and not self.unpaired:
            return "Neither run measured anything"
        if not self.measurements:
            return f"None of the {len(self.unpaired)} metrics could be compared"
        moved = len(self.moved)
        total = len(self.measurements)
        tail = f"; {len(self.unpaired)} could not be compared" if self.unpaired else ""
        if not moved:
            return f"{total} metrics compared, none moved by more than noise{tail}"
        return f"{moved} of {total} metrics moved by more than noise{tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_label": self.before_label,
            "after_label": self.after_label,
            "summary": self.summary,
            "measurements": [
                {
                    "metric": m.metric,
                    "before": round(m.before, 6),
                    "after": round(m.after, 6),
                    "delta": round(m.delta, 6),
                    "percent_change": round(m.percent_change, 2),
                    "unit": m.unit,
                    "noise": _json_safe(m.noise),
                    "exceeds_noise": m.exceeds_noise,
                }
                for m in self.measurements
            ],
            "unpaired": [{"metric": metric, "reason": reason} for metric, reason in self.unpaired],
        }


def compare_runs(before: SuiteRun, after: SuiteRun) -> SuiteComparison:
    """Pair every metric both runs measured and say what moved.

    Built on `measure_pair`, so the noise floor is the wider of the two sides'
    spreads: a machine that was noisier after the change than before has to be
    beaten at its noisier level. A metric only one side measured is reported as
    unpaired rather than dropped — a comparison that only counts its successes
    is the arithmetic version of a marketing claim.
    """
    comparison_metrics = []
    unpaired: list[tuple[str, str]] = []

    for metric in before.metrics:
        if after.reading(metric) is None:
            unpaired.append((metric, NO_AFTER))
        else:
            comparison_metrics.append(metric)

    for metric in after.metrics:
        if before.reading(metric) is None:
            unpaired.append((metric, NO_BEFORE))

    measurements = []
    for metric in comparison_metrics:
        before_reading = before.reading(metric)
        after_reading = after.reading(metric)
        assert before_reading is not None and after_reading is not None  # both checked above

        if before_reading.improves_upward is None:
            unpaired.append((metric, NO_DIRECTION))
            continue

        measurements.append(
            measure_pair(
                metric,
                before_reading.samples,
                after_reading.samples,
                before_reading.unit or after_reading.unit,
            )
        )

    return SuiteComparison(
        before_label=before.label,
        after_label=after.label,
        measurements=measurements,
        unpaired=unpaired,
    )
