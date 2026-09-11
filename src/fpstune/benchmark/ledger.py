"""What fpstune is measuring, how far it got, and which machine it is about.

Everything else in `benchmark/` is deliberately stateless. `SuiteRun` lives in
the caller's hands, `/suite/compare` takes two runs in a request body and
forgets them, and `headroom.json` keeps one current answer per game rather than
a history. That was the right call for a button a human presses twice in one
sitting: the browser holds both halves, and nothing accumulates on disk.

A scheduler cannot work that way. It has to know, across a crash, a restart and
a reboot, which run is this machine's baseline, which bench of the plan it was
on when the lights went out, and how many times a bench has already refused to
run. None of that fits in a request body, so this module is the one place in the
package that owns durable state.

It stays small on purpose, and four rules keep it honest — each of them a
failure `state.json` in PC-Check had already been through:

*The step index advances only after the step's result is on disk.* Written the
other way round, a crash between the two writes leaves a ledger claiming a bench
finished and a run file that never held it, and that bench is never measured
again. So `record_step` writes the run first, always, and the ordering is
asserted by a test rather than left to the reader.

*A ledger from another machine is archived, never resumed.* A baseline is a
statement about one set of hardware. Pairing it with an "after" taken somewhere
else produces a verdict that is confidently about nothing, which is precisely
the class of number C11 exists to refuse. The identity is derived at runtime
(C9) and it is not the hostname: a renamed machine is the same machine, and two
machines on different networks can carry the same name.

*Every write is atomic.* `ResultStore.save` writes in place, which is safe for
a result nobody has yet — losing it loses nothing. A ledger truncated by a power
cut is different: it reads back as no job at all, and the baseline it pointed at
becomes unreachable while still sitting on disk. Temp file, then `os.replace`.

*Attempts are persisted rather than counted in memory.* A bench that fails
because a reboot is pending would otherwise get three fresh attempts after every
reboot, forever.

Runs land beside the ledger in exactly the shape `SuiteRun.to_dict()` already
emits, so `SuiteRun.from_dict()` reads them back with no second serialiser.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fpstune.benchmark.suite import BenchResult, SuiteRun
from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

logger = get_logger()

# --- Status -----------------------------------------------------------------

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
ARCHIVED = "archived"

OPEN_STATUSES = frozenset({QUEUED, RUNNING})
"""A job the scheduler may still pick up. Everything else is history."""

# --- Trigger ----------------------------------------------------------------

BASELINE = "baseline"
"""No baseline on record, so measure the machine as the user currently has it."""

AFTER = "after"
"""A bulk apply finished, so measure again and pair it with the baseline."""

MANUAL = "manual"
"""The user asked. Becomes whichever half the ledger is missing."""

# --- Run labels -------------------------------------------------------------
#
# Two labels and no more. `compare_runs` needs a before and an after; a third
# name would be a run nothing ever compares, which is a file that grows and is
# never read — the decision `headroom.json` already made.

BASELINE_LABEL = "baseline"
AFTER_LABEL = "after"

# --- Retry ------------------------------------------------------------------

MAX_ATTEMPTS = 3
"""Past this a bench is not failing intermittently, it is failing."""

BACKOFF_SECONDS: tuple[float, ...] = (30.0, 120.0, 480.0)
"""30 s, 2 min, 8 min.

