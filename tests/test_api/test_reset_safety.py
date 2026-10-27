"""Reset is an apply of the row's default, and carries apply's rollback safety net.

Reset writes to the registry / powercfg / BCD exactly like apply does, so a bad
reset is just as hard to undo. There is no reset endpoint: the client posts the
row's `default_value` to `/apply`, so the restore point, the validation and the
re-detect are the apply path's own.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.schemas import ApplyResponse
from tests.conftest import neutral_hardware_context


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
    s.choices = ("0", "1")
    # An empty dict, not a MagicMock: applicability reads the declared
    # conditions as a mapping (`.get`), and a double that answers every
    # attribute would claim every condition holds.
    s.applicable_conditions = {}
    s.requires_reboot = False
    s.is_action = False
    s.is_readonly = False
    s.apply_type = MagicMock()
    s.apply_type.value = "registry"
    s.apply_args = {}
    return s


class TestResetCreatesRestorePoint:
    def test_applying_the_default_creates_a_restore_point(self, client: TestClient) -> None:
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
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch(
                "fpstune.api.routes.settings._finalize_apply_response",
                return_value=response_obj,
            ),
            patch(
                "fpstune.api.routes.settings_apply.CommandExecutor.apply", return_value=(True, None)
            ) as write,
            patch("fpstune.utils.self_check.ensure_checked_before_first_apply"),
            patch("fpstune.api.routes.settings.sys.platform", "win32"),
            # No bench holds the machine. Patching ``sys.platform`` is global, so
            # without this the operation lock would reach for kernel32, which
            # exists only on a real Windows host.
            patch("fpstune.api.routes.settings_apply.is_free", return_value=True),
            patch("fpstune.api.routes.settings._ensure_restore_point") as mock_rp,
        ):
            result = client.post(
                f"/api/settings/{setting.id}/apply", json={"value": setting.default_value}
            )

        assert result.status_code == 200
        assert result.json()["success"] is True
        write.assert_called_once_with(setting, "0", None)
        mock_rp.assert_called_once()

    def test_a_bulk_reset_creates_a_restore_point(self, client: TestClient) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # unknown IDs still exercise the guard

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch(
                "fpstune.api.routes.settings_stream._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch("fpstune.api.routes.settings_stream.sys.platform", "win32"),
            patch("fpstune.api.routes.settings_stream._ensure_restore_point") as mock_rp,
        ):
            result = client.post(
                "/api/settings/bulk/stream-apply", json={"settings": {"core:whatever": "0"}}
            )

        assert result.status_code == 200
        mock_rp.assert_called_once()

    def test_a_bulk_reset_skips_the_restore_point_for_an_empty_request(
        self, client: TestClient
    ) -> None:
        """No settings means no state change — don't spend minutes on a restore point."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with (
            patch("fpstune.api.routes.settings_stream._get_registry", return_value=mock_registry),
            patch(
                "fpstune.api.routes.settings_stream._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch("fpstune.api.routes.settings_stream.sys.platform", "win32"),
            patch("fpstune.api.routes.settings_stream._ensure_restore_point") as mock_rp,
        ):
            result = client.post("/api/settings/bulk/stream-apply", json={"settings": {}})

        assert result.status_code == 200
        mock_rp.assert_not_called()


class TestResetWithoutADerivedDefault:
    """A row with no derivable default (DefaultSource.NONE) used to reach the write with None."""

    def test_a_null_value_is_refused_and_nothing_is_written(self, client: TestClient) -> None:
        """Reset is `apply(default_value)`; a row with no default has `None` to send.

        The refusal moved from the reset route to the one validation every apply
        path shares, so a client that posts the null anyway reaches no write.
        """
        setting = _fake_setting()
        setting.default_value = None
        mock_registry = MagicMock()
        mock_registry.get.return_value = setting

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=mock_registry),
            patch("fpstune.api.routes.settings.apply_and_finalize") as write,
            patch("fpstune.api.routes.settings._ensure_restore_point") as restore_point,
        ):
            response = client.post(
                f"/api/settings/{setting.id}/apply", json={"value": setting.default_value}
            )

        assert response.status_code == 400
        assert "needs a value" in response.json()["detail"]
        write.assert_not_called()
        restore_point.assert_not_called()
