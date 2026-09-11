"""When to measure, and — mostly — when to keep out of the way.

The benches here need the machine *not* to be doing anything, they change
nothing themselves, and there is no user watching to confirm the moment was a
good one. So every decision here has to be defensible on its own, because a
measurement taken at the wrong moment is indistinguishable from a good one
afterwards — and that is exactly the class of number C11 exists to refuse.

**The triggers, all derived, none of them a button.** No baseline on record →
take one, because every later comparison needs a before and the user should not
have to know that. A bulk apply just finished → take an "after", signalled by a
sentinel file the apply path writes so the trigger survives a restart between
the two. Nothing else.

**The frame-rate band comes from here too.** `gpu_scene` is in the plan, so a
scheduled run already renders the fixed scene at the panel's own resolution;
`performance_headroom` gets that result and turns it into the machine's band.
Which is why there is no second daemon waiting for a game to start: the reading
that decides whether image quality is affordable is produced by the same pass
that produces the baseline, on a load that is the same every time.

**The guards, and why each one is a refusal rather than a filter.**

*A known game is running.* A synthetic bench during a match steals frames from
the thing the whole product exists to protect. Consequence 3, applied to our own
tooling: a benchmark that lowers the ceiling is not a benchmark.

*The machine is in use.* Measured through `GetLastInputInfo` over `ctypes` — not
PowerShell `Add-Type`, which is banned outright after Defender classified it as
a trojan. Measuring while somebody types measures the typing.

*Another operation holds the lock.* An apply, a cleanup and a bench must never
overlap; a run that straddles a bulk apply describes a machine halfway between
two states and cannot say which one it meant.

*An apply is running in this process.* The lock alone does not cover it: a
Windows mutex is owned by the thread that took it, and a bulk apply runs on
sixteen pool threads while this one asks. So the apply path keeps a counter
(`settings_apply.applies_in_flight`) and this reads it live. Read rather than
mirrored — a second copy of that count would go stale exactly when it mattered.

An unreadable answer to any of these counts as "do not run". The cost of
deferring is one minute; the cost of measuring at the wrong moment is a number
that misleads for as long as it is on screen.

**One bench per tick.** A whole plan under one lock would hold it for minutes
and make every guard a decision taken once rather than continuously — the game
the user launched thirty seconds in would find the bench already committed.

The shape — `_stop` event, `poll_once` split out from the loop, 60-second
cadence, daemon thread — keeps every decision above testable without waiting a
minute for a timer, and keeps starting and stopping the daemon one call each.
"""

from __future__ import annotations

import contextlib
import ctypes
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

from fpstune.benchmark import ledger
from fpstune.benchmark.benches import benches_for, default_keys, tool_executable_names
from fpstune.benchmark.operation_lock import operation_lock
from fpstune.benchmark.suite import Bench, BenchResult, run_bench_with_deadline
from fpstune.settings.executors.game_processes import GAME_PROCESSES, game_is_running
from fpstune.utils.logger import get_logger

logger = get_logger()

POLL_INTERVAL_SECONDS = 60.0
"""The checks are cheap, and nothing this decides is urgent to the second."""

FIRST_POLL_DELAY_SECONDS = 90.0
"""Long enough to be out of startup, because this one can start a bench.

Startup is registry warm-up, GPU detection and the first scan. A baseline taken
into the middle of that would measure fpstune starting up and then stand as this
machine's reference number for every comparison afterwards.
"""

IDLE_REQUIRED_SECONDS = 300.0
"""Five minutes with no keyboard or mouse before anything synthetic starts.

Long enough that a pause to read something is not mistaken for an empty chair,
and short enough that a machine left alone gets measured the same session.
"""

BENCH_REPEATS = 3
"""`DEFAULT_REPEATS`, and for the same reason: two is the floor at which a noise
floor exists at all, three is the floor at which one outlier cannot own the
median."""

# What one tick did. Named rather than boolean because the reasons are the
# useful part — `sources.py`'s "here is why we cannot check that", applied to
# the scheduler's own decisions.
RAN = "ran"
NOTHING_TO_DO = "nothing_to_do"
GAME_RUNNING = "game_running"
NOT_IDLE = "not_idle"
BUSY = "busy"
WAITING_BACKOFF = "waiting_backoff"
FAILED = "failed"


