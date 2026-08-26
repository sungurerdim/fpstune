"""Regression tests: the status cache's shutdown signal actually fires (#22).

``_stop_event`` was set at shutdown and never read by ``_refresh_from_settings``,
so ``stop_background_refresh`` did nothing except spend five seconds in a
``join`` while the scan it meant to cancel ran on to completion.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

import fpstune.api.status_cache as status_cache


@pytest.fixture(autouse=True)
def _fresh_module_state():
    """Leave no stop signal or thread handle behind for the next test."""
    status_cache._stop_event.clear()
    status_cache._background_thread = None
    yield
    status_cache._stop_event.clear()
    status_cache._background_thread = None


def _registry_with(setting_count: int) -> MagicMock:
    registry = MagicMock()
    settings = []
    for i in range(setting_count):
        setting = MagicMock()
        setting.id = f"test:setting_{i}"
        setting.category.value = "core"
        setting.value_type.value = "string"
        setting.choices = ()
        settings.append(setting)
    registry.get_all.return_value = settings
    return registry


class TestStopEventIsHonoured:
    def test_refresh_does_not_start_once_stopping(self) -> None:
        """Building the registry alone is seconds of hardware discovery."""
        status_cache._stop_event.set()

        with patch("fpstune.api.routes.settings._get_registry") as get_registry:
            status_cache._refresh_from_settings()

        get_registry.assert_not_called()

    def test_scan_result_is_discarded_when_the_stop_lands_mid_scan(self) -> None:
        """A cache written after shutdown began is a scan nobody will read."""
        before, _ = status_cache.get_cached_status()

        def _detect_all(_settings):
            status_cache._stop_event.set()
            return {}

        engine = MagicMock()
        engine.detect_all.side_effect = _detect_all

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=_registry_with(2)),
            patch("fpstune.settings.DetectionEngine", return_value=engine),
        ):
            status_cache._refresh_from_settings()

        after, _ = status_cache.get_cached_status()
        engine.detect_all.assert_called_once()
        assert after is before

    def test_background_update_is_not_started_once_stopping(self) -> None:
        status_cache._stop_event.set()
        status_cache.start_background_update()
        assert status_cache._background_thread is None

    def test_force_refresh_is_not_started_once_stopping(self) -> None:
        status_cache._stop_event.set()

        with patch("fpstune.api.routes.settings._get_registry") as get_registry:
            status_cache.force_refresh(_wait=True)

        get_registry.assert_not_called()


class TestStopBackgroundRefresh:
    def test_join_waits_for_the_running_refresh(self) -> None:
        """The handle must be published so shutdown can see the thread at all."""
        released = threading.Event()
        entered = threading.Event()

        def _slow_refresh() -> None:
            entered.set()
            released.wait(timeout=10)

        with patch.object(status_cache, "_refresh_from_settings", _slow_refresh):
            status_cache.start_background_update()
            assert entered.wait(timeout=10) is True
            thread = status_cache._background_thread
            assert thread is not None
            released.set()
            status_cache.stop_background_refresh()

        assert thread.is_alive() is False

    def test_stop_clears_the_signal_so_a_later_refresh_still_runs(self) -> None:
        """Left set, the event would make every subsequent scan a silent no-op."""
        status_cache.stop_background_refresh()
        assert status_cache._stop_event.is_set() is False

        with patch("fpstune.api.routes.settings._get_registry") as get_registry:
            get_registry.return_value = _registry_with(0)
            status_cache._refresh_from_settings()

        get_registry.assert_called_once()
