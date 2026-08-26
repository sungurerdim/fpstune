"""Whether this machine can hold a cadence, measured without a game.

Most of what fpstune changes lives on this side of the frame: timer resolution,
scheduler quantum, core parking, the power plan's idle behaviour, MMCSS, GPU
scheduling. None of them make a GPU faster. What they decide is whether the work
for frame N is finished when frame N is due, or a little late, or occasionally
very late — and "occasionally very late" is what a player feels as a stutter
while the average frame rate says nothing happened.

Nothing here could measure that without a game: PresentMon is the only frame
instrument in the build and it needs something rendering. This one needs
nothing. It is a frame loop with no renderer: fixed cadence, fixed work per
frame, and a record of when each frame actually landed.

**It answers in its own vocabulary, and that is a decision rather than an
oversight.** `frame_time_ms` and `stutter_count` are PresentMon's, because they
describe a real game; this describes a synthetic loop, and letting one name
cover both would let a claim about a game's frame time be "verified" by
something that never drew a frame. So it maps to no `impact_scores` claim at
all — which is itself a finding, and B4's problem: the claims are written in
terms of frame rates, and pacing is not one.

**What one frame does**, and why each part is there:

*A dependent load chain over a buffer bigger than cache.* `buf[i] = next i` over
a random permutation, so every step waits for the previous one to return from
memory. The CPU cannot prefetch a chain it cannot predict, which is what makes
this cost real time rather than retiring in the background — and real time is
what a scheduler decision moves.

*A round trip through another thread.* The frame's work is handed to a worker
and handed back. Two context switches per frame, which is where quantum,
priority and core parking show up: a parked core takes microseconds to come
back, and it comes back once per frame.

*A wait until the deadline*, through `kernel32.Sleep` for the whole
milliseconds and a spin for the remainder — which is what a game engine does,
and the reason for it is measured rather than assumed. The first version of
this bench used `time.sleep`, and a timer-resolution change moved nothing:
CPython 3.11 and later wait on a high-resolution waitable timer, so the
process-wide timer period the tweak changes does not reach it. A bench that
cannot see the setting class it exists for is worse than no bench, because it
reports "no change" with the same face it would report a real one. `Sleep` is
affected by the timer period, so this measures what a game would feel.

**What it does not claim.** This is not a frame rate. It says nothing about what
a GPU will do, and a machine that scores well here can still be GPU-bound in
every game it runs. What it measures is the machine's ability to be on time,
which is the half of a stutter that a driver setting cannot fix.

A machine that cannot reach the target at all still produces a usable
comparison: the target is the same on both sides, so a change that moves
`missed_frame_percent` from 40% to 12% is as real as one that moves it from 4%
to 0%. `detail` carries the target so a reader is never guessing what the
percentage is a percentage of.

**Measured on the machine that wrote this**, 2026-08-24, five passes of one
second at 120 Hz:

    idle              pacing_interval_ms 8.333, noise 0.000 | p99 8.36 +/- 0.026
                      jitter 0.002 ms | missed 0.0%
    16 busy processes pacing_interval_ms 8.333, noise 20.1  | p99 22.9 +/- 50.9
                      jitter 3.78 ms  | missed 35.8%

Two things that reads as. Idle, the noise floor is small enough to resolve a
change of a few hundredths of a millisecond, which is the state a before/after
comparison is actually run in. Under a chaotic load the machine's own variation
is larger than the effect, and `measure_pair` refuses to call any of it a change
— correctly, and it is worth knowing the refusal is not a bug.

**Not verified, and it is the obvious one:** that a timer-resolution change
moves these numbers. This machine reports `NtQueryTimerResolution` at 0.5 ms
already — the finest it offers — so there is nothing to raise and the tweak is a
no-op here. `timeBeginPeriod(1)` moved nothing, which is the right answer for
this machine and no evidence at all about a machine sitting at 15.6 ms. Filed in
tasks.md rather than claimed.
"""

from __future__ import annotations

import queue
import random
import statistics
import sys
import threading
import time
from array import array
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult


def _load_kernel32() -> Any | None:
    """The Windows sleep, or None where there is not one.

    Resolved once at import: this is called once per frame, and looking it up
    inside the loop would put a DLL lookup inside the thing being timed.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


_kernel32 = _load_kernel32()

DEFAULT_TARGET_FPS = 120
"""Fast enough that a 15.6 ms timer tick cannot be hidden inside one frame.