@dataclass(frozen=True)
class TickOutcome:
    """What one pass decided, and why."""

    outcome: str
    detail: str
    job_id: str | None = None
    bench: str | None = None

    @property
    def measured(self) -> bool:
        return self.outcome == RAN


# --- Is anyone playing? ------------------------------------------------------


def running_games() -> list[str]:
    """Which of the known games is rendering right now, in a stable order.

    Sorted rather than dictionary order so the sentence a refusal produces is
    the same on two machines running the same two games.
    """
    return [game for game in sorted(GAME_PROCESSES) if game_is_running(game)]


# --- Is anyone using this machine? ------------------------------------------


class _LastInputInfo(ctypes.Structure):
    _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))


_TICK_WRAP = 0x100000000
"""`GetTickCount` is 32-bit and wraps after 49.7 days of uptime.

`dwTime` comes from that same 32-bit clock, so the difference is taken modulo
its range. Subtracting it from `GetTickCount64` instead reads correctly for
seven weeks and then reports an idle time of about 49 days, which would license
a benchmark in the middle of whatever the user was doing.
"""


def idle_seconds() -> float:
    """How long since the last keyboard or mouse input, in seconds.

    Zero when it cannot be read, and zero means "in use" to every caller here.
    That is the conservative direction on purpose: an idle time nothing could
    establish must not be the reason a bench starts during a match.
    """
    if sys.platform != "win32":
        return 0.0

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetLastInputInfo.argtypes = (ctypes.POINTER(_LastInputInfo),)
        user32.GetLastInputInfo.restype = wintypes.BOOL
        kernel32.GetTickCount.restype = wintypes.DWORD

        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(_LastInputInfo)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0

        elapsed = (int(kernel32.GetTickCount()) - int(info.dwTime)) % _TICK_WRAP
        return float(elapsed) / 1000.0
    except Exception as exc:  # noqa: BLE001 - an unreadable idle time is "in use"
        logger.debug("Could not read the last input time: %s", exc)
        return 0.0


# --- Leftovers from a previous session --------------------------------------


def sweep_leftover_tools(names: list[str] | None = None) -> int:
    """Kill benchmark tools a previous session left running. Returns how many.

    PC-Check's `Stop-StressTools` at launch, absorbed. A FurMark left running by
    a crash is a power virus holding the GPU at its thermal limit; a PresentMon
    left running holds an ETW session. Either one silently ruins the first
    measurement of the new session, and looks like a result rather than a
    mistake.

    The names come from the tools' own executable paths rather than a list kept
    here — see `benches.tool_executable_names`.
    """
    if sys.platform != "win32":
        return 0

    targets = tool_executable_names() if names is None else names
    killed = 0
    for name in targets:
        try:
            completed = subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("Could not sweep %s: %s", name, exc)
            continue
        # Exit code 128 is "no such process", which is the ordinary case and not
        # worth a word.
        if completed.returncode == 0:
            logger.info("Swept a leftover %s from a previous session", name)
            killed += 1
    return killed


# --- Which benches, and which one is next -----------------------------------


def plan_keys() -> list[str]:
    """The benches a scheduled job runs, in order.

    The default set rather than every bench: `network_load` downloads about
    25 MB a pass, and a daemon nobody asked doing that on a metered connection
    is a cost the user never agreed to. `benches.py` already draws that line and
    this defers to it rather than drawing a second one.
    """
    return default_keys()


def bench_named(key: str) -> Bench:
    """One bench, freshly built. Raises KeyError if the plan names a stranger."""
    found = benches_for([key])
    if not found:
        raise KeyError(f"no bench named {key!r}")
    return found[0]


# --- One pass ---------------------------------------------------------------


