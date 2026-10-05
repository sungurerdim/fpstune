"""A claimed cleanup size always ends up with an answer, and never too early.

"calculating" means a worker is on its way back. It used to mean that forever: a
worker that died — a killed PowerShell whose grandchild kept the pipes, measured
2026-09-03 — left the row spinning and the UI polling every three seconds for the
life of the process. A fixed deadline fixed that and broke the other side: a scan
still working past it was declared unavailable and a second one started.

A claim now lasts exactly as long as its worker: it settles once the worker's
`done` event is set without an outcome, and not a moment before.
"""

from __future__ import annotations

import threading
import time

from fpstune.settings.cleanup_cache import CleanupSizeCache


def _claimed(key: str) -> tuple[CleanupSizeCache, threading.Event]:
    cache = CleanupSizeCache()
    done = threading.Event()
    cache.mark_calculating(key, done)
    return cache, done


def test_a_running_worker_keeps_its_claim_however_long_it_takes() -> None:
    cache, _ = _claimed("cleanup:dism_cleanup")
    time.sleep(0.05)

    entry = cache.get("cleanup:dism_cleanup")

    assert entry is not None
    assert entry["status"] == "calculating"
    assert cache.is_calculating("cleanup:dism_cleanup")


def test_a_worker_that_ended_without_an_answer_settles_unavailable() -> None:
    """The worker is not coming back, so the row says so instead of spinning."""
    cache, done = _claimed("cleanup:dism_cleanup")
    done.set()

    entry = cache.get("cleanup:dism_cleanup")

    assert entry is not None
    assert entry["status"] == "unavailable"


def test_the_polled_snapshot_settles_an_abandoned_claim_too() -> None:
    """`all_entries` is what the UI polls, and nothing else re-detects a size.

    Settling only in `get` would leave the endpoint reporting "calculating" until
    something asked the detector about that setting again — which, for a cleanup
    size, is nothing.
    """
    cache, done = _claimed("cleanup:temp_files")
    done.set()

    entries = cache.all_entries()

    assert entries["cleanup:temp_files"]["status"] == "unavailable"
    assert "done" not in entries["cleanup:temp_files"], "the event is not UI data"


def test_settling_leaves_a_short_lived_entry_so_the_next_detect_rescans() -> None:
    """ "unavailable" carries its own 15 s TTL — the give-up is not permanent."""
    cache, done = _claimed("cleanup:temp_files")
    done.set()
    cache.all_entries()

    settled = cache._data["cleanup:temp_files"]
    assert settled["status"] == "unavailable"
    assert time.monotonic() - settled["ts"] < 1.0


def test_a_finished_scan_is_never_overwritten_when_its_worker_ends() -> None:
    """A worker that answered owns the entry; its `done` must not undo that."""
    cache, done = _claimed("cleanup:temp_files")
    cache.set_result("cleanup:temp_files", 6 * 1024 * 1024)
    done.set()

    entry = cache.get("cleanup:temp_files")

    assert entry is not None
    assert entry["status"] == "ready"
    assert entry["bytes"] == 6 * 1024 * 1024
