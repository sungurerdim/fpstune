"""DPC (Deferred Procedure Call) latency benchmark for fpstune.

Measures system timer resolution and interrupt latency to evaluate
the impact of timer tweaks (HPET, dynamic tick, timer resolution).

DPC latency affects:
- Audio (crackling/popping)
- Input latency
- Frame pacing consistency
"""

from __future__ import annotations

import ctypes
import logging
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fpstune.benchmark.result_store import ResultStore
from fpstune.utils.config import get_config_dir


@dataclass
class DpcStats:
    """DPC latency statistics."""

    # Timer resolution
    timer_resolution_ns: int = 0  # Current timer resolution in nanoseconds
    timer_resolution_ms: float = 0.0  # Current timer resolution in ms

    # Sleep accuracy measurements
    sample_count: int = 0
    sleep_accuracy_avg_us: float = 0.0  # Average sleep overshoot in microseconds
    sleep_accuracy_max_us: float = 0.0  # Maximum sleep overshoot
    sleep_accuracy_stdev_us: float = 0.0

    # Timing jitter
    timing_jitter_avg_us: float = 0.0
    timing_jitter_max_us: float = 0.0

    # Performance counter stats
    qpc_resolution_ns: float = 0.0  # QueryPerformanceCounter resolution

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timer_resolution_ns": self.timer_resolution_ns,
            "timer_resolution_ms": self.timer_resolution_ms,
            "sample_count": self.sample_count,
            "sleep_accuracy_avg_us": self.sleep_accuracy_avg_us,
            "sleep_accuracy_max_us": self.sleep_accuracy_max_us,
            "sleep_accuracy_stdev_us": self.sleep_accuracy_stdev_us,
            "timing_jitter_avg_us": self.timing_jitter_avg_us,
            "timing_jitter_max_us": self.timing_jitter_max_us,
            "qpc_resolution_ns": self.qpc_resolution_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DpcStats:
        """Create from dictionary."""
        return cls(
            timer_resolution_ns=data.get("timer_resolution_ns", 0),
            timer_resolution_ms=data.get("timer_resolution_ms", 0.0),
            sample_count=data.get("sample_count", 0),
            sleep_accuracy_avg_us=data.get("sleep_accuracy_avg_us", 0.0),
            sleep_accuracy_max_us=data.get("sleep_accuracy_max_us", 0.0),
            sleep_accuracy_stdev_us=data.get("sleep_accuracy_stdev_us", 0.0),
            timing_jitter_avg_us=data.get("timing_jitter_avg_us", 0.0),
            timing_jitter_max_us=data.get("timing_jitter_max_us", 0.0),
            qpc_resolution_ns=data.get("qpc_resolution_ns", 0.0),
        )


@dataclass
class DpcBenchmarkResult:
    """DPC latency benchmark result."""

    name: str
    timestamp: str
    stats: DpcStats
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "stats": self.stats.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DpcBenchmarkResult:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            timestamp=data["timestamp"],
            stats=DpcStats.from_dict(data["stats"]),
            notes=data.get("notes", ""),
        )


