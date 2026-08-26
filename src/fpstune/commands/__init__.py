"""CLI command modules for fpstune."""

from fpstune.commands.benchmark import benchmark, dpc_bench, fps, gpu_bench, network_bench
from fpstune.commands.cleanup import cleanup
from fpstune.commands.gpu import gpu
from fpstune.commands.status import status

__all__ = [
    "benchmark",
    "cleanup",
    "dpc_bench",
    "fps",
    "gpu",
    "gpu_bench",
    "network_bench",
    "status",
]
