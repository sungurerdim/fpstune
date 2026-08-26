"""Tests for the debug API routes (debug.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helper: build a test client with debug_mode toggled
# ---------------------------------------------------------------------------


def _make_client(*, debug: bool) -> TestClient:
    """Create a TestClient with debug mode enabled or disabled."""
    with (
        patch("fpstune.utils.debug.is_debug_enabled", return_value=debug),
        patch("fpstune.api.main.is_debug_enabled", return_value=debug),
    ):
        from fpstune.api.main import create_app

        app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_debug_off() -> TestClient:
    """TestClient with debug mode disabled (production default)."""
    return _make_client(debug=False)


@pytest.fixture
def client_debug_on() -> TestClient:
    """TestClient with debug mode enabled."""
    return _make_client(debug=True)


# ---------------------------------------------------------------------------
# /api/debug/status — always accessible regardless of debug flag
# ---------------------------------------------------------------------------


class TestDebugStatus:
    """Tests for GET /api/debug/status."""

    def test_status_returns_200(self, client_debug_on: TestClient) -> None:
        with patch(
            "fpstune.api.routes.debug.get_debug_status",
            return_value={
                "enabled": True,
                "entry_count": 0,
                "components": [],
            },
        ):
            response = client_debug_on.get("/api/debug/status")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data

    def test_status_debug_disabled(self, client_debug_on: TestClient) -> None:
        with patch(
            "fpstune.api.routes.debug.get_debug_status",
            return_value={"enabled": False, "entry_count": 0},
        ):
            response = client_debug_on.get("/api/debug/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False


# ---------------------------------------------------------------------------
# /api/debug/entries — GET and DELETE
# ---------------------------------------------------------------------------


class TestDebugEntries:
    """Tests for GET/DELETE /api/debug/entries."""

    def test_get_entries_empty(self, client_debug_on: TestClient) -> None:
        with (
            patch("fpstune.api.routes.debug.get_debug_entries", return_value=[]),
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=False),
        ):
            response = client_debug_on.get("/api/debug/entries")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["entries"] == []

    def test_get_entries_with_data(self, client_debug_on: TestClient) -> None:
        fake_entries = [
            {"timestamp": "2026-01-01T00:00:00", "component": "settings", "message": "applied"},
            {"timestamp": "2026-01-01T00:00:01", "component": "gpu", "message": "detected"},
        ]
        with (
            patch("fpstune.api.routes.debug.get_debug_entries", return_value=fake_entries),
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True),
        ):
            response = client_debug_on.get("/api/debug/entries?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["entries"]) == 2
        assert data["debug_enabled"] is True

    def test_get_entries_component_filter(self, client_debug_on: TestClient) -> None:
        with (
            patch("fpstune.api.routes.debug.get_debug_entries", return_value=[]) as mock_get,
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True),
        ):
            response = client_debug_on.get("/api/debug/entries?component=gpu")

        assert response.status_code == 200
        mock_get.assert_called_once_with(limit=100, component="gpu")

    def test_delete_entries_clears(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.clear_debug_entries") as mock_clear:
            response = client_debug_on.delete("/api/debug/entries")

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_clear.assert_called_once()


# ---------------------------------------------------------------------------
# /api/debug/diagnose/* — Windows-only guard
# ---------------------------------------------------------------------------


class TestDiagnoseEndpointsNonWindows:
    """Tests for diagnose endpoints on non-Windows (should return 400)."""

    def test_diagnose_monitors_non_windows(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.sys") as mock_sys:
            mock_sys.platform = "linux"
            response = client_debug_on.get("/api/debug/diagnose/monitors")

        assert response.status_code == 400

    def test_diagnose_network_non_windows(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.sys") as mock_sys:
            mock_sys.platform = "linux"
            response = client_debug_on.get("/api/debug/diagnose/network")

        assert response.status_code == 400

    def test_diagnose_audio_non_windows(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.sys") as mock_sys:
            mock_sys.platform = "linux"
            response = client_debug_on.get("/api/debug/diagnose/audio")

        assert response.status_code == 400


class TestDiagnoseEndpointsWindows:
    """Tests for diagnose endpoints on Windows (mocked PowerShell)."""

    def test_diagnose_monitors_windows(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch(
                "fpstune.api.routes.debug.run_powershell",
                return_value=(True, '{"Name": "winmgmt", "Status": "Running"}'),
            ):
                response = client_debug_on.get("/api/debug/diagnose/monitors")

        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert "platform" in data
        assert isinstance(data["steps"], list)

    def test_diagnose_network_windows(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch(
                "fpstune.api.routes.debug.run_powershell",
                return_value=(True, '[{"Name": "Ethernet", "Status": "Up"}]'),
            ):
                response = client_debug_on.get("/api/debug/diagnose/network")

        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert len(data["steps"]) > 0

    def test_diagnose_audio_windows(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch(
                "fpstune.api.routes.debug.run_powershell",
                return_value=(True, "[]"),
            ):
                response = client_debug_on.get("/api/debug/diagnose/audio")

        assert response.status_code == 200
        data = response.json()
        assert "steps" in data


class TestDiagnoseSettings:
    """Tests for GET /api/debug/diagnose/settings."""

    def _mock_registry(self) -> MagicMock:
        registry = MagicMock()
        setting_a, setting_b = MagicMock(), MagicMock()
        setting_a.id, setting_b.id = "core:setting_a", "core:setting_b"
        registry.get_all.return_value = [setting_a, setting_b]
        registry.get_categories.return_value = ["core", "timer"]
        return registry

    def _mock_engine(self) -> MagicMock:
        result = MagicMock()
        result.value = "1"
        result.is_applicable = True
        result.applicable_reason = ""
        engine = MagicMock()
        engine.detect_one.return_value = result
        return engine

    def test_diagnose_settings_returns_registry_info(self, client_debug_on: TestClient) -> None:
        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=self._mock_registry()),
            patch("fpstune.settings.detection.DetectionEngine", return_value=self._mock_engine()),
        ):
            response = client_debug_on.get("/api/debug/diagnose/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["settings_count"] == 2
        assert "core" in data["categories"]
        assert [s["id"] for s in data["sample_settings"]] == [
            "core:setting_a",
            "core:setting_b",
        ]

    def test_it_reuses_the_registry_singleton(self, client_debug_on: TestClient) -> None:
        """This route was the last one building its own ``SettingsRegistry()``.

        A fresh one re-runs adapter, monitor and game discovery — seconds of
        PowerShell — for a diagnostic that only reads what is already
        registered, and it did it on the event loop.
        """
        with (
            patch(
                "fpstune.api.routes.settings._get_registry", return_value=self._mock_registry()
            ) as singleton,
            patch("fpstune.settings.registry.SettingsRegistry") as constructed,
            patch("fpstune.settings.detection.DetectionEngine", return_value=self._mock_engine()),
        ):
            assert client_debug_on.get("/api/debug/diagnose/settings").status_code == 200

        singleton.assert_called_once()
        constructed.assert_not_called()

    def test_the_blocking_scan_is_offloaded_from_the_event_loop(
        self, client_debug_on: TestClient
    ) -> None:
        """Twenty synchronous ``detect_one`` calls inside an ``async def`` block
        every other request for as long as they run (issue #21)."""
        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=self._mock_registry()),
            patch("fpstune.settings.detection.DetectionEngine", return_value=self._mock_engine()),
            patch(
                "fpstune.api.routes.debug.asyncio.to_thread", wraps=asyncio.to_thread
            ) as to_thread,
        ):
            assert client_debug_on.get("/api/debug/diagnose/settings").status_code == 200

        assert to_thread.called, "the diagnostic scan still runs on the event loop"

    def test_a_failing_scan_is_reported_not_raised(self, client_debug_on: TestClient) -> None:
        with patch(
            "fpstune.api.routes.settings._get_registry", side_effect=RuntimeError("no registry")
        ):
            response = client_debug_on.get("/api/debug/diagnose/settings")

        assert response.status_code == 200
        assert response.json()["error"] == "no registry"


