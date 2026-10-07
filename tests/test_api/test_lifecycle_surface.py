"""A setting has two verbs: detect and apply. Reset is apply(default_value).

Failures these tests guard against:

  - a `/verify` or `/reset` endpoint coming back beside `/apply`: a second path
    that writes (or reads) a setting with its own idea of "correct", which is how
    `verify` once reported a correctly reset setting as failed;
  - reset losing what the retired endpoint had: the default written verbatim, the
    value read back and compared by the one `values_equal` truth, and a refusal
    for a row whose default could not be derived (C6) — now carried by `/apply`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api import schemas
from fpstune.api.main import create_app
from fpstune.api.routes.settings import _validate_apply_value
from fpstune.settings.base import (
    DetectionResult,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from tests.conftest import neutral_hardware_context


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _tweak(*, default: object = "off", recommended: object = "on") -> SettingExecutor:
    return SettingExecutor(
        id="system:lifecycle_probe",
        category=SettingCategory.SYSTEM,
        display_name="Lifecycle Probe",
        description="A state setting that a reset must return to its default.",
        value_type=SettingValueType.CHOICE,
        choices=("off", "on"),
        default_value=default,
        recommended_value=recommended,
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Set-Something -Value '%value%'",
    )


def _cleanup() -> SettingExecutor:
    return SettingExecutor(
        id="cleanup:lifecycle_probe",
        category=SettingCategory.MAINTENANCE,
        display_name="Lifecycle Cleanup",
        description="An action: its value is permission to run, never a state.",
        value_type=SettingValueType.BOOL,
        choices=(),
        default_value=False,
        recommended_value=True,
        is_action=True,
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Do-Something",
    )


def _reading(setting_id: str, value: object) -> DetectionResult:
    return DetectionResult(
        setting_id=setting_id, value=value, error=None, time_ms=1, is_optimized=False
    )


def _post_apply(client: TestClient, setting: SettingExecutor, value: object, *, detected: object):
    """POST `/apply` for `setting`, with the registry, machine and re-detect scripted."""
    registry = MagicMock()
    registry.get.return_value = setting
    engine = MagicMock()
    engine.detect_one.return_value = _reading(setting.id, detected)
    with (
        patch("fpstune.api.routes.settings._get_registry", return_value=registry),
        patch(
            "fpstune.api.routes.settings._get_hardware_context",
            return_value=neutral_hardware_context(),
        ),
        patch("fpstune.api.routes.settings.DetectionEngine", return_value=engine),
        patch("fpstune.api.routes.settings._ensure_restore_point"),
        patch("fpstune.utils.self_check.ensure_checked_before_first_apply"),
        patch("fpstune.api.routes.settings_apply.is_free", return_value=True),
        patch(
            "fpstune.api.routes.settings_apply.CommandExecutor.apply", return_value=(True, None)
        ) as write,
    ):
        response = client.post(f"/api/settings/{setting.id}/apply", json={"value": value})
    return response, write


class TestOnlyDetectAndApplyRemain:
    def test_no_settings_route_ends_in_reset_or_verify(self) -> None:
        paths = {
            path for path in create_app().openapi()["paths"] if path.startswith("/api/settings")
        }

        offenders = sorted(p for p in paths if p.endswith(("/reset", "/verify")))
        assert offenders == [], f"a second verb is back beside detect and apply: {offenders}"
        assert "/api/settings/{setting_id}/apply" in paths
        assert "/api/settings/detect" in paths

    @pytest.mark.parametrize("verb", ["reset", "verify"])
    def test_the_retired_verbs_answer_not_found(self, client: TestClient, verb: str) -> None:
        response = client.post(f"/api/settings/network:nagle_algorithm/{verb}")

        assert response.status_code == 404

    def test_the_verify_models_are_gone_from_the_schema_module(self) -> None:
        assert not hasattr(schemas, "VerifyResponse")
        assert not hasattr(schemas, "VerifyRequest")


class TestResetIsAnApplyOfTheDefault:
    def test_the_default_is_written_verbatim_and_read_back(self, client: TestClient) -> None:
        setting = _tweak(default="off", recommended="on")

        response, write = _post_apply(client, setting, setting.default_value, detected="off")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["verified"] is True
        assert body["state"]["current"] == "off"
        write.assert_called_once_with(setting, "off", None)

    def test_a_reset_that_did_not_land_reports_the_mismatch(self, client: TestClient) -> None:
        """Verification compares what was written with what was read back, so a
        default the machine did not take is a failure, not a quiet success."""
        setting = _tweak(default="off", recommended="on")

        response, _write = _post_apply(client, setting, setting.default_value, detected="on")

        body = response.json()
        assert body["success"] is False
        assert body["verified"] is False
        assert "expected 'off', got 'on'" in body["error"]

    def test_an_action_default_is_do_not_run_and_runs_nothing(self, client: TestClient) -> None:
        setting = _cleanup()

        response, write = _post_apply(client, setting, setting.default_value, detected=None)

        assert response.status_code == 200
        assert response.json()["success"] is True
        # CommandExecutor.apply is where "a falsy action value means do not run"
        # lives; the route hands it the default exactly as it would any value.
        write.assert_called_once_with(setting, False, None)


class TestANullValueIsNeverWritten:
    """C6: a default that cannot be derived is not invented."""

    def test_a_state_setting_refuses_null(self) -> None:
        refusal = _validate_apply_value(_tweak(default=None), None)

        assert refusal is not None
        assert "needs a value" in refusal

    def test_an_action_still_takes_null_as_do_not_run(self) -> None:
        assert _validate_apply_value(_cleanup(), None) is None

    def test_the_route_refuses_null_before_any_write(self, client: TestClient) -> None:
        setting = _tweak(default=None)

        response, write = _post_apply(client, setting, None, detected="off")

        assert response.status_code == 400
        assert "needs a value" in response.json()["detail"]
        write.assert_not_called()
