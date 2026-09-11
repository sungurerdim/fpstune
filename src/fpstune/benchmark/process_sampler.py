"""What the machine is spending on itself while nobody is playing.

The largest gap in `sources.py` was also the dullest: forty-one settings claim a
`cpu_usage` change, nineteen claim `ram_saved`, one claims `disk_io`, and the
reason none of them could be checked was *"no sampler for process CPU time"*.
Not a hard instrument — Windows has published these counters since NT — just one
nobody had written.

This is that sampler. Three quantities, each read from the class that owns it:

| Reading | Counter | Why this one |
|---|---|---|
| `cpu_usage` | `_Total` minus `Idle`, over the machine's own capacity | the share of the machine background work is taking |
| `ram_available_mb` | `PerfOS_Memory.AvailableMBytes` | memory the game can still have |
| `disk_io` | `_Total.IODataBytesPersec` | bytes a second everything else is moving |

Four decisions.

*Available memory, not working set.* `ram_saved` is a claim that goes up when the
setting works, so it is measured by a number that goes up. Summing every
process's working set would also double-count shared pages, and it is the wrong
direction besides — a verdict built on it would report freed memory as a loss.

*Idle is subtracted rather than trusted.* The `_Total` instance of the process
class includes the Idle process, so on this sixteen-thread machine an idle
reading is about 1600, not 0. Reporting that as "1653% CPU" is not a rounding
error, it is reading the wrong quantity.

*Whichever known game is running is sampled beside the machine.* Its cost is
published under its own names — `game_cpu_usage`, `game_working_set_mb` — and
never mixed into the machine-wide figures. A run with a game open and one
without are different conditions, and `compare_runs` reports the game's readings
as unpaired rather than pretending the two are the same measurement.

*One PowerShell process for the whole window.* The loop is inside the script, so
a four-second sample costs one start-up rather than four. WMI class and property
names are the same on every Windows — this reads `Win32_PerfFormattedData_*`
rather than a `typeperf` counter path for exactly that reason (C4's evidence
carve-out: a counter *path* is translated on a localised machine, a class name is
not).
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.settings.executors.game_processes import (
    GAME_LABELS,
    GAME_PROCESSES,
    game_is_running,
)
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_WINDOW_SAMPLES = 4
"""Readings per repeat, one a second.

Four is enough for a background spike to show up as one sample out of four
rather than as the whole window, and short enough that three repeats of it are
twelve seconds rather than a minute.
"""

SAMPLE_INTERVAL_MS = 1000

_PER_SAMPLE_SECONDS = 2.5
"""What one second of sampling costs on a slow machine, deadline-wise.

A WMI query against the process class is not free — it walks every process — so
the second of sleep is the smaller half of each sample.
"""

BYTES_PER_MB = 1024.0 * 1024.0

_SAFE_PROCESS_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
"""What may be interpolated into a WQL filter.

