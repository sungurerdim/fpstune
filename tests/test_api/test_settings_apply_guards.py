"""Every apply path shares one value validation, and bulk work stays off the loop.

Failures these tests guard against, each observed in the shipped route module:

  SEC-16   the bulk route (now ``POST /bulk/stream-apply``) handed each
           request value straight to ``CommandExecutor.apply`` with no
           validation, so a value the single-setting route refused with a 400
           reached an elevated ``%value%`` command slot through the bulk route.
  SEC-12   a free-form STRING setting (``choices=()``) was never validated on
           any path, so shell metacharacters could ride a plausible-looking
           request into the same slot.
  PERF-23  ``_get_registry()`` ran on the event loop, so a request arriving
           during startup warm-up blocked the loop for the whole discovery.
  CC-02    a local two-string respelling of the absence sentinels let
           ``not_supported`` and ``not_found`` fail post-apply verification.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.api.routes.settings import (
    _finalize_apply_response,
    _verify_setting_applied,
    get_definitions,
)
from fpstune.api.schemas import ApplyResponse, SettingState
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from tests.conftest import neutral_hardware_context


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _choice_setting(setting_id: str = "test:mode") -> SettingExecutor:
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.SYSTEM,
        display_name="Test Mode",
        description="A test setting with enumerated values.",
        value_type=SettingValueType.CHOICE,
        choices=("off", "on"),
        default_value="off",
        recommended_value="on",
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Set-Something -Value '%value%'",
    )


def _free_string_setting(validate_pattern: str | None = None) -> SettingExecutor:
    return SettingExecutor(
        id="test:free_string",
        category=SettingCategory.GAME_CONFIG,
        display_name="Test Free String",
        description="A free-form STRING setting, like a derived resolution or refresh rate.",
        value_type=SettingValueType.STRING,
        choices=(),
        default_value="2560x1440",
        recommended_value="2560x1440",
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Set-Something -Value '%value%'",
        validate_pattern=validate_pattern,
    )


def _success_response(setting_id: str, value: Any) -> ApplyResponse:
    return ApplyResponse(
        setting_id=setting_id,
        success=True,
        error=None,
        state=SettingState(setting_id=setting_id, current=value),
        requires_reboot=False,
        verified=True,
    )


@contextmanager
def _route_mocks(setting: SettingExecutor) -> Iterator[None]:
    """The standard patch set: fake registry, no hardware, no restore point."""
    registry = MagicMock()
    registry.get.return_value = setting
    with (
        patch("fpstune.api.routes.settings._get_registry", return_value=registry),
        patch(
            "fpstune.api.routes.settings._get_hardware_context",
            return_value=neutral_hardware_context(),
        ),
        patch("fpstune.api.routes.settings._ensure_restore_point"),
    ):
        yield


@contextmanager
def _stream_mocks(setting: SettingExecutor) -> Iterator[None]:
    """The same patch set for the bulk stream, which binds its own names."""
    registry = MagicMock()
    registry.get.return_value = setting
    with (
        patch("fpstune.api.routes.settings_stream._get_registry", return_value=registry),
        patch(
            "fpstune.api.routes.settings_stream._get_hardware_context",
            return_value=neutral_hardware_context(),
        ),
        patch("fpstune.api.routes.settings_stream._ensure_restore_point"),
    ):
        yield


def _events(response: Any) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data:") :].strip())
        for line in response.text.splitlines()
        if line.strip().startswith("data:")
    ]


class TestBulkApplySharesSingleApplyValidation:
    """SEC-16: the bulk stream must refuse exactly what single apply refuses."""

    def test_bulk_apply_rejects_a_value_the_single_route_would_reject(
        self, client: TestClient
    ) -> None:
        """The defect, exactly: a non-choice value through the bulk route used to
        reach CommandExecutor.apply — and its %value% slot — unvalidated."""
        setting = _choice_setting()

        with (
            _stream_mocks(setting),
            patch("fpstune.api.routes.settings_apply.CommandExecutor.apply") as apply_cmd,
        ):
            result = client.post(
                "/api/settings/bulk/stream-apply",
                json={"settings": {"test:mode": "on'; Start-Process calc; '"}},
            )

        assert result.status_code == 200
        events = _events(result)
        failed = [e for e in events if e["event"] == "failed"]
        assert [e["id"] for e in failed] == ["test:mode"]
        assert "not valid" in failed[0]["error"]
        assert events[-1]["failed"] == 1
        apply_cmd.assert_not_called()

    def test_a_declared_value_still_applies_through_bulk(self, client: TestClient) -> None:
        """The guard must not eat legitimate bulk applies."""
        setting = _choice_setting()

        with (
            _stream_mocks(setting),
            patch(
                "fpstune.api.routes.settings_apply.CommandExecutor.apply", return_value=(True, None)
            ) as apply_cmd,
            patch(
                "fpstune.api.routes.settings._finalize_apply_response",
                return_value=_success_response(setting.id, "on"),
            ),
            patch("fpstune.api.routes.settings_apply.is_free", return_value=True),
        ):
            result = client.post(
                "/api/settings/bulk/stream-apply",
                json={"settings": {"test:mode": "on"}},
            )

        assert result.status_code == 200
        assert _events(result)[-1]["succeeded"] == 1
        # The third argument is the line pump the stream hands every command.
        apply_cmd.assert_called_once()
        assert apply_cmd.call_args.args[:2] == (setting, "on")


class TestFreeStringValidation:
    """SEC-12: a STRING setting with no choices gets a shape check, not a pass."""

    def _apply(self, client: TestClient, setting: SettingExecutor, value: Any):
        with (
            _route_mocks(setting),
            patch(
                "fpstune.api.routes.settings_apply.CommandExecutor.apply", return_value=(True, None)
            ) as apply_cmd,
            patch(
                "fpstune.api.routes.settings._finalize_apply_response",
                return_value=_success_response(setting.id, value),
            ),
        ):
            result = client.post(f"/api/settings/{setting.id}/apply", json={"value": value})
        return result, apply_cmd

    @pytest.mark.parametrize("value", ["2560x1440", "300.000", "Auto:300.000", "270"])
    def test_every_shipped_free_string_shape_is_accepted(
        self, client: TestClient, value: str
    ) -> None:
        """The rule must not reject what the shipped settings genuinely write:
        resolutions, bare refresh rates, and MW4's prefixed ``Auto:<hz>``."""
        result, apply_cmd = self._apply(client, _free_string_setting(), value)

        assert result.status_code == 200
        apply_cmd.assert_called_once()

    @pytest.mark.parametrize(
        "value",
        [
            "300.000; Start-Process calc",
            "$(whoami)",
            "`whoami`",
            "300 | Out-File pwned",
            'a"b',
            "x" * 65,
        ],
    )
    def test_command_shaped_values_are_refused_with_a_400(
        self, client: TestClient, value: str
    ) -> None:
        """Previously every one of these reached the %value% slot untouched."""
        result, apply_cmd = self._apply(client, _free_string_setting(), value)

        assert result.status_code == 400
        assert "allowed format" in result.json()["detail"]
        apply_cmd.assert_not_called()

    def test_a_declared_validate_pattern_overrides_the_default_allowlist(
        self, client: TestClient
    ) -> None:
        """A setting that bounds its own strings is held to its own bound."""
        setting = _free_string_setting(validate_pattern=r"\d+x\d+")

        rejected, apply_cmd = self._apply(client, setting, "abc.def")
        assert rejected.status_code == 400, "passes the generic allowlist, not the setting's own"
        apply_cmd.assert_not_called()

        accepted, _ = self._apply(client, setting, "2560x1440")
        assert accepted.status_code == 200

    def test_bulk_apply_holds_free_strings_to_the_same_rule(self, client: TestClient) -> None:
        """SEC-12 through the SEC-16 chokepoint: one rule, both routes."""
        setting = _free_string_setting()

        with (
            _stream_mocks(setting),
            patch("fpstune.api.routes.settings_apply.CommandExecutor.apply") as apply_cmd,
        ):
            result = client.post(
                "/api/settings/bulk/stream-apply",
                json={"settings": {"test:free_string": "$(whoami)"}},
            )

        failed = [e for e in _events(result) if e["event"] == "failed"]
        assert [e["id"] for e in failed] == ["test:free_string"]
        apply_cmd.assert_not_called()


