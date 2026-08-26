"""Regression tests: subprocess-backed work must not run on the event loop.

Each test drives a route whose backing call used to execute synchronously
inside an ``async def`` handler (PERF-15, PERF-16, PERF-17 route side,
PERF-19, PERF-21) and asserts the call now executes on a thread with no
running event loop — the observable mechanism of ``asyncio.to_thread``.
The assertion is on the mechanism, never on wall-clock timing.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _loop_recorder(record: dict[str, bool], result: Any) -> Any:
    """Build a stand-in that records whether its thread has a running loop.

    Called via ``asyncio.to_thread`` there is no running loop in the worker
    thread; called inline in an async route there is — which was the bug.
    """

    def _call(*_args: Any, **_kwargs: Any) -> Any:
        try:
            asyncio.get_running_loop()
            record["on_event_loop"] = True
        except RuntimeError:
            record["on_event_loop"] = False
        return result

    return _call


class TestRestorePointOffload:
    """PERF-15: Checkpoint-Computer (120 s timeout) blocked the loop."""

    def test_create_restore_point_runs_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        mock_rp = MagicMock()
        mock_rp.is_available = True
        mock_rp.create_restore_point = MagicMock(side_effect=_loop_recorder(record, True))

        with (
            patch("fpstune.api.routes.safety.RestorePointManager", return_value=mock_rp),
            patch("fpstune.api.routes.safety.log_activity"),
        ):
            response = client.post("/api/restore-point")

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert record["on_event_loop"] is False


class TestSystemInfoCpuOffload:
    """PERF-17 (route side): /api/system reached the CPU detector on the loop."""

    def test_get_cpu_info_runs_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        os_info = MagicMock(
            platform="win32",
            version="10.0.26100",
            build="26100",
            edition="Windows 11 Pro",
            display_version="24H2",
            is_supported=True,
        )
        with (
            patch("fpstune.api.routes.system.hardware_manager") as mock_hw,
            patch(
                "fpstune.api.routes.system.get_cpu_info",
                side_effect=_loop_recorder(
                    record, {"cpu_name": "AMD Ryzen 7 5800X", "core_count": "16"}
                ),
            ),
            patch(
                "fpstune.api.routes.system.get_ram_info",
                return_value={"total_mb": 32768, "available_mb": 16384},
            ),
            patch(
                "fpstune.api.routes.system.get_gpu_info_cached",
                return_value=(None, False),
            ),
            patch("fpstune.api.routes.system.is_admin", return_value=False),
        ):
            mock_hw.detect_os.return_value = os_info
            response = client.get("/api/system")

        assert response.status_code == 200
        assert response.json()["cpu_name"] == "AMD Ryzen 7 5800X"
        assert record["on_event_loop"] is False


class TestHardwareRouteUsesCachedCpuPath:
    """PERF-18 (route side): /api/hardware bypassed hardware_manager's CPU cache."""

    def test_hardware_route_calls_hardware_manager_detect_cpu(self, client: TestClient) -> None:
        cpu = MagicMock()
        cpu.name = "AMD Ryzen 7 5800X"
        cpu.physical_cores = 8
        cpu.logical_cores = 16
        cpu.base_clock_mhz = 3800
        cpu.architecture = "AMD64"
        cpu.cache_l3_mb = 32
        cpu.sockets = 1
        cpu.p_cores = 8
        cpu.e_cores = 0
        cpu.is_hybrid = False

        with (
            patch("fpstune.api.routes.system.hardware_manager") as mock_hw,
            patch(
                "fpstune.api.routes.system.get_gpu_info_cached",
                return_value=(None, False),
            ),
            patch(
                "fpstune.api.routes.system.get_detailed_network_adapters",
                return_value=[],
            ),
            patch(
                "fpstune.api.routes.system.get_detailed_storage_drives",
                return_value=[],
            ),
            patch("fpstune.api.routes.system.get_audio_devices", return_value=[]),
        ):
            mock_hw.detect_cpu.return_value = cpu
            mock_hw.detect_monitors.return_value = []
            response = client.get("/api/hardware")

        assert response.status_code == 200
        assert response.json()["cpu"]["name"] == "AMD Ryzen 7 5800X"
        # The cached path: detect_cpu memoizes forever, get_cpu_detailed_info
        # used to be called directly and spawned PowerShell per request.
        mock_hw.detect_cpu.assert_called_once()


class TestDisplayDetectionOffload:
    """PERF-19: monitor detection (PowerShell + Add-Type compile) blocked the loop."""

    def test_refresh_displays_detects_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
        ):
            mock_hw.detect_monitors = MagicMock(side_effect=_loop_recorder(record, []))
            response = client.post("/api/display/refresh")

        assert response.status_code == 200
        # /display/refresh invalidates the cache first, so this call is always
        # a cold multi-second detection — the worst case of the finding.
        assert record["on_event_loop"] is False

    def test_set_display_to_auto_detects_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        monitor = MagicMock()
        monitor.native_width = 2560
        monitor.native_height = 1440
        monitor.native_refresh_rate_hz = 165
        monitor.max_refresh_rate_hz = 165
        monitor.is_resolution_optimal = True
        monitor.is_refresh_optimal = True

        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
        ):
            mock_hw.detect_monitors = MagicMock(side_effect=_loop_recorder(record, [monitor]))
            response = client.post("/api/display/0/auto")

        assert response.status_code == 200
        assert record["on_event_loop"] is False


