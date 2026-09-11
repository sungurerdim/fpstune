"""What this CPU gets through, on one core and on all of them.

`sources.py` never carried a CPU throughput number. `gpu_performance` has its
instrument now (`gpu_scene`), but the CPU half of that question was never even
asked; and every setting that
claims to leave more of the processor for the game — core parking, the idle
floor, the scheduler tweaks, a background service that stops running — is
judged today by how *busy* the machine looks rather than by how much it gets
done. Utilisation is not throughput: a parked core reads as 0% busy and as
nothing missing.

Two numbers, because a CPU fails a game in two different ways.

*Single-core throughput* is the one a frame loop waits on. A game's main thread
is one thread, and a machine whose one thread is slow is a machine that stutters
however many cores it has.

*All-core throughput* is what everything else runs in — shader compilation, asset
streaming, the driver's own threads, and whatever the user left open. It is also
the only number that shows a core that has stopped participating: a part whose
scaling collapses from 8x to 4x has half its cores parked or thermally pinned,
and nothing else fpstune measures would say so.

**The workload is `zlib.compress` over a fixed random block.** Three properties
decide that choice and each of them was checked rather than assumed:

*It releases the GIL.* Measured here 2026-09-11: one thread 45.5 passes/s,
sixteen threads 361 passes/s — 7.94x on an eight-core part with SMT, which is
what an eight-core part should give. A workload that held the GIL would report
every machine as single-core.

*It is branch-heavy integer work with no dedicated instruction behind it.* A
hash would have been simpler and would have measured SHA-NI — a fixed-function
unit whose throughput says almost nothing about the core running a game loop.

*The input is seeded, not random.* `Random(seed).randbytes` gives the same block
on every machine and in every run, so the before and the after compress exactly
the same bytes. `os.urandom` would have put a different amount of work into each
side of the comparison and called the difference a result.

**Why threads and not processes.** The obvious answer to the GIL is
`multiprocessing`, and it is the wrong one here for a reason that has nothing to
do with performance: fpstune ships as a PyInstaller single executable and calls
`multiprocessing.freeze_support()` nowhere. In a frozen build, spawning is
implemented by re-running the executable — so a bench that spawned sixteen
workers would open sixteen copies of fpstune, each of which would open sixteen
more. Releasing the GIL inside the workload gets the same parallelism with none
of that.

**What this is not.** It is not a CPU score to compare against another machine's
— the interpreter's own overhead sits in every number, and zlib's build differs
between Python distributions. It is a repeatable figure on one machine, which is
exactly and only what a before/after comparison needs.
"""

from __future__ import annotations

import os
import random
import threading
import time
import zlib

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for

DEFAULT_BLOCK_KB = 1024
"""One megabyte a pass.

Large enough that the per-call overhead — the GIL release, the allocation, the
return trip into Python — is a small share of the pass, and small enough that
the working set stays in cache and this measures the core rather than the memory
subsystem, which `memory.py` already owns.
"""

DEFAULT_ITERATIONS = 12
"""Passes behind one sample. About a quarter of a second on the machine this was
written on, and a second or two on something much slower — short enough that the
bench is a fraction of a suite run either way."""

COMPRESSION_LEVEL = 1
"""The fastest level, deliberately.

The higher levels spend their time searching a larger window, which makes the
number increasingly about the last-level cache. Level 1 keeps the work in the
core.
"""

_SEED = 0xC9C5C0DE
"""One block, every machine, every run.

zlib's work depends on what it is compressing, so a fresh random block on each
side of a comparison would put a different amount of work into each side and
report the difference as a result.
"""

_INNER_PASSES = 3
"""Passes behind each reported sample, of which the best is kept.

Best-of rather than mean, and the reason is directional, exactly as in
`memory.py`: interference only ever makes a CPU pass slower. A sample that caught
another process's burst is not a fact about this processor, and averaging it in
widens the run-to-run spread — the noise floor every verdict is measured against
— without adding information.
"""

_SLOW_PASS_SECONDS = 0.5
"""A pessimistic cost for one compression pass, used only for the deadline.

Twenty times what this machine takes. Generous on purpose: this figure decides
only when to call a bench hung, and a deadline a slow-but-working machine trips
turns its measurement into a missing one.
"""


def _block(block_kb: int) -> bytes:
    """The bytes every pass compresses. Seeded, so it is the same bytes."""
    return random.Random(_SEED).randbytes(block_kb * 1024)


