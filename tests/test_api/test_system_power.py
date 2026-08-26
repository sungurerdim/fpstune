"""The power-profile routes: a failed powercfg call must never read as success.

`activate` and `revert` run elevated powercfg through PowerProfileManager. The
route layer decides what a failure becomes: an HTTP 500 carrying the manager's
own message, or — the failure these tests guard against — a 200 with
success=True over a profile that was never created.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _manager(**overrides) -> MagicMock:
    manager = MagicMock()
    manager.status.return_value = {
        "active_plan": "Balanced",
        "active_guid": "381b4222-f694-41f0-9685-ff5bb260df2e",
        "fps_balanced_exists": True,
        "fps_balanced_active": False,
        "optimizations": ["usb_suspend_off"],
    }
    for key, value in overrides.items():
        setattr(manager, key, value)
    return manager


class TestPowerProfileStatus:
    def test_status_reports_what_the_manager_read(self, client) -> None:
        manager = _manager()
        with patch("fpstune.core.power_profile.get_power_profile_manager", return_value=manager):
            response = client.get("/api/power-profile/status")

        assert response.status_code == 200
        body = response.json()
        assert body["active_plan"] == "Balanced"
        assert body["fps_balanced_exists"] is True
        assert body["fps_balanced_active"] is False
        assert body["optimizations"] == ["usb_suspend_off"]

    def test_a_sparse_status_gets_honest_defaults(self, client) -> None:
        """A manager that could not read powercfg returns a bare dict; the
        route must answer 'Unknown', never KeyError into a 500."""
        manager = _manager()
        manager.status.return_value = {}
        with patch("fpstune.core.power_profile.get_power_profile_manager", return_value=manager):
            response = client.get("/api/power-profile/status")

        assert response.status_code == 200
        body = response.json()
        assert body["active_plan"] == "Unknown"
        assert body["fps_balanced_exists"] is False


class TestActivateAndRevert:
    def test_activate_failure_is_a_500_with_the_managers_words(self, client) -> None:
        """powercfg failing (not elevated, GUID collision) must surface as an
        error carrying the manager's message — not a green success the UI
        would toast."""
        result = MagicMock(success=False, message="powercfg -duplicatescheme failed")
        manager = _manager()
        manager.activate.return_value = result

        with patch("fpstune.core.power_profile.get_power_profile_manager", return_value=manager):
            response = client.post("/api/power-profile/activate")

        assert response.status_code == 500
        assert "powercfg -duplicatescheme failed" in response.json()["detail"]

    def test_activate_success_carries_the_profile_guid(self, client) -> None:
        result = MagicMock(
            success=True, message="activated", profile_guid="11111111-2222-3333-4444-555555555555"
        )
        manager = _manager()
        manager.activate.return_value = result

        with patch("fpstune.core.power_profile.get_power_profile_manager", return_value=manager):
            response = client.post("/api/power-profile/activate")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["profile_guid"] == "11111111-2222-3333-4444-555555555555"

    def test_revert_failure_is_a_500(self, client) -> None:
        result = MagicMock(success=False, message="Balanced scheme not found")
        manager = _manager()
        manager.revert.return_value = result

        with patch("fpstune.core.power_profile.get_power_profile_manager", return_value=manager):
            response = client.post("/api/power-profile/revert")

        assert response.status_code == 500
        assert "Balanced scheme not found" in response.json()["detail"]

    def test_revert_success_says_so(self, client) -> None:
        result = MagicMock(success=True, message="reverted to Balanced")
        manager = _manager()
        manager.revert.return_value = result

        with patch("fpstune.core.power_profile.get_power_profile_manager", return_value=manager):
            response = client.post("/api/power-profile/revert")

        assert response.status_code == 200
        assert response.json()["success"] is True
