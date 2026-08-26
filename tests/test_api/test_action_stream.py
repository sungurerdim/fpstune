"""Tests for the SSE action route (GET /api/settings/actions/{id}/execute).

The route existed with no test at all: nothing exercised the 404/400 guards or
proved that the executor's events actually reach the wire. Subprocess behavior
itself is covered in tests/test_settings/test_action_executor.py; this file
pins the route wiring.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.settings.action_executor import ActionEvent


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestActionStreamRoute:
    def test_unknown_setting_is_404(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with patch("fpstune.api.routes.settings._get_registry", return_value=mock_registry):
            response = client.get("/api/settings/actions/ghost:action/execute")

        assert response.status_code == 404

    def test_non_action_setting_is_400(self, client: TestClient) -> None:
        setting = MagicMock()
        setting.is_action = False

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with patch("fpstune.api.routes.settings._get_registry", return_value=mock_registry):
            response = client.get("/api/settings/actions/core:game_mode/execute")

        assert response.status_code == 400

    def test_the_executors_events_reach_the_wire(self, client: TestClient) -> None:
        setting = MagicMock()
        setting.is_action = True
        setting.display_name = "Fake Maintenance"

        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        async def fake_stream(_setting: object) -> AsyncGenerator[str, None]:
            yield ActionEvent(type="output", line="working on it").to_json()
            yield ActionEvent(type="complete", success=True).to_json()

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=mock_registry),
            patch("fpstune.settings.action_executor.execute_action", new=fake_stream),
        ):
            response = client.get("/api/settings/actions/maintenance:fake/execute")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "working on it" in response.text
        assert "complete" in response.text
