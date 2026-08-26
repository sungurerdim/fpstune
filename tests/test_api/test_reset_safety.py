"""Reset must carry the same rollback safety net as apply.

Reset writes to the registry / powercfg / BCD exactly like apply does, so a bad
reset is just as hard to undo. The apply paths created a system restore point;
the reset paths did not.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.schemas import ApplyResponse


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _fake_setting(setting_id: str = "core:fake_reset"):
    s = MagicMock()
    s.id = setting_id
    s.display_name = "Fake Reset"
    s.default_value = "0"
    s.recommended_value = "1"
    s.requires_reboot = False
    s.apply_type = MagicMock()
    s.apply_type.value = "registry"
    s.apply_args = {}
    return s


class TestResetCreatesRestorePoint:
    def test_single_reset_creates_restore_point(self, client: TestClient) -> None:
        setting = _fake_setting()
        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        response_obj = ApplyResponse(
            setting_id=setting.id,
            success=True,
            error=None,
            new_value="0",
            requires_reboot=False,
            verified=True,
        )

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings._get_hardware_context", return_value=None),
            patch(
                "fpstune.api.routes.settings._finalize_apply_response",
                return_value=response_obj,
            ),
            patch("fpstune.api.routes.settings.CommandExecutor.apply", return_value=(True, None)),
            patch("fpstune.api.routes.settings.sys.platform", "win32"),
            patch("fpstune.api.routes.settings._create_restore_point_async") as mock_rp,
        ):
            result = client.post(f"/api/settings/{setting.id}/reset")

        assert result.status_code == 200
        mock_rp.assert_called_once()

    def test_bulk_stream_reset_creates_restore_point(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # unknown IDs still exercise the guard

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream.sys.platform", "win32"),
            patch("fpstune.api.routes.settings_stream._create_restore_point_async") as mock_rp,
        ):
            result = client.post("/api/settings/bulk/stream-reset", json={"ids": ["core:whatever"]})

        assert result.status_code == 200
        mock_rp.assert_called_once()

    def test_bulk_stream_reset_skips_restore_point_for_empty_request(
        self, client: TestClient
    ) -> None:
        """No IDs means no state change — don't spend minutes on a restore point."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings_stream._get_hardware_context", return_value=None),
            patch("fpstune.api.routes.settings_stream.sys.platform", "win32"),
            patch("fpstune.api.routes.settings_stream._create_restore_point_async") as mock_rp,
        ):
            result = client.post("/api/settings/bulk/stream-reset", json={"ids": []})

        assert result.status_code == 200
        mock_rp.assert_not_called()
