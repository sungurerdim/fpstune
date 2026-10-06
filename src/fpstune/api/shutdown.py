"""Stopping the running API on request, the way uvicorn stops on Ctrl+C.

A newly started fpstune closes the one already running by POSTing
``/api/system/shutdown`` to it. Stopping must be *graceful*: the lifespan's
shutdown path runs (hot-plug poller and bench scheduler stop, a scene left on
screen is closed, a pending adapter restart is flushed) and in-flight requests
finish. ``TerminateProcess`` does none of that, and would leave a half-applied
tweak with nobody to finish or report it.

The mechanism is a hook rather than a signal. Whoever owns the uvicorn server
(``api/serving.py``) installs a callable that flips ``Server.should_exit`` —
the same flag Ctrl+C flips. The route cannot reach the server any other way, and
a signal sent to the own process would race the terminal's own Ctrl+C handling
and, on Windows, address a whole console process group.

The stop waits for the machine-wide operation lock first
(``benchmark/operation_lock.py``): an apply, a cleanup or a bench that holds it
is changing or measuring this machine, and cutting it off mid-way is the one
thing a shutdown request must never do. The wait is bounded, so a hung operation
cannot make the request immortal; past the bound the stop proceeds anyway, and
uvicorn still lets every in-flight request finish.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from fpstune.benchmark import operation_lock
from fpstune.utils.logger import get_logger

logger = get_logger()

OPERATION_WAIT_SECONDS = 60.0
"""How long a stop waits for a running apply, cleanup or bench before going on."""

_POLL_SECONDS = 0.5

_stop_server: Callable[[], None] | None = None
_pending = False


def install_stop_hook(stop: Callable[[], None]) -> None:
    """Register how this process's server is told to stop (called by the server's owner)."""
    global _stop_server
    _stop_server = stop


def clear_stop_hook() -> None:
    """Forget the hook once its server has returned; a stop can no longer be delivered."""
    global _stop_server
    _stop_server = None


def is_stoppable() -> bool:
    """Whether a server in this process registered a way to stop it.

    False for an app served by anything else (``uvicorn fpstune.api.main:app``,
    a test client): there is nothing the route could honestly promise.
    """
    return _stop_server is not None


def is_pending() -> bool:
    """Whether a stop has been requested already (a second request is not another stop)."""
    return _pending


def mark_pending() -> None:
    global _pending
    _pending = True


async def operation_in_progress() -> bool:
    """Whether an apply, a cleanup or a bench holds the operation lock right now."""
    return not await asyncio.to_thread(operation_lock.is_free)


async def stop_when_idle(
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
) -> None:
    """Wait (bounded) for the operation lock to be free, then stop the server.

    Runs after the 202 has been sent, so the caller already has its answer. The
    bounds are read at call time (``OPERATION_WAIT_SECONDS``, ``_POLL_SECONDS``).
    """
    wait_seconds = OPERATION_WAIT_SECONDS if wait_seconds is None else wait_seconds
    poll_seconds = _POLL_SECONDS if poll_seconds is None else poll_seconds
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds
    announced = False
    while await operation_in_progress():
        if not announced:
            logger.info(
                "Shutdown requested; waiting up to %.0f s for the running operation", wait_seconds
            )
            announced = True
        if loop.time() >= deadline:
            logger.warning(
                "An operation still holds the lock after %.0f s; stopping now, "
                "in-flight requests are allowed to finish",
                wait_seconds,
            )
            break
        await asyncio.sleep(poll_seconds)

    stop = _stop_server
    if stop is None:
        logger.error("Shutdown requested but the server's stop hook is gone")
        return
    logger.info("Stopping the API on request")
    stop()
