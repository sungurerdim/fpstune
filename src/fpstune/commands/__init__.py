"""CLI command modules for fpstune."""

from fpstune.commands.benchmark import dpc_bench, fps, network_bench
from fpstune.commands.cleanup import cleanup
from fpstune.commands.gpu import gpu, nvidia_dump
from fpstune.commands.status import status

__all__ = [
    "cleanup",
    "dpc_bench",
    "fps",
    "gpu",
    "network_bench",
    "nvidia_dump",
    "status",
]
