"""Benchmark API routes."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fpstune.api.routes.benchmark_ledger import router as ledger_router
from fpstune.benchmark.sources import NO_INSTRUMENT, SOURCES, Source, coverage
from fpstune.benchmark.verify_round import measure_pair, run_round
from fpstune.settings.performance_headroom import (
    PerformanceHeadroom,
    measure_now,
    read_headroom,
)
from fpstune.utils.logger import log_activity

router = APIRouter()

# The ledger endpoints hang off this router rather than being mounted separately.
# This one is already registered at `/api/benchmark`, and the ledger asks the
# same family of question: what did this machine measure. Nesting the routers is
# what lets the ledger keep its own module — that file is about the ledger, this
# one about headroom and verification — without a second `include_router` in
# `main.py`.
router.include_router(ledger_router)

# Which instruments a caller may start on demand, and what running one costs.
#
# presentmon and furmark are deliberately absent. presentmon has nothing to read
# without a game already rendering, so a button that "runs" it returns an empty
# sample dressed as a measurement. furmark heats the card on purpose, which is
# not something to start because a panel offered a button. Both still appear in
# coverage with their `requires` line, so the user is told what to arrange
# rather than told nothing.
_RUNNABLE: dict[str, str] = {
    "dpc": "timer jitter, measured on the machine as it is",
    "network": "round-trip latency and loss against a known host",
}


class CoverageRequest(BaseModel):
    """Which settings the user is considering."""

    setting_ids: list[str] = Field(default_factory=list, max_length=2000)


class VerifyRequest(BaseModel):
    """One before/after pair, and the settings it is supposed to be about.

    The samples come from the caller rather than being collected here, because
    only the caller knows when the machine is in the state worth measuring — a
    frame-rate claim needs a match running, and no server-side timer can tell.
    Judging and reporting stay here, where the rules live.
    """

    setting_ids: list[str] = Field(default_factory=list, max_length=2000)
    before: dict[str, list[float]] = Field(default_factory=dict)
    after: dict[str, list[float]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list, max_length=50)


def _resolve(setting_ids: list[str]) -> list[Any]:
    """Look the ids up, and refuse rather than quietly measuring fewer settings.

    Silently skipping an unknown id would produce a round that reports on four
    settings while the user believes it reports on five — the same
    narrower-observation-than-action defect the apply path had to learn.
    """
    import fpstune.settings.registry_cache as registry_cache

    registry = registry_cache.get_registry()
    resolved = []
    missing = []
    for setting_id in setting_ids:
        setting = registry.get(setting_id)
        if setting is None:
            missing.append(setting_id)
        else:
            resolved.append(setting)

    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown settings: {missing}")
    return resolved


def _headroom_payload(headroom: PerformanceHeadroom) -> dict[str, Any]:
    """This machine's current reading, shaped for a panel.

    ``achievement_percent`` is computed here rather than in the browser so the
    number the UI shows and the number the recommendation engine acts on cannot
    drift apart — they come from the same property.
    """
    achievement = headroom.achievement
    return {
        "is_measured": headroom.is_measured,
        "measured_fps": headroom.measured_fps,
        "fps_1_percent_low": headroom.fps_1_percent_low,
        "target_fps": headroom.target_fps,
        "achievement_percent": round(achievement * 100) if achievement is not None else None,
        "tier": headroom.tier,
        "bottleneck": headroom.bottleneck,
        "present_mode": headroom.present_mode,
        "width": headroom.width,
        "height": headroom.height,
        "measured_at": headroom.measured_at,
    }


@router.get("/headroom")
async def get_headroom() -> dict[str, Any]:
    """What this machine last reached on the fixed scene, against what it can show.

    Always answerable, including before anything has ever been measured — an
    unmeasured machine reports itself as unmeasured rather than as a zero,
    because "we have not looked yet" is the answer the user needs in order to
    press the button.

    One reading, not one per game: the scene is the same every run, so the
    number describes the machine. No history either — it is overwritten in place.
    """
    headroom = await asyncio.to_thread(read_headroom)
    return {"headroom": _headroom_payload(headroom)}


@router.post("/headroom/measure")
async def measure_headroom() -> dict[str, Any]:
    """Run the scene now, on the user's say-so, and return what it found.

    Not an error when it cannot: "a game is running" and "the scene is not
    installed" are true statements about the machine, not faults, and the
    response says which of the reasons applied so the panel can tell the user
    what to do rather than that something broke.
    """
    # Said before the wait, not after it. The scene loads for about fifteen
    # seconds and then records for thirty, and a minute of silence is what made
    # the suite's runs look hung — the same report, on a slower path.
    log_activity(
        "Measuring what this machine reaches on the test scene — this takes about a minute",
        "info",
    )
    outcome = await asyncio.to_thread(measure_now)
    payload: dict[str, Any] = {
        "measured": outcome.measured,
        "outcome": outcome.outcome,
        "detail": outcome.detail,
        "headroom": (_headroom_payload(outcome.headroom) if outcome.headroom is not None else None),
    }
    # Both endings reach the log. A refusal that only reaches the panel leaves
    # the console showing a measurement that started and never said anything.
    log_activity(outcome.detail, "success" if outcome.measured else "warning")
    return payload


@router.post("/verify/coverage")
async def verify_coverage(request: CoverageRequest) -> dict[str, Any]:
    """What a verification round over these settings could and could not show.

    Answered before anything is measured, because the useful half of the answer
    is the half that says "start a match first" or "nothing here measures that".
    """
    return coverage(_resolve(request.setting_ids)).to_dict()


@router.post("/verify/round")
async def verify_round_endpoint(request: VerifyRequest) -> dict[str, Any]:
    """Judge these settings' own claims against a before/after pair.

    A metric present on only one side is dropped with a note rather than
    half-measured: a pair is the unit here, and one side of one is not evidence.

    The verdict is returned and not filed. Every round used to leave a JSON and
    an HTML file behind, and ninety of them had accumulated in the state
    directory describing machine states that no longer existed — a shelf of
    stale answers to a question that only ever has one current answer.
    """
    settings = _resolve(request.setting_ids)

    notes = list(request.notes)
    measurements = {}
    for metric, before in request.before.items():
        after = request.after.get(metric)
        if not before or not after:
            notes.append(f"{metric}: measured on only one side, so it was not judged")
            continue
        measurements[metric] = measure_pair(metric, before, after)

    for metric in request.after:
        if metric not in request.before:
            notes.append(f"{metric}: measured on only one side, so it was not judged")

    round_ = run_round(settings, measurements, notes=notes)

    log_activity(round_.summary, "info")

    return round_.to_dict()


@router.get("/verify/sources")
async def verify_sources() -> dict[str, Any]:
    """Which instrument can speak to which claim metric, and why not the rest.

    Exposed because the browser has to know which metric a sample belongs to,
    and the alternative is a second copy of the mapping in TypeScript that
    drifts from this one silently. The mapping stays owned here; this only
    reads it out. The `no_instrument` half ships with it deliberately — a
    coverage figure that lists only its successes is the thing sources.py was
    written to avoid.
    """
    return {
        "sources": [
            {
                "name": source.name,
                "requires": source.requires,
                "metrics": sorted(source.fields),
                "units": source.units,
                "runnable": source.name in _RUNNABLE,
            }
            for source in SOURCES
        ],
        "no_instrument": NO_INSTRUMENT,
    }


class SampleRequest(BaseModel):
    """One reading from one instrument, mapped to the metrics it can speak to."""

    instrument: Literal["dpc", "network"]
    target_name: str = ""
    """A name from the network benchmark's own target list, not a host.

    Free-form here would be a host string on its way to a ping subprocess. The
    caller picks a name, the server resolves it, and nothing a browser typed
    reaches a command line.
    """


def _sample_network(target_name: str) -> dict[str, Any]:
    from fpstune.benchmark.network import NetworkBenchmark

    bench = NetworkBenchmark()
    targets = bench.get_available_targets()
    name = target_name or next(iter(targets), "")
    if name not in targets:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown target {name!r}; known targets are {sorted(targets)}",
        )
    host, port = targets[name]
    result = bench.run_benchmark(name="verify_sample", target=host, tcp_target=(host, port))
    if result is None:
        raise HTTPException(status_code=503, detail=f"The network benchmark against {name} failed")
    return result.stats.to_dict()


def _sample_dpc() -> dict[str, Any]:
    from fpstune.benchmark.dpc import DpcBenchmark

    result = DpcBenchmark().run_benchmark(name="verify_sample")
    if result is None:
        raise HTTPException(
            status_code=503,
            detail="The DPC benchmark produced nothing; it runs on Windows only",
        )
    return result.stats.to_dict()


@router.post("/verify/sample")
async def verify_sample(request: SampleRequest) -> dict[str, Any]:
    """Run one instrument once and return its reading, keyed by claim metric.

    The mapping from an instrument's own field names to claim metrics happens
    here rather than in the caller, for the same reason /verify/sources exists:
    the two quantities are only the same thing where sources.py says they are,
    and a caller guessing at that is how a verdict comes to compare a timer's
    jitter with a round trip.

    A field the instrument did not produce is left out rather than sent as
    zero — a missing reading and a reading of nothing are different, and
    /verify/round is entitled to know which it got.
    """
    if request.instrument == "network":
        raw = await asyncio.to_thread(_sample_network, request.target_name)
    else:
        raw = await asyncio.to_thread(_sample_dpc)

    source = next(s for s in SOURCES if s.name == request.instrument)
    return {
        "instrument": source.name,
        "requires": source.requires,
        "metrics": scaled_metrics(source, raw),
    }


def scaled_metrics(source: Source | None, raw: dict[str, Any]) -> dict[str, float]:
    """One instrument's raw reading, keyed and scaled into claim metrics.

    Split out of the route because it is the *second* path a reading takes into
    `judge` — `timing_bench.py` is the first — and the two disagreeing is how
    `latency_spike_ms` came to mean microseconds on one and milliseconds on the
    other. A shared function is what makes "same machine, same number" testable
    rather than asserted.
    """
    if source is None:
        return {}
    return {
        metric: float(raw[field]) * source.scales.get(metric, 1.0)
        for metric, field in source.fields.items()
        if raw.get(field) is not None
    }
