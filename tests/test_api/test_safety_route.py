"""Tests for the safety API route (safety.py).

The manifest-based backup/revert endpoints were removed along with their
implementation; System Restore is the supported rollback path.
"""

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
# POST /api/restore-point
# ---------------------------------------------------------------------------


class TestCreateRestorePoint:
    """Tests for POST /api/restore-point."""

    def test_not_available_returns_failure(self, client: TestClient) -> None:
        mock_rp = MagicMock()
        mock_rp.is_available = False

        with patch("fpstune.api.routes.safety.RestorePointManager", return_value=mock_rp):
            response = client.post("/api/restore-point")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not available" in data["message"].lower()

    def test_create_succeeds(self, client: TestClient) -> None:
        mock_rp = MagicMock()
        mock_rp.is_available = True
        mock_rp.create_restore_point.return_value = True

        with (
            patch("fpstune.api.routes.safety.RestorePointManager", return_value=mock_rp),
            patch("fpstune.api.routes.safety.log_activity"),
        ):
            response = client.post("/api/restore-point")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "created" in data["message"].lower()

    def test_create_fails(self, client: TestClient) -> None:
        mock_rp = MagicMock()
        mock_rp.is_available = True
        mock_rp.create_restore_point.return_value = False

        with (
            patch("fpstune.api.routes.safety.RestorePointManager", return_value=mock_rp),
            patch("fpstune.api.routes.safety.log_activity"),
        ):
            response = client.post("/api/restore-point")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_custom_description_passed_through(self, client: TestClient) -> None:
        mock_rp = MagicMock()
        mock_rp.is_available = True
        mock_rp.create_restore_point.return_value = True

        with (
            patch("fpstune.api.routes.safety.RestorePointManager", return_value=mock_rp),
            patch("fpstune.api.routes.safety.log_activity"),
        ):
            response = client.post("/api/restore-point?description=before+major+changes")

        assert response.status_code == 200
        mock_rp.create_restore_point.assert_called_once_with("before major changes")


class TestRemovedBackupEndpointsAreGone:
    """The removed endpoints must not linger as stubs returning success."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/backups"),
            ("post", "/api/backup"),
            ("post", "/api/restore"),
            ("delete", "/api/backups/backup_20260101_120000"),
            ("post", "/api/backups/backup_20260101_120000/restore"),
        ],
    )
    def test_endpoint_no_longer_registered(
        self, client: TestClient, method: str, path: str
    ) -> None:
        response = getattr(client, method)(path)
        assert response.status_code == 404