The names come from fpstune's own table rather than from a user, and the
allowlist is here so that stays true after somebody adds an entry: a name with a
quote in it would end the literal and continue the query.
"""

NOTHING_SAMPLED = "the performance counters returned nothing to sample"


def running_game() -> str | None:
    """Which known game is running, or None.

    The first match in the table's own order. Two known games running at once is
    not a case worth splitting readings over — it is a machine nobody is
    benchmarking.
    """
    for game in GAME_PROCESSES:
        if game_is_running(game):
            return game
    return None


def build_script(samples: int, process_names: tuple[str, ...] = ()) -> str:
    """The whole sampling window as one PowerShell expression.

    `Name LIKE 'x%'` rather than `Name = 'x'`: the performance class disambiguates
    two processes with one image name by appending `#1`, so an exact match loses
    the second copy of a game that launched a child under its own name.
    """
    clauses = ["Name='_Total'", "Name='Idle'"]
    for name in process_names:
        if not _SAFE_PROCESS_NAME.match(name):
            logger.warning("Skipping process name %r: it cannot go into a WQL filter", name)
            continue
        clauses.append(f"Name LIKE '{name}%'")
    where = " OR ".join(clauses)

    return (
        f"1..{int(samples)} | ForEach-Object {{ "
        "$rows=@(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process "
        f'-Filter "{where}"); '
        "$total=@($rows | Where-Object { $_.Name -eq '_Total' })[0]; "
        "$idle=@($rows | Where-Object { $_.Name -eq 'Idle' })[0]; "
        "$game=@($rows | Where-Object { $_.Name -ne '_Total' -and $_.Name -ne 'Idle' }); "
        "$mem=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory; "
        "[pscustomobject]@{"
        "total_cpu=[double]$total.PercentProcessorTime;"
        "idle_cpu=[double]$idle.PercentProcessorTime;"
        "total_io=[double]$total.IODataBytesPersec;"
        "total_ws=[double]$total.WorkingSetPrivate;"
        "available_mb=[double]$mem.AvailableMBytes;"
        "game_cpu=[double](($game | Measure-Object PercentProcessorTime -Sum).Sum);"
        "game_ws=[double](($game | Measure-Object WorkingSetPrivate -Sum).Sum);"
        "game_instances=$game.Count"
        "}; "
        f"if($_ -lt {int(samples)}){{ Start-Sleep -Milliseconds {SAMPLE_INTERVAL_MS} }} }}"
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def busy_percent(total_cpu: float, idle_cpu: float, logical_processors: int | None) -> float:
    """The share of the machine that is doing something.

    `_Total` counts the Idle process too, so the busy share is what is left after
    it, over the machine's own capacity — a hundred per cent per logical
    processor. When the processor count is unknown the measured total stands in
    for the capacity, which is what it is: the same sixteen hundred, arrived at
    by measurement instead of by counting cores.
    """
    capacity = (logical_processors or 0) * 100.0
    if capacity <= 0:
        capacity = max(total_cpu, 1.0)
    busy = (total_cpu - idle_cpu) / capacity * 100.0
    return max(0.0, min(busy, 100.0))


class ProcessSamplerBench:
    """Background CPU, free memory and disk traffic, sampled once a second."""

    key = "process_sampler"
    label = "Background load"
    requires = "nothing — it reads counters Windows keeps anyway"

    def __init__(self, *, window_samples: int = DEFAULT_WINDOW_SAMPLES) -> None:
        if window_samples < 1:
            raise ValueError("a sampling window needs at least one sample")
        self.window_samples = int(window_samples)

    def timeout_seconds(self, repeats: int) -> float:
        return deadline_for(_PER_SAMPLE_SECONDS * self.window_samples, repeats)

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def sample_window(self, process_names: tuple[str, ...]) -> tuple[list[dict[str, Any]], str]:
        """One window of per-second rows, or an empty list and the reason."""
        # The timeout allows the sleeps plus a slow machine's query time, so a
        # window that is merely slow is not reported as a machine that refused.
        budget = int(self.window_samples * _PER_SAMPLE_SECONDS + 15)
        rows, reason = query_rows(
            build_script(self.window_samples, process_names),
            timeout=budget,
            component="benchmark.process_sampler",
        )
        if reason:
            return [], reason
        if not rows:
            return [], NOTHING_SAMPLED
        return rows, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()
        game = running_game()
        names = GAME_PROCESSES.get(game or "", ())
        logical = os.cpu_count()

        cpu: list[float] = []
        available: list[float] = []
        disk: list[float] = []
        game_cpu: list[float] = []
        game_ws: list[float] = []
        series: list[dict[str, Any]] = []

        for _ in range(repeats):
            rows, reason = self.sample_window(names)
            if not rows:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=reason,
                    duration_seconds=time.perf_counter() - started,
                )

            window = [
                busy_percent(
                    float(row.get("total_cpu") or 0.0),
                    float(row.get("idle_cpu") or 0.0),
                    logical,
                )
                for row in rows
            ]
            cpu.append(_mean(window))
            available.append(_mean([float(row.get("available_mb") or 0.0) for row in rows]))
            disk.append(_mean([float(row.get("total_io") or 0.0) for row in rows]))
            series.append({"cpu_percent": [round(value, 3) for value in window]})

            if game is not None and any(int(row.get("game_instances") or 0) for row in rows):
                game_cpu.append(
                    _mean(
                        [
                            min(float(row.get("game_cpu") or 0.0) / max(logical or 1, 1), 100.0)
                            for row in rows
                        ]
                    )
                )
                game_ws.append(
                    _mean([float(row.get("game_ws") or 0.0) / BYTES_PER_MB for row in rows])
                )

        readings = {
            "cpu_usage": BenchReading("cpu_usage", cpu, "%"),
            "ram_available_mb": BenchReading("ram_available_mb", available, "MB"),
            "disk_io": BenchReading("disk_io", disk, "bytes/s"),
        }
        if game_cpu:
            # The game's own cost, never folded into the machine-wide figures: a
            # run taken with a game open is a different condition, and a
            # comparison that mixed the two would credit closing the game to
            # whatever setting was applied in between.
            readings["game_cpu_usage"] = BenchReading(
                "game_cpu_usage", game_cpu, "%", higher_is_better=False
            )
            readings["game_working_set_mb"] = BenchReading(
                "game_working_set_mb", game_ws, "MB", higher_is_better=False
            )

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail={
                "window_samples": self.window_samples,
                "logical_processors": logical,
                "game": game,
                "game_label": GAME_LABELS.get(game or "", ""),
                "samples": series,
            },
            duration_seconds=time.perf_counter() - started,
        )