def _compress_repeatedly(payload: bytes, iterations: int) -> None:
    """The unit of work, and the only thing being timed."""
    for _ in range(iterations):
        zlib.compress(payload, COMPRESSION_LEVEL)


class CpuBench:
    """Single-thread and all-thread compression throughput, in passes a second."""

    key = "cpu"
    label = "CPU throughput"
    requires = "nothing — it works the processor it is measuring"

    def __init__(
        self,
        *,
        block_kb: int = DEFAULT_BLOCK_KB,
        iterations: int = DEFAULT_ITERATIONS,
        threads: int | None = None,
    ) -> None:
        if block_kb <= 0:
            raise ValueError("block_kb has to be positive to have anything to compress")
        if iterations <= 0:
            raise ValueError("iterations has to be positive to time anything")
        self.block_kb = block_kb
        self.iterations = iterations
        # Derived from the machine, never a constant: a four-thread laptop and a
        # thirty-two-thread desktop are the same code and different answers (C1).
        self.threads = threads if threads is not None else (os.cpu_count() or 1)
        if self.threads < 1:
            raise ValueError("threads has to be at least one to measure anything")

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def timeout_seconds(self, repeats: int) -> float:
        """Derived from the passes it runs, single-threaded and all-threaded.

        The all-thread leg is counted as one thread's worth of wall clock rather
        than as every thread's work added up: the threads run at the same time,
        so the run takes as long as the slowest of them and not as long as their
        sum. Counting the sum would hand a thirty-two-thread machine a deadline
        thirty-two times too generous, which is a deadline that never fires.
        """
        per_leg = self.iterations * _SLOW_PASS_SECONDS * _INNER_PASSES
        return deadline_for(2 * per_leg, repeats)

    def _throughput(self, payload: bytes, threads: int) -> float:
        """Passes a second with this many threads working at once.

        Wall clock around the whole group rather than each thread's own elapsed
        time. What is being measured is what the machine got through, and the
        machine was busy from the first thread starting to the last one
        finishing — a per-thread average would flatter a machine whose threads
        did not overlap.
        """
        if threads == 1:
            started = time.perf_counter()
            _compress_repeatedly(payload, self.iterations)
            elapsed = time.perf_counter() - started
        else:
            workers = [
                threading.Thread(
                    target=_compress_repeatedly,
                    args=(payload, self.iterations),
                    name=f"cpu-bench-{index}",
                )
                for index in range(threads)
            ]
            started = time.perf_counter()
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            elapsed = time.perf_counter() - started

        if elapsed <= 0:
            return 0.0
        return (self.iterations * threads) / elapsed

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()
        payload = _block(self.block_kb)

        # One unmeasured pass first, for the same reason `memory.py` takes one:
        # the first call pays for zlib's own allocations and for the pages the
        # allocator has not faulted in yet. Left in, it lands entirely in the
        # first repeat and widens the spread the noise floor is drawn from.
        _compress_repeatedly(payload, 1)

        single: list[float] = []
        multi: list[float] = []

        for _ in range(repeats):
            single.append(max(self._throughput(payload, 1) for _ in range(_INNER_PASSES)))
            multi.append(max(self._throughput(payload, self.threads) for _ in range(_INNER_PASSES)))

        # Derived from the two readings above and therefore not a reading of its
        # own: comparing it before and after would say nothing the pair does not
        # already say, and a third number that moves whenever either of the
        # other two does is how a panel comes to look like three findings.
        best_single = max(single)
        scaling = (max(multi) / best_single) if best_single > 0 else 0.0

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                # The number a frame loop waits on: a game's main thread is one
                # thread, and no core count rescues a slow one.
                "cpu_single_core_ops": BenchReading(
                    "cpu_single_core_ops", single, "passes/s", higher_is_better=True
                ),
                # Everything else the machine is doing while the frame is drawn
                # — and the only reading here that notices a core that has
                # stopped participating.
                "cpu_multi_core_ops": BenchReading(
                    "cpu_multi_core_ops", multi, "passes/s", higher_is_better=True
                ),
            },
            detail={
                "threads": self.threads,
                "block_kb": self.block_kb,
                "iterations": self.iterations,
                "compression_level": COMPRESSION_LEVEL,
                "scaling": round(scaling, 2),
                "scaling_note": (
                    "all-thread over single-thread — well under the thread count "
                    "means cores parked, thermally pinned, or busy with something else"
                ),
                "note": "one machine's repeatable figure, not a score to compare against another",
            },
            duration_seconds=time.perf_counter() - started,
        )
