"""The one process-wide SettingsRegistry, built once and cached.

This lived in ``api/routes/settings.py`` for most of the project's life, which
made a route module the only place anything could ask for the registry — the
benchmark and debug routes reached into a sibling route's privates, and the CLI
would have had to import an HTTP module to enumerate settings. The singleton
now lives with the thing it caches; the API warms it, everything consumes it.

Callers go through the module (``registry_cache.get_registry()``), not a
``from``-import of the function — that keeps one patch target for tests and
means a patched ``get_registry`` is patched for every consumer at once.
"""

from __future__ import annotations

import logging
import threading

from fpstune.settings import SettingsRegistry

logger = logging.getLogger(__name__)

# Module-level registry cache — avoids re-running PowerShell adapter discovery
# (10s subprocess) on every request. Invalidated on process restart.
_registry: SettingsRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> SettingsRegistry:
    """Return the cached SettingsRegistry, building it on first call.

    Locked, not a bare check-then-build. Building it enumerates adapters, reads
    driver metadata and detects monitors, so two callers arriving together would
    each run that — and since the warm-up below deliberately makes a second
    caller likely, the race stopped being theoretical the moment it existed.
    """
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SettingsRegistry()
        return _registry


def warm_registry() -> None:
    """Build the registry now, off the request path.

    ``/settings/definitions`` is documented as instant and is not: the first
    call pays for the whole hardware discovery. Measured, 1.80 s for the first
    request and 0.01 s for every one after it — so the cost is real, paid once,
    and lands squarely on the first screen a user ever sees.

    Called at API startup in a daemon thread, alongside the GPU pre-warm that
    already exists for the same reason. The browser spends its own hundreds of
    milliseconds fetching and parsing the bundle before it can ask, and this
    uses that window. A request that still arrives first simply blocks on the
    lock and gets the answer the warm-up was already computing, rather than
    starting a second discovery.
    """
    try:
        get_registry()
    except Exception as exc:  # pragma: no cover - environment dependent
        # The next real request rebuilds; a failed warm-up must not be the thing
        # that takes the API down at startup.
        logger.warning("registry warm-up failed, the first request will pay for it: %s", exc)
