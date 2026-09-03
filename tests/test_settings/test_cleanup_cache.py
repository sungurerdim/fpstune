"""A claimed cleanup size always ends up with an answer.

"calculating" means a worker is on its way back. It used to mean that forever:
the entry had no deadline, so a worker that died — a killed PowerShell whose
grandchild kept the pipes, measured 2026-09-03 — left the row spinning and the
UI polling every three seconds for the life of the process.
"""

from __future__ import annotations

import time

from fpstune.settings.cleanup_cache import CleanupSizeCache


def test_a_claim_within_its_deadline_is_still_calculating() -> None:
    cache = CleanupSizeCache()
    cache.mark_calculating("cleanup:dism_cleanup", ttl=60)

    entry = cache.get("cleanup:dism_cleanup")

    assert entry is not None
    assert entry["status"] == "calculating"
    assert cache.is_calculating("cleanup:dism_cleanup")


def test_a_claim_past_its_deadline_answers_unavailable() -> None:
    """The worker is not coming back, so the row says so instead of spinning."""
    cache = CleanupSizeCache()
    cache.mark_calculating("cleanup:dism_cleanup", ttl=0.01)
    time.sleep(0.05)

    entry = cache.get("cleanup:dism_cleanup")

    assert entry is not None
    assert entry["status"] == "unavailable"


def test_the_polled_snapshot_settles_an_abandoned_claim_too() -> None:
    """`all_entries` is what the UI polls, and nothing else re-detects a size.

    Settling only in `get` would leave the endpoint reporting "calculating" until
    something asked the detector about that setting again — which, for a cleanup
    size, is nothing.
    """
    cache = CleanupSizeCache()
    cache.mark_calculating("cleanup:temp_files", ttl=0.01)
    time.sleep(0.05)

    assert cache.all_entries()["cleanup:temp_files"]["status"] == "unavailable"


def test_settling_leaves_a_short_lived_entry_so_the_next_detect_rescans() -> None:
    """ "unavailable" carries its own 15 s TTL — the give-up is not permanent."""
    cache = CleanupSizeCache()
    cache.mark_calculating("cleanup:temp_files", ttl=0.01)
    time.sleep(0.05)
    cache.all_entries()

    settled = cache._data["cleanup:temp_files"]
    assert settled["status"] == "unavailable"
    assert time.monotonic() - settled["ts"] < 1.0


def test_a_finished_scan_is_never_overwritten_by_the_deadline() -> None:
    """A worker that answered owns the entry; the backstop must not touch it."""
    cache = CleanupSizeCache()
    cache.mark_calculating("cleanup:temp_files", ttl=0.01)
    cache.set_result("cleanup:temp_files", 6 * 1024 * 1024)
    time.sleep(0.05)

    entry = cache.get("cleanup:temp_files")

    assert entry is not None
    assert entry["status"] == "ready"
    assert entry["bytes"] == 6 * 1024 * 1024
