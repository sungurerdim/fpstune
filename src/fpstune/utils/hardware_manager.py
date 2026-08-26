"""Centralized hardware detection manager.

Provides a single entry point for all hardware detection with:
- Caching to avoid redundant detection
- Request deduplication (concurrent requests share results)
- Background detection support
- Thread-safe operations
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from fpstune.utils.detect import (
    CpuDetailedInfo,
    GpuInfo,
    MonitorInfo,
    OsInfo,
    get_cpu_detailed_info,
    get_monitors,
    get_os_info,
)

logger = logging.getLogger(__name__)

# C7: monitor info is the one hardware fact a user can change mid-session by
# plugging a cable, so it expires where CPU/GPU/OS do not.
MONITOR_CACHE_TTL_SECONDS = 300.0

# C7: how often the hot-plug thread re-reads the panel set. Shorter than the
# TTL on purpose — the poller is what makes a newly attached monitor appear
# without a request, the TTL is only the fallback when the poller is not running.
HOTPLUG_POLL_INTERVAL_SECONDS = 15.0


@dataclass
class HardwareCache:
    """Cached hardware detection results."""

    cpu: CpuDetailedInfo | None = None
    gpu: GpuInfo | None = None
    monitors: list[MonitorInfo] = field(default_factory=list)
    # Pushed in by the API routes that detect them, so the element types are
    # api.schemas models. Naming them here would make utils import the API
    # layer it is imported by.
    network_adapters: list[Any] = field(default_factory=list)
    audio_devices: list[Any] = field(default_factory=list)
    os_info: OsInfo | None = None

    # Detection status
    gpu_detecting: bool = False
    # Monotonic stamp of the last successful monitor detection, for the TTL.
    monitors_detected_at: float = 0.0


class HardwareManager:
    """Centralized hardware detection manager.

    Singleton that manages all hardware detection with:
    - Caching to avoid redundant detection
    - Request deduplication (concurrent requests wait for ongoing detection)
    - Background detection support
    """

    _instance: HardwareManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> HardwareManager:
        """Singleton pattern - ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the hardware manager."""
        if getattr(self, "_initialized", False):
            return

        self._cache = HardwareCache()
        # One lock per detected component, each held across the whole
        # check-compute-store. A lock released around the subprocess would let
        # the registry warm-up pool, an API route and the hot-plug thread all
        # see an empty cache and each spawn the same PowerShell. Per component
        # rather than one global lock so a 60 s monitor probe does not block a
        # CPU read that has nothing to do with it.
        self._cpu_lock = threading.Lock()
        self._monitors_lock = threading.Lock()
        self._os_lock = threading.Lock()

        self._hotplug_lock = threading.Lock()
        self._hotplug_stop = threading.Event()
        self._hotplug_thread: threading.Thread | None = None
        self._initialized = True

    @property
    def cache(self) -> HardwareCache:
        """Get the current cache."""
        return self._cache

    def get_gpu_info(self, wait: bool = True) -> tuple[GpuInfo | None, bool]:
        """Get GPU info, optionally waiting for detection.

        Args:
            wait: If True, wait for ongoing detection to complete.

        Returns:
            Tuple of (GpuInfo or None, is_detecting).
        """
        # Import here to avoid circular import
        from fpstune.utils.detect import get_gpu_info_cached, wait_for_gpu_detection

        gpu_info, detecting = get_gpu_info_cached()

        if wait and detecting and gpu_info is None:
            wait_for_gpu_detection()
            gpu_info, detecting = get_gpu_info_cached()

        self._cache.gpu = gpu_info
        self._cache.gpu_detecting = detecting
        return gpu_info, detecting

    def detect_cpu(self) -> CpuDetailedInfo | None:
        """Detect CPU info."""
        with self._cpu_lock:
            if self._cache.cpu is not None:
                return self._cache.cpu

            try:
                self._cache.cpu = get_cpu_detailed_info()
            except Exception as e:
                logger.debug(f"Failed to detect CPU: {e}")

            return self._cache.cpu

    def detect_monitors(self) -> list[MonitorInfo]:
        """Detect monitor info, re-reading once the cached set goes stale."""
        with self._monitors_lock:
            age = time.monotonic() - self._cache.monitors_detected_at
            if self._cache.monitors and age < MONITOR_CACHE_TTL_SECONDS:
                return self._cache.monitors

            try:
                self._cache.monitors = get_monitors()
                self._cache.monitors_detected_at = time.monotonic()
            except Exception as e:
                logger.debug(f"Failed to detect monitors: {e}")

            return self._cache.monitors

    def detect_os(self) -> OsInfo | None:
        """Detect OS info."""
        with self._os_lock:
            if self._cache.os_info is not None:
                return self._cache.os_info

            try:
                self._cache.os_info = get_os_info()
            except Exception as e:
                logger.debug(f"Failed to detect OS: {e}")

            return self._cache.os_info

    def set_network_adapters(self, adapters: list[Any]) -> None:
        """Set network adapters (detected externally via PowerShell)."""
        self._cache.network_adapters = adapters

    def set_audio_devices(self, devices: list[Any]) -> None:
        """Set audio devices (detected externally via PowerShell)."""
        self._cache.audio_devices = devices

    def start_hotplug_polling(self, interval: float = HOTPLUG_POLL_INTERVAL_SECONDS) -> None:
        """Start background thread that polls for monitor hotplug events.

        Compares the monitor list every `interval` seconds. When the set
        of connected monitor names changes, invalidates the monitors cache
        so the next API request returns fresh data.

        Calling this while a poller is already running is a no-op, so a
        second startup path cannot double the subprocess rate.
        """
        with self._hotplug_lock:
            if self._hotplug_thread is not None and self._hotplug_thread.is_alive():
                return
            self._hotplug_stop.clear()
            thread = threading.Thread(
                target=self._poll_hotplug,
                args=(interval,),
                daemon=True,
                name="fpstune-hotplug",
            )
            self._hotplug_thread = thread

        thread.start()
        logger.debug("Hotplug polling started (interval=%.0fs)", interval)

    def stop_hotplug_polling(self, timeout: float = 5.0) -> None:
        """Signal the hot-plug thread to stop and wait briefly for it.

        Without this the poller re-detects monitors — a PowerShell process
        each time — for as long as the process lives, including while the UI
        is closed.
        """
        self._hotplug_stop.set()
        with self._hotplug_lock:
            thread = self._hotplug_thread
            self._hotplug_thread = None

        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def _poll_hotplug(self, interval: float) -> None:
        """Re-read the monitor set until stopped.

        The wait is on the stop event rather than a sleep, so shutdown does
        not have to outlast a full interval.
        """
        while not self._hotplug_stop.wait(interval):
            try:
                old_names = (
                    {m.name for m in self._cache.monitors} if self._cache.monitors else set()
                )
                self.invalidate_cache("monitors")
                new_monitors = self.detect_monitors()
                new_names = {m.name for m in new_monitors}
                if old_names and old_names != new_names:
                    logger.info(
                        "Monitor hotplug detected: %s → %s",
                        sorted(old_names),
                        sorted(new_names),
                    )
            except Exception as exc:
                logger.debug("Hotplug polling error: %s", exc)

    def invalidate_cache(self, component: str | None = None) -> None:
        """Invalidate cache for a specific component or all.

        Args:
            component: Optional component name ('cpu', 'gpu', 'monitors', etc.).
                       If None, invalidates all cache.
        """
        if component is None:
            # Every detection lock, so a clear cannot land between a detector's
            # subprocess and its store and be overwritten by the stale result.
            with self._cpu_lock, self._monitors_lock, self._os_lock:
                self._cache = HardwareCache()
        elif component == "cpu":
            with self._cpu_lock:
                self._cache.cpu = None
        elif component == "gpu":
            self._cache.gpu = None
        elif component == "monitors":
            with self._monitors_lock:
                self._cache.monitors = []
                self._cache.monitors_detected_at = 0.0
        elif component == "network_adapters":
            self._cache.network_adapters = []
        elif component == "audio_devices":
            self._cache.audio_devices = []


# Global singleton instance
hardware_manager = HardwareManager()