def _job_for_trigger() -> ledger.Job | None:
    """Open a job if something has triggered one, else None.

    Order matters: a machine with no baseline takes one first, because an
    "after" with nothing to compare against is half a measurement that will
    never become whole.
    """
    if ledger.baseline() is None:
        logger.info("No baseline on record; measuring this machine as it stands")
        return ledger.open_job(ledger.BASELINE, plan_keys())

    if ledger.take_bulk_apply_sentinel():
        logger.info("A bulk apply finished; measuring the result")
        return ledger.open_job(ledger.AFTER, plan_keys())

    return None


def applies_in_flight() -> int:
    """How many applies are running in this process right now.

    Imported inside the function on purpose. `api.routes.settings_apply` imports
    `benchmark.operation_lock` at module level, so the edge back to it has to be
    a late one — the dependency between the apply path and the benchmark package
    stays one-way, and importing a FastAPI route module to answer a scheduler
    question would drag the whole API layer into a daemon that does not need it.

    Zero when it cannot be answered, which is the same direction the lock takes:
    the lock is checked immediately afterwards and is the stronger of the two.
    """
    try:
        from fpstune.api.routes.settings_apply import applies_in_flight as counted
    except Exception as exc:  # noqa: BLE001 - a missing apply path is not an apply
        logger.debug("Could not read the apply counter: %s", exc)
        return 0
    return counted()


def _guard() -> TickOutcome | None:
    """The reasons not to start a synthetic bench, or None to go ahead."""
    running_applies = applies_in_flight()
    if running_applies:
        return TickOutcome(
            BUSY,
            f"{running_applies} apply/applies are running; a bench now would measure "
            "a machine halfway between two states",
        )

    games = running_games()
    if games:
        return TickOutcome(
            GAME_RUNNING,
            f"{', '.join(games)} is running — a synthetic bench would take frames from it",
        )

    idle = idle_seconds()
    if idle < IDLE_REQUIRED_SECONDS:
        return TickOutcome(
            NOT_IDLE,
            f"the machine was used {idle:.0f}s ago; measuring now would measure that",
        )

    return None


def record_headroom_band(result: BenchResult) -> bool:
    """Turn a finished `gpu_scene` run into this machine's band. Returns if it wrote.

    Every scheduled job renders the scene anyway — it is in the default plan, so
    both the baseline and the "after" produce one. Reading the band off that run
    is what makes the measurement unattended: nothing has to be played, and the
    number that decides whether image quality is affordable is produced by the
    same fixed load on both sides of a comparison.

    Only `gpu_scene`. A band is a frame rate against the panel's own ceiling, and
    no other bench in the plan measures a frame rate.

    A failure here is logged and swallowed. The ledger already holds the result;
    an unwritable state directory must leave the product recommending
    conservatively, not abandon the job halfway through its plan.
    """
    if result.bench != "gpu_scene":
        return False

    try:
        from fpstune.settings.performance_headroom import panel_target_fps, record_scene_result

        target = panel_target_fps()
        if target is None:
            logger.debug("The panel reports no refresh rate, so the scene result has no target")
            return False
        return record_scene_result(result, target_fps=target, measured_at=time.time())
    except Exception as exc:  # noqa: BLE001 - a band nobody could write is not a failed job
        logger.debug("Could not record the headroom band: %s", exc)
        return False


def _run_step(job: ledger.Job, bench_key: str) -> TickOutcome:
    """Measure one bench and put its result, or its failure, on the record."""
    try:
        bench = bench_named(bench_key)
    except KeyError as exc:
        # A plan naming a bench that no longer exists must not wedge the job.
        result = BenchResult(bench=bench_key, label=bench_key, ran=False, reason=str(exc))
        ledger.record_step(job, result)
        return TickOutcome(FAILED, str(exc), job.id, bench_key)

    available, why = bench.is_available()
    if not available:
        # Not a failure to retry: "this machine has no such thing" does not
        # become true on the third attempt.
        ledger.record_step(
            job, BenchResult(bench=bench.key, label=bench.label, ran=False, reason=why)
        )
        return TickOutcome(RAN, f"{bench.label} cannot run here: {why}", job.id, bench_key)

    result = run_bench_with_deadline(bench, BENCH_REPEATS)

    if result.ran:
        ledger.record_step(job, result)
        record_headroom_band(result)
        _close_if_done(job)
        return TickOutcome(RAN, f"{bench.label} measured", job.id, bench_key)

    ledger.record_attempt(job, bench_key)
    if job.attempts_exhausted(bench_key):
        # The last failure verbatim, never paraphrased: it is the only part that
        # tells the user whether they can do anything about it (C11 rule 3).
        ledger.record_step(job, result)
        _close_if_done(job)
        return TickOutcome(RAN, f"{bench.label} gave up: {result.reason}", job.id, bench_key)

    return TickOutcome(
        FAILED,
        f"{bench.label} did not measure ({result.reason}); "
        f"attempt {job.attempts[bench_key]} of {ledger.MAX_ATTEMPTS}",
        job.id,
        bench_key,
    )


