"""What this machine measured, per area, and what it could not.

`/suite/compare` answers "here are two runs, judge them" and keeps nothing. That
is the right shape for a button a human presses twice in one sitting, and the
wrong one for the question a user actually has — *did any of that help?* — which
they should be able to ask without having known to take a "before" first. The
scheduler takes both halves unasked; this reads them back.

**One area, one instrument, and never a total.** This endpoint is precisely the
shape that invites a headline, and a headline is what fpstune has shipped wrong
three times: `"GAINED -683ms LATENCY"` summed four unrelated clocks,
`"Gained +28-45% FPS"` summed claims nobody measured. So each area names exactly
one instrument and reports only what that instrument produced. There is no field
here that adds two areas together, and a test asserts there is not.

**An area with no pair carries a reason, never a number.** Not zero, not "no
change" — a sentence saying why it could not be checked, in the same voice
`sources.py` and `benches.catalogue()` already use. Two of the seven areas say
that permanently on this build, and they are the honest half of the screen: fps
and input latency need a game rendering, which is `headroom_watch`'s department,
and thermal has no instrument on the performance path at all because FurMark is
a power virus (C11 rule 6).

Its models live here rather than in `api/schemas.py`, following
`benchmark_suite.py`: these shapes have exactly one caller and putting them in
the shared module would make them look like part of the settings contract.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter

from fpstune.benchmark import ledger, scheduler
from fpstune.benchmark.suite import SuiteRun, compare_runs
from fpstune.benchmark.verify_round import direction_of
from fpstune.utils.logger import get_logger

logger = get_logger()

router = APIRouter()


@dataclass(frozen=True)
class Area:
    """One kind of gain, and the single instrument entitled to speak to it."""

    key: str
    label: str
    instrument: str
    """The bench key whose reading this area is. One, never a blend."""

    metric: str | None
    """The reading within that bench. None when this build has no instrument."""

    absent_reason: str
    """Why there is no number, when there is none. Written for a user to read."""


AREAS: tuple[Area, ...] = (
    Area(
        key="fps",
        label="Frame rate",
        instrument="presentmon",
        metric="fps",
        absent_reason=(
            "A frame rate needs a game rendering to measure. fpstune captures one "
            "automatically while you play — see Frame-rate headroom."
        ),
    ),
    Area(
        key="input_latency",
        label="Input latency",
        instrument="presentmon",
        metric="input_latency_ms",
        absent_reason=(
            "Click-to-photon latency is only reported by a capture that tracked it, "
            "which needs a game running and a driver that supplies the timings."
        ),
    ),
    Area(
        key="timing",
        label="Timer and scheduling",
        instrument="timing",
        metric="latency_spike_ms",
        absent_reason="The timer benchmark has not run on both sides of a change yet.",
    ),
    Area(
        key="disk",
        label="Disk",
        instrument="disk_io",
        metric="storage_performance",
        absent_reason="The disk benchmark has not run on both sides of a change yet.",
    ),
    Area(
        key="network",
        label="Network",
        instrument="network",
        metric="latency_ms",
        absent_reason="The network benchmark has not run on both sides of a change yet.",
    ),
    Area(
        key="cpu",
        label="Processor",
        instrument="cpu",
        # The all-thread figure, because it is the one that notices a core that
        # has stopped participating — a parked core reads as 0% busy and as
        # nothing missing, and the single-thread number would not move at all.
        metric="cpu_multi_core_ops",
        absent_reason="The processor benchmark has not run on both sides of a change yet.",
    ),
    Area(
        key="memory",
        label="Memory",
        instrument="memory",
        metric="memory_bandwidth",
        absent_reason="The memory benchmark has not run on both sides of a change yet.",
    ),
    Area(
        key="thermal",
        label="Heat and wear",
        instrument="sensors",
        metric="gpu_temp_c",
        absent_reason=(
            "GPU temperature comes from the NVIDIA driver's own tool here, so a "
            "machine with an AMD or Intel card has no GPU reading yet — its system "
            "temperature is measured all the same. FurMark stays off this path: it "
            "heats the card under a load nobody plays at."
        ),
    ),
    Area(
        key="stability",
        label="Crashes and faults",
        instrument="event_scan",
        metric="crash_rate",
        absent_reason=(
            "Stability is counted from what Windows recorded, over a trailing week "
            "on each side of a change. Nothing has been counted twice yet."
        ),
    ),
    Area(
        key="storage_health",
        label="Drive life",
        instrument="storage_health",
        metric="ssd_longevity",
        absent_reason=(
            "A drive reports the endurance it has spent only to an administrator, "
            "so this needs fpstune started as one."
        ),
    ),
    Area(
        key="boot",
        label="Starting and shutting down",
        instrument="boot_time",
        metric="boot_time_s",
        absent_reason=(
            "Boot times come from the log Windows writes at every start, which it "
            "opens only for an administrator."
        ),
    ),
)

IMPROVED = "improved"
UNCHANGED = "unchanged"
WORSE = "worse"
UNMEASURED = "unmeasured"
"""The four things an area can be, and why "unchanged" is not the default.

