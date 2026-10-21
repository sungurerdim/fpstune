"""Benchmark tools for fpstune."""

from fpstune.benchmark.disk_io import DiskIoBench
from fpstune.benchmark.dpc import (
    DpcBenchmark,
    DpcBenchmarkResult,
    DpcComparison,
    DpcStats,
    TimingBench,
)
from fpstune.benchmark.memory import MemoryBench
from fpstune.benchmark.network import (
    LatencyStats,
    NetworkBenchmark,
    NetworkBenchmarkResult,
    NetworkComparison,
    NetworkIdleBench,
)
from fpstune.benchmark.network_load import NetworkLoadBench
from fpstune.benchmark.presentmon import (
    BenchmarkCapture,
    FrameTimeStats,
    PresentMonBenchmark,
)
from fpstune.benchmark.presentmon import (
    BenchmarkComparison as FpsBenchmarkComparison,
)
from fpstune.benchmark.suite import (
    Bench,
    BenchReading,
    BenchResult,
    SuiteComparison,
    SuiteRun,
    compare_runs,
    run_suite,
)

__all__ = [
    "Bench",
    "DiskIoBench",
    "MemoryBench",
    "NetworkIdleBench",
    "NetworkLoadBench",
    "TimingBench",
    "BenchReading",
    "BenchResult",
    "SuiteRun",
    "SuiteComparison",
    "run_suite",
    "compare_runs",
    "PresentMonBenchmark",
    "FrameTimeStats",
    "BenchmarkCapture",
    "FpsBenchmarkComparison",
    "NetworkBenchmark",
    "NetworkBenchmarkResult",
    "NetworkComparison",
    "LatencyStats",
    "DpcBenchmark",
    "DpcBenchmarkResult",
    "DpcComparison",
    "DpcStats",
]
