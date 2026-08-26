"""Tests for GPU API routes (gpu.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /api/gpu/detect
# ---------------------------------------------------------------------------


class TestGpuDetect:
    """Tests for GET /api/gpu/detect."""

    def test_nvidia_gpu_detected(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        mock_gpu = MagicMock()
        mock_gpu.vendor = GpuVendor.NVIDIA  # real enum; .value == "nvidia"
        mock_gpu.name = "NVIDIA GeForce RTX 4090"
        mock_gpu.driver_version = "555.42"
        mock_gpu.vram_mb = 24576

        with patch("fpstune.api.routes.gpu.get_gpu_info", return_value=mock_gpu):
            response = client.get("/api/gpu/detect")

        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "nvidia"
        assert data["name"] == "NVIDIA GeForce RTX 4090"
        assert data["driver_version"] == "555.42"
        assert data["vram_mb"] == 24576

    def test_amd_gpu_detected(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        mock_gpu = MagicMock()
        mock_gpu.vendor = GpuVendor.AMD  # real enum; .value == "amd"
        mock_gpu.name = "AMD Radeon RX 7900 XTX"
        mock_gpu.driver_version = "24.3.1"
        mock_gpu.vram_mb = 24576

        with patch("fpstune.api.routes.gpu.get_gpu_info", return_value=mock_gpu):
            response = client.get("/api/gpu/detect")

        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "amd"

    def test_no_gpu_returns_unknown(self, client: TestClient) -> None:
        with patch("fpstune.api.routes.gpu.get_gpu_info", return_value=None):
            response = client.get("/api/gpu/detect")

        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "unknown"


# ---------------------------------------------------------------------------
# GET /api/gpu/settings
# ---------------------------------------------------------------------------


class TestGpuSettings:
    """Tests for GET /api/gpu/settings."""

    def test_unknown_vendor_returns_empty_settings(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        with patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.UNKNOWN):
            response = client.get("/api/gpu/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "unknown"
        assert data["settings"] == {}

    def test_nvidia_vendor_returns_settings(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        mock_registry = MagicMock()
        mock_nvidia_setting = MagicMock()
        mock_nvidia_setting.id = "gpu-nvidia:low_latency"
        mock_registry.get_all.return_value = [mock_nvidia_setting]

        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.value = "ultra"
        mock_engine.detect_all.return_value = {"gpu-nvidia:low_latency": mock_result}

        with (
            patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.NVIDIA),
            patch("fpstune.api.routes.gpu._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.gpu.DetectionEngine", return_value=mock_engine),
        ):
            response = client.get("/api/gpu/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "nvidia"
        assert "low_latency" in data["settings"]
        assert data["settings"]["low_latency"] == "ultra"


# ---------------------------------------------------------------------------
# POST /api/gpu/nvidia/apply
# ---------------------------------------------------------------------------


class TestGpuNvidiaApply:
    """Tests for POST /api/gpu/nvidia/apply."""

    def test_no_nvidia_gpu_returns_400(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        with patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.AMD):
            response = client.post(
                "/api/gpu/nvidia/apply",
                json={
                    "low_latency": "ultra",
                    "power_mode": "maximum",
                    "threaded_opt": "auto",
                    "shader_cache": "on",
                    "vsync": "off",
                },
            )

        assert response.status_code == 400

    def test_nvidia_applies_successfully(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        mock_registry = MagicMock()
        mock_setting = MagicMock()
        mock_setting.requires_reboot = False
        mock_registry.get.return_value = mock_setting

        ok = MagicMock()
        ok.success = True
        ok.requires_reboot = False
        ok.error = None

        with (
            patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.NVIDIA),
            patch("fpstune.api.routes.gpu._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.gpu._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.gpu._apply_one", return_value=("id", ok)),
        ):
            response = client.post(
                "/api/gpu/nvidia/apply",
                json={
                    "low_latency": "ultra",
                    "power_mode": "maximum",
                    "threaded_opt": "auto",
                    "shader_cache": "on",
                    "vsync": "off",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "message" in data

    def test_nvidia_apply_unknown_setting(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # setting not found

        with (
            patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.NVIDIA),
            patch("fpstune.api.routes.gpu._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.gpu._get_hardware_context", return_value=None),
        ):
            response = client.post(
                "/api/gpu/nvidia/apply",
                json={"low_latency": "ultra"},
            )

        assert response.status_code == 200
        data = response.json()
        # All settings are unknown → errors dict is non-empty, success=False
        assert data["success"] is False


# ---------------------------------------------------------------------------
# POST /api/gpu/amd/apply
# ---------------------------------------------------------------------------


class TestGpuAmdApply:
    """Tests for POST /api/gpu/amd/apply."""

    def test_no_amd_gpu_returns_400(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        with patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.NVIDIA):
            response = client.post(
                "/api/gpu/amd/apply",
                json={"anti_lag": "enabled", "shader_cache": "enabled", "vsync": "off"},
            )

        assert response.status_code == 400

    def test_amd_applies_successfully(self, client: TestClient) -> None:
        from fpstune.utils.detect import GpuVendor

        mock_registry = MagicMock()
        mock_setting = MagicMock()
        mock_setting.requires_reboot = False
        mock_registry.get.return_value = mock_setting

        ok = MagicMock()
        ok.success = True
        ok.requires_reboot = False
        ok.error = None

        with (
            patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.AMD),
            patch("fpstune.api.routes.gpu._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.gpu._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.gpu._apply_one", return_value=("id", ok)),
        ):
            response = client.post(
                "/api/gpu/amd/apply",
                json={"anti_lag": "enabled", "shader_cache": "enabled", "vsync": "off"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data


# ---------------------------------------------------------------------------
# POST /api/gpu/apply (auto-detect vendor)
# ---------------------------------------------------------------------------


class TestGpuApplyAutoDetect:
    """Tests for POST /api/gpu/apply (vendor auto-detection)."""

    def test_unknown_vendor_returns_400_like_the_vendor_routes(self, client: TestClient) -> None:
        """One condition, one shape.

        ``/nvidia/apply`` and ``/amd/apply`` have always answered 400 for a
        vendor they cannot serve; ``/apply`` answered 200 with a
        ``success=False`` body, so a client had to branch on the status code to
        know which of the two shapes it was about to parse.
        """
        from fpstune.utils.detect import GpuVendor

        with patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.UNKNOWN):
            response = client.post(
                "/api/gpu/apply",
                params={"low_latency": "ultra", "power_mode": "maximum", "vsync": "off"},
            )

        assert response.status_code == 400
        assert "No supported GPU" in response.json()["detail"]

    def test_a_value_outside_the_setting_choices_is_rejected(self, client: TestClient) -> None:
        """The query params are typed against the settings' own choices.

        gpu.py declared its own request models with bare ``str`` fields, so an
        arbitrary value reached the apply path and was only caught deeper down —
        or, for ``/apply``, was passed straight into the canonical model and
        raised a validation error inside the handler.
        """
        response = client.post("/api/gpu/apply", params={"low_latency": "turbo"})

        assert response.status_code == 422


class TestRequestModelsAreTheCanonicalOnes:
    """gpu.py declared its own copies of three payloads that api/schemas.py
    already owned. The copies drifted: bare ``str`` where the canonical models
    use ``Literal``, and an AMD request that never grew ``anti_lag_2``, so the
    two declarations disagreed about which fields the same endpoint accepts."""

    def test_the_route_models_are_the_schema_models(self) -> None:
        from fpstune.api import schemas
        from fpstune.api.routes import gpu

        assert gpu.GpuDetectResponse is schemas.GpuDetectResponse
        assert gpu.GpuNvidiaApplyRequest is schemas.GpuNvidiaApplyRequest
        assert gpu.GpuAmdApplyRequest is schemas.GpuAmdApplyRequest

    def test_amd_apply_accepts_anti_lag_2(self, client: TestClient) -> None:
        """The field the local copy was missing must reach the endpoint."""
        from fpstune.utils.detect import GpuVendor

        seen: dict[str, object] = {}

        def _capture(_prefix: str, settings_map: dict[str, object]):
            seen.update(settings_map)
            from fpstune.api.routes.gpu import GpuApplyResponse

            return GpuApplyResponse(success=True, message="ok")

        with (
            patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.AMD),
            patch("fpstune.api.routes.gpu._apply_gpu_settings", side_effect=_capture),
        ):
            response = client.post(
                "/api/gpu/amd/apply",
                json={
                    "anti_lag": "enabled",
                    "anti_lag_2": "on",
                    "shader_cache": "enabled",
                    "vsync": "off",
                },
            )

        assert response.status_code == 200
        assert seen["anti_lag_2"] == "on"

    def test_anti_lag_2_is_not_forwarded_when_the_caller_never_asked(
        self, client: TestClient
    ) -> None:
        """No ``gpu-amd:anti_lag_2`` executor is registered yet, so forwarding
        the field's default would make every AMD apply report an unknown-setting
        failure on hardware that is working fine."""
        from fpstune.utils.detect import GpuVendor

        seen: dict[str, object] = {}

        def _capture(_prefix: str, settings_map: dict[str, object]):
            seen.update(settings_map)
            from fpstune.api.routes.gpu import GpuApplyResponse

            return GpuApplyResponse(success=True, message="ok")

        with (
            patch("fpstune.api.routes.gpu.get_gpu_vendor", return_value=GpuVendor.AMD),
            patch("fpstune.api.routes.gpu._apply_gpu_settings", side_effect=_capture),
        ):
            response = client.post("/api/gpu/amd/apply", json={"vsync": "off"})

        assert response.status_code == 200
        assert "anti_lag_2" not in seen


# ---------------------------------------------------------------------------
# Verify after apply (ARCH-13 regression)
# ---------------------------------------------------------------------------


class TestVerifyAfterApply:
    """gpu.py used to call CommandExecutor.apply directly and never read the
    value back, so a write the driver silently rejected was reported as
    applied. Every GPU apply now runs through _apply_one, whose
    _finalize_apply_response detects, verifies and logs — this class pins the
    read-back to the response.
    """

    def _setting(self):
        from fpstune.settings.base import (
            DetectType,
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )

        # A real SettingExecutor: a MagicMock's truthy is_action/is_readonly
        # would make _verify_setting_applied skip the very check under test.
        return SettingExecutor(
            id="gpu-nvidia:vsync",
            category=SettingCategory.GPU,
            display_name="Vertical Sync",
            description="Driver-level vertical sync. Off removes a frame of queueing latency.",
            value_type=SettingValueType.CHOICE,
            choices=("off", "on"),
            default_value="on",
            recommended_value="off",
            detect_type=DetectType.REGISTRY,
            detect_command="",
            detect_args={},
            apply_type=DetectType.REGISTRY,
            apply_command="",
            apply_args={},
        )

    def _run(self, detected_value: str):
        from fpstune.api.routes.gpu import _apply_gpu_settings

        setting = self._setting()
        registry = MagicMock()
        registry.get.return_value = setting

        readback = MagicMock()
        readback.value = detected_value
        engine = MagicMock()
        engine.detect_one.return_value = readback

        with (
            patch("fpstune.api.routes.gpu._get_registry", return_value=registry),
            patch("fpstune.api.routes.gpu._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings.CommandExecutor") as cmd,
            patch("fpstune.api.routes.settings.DetectionEngine", return_value=engine),
        ):
            cmd.apply.return_value = (True, None)  # the write itself claims success
            response = _apply_gpu_settings("gpu-nvidia", {"vsync": "off"})
        return response, engine

    def test_a_write_that_did_not_land_is_reported_failed(self) -> None:
        # The apply returned success but the read-back still holds the old
        # value — the exact silent failure the direct-apply path used to
        # report as applied.
        response, engine = self._run(detected_value="on")

        assert response.success is False
        assert "Verification failed" in response.errors["vsync"]
        assert response.applied == {}
        engine.detect_one.assert_called_once()

    def test_a_verified_write_is_reported_applied(self) -> None:
        response, engine = self._run(detected_value="off")

        assert response.success is True
        assert response.applied == {"vsync": "off"}
        assert response.errors == {}
        engine.detect_one.assert_called_once()