def _close_if_done(job: ledger.Job) -> None:
    if job.is_complete:
        logger.info("Benchmark job %s finished its plan", job.id)
        ledger.finish_job(job)


def _backoff_pending(job: ledger.Job, bench_key: str, now: float) -> TickOutcome | None:
    """Whether this bench is still inside the wait after its last failure."""
    attempts = job.attempts.get(bench_key, 0)
    if attempts == 0:
        return None

    wait = ledger.backoff_for(attempts - 1)
    waited = now - job.updated_at
    if waited >= wait:
        return None

    return TickOutcome(
        WAITING_BACKOFF,
        f"{bench_key} failed {attempts} time(s); waiting {wait - waited:.0f}s more",
        job.id,
        bench_key,
    )


def poll_once(now: float | None = None, *, first_tick: bool = False) -> TickOutcome:
    """One pass: resume, or trigger, or explain why not.

    Split out from the loop so every decision above is testable without waiting
    a minute for a timer.
    """
    now = time.time() if now is None else now

    if first_tick:
        # Before anything of ours starts, and only once: a tool left running by
        # the last session is competing with the bench about to begin.
        with contextlib.suppress(Exception):
            sweep_leftover_tools()

    job = ledger.current_job()
    resuming = job is not None

    # The guards come before a job is *opened*, not just before it runs. Opening
    # one and then refusing to run it would spend the bulk-apply sentinel on a
    # tick that measured nothing, and the trigger would not come back.
    blocked = _guard()
    if blocked is not None:
        return blocked

    if job is None:
        job = _job_for_trigger()
    if job is None:
        return TickOutcome(NOTHING_TO_DO, "a baseline is on record and no apply is waiting")

    bench_key = job.current_bench
    if bench_key is None:
        _close_if_done(job)
        return TickOutcome(NOTHING_TO_DO, "the open job had nothing left in its plan", job.id)

    waiting = _backoff_pending(job, bench_key, now)
    if waiting is not None:
        return waiting

    with operation_lock() as taken:
        if not taken:
            return TickOutcome(
                BUSY,
                "another fpstune operation is running; a bench now would measure "
                "a machine halfway between two states",
                job.id,
                bench_key,
            )
        if resuming:
            logger.debug("Resuming benchmark job %s at %s", job.id, bench_key)
        return _run_step(job, bench_key)


# --- The daemon -------------------------------------------------------------

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()


def _watch_loop() -> None:  # pragma: no cover - timing loop, poll_once is tested
    if _stop.wait(FIRST_POLL_DELAY_SECONDS):
        return
    first = True
    while True:
        try:
            outcome = poll_once(first_tick=first)
            first = False
            if outcome.measured:
                logger.info("benchmark: %s", outcome.detail)
            else:
                logger.debug("benchmark: %s (%s)", outcome.detail, outcome.outcome)
        except Exception as exc:
            # A background measurement failing must never take the API with it.
            logger.debug("benchmark poll failed: %s", exc)
        if _stop.wait(POLL_INTERVAL_SECONDS):
            return


def start_bench_scheduler() -> bool:
    """Begin scheduling measurements. Returns whether a thread was started."""
    global _thread

    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(target=_watch_loop, daemon=True, name="bench-scheduler")
        _thread.start()
    return True


def stop_bench_scheduler(timeout: float = 5.0) -> None:
    """Ask the scheduler thread to stop, and wait briefly for it."""
    global _thread

    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    _thread = None
