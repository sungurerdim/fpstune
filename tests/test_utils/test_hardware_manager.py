"""Tests for fpstune.utils.hardware_manager — singleton, cache locking, TTL, hot-plug."""

from __future__ import annotations

import inspect
import threading
from unittest.mock import MagicMock, patch

import pytest

from fpstune.utils.detect import MonitorInfo


def _monitor(device: str) -> MonitorInfo:
    """A neutral panel description; the tests only read `.name`."""
    return MonitorInfo(
        name=device,
        width=1920,
        height=1080,
        refresh_rate_hz=60,
        is_primary=True,
    )


class TestHardwareManagerSingleton:
    """HardwareManager must enforce singleton semantics."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def test_two_instances_are_same_object(self):
        """Two HardwareManager() calls must return the same object."""
        from fpstune.utils.hardware_manager import HardwareManager

        a = HardwareManager()
        b = HardwareManager()
        assert a is b

    def test_state_persists_across_acquisitions(self):
        """Cache state set on first instance must be visible on second."""
        from fpstune.utils.hardware_manager import HardwareManager

        a = HardwareManager()
        a._cache.monitors = [_monitor(r"\\.\DISPLAY1")]  # noqa: SLF001
        b = HardwareManager()
        assert [m.name for m in b._cache.monitors] == [r"\\.\DISPLAY1"]  # noqa: SLF001

    def test_init_idempotent(self):
        """Re-initializing the singleton must NOT reset cached state."""
        from fpstune.utils.hardware_manager import HardwareManager

        a = HardwareManager()
        a._cache.monitors = [_monitor(r"\\.\DISPLAY1")]  # noqa: SLF001
        a.__init__()  # reentry
        assert len(a._cache.monitors) == 1  # noqa: SLF001


class TestGetGpuInfo:
    """get_gpu_info contract: cached + waiting behavior."""

    def setup_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def teardown_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def test_returns_cached_gpu_when_not_detecting(self):
        """If detection complete, must return GPU info immediately without polling."""
        from fpstune.utils.hardware_manager import HardwareManager

        mock_gpu = MagicMock()
        with patch(
            "fpstune.utils.detect.get_gpu_info_cached",
            return_value=(mock_gpu, False),
        ):
            mgr = HardwareManager()
            gpu, detecting = mgr.get_gpu_info(wait=False)
            assert gpu is mock_gpu
            assert detecting is False

    def test_no_wait_returns_immediately(self):
        """wait=False must NOT wait even if detection ongoing."""
        from fpstune.utils.hardware_manager import HardwareManager

        with (
            patch(
                "fpstune.utils.detect.get_gpu_info_cached",
                return_value=(None, True),
            ) as mock_cached,
            patch("fpstune.utils.detect.wait_for_gpu_detection") as mock_wait,
        ):
            mgr = HardwareManager()
            gpu, detecting = mgr.get_gpu_info(wait=False)
            assert gpu is None
            assert detecting is True
            mock_wait.assert_not_called()
            assert mock_cached.call_count == 1

    def test_waits_until_detection_completes(self):
        """When wait=True and detection ongoing, must re-read the cache after the wait."""
        from fpstune.utils.hardware_manager import HardwareManager

        mock_gpu = MagicMock()
        cached_calls = iter([(None, True), (mock_gpu, False)])

        with (
            patch(
                "fpstune.utils.detect.get_gpu_info_cached",
                side_effect=lambda: next(cached_calls),
            ),
            patch("fpstune.utils.detect.wait_for_gpu_detection", return_value=True) as mock_wait,
        ):
            mgr = HardwareManager()
            gpu, detecting = mgr.get_gpu_info(wait=True)

        assert gpu is mock_gpu
        assert detecting is False
        mock_wait.assert_called_once()

    def test_wait_blocks_on_an_event_not_a_sleep_loop(self):
        """The wait must be the detection's own event, never a poll (#21).

        A sleep-poll costs up to 15 s of a worker thread and answers late by
        up to one poll interval; the event answers the instant detection ends.
        """
        import fpstune.utils.detect as detect
        from fpstune.utils.hardware_manager import HardwareManager

        with (
            patch("fpstune.utils.detect.get_gpu_info_cached", return_value=(None, True)),
            patch.object(detect._gpu_detection_done, "wait", return_value=True) as event_wait,
            patch("time.sleep") as mock_sleep,
        ):
            mgr = HardwareManager()
            gpu, _ = mgr.get_gpu_info(wait=True)

        assert gpu is None
        event_wait.assert_called_once()
        mock_sleep.assert_not_called()


class TestDetectorsHoldTheirLock:
    """Each detector's check-then-set must be atomic (#22).

    The registry warm-up pool, the API routes and the hot-plug thread all reach
    these three at once. Reading "cache is empty", releasing, then spawning the
    subprocess means every one of them spawns it.
    """

    def setup_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def teardown_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def test_monitor_detection_runs_under_the_monitor_lock(self):
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        held: list[bool] = []

        def _fake_get_monitors() -> list[MonitorInfo]:
            held.append(mgr._monitors_lock.locked())  # noqa: SLF001
            return [_monitor(r"\\.\DISPLAY1")]

        with patch("fpstune.utils.hardware_manager.get_monitors", _fake_get_monitors):
            mgr.detect_monitors()

        assert held == [True]

    def test_cpu_detection_runs_under_the_cpu_lock(self):
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        held: list[bool] = []

        def _fake_cpu():
            held.append(mgr._cpu_lock.locked())  # noqa: SLF001
            return MagicMock()

        with patch("fpstune.utils.hardware_manager.get_cpu_detailed_info", _fake_cpu):
            mgr.detect_cpu()

        assert held == [True]

    def test_os_detection_runs_under_the_os_lock(self):
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        held: list[bool] = []

        def _fake_os():
            held.append(mgr._os_lock.locked())  # noqa: SLF001
            return MagicMock()

        with patch("fpstune.utils.hardware_manager.get_os_info", _fake_os):
            mgr.detect_os()

        assert held == [True]

    def test_concurrent_monitor_detection_spawns_one_probe(self):
        """Eight callers arriving together must share a single detection."""
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        calls = 0
        calls_lock = threading.Lock()
        start = threading.Barrier(8)

        def _fake_get_monitors() -> list[MonitorInfo]:
            nonlocal calls
            with calls_lock:
                calls += 1
            return [_monitor(r"\\.\DISPLAY1")]

        def _worker() -> None:
            start.wait(timeout=10)
            mgr.detect_monitors()

        with patch("fpstune.utils.hardware_manager.get_monitors", _fake_get_monitors):
            threads = [threading.Thread(target=_worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert calls == 1


class TestMonitorCacheTtl:
    """C7 gives monitor info a five-minute TTL; the code used to have none."""

    def setup_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def teardown_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def test_ttl_is_five_minutes(self):
        from fpstune.utils.hardware_manager import MONITOR_CACHE_TTL_SECONDS

        assert MONITOR_CACHE_TTL_SECONDS == 300.0

    def test_second_call_within_the_ttl_reuses_the_cache(self):
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        with patch(
            "fpstune.utils.hardware_manager.get_monitors",
            return_value=[_monitor(r"\\.\DISPLAY1")],
        ) as probe:
            mgr.detect_monitors()
            mgr.detect_monitors()

        assert probe.call_count == 1

    def test_cache_older_than_the_ttl_is_re_read(self):
        """A cache that never expires cannot notice a panel swapped while idle."""
        from fpstune.utils.hardware_manager import MONITOR_CACHE_TTL_SECONDS, HardwareManager

        mgr = HardwareManager()
        with patch(
            "fpstune.utils.hardware_manager.get_monitors",
            return_value=[_monitor(r"\\.\DISPLAY1")],
        ) as probe:
            mgr.detect_monitors()
            mgr._cache.monitors_detected_at -= MONITOR_CACHE_TTL_SECONDS + 1  # noqa: SLF001
            mgr.detect_monitors()

        assert probe.call_count == 2

    def test_invalidating_monitors_clears_the_ttl_stamp(self):
        """Otherwise the next detect would keep answering from an emptied cache."""
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        with patch(
            "fpstune.utils.hardware_manager.get_monitors",
            return_value=[_monitor(r"\\.\DISPLAY1")],
        ):
            mgr.detect_monitors()
            mgr.invalidate_cache("monitors")

        assert mgr._cache.monitors == []  # noqa: SLF001
        assert mgr._cache.monitors_detected_at == 0.0  # noqa: SLF001


class TestHotplugPolling:
    """The poller must be startable once, stoppable, and run at the C7 interval."""

    def setup_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        HardwareManager._instance = None

    def teardown_method(self) -> None:
        from fpstune.utils.hardware_manager import HardwareManager

        if HardwareManager._instance is not None:
            HardwareManager._instance.stop_hotplug_polling(timeout=5)
        HardwareManager._instance = None

    def test_default_interval_is_the_c7_fifteen_seconds(self):
        """C7 and the lifespan comment both say 15 s; the call site said 60."""
        from fpstune.utils.hardware_manager import (
            HOTPLUG_POLL_INTERVAL_SECONDS,
            HardwareManager,
        )

        assert HOTPLUG_POLL_INTERVAL_SECONDS == 15.0
        default = (
            inspect.signature(HardwareManager.start_hotplug_polling).parameters["interval"].default
        )
        assert default == HOTPLUG_POLL_INTERVAL_SECONDS

    def test_stop_ends_the_thread_without_waiting_out_the_interval(self):
        """A `while True` with no stop event re-probes monitors forever (#21)."""
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        with patch("fpstune.utils.hardware_manager.get_monitors", return_value=[]):
            # An hour-long interval parks the thread in the event wait, so the
            # thread can only exit by being signalled, never by timing out.
            mgr.start_hotplug_polling(interval=3600.0)
            thread = mgr._hotplug_thread  # noqa: SLF001
            assert thread is not None
            mgr.stop_hotplug_polling(timeout=10)

        assert thread.is_alive() is False

    def test_starting_twice_leaves_one_poller(self):
        """A second start would double the subprocess rate for the same job."""
        from fpstune.utils.hardware_manager import HardwareManager

        mgr = HardwareManager()
        with patch("fpstune.utils.hardware_manager.get_monitors", return_value=[]):
            mgr.start_hotplug_polling(interval=3600.0)
            first = mgr._hotplug_thread  # noqa: SLF001
            mgr.start_hotplug_polling(interval=3600.0)
            second = mgr._hotplug_thread  # noqa: SLF001
            mgr.stop_hotplug_polling(timeout=10)

        assert first is second


@pytest.fixture(autouse=True)
def _reset_hardware_manager_singleton():
    """Ensure singleton is fresh for every test in this module."""
    from fpstune.utils.hardware_manager import HardwareManager

    HardwareManager._instance = None
    yield
    if HardwareManager._instance is not None:
        HardwareManager._instance.stop_hotplug_polling(timeout=5)
    HardwareManager._instance = None