class TestVrrGpuWaitOffload:
    """PERF-21: get_gpu_info(wait=True) sleep-polls up to 15 s."""

    def test_vrr_info_gpu_wait_runs_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info = MagicMock(side_effect=_loop_recorder(record, (None, False)))
            response = client.get("/api/display/vrr-optimization")

        assert response.status_code == 200
        assert record["on_event_loop"] is False

    def test_vrr_apply_gpu_wait_runs_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info = MagicMock(side_effect=_loop_recorder(record, (None, False)))
            response = client.post(
                "/api/display/vrr-optimization/apply",
                json={"fps_limit": 0, "vrr_mode": "off", "vsync": "off"},
            )

        # No GPU → 400, but the wait still must have happened off the loop.
        assert response.status_code == 400
        assert record["on_event_loop"] is False


class TestSettingHardwareContextOffload:
    """apply/reset/undo/verify built the hardware context on the loop.

    It is cached, so the warm path was cheap — but the build enumerates adapters
    and reads driver metadata through subprocesses, and the request that pays
    for it is the first one after start-up.
    """

    def _patched(self, record: dict[str, bool]):
        """Record the context builder's thread, and stop short of any write.

        The applicability answer is forced to False so the handler returns
        before ``CommandExecutor.apply`` — these tests must never touch the
        machine they run on. The restore point is stubbed for the same reason.
        """
        return (
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                side_effect=_loop_recorder(record, None),
            ),
            patch(
                "fpstune.api.routes.settings.ApplicabilityChecker",
                return_value=MagicMock(is_applicable=MagicMock(return_value=(False, "not here"))),
            ),
            patch("fpstune.api.routes.settings._create_restore_point_async"),
        )

    def test_apply_builds_the_context_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        ctx, checker, rp = self._patched(record)
        with ctx, checker, rp:
            response = client.post(
                "/api/settings/network:nagle_algorithm/apply", json={"value": "enabled"}
            )

        assert response.status_code == 200
        assert response.json()["success"] is False  # short-circuited before any write
        assert record["on_event_loop"] is False

    def test_reset_builds_the_context_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        ctx, checker, rp = self._patched(record)
        with ctx, checker, rp:
            response = client.post("/api/settings/network:nagle_algorithm/reset")

        assert response.status_code == 200
        assert record["on_event_loop"] is False

    def test_verify_builds_the_context_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        engine = MagicMock()
        engine.detect_one.return_value = MagicMock(is_applicable=True, error=None, value="enabled")
        with (
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                side_effect=_loop_recorder(record, None),
            ),
            patch("fpstune.api.routes.settings.DetectionEngine", return_value=engine),
        ):
            response = client.post("/api/settings/network:nagle_algorithm/verify")

        assert response.status_code == 200
        assert record["on_event_loop"] is False

    def test_undo_builds_the_context_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        originals = MagicMock()
        originals.get.return_value = "enabled"
        ctx, checker, rp = self._patched(record)
        with (
            ctx,
            checker,
            rp,
            patch("fpstune.api.routes.settings.get_original_values", return_value=originals),
        ):
            response = client.post("/api/settings/network:nagle_algorithm/undo")

        assert response.status_code == 200
        assert record["on_event_loop"] is False


class TestBulkStreamSetupOffload:
    """The SSE handlers resolved the registry and the context before returning
    the StreamingResponse, both inline in the async handler — so a cold start
    held the loop for the whole hardware discovery before a single event."""

    def test_stream_apply_resolves_the_registry_off_the_event_loop(
        self, client: TestClient
    ) -> None:
        record: dict[str, bool] = {}
        registry = MagicMock()
        registry.get.return_value = None
        with (
            patch(
                "fpstune.api.routes.settings_stream._get_registry",
                side_effect=_loop_recorder(record, registry),
            ),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream._create_restore_point_async"),
        ):
            response = client.post("/api/settings/bulk/stream-apply", json={"ids": ["x:y"]})

        assert response.status_code == 200
        assert record["on_event_loop"] is False

    def test_stream_reset_builds_the_context_off_the_event_loop(self, client: TestClient) -> None:
        record: dict[str, bool] = {}
        registry = MagicMock()
        registry.get.return_value = None
        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings_stream._get_hardware_context",
                side_effect=_loop_recorder(record, None),
            ),
            patch("fpstune.api.routes.settings_stream._create_restore_point_async"),
        ):
            response = client.post("/api/settings/bulk/stream-reset", json={"ids": ["x:y"]})

        assert response.status_code == 200
        assert record["on_event_loop"] is False
