"""FastAPI application for fpstune."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import threading
import traceback
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fpstune import __version__
from fpstune.api.routes import (
    benchmark_router,
    benchmark_suite_router,
    display_router,
    safety_router,
    settings_router,
    settings_stream_router,
    system_audio_router,
    system_network_router,
    system_power_router,
    system_router,
    system_storage_router,
)
from fpstune.api.routes.debug import router as debug_router
from fpstune.utils.debug import is_debug_enabled
from fpstune.utils.detect import start_gpu_detection_async
from fpstune.utils.logger import get_logger as _get_shared_logger
from fpstune.utils.runtime import frontend_dist, is_frozen


def _running_under_pytest() -> bool:
    """Whether this process is a pytest run rather than a served instance."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def _get_logger() -> logging.Logger:
    """Get or create the API logger based on environment."""
    # Skip fancy logging during tests to avoid terminal interference
    if _running_under_pytest():
        logger = logging.getLogger("fpstune.api")
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.WARNING)
            handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.WARNING)
        return logger

    # The shared handler lives on the "fpstune" logger (utils.logger owns the
    # format and the colour decision); "fpstune.api" reaches it by propagation.
    _get_shared_logger()

    # Reduce noise from third-party libraries. "httpx2"/"httpcore2" are the
    # names those packages emit under (verified in their sources), not typos
    # for httpx/httpcore.
    for name in ("uvicorn.access", "uvicorn.error", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)

    return logging.getLogger("fpstune.api")


