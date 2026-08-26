"""Regression tests: background GPU detection is claimed once and waited on by event.

Two defects live here (#22, #21):

* ``start_gpu_detection_async`` read ``_gpu_detecting`` outside the cache lock
  and set it *inside* the thread it spawned, so the lifespan hook and the first
  request could both start a full hardware probe.
* the wait for that detection was a 0.1 s sleep poll bounded at 15 s, on a
  worker thread, where the detection's own completion event says the same thing
  immediately.
"""

from __future__ import annotations

import threading

import pytest

import fpstune.utils.detect as detect


@pytest.fixture(autouse=True)
def _fresh_gpu_state(monkeypatch: pytest.MonkeyPatch):
    """Isolate each test from module-level GPU cache state."""
    monkeypatch.setattr(detect, "_gpu_cache", None)
    monkeypatch.setattr(detect, "_gpu_cache_time", 0.0)
    monkeypatch.setattr(detect, "_gpu_detecting", False)
    done = threading.Event()
    done.set()
    monkeypatch.setattr(detect, "_gpu_detection_done", done)
    yield
    # Never leave a claimed-but-unfinished detection behind for the next test.
    detect._gpu_detecting = False
    done.set()


class TestDetectionIsClaimedOnce:
    def test_two_concurrent_starts_spawn_one_probe(self) -> None:
        """The concrete failure: two full GPU probes for one cold cache."""
        release = threading.Event()
        calls = 0
        calls_lock = threading.Lock()
        start = threading.Barrier(2)

        def _fake_detect():
            nonlocal calls
            with calls_lock:
                calls += 1
            release.wait(timeout=10)
            return None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(detect, "_detect_gpu_sync", _fake_detect)

            def _worker() -> None:
                start.wait(timeout=10)
                detect.start_gpu_detection_async()

            threads = [threading.Thread(target=_worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            # Both callers have returned; whoever claimed the detection is now
            # parked inside the fake probe.
            assert detect.is_gpu_detecting() is True
            release.set()
            detect.wait_for_gpu_detection(timeout=10)

        assert calls == 1

    def test_claim_is_taken_under_the_cache_lock(self) -> None:
        """Reading the flag outside the lock is what makes the claim racy.

        Holding the lock must stop a starter dead. It used to sail past and
        spawn a probe while another thread was mid-claim.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(detect, "_detect_gpu_sync", lambda: None)

            detect._gpu_cache_lock.acquire()
            starter = threading.Thread(target=detect.start_gpu_detection_async)
            try:
                starter.start()
                starter.join(timeout=0.25)
                # Read the global directly: is_gpu_detecting() would want the
                # very lock this thread is holding.
                assert starter.is_alive() is True
                assert detect._gpu_detecting is False
            finally:
                detect._gpu_cache_lock.release()

            starter.join(timeout=10)
            detect.wait_for_gpu_detection(timeout=10)

        assert detect.is_gpu_detecting() is False


class TestWaitIsAnEvent:
    def test_wait_returns_only_after_detection_finishes(self) -> None:
        """Ordering is forced by events, not by elapsed time."""
        release = threading.Event()
        waiter_returned = threading.Event()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(detect, "_detect_gpu_sync", lambda: release.wait(timeout=10) and None)
            detect.start_gpu_detection_async()

            def _waiter() -> None:
                detect.wait_for_gpu_detection(timeout=10)
                waiter_returned.set()

            waiting = threading.Thread(target=_waiter)
            waiting.start()

            # The probe is still parked, so the waiter must still be blocked.
            assert waiter_returned.wait(timeout=0.25) is False

            release.set()
            assert waiter_returned.wait(timeout=10) is True
            waiting.join(timeout=10)

        assert detect.is_gpu_detecting() is False

    def test_wait_returns_at_once_when_nothing_is_running(self) -> None:
        """A waiter arriving after detection must not pay the timeout."""
        assert detect.wait_for_gpu_detection(timeout=0.0) is True


class TestCachedReadDoesNotDoubleStart:
    def test_cached_value_starts_no_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sentinel = detect.GpuInfo(
            vendor=detect.GpuVendor.UNKNOWN,
            name="Test Adapter",
            driver_version="1.0",
            vram_mb=0,
        )
        monkeypatch.setattr(detect, "_gpu_cache", sentinel)
        started = 0

        def _fake_start(_callback=None):
            nonlocal started
            started += 1

        monkeypatch.setattr(detect, "start_gpu_detection_async", _fake_start)

        info, detecting = detect.get_gpu_info_cached()

        assert info is sentinel
        assert detecting is False
        assert started == 0
