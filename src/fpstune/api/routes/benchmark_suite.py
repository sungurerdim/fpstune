"""The measurement suite, over HTTP.

Three endpoints, and the shape of them follows from what the suite refuses to
do rather than from what it measures.

`GET /suite` answers before anything runs: which benches exist, which can run
here, what each costs, and for the ones that cannot, why. A user should read
"start a game first" on a page rather than after waiting through a run that
produced nothing.

`POST /suite/run` streams, because a full pass takes tens of seconds and a
progress bar that only moves at the end is a spinner. Same SSE shape as
`settings_stream.py`: one event per bench as it finishes, then `done`.

`POST /suite/compare` takes two runs the caller is holding and returns a
per-metric verdict from `measure_pair`. **Nothing is stored here.** A comparison
needs a "before" taken minutes ago, and the obvious design keeps it server-side
— which is how the old verify round ended up with ninety JSON and HTML files in
the state directory describing machines that no longer existed. The client keeps
its two runs; this endpoint judges them and forgets them.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fpstune.benchmark.benches import benches_for, catalogue, default_keys
from fpstune.benchmark.suite import (
    DEFAULT_REPEATS,
    MINIMUM_REPEATS,
    BenchResult,
    SuiteRun,
    compare_runs,
)
from fpstune.settings.impact_categories import derive_impact_categories
from fpstune.utils.logger import get_logger, log_activity

logger = get_logger()

router = APIRouter()

MAX_REPEATS = 10
"""Above this the run outlasts anyone's patience without sharpening anything.

The noise floor is a spread rather than a mean, so more repeats widen it as
often as they tighten it — past a handful the returns are not just diminishing,
they can reverse.
"""


class SuiteRunRequest(BaseModel):
    """Which benches to run, under what name, how many times each."""

    benches: list[str] | None = Field(default=None, max_length=32)
    """`null` means the default set — which is not every bench. See `benches.py`."""

    label: str = Field(default="before", min_length=1, max_length=64)
    repeats: int = Field(default=DEFAULT_REPEATS, ge=MINIMUM_REPEATS, le=MAX_REPEATS)


class SuiteCompareRequest(BaseModel):
    """Two runs the caller took, in the shape `SuiteRun.to_dict()` emits."""

    before: dict[str, Any]
    after: dict[str, Any]


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("/suite")
async def suite_catalogue() -> dict[str, Any]:
    """Every bench, whether it can run here, and what running it costs."""
    listing = await asyncio.to_thread(catalogue)
    return {
        "benches": listing,
        "default_keys": default_keys(),
        "min_repeats": MINIMUM_REPEATS,
        "default_repeats": DEFAULT_REPEATS,
        "max_repeats": MAX_REPEATS,
    }


async def _stream_suite(keys: list[str] | None, label: str, repeats: int) -> AsyncIterator[str]:
    """One event per bench as it lands, then a `done` carrying the whole run.

    Each bench runs in `asyncio.to_thread` — they are all blocking, several of
    them for seconds at a time, and holding the event loop through one would
    stall every other request the app is serving. Same rule the bulk apply
    stream follows.

    Every step writes an activity line as well as an SSE event. Reported by the
    user: a suite run printed nothing at all until it finished, so a run that had
    started, a run that had failed to start and a run that was simply slow were
    indistinguishable — and several of these benches take tens of seconds. The
    SSE stream reaches the panel that opened it and nothing else; `log_activity`
    reaches both the terminal and the in-app log, which is where somebody looks
    when the screen appears to be doing nothing.
    """
    try:
        benches = benches_for(keys)
    except KeyError as exc:
        # `str(KeyError(...))` wraps its own message in quotes, which reaches a
        # UI as `"no bench named ['disc_io']"` complete with the quotes.
        log_activity(f"Benchmark suite '{label}' could not start: {exc.args[0]}", "error")
        yield _sse({"event": "failed", "reason": str(exc.args[0])})
        return

    run = SuiteRun(label=label, started_at=time.time())
    log_activity(
        f"Benchmark suite '{label}' started: {len(benches)} instruments, {repeats} repeats each",
        "info",
    )
    yield _sse(
        {
            "event": "started",
            "label": label,
            "repeats": repeats,
            "benches": [bench.key for bench in benches],
        }
    )

    for index, bench in enumerate(benches):
        position = f"{index + 1}/{len(benches)}"
        log_activity(f"Measuring {bench.label} ({position})", "info")
        yield _sse({"event": "running", "bench": bench.key, "label": bench.label})

        available, why = await asyncio.to_thread(bench.is_available)
        if not available:
            result = BenchResult(bench=bench.key, label=bench.label, ran=False, reason=why)
        else:
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(bench.run, repeats)
            except Exception as exc:  # noqa: BLE001 — one bench must not end the run
                logger.warning("Bench %s failed: %s", bench.key, exc)
                result = BenchResult(
                    bench=bench.key,
                    label=bench.label,
                    ran=False,
                    reason=f"the measurement failed partway through: {exc}",
                    duration_seconds=time.perf_counter() - started,
                )

        # A bench that could not run says so at the moment it drops out, not
        # only in the summary at the end (C11 rule 3).
        if result.ran:
            log_activity(f"{bench.label} done in {result.duration_seconds:.1f}s", "success")
        else:
            log_activity(f"{bench.label} did not run: {result.reason}", "warning")

        run.results.append(result)
        yield _sse(
            {
                "event": "measured" if result.ran else "skipped",
                "bench": bench.key,
                "progress": round((index + 1) / len(benches) * 100),
                "result": result.to_dict(),
            }
        )

    log_activity(f"Benchmark suite '{label}': {run.summary}", "info")
    yield _sse({"event": "done", "run": run.to_dict()})


@router.post("/suite/run")
async def run_suite_stream(request: SuiteRunRequest) -> StreamingResponse:
    """Run the suite, streaming one event per bench.

    The whole run comes back on the `done` event rather than being assembled
    client-side from the per-bench ones — a stream that drops a message would
    otherwise produce a run quietly missing a bench, which is the failure this
    suite is built to make impossible.
    """
    return StreamingResponse(
        _stream_suite(request.benches, request.label, request.repeats),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/suite/compare")
async def compare_suite_runs(request: SuiteCompareRequest) -> dict[str, Any]:
    """Judge two runs against each other, metric by metric.

    A metric only one side measured comes back under `unpaired` with the reason,
    never dropped. A difference smaller than the machine's own variation comes
    back with `exceeds_noise` false, never as an improvement.
    """
    try:
        before = SuiteRun.from_dict(request.before)
        after = SuiteRun.from_dict(request.after)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"that is not a pair of suite runs: {exc}"
        ) from exc

    payload = compare_runs(before, after).to_dict()

    # Which kind of gain each measurement is, decided by the same map the
    # settings use. Grouped here rather than in the browser: `impact_categories`
    # is where a metric's category is decided, and a copy of that map in
    # TypeScript is a second answer waiting to disagree with the first.
    for measurement in payload["measurements"]:
        measurement["category"] = _category_of(measurement["metric"])

    return payload


def _category_of(metric: str) -> str | None:
    """The impact category a metric belongs to, or None.

    None for the metrics the benches invented for themselves —
    `pacing_p999_ms`, `bufferbloat_ms` — which no setting claims and which the
    settings' category map has therefore never had a reason to know. Reported
    as null and rendered on its own rather than filed under a category it does
    not belong to.
    """
    categories = derive_impact_categories({metric: 0})
    return categories[0] if categories else None