The short wait covers a bench blocked by something that clears on its own — a
file still being written, a burst of CPU from another process. The long one
stops a bench blocked by something that does not clear from asking every minute
until the machine reboots.
"""


def backoff_for(attempt: int) -> float:
    """How long to wait after `attempt` failures.

    Clamped rather than extrapolated: an attempt count past the end of the table
    only happens when the caller ignored `attempts_exhausted`, and inventing a
    longer wait would hide that.
    """
    return BACKOFF_SECONDS[min(max(attempt, 0), len(BACKOFF_SECONDS) - 1)]


# --- Where it all lives -----------------------------------------------------


def bench_dir() -> Path:
    """`~/.fpstune/bench` — the ledger, the runs and the sentinel."""
    return get_config_dir() / "bench"


def ledger_path() -> Path:
    return bench_dir() / "ledger.json"


def runs_dir() -> Path:
    return bench_dir() / "runs"


def sentinel_path() -> Path:
    """Where the apply path leaves word that a bulk apply finished.

    A file rather than an in-process flag because the two ends need not overlap
    in time: a user can apply forty settings and close fpstune before the next
    scheduler tick, and the "measure the result" trigger has to still be there
    when it opens again.
    """
    return bench_dir() / "bulk-apply-finished.json"


# --- Which machine this is --------------------------------------------------

_machine_lock = threading.Lock()
_machine_cache: str | None = None


def _compute_machine_id() -> str:
    """Derive a stable identity for this machine, at runtime, from the machine.

    `MachineGuid` is Windows' own answer to "which installation is this": it is
    written at setup, survives renames and hardware swaps, and reads out of the
    registry with no subprocess and no measurable delay. It is hashed rather
    than stored because the ledger only ever needs to answer "same machine or
    not", and an identifier that never has to be read does not have to be kept.

    The fallback exists for the non-Windows path and for a registry read that is
    refused. It is weaker — an architecture and a core count identify a model
    rather than a machine — but it is still derived, still stable across runs,
    and still never a literal about the machine this was written on (C9).

    Never the hostname: a renamed machine is the same machine, and two machines
    on different networks can carry the same name.
    """
    raw = ""
    if sys.platform == "win32":
        with contextlib.suppress(OSError, ValueError):
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                raw = str(value)

    if not raw:
        # Deliberately coarse and deliberately not empty. An unknown identity
        # that compared equal to nothing would archive this machine's own ledger
        # on every tick and never produce a comparison at all.
        raw = f"{platform.machine()}|{os.cpu_count()}|{platform.system()}"
        logger.debug("machine identity fell back to a derived description")

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def machine_id() -> str:
    """This machine's identity, computed once per process."""
    global _machine_cache
    with _machine_lock:
        if _machine_cache is None:
            _machine_cache = _compute_machine_id()
        return _machine_cache


def reset_machine_id() -> None:
    """Forget the cached identity. For tests."""
    global _machine_cache
    with _machine_lock:
        _machine_cache = None


# --- The job ----------------------------------------------------------------