# Set up logging (lazy - avoids issues during import in tests)
logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    """Get the API logger, initializing if needed."""
    global logger
    if logger is None:
        logger = _get_logger()
    return logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    On shutdown we stop the background-refresh thread, then give in-flight
    GPU detection a short grace window before exiting so tail-latency
    requests don't see a half-finished cache. Daemon threads (GPU detect)
    die with the process either way; the join just makes shutdown logs
    deterministic.
    """
    _ = app  # Reserved for future startup/shutdown hooks
    # Startup
    get_logger().info("fpstune API starting...")
    # Pre-warm GPU detection cache in background to avoid delay on first request
    start_gpu_detection_async()
    get_logger().info("GPU detection started in background")
    # Same reason, larger cost: building the settings registry enumerates
    # adapters, reads their driver metadata and detects monitors. Measured, that
    # is 1.80 s on the first /settings/definitions and 0.01 s after — an
    # endpoint documented as instant, paying for hardware discovery on the first
    # screen a user ever sees. The browser is still fetching its bundle here.
    from fpstune.api.routes.settings import warm_registry

    threading.Thread(target=warm_registry, daemon=True, name="registry-warmup").start()
    # Start monitor hot-plug polling (15s interval, daemon thread)
    from fpstune.utils.hardware_manager import hardware_manager as _hw_mgr

    _hw_mgr.start_hotplug_polling()
    # Watch for a game to measure. Not a measurement now — a frame rate needs
    # something rendering, and at startup the game is almost always closed — so
    # this starts the watch and takes the reading at the only moment it can be
    # taken. Costs one process snapshot a minute until then.
    from fpstune.benchmark.headroom_watch import start_headroom_watch

    start_headroom_watch()
    yield
    # Shutdown
    get_logger().info("fpstune API shutting down...")
    # Signal background threads to stop
    with contextlib.suppress(Exception):
        _hw_mgr.stop_hotplug_polling()
    with contextlib.suppress(Exception):
        from fpstune.benchmark.headroom_watch import stop_headroom_watch

        stop_headroom_watch()
    # Brief grace window for in-flight GPU detection
    with contextlib.suppress(Exception):
        from fpstune.utils.detect import is_gpu_detecting

        deadline = 0.0
        while is_gpu_detecting() and deadline < 2.0:
            await asyncio.sleep(0.1)
            deadline += 0.1


# Hostnames a request may legitimately address this server by. The API binds
# loopback and runs elevated with no authentication, so a Host header naming
# anything else is a DNS name an attacker rebound to 127.0.0.1 — same-origin
# to itself, which CORS never inspects.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Methods whose handlers write registry keys, power schemes and NIC state.
# OPTIONS stays out so CORS preflight still reaches its middleware.
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Vite/CRA dev servers, allowed cross-origin access from a source checkout
# only — a frozen build serves its UI same-origin at /ui and grants nothing.
_DEV_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)


def _host_name(host_header: str) -> str:
    """The hostname of a Host header, without port or IPv6 brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:].partition("]")[0]
    return host.partition(":")[0]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application.
    """
    # Interactive API docs (Swagger/ReDoc) and the debug router expose the full
    # schema plus PII-bearing diagnostics; gate both behind FPSTUNE_DEBUG so the
    # packaged production binary does not surface them.
    debug_mode = is_debug_enabled()

    app = FastAPI(
        title="fpstune API",
        description="Windows Gaming Performance Optimization API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if debug_mode else None,
        redoc_url="/redoc" if debug_mode else None,
    )

    # Cross-origin access exists for the dev servers only; the shipped exe
    # serves its UI same-origin at /ui and must not grant any other local
    # page — a dev server someone else runs on these ports included —
    # credentialed access to an elevated API.
    dev_origins: tuple[str, ...] = () if is_frozen() else _DEV_ORIGINS
    if dev_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(dev_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        )

    allowed_hosts = set(_LOOPBACK_HOSTS)
    if _running_under_pytest():
        # TestClient's default base_url is http://testserver. A bare single
        # label is not a registrable public DNS name, but it is only trusted
        # while pytest is the caller all the same.
        allowed_hosts.add("testserver")

    @app.middleware("http")
    async def reject_foreign_callers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Refuse requests no local, same-origin caller could have produced.

        There is no authentication by design, so the browser's own headers are
        the entire perimeter. Two checks:

        * The Host header must name loopback. A hostile page whose DNS name
          rebinds to 127.0.0.1 is same-origin to itself, so CORS never runs;
          the foreign name it addresses this server by is the one tell left.
        * A state-changing request that carries an Origin must carry this
          server's own, or a dev-server origin from a source checkout. The
          write endpoints take query/path params only, which makes them
          CORS-simple: a cross-site POST's response is opaque, but the
          elevated side effect would land anyway — and every browser stamps
          such a request with the foreign Origin. Non-browser clients (the
          CLI, tests, curl) send no Origin and pass.
        """
        host = request.headers.get("host", "")
        if _host_name(host) not in allowed_hosts:
            return JSONResponse(status_code=400, content={"detail": "Invalid Host header"})
        if request.method in _STATE_CHANGING_METHODS:
            origin = request.headers.get("origin")
            if (
                origin is not None
                and origin not in dev_origins
                and urlsplit(origin).netloc.lower() != host.strip().lower()
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected"},
                )
        return await call_next(request)

    # Include routers
    app.include_router(system_router, prefix="/api", tags=["System"])
    app.include_router(system_network_router, prefix="/api", tags=["System"])
    app.include_router(system_audio_router, prefix="/api", tags=["System"])
    app.include_router(system_power_router, prefix="/api", tags=["System"])
    app.include_router(system_storage_router, prefix="/api", tags=["System"])
    app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
    app.include_router(settings_stream_router, prefix="/api/settings", tags=["Settings"])
    app.include_router(display_router, prefix="/api", tags=["Display"])
    app.include_router(safety_router, prefix="/api", tags=["Safety"])
    app.include_router(benchmark_router, prefix="/api/benchmark", tags=["Benchmark"])
    app.include_router(benchmark_suite_router, prefix="/api/benchmark", tags=["Benchmark"])
    if debug_mode:
        app.include_router(debug_router, tags=["Debug"])

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {
            "name": "fpstune API",
            "version": __version__,
            "docs": "/docs",
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Health check endpoint with subsystem readiness probes.

        The probe set is intentionally minimal: each check is a pure-Python
        capability lookup or a cached query — no subprocess, no I/O — so
        /health stays cheap to call from supervisors and uptime checks.
        """
        from fpstune.utils.admin import is_admin
        from fpstune.utils.detect import is_gpu_detecting
        from fpstune.utils.hardware_manager import hardware_manager

        is_windows = sys.platform == "win32"
        gpu_ready = hardware_manager.cache.gpu is not None
        gpu_loading = is_gpu_detecting()

        subsystems: dict[str, Any] = {
            # Registry / PowerShell readiness is platform-truthful: they are
            # only "ready" on Windows. Non-Windows users can still exercise
            # the API surface (mocked or read-only paths).
            "registry": is_windows,
            "powershell": is_windows,
            # GPU detection: tri-state info — ready / loading / pending. Not
            # gating overall health, so a fresh process start isn't degraded.
            "gpu_detection": ("ready" if gpu_ready else ("loading" if gpu_loading else "pending")),
        }
        # Only platform-required subsystems gate the healthy/degraded flag.
        required_ok = (not is_windows) or (subsystems["registry"] and subsystems["powershell"])

        return {
            "status": "healthy" if required_ok else "degraded",
            "platform": sys.platform,
            "is_admin": is_admin(),
            "subsystems": subsystems,
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Global exception handler for unhandled errors."""
        log = get_logger()
        log.error(f"Unhandled exception on {request.method} {request.url.path}")
        log.error(f"Exception: {type(exc).__name__}: {exc}")
        log.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": request.url.path,
            },
        )

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Log all incoming requests with clean formatting."""
        import time

        start = time.perf_counter()
        log = get_logger()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000

            # Skip noisy polling endpoints
            path = request.url.path
            if path in ("/api/status", "/health") and response.status_code == 200:
                return response

            # Status indicator based on response code (ASCII only)
            if response.status_code < 300:
                status = "[OK]"
            elif response.status_code < 400:
                status = "[->]"
            elif response.status_code < 500:
                status = "[!!]"
            else:
                status = "[XX]"

            log.info(
                f"{status} {request.method:6} {path} -> {response.status_code} ({duration_ms:.0f}ms)"
            )
            return response
        except Exception as e:
            log.error(f"[XX] {request.method:6} {request.url.path} -> Error: {e}")
            raise

    # Mount bundled frontend last so API routes take priority. utils.runtime owns
    # where the UI lives, so the CLI and the API cannot disagree about it — they
    # did, and the CLI was wrong.
    dist_dir = frontend_dist()
    if dist_dir:
        app.mount("/ui", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app


# Create app instance for uvicorn
app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API server.

    Args:
        host: Host to bind to.
        port: Port to bind to.
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
