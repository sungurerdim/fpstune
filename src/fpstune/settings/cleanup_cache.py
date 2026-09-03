"""Thread-safe TTL cache for cleanup size background detection."""

from __future__ import annotations

import threading
import time
from typing import Any

_TTL = 300  # 5 minutes for a successfully computed size
# "unavailable" (e.g. Docker engine down) expires fast so a re-detect after the
# user starts the service recomputes instead of showing a stale unavailable state.
_UNAVAILABLE_TTL = 15
# "calculating" says a worker is on its way back with an answer, and for the life
# of the process it used to be unfalsifiable: an id whose worker never reported
# kept the spinner and the UI's 3-second poll going forever. Measured on
# 2026-09-03, `cleanup:dism_cleanup` sat there for twenty minutes after its scan's
# PowerShell was killed (see utils.powershell._reap_in_background for why the
# worker never came back).
#
# So a claim now carries the deadline its own worker promised — `mark_calculating`
# takes the scan's timeout — and this is only the default for a caller that names
# none. It is a backstop, not the mechanism: every worker settles its ids in a
# `finally`, and this fires only when one dies without reaching it.
_CALCULATING_TTL = 600


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

    def _settle_calculating(self, key: str) -> dict[str, Any] | None:
        """Give up on a "calculating" entry whose worker is past its own deadline.

        Answering "unavailable" rather than dropping the entry is deliberate: it
        carries its own short TTL, so the next detect starts a fresh scan, and in
        the meantime the row says what happened instead of spinning. Caller holds
        the lock.
        """
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry["status"] != "calculating":
            return entry
        if time.monotonic() - entry["ts"] <= entry.get("ttl", _CALCULATING_TTL):
            return entry
        settled: dict[str, Any] = {
            "bytes": 0,
            "status": "unavailable",
            "ts": time.monotonic(),
        }
        self._data[key] = settled
        return settled

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._settle_calculating(key)
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

    def mark_calculating(self, key: str, ttl: float = _CALCULATING_TTL) -> None:
        """Claim `key` for a worker that promises an answer within `ttl` seconds.

        The deadline is the worker's own timeout plus its queueing headroom, so
        the claim expires when that worker has demonstrably failed to report —
        not on a guess about how long a folder takes to size.
        """
        with self._lock:
            if key not in self._data or self._data[key]["status"] != "calculating":
                self._data[key] = {
                    "bytes": 0,
                    "status": "calculating",
                    "ts": time.monotonic(),
                    "ttl": ttl,
                }

    def is_calculating(self, key: str) -> bool:
        with self._lock:
            entry = self._data.get(key)
            return entry is not None and entry["status"] == "calculating"

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def all_entries(self) -> dict[str, dict[str, Any]]:
        """Every entry as the UI should see it, abandoned scans settled.

        The deadline is applied here and not only in :meth:`get` because this is
        what the polling endpoint reads: a scan that never reported would
        otherwise stay "calculating" in the UI until something happened to
        re-detect it, which for a cleanup size is nothing.
        """
        with self._lock:
            return {k: dict(v) for k in list(self._data) if (v := self._settle_calculating(k))}


cleanup_size_cache = CleanupSizeCache()
