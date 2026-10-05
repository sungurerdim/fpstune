"""Running a child process until it finishes or stops making progress — the one rule.

A timeout here means *stuck*, never *slow*. Fixed ceilings were set per command
from a guess at how long it takes, and every guess was wrong somewhere: a 30 s
restore point killed mid-snapshot, a 60 s Windows Update cache cleanup killed
mid-delete on a machine with 15 GB to remove — each reported as a failure while
the work was going fine. A clean machine and a neglected one differ by orders of
magnitude in how long the same command takes, and no constant covers both.

So the clock measures silence. Progress is any of: a new line of output, bytes
read or written anywhere in the process tree, or CPU work above a floor anywhere
in the tree (`winapi.job`). Each one resets the clock; only a stretch with none
of them, as long as the policy's ``stall_s``, ends the run as timed out. A
silent ``Remove-Item`` over a large folder moves bytes the whole time and is
never cut off; a process blocked on a lock that never comes moves nothing and is.

What happens to a stuck tree is the policy's call. ``kill`` stops the whole tree
through its job. ``leave`` reports the stall and lets it run — for servicing
(DISM, SFC), where interrupting a write is worse than an operation that
finishes unwatched.

Every caller picks a named policy below rather than a number; a new kind of
command adds a policy here, which keeps the rule in one place.
"""

from __future__ import annotations

import codecs
import contextlib
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import IO, Literal, Protocol

from fpstune.utils.winapi.job import ProcessTreeJob, TreeActivity


@dataclass(frozen=True)
class StallPolicy:
    """When a run counts as stuck, and what to do about it."""

    name: str
    # No progress for this long means the run is stuck.
    stall_s: float
    on_stall: Literal["kill", "leave"] = "kill"
    # CPU below this fraction of one core, sustained over a sample, is a waiting
    # loop rather than work: a polling script must not count as progress forever.
    cpu_floor: float = 0.02
    # Seconds between activity samples.
    sample_s: float = 2.0


# A read: an inventory query, a state probe. Seconds of work when healthy, so a
# minute with nothing happening is already abnormal.
QUERY = StallPolicy("query", stall_s=60.0)
# A change: an apply, a cleanup, a reset. Can legitimately run for many minutes,
# but never minutes without moving a byte or a CPU cycle.
CHANGE = StallPolicy("change", stall_s=300.0)
# Servicing: DISM component work, SFC. Long quiet phases are normal, and killing
# one mid-write can damage the component store, so a stall is reported and the
# tree is left to finish.
SERVICING = StallPolicy("servicing", stall_s=900.0, on_stall="leave")


def quiet_for(seconds: float, base: StallPolicy = QUERY) -> StallPolicy:
    """``base`` for a command that is silent for ``seconds`` by design.

    A sampling script that sleeps between readings and prints once at the end
    looks exactly like a stuck one until it prints. Its own planned quiet period
    is added to the stall window, so only silence *beyond* the plan counts.
    """
    return replace(base, name=f"{base.name}+quiet", stall_s=base.stall_s + seconds)


@dataclass
class RunResult:
    """How a watched run ended."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    # True when the run stalled under a "leave" policy and is still going.
    left_running: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class ActivityProbe(Protocol):
    """What the watcher asks about the running tree."""

    def activity(self) -> TreeActivity | None: ...

    def terminate(self) -> None: ...

    def close(self) -> None: ...


class _ProcessOnlyProbe:
    """Where no job could be made: no counters, and only the direct child to stop."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process

    def activity(self) -> TreeActivity | None:
        return None

    def terminate(self) -> None:
        with contextlib.suppress(OSError):
            self._process.kill()

    def close(self) -> None:
        return None


def _default_probe(process: subprocess.Popen[bytes]) -> ActivityProbe:
    handle = getattr(process, "_handle", None)
    job = ProcessTreeJob.around(int(handle)) if handle is not None else None
    return job if job is not None else _ProcessOnlyProbe(process)


def describe_stall(policy: StallPolicy) -> str:
    """The sentence every caller shows for a stall, so none words it differently."""
    whole = int(policy.stall_s)
    span = f"{whole // 60} min" if whole >= 60 and whole % 60 == 0 else f"{whole} s"
    tail = " (left running)" if policy.on_stall == "leave" else ""
    return f"no progress for {span}{tail}"


