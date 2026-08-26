"""Measure what a scan costs, so an optimization can be proved rather than claimed.

Run the same command before and after a change. Nothing about scan performance
gets committed on the strength of a green test suite: a batch that silently
stopped batching passes every test it has, because the per-setting fallback
produces the same values. Twice this codebase shipped a batch that was dead in
production — the adapter snapshot that parsed to nothing (#31), and the
prefetchers that copied an empty context into their worker threads — and in both
cases the suite was green throughout. Only the process count showed it.

    python scripts/measure_scan.py                  three runs, human-readable
    python scripts/measure_scan.py --repeat 5
    python scripts/measure_scan.py --json before.json
    python scripts/measure_scan.py --no-batch       batches off, for comparison

Four numbers, and the last one is what catches a dead batch:

  discovery    building the registry: what the first screen waits on
  scan (cold)  a first detection pass: what a user actually sits through
  background   how long until everything that pass started has finished
  processes    subprocesses spawned. A batch's whole purpose is to lower this,
               and it is the only metric that distinguishes "the batch ran" from
               "the batch was skipped and every setting ran its own command".

Three ways this harness flattered the result before it stopped:

* it closed the process counter when ``detect_all`` returned, missing the daemon
  threads a scan starts. It counted 24 where 57 was real, and made a change that
  removed 32 processes look like it removed 6.
* it reported only the warm scan. Cleanup sizes cache for five minutes, so 33
  folder walks were invisible from the second pass onward.
* it took the median discovery across runs. GPU and OS detection cache at module
  level with no expiry, so later runs re-use the first one's answers — a median
  of three read 0.94 s against a true cold 1.75 s. Discovery is now reported
  from the first run alone.

Each of those made the tool look better than the machine was, which is the only
direction a measurement is dangerous in.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class ProcessCounter:
    """Count every subprocess a block of work spawns, by executable.

    Wraps ``subprocess.Popen`` rather than ``run``, because everything —
    ``run``, ``check_output``, the executors' own helpers — goes through it, and
    a counter that wrapped only ``run`` would miss whatever moved off it later.
    """

    def __init__(self) -> None:
        self.by_exe: Counter[str] = Counter()
        self._real = subprocess.Popen

    def __enter__(self) -> ProcessCounter:
        counter = self

        class CountingPopen(counter._real):  # type: ignore[misc,valid-type]
            def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
                name = args[0] if isinstance(args, (list, tuple)) and args else str(args)
                counter.by_exe[Path(str(name)).name.lower()] += 1
                super().__init__(args, *rest, **kwargs)

        subprocess.Popen = CountingPopen  # type: ignore[misc]
        return self

    def __exit__(self, *_exc: object) -> None:
        subprocess.Popen = self._real  # type: ignore[misc]

    @property
    def total(self) -> int:
        return sum(self.by_exe.values())


def measure_once(*, use_batch: bool) -> dict[str, Any]:
    """Discovery, then a cold scan, then a warm one, counting what each spawns.

    Both scans matter and they measure different things. The **cold** one is what
    a user actually sits through: nothing is cached, so every background
    computation the scan kicks off starts here. The **warm** one is the steady
    state a re-detect hits, and it is the number that shows whether the caches
    are doing their job.

    Reporting only the warm scan flatters the tool badly: cleanup sizes cache for
    five minutes, so the 33 folder walks they trigger are invisible from the
    second scan onward and were entirely missing from this harness's first
    baseline.
    """
    from fpstune.settings.detection import DetectionEngine
    from fpstune.settings.registry import SettingsRegistry

    with ProcessCounter() as discovery_procs:
        started = time.perf_counter()
        registry = SettingsRegistry(discover_dynamic=True)
        settings = registry.get_all()
        discovery_seconds = time.perf_counter() - started

    engine = DetectionEngine()

    # The counter stays open across the settle, and that is the point. A cold
    # scan returns quickly and then keeps working: cleanup sizing runs in daemon
    # threads so the UI can show "calculating" instead of blocking. Closing the
    # counter when detect_all returns therefore misses almost every process the
    # scan is responsible for — measured, it missed 33 of them — and made a
    # change that removed 32 of those look like it removed 6.
    with ProcessCounter() as cold_procs:
        started = time.perf_counter()
        engine.detect_all(settings)
        cold_seconds = time.perf_counter() - started
        _await_background_work()
        settle_seconds = time.perf_counter() - started

    with ProcessCounter() as warm_procs:
        started = time.perf_counter()
        results = engine.detect_all(settings)
        warm_seconds = time.perf_counter() - started

    detected = sum(1 for r in results.values() if r.is_applicable and r.value is not None)

    return {
        "batch": use_batch,
        "settings": len(settings),
        "detected": detected,
        "discovery_seconds": round(discovery_seconds, 3),
        "cold_seconds": round(cold_seconds, 3),
        "settle_seconds": round(settle_seconds, 3),
        "scan_seconds": round(warm_seconds, 3),
        "discovery_processes": discovery_procs.total,
        "cold_processes": cold_procs.total,
        "scan_processes": warm_procs.total,
        "cold_processes_by_exe": dict(cold_procs.by_exe.most_common()),
        "scan_processes_by_exe": dict(warm_procs.by_exe.most_common()),
    }


def _await_background_work(timeout: float = 180.0) -> None:
    """Block until the scan's own daemon threads have finished.

    Named rather than slept on: a fixed sleep is either too short (and the next
    measurement races unfinished work) or too long (and every run pays for it).
    """
    import threading

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        alive = [
            t
            for t in threading.enumerate()
            if t.is_alive() and ("cleanup" in t.name or t.name.startswith("fpstune"))
        ]
        if not alive:
            return
        time.sleep(0.2)


def _summarise(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Median over the runs. Median, not mean: one run that hit a slow WMI
    query should not move the number the next change is judged against."""

    def median_of(key: str) -> float:
        return round(statistics.median(run[key] for run in runs), 3)

    return {
        "runs": len(runs),
        "settings": runs[0]["settings"],
        "detected": runs[0]["detected"],
        # Discovery is taken from the first run alone, never the median. GPU and
        # OS detection cache at module level with no expiry (deliberately — they
        # cannot change while the process lives), so runs two and three re-use
        # run one's answers and discovery looks about a third of its real cost.
        # A median over three runs reported 0.94s against a true cold 1.75s.
        "discovery_seconds": runs[0]["discovery_seconds"],
        "discovery_processes": runs[0]["discovery_processes"],
        "cold_seconds": median_of("cold_seconds"),
        "settle_seconds": median_of("settle_seconds"),
        "scan_seconds": median_of("scan_seconds"),
        "cold_processes": int(median_of("cold_processes")),
        "scan_processes": int(median_of("scan_processes")),
        "cold_processes_by_exe": runs[0]["cold_processes_by_exe"],
        "scan_processes_by_exe": runs[-1]["scan_processes_by_exe"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=3, help="runs to take the median of")
    parser.add_argument("--json", type=Path, help="write the summary here for a before/after diff")
    parser.add_argument(
        "--no-batch",
        action="store_true",
        help="disable the per-scan batches, to show what they are worth",
    )
    args = parser.parse_args()

    if args.no_batch:
        # Neutralise the scan cache: without it every batched lookup falls back
        # to its own subprocess, which is precisely the cost being measured.
        from fpstune.settings.executors import ps_batch

        ps_batch.init_scan_cache = lambda: ({}, None)  # type: ignore[assignment]
        ps_batch.reset_scan_cache = lambda _token: None  # type: ignore[assignment]
        ps_batch._get_cache = lambda: None  # type: ignore[assignment]

    runs = [measure_once(use_batch=not args.no_batch) for _ in range(args.repeat)]
    summary = _summarise(runs)

    label = "batches OFF" if args.no_batch else "batches on"
    print(f"\nscan baseline ({label}, median of {summary['runs']})")
    print(f"  settings          {summary['settings']} ({summary['detected']} detected)")
    print(
        f"  discovery         {summary['discovery_seconds']:.2f}s"
        f"   {summary['discovery_processes']} processes   (first run only, see below)"
    )
    print(f"  scan (cold)       {summary['cold_seconds']:.2f}s   blocking")
    print(
        f"  + background      {summary['settle_seconds']:.2f}s   until everything it "
        f"started has finished, {summary['cold_processes']} processes in total"
    )
    print(
        f"  scan (warm)       {summary['scan_seconds']:.2f}s"
        f"   {summary['scan_processes']} processes"
    )
    print("  cold scan processes by executable:")
    for exe, count in summary["cold_processes_by_exe"].items():
        print(f"    {exe:24} {count}")

    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\n  written to {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
