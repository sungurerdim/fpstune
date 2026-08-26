"""Tests for API detection endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestSettingsDefinitions:
    """Tests for settings definitions endpoint."""

    def test_get_definitions(self, client):
        """Test getting setting definitions."""
        response = client.get("/api/settings/definitions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestSettingsDetection:
    """Tests for settings detection endpoints."""

    def test_detect_settings(self, client):
        """Test detecting all settings."""
        response = client.post("/api/settings/detect", json={})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_time_ms" in data
        assert "success_count" in data

    def test_detect_by_category(self, client):
        """Test detecting settings by category."""
        response = client.post("/api/settings/detect", json={"category": "timer"})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data


class TestSettingsApply:
    """Tests for settings apply endpoints."""

    def test_apply_unknown_setting(self, client):
        """Test applying unknown setting returns 404."""
        response = client.post(
            "/api/settings/unknown_setting_xyz/apply",
            json={"value": "test"},
        )
        assert response.status_code == 404

    def test_revert_unknown_setting(self, client):
        """Test reverting unknown setting returns 404."""
        response = client.post("/api/settings/unknown_setting_xyz/revert")
        assert response.status_code == 404


class TestDetectionModule:
    """Tests for detection module (internal)."""

    def test_detection_result_structure(self):
        """Test DetectionResult structure."""
        from fpstune.settings.base import DetectionResult

        result = DetectionResult(
            setting_id="test:setting",
            value="test_value",
            error=None,
            time_ms=100,
            is_optimized=True,
            is_applicable=True,
        )

        assert result.setting_id == "test:setting"
        assert result.value == "test_value"
        assert result.success is True  # Computed property: error is None
        assert result.is_optimized is True
        assert result.is_applicable is True


class TestApplicabilitySystem:
    """Tests for the applicability system."""

    def test_hardware_context_structure(self):
        """Test HardwareContext structure."""
        from fpstune.settings.applicability import HardwareContext

        context = HardwareContext(
            gpu_vendor="nvidia",
            gpu_vendors=["nvidia"],
            windows_build=22000,
            is_windows_11=True,
            is_admin=True,
        )

        assert context.gpu_vendor == "nvidia"
        assert context.is_windows_11 is True
        assert context.is_admin is True

    def test_applicability_checker_no_conditions(self):
        """Test ApplicabilityChecker with no conditions."""
        from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
        from fpstune.settings.base import (
            DetectType,
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )

        context = HardwareContext()
        checker = ApplicabilityChecker(context)

        setting = SettingExecutor(
            id="test:setting",
            category=SettingCategory.CORE,
            display_name="Test",
            description="Test setting",
            value_type=SettingValueType.BOOL,
            default_value=False,
            recommended_value=True,
            detect_type=DetectType.REGISTRY,
            detect_command="",
            apply_type=DetectType.REGISTRY,
            apply_command="",
        )

        is_applicable, reason = checker.is_applicable(setting)
        assert is_applicable is True
        assert reason == ""

    def test_applicability_checker_gpu_condition(self):
        """Test ApplicabilityChecker with GPU condition."""
        from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
        from fpstune.settings.base import (
            DetectType,
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )

        context = HardwareContext(gpu_vendor="amd")
        checker = ApplicabilityChecker(context)

        setting = SettingExecutor(
            id="test:nvidia_only",
            category=SettingCategory.GPU,
            display_name="NVIDIA Only",
            description="Test setting",
            value_type=SettingValueType.BOOL,
            default_value=False,
            recommended_value=True,
            detect_type=DetectType.REGISTRY,
            detect_command="",
            apply_type=DetectType.REGISTRY,
            apply_command="",
            applicable_conditions={"gpu_vendor": "nvidia"},
        )

        is_applicable, reason = checker.is_applicable(setting)
        assert is_applicable is False
        assert "NVIDIA" in reason