@dataclass
class DpcComparison:
    """Comparison between two DPC benchmarks."""

    before: DpcBenchmarkResult
    after: DpcBenchmarkResult

    resolution_improvement: float = 0.0
    accuracy_improvement: float = 0.0
    jitter_improvement: float = 0.0

    def __post_init__(self) -> None:
        """Calculate improvements."""
        # Timer resolution improvement (lower is better)
        if self.before.stats.timer_resolution_ms > 0:
            self.resolution_improvement = (
                (self.before.stats.timer_resolution_ms - self.after.stats.timer_resolution_ms)
                / self.before.stats.timer_resolution_ms
                * 100
            )

        # Sleep accuracy improvement (lower is better)
        if self.before.stats.sleep_accuracy_avg_us > 0:
            self.accuracy_improvement = (
                (self.before.stats.sleep_accuracy_avg_us - self.after.stats.sleep_accuracy_avg_us)
                / self.before.stats.sleep_accuracy_avg_us
                * 100
            )

        # Jitter improvement (lower is better)
        if self.before.stats.timing_jitter_avg_us > 0:
            self.jitter_improvement = (
                (self.before.stats.timing_jitter_avg_us - self.after.stats.timing_jitter_avg_us)
                / self.before.stats.timing_jitter_avg_us
                * 100
            )

    def format_report(self) -> str:
        """Format comparison as a report."""
        lines = [
            "",
            "=" * 60,
            "DPC LATENCY COMPARISON",
            "=" * 60,
            "",
            f"Before: {self.before.name} ({self.before.timestamp[:19]})",
            f"After:  {self.after.name} ({self.after.timestamp[:19]})",
            "",
            "-" * 60,
            f"{'Metric':<25} {'Before':>12} {'After':>12} {'Change':>10}",
            "-" * 60,
        ]

        # Timer resolution
        res_change = (
            f"{self.resolution_improvement:+.1f}%" if self.resolution_improvement != 0 else "="
        )
        lines.append(
            f"{'Timer Resolution (ms)':<25} {self.before.stats.timer_resolution_ms:>12.3f} "
            f"{self.after.stats.timer_resolution_ms:>12.3f} {res_change:>10}"
        )

        # Sleep accuracy
        acc_change = f"{self.accuracy_improvement:+.1f}%" if self.accuracy_improvement != 0 else "="
        lines.append(
            f"{'Sleep Accuracy Avg (us)':<25} {self.before.stats.sleep_accuracy_avg_us:>12.1f} "
            f"{self.after.stats.sleep_accuracy_avg_us:>12.1f} {acc_change:>10}"
        )
        lines.append(
            f"{'Sleep Accuracy Max (us)':<25} {self.before.stats.sleep_accuracy_max_us:>12.1f} "
            f"{self.after.stats.sleep_accuracy_max_us:>12.1f}"
        )

        # Jitter
        jitter_change = f"{self.jitter_improvement:+.1f}%" if self.jitter_improvement != 0 else "="
        lines.append(
            f"{'Timing Jitter Avg (us)':<25} {self.before.stats.timing_jitter_avg_us:>12.1f} "
            f"{self.after.stats.timing_jitter_avg_us:>12.1f} {jitter_change:>10}"
        )
        lines.append(
            f"{'Timing Jitter Max (us)':<25} {self.before.stats.timing_jitter_max_us:>12.1f} "
            f"{self.after.stats.timing_jitter_max_us:>12.1f}"
        )

        lines.append("-" * 60)

        # Summary
        avg_improvement = (
            self.resolution_improvement + self.accuracy_improvement + self.jitter_improvement
        ) / 3

        if avg_improvement > 10:
            lines.append(
                f"\nSignificant improvement! Timer responsiveness improved by {avg_improvement:.1f}%"
            )
        elif avg_improvement > 0:
            lines.append(f"\nTimer responsiveness improved by {avg_improvement:.1f}%")
        elif avg_improvement < -10:
            lines.append(f"\nWarning: Timer responsiveness degraded by {abs(avg_improvement):.1f}%")
        else:
            lines.append("\nNo significant change in timer responsiveness")

        return "\n".join(lines)


