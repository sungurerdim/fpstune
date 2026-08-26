"""API route modules."""

from fpstune.api.routes.benchmark import router as benchmark_router
from fpstune.api.routes.benchmark_suite import router as benchmark_suite_router
from fpstune.api.routes.display import router as display_router
from fpstune.api.routes.safety import router as safety_router
from fpstune.api.routes.settings import router as settings_router
from fpstune.api.routes.settings_stream import router as settings_stream_router
from fpstune.api.routes.system import router as system_router
from fpstune.api.routes.system_audio import router as system_audio_router
from fpstune.api.routes.system_network import router as system_network_router
from fpstune.api.routes.system_power import router as system_power_router

__all__ = [
    "system_router",
    "safety_router",
    "benchmark_router",
    "benchmark_suite_router",
    "settings_router",
    "settings_stream_router",
    "system_audio_router",
    "system_network_router",
    "system_power_router",
    "display_router",
]
