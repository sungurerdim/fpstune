"""Benchmark runner for fpstune.

This module provides tools for measuring system performance
before and after applying optimizations.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fpstune.benchmark.result_store import ResultStore

_logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    timestamp: str
    name: str
    metrics: dict[str, float] = field(default_factory=dict)
    system_info: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "name": self.name,
            "metrics": self.metrics,
            "system_info": self.system_info,
            "notes": self.notes,
        }


class BenchmarkRunner:
    """Runs various system benchmarks.

    Available benchmarks:
    - Timer resolution test
    - DPC latency measurement
    - CPU scheduling latency
    - Memory latency
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        """Initialize BenchmarkRunner.

        Args:
            output_dir: Directory to save benchmark results.
        """
        from fpstune.utils.config import get_config_dir

        self._output_dir = output_dir or get_config_dir() / "benchmarks"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._store = ResultStore(self._output_dir, _logger)

    @property
    def output_dir(self) -> Path:
        """Where results are written, for callers that store alongside them."""
        return self._output_dir

    def run_all(self, name: str = "benchmark") -> BenchmarkResult:
        """Run all available benchmarks.

        Args:
            name: Name for this benchmark run.

        Returns:
            BenchmarkResult with all metrics.
        """
        result = BenchmarkResult(
            timestamp=datetime.now().isoformat(),
            name=name,
        )

        # Collect system info
        result.system_info = self._get_system_info()

        # Run benchmarks
        result.metrics.update(self._benchmark_timer_resolution())
        result.metrics.update(self._benchmark_sleep_accuracy())

        if sys.platform == "win32":
            result.metrics.update(self._benchmark_qpc_performance())

        return result

    def run_timer_benchmark(self) -> BenchmarkResult:
        """Run timer-specific benchmarks.

        Returns:
            BenchmarkResult with timer metrics.
        """
        result = BenchmarkResult(
            timestamp=datetime.now().isoformat(),
            name="timer_benchmark",
        )

        result.system_info = self._get_system_info()
        result.metrics.update(self._benchmark_timer_resolution())
        result.metrics.update(self._benchmark_sleep_accuracy())

        if sys.platform == "win32":
            result.metrics.update(self._benchmark_qpc_performance())

        return result

    def _get_system_info(self) -> dict[str, str]:
        """Get system information."""
        import platform

        from fpstune.utils.detect import get_cpu_info, get_gpu_info, get_ram_info

        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
        }

        cpu = get_cpu_info()
        info["cpu"] = cpu.get("cpu_name", "Unknown")
        info["cpu_cores"] = cpu.get("core_count", "0")

        ram = get_ram_info()
        info["ram_total_mb"] = str(ram.get("total_mb", 0))

        gpu = get_gpu_info()
        if gpu:
            info["gpu"] = gpu.name
            info["gpu_driver"] = gpu.driver_version

        return info

    def _benchmark_timer_resolution(self) -> dict[str, float]:
        """Benchmark timer resolution.

        Measures the actual timer resolution by measuring
        small sleep intervals.
        """
        results = {}

        # Measure time.perf_counter resolution
        samples = []
        for _ in range(100):
            start = time.perf_counter()
            end = time.perf_counter()
            samples.append((end - start) * 1000000)  # microseconds

        # Filter out zero samples (below resolution)
        samples = [s for s in samples if s > 0]
        if samples:
            results["perf_counter_resolution_us"] = min(samples)
            results["perf_counter_avg_us"] = sum(samples) / len(samples)

        return results

    def _benchmark_sleep_accuracy(self) -> dict[str, float]:
        """Benchmark sleep accuracy.

        Measures how accurate sleep() is at different intervals.
        """
        results = {}

        test_intervals = [0.001, 0.005, 0.010, 0.016]  # 1ms, 5ms, 10ms, 16ms

        for interval in test_intervals:
            errors = []
            for _ in range(10):
                start = time.perf_counter()
                time.sleep(interval)
                actual = time.perf_counter() - start

                error = (actual - interval) * 1000  # Error in ms
                errors.append(abs(error))

            avg_error = sum(errors) / len(errors)
            results[f"sleep_{int(interval * 1000)}ms_error_ms"] = round(avg_error, 3)

        return results

    def _benchmark_qpc_performance(self) -> dict[str, float]:
        """Benchmark QueryPerformanceCounter on Windows.

        This measures the overhead of calling QPC.
        """
        if sys.platform != "win32":
            return {}

        results = {}

        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32

            class LARGE_INTEGER(ctypes.Structure):
                _fields_ = [("QuadPart", ctypes.c_longlong)]

            freq = LARGE_INTEGER()
            kernel32.QueryPerformanceFrequency(ctypes.byref(freq))
            results["qpc_frequency_hz"] = float(freq.QuadPart)

            # Measure QPC call overhead
            counter = LARGE_INTEGER()
            samples = []

            for _ in range(1000):
                start = time.perf_counter_ns()
                kernel32.QueryPerformanceCounter(ctypes.byref(counter))
                end = time.perf_counter_ns()
                samples.append(end - start)

            results["qpc_call_overhead_ns"] = sum(samples) / len(samples)
            results["qpc_call_min_ns"] = min(samples)

        except (OSError, AttributeError):
            pass

        return results

    def save_result(self, result: BenchmarkResult) -> Path:
        """Save benchmark result to file.

        Args:
            result: BenchmarkResult to save.

        Returns:
            Path to saved file.
        """
        return self._store.save(result.to_dict(), result.name)

    def load_result(self, path: Path) -> BenchmarkResult | None:
        """Load benchmark result from file.

        Args:
            path: Path to result file.

        Returns:
            BenchmarkResult or None if loading fails.
        """
        return self._store.load(
            path,
            lambda data: BenchmarkResult(
                timestamp=data["timestamp"],
                name=data["name"],
                metrics=data.get("metrics", {}),
                system_info=data.get("system_info", {}),
                notes=data.get("notes", ""),
            ),
        )

    def list_results(self) -> list[Path]:
        """List all saved benchmark results, newest first.

        Returns:
            List of result file paths.
        """
        return self._store.list_files()