class DpcBenchmark:
    """DPC latency benchmark runner.

    Measures system timer precision and sleep accuracy to evaluate
    the effectiveness of timer-related optimizations.
    """

    def __init__(self, results_dir: Path | None = None) -> None:
        """Initialize DpcBenchmark.

        Args:
            results_dir: Directory to store results. Defaults to ~/.fpstune/dpc/
        """
        self._results_dir = results_dir or (get_config_dir() / "dpc")
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(__name__)
        self._store = ResultStore(self._results_dir, self._logger)

    def _get_timer_resolution(self) -> tuple[int, int, int]:
        """Get system timer resolution using NtQueryTimerResolution.

        Returns:
            Tuple of (minimum, maximum, current) resolution in 100ns units.
        """
        if sys.platform != "win32":
            return 0, 0, 0

        try:
            ntdll = ctypes.windll.ntdll

            minimum = ctypes.c_ulong()
            maximum = ctypes.c_ulong()
            current = ctypes.c_ulong()

            status = ntdll.NtQueryTimerResolution(
                ctypes.byref(minimum),
                ctypes.byref(maximum),
                ctypes.byref(current),
            )

            if status == 0:  # STATUS_SUCCESS
                return minimum.value, maximum.value, current.value
        except Exception as e:
            self._logger.debug(f"Failed to get timer resolution: {e}")

        return 0, 0, 0

    def _get_qpc_frequency(self) -> int:
        """Get QueryPerformanceCounter frequency.

        Returns:
            Frequency in Hz.
        """
        if sys.platform != "win32":
            return 0

        try:
            frequency = ctypes.c_longlong()
            ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency))
            return frequency.value
        except Exception:
            return 0

    def _measure_sleep_accuracy(
        self,
        target_ms: float = 1.0,
        samples: int = 100,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[float]:
        """Measure sleep timing accuracy.

        Args:
            target_ms: Target sleep time in milliseconds.
            samples: Number of samples.
            progress_callback: Optional progress callback.

        Returns:
            List of overshoot times in microseconds.
        """
        overshoots: list[float] = []
        target_ns = target_ms * 1_000_000

        for i in range(samples):
            start = time.perf_counter_ns()
            time.sleep(target_ms / 1000)  # Convert to seconds
            end = time.perf_counter_ns()

            actual_ns = end - start
            overshoot_us = (actual_ns - target_ns) / 1000  # Convert to microseconds

            overshoots.append(overshoot_us)

            if progress_callback:
                progress_callback(int((i + 1) / samples * 50))  # 0-50%

        return overshoots

    def _measure_timing_jitter(
        self,
        samples: int = 100,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[float]:
        """Measure timing jitter between consecutive measurements.

        Args:
            samples: Number of samples.
            progress_callback: Optional progress callback.

        Returns:
            List of jitter values in microseconds.
        """
        timestamps: list[int] = []

        # Collect timestamps as fast as possible
        for i in range(samples + 1):
            timestamps.append(time.perf_counter_ns())

            if progress_callback and i % 10 == 0:
                progress_callback(50 + int(i / (samples + 1) * 50))  # 50-100%

        # Calculate intervals and jitter
        intervals = [
            (timestamps[i + 1] - timestamps[i]) / 1000  # Convert to microseconds
            for i in range(len(timestamps) - 1)
        ]

        if len(intervals) < 2:
            return []

        avg_interval = statistics.mean(intervals)
        jitters = [abs(interval - avg_interval) for interval in intervals]

        return jitters

    def run_benchmark(
        self,
        name: str = "benchmark",
        sleep_samples: int = 100,
        jitter_samples: int = 100,
        progress_callback: Callable[[int], None] | None = None,
    ) -> DpcBenchmarkResult | None:
        """Run DPC latency benchmark.

        Args:
            name: Name for this benchmark.
            sleep_samples: Number of sleep accuracy samples.
            jitter_samples: Number of jitter samples.
            progress_callback: Optional callback for progress (0-100).

        Returns:
            DpcBenchmarkResult or None if failed.
        """
        if sys.platform != "win32":
            self._logger.error("DPC benchmark only supported on Windows")
            return None

        try:
            stats = DpcStats()

            # Get timer resolution
            _, _, current_resolution = self._get_timer_resolution()
            if current_resolution > 0:
                stats.timer_resolution_ns = current_resolution * 100  # Convert to ns
                stats.timer_resolution_ms = current_resolution / 10000  # Convert to ms

            # Get QPC resolution
            qpc_freq = self._get_qpc_frequency()
            if qpc_freq > 0:
                stats.qpc_resolution_ns = 1_000_000_000 / qpc_freq

            # Measure sleep accuracy
            overshoots = self._measure_sleep_accuracy(
                target_ms=1.0,
                samples=sleep_samples,
                progress_callback=progress_callback,
            )

            if overshoots:
                stats.sample_count = len(overshoots)
                stats.sleep_accuracy_avg_us = statistics.mean(overshoots)
                stats.sleep_accuracy_max_us = max(overshoots)
                stats.sleep_accuracy_stdev_us = (
                    statistics.stdev(overshoots) if len(overshoots) > 1 else 0.0
                )

            # Measure timing jitter
            jitters = self._measure_timing_jitter(
                samples=jitter_samples,
                progress_callback=progress_callback,
            )

            if jitters:
                stats.timing_jitter_avg_us = statistics.mean(jitters)
                stats.timing_jitter_max_us = max(jitters)

            return DpcBenchmarkResult(
                name=name,
                timestamp=datetime.now().isoformat(),
                stats=stats,
            )
        except Exception as e:
            self._logger.error(f"DPC benchmark failed: {e}")
            return None

    def get_current_resolution(self) -> dict[str, float]:
        """Get current timer resolution info.

        Returns:
            Dictionary with resolution info.
        """
        minimum, maximum, current = self._get_timer_resolution()

        return {
            "minimum_ms": minimum / 10000 if minimum > 0 else 0.0,
            "maximum_ms": maximum / 10000 if maximum > 0 else 0.0,
            "current_ms": current / 10000 if current > 0 else 0.0,
        }

    def save_result(self, result: DpcBenchmarkResult) -> Path:
        """Save benchmark result.

        Args:
            result: Result to save.

        Returns:
            Path to saved file.
        """
        return self._store.save(result.to_dict(), result.name)

    def load_result(self, path: Path) -> DpcBenchmarkResult | None:
        """Load benchmark result from file.

        Args:
            path: Path to result file.

        Returns:
            DpcBenchmarkResult or None if failed.
        """
        return self._store.load(path, DpcBenchmarkResult.from_dict)

    def list_results(self) -> list[Path]:
        """List saved benchmark results.

        Returns:
            List of result file paths, newest first.
        """
        return self._store.list_files()

    def compare(
        self,
        before: DpcBenchmarkResult,
        after: DpcBenchmarkResult,
    ) -> DpcComparison:
        """Compare two benchmark results.

        Args:
            before: Before optimization result.
            after: After optimization result.

        Returns:
            DpcComparison with analysis.
        """
        return DpcComparison(before=before, after=after)