@dataclass
class _Pipe:
    """One output stream, decoded as it arrives."""

    stream: IO[bytes]
    encoding: str
    on_text: Callable[[str], None] | None
    chunks: list[str] = field(default_factory=list)
    thread: threading.Thread | None = None


def run_watched(
    argv: list[str],
    policy: StallPolicy,
    *,
    on_text: Callable[[str], None] | None = None,
    merge_stderr: bool = False,
    encoding: str = "utf-8",
    creationflags: int = 0,
    probe_factory: Callable[[subprocess.Popen[bytes]], ActivityProbe] = _default_probe,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Run ``argv`` to completion unless it stops making progress.

    ``on_text`` receives stdout as it is decoded (merged with stderr when
    ``merge_stderr``), on a reader thread. Raises ``OSError`` when the program
    cannot be started, exactly as ``subprocess.Popen`` does.
    """
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        creationflags=creationflags,
    )
    probe = probe_factory(process)
    last_progress = clock()
    progress_lock = threading.Lock()

    def _note_progress() -> None:
        nonlocal last_progress
        with progress_lock:
            last_progress = clock()

    pipes: list[_Pipe] = []
    assert process.stdout is not None
    pipes.append(_Pipe(process.stdout, encoding, on_text))
    if not merge_stderr:
        assert process.stderr is not None
        pipes.append(_Pipe(process.stderr, encoding, None))

    for pipe in pipes:
        pipe.thread = threading.Thread(
            target=_pump, args=(pipe, _note_progress), daemon=True, name="watched-pipe"
        )
        pipe.thread.start()

    previous = probe.activity()
    try:
        while process.poll() is None:
            time.sleep(policy.sample_s)
            current = probe.activity()
            if _tree_moved(previous, current, policy):
                _note_progress()
            previous = current if current is not None else previous
            with progress_lock:
                silent_for = clock() - last_progress
            if silent_for >= policy.stall_s:
                reason = describe_stall(policy)
                if policy.on_stall == "kill":
                    probe.terminate()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=10)
                    return _result(process, pipes, timed_out=True, reason=reason)
                return _result(process, pipes, timed_out=True, left_running=True, reason=reason)
        # The direct child has exited. A grandchild can still hold a pipe open;
        # the readers are daemons, so collect what arrived and do not wait on them.
        for pipe in pipes:
            if pipe.thread is not None:
                pipe.thread.join(timeout=2)
        return _result(process, pipes)
    finally:
        probe.close()


def _tree_moved(
    before: TreeActivity | None, after: TreeActivity | None, policy: StallPolicy
) -> bool:
    if before is None or after is None:
        return False
    if after.io_bytes > before.io_bytes:
        return True
    return (after.cpu_seconds - before.cpu_seconds) >= policy.cpu_floor * policy.sample_s


def _pump(pipe: _Pipe, note_progress: Callable[[], None]) -> None:
    decoder = codecs.getincrementaldecoder(pipe.encoding)("replace")
    read = getattr(pipe.stream, "read1", pipe.stream.read)
    with contextlib.suppress(Exception):
        while True:
            chunk = read(4096)
            if not chunk:
                break
            note_progress()
            text = decoder.decode(chunk)
            if text:
                pipe.chunks.append(text)
                if pipe.on_text is not None:
                    pipe.on_text(text)
        tail = decoder.decode(b"", final=True)
        if tail:
            pipe.chunks.append(tail)
            if pipe.on_text is not None:
                pipe.on_text(tail)


def _result(
    process: subprocess.Popen[bytes],
    pipes: list[_Pipe],
    *,
    timed_out: bool = False,
    left_running: bool = False,
    reason: str = "",
) -> RunResult:
    stdout = "".join(pipes[0].chunks)
    stderr = "".join(pipes[1].chunks) if len(pipes) > 1 else ""
    return RunResult(
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        left_running=left_running,
        reason=reason,
    )


def no_window_flags() -> int:
    """CREATE_NO_WINDOW on Windows, nothing elsewhere."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
