"""Tests for API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestRootEndpoints:
    """Tests for root endpoints."""

    def test_root(self, client):
        """Test root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "fpstune" in data["name"].lower()

    def test_health(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestSystemEndpoints:
    """Tests for system endpoints."""

    @patch("fpstune.api.routes.system.hardware_manager")
    @patch("fpstune.api.routes.system.get_gpu_info_cached")
    @patch("fpstune.api.routes.system.get_cpu_info")
    @patch("fpstune.api.routes.system.get_ram_info")
    @patch("fpstune.api.routes.system.is_admin")
    def test_system_info(
        self,
        mock_admin,
        mock_ram,
        mock_cpu,
        mock_gpu_cached,
        mock_hw_manager,
        client,
    ):
        """Test system info endpoint."""
        from fpstune.utils.detect import GpuVendor

        mock_hw_manager.detect_os.return_value = MagicMock(
            platform="win32",
            version="10.0.22621",
            build="22621",
            edition="Windows 11 Pro",
            display_version="24H2",
            is_supported=True,
        )
        # get_gpu_info_cached returns (gpu_info, is_detecting)
        gpu_mock = MagicMock()
        gpu_mock.vendor = GpuVendor.NVIDIA
        gpu_mock.name = "RTX 4080"
        gpu_mock.driver_version = "555.42"
        gpu_mock.vram_mb = 16384
        mock_gpu_cached.return_value = (gpu_mock, False)
        mock_cpu.return_value = {"cpu_name": "Intel Core i7", "core_count": "8"}
        mock_ram.return_value = {"total_mb": 32768, "available_mb": 16384}
        mock_admin.return_value = True

        response = client.get("/api/system")

        assert response.status_code == 200
        data = response.json()
        assert data["os_platform"] == "win32"
        assert data["is_admin"] is True
        assert data["gpu_vendor"] == "nvidia"


class TestModuleMetadataIsConsistent:
    """One condition may not have two answers.

    ``/modules/metadata`` generated a title-cased stand-in for a module with no
    ``MODULE_METADATA`` entry while ``/modules/{id}/metadata`` answered 404 for
    the same id. That fallback is also what hid ``game_cleanup`` shipping twelve
    settings with no declared metadata and no test noticing.
    """

    def _registry_shipping(self, module_id: str):
        """A registry holding one setting under a module nobody declared."""
        setting = MagicMock()
        setting.module = module_id
        registry = MagicMock()
        registry.get_all.return_value = [setting]
        return patch("fpstune.api.routes.settings._get_registry", return_value=registry)

    def test_a_module_that_ships_nothing_is_still_404(self, client):
        with self._registry_shipping("undeclared_module"):
            response = client.get("/api/settings/modules/no_such_module/metadata")

        assert response.status_code == 404

    def test_the_missing_entry_is_named_rather_than_papered_over(self, client):
        with (
            self._registry_shipping("undeclared_module"),
            patch("fpstune.api.routes.settings.logger") as log,
        ):
            assert client.get("/api/settings/modules/metadata").status_code == 200

        assert "undeclared_module" in str(log.warning.call_args)

    def test_every_shipped_module_is_declared(self):
        """The gap ``modules_missing_metadata`` was written to expose was
        ``game_cleanup``: twelve shipped settings rendered under a generated
        title. Declaring it closed that instance; this closes the class, so the
        next module to ship settings without an entry goes red here rather than
        reaching the UI under a title-cased id."""
        from fpstune.api.routes.settings import _get_registry, modules_missing_metadata

        active = {s.module for s in _get_registry().get_all()}

        assert modules_missing_metadata(active) == []


class TestBenchmarkEndpoints:
    """Tests for benchmark endpoints."""
