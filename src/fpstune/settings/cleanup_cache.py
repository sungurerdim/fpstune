"""Thread-safe TTL cache for cleanup size background detection."""

from __future__ import annotations

import threading
import time
from typing import Any

_TTL = 300  # 5 minutes for a successfully computed size
# "unavailable" (e.g. Docker engine down) expires fast so a re-detect after the
# user starts the service recomputes instead of showing a stale unavailable state.
_UNAVAILABLE_TTL = 15


class CleanupSizeCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {setting_id: {"bytes": int,
        #               "status": "ready"|"calculating"|"unavailable"|"not_installed",
        #               "ts": float}}
        # "not_installed": the cleanup's target software/dirs are absent → the setting
        # is not applicable (hidden + excluded from totals). Persists (no TTL): a fresh
        # install is picked up on the next full re-detect (app reload).
        self._data: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            now = time.monotonic()
            if entry["status"] == "ready" and now - entry["ts"] > _TTL:
                del self._data[key]
                return None
            if entry["status"] == "unavailable" and now - entry["ts"] > _UNAVAILABLE_TTL:
                del self._data[key]
                return None
            return dict(entry)

    def set_result(self, key: str, bytes_val: int) -> None:
        with self._lock:
            self._data[key] = {
                "bytes": bytes_val,
                "status": "ready",
                "ts": time.monotonic(),
            }

    def set_unavailable(self, key: str) -> None:
        """Mark a size as unavailable (the underlying service/daemon is not running)."""
        with self._lock:
            self._data[key] = {
                "bytes": 0,
                "status": "unavailable",
                "ts": time.monotonic(),
            }

    def set_not_installed(self, key: str) -> None:
        """Mark a cleanup as not-installed (no target software/dirs on this system)."""
        with self._lock:
            self._data[key] = {
                "bytes": 0,
                "status": "not_installed",
                "ts": time.monotonic(),
            }

    def mark_calculating(self, key: str) -> None:
        with self._lock:
            if key not in self._data or self._data[key]["status"] != "calculating":
                self._data[key] = {
                    "bytes": 0,
                    "status": "calculating",
                    "ts": time.monotonic(),
                }

    def is_calculating(self, key: str) -> bool:
        with self._lock:
            entry = self._data.get(key)
            return entry is not None and entry["status"] == "calculating"

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def all_entries(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}


cleanup_size_cache = CleanupSizeCache()