A delta is not a verdict: -3 ms on a metric where lower is better and -3 ms on
one where higher is better read identically and mean opposite things. The
direction is not decided here — it comes from `verify_round.direction_of`, the
same vocabulary the claim verifier uses, so a fall in timer jitter cannot be a
gain on one screen and a regression on the other.

`unchanged` and `unmeasured` are kept apart for the same reason. "It did not
move" is a finding, produced by two runs whose difference did not beat this
machine's own noise (C11 rule 2). "We never looked" is not a finding at all, and
a panel that renders them alike has stated something it did not measure.
"""


def _improves_upward(metric: str | None) -> bool | None:
    """True when a bigger number is a better one, None when nothing knows.

    `direction_of` answers "is lower better", so this is its inverse — and None
    stays None: an unfamiliar metric gets no verdict rather than a guessed
    direction, which is how a regression gets reported as a win.
    """
    if metric is None:
        return None
    lower_is_better = direction_of(metric)
    return None if lower_is_better is None else not lower_is_better


def _verdict(delta: float, exceeds_noise: bool, improves_upward: bool | None) -> str:
    """Which of the four an area's measured pair earned."""
    if improves_upward is None:
        return UNMEASURED
    if not exceeds_noise or delta == 0:
        return UNCHANGED
    return IMPROVED if (delta > 0) is improves_upward else WORSE


def _sample_count(run: SuiteRun | None, metric: str | None) -> int:
    """How many samples that side of the pair is standing on.

    On the response because a reader is entitled to know what a verdict cost. A
    difference drawn from two samples has an enormous noise floor and almost
    never beats it; one drawn from ten is worth more, and the count is the only
    thing on the response that says which of the two this was.
    """
    if run is None or metric is None:
        return 0
    reading = run.reading(metric)
    return 0 if reading is None else len(reading.samples)


NO_PAIR = "Nothing has been measured twice yet, so there is no before and after to compare."
"""Said once per area rather than once for the screen.

A single banner saying "no data" reads as a broken panel; seven rows each saying
what they are waiting for reads as a plan.
"""


def _run_summary(run: SuiteRun | None) -> dict[str, Any] | None:
    """One run, described in its own words.

    `summary` is `SuiteRun`'s own — it leads with the shortfall, which is the
    honest part — rather than re-derived here. A second opinion about the same
    run is a second opinion that will eventually disagree.
    """
    if run is None:
        return None
    return {
        "label": run.label,
        "started_at": run.started_at,
        "summary": run.summary,
        "bench_count": len(run.results),
        "ran_count": len(run.ran),
        "metrics": run.metrics,
    }


