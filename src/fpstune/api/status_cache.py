"""Status cache using the unified settings system.

Provides backward-compatible API for system status endpoints.
Internally uses SettingsRegistry and DetectionEngine.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from fpstune.settings.base import DetectionResult, SettingExecutor

logger = logging.getLogger(__name__)


class CachedSetting(TypedDict):
    """One setting's row in the status cache.

    Declared rather than assembled inline because this is a hand-off across a
    module boundary: ``api/routes/system.py`` splats these into
    ``ModuleSettingResponse``, and pydantic discards any key the model has no
    field for — silently, which is how ``is_optimized`` travelled from here to
    the client and never arrived. Naming the keys in one place is what lets
    ``tests/test_api/test_status_cache_contract.py`` hold the two sides equal,
    so the next key added here goes red instead of disappearing.
    """

    name: str
    display_name: str
    description: str
    current_value: Any
    recommended_value: Any
    value_type: str
    choices: list[str]
    requires_reboot: bool
    current_impact: str
    recommended_impact: str
    default_value: Any
    is_optimized: bool


def _cached_setting(setting: SettingExecutor, result: DetectionResult | None) -> CachedSetting:
    """Build one cache row from a setting and its detection result."""
    return CachedSetting(
        name=setting.id,
        display_name=setting.display_name,
        description=setting.description,
        current_value=result.value if result else None,
        recommended_value=setting.recommended_value,
        value_type=setting.value_type.value,
        choices=list(setting.choices),
        requires_reboot=setting.requires_reboot,
        current_impact=setting.current_impact,
        recommended_impact=setting.recommended_impact,
        default_value=setting.default_value,
        is_optimized=result.is_optimized if result else False,
    )


@dataclass
class ModuleInfo:
    """Module information for status response."""

    name: str
    display_name: str
    description: str
    status: str
    message: str
    details: list[str]
    changes: dict[str, Any]
    is_available: bool
    requires_reboot: bool
    # Widened from ``list[CachedSetting]`` only because the one consumer,
    # ``api/routes/system.py::_module_setting_from_cache``, still takes
    # ``dict[str, Any]``. Narrow this the moment that signature names
    # CachedSetting; the rows are built through ``_cached_setting`` either way,
    # so the producer side is already checked.
    settings: list[dict[str, Any]]
    loading: bool = False


@dataclass
class CachedStatus:
    """Cached overall status."""

    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    applied_count: int = 0
    total_count: int = 0


# Global cache state
_cache = CachedStatus()
_cache_lock = threading.Lock()
_is_loading = False
_background_thread: threading.Thread | None = None

# Set means "abandon the scan in flight". A full scan is one long
# ``detect_all`` call that cannot be interrupted from outside, so the refresh
# checks this at the boundaries either side of it instead.
_stop_event = threading.Event()


def get_cached_status() -> tuple[CachedStatus, bool]:
    """Get cached status.

    Returns:
        Tuple of (CachedStatus, is_loading)
    """
    with _cache_lock:
        return _cache, _is_loading


def force_refresh(_wait: bool = False) -> None:
    """Force refresh the status cache.

    Args:
        _wait: If True, wait for refresh to complete.
    """
    global _is_loading

    if _stop_event.is_set():
        return

    with _cache_lock:
        _is_loading = True

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_refresh_from_settings)
            future.result(timeout=120)  # 2 minute max for full detection run
    except concurrent.futures.TimeoutError:
        logger.warning("Status cache refresh timed out after 120s")
    except Exception as e:
        logger.error("Status cache refresh failed: %s", e)
    finally:
        with _cache_lock:
            _is_loading = False


def _refresh_from_settings() -> None:
    """Refresh cache from settings system."""
    global _cache

    if _stop_event.is_set():
        return

    try:
        from fpstune.api.routes.settings import _get_registry
        from fpstune.settings import DetectionEngine

        # Reuse the module-level registry singleton — constructing a fresh
        # SettingsRegistry re-runs adapter discovery (~10s of PowerShell) on
        # every background refresh (C7 violation).
        registry = _get_registry()
        engine = DetectionEngine()

        # Detect all settings
        all_settings = registry.get_all()

        # Building the registry above is itself seconds of hardware discovery,
        # so shutdown gets a chance to land before the far longer scan starts.
        if _stop_event.is_set():
            logger.debug("Status cache refresh abandoned before detection: shutting down")
            return

        results = engine.detect_all(all_settings)

        if _stop_event.is_set():
            logger.debug("Status cache refresh discarded after detection: shutting down")
            return

        # Group by category
        categories: dict[str, list[CachedSetting]] = {}
        for setting in all_settings:
            cat = setting.category.value
            categories.setdefault(cat, []).append(_cached_setting(setting, results.get(setting.id)))

        # Create module infos from categories
        modules: dict[str, ModuleInfo] = {}
        applied_count = 0
        total_count = 0

        for cat_name, settings in categories.items():
            optimized = sum(1 for s in settings if s["is_optimized"])
            total = len(settings)
            total_count += total
            applied_count += optimized

            status = "applied" if optimized == total else "not_applied"
            if optimized > 0 and optimized < total:
                status = "partially_applied"

            modules[cat_name] = ModuleInfo(
                name=cat_name,
                display_name=cat_name.replace("-", " ").replace("_", " ").title(),
                description=f"{total} settings in this category",
                status=status,
                message=f"{optimized}/{total} optimized",
                details=[],
                changes={},
                is_available=True,
                requires_reboot=any(s["requires_reboot"] for s in settings),
                settings=[dict(s) for s in settings],
                loading=False,
            )

        with _cache_lock:
            _cache = CachedStatus(
                modules=modules,
                applied_count=applied_count,
                total_count=total_count,
            )

    except Exception as e:
        logger.error("Failed to refresh status from settings: %s", e)


def start_background_update() -> None:
    """Start background status update if not already running."""
    global _background_thread, _is_loading

    if _stop_event.is_set():
        return

    def _update() -> None:
        global _is_loading
        try:
            _refresh_from_settings()
        finally:
            with _cache_lock:
                _is_loading = False

    with _cache_lock:
        if _background_thread is not None and _background_thread.is_alive():
            return
        _is_loading = True
        # Published under the same lock that reads it, so a shutdown running
        # concurrently either sees no thread or sees this one.
        _background_thread = threading.Thread(target=_update, daemon=True)
        thread = _background_thread

    thread.start()


def stop_background_refresh() -> None:
    """Signal the background refresh thread to stop.

    Sets the stop event so any running background update knows to exit
    at its next check point. Called during application shutdown.
    """
    _stop_event.set()
    try:
        with _cache_lock:
            thread = _background_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
            if thread.is_alive():
                logger.debug(
                    "Background status refresh still running after 5s; "
                    "it is a daemon thread and will not outlive the process"
                )
    finally:
        # The event means "abandon the scan in flight", not "this module is
        # closed for good": leaving it set would make every later refresh a
        # silent no-op in any process that outlives one shutdown.
        _stop_event.clear()