At 60 Hz a frame is 16.7 ms and the default Windows tick fits inside it, so a
timer-resolution change barely shows. At 120 Hz the budget is 8.3 ms and the
same tick is larger than the whole frame, which is the point being measured.
"""

DEFAULT_SECONDS = 2.0
"""Long enough for a 0.1% figure to mean something: 120 Hz x 2 s is 240 frames,
so `pacing_p999_ms` is the worst of them rather than a coin flip."""

DEFAULT_WORKING_SET_MB = 8
"""Comfortably past any current L3, so the chase actually reaches memory."""

DEFAULT_CHASE_STEPS = 4000
"""About a millisecond of dependent loads — a real cost inside an 8.3 ms budget,
and small enough that the loop is measuring pacing rather than saturation."""

_CHASE_SEED = 0x5EED
"""Fixed, because the permutation has to be the same one before and after.

A fresh shuffle per run would change the miss pattern between the two halves of
a comparison, and the difference would be the seed rather than the machine.
"""

# A job is one frame's half of the chase — the buffer, where to start, how many
# steps — and `None` is the stop token. The worker ends by running out of work
# rather than by recognising a sentinel object, which is one fewer thing to get
# wrong when the loop is also the thing being timed.


_SPIN_MARGIN_MS = 1.0
"""How much of the wait is spun rather than slept.

`Sleep` takes whole milliseconds and may return late by whatever the timer
period is, so the last millisecond is burned in a loop. One millisecond of spin
per frame is what an engine budgets for the same reason: it is the difference
between hitting a deadline and hitting the one after it.
"""


def _wait_until(deadline: float) -> None:
    """Hold until `deadline`, the way a frame loop does.

    Whole milliseconds through the OS — `kernel32.Sleep` on Windows, which the
    timer period affects and which is therefore what this bench is here to
    measure — and the last millisecond spun, because no sleep primitive is
    accurate enough to land on a 8.3 ms boundary.
    """
    remaining_ms = (deadline - time.perf_counter()) * 1000.0
    if remaining_ms > _SPIN_MARGIN_MS:
        sleep_ms = int(remaining_ms - _SPIN_MARGIN_MS)
        if sleep_ms > 0:
            if _kernel32 is not None:
                _kernel32.Sleep(sleep_ms)
            else:
                time.sleep(sleep_ms / 1000.0)

    while time.perf_counter() < deadline:
        pass


def _build_chase(working_set_mb: int) -> array[int]:
    """A random permutation, as a chain each step of which has to be waited for.

    `buf[i]` gives the next index, so the address of load N+1 is not known until
    load N returns. That is what defeats the prefetcher; a linear walk of the
    same size would be almost free.
    """
    count = max(1024, (working_set_mb * 1024 * 1024) // 8)
    order = list(range(count))
    random.Random(_CHASE_SEED).shuffle(order)

    chase = array("q", [0]) * count
    for position, index in enumerate(order):
        chase[index] = order[(position + 1) % count]
    return chase


def _chase(buf: array[int], start: int, steps: int) -> int:
    index = start
    for _ in range(steps):
        index = buf[index]
    return index


def _worker(
    inbox: queue.SimpleQueue[tuple[array[int], int, int] | None],
    outbox: queue.SimpleQueue[int],
) -> None:
    """Half of every frame's work, so every frame crosses a thread boundary."""
    while True:
        job = inbox.get()
        if job is None:
            return
        buf, start, steps = job
        outbox.put(_chase(buf, start, steps))