def _job_summary(job: ledger.Job | None) -> dict[str, Any] | None:
    """The open job, or None when nothing is in flight."""
    if job is None:
        return None
    return {
        "id": job.id,
        "trigger": job.trigger,
        "label": job.label,
        "status": job.status,
        "plan": list(job.plan),
        "step_index": job.step_index,
        "current_bench": job.current_bench,
        "remaining": job.remaining,
        "attempts": dict(job.attempts),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _unmeasured(
    area: Area,
    reason: str,
    *,
    samples_before: int = 0,
    samples_after: int = 0,
) -> dict[str, Any]:
    """An area with nothing to report, and why — never a zero standing in."""
    return {
        "area": area.key,
        "label": area.label,
        "instrument": area.instrument,
        "metric": area.metric,
        "measured": False,
        "reason": reason,
        "before": None,
        "after": None,
        "delta": None,
        "percent_change": None,
        "unit": "",
        "noise": None,
        "exceeds_noise": False,
        "verdict": UNMEASURED,
        "improves_upward": _improves_upward(area.metric),
        # Not always zero: one side may have measured while the other did not,
        # and that is the difference between "waiting for the second half" and
        # "this instrument has never produced a reading here".
        "samples_before": samples_before,
        "samples_after": samples_after,
    }


def area_verdicts(pair: tuple[SuiteRun, SuiteRun] | None) -> list[dict[str, Any]]:
    """One verdict per area, measured or explained.

    Every area appears on every response. An area filtered out because it had
    nothing to say looks like an area that does not exist, and the point of this
    screen is to be honest about what is not known as well as what is.
    """
    if pair is None:
        # An area with no instrument keeps its own reason even here. Telling a
        # user "measure twice and this will appear" about thermal would be a
        # promise this build cannot keep — the pair is not what it is missing.
        return [
            _unmeasured(area, area.absent_reason if area.metric is None else NO_PAIR)
            for area in AREAS
        ]

    before, after = pair
    comparison = compare_runs(before, after)
    measured = {m.metric: m for m in comparison.measurements}
    unpaired = dict(comparison.unpaired)

    verdicts: list[dict[str, Any]] = []
    for area in AREAS:
        counts = {
            "samples_before": _sample_count(before, area.metric),
            "samples_after": _sample_count(after, area.metric),
        }
        if area.metric is None:
            verdicts.append(_unmeasured(area, area.absent_reason, **counts))
            continue

        found = measured.get(area.metric)
        if found is None:
            # `compare_runs` already worked out why — measured on one side only,
            # or no known direction. Its wording is reused rather than replaced,
            # so the ledger screen and the compare screen give the same account
            # of the same gap.
            verdicts.append(
                _unmeasured(area, unpaired.get(area.metric) or area.absent_reason, **counts)
            )
            continue

        improves_upward = _improves_upward(area.metric)
        verdicts.append(
            {
                "area": area.key,
                "label": area.label,
                "instrument": area.instrument,
                "metric": area.metric,
                "measured": True,
                "reason": "",
                "before": round(found.before, 6),
                "after": round(found.after, 6),
                "delta": round(found.delta, 6),
                "percent_change": round(found.percent_change, 2),
                "unit": found.unit,
                # An unknown noise floor is null on the wire, never `Infinity`:
                # a strict JSON parser rejects the bare token.
                "noise": None if found.noise == float("inf") else round(found.noise, 6),
                "exceeds_noise": found.exceeds_noise,
                "verdict": _verdict(found.delta, found.exceeds_noise, improves_upward),
                "improves_upward": improves_upward,
                **counts,
            }
        )
    return verdicts


def _ledger_payload() -> dict[str, Any]:
    """Everything the ledger screen shows, read off disk in one pass."""
    pair = ledger.pair()
    return {
        "job": _job_summary(ledger.current_job()),
        "baseline": _run_summary(ledger.baseline()),
        "after": _run_summary(ledger.latest_after()),
        "areas": area_verdicts(pair),
        "bulk_apply_pending": ledger.bulk_apply_pending(),
        "poll_interval_seconds": scheduler.POLL_INTERVAL_SECONDS,
    }


def _runs_payload() -> dict[str, Any]:
    """Both halves whole, in exactly the shape `SuiteRun.from_dict` reads back.

    Separate from `/ledger` on purpose. That one is for a panel: a summary line
    and one verdict per area, small enough to poll. This is for a caller that
    has to judge — `VerifyPanel` runs the same comparison over the samples, and
    samples are the one thing a summary cannot carry. Two shapes because there
    are two questions, not because one of them was left incomplete.
    """
    baseline = ledger.baseline()
    after = ledger.latest_after()
    return {
        "baseline": None if baseline is None else baseline.to_dict(),
        "after": None if after is None else after.to_dict(),
    }


@router.get("/ledger/runs")
async def get_ledger_runs() -> dict[str, Any]:
    """The persisted baseline and after runs, samples and all.

    Null rather than 404 for a half that was never taken: a machine that has not
    measured yet is the ordinary first state, and an error would render as a
    broken panel rather than as "not yet".
    """
    return await asyncio.to_thread(_runs_payload)


@router.get("/ledger")
async def get_ledger() -> dict[str, Any]:
    """What has been measured on this machine, per area, and what has not.

    Never an error for having measured nothing: "we have not looked yet" is the
    answer that makes the button worth pressing, and a 404 would render as a
    broken panel.
    """
    return await asyncio.to_thread(_ledger_payload)


def _enqueue() -> dict[str, Any]:
    """Open a manual job, unless one is already open.

    Enqueued rather than run. The suite takes minutes, the guards that decide
    *when* it may run live in the scheduler, and a request that measured inline
    would both hold a connection open and bypass every one of them.
    """
    existing = ledger.current_job()
    if existing is not None:
        # Two open jobs would write two runs under one label and race each
        # other for it. The honest answer is "one is already running".
        return {"queued": False, "job": _job_summary(existing)}

    job = ledger.open_job(ledger.MANUAL, scheduler.plan_keys())
    logger.info("Queued a manual benchmark job %s (%s)", job.id, job.label)
    return {"queued": True, "job": _job_summary(job)}


@router.post("/ledger/run")
async def run_ledger_job() -> dict[str, Any]:
    """Ask for a measurement now — the same pipeline the scheduler uses.

    Same job, same plan, same guards. A manual path that ran the benches
    directly would be a second measurement pipeline, and two pipelines is how
    the numbers on two screens come to disagree.
    """
    return await asyncio.to_thread(_enqueue)