class TestRegistryFetchRunsOffTheEventLoop:
    """PERF-23: the blocking registry build must execute on a worker thread.

    Asserted on the mechanism — the thread the synchronous core actually ran
    on — not on wall-clock timing. ``asyncio.run`` drives the loop on the
    test's own thread, so a core that recorded the test thread's ident ran
    inline on the loop, which is the regression.
    """

    @staticmethod
    def _record_thread(seen: list[int], response: Any):
        def _recorder(*_args: Any, **_kwargs: Any) -> Any:
            seen.append(threading.get_ident())
            return response

        return _recorder

    def test_registry_fetch_runs_on_a_worker_thread(self) -> None:
        """PERF-23: a request during warm-up must wait on _registry_lock from a
        worker thread, never on the loop itself."""
        seen: list[int] = []
        registry = MagicMock()
        registry.get_all.return_value = []

        with patch(
            "fpstune.api.routes.settings._get_registry",
            side_effect=self._record_thread(seen, registry),
        ):
            asyncio.run(get_definitions())

        assert seen and seen[0] != threading.get_ident(), (
            "_get_registry ran inline on the event loop"
        )


class TestAbsenceSentinelsSkipVerification:
    """CC-02: all four ABSENT_READINGS spellings skip verification, not two.

    The route held a local tuple ("not_installed", "not_available"), so a
    setting whose detection answered "not_supported" or "not_found" failed
    verification instead of being recognised as absent.
    """

    @pytest.mark.parametrize(
        "sentinel",
        ["not_supported", "not_found", "not_available", "not_installed", "Not_Supported\r\n"],
    )
    def test_every_absence_sentinel_skips_verification(self, sentinel: str) -> None:
        success, error, verified = _verify_setting_applied(_choice_setting(), "on", sentinel)

        assert success is True
        assert error is None
        assert verified is None, "a skipped check must not be reported as a passed one"

    def test_a_real_mismatch_still_fails(self) -> None:
        """The sentinel skip must not swallow genuine verification failures."""
        success, error, verified = _verify_setting_applied(_choice_setting(), "on", "off")

        assert success is False
        assert error is not None
        assert verified is False


