"""Benchmark tools for fpstune."""

from fpstune.benchmark.compare import BenchmarkComparison
from fpstune.benchmark.disk_io import DiskIoBench
from fpstune.benchmark.dpc import (
    DpcBenchmark,
    DpcBenchmarkResult,
    DpcComparison,
    DpcStats,
)
from fpstune.benchmark.frame_pacing import FramePacingBench
from fpstune.benchmark.furmark import (
    FurMarkBenchmark,
    FurMarkComparison,
    FurMarkResult,
)
from fpstune.benchmark.memory import MemoryBench
from fpstune.benchmark.network import (
    LatencyStats,
    NetworkBenchmark,
    NetworkBenchmarkResult,
    NetworkComparison,
)
from fpstune.benchmark.network_bench import NetworkIdleBench
from fpstune.benchmark.network_load import NetworkLoadBench
from fpstune.benchmark.presentmon import (
    BenchmarkCapture,
    FrameTimeStats,
    PresentMonBenchmark,
)
from fpstune.benchmark.presentmon import (
    BenchmarkComparison as FpsBenchmarkComparison,
)
from fpstune.benchmark.runner import BenchmarkResult, BenchmarkRunner
from fpstune.benchmark.suite import (
    Bench,
    BenchReading,
    BenchResult,
    SuiteComparison,
    SuiteRun,
    compare_runs,
    run_suite,
)
from fpstune.benchmark.timing_bench import TimingBench

__all__ = [
    "Bench",
    "FramePacingBench",
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
    "BenchmarkRunner",
    "BenchmarkResult",
    "BenchmarkComparison",
    "PresentMonBenchmark",
    "FrameTimeStats",
    "BenchmarkCapture",
    "FpsBenchmarkComparison",
    "FurMarkBenchmark",
    "FurMarkResult",
    "FurMarkComparison",
    "NetworkBenchmark",
    "NetworkBenchmarkResult",
    "NetworkComparison",
    "LatencyStats",
    "DpcBenchmark",
    "DpcBenchmarkResult",
    "DpcComparison",
    "DpcStats",
]
