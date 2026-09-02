"""Tests for the display/monitor API routes (display.py)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.utils.winapi.display import DisplayMode


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _no_stray_reverts():
    """Cancel any revert timer a test scheduled.

    A leaked timer would fire after its test's user32 patch is gone and run
    a real mode change against whatever display the fixture named — on the
    machine running the suite.
    """
    yield
    from fpstune.api.routes import display as display_module

    with display_module._pending_lock:
        for pending in display_module._pending_reverts.values():
            pending["timer"].cancel()
        display_module._pending_reverts.clear()


@contextmanager
def _fake_user32(prior, *, test_code: int = 0, write_code: int = 0):
    """Stand in for the two user32 calls the route makes, and log every mode write.

    The route used to run a PowerShell script whose stdout the tests faked; it
    now calls ``winapi.display`` directly, so the fakes sit on those two
    functions. ``calls`` records ("test" | "write", device, width, height, hz).
    """
    from fpstune.api.routes import display as display_module

    calls: list[tuple[str, str, int, int, int]] = []

    def current_mode(_device: str):
        return DisplayMode(*prior) if prior else None

    def change_mode(device, width, height, refresh, _fields, *, test_only):
        calls.append(("test" if test_only else "write", device, width, height, refresh))
        return test_code if test_only else write_code

    with (
        patch.object(display_module.winapi_display, "current_mode", current_mode),
        patch.object(display_module.winapi_display, "change_mode", change_mode),
    ):
        yield calls


def _make_monitor(
    name: str = "DISPLAY1",
    width: int = 2560,
    height: int = 1440,
    refresh_rate_hz: int = 165,
    is_primary: bool = True,
    native_width: int = 2560,
    native_height: int = 1440,
    native_refresh_rate_hz: int = 165,
    max_refresh_rate_hz: int = 165,
    is_resolution_optimal: bool = True,
    is_refresh_optimal: bool = True,
    is_resolution_known: bool = True,
    is_refresh_known: bool = True,
    supports_vrr: bool = True,
    is_active: bool = True,
    friendly_name: str = "ASUS VG27AQ1A",
    hardware_id: str = "GSM5B08",
) -> MagicMock:
    """Build a mock MonitorInfo."""
    m = MagicMock()
    m.name = name
    m.width = width
    m.height = height
    m.refresh_rate_hz = refresh_rate_hz
    m.is_primary = is_primary
    m.native_width = native_width
    m.native_height = native_height
    m.native_refresh_rate_hz = native_refresh_rate_hz
    m.max_refresh_rate_hz = max_refresh_rate_hz
    m.is_resolution_optimal = is_resolution_optimal
    m.is_refresh_optimal = is_refresh_optimal
    m.is_resolution_known = is_resolution_known
    m.is_refresh_known = is_refresh_known
    m.supports_vrr = supports_vrr
    m.is_active = is_active
    m.friendly_name = friendly_name
    m.hardware_id = hardware_id
    return m


# ---------------------------------------------------------------------------
# GET /api/display/monitors
# ---------------------------------------------------------------------------


class TestRefreshDisplays:
    """Tests for POST /api/display/refresh."""

    def test_refresh_returns_monitor_list(self, client: TestClient) -> None:
        monitor = _make_monitor()
        with patch("fpstune.api.routes.display.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
                mock_hw.detect_monitors.return_value = [monitor]
                response = client.post("/api/display/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["monitors"], list)
        assert len(data["monitors"]) == 1

    def test_refresh_invalidates_cache(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.display.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
                mock_hw.detect_monitors.return_value = []
                response = client.post("/api/display/refresh")

        assert response.status_code == 200
        mock_hw.invalidate_cache.assert_called_once_with("monitors")

    def test_refresh_non_windows_returns_empty(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.display.sys") as mock_sys:
            mock_sys.platform = "linux"
            response = client.post("/api/display/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["monitors"] == []


# ---------------------------------------------------------------------------
# POST /api/display/{index}/auto
# ---------------------------------------------------------------------------


class TestSetDisplayAuto:
    """Tests for POST /api/display/{index}/auto."""

    def test_returns_400_on_non_windows(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.display.sys") as mock_sys:
            mock_sys.platform = "linux"
            response = client.post("/api/display/0/auto")

        assert response.status_code == 400

    def test_returns_404_when_index_out_of_range(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.display.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
                mock_hw.detect_monitors.return_value = []
                response = client.post("/api/display/0/auto")

        assert response.status_code == 404

    def test_already_optimal_skips_powershell(self, client: TestClient) -> None:
        monitor = _make_monitor(is_resolution_optimal=True, is_refresh_optimal=True)
        with patch("fpstune.api.routes.display.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
                mock_hw.detect_monitors.return_value = [monitor]
                response = client.post("/api/display/0/auto")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "already at optimal" in data["message"]

    def test_applies_settings_via_user32(self, client: TestClient) -> None:
        monitor = _make_monitor(
            is_resolution_optimal=False,
            is_refresh_optimal=False,
            native_width=2560,
            native_height=1440,
            max_refresh_rate_hz=165,
        )
        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
            _fake_user32((1920, 1080, 60)) as calls,
        ):
            mock_hw.detect_monitors.return_value = [monitor]
            response = client.post("/api/display/0/auto")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["resolution"] == "2560x1440"
        assert data["refresh_rate"] == 165
        assert [c[0] for c in calls] == ["test", "write"]

    def test_index_validation_gt10_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/display/11/auto")
        assert response.status_code == 422

    def test_index_negative_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/display/-1/auto")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/display/vrr-optimization
# ---------------------------------------------------------------------------


class TestVrrOptimizationInfo:
    """Tests for GET /api/display/vrr-optimization."""

    def test_non_nvidia_reports_a_product_gap_never_a_hardware_verdict(
        self, client: TestClient
    ) -> None:
        """A6 / C10: "not built yet" and "not supported" are different claims.

        The old copy told AMD and Intel owners "G-Sync features not available"
        as a fact about their machine, while the panel's VRR answer (EDID) is
        vendor-neutral and was known all along.
        """
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "amd"
        freesync_panel = _make_monitor(supports_vrr=True, max_refresh_rate_hz=165)
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            mock_hw.detect_monitors.return_value = [freesync_panel]
            response = client.get("/api/display/vrr-optimization")

        assert response.status_code == 200
        data = response.json()
        # The panel's own answer survives the vendor gap.
        assert data["supports_vrr"] is True
        assert data["monitor_refresh_hz"] == 165
        # The gap is named as fpstune's, not the hardware's.
        assert "not built yet" in data["explanation"]
        assert "product gap" in data["warning"]
        assert "not available" not in data["warning"]

    def test_no_gpu_returns_unavailable(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (None, False)
            mock_hw.detect_monitors.return_value = []
            response = client.get("/api/display/vrr-optimization")

        assert response.status_code == 200
        data = response.json()
        # No GPU info and no panel probed: VRR support is unknown, not "no".
        assert data["supports_vrr"] is None

    def test_nvidia_no_monitors_returns_no_monitor(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            mock_hw.detect_monitors.return_value = []
            response = client.get("/api/display/vrr-optimization")

        assert response.status_code == 200
        data = response.json()
        assert data["monitor_name"] == "No monitor"

    def test_nvidia_with_vrr_monitor(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"
        monitor = _make_monitor(supports_vrr=True, max_refresh_rate_hz=165)

        mock_executor = MagicMock()
        mock_executor.get_vrr_optimization_info_for_monitor.return_value = {
            "monitor_refresh_hz": 165,
            "supports_vrr": True,
            "recommended_fps_limit": 163,
            "recommended_vrr_mode": "fullscreen",
            "recommended_vsync": "off",
            "explanation": "G-Sync active: cap FPS 2 below refresh to keep VRR range engaged.",
        }
        mock_executor._load_cache.return_value = {
            "fps_limit": 0,
            "vrr_mode": "off",
            "vsync": "off",
        }

        with (
            patch(
                "fpstune.settings.executors.nvprofile.NvProfileExecutor",
                return_value=mock_executor,
            ),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
        ):
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            mock_hw.detect_monitors.return_value = [monitor]
            response = client.get("/api/display/vrr-optimization")

        assert response.status_code == 200
        data = response.json()
        assert data["supports_vrr"] is True
        assert data["monitor_refresh_hz"] == 165
        assert data["recommended_fps_limit"] == 163


# ---------------------------------------------------------------------------
# POST /api/display/vrr-optimization/apply
# ---------------------------------------------------------------------------


class TestApplyVrrOptimization:
    """Tests for POST /api/display/vrr-optimization/apply."""

    def test_non_nvidia_returns_400_naming_the_gap(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "amd"
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            response = client.post(
                "/api/display/vrr-optimization/apply",
                json={"fps_limit": 0, "vrr_mode": "off", "vsync": "off"},
            )

        assert response.status_code == 400
        assert "product gap" in response.json()["detail"]

    def test_invalid_vrr_mode_returns_400(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            response = client.post(
                "/api/display/vrr-optimization/apply",
                json={"fps_limit": 0, "vrr_mode": "invalid_mode", "vsync": "off"},
            )

        assert response.status_code == 400

    def test_invalid_vsync_returns_400(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            response = client.post(
                "/api/display/vrr-optimization/apply",
                json={"fps_limit": 0, "vrr_mode": "off", "vsync": "bad_value"},
            )

        assert response.status_code == 400

    def test_fps_limit_out_of_range_returns_400(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            response = client.post(
                "/api/display/vrr-optimization/apply",
                json={"fps_limit": 999, "vrr_mode": "off", "vsync": "off"},
            )

        assert response.status_code == 400

    def test_successful_apply(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"

        mock_executor = MagicMock()
        mock_executor._load_cache.return_value = {
            "power_mode": "optimal",
            "low_latency": "ultra",
            "threaded_opt": "on",
            "shader_cache": "on",
            "bg_app_fps": 30,
            "aniso_sample_opt": "on",
            "texture_lod_bias": "clamp",
            "ogl_thread_opt": "on",
            "cuda_force_p2": "off",
        }

        mock_nv = MagicMock()
        mock_nv.apply_gaming_profile.return_value = (True, None)

        with (
            patch(
                "fpstune.settings.executors.nvprofile.NvProfileExecutor",
                return_value=mock_executor,
            ),
            patch("fpstune.core.nv_profile.NvidiaProfileInspector", return_value=mock_nv),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
        ):
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            response = client.post(
                "/api/display/vrr-optimization/apply",
                json={"fps_limit": 163, "vrr_mode": "fullscreen", "vsync": "off"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["applied_fps_limit"] == 163
        assert data["applied_vrr_mode"] == "fullscreen"
        assert data["applied_vsync"] == "off"


# ---------------------------------------------------------------------------
# POST /api/display/vrr-optimization/reset
# ---------------------------------------------------------------------------


class TestResetVrrOptimization:
    """Tests for POST /api/display/vrr-optimization/reset."""

    def test_reset_calls_apply_with_defaults(self, client: TestClient) -> None:
        mock_gpu = MagicMock()
        mock_gpu.vendor = MagicMock()
        mock_gpu.vendor.lower.return_value = "nvidia"

        mock_executor = MagicMock()
        mock_executor._load_cache.return_value = {
            "power_mode": "optimal",
            "low_latency": "ultra",
            "threaded_opt": "on",
            "shader_cache": "on",
            "bg_app_fps": 30,
            "aniso_sample_opt": "on",
            "texture_lod_bias": "clamp",
            "ogl_thread_opt": "on",
            "cuda_force_p2": "off",
        }
        mock_nv = MagicMock()
        mock_nv.apply_gaming_profile.return_value = (True, None)

        with (
            patch(
                "fpstune.settings.executors.nvprofile.NvProfileExecutor",
                return_value=mock_executor,
            ),
            patch("fpstune.core.nv_profile.NvidiaProfileInspector", return_value=mock_nv),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
        ):
            mock_hw.get_gpu_info.return_value = (mock_gpu, False)
            response = client.post("/api/display/vrr-optimization/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["applied_fps_limit"] == 0
        assert data["applied_vrr_mode"] == "off"
        assert data["applied_vsync"] == "off"


# ---------------------------------------------------------------------------
# Monitor payload contract (CC-08)
# ---------------------------------------------------------------------------


class TestMonitorPayloadContract:
    """CC-08: /api/hardware and /api/display/refresh must serialize monitors
    identically.

    Three serializers used to exist and the schema one dropped ``is_active``
    and ``hardware_id`` — fields MonitorCard.tsx reads — so a disconnected
    monitor rendered as active until a refresh ran.
    """

    @staticmethod
    def _detected_monitor():  # type: ignore[no-untyped-def]
        from fpstune.utils.detect import MonitorInfo as DetectedMonitor

        return DetectedMonitor(
            name="\\\\.\\DISPLAY1",
            width=2560,
            height=1440,
            refresh_rate_hz=144,
            is_primary=True,
            friendly_name="ASUS VG27AQ1A",
            native_width=2560,
            native_height=1440,
            native_refresh_rate_hz=170,
            max_refresh_rate_hz=170,
            supports_vrr=True,
            is_active=False,
            hardware_id="GSM5B08",
        )

    def _refresh_payload(self, client: TestClient) -> dict:
        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
        ):
            mock_hw.detect_monitors.return_value = [self._detected_monitor()]
            response = client.post("/api/display/refresh")
        assert response.status_code == 200
        return response.json()["monitors"][0]

    def _hardware_payload(self, client: TestClient) -> dict:
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
            mock_hw.detect_cpu.return_value = None
            mock_hw.detect_monitors.return_value = [self._detected_monitor()]
            response = client.get("/api/hardware")
        assert response.status_code == 200
        return response.json()["monitors"][0]

    def test_both_endpoints_serialize_the_same_monitor_identically(
        self, client: TestClient
    ) -> None:
        refresh_mon = self._refresh_payload(client)
        hardware_mon = self._hardware_payload(client)

        assert set(refresh_mon) == set(hardware_mon)
        assert refresh_mon == hardware_mon

    def test_payload_carries_the_fields_the_ui_reads(self, client: TestClient) -> None:
        for payload in (self._refresh_payload(client), self._hardware_payload(client)):
            # A monitor detached in Windows settings must not render as active.
            assert payload["is_active"] is False
            # C5 stable identifier the card shows next to the device name.
            assert payload["hardware_id"] == "GSM5B08"


# ---------------------------------------------------------------------------
# POST /api/display/{index}/auto — the two write guards (A10)
# ---------------------------------------------------------------------------


class TestModeWriteGuards:
    """A wrong mode on a friend's machine is a black screen nobody can debug.

    Two guards: CDS_TEST validates the mode before anything is written, and a
    revert timer writes the prior mode back unless the user keeps the change.
    A change whose prior mode could not be read is refused outright — a write
    that cannot be undone is a one-way door.
    """

    def _suboptimal(self) -> MagicMock:
        return _make_monitor(
            name="\\.\\DISPLAY7",
            refresh_rate_hz=60,
            is_refresh_optimal=False,
            native_width=2560,
            native_height=1440,
            max_refresh_rate_hz=165,
        )

    def _post(self, client: TestClient, prior, *, test_code: int = 0, write_code: int = 0):
        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
            _fake_user32(prior, test_code=test_code, write_code=write_code) as calls,
        ):
            mock_hw.detect_monitors.return_value = [self._suboptimal()]
            response = client.post("/api/display/0/auto")
        return response, calls

    def test_a_mode_the_driver_rejects_is_never_written(self, client: TestClient) -> None:
        """CDS_TEST said no; the endpoint reports it and nothing changed."""
        response, calls = self._post(client, (1920, 1080, 60), test_code=-5)
        assert response.status_code == 409
        assert "Nothing was changed" in response.json()["detail"]
        assert [c[0] for c in calls] == ["test"]

    def test_the_test_call_precedes_the_write(self, client: TestClient) -> None:
        """The driver validates before anything is written — the order is the safety."""
        _, calls = self._post(client, (1920, 1080, 60))
        assert [c[0] for c in calls] == ["test", "write"]

    def test_an_unreadable_prior_mode_refuses_the_change(self, client: TestClient) -> None:
        """No mode to revert to means no write happens at all."""
        response, calls = self._post(client, None)
        assert response.status_code == 500
        assert "one-way door" in response.json()["detail"]
        assert calls == []

    def test_a_successful_write_awaits_confirmation(self, client: TestClient) -> None:
        response, _ = self._post(client, (1920, 1080, 60))
        assert response.status_code == 200
        data = response.json()
        assert data["requires_confirmation"] is True
        assert data["revert_timeout_s"] is not None

    def test_no_confirmation_reverts_to_the_prior_mode(self, client: TestClient) -> None:
        """The gate: the timer fires and writes back exactly what was read."""
        import time

        from fpstune.api.routes import display as display_module

        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
            patch.object(display_module, "_REVERT_TIMEOUT_S", 0.05),
            _fake_user32((1920, 1080, 60)) as calls,
        ):
            mock_hw.detect_monitors.return_value = [self._suboptimal()]
            response = client.post("/api/display/0/auto")
            assert response.status_code == 200
            deadline = time.monotonic() + 2.0
            while sum(c[0] == "write" for c in calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            writes = [c for c in calls if c[0] == "write"]
            assert len(writes) == 2, "the revert never ran"
            # The revert writes back exactly the mode the apply read out.
            assert writes[1][2:] == (1920, 1080, 60)

    def test_confirmation_keeps_the_mode_and_cancels_the_revert(self, client: TestClient) -> None:
        import time

        from fpstune.api.routes import display as display_module

        with (
            patch("fpstune.api.routes.display.sys.platform", "win32"),
            patch("fpstune.api.routes.display.hardware_manager") as mock_hw,
            patch.object(display_module, "_REVERT_TIMEOUT_S", 0.2),
            _fake_user32((1920, 1080, 60)) as calls,
        ):
            mock_hw.detect_monitors.return_value = [self._suboptimal()]
            assert client.post("/api/display/0/auto").status_code == 200
            confirm = client.post("/api/display/0/confirm")
            assert confirm.status_code == 200
            time.sleep(0.4)
            assert sum(c[0] == "write" for c in calls) == 1, "the cancelled revert still ran"

    def test_confirming_with_nothing_pending_is_a_404(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.display.hardware_manager") as mock_hw:
            mock_hw.detect_monitors.return_value = [self._suboptimal()]
            response = client.post("/api/display/0/confirm")
        assert response.status_code == 404