class FramePacingBench:
    """A frame loop with no renderer, measured against its own deadline."""

    key = "frame_pacing"
    label = "Frame pacing"
    requires = "nothing — it runs its own frame loop on the CPU"

    def __init__(
        self,
        *,
        target_fps: int = DEFAULT_TARGET_FPS,
        seconds: float = DEFAULT_SECONDS,
        working_set_mb: int = DEFAULT_WORKING_SET_MB,
        chase_steps: int = DEFAULT_CHASE_STEPS,
    ) -> None:
        if target_fps <= 0:
            raise ValueError("target_fps has to be positive to have a deadline")
        if seconds <= 0:
            raise ValueError("seconds has to be positive to have any frames in it")
        self.target_fps = target_fps
        self.seconds = seconds
        self.working_set_mb = working_set_mb
        self.chase_steps = chase_steps

    def is_available(self) -> tuple[bool, str]:
        """Always. That is the whole reason this bench exists."""
        return True, ""

    def _one_pass(self, chase: array[int]) -> tuple[list[float], list[float]]:
        """One pass of the loop, as (delivered intervals, per-frame lateness).

        The interval is the gap between one frame starting and the next — the
        cadence a player would actually see, not the time the work took. Those
        are different numbers and only the first one is pacing: a frame whose
        work takes 1 ms of an 8.3 ms budget can still arrive late, and that is
        the failure this bench exists to catch.

        Lateness is measured against a fixed schedule (`start + n * interval`)
        rather than against the previous frame, so a single stalled frame does
        not move every deadline after it. Drift accumulates against a wall clock
        the way it does against a display's refresh.
        """
        interval = 1.0 / self.target_fps
        frames = max(2, int(self.seconds * self.target_fps))

        inbox: queue.SimpleQueue[tuple[array[int], int, int] | None] = queue.SimpleQueue()
        outbox: queue.SimpleQueue[int] = queue.SimpleQueue()
        worker = threading.Thread(target=_worker, args=(inbox, outbox), daemon=True)
        worker.start()

        starts: list[float] = []
        lateness: list[float] = []
        index = 0
        half = self.chase_steps // 2

        try:
            # One frame's work before the clock starts. Starting a thread,
            # faulting in the queue and touching the chase for the first time
            # all land in frame zero, and the schedule below is absolute — so a
            # slow frame zero puts every later deadline in the past, the wait
            # never waits, and the whole pass runs flat out. It came back at
            # 0.76 ms against a 5 ms target on a CI runner, which reads as a
            # loop delivering frames faster than it was asked to.
            inbox.put((chase, index, half))
            index = _chase(chase, index, self.chase_steps - half)
            index = outbox.get()

            start = time.perf_counter()

            for frame in range(frames):
                starts.append(time.perf_counter())

                # Half the chain here, half on the worker, so the frame is not
                # finished until both threads have been scheduled.
                inbox.put((chase, index, half))
                index = _chase(chase, index, self.chase_steps - half)
                index = outbox.get()

                deadline = start + (frame + 1) * interval
                lateness.append((time.perf_counter() - deadline) * 1000.0)
                _wait_until(deadline)
        finally:
            inbox.put(None)
            worker.join(timeout=5.0)

        intervals = [
            (later - earlier) * 1000.0 for earlier, later in zip(starts, starts[1:], strict=False)
        ]
        return intervals, lateness

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()
        budget_ms = 1000.0 / self.target_fps

        # Built once and reused across repeats: the permutation is the load, and
        # rebuilding it would measure the allocator instead of the pacing.
        chase = _build_chase(self.working_set_mb)

        medians: list[float] = []
        p99s: list[float] = []
        p999s: list[float] = []
        jitters: list[float] = []
        missed: list[float] = []

        for _ in range(repeats):
            intervals, lateness = self._one_pass(chase)
            ranked = sorted(intervals)

            medians.append(statistics.median(ranked))
            p99s.append(_percentile(ranked, 0.99))
            p999s.append(_percentile(ranked, 0.999))
            # Deviation from the target, not from the mean: a loop running
            # steadily at the wrong cadence has a low standard deviation and is
            # still not holding the frame rate it was asked for.
            jitters.append(
                statistics.fmean(abs(value - budget_ms) for value in intervals),
            )
            over = sum(1 for value in lateness if value > 0.0)
            missed.append(over / len(lateness) * 100.0)

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                # Its own vocabulary, deliberately not the claim one. `frame_time_ms`
                # and `stutter_count` belong to PresentMon, which measures a real
                # game; this measures a synthetic loop, and letting it answer a
                # claim about a game's frame time would be two different
                # quantities wearing one name. `sources.py` keeps one instrument
                # per metric for exactly that reason.
                "pacing_interval_ms": BenchReading(
                    "pacing_interval_ms", medians, "ms", higher_is_better=False
                ),
                "pacing_p99_ms": BenchReading("pacing_p99_ms", p99s, "ms", higher_is_better=False),
                "pacing_p999_ms": BenchReading(
                    "pacing_p999_ms", p999s, "ms", higher_is_better=False
                ),
                "pacing_jitter_ms": BenchReading(
                    "pacing_jitter_ms", jitters, "ms", higher_is_better=False
                ),
                "missed_frame_percent": BenchReading(
                    "missed_frame_percent", missed, "%", higher_is_better=False
                ),
            },
            detail={
                "target_fps": self.target_fps,
                "frame_budget_ms": round(budget_ms, 4),
                "seconds_per_pass": self.seconds,
                "working_set_mb": self.working_set_mb,
                "chase_steps": self.chase_steps,
            },
            duration_seconds=time.perf_counter() - started,
        )


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted list.

    Nearest-rank rather than interpolated on purpose: p99.9 is supposed to name
    a frame that actually happened, and interpolating invents a frame time
    between two real ones — which for the worst frame is exactly the number
    being asked about.
    """
    if not sorted_values:
        raise ValueError("no values to take a percentile of")
    rank = max(0, min(len(sorted_values) - 1, round(fraction * len(sorted_values)) - 1))
    return sorted_values[rank]