def _engine_with(value: str) -> MagicMock:
    result = SimpleNamespace(
        value=value,
        is_applicable=True,
        applicable_reason="",
        is_optimized=True,
        error=None,
        finding=None,
    )
    engine = MagicMock()
    engine.detect_one.return_value = result
    return engine


def test_a_successful_action_message_is_not_reported_as_a_partial_failure() -> None:
    """`power_plan_switch` returns "FPS Balanced profile activated" on success.

    That sentence used to stay in the error slot, so a clean apply read as
    partial in the API and in the operation log. A message that is not the
    "applied, but ..." warning shape is an informational note.
    """
    setting = _choice_setting()
    with patch("fpstune.api.routes.settings.log_activity") as log:
        response = _finalize_apply_response(
            setting, "on", _engine_with("on"), True, "FPS Balanced profile activated"
        )

    assert response.success is True
    assert response.error is None
    assert any(call.args[1] == "info" for call in log.call_args_list)


def test_a_real_partial_write_keeps_its_warning() -> None:
    """The generic success-message rule must not swallow "applied, but ..."."""
    setting = _choice_setting()
    response = _finalize_apply_response(
        setting, "on", _engine_with("on"), True, "applied, but 1 write(s) failed"
    )

    assert response.success is True
    assert response.error is None
    assert response.warnings == ["applied, but 1 write(s) failed"]


def test_a_failed_write_is_logged_with_its_verb_not_its_past_tense() -> None:
    """The log read "Failed to applied <name>" because the past-tense label was lowercased."""
    setting = _choice_setting()
    with patch("fpstune.api.routes.settings.log_activity") as log:
        response = _finalize_apply_response(setting, "on", MagicMock(), False, "refused")

    assert response.success is False
    message = log.call_args.args[0]
    assert message == f"Failed to apply {setting.display_name}: refused"
