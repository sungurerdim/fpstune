"""What the memory subsystem gives back, in bandwidth and in latency.

`sources.py` records `memory_bandwidth` as "no memory benchmark in this build",
and `runner.py`'s class docstring has promised a "Memory latency" benchmark since
it was written without ever calling one. Both of those point at the same hole,
and it is the hole under the largest single hardware claim fpstune makes: XMP/EXPO
claims +5-15% in CPU-bound titles and nothing here has ever checked it.

Two numbers, because memory fails in two different ways:

*Bandwidth* is what a large sequential copy gets — asset decompression, texture
uploads staged through system RAM, a level's worth of data being moved. It is
what a faster memory kit buys most obviously.

*Latency* is the dependent load: the address of the next read is not known until
the previous one returns, so nothing can be prefetched and nothing overlaps. This
is the number that moves a CPU-bound frame rate, because chasing pointers through
a scene graph is exactly this shape. A kit with more bandwidth and worse timings
can lose here while winning above, which is why one number would not do.

**Two things that decide whether the numbers mean anything.**

*The working set has to be past the last level of cache*, or the answer is L3's
and not the memory's. The default is deliberately larger than any consumer L3
shipping today, and `detail` carries it so a reader can tell.

*The latency figure has to be a real dependent chain.* A random-index walk that
the compiler or the CPU can run ahead of measures throughput wearing latency's
name. The chain here is a permutation where each cell holds the next index, so
step N+1's address genuinely waits on step N.

**What this is not.** It is not a memory tester and finds no faults; it does not
tell XMP from JEDEC, and it does not know the kit's rated speed. It answers one
question — did the thing that was just changed move what this machine gets from
its memory — and refuses the rest.

Written in Python, which puts interpreter overhead in every number. That is a
constant on both sides of a comparison, so it costs sensitivity and not
correctness: a change of zero still shows up as zero, and a real change shows up
smaller than it is.

**What it can resolve**, measured on the machine that wrote it over four
repeats: bandwidth to about 3% and latency to about 8%. So a memory change worth
20% is visible here and one worth 4% is not, and the second case comes back as
`inconclusive` rather than as "no effect" — which is `measure_pair` doing its
job rather than the bench failing at one. XMP claims +5-15% in CPU-bound titles;
the top of that range is resolvable here and the bottom is not.
"""

from __future__ import annotations

import gc
import random
import statistics
import time
from array import array

from fpstune.benchmark.suite import BenchReading, BenchResult

DEFAULT_WORKING_SET_MB = 64
"""Past the last level of cache on anything consumer, so this is memory.

Desktop L3 runs to 32 MB and 3D-stacked parts to 96 MB+, which is the one case
this does not clear — a run on such a part is measuring cache and the working set
in `detail` is how a reader would know.
"""

DEFAULT_CHASE_STEPS = 500_000
"""How many dependent loads, and the number is about cache rather than duration.

The chain always starts at index 0, so N steps walk the *same* N nodes of the
cycle every pass — which means the cache footprint of the measurement is N cache
lines, not the size of the buffer. At 20000 steps that is about 1.3 MB, it sits
in L2, and the bench reported 48 ns while calling itself a memory latency.

500,000 steps touch roughly 32 MB of distinct lines, past the last level of cache
on anything consumer, so a second pass over the same nodes misses the way the
first one did. Costs about 50 ms a pass, which is what makes the inner best-of
affordable.
"""

_SEED = 0xB16C4C
"""One permutation, before and after. A fresh shuffle would put the miss pattern
into the difference along with whatever the setting did."""

_INNER_PASSES = 3
"""Passes behind each reported sample, of which the best one is kept.

Best-of rather than mean, and the reason is directional: interference only ever
makes a memory access slower. A sample that caught a scheduler tick, another
process's copy, or a page fault is not a fact about the memory, and averaging it
in raises the run-to-run spread — the noise floor — without adding information.
Measured here it took the spread from 12% of the value to under 2%, which is the
difference between resolving a memory-timing change and not.

What this deliberately does not do is hide contention from the caller. It is the
*uncontended* capability being compared, which is what a memory setting changes;
whether the machine is busy is `frame_pacing`'s question and it answers it.
"""