# ---------------------------------------------------------------------------
# /api/debug/test/powershell — debug-mode gate + allowlist
# ---------------------------------------------------------------------------


class TestPowershellEndpoint:
    """Tests for POST /api/debug/test/powershell."""

    def test_powershell_blocked_when_debug_off(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.is_debug_enabled", return_value=False):
            response = client_debug_on.post("/api/debug/test/powershell?command=Get-Process")

        assert response.status_code == 403

    def test_powershell_allowed_when_debug_on(self, client_debug_on: TestClient) -> None:
        with (
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True),
            patch(
                "fpstune.api.routes.debug.run_powershell",
                return_value=(True, "System.Diagnostics.Process"),
            ),
        ):
            response = client_debug_on.post("/api/debug/test/powershell?command=Get-Process")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "System.Diagnostics.Process" in data["output"]

    def test_powershell_blocked_non_allowlist_command(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True):
            response = client_debug_on.post("/api/debug/test/powershell?command=Set-Item something")

        assert response.status_code == 400

    def test_powershell_blocked_with_dangerous_token(self, client_debug_on: TestClient) -> None:
        with patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True):
            # Starts with Get- but contains a blocked token (|)
            response = client_debug_on.post(
                "/api/debug/test/powershell?command=Get-Process | Stop-Process"
            )

        assert response.status_code == 400

    def test_powershell_command_too_long(self, client_debug_on: TestClient) -> None:
        long_cmd = "Get-Process " + "A" * 5000
        with patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True):
            response = client_debug_on.post(f"/api/debug/test/powershell?command={long_cmd}")

        assert response.status_code == 400

    def test_powershell_safe_test_command(self, client_debug_on: TestClient) -> None:
        with (
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True),
            patch(
                "fpstune.api.routes.debug.run_powershell",
                return_value=(True, "True"),
            ),
        ):
            response = client_debug_on.post(
                "/api/debug/test/powershell?command=Test-Path C:\\Windows"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# /api/debug/test/powershell — allowlist of shapes (issue #20)
# ---------------------------------------------------------------------------


class TestPowershellShapeAllowlist:
    """The denylist this replaced named `iex`, `&`, `;` and `|`, and a
    two-statement command walked past all four: PowerShell ends a statement at a
    bare newline, and `$( )` runs a subexpression without any of them."""

    REFUSED = [
        "Get-Date\nRemove-Item C:\\Windows -Recurse",
        "Get-Date\r\nRemove-Item C:\\Windows",
        "Get-Date\rRemove-Item C:\\Windows",
        "Get-Process $(Remove-Item C:\\Windows)",
        "Get-Process `nRemove-Item",
        "Get-Content 'a' + 'b'",
        'Get-Process "$(hostname)"',
        "Get-Process &whoami",
        "Get-Process; Remove-Item x",
        "Remove-Item C:\\Windows",
        "Get-Process | Stop-Process",
        "   ",
        "Get-Process -Name 'a'; iex 'b'",
    ]

    ALLOWED = [
        "Get-Process",
        "Get-Process -Name explorer",
        "Test-Path C:\\Windows",
        "Get-Service -Name 'Audiosrv'",
        "Write-Output hello",
        "$PSVersionTable",
        "$PSVersionTable.PSVersion",
        "Get-NetAdapter -InterfaceIndex 5",
    ]

    @pytest.mark.parametrize("command", REFUSED)
    def test_refused_command_never_reaches_powershell(
        self, client_debug_on: TestClient, command: str
    ) -> None:
        with (
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True),
            patch("fpstune.api.routes.debug.run_powershell") as run,
        ):
            response = client_debug_on.post(
                "/api/debug/test/powershell", params={"command": command}
            )

        assert response.status_code == 400
        run.assert_not_called()

    @pytest.mark.parametrize("command", ALLOWED)
    def test_read_only_shape_is_still_accepted(
        self, client_debug_on: TestClient, command: str
    ) -> None:
        with (
            patch("fpstune.api.routes.debug.is_debug_enabled", return_value=True),
            patch("fpstune.api.routes.debug.run_powershell", return_value=(True, "ok")) as run,
        ):
            response = client_debug_on.post(
                "/api/debug/test/powershell", params={"command": command}
            )

        assert response.status_code == 200, command
        assert run.call_args.args[0] == command.strip()
