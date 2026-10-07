"""One shape for a setting's state: detect returns it, and so does apply.

Failures these tests guard against:

  - `/detect` and `/apply` describing the same setting in two vocabularies
    (`value` / `new_value`, `recommended_value`, `is_applicable`), so a client
    carried a translation for each and the two drifted;
  - `default` and `default_source` missing from a state, so the UI could not say
    what a reset would write or whose stock it is ("Windows default", "Driver
    default", "Game default") without asking the definitions a second time;
  - an apply that re-detected and then threw the reading away, leaving the client
    to run a second detect to learn what the write had done.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.schemas import SettingState
from fpstune.settings.base import (
    DefaultSource,
    DetectionResult,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.registry import SettingsRegistry
from tests.conftest import neutral_hardware_context

#: The keys the contract names. Anything else on a state is detail around them.
CONTRACT_KEYS = {"current", "applicable", "recommended", "default", "default_source"}

#: Spellings the two verbs used before they shared one shape.
RETIRED_KEYS = {"value", "new_value", "recommended_value", "is_applicable"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _reading(setting_id: str, value: object, **fields: Any) -> DetectionResult:
    return DetectionResult(
        setting_id=setting_id, value=value, error=None, time_ms=3, is_optimized=False, **fields
    )


def _tweak() -> SettingExecutor:
    return SettingExecutor(
        id="system:state_probe",
        category=SettingCategory.SYSTEM,
        display_name="State Probe",
        description="A state setting with a derived default.",
        value_type=SettingValueType.CHOICE,
        choices=("off", "on"),
        default_value="off",
        recommended_value="on",
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Set-Something -Value '%value%'",
    )


class TestDetectAnswersInTheOneShape:
    def test_every_registered_setting_carries_the_five_keys(self, client: TestClient) -> None:
        """A registry-wide detect: the contract holds for every row, not a sample.

        The registry is the real static one (every definitions file); only the
        machine is stubbed, because what is under test is the shape the route
        puts around a reading, not the reading.
        """
        registry = SettingsRegistry(discover_dynamic=False)
        settings = registry.get_all()
        engine = MagicMock()
        engine.detect_all.side_effect = lambda rows: {
            row.id: _reading(row.id, row.recommended_value) for row in rows
        }

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch("fpstune.api.routes.settings.DetectionEngine", return_value=engine),
        ):
            response = client.post("/api/settings/detect", json={})

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(settings) > 100, "the registry is not vacuous"
        assert set(results) == {s.id for s in settings}
        for setting in settings:
            state = results[setting.id]
            assert set(state) >= CONTRACT_KEYS, f"{setting.id} lacks {CONTRACT_KEYS - set(state)}"
            assert not RETIRED_KEYS & set(state), f"{setting.id} still speaks the old spelling"
            assert state["default"] == setting.default_value, setting.id
            assert state["recommended"] == setting.recommended_value, setting.id
            assert state["default_source"] == (
                setting.default_source.value if setting.default_source else None
            ), setting.id
            assert state["current"] == setting.recommended_value, setting.id
            assert state["applicable"] is True

    @pytest.mark.parametrize("source", list(DefaultSource), ids=lambda s: s.value)
    def test_every_default_source_crosses_the_wire_as_its_own_word(
        self, source: DefaultSource
    ) -> None:
        """The enum the wire carries is the definitions' own, not a second list:
        each member serialises to the word the UI keys "Windows default" /
        "Driver default" / "Game default" on, never to an enum repr."""
        state = SettingState(setting_id="x:y", default_source=source)

        assert state.model_dump(mode="json")["default_source"] == source.value

    def test_an_unreadable_or_absent_setting_still_has_the_shape(self, client: TestClient) -> None:
        setting = _tweak()
        registry = MagicMock()
        registry.get_all.return_value = [setting]
        engine = MagicMock()
        engine.detect_all.return_value = {
            setting.id: DetectionResult(
                setting_id=setting.id,
                value=None,
                error="Get-Something timed out",
                time_ms=9,
                is_applicable=False,
                applicable_reason="No such adapter on this machine",
            )
        }

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch("fpstune.api.routes.settings.DetectionEngine", return_value=engine),
        ):
            body = client.post("/api/settings/detect", json={}).json()

        state = body["results"][setting.id]
        assert set(state) >= CONTRACT_KEYS
        assert state["current"] is None
        assert state["applicable"] is False
        assert state["applicable_reason"] == "No such adapter on this machine"
        assert state["error"] == "Get-Something timed out"
        assert (body["success_count"], body["error_count"]) == (0, 1)
        assert state["default"] == "off"


class TestApplyReturnsTheSameObject:
    def _detect_then_apply(self, client: TestClient, reading_after: DetectionResult):
        setting = _tweak()
        registry = MagicMock()
        registry.get.return_value = setting
        registry.get_all.return_value = [setting]
        engine = MagicMock()
        engine.detect_all.return_value = {setting.id: reading_after}
        engine.detect_one.return_value = reading_after
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
                "fpstune.api.routes.settings_apply.CommandExecutor.apply",
                return_value=(True, None),
            ),
        ):
            detected = client.post("/api/settings/detect", json={}).json()["results"][setting.id]
            applied = client.post(f"/api/settings/{setting.id}/apply", json={"value": "on"}).json()
        return setting, detected, applied

    def test_the_state_after_an_apply_is_what_detect_would_have_said(
        self, client: TestClient
    ) -> None:
        """One reading, two verbs, one object: the apply's re-detect is not a
        second vocabulary a client has to learn."""
        after = _reading("system:state_probe", "on", is_applicable=True)
        after.is_optimized = True

        _setting, detected, applied = self._detect_then_apply(client, after)

        assert applied["success"] is True and applied["verified"] is True
        assert applied["state"] == detected
        assert set(applied["state"]) >= CONTRACT_KEYS
        assert applied["state"]["current"] == "on"
        assert applied["state"]["default"] == "off"
        assert applied["state"]["default_source"] == "windows_stock"
        assert "new_value" not in applied

    def test_a_write_that_did_not_land_still_reports_what_was_read(
        self, client: TestClient
    ) -> None:
        """Verification failed, but the re-detect happened: the client needs the
        value the machine actually holds, not a blank."""
        after = _reading("system:state_probe", "off")

        _setting, _detected, applied = self._detect_then_apply(client, after)

        assert applied["success"] is False
        assert applied["verified"] is False
        assert applied["state"]["current"] == "off"
        assert applied["state"]["default"] == "off"

    def test_a_refused_value_has_no_state_because_nothing_was_re_detected(
        self, client: TestClient
    ) -> None:
        setting = _tweak()
        registry = MagicMock()
        registry.get.return_value = setting
        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch("fpstune.api.routes.settings.ApplicabilityChecker") as checker,
            patch("fpstune.api.routes.settings._ensure_restore_point"),
        ):
            checker.return_value.is_applicable.return_value = (False, "not on this machine")
            body = client.post(f"/api/settings/{setting.id}/apply", json={"value": "on"}).json()

        assert body["success"] is False
        assert body["state"] is None

    def test_a_failed_command_has_no_state(self, client: TestClient) -> None:
        """The command failed, so there is no write to read back."""
        setting = _tweak()
        registry = MagicMock()
        registry.get.return_value = setting
        engine = MagicMock()
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
                "fpstune.api.routes.settings_apply.CommandExecutor.apply",
                return_value=(False, "Set-Something: access denied"),
            ),
        ):
            body = client.post(f"/api/settings/{setting.id}/apply", json={"value": "on"}).json()

        assert body["success"] is False
        assert body["error"] == "Set-Something: access denied"
        assert body["state"] is None
        engine.detect_one.assert_not_called()