@dataclass
class Job:
    """One measurement plan, and how far through it this machine got."""

    id: str
    trigger: str
    plan: list[str]
    """Bench keys, in the order they will run."""

    step_index: int = 0
    """How many of `plan` have their result on disk. Never more than that."""

    status: str = QUEUED
    attempts: dict[str, int] = field(default_factory=dict)
    """Per bench, how many times it has been tried and failed."""

    machine: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    runs: dict[str, str] = field(default_factory=dict)
    """Label -> the run file's path, reserved when the job opens.

    Reserved rather than assigned at the end, because a resume has to find the
    partial run before the plan is finished — and a path derived twice is a path
    that can be derived differently twice.
    """

    @property
    def label(self) -> str:
        """Which half of a comparison this job is measuring."""
        return next(iter(self.runs), AFTER_LABEL)

    @property
    def run_path(self) -> Path:
        return Path(self.runs[self.label])

    @property
    def remaining(self) -> list[str]:
        """The benches still to run, in plan order."""
        return self.plan[self.step_index :]

    @property
    def current_bench(self) -> str | None:
        """The bench this job is on, or None when the plan is finished."""
        return self.plan[self.step_index] if self.step_index < len(self.plan) else None

    @property
    def is_complete(self) -> bool:
        return self.step_index >= len(self.plan)

    def attempts_exhausted(self, bench: str) -> bool:
        return self.attempts.get(bench, 0) >= MAX_ATTEMPTS

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trigger": self.trigger,
            "plan": list(self.plan),
            "step_index": self.step_index,
            "status": self.status,
            "attempts": dict(self.attempts),
            "machine": self.machine,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "runs": dict(self.runs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Job:
        return cls(
            id=str(payload["id"]),
            trigger=str(payload["trigger"]),
            plan=[str(key) for key in payload["plan"]],
            step_index=int(payload.get("step_index", 0)),
            status=str(payload.get("status", QUEUED)),
            attempts={str(k): int(v) for k, v in (payload.get("attempts") or {}).items()},
            machine=str(payload.get("machine", "")),
            created_at=float(payload.get("created_at", 0.0)),
            updated_at=float(payload.get("updated_at", 0.0)),
            runs={str(k): str(v) for k, v in (payload.get("runs") or {}).items()},
        )


# --- Atomic writes ----------------------------------------------------------

# Windows hands back a sharing violation when an indexer or a scanner has the
# destination open for the moment `os.replace` needs it. The same retry the MW4
# config writer already carries, for the same reason.
_REPLACE_ATTEMPTS = 5
_REPLACE_PAUSE_SECONDS = 0.05

_write_lock = threading.Lock()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON so that a reader sees the old file or the new one, never half.

    The temp file is removed on every path. A failed write that left its own
    `.tmp` behind would accumulate one per power cut, in the directory whose
    whole job is to be readable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        last: OSError | None = None
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                return
            except OSError as exc:
                last = exc
                if attempt < _REPLACE_ATTEMPTS - 1:
                    time.sleep(_REPLACE_PAUSE_SECONDS)
        raise last if last is not None else OSError(f"could not replace {path}")
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read one JSON object, or say why it could not be read.

    Never silent (C11 rule 3): a ledger that cannot be parsed is a baseline the
    user will never see again, and swallowing that makes the next run look like
    a first run.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Benchmark ledger at %s could not be read: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Benchmark ledger at %s is not a JSON object", path)
        return None
    return data


def _write_run(path: Path, run: SuiteRun) -> None:
    """Persist a run in exactly the shape `SuiteRun.from_dict` expects back."""
    _atomic_write(path, run.to_dict())


def _write_job(job: Job) -> None:
    job.updated_at = time.time()
    _atomic_write(ledger_path(), job.to_dict())


# --- Reading and opening ----------------------------------------------------


def read_job() -> Job | None:
    """Whatever the ledger holds, whatever machine it is about."""
    payload = _read_json(ledger_path())
    if payload is None:
        return None
    try:
        return Job.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Benchmark ledger holds no readable job: %s", exc)
        return None


def _is_ours(job: Job) -> bool:
    return job.machine == machine_id()


def _archive(job: Job, why: str) -> None:
    logger.info("Archiving benchmark job %s: %s", job.id, why)
    job.status = ARCHIVED
    _write_job(job)


def current_job() -> Job | None:
    """The job this machine may still work on, or None.

    A job belonging to another machine is archived on the way past rather than
    deleted — a ledger that arrived from somewhere else is worth being able to
    see, and a silent delete would make a copied `~/.fpstune` look like a fresh
    install.
    """
    job = read_job()
    if job is None:
        return None
    if not _is_ours(job):
        if job.status != ARCHIVED:
            _archive(job, "it was written by a different machine")
        return None
    if job.status not in OPEN_STATUSES:
        return None
    return job


def _label_for(trigger: str) -> str:
    """Which half of the comparison a new job is measuring.

    A manual job is whichever half is missing: measuring for the first time
    because the user asked is still a first measurement, and filing it as an
    "after" would leave a comparison half with nothing to compare against.
    """
    if trigger == BASELINE:
        return BASELINE_LABEL
    if trigger == AFTER:
        return AFTER_LABEL
    return AFTER_LABEL if baseline() is not None else BASELINE_LABEL


def open_job(trigger: str, plan: list[str], *, now: float | None = None) -> Job:
    """Start a job and put it on disk before a single bench runs.

    Written first, deliberately: a job that only reaches the ledger once it
    finishes cannot be resumed, which is the entire reason the ledger exists.
    """
    if not plan:
        raise ValueError("a job with no benches in its plan would measure nothing")

    now = time.time() if now is None else now
    job_id = uuid.uuid4().hex[:12]
    label = _label_for(trigger)

    with _write_lock:
        job = Job(
            id=job_id,
            trigger=trigger,
            plan=list(plan),
            status=QUEUED,
            machine=machine_id(),
            created_at=now,
            updated_at=now,
            runs={label: str(runs_dir() / f"{label}_{job_id}.json")},
        )
        runs_dir().mkdir(parents=True, exist_ok=True)
        _write_job(job)
    return job


def read_run(job: Job) -> SuiteRun | None:
    """This job's run so far, including a partial one mid-plan."""
    payload = _read_json(job.run_path)
    if payload is None:
        return None
    try:
        return SuiteRun.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Benchmark run at %s could not be rebuilt: %s", job.run_path, exc)
        return None


def record_step(job: Job, result: BenchResult) -> Job:
    """Append one bench's result to the run, then advance the step.

    The order is the guarantee. The run file is written first and the ledger
    second, so a crash between them re-runs exactly one bench — the one that was
    in flight — rather than losing a result the ledger already counted.
    """
    with _write_lock:
        run = read_run(job) or SuiteRun(label=job.label, started_at=job.created_at)
        run.results = [existing for existing in run.results if existing.bench != result.bench]
        run.results.append(result)

        _write_run(job.run_path, run)

        job.step_index = min(job.step_index + 1, len(job.plan))
        job.status = DONE if job.is_complete else RUNNING
        _write_job(job)
    return job


def record_attempt(job: Job, bench: str) -> Job:
    """Count one failed attempt at a bench, on disk.

    In memory it would reset with the process, and a bench blocked by something
    that outlives the process — a pending reboot, a missing tool — would get
    three fresh attempts every time fpstune opened.
    """
    with _write_lock:
        job.attempts[bench] = job.attempts.get(bench, 0) + 1
        _write_job(job)
    return job


def finish_job(job: Job, *, status: str = DONE) -> Job:
    """Close a job out. Its run stays; the job stops being resumable."""
    with _write_lock:
        job.status = status
        _write_job(job)
    return job


# --- The bulk-apply sentinel ------------------------------------------------


def mark_bulk_apply_finished() -> None:
    """Record that a bulk apply just finished, for the scheduler to find.

    Called from the apply path — see the `TODO(wire)` note — and deliberately
    the only thing that path has to know about benchmarking. Writing a file
    rather than calling the scheduler keeps the dependency one-way and lets the
    trigger outlive a restart between the apply and the next tick.

    Idempotent: two bulk applies before a single tick are one reason to measure,
    not two. The timestamp is overwritten so the sentinel always names the most
    recent apply.
    """
    with contextlib.suppress(OSError):
        _atomic_write(sentinel_path(), {"finished_at": time.time()})


def bulk_apply_pending() -> bool:
    """Whether an apply is waiting to be measured. Does not consume it."""
    return sentinel_path().exists()


def take_bulk_apply_sentinel() -> bool:
    """Consume the sentinel, answering whether there was one.

    Consumed at the moment the job is opened rather than when it finishes: a
    scheduler that left it in place would open an "after" job on every tick for
    as long as the first one took to run.
    """
    path = sentinel_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Could not consume the bulk-apply sentinel: %s", exc)
        return False
    return True


# --- The two halves of a comparison -----------------------------------------


def _finished_runs(label: str) -> list[Path]:
    """Every completed run under this label, newest first."""
    directory = runs_dir()
    if not directory.is_dir():
        return []
    found = list(directory.glob(f"{label}_*.json"))
    found.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return found


def _load_run(path: Path) -> SuiteRun | None:
    payload = _read_json(path)
    if payload is None:
        return None
    try:
        return SuiteRun.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Benchmark run at %s could not be rebuilt: %s", path, exc)
        return None


def _runs_are_ours() -> bool:
    """Whether the runs on disk describe this machine.

    The run files carry no identity of their own — they are exactly
    `SuiteRun.to_dict()`, and adding a field would mean a second serialiser —
    so the ledger beside them is the authority on whose they are. No ledger at
    all means no provenance, and a run whose machine cannot be established is
    not offered as half of a comparison: that is the mistake this check exists
    to prevent, arriving through a different door.
    """
    job = read_job()
    if job is None:
        return False
    if not _is_ours(job):
        if job.status != ARCHIVED:
            _archive(job, "it was written by a different machine")
        return False
    return True


def _newest_complete(label: str) -> SuiteRun | None:
    """The newest run under this label that belongs to a finished job.

    Unfinished jobs are skipped rather than returned partial: comparing four
    benches against six pairs half a measurement with a whole one, and
    `compare_runs` would honestly report the difference as unpaired metrics
    while the summary counted a run that never completed.
    """
    if not _runs_are_ours():
        return None

    open_now = read_job()
    in_flight = (
        Path(open_now.run_path) if open_now is not None and not open_now.is_complete else None
    )

    for path in _finished_runs(label):
        if in_flight is not None and path == in_flight:
            continue
        run = _load_run(path)
        if run is not None:
            return run
    return None


def baseline() -> SuiteRun | None:
    """This machine's baseline run, or None if it has not taken one."""
    return _newest_complete(BASELINE_LABEL)


def latest_after() -> SuiteRun | None:
    """The most recent post-apply run, or None."""
    return _newest_complete(AFTER_LABEL)


def pair() -> tuple[SuiteRun, SuiteRun] | None:
    """Both halves of a comparison, before then after — or None.

    None rather than a one-sided result on purpose. A comparison needs two runs,
    and returning one with a placeholder for the other is how half a measurement
    becomes a verdict (C11 rule 2).
    """
    before = baseline()
    after = latest_after()
    if before is None or after is None:
        return None
    return before, after
