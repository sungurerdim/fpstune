"""How much video memory is actually in use, on whichever GPU is doing the work.

Eleven settings claim a `vram_mb` change and none of them could be checked:
*"no sampler for video memory"*. Windows has had one since the WDDM 2.x
counters shipped — `GPU Adapter Memory`, per adapter, dedicated and shared — and
it needs no vendor SDK, which is what makes it the vendor-neutral answer C10
asks for.

**Read as a WMI class rather than as a counter path.** The survey verified that
`typeperf "\\GPU Adapter Memory(*)\\Dedicated Usage"` returns English counter
names even on this Turkish install, and both paths were run here: the counter
path and `Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory`
reported the same 939376640 bytes for the same adapter in the same minute. The
class is used anyway, for two reasons that are facts rather than preferences:

* a WMI class name and its properties are never translated, while a counter
  *path* is — the English name working here is a property of this install's
  Perflib, not a guarantee about the next machine;
* the documented escape from a translated path is the counter *index*, and that
  escape does not exist for this tool: `typeperf "\\10914(*)\\10918"`, built
  from the indices in `Perflib\\009` on this machine, answered `Error: No valid
  counters.` The index has to be translated back through PDH first, which
  `typeperf` will not do.

**The busiest adapter is the reading, not the sum.** A laptop reports three
adapter instances — the discrete GPU, the integrated one, and the render-only
device — and only one of them is drawing the game. Adding them together would
answer a question nobody asked, and averaging would dilute the one that matters.
Every instance is in `detail`.

**Vendor coverage is stated rather than assumed (C10).** Verified here on an
NVIDIA adapter, where the counter is populated. Whether AMD and Intel adapters
populate `Dedicated Usage` is **not verified** — the integrated adapter on this
machine reports 0, which is what an idle iGPU with no dedicated memory would
report either way, so it settles nothing. On a machine where no adapter reports
the counter, this bench says so rather than reporting zero megabytes in use.
"""

from __future__ import annotations

import time
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.utils.logger import get_logger

logger = get_logger()

BYTES_PER_MB = 1024.0 * 1024.0

_QUERY_SECONDS = 3.0

NO_ADAPTER = (
    "no adapter here reports the Windows GPU memory counter, so there is "
    "nothing to read — the counter arrives with the display driver"
)

# Never-translated class and property names. The instance `Name` is the
# adapter's LUID, which is Windows' own identifier for it and is discovered at
# runtime rather than named here (C9).
SCRIPT = (
    "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory "
    "-ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{"
    "adapter=[string]$_.Name;"
    "dedicated=[double]$_.DedicatedUsage;"
    "shared=[double]$_.SharedUsage;"
    "committed=[double]$_.TotalCommitted"
    "} }"
)


_counter_present: tuple[bool, str] | None = None
"""Whether this machine publishes the counter at all, asked once.

A display driver does not start publishing a counter halfway through a session,
and `benches.catalogue()` asks every bench whether it can run each time a panel
opens — so without this, opening the benchmarks tab would cost a PowerShell
start-up for an answer that cannot have changed (C7).
"""


def forget_counter_probe() -> None:
    """Drop the cached answer. For tests, and after a driver install."""
    global _counter_present
    _counter_present = None


class GpuMemoryBench:
    """Dedicated video memory in use, from the adapter using the most of it."""

    key = "gpu_memory"
    label = "Video memory in use"
    requires = "a display adapter whose driver publishes the Windows GPU counters"

    def timeout_seconds(self, repeats: int) -> float:
        return deadline_for(_QUERY_SECONDS, repeats)

    def is_available(self) -> tuple[bool, str]:
        # Asked by running the query rather than by inspecting the GPU: the
        # counter comes from the display driver, so a card fpstune recognises
        # perfectly well may still publish nothing.
        global _counter_present
        if _counter_present is None:
            _, reason = self.sample()
            _counter_present = (not reason, reason)
        return _counter_present

    def sample(self) -> tuple[list[dict[str, Any]], str]:
        """Every adapter instance, or an empty list and the reason."""
        rows, reason = query_rows(SCRIPT, timeout=20, component="benchmark.gpu_memory")
        if reason:
            return [], reason
        if not rows:
            return [], NO_ADAPTER
        return rows, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        used: list[float] = []
        shared: list[float] = []
        adapters: list[dict[str, Any]] = []

        for _ in range(repeats):
            rows, reason = self.sample()
            if not rows:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=reason,
                    duration_seconds=time.perf_counter() - started,
                )
            adapters = [
                {
                    "adapter": str(row.get("adapter") or ""),
                    "dedicated_mb": round(float(row.get("dedicated") or 0.0) / BYTES_PER_MB, 2),
                    "shared_mb": round(float(row.get("shared") or 0.0) / BYTES_PER_MB, 2),
                    "committed_mb": round(float(row.get("committed") or 0.0) / BYTES_PER_MB, 2),
                }
                for row in rows
            ]
            busiest = max(adapters, key=lambda row: row["dedicated_mb"])
            used.append(busiest["dedicated_mb"])
            shared.append(busiest["shared_mb"])

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                "vram_mb": BenchReading("vram_mb", used, "MB"),
                # Shared memory is system RAM the GPU is borrowing, which is a
                # different resource and gets its own name rather than being
                # added to the dedicated figure.
                "gpu_shared_mb": BenchReading(
                    "gpu_shared_mb", shared, "MB", higher_is_better=False
                ),
            },
            detail={"adapters": adapters},
            duration_seconds=time.perf_counter() - started,
        )
