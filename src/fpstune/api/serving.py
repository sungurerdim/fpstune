"""Run the API under a uvicorn server that can be asked to stop over HTTP.

``uvicorn.run`` builds its ``Server`` internally and never hands it back, so
nothing could flip the flag that makes it stop gracefully. This builds the same
server, gives ``api/shutdown.py`` the one callable that stops it, and runs it.

Two callers: ``fpstune serve`` in this process, and the ``--dev`` source path,
which starts ``python -m fpstune.api.serving --port N`` as a child so Vite can
run beside it.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from fpstune.api import shutdown

if TYPE_CHECKING:
    from fastapi import FastAPI

_STARTUP_FAILURE = 3
"""uvicorn's own exit code for "the server never started" (a taken port, say)."""


def run_api(*, host: str = "127.0.0.1", port: int = 8000, app: FastAPI | None = None) -> None:
    """Serve the API until Ctrl+C or a shutdown request, then return.

    Returns normally on a graceful stop, so the caller's cleanup runs. Raises
    ``SystemExit(3)`` when the server never started, as ``uvicorn.run`` does.
    ``app`` is fpstune's own unless a test serves a smaller one.
    """
    import uvicorn

    if app is None:
        from fpstune.api.main import app as fpstune_app

        app = fpstune_app
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    shutdown.install_stop_hook(lambda: setattr(server, "should_exit", True))
    try:
        server.run()
    finally:
        shutdown.clear_stop_hook()
    if not server.started:
        raise SystemExit(_STARTUP_FAILURE)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m fpstune.api.serving")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_api(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
