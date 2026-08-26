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

    @patch("fpstune.api.routes.system.get_cached_status")
    @patch("fpstune.api.routes.system.start_background_update")
    def test_status_empty_modules(self, mock_start, mock_get_cached, client):
        """Test status with no modules."""
        from fpstune.api.status_cache import CachedStatus

        mock_start.return_value = None
        mock_get_cached.return_value = (
            CachedStatus(
                modules={},
                applied_count=0,
                total_count=0,
            ),
            False,  # is_loading
        )

        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert data["total_count"] == 0


class TestStatusCacheHandoff:
    """``status_cache`` hands ``/api/status`` plain dicts, not a typed object.

    ``ModuleSettingResponse(**s)`` therefore dropped every key the model does
    not declare without a word — which is how ``is_optimized`` reached the
    client as nothing for as long as the model had no field for it. The model
    declares it now, and the receiving end reports any key it still has to drop.
    """

    def _cached(self, setting: dict):
        from fpstune.api.status_cache import CachedStatus, ModuleInfo

        return CachedStatus(
            modules={
                "network": ModuleInfo(
                    name="network",
                    display_name="Network",
                    description="1 settings in this category",
                    status="not_applied",
                    message="0/1 optimized",
                    details=[],
                    changes={},
                    is_available=True,
                    requires_reboot=False,
                    settings=[setting],
                )
            },
            applied_count=0,
            total_count=1,
        )

    def _base_setting(self) -> dict:
        return {
            "name": "network:nagle_algorithm",
            "display_name": "Nagle's Algorithm (TcpNoDelay)",
            "description": "TCP small-packet batching.",
            "current_value": "enabled",
            "recommended_value": "enabled",
            "value_type": "choice",
            "choices": ["enabled", "disabled"],
            "requires_reboot": False,
            "current_impact": "Enabled: batching on",
            "recommended_impact": "Enabled: batching on",
            "default_value": "enabled",
            "is_optimized": True,
        }

    def _get(self, client, setting: dict):
        with (
            patch("fpstune.api.routes.system.start_background_update"),
            patch(
                "fpstune.api.routes.system.get_cached_status",
                return_value=(self._cached(setting), False),
            ),
        ):
            return client.get("/api/status")

    def test_the_cache_row_arrives_whole(self, client):
        """Every key ``_cached_setting`` produces reaches the client.

        ``is_optimized`` is the one that did not: the model had no field for it,
        so pydantic dropped it and the UI derived per-module counts from a flag
        that was never sent. ``True`` here rather than the model's ``False``
        default is what tells the round trip apart from the drop.
        """
        row = self._base_setting()

        # The project logger does not propagate to root (it writes through the
        # Rich console), so caplog sees nothing; the handler is the assertion.
        with patch("fpstune.api.routes.system.logger") as log:
            response = self._get(client, row)

        assert response.status_code == 200
        log.warning.assert_not_called()
        setting = response.json()["modules"][0]["settings"][0]
        assert setting["name"] == "network:nagle_algorithm"
        assert row["is_optimized"] is True
        assert setting["is_optimized"] is True
        assert set(row) <= set(setting)

    def test_an_undeclared_producer_key_is_reported(self, client):
        """The next field status_cache grows must not vanish in silence."""
        from fpstune.api.routes import system

        system._reported_unknown_cache_keys.clear()
        setting = self._base_setting()
        setting["evidence_level"] = "proven"

        with patch("fpstune.api.routes.system.logger") as log:
            response = self._get(client, setting)

        assert response.status_code == 200
        assert "evidence_level" in str(log.warning.call_args)


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

    def test_an_undeclared_active_module_gets_the_same_answer_from_both(self, client):
        with self._registry_shipping("undeclared_module"):
            from_list = client.get("/api/settings/modules/metadata").json()
            by_id = client.get("/api/settings/modules/undeclared_module/metadata")

        assert by_id.status_code == 200
        assert from_list == [by_id.json()]
        assert by_id.json()["display_name"] == "Undeclared Module"

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

    def test_benchmark_status(self, client):
        """Test benchmark status endpoint."""
        with patch("fpstune.api.routes.benchmark.BenchmarkRunner") as mock:
            mock.return_value.list_results.return_value = []

            response = client.get("/api/benchmark/status")

            assert response.status_code == 200
            data = response.json()
            assert "saved_results" in data