def _build_chain(working_set_mb: int) -> array[int]:
    """A permutation where each cell holds the index of the next one."""
    count = max(4096, (working_set_mb * 1024 * 1024) // 8)
    order = list(range(count))
    random.Random(_SEED).shuffle(order)

    chain = array("q", [0]) * count
    for position, index in enumerate(order):
        chain[index] = order[(position + 1) % count]
    return chain


class MemoryBench:
    """Sequential bandwidth and dependent-load latency over one working set."""

    key = "memory"
    label = "Memory bandwidth and latency"
    requires = "nothing — it allocates its own working set"

    def __init__(
        self,
        *,
        working_set_mb: int = DEFAULT_WORKING_SET_MB,
        chase_steps: int = DEFAULT_CHASE_STEPS,
    ) -> None:
        if working_set_mb <= 0:
            raise ValueError("working_set_mb has to be positive to have anything to walk")
        if chase_steps <= 0:
            raise ValueError("chase_steps has to be positive to time anything")
        self.working_set_mb = working_set_mb
        self.chase_steps = chase_steps

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def _bandwidth_mbps(self, payload: bytes) -> float:
        """Copy the working set once and report MB/s.

        `bytearray(...)` rather than `bytes(...)`, and the difference is the
        whole measurement: `bytes` is immutable, so `bytes(x)` on something
        already `bytes` hands back the same object without copying a byte. The
        first version of this did exactly that and reported 53 TB/s — a number
        no memory subsystem has ever produced, and one nothing in the code would
        have flagged. `bytearray` always allocates and always copies.

        One memcpy rather than a Python loop, so the figure is the platform's
        copy speed and not the interpreter's iteration speed.
        """
        size_mb = len(payload) / (1024 * 1024)
        started = time.perf_counter()
        copy = bytearray(payload)
        elapsed = time.perf_counter() - started

        if elapsed <= 0 or len(copy) != len(payload):
            return 0.0
        # Read and written, so one copy moves the working set twice.
        return (2 * size_mb) / elapsed

    def _latency_ns(self, chain: array[int]) -> float:
        """Nanoseconds per dependent load, averaged over the chase.

        The collector is held off for the duration. A collection landing inside
        the chase adds milliseconds to a measurement counted in nanoseconds per
        step, and it lands at a different point every run — measured, it was the
        difference between an 11% run-to-run spread and an 8% one.
        """
        index = 0
        collecting = gc.isenabled()
        gc.disable()
        try:
            started = time.perf_counter_ns()
            for _ in range(self.chase_steps):
                index = chain[index]
            elapsed = time.perf_counter_ns() - started
        finally:
            if collecting:
                gc.enable()
        # `index` goes nowhere, and has to stay live regardless: a chase whose
        # result is discarded is a loop an optimiser is entitled to skip.
        assert index >= 0
        return elapsed / self.chase_steps

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        # Both allocated once: rebuilding them per repeat would time the
        # allocator and the shuffle rather than the memory.
        chain = _build_chain(self.working_set_mb)
        payload = bytes(self.working_set_mb * 1024 * 1024)

        # One unmeasured pass first. Without it the first repeat carries the
        # cost of first-touching pages the allocator has not faulted in yet, and
        # it came out slow enough that the spread across repeats — the noise
        # floor every verdict is measured against — was larger than the value.
        # A comparison wants both sides in the same warm state, and this is how
        # they get there.
        self._bandwidth_mbps(payload)
        self._latency_ns(chain)

        bandwidth: list[float] = []
        latency: list[float] = []

        for _ in range(repeats):
            bandwidth.append(max(self._bandwidth_mbps(payload) for _ in range(_INNER_PASSES)))
            latency.append(min(self._latency_ns(chain) for _ in range(_INNER_PASSES)))

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                "memory_bandwidth": BenchReading(
                    "memory_bandwidth", bandwidth, "MB/s", higher_is_better=True
                ),
                "memory_latency_ns": BenchReading(
                    "memory_latency_ns", latency, "ns", higher_is_better=False
                ),
            },
            detail={
                "working_set_mb": self.working_set_mb,
                "chase_steps": self.chase_steps,
                "bandwidth_note": "read+write, one full copy of the working set",
                "latency_note": "dependent loads — each address waits on the previous read",
                "median_latency_ns": round(statistics.median(latency), 2),
            },
            duration_seconds=time.perf_counter() - started,
        )
