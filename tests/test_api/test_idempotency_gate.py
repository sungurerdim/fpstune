"""H6 GATE: apply twice equals apply once, and verify agrees.

The single most under-tested property in the product. Every writer fpstune
ships is *meant* to be idempotent — a registry value set to what it already
holds, a config line rewritten to itself — but nothing ever proved the
pipeline keeps that promise, and an accumulating writer (a value appended
instead of assigned, a counter bumped per call) would report success on
every apply while drifting the machine further each time.

The harness runs the real route pipeline — validation, apply, post-apply
detect, verify — over a fake machine whose state is a dict, with only the
command boundary substituted. The gate is the pair of properties below; the
third test is the in-suite red proof (house style): the same harness handed
a deliberately accumulating writer must fail the same assertions, or the
gate is measuring nothing.

The live half of this property belongs to the opt-in hardware sweep
(test_apply_roundtrip.py, FPSTUNE_APPLY_SWEEP), which applies real settings
to a real machine and re-detects.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.settings.base import (
    DetectionResult,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _setting() -> SettingExecutor:
    return SettingExecutor(
        id="system:h6_probe",
        category=SettingCategory.SYSTEM,
        display_name="H6 Probe",
        description="A probe setting for the idempotency gate.",
        value_type=SettingValueType.CHOICE,
        choices=("stock", "tuned"),
        default_value="stock",
        recommended_value="tuned",
        detect_type=DetectType.POWERSHELL,
        detect_command="Get-Something",
        apply_type=DetectType.POWERSHELL,
        apply_command="Set-Something -Value '%value%'",
    )


class _FakeMachine:
    """The machine as a dict, written through the same boundary the real one is."""

    def __init__(self, *, accumulating: bool = False) -> None:
        self.state: dict[str, Any] = {"system:h6_probe": "stock"}
        self.accumulating = accumulating

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        if self.accumulating:
            # The defect class, exactly: a writer that adds instead of assigns.
            self.state[setting.id] = f"{self.state[setting.id]}+{value}"
        else:
            self.state[setting.id] = value
        return True, None

    def detect(self, setting: SettingExecutor) -> DetectionResult:
        return DetectionResult(
            setting_id=setting.id,
            value=self.state[setting.id],
            error=None,
            time_ms=1,
            is_optimized=self.state[setting.id] == setting.recommended_value,
            is_applicable=True,
        )


def _double_apply(client: TestClient, machine: _FakeMachine) -> tuple[Any, Any]:
    setting = _setting()
    registry = MagicMock()
    registry.get.return_value = setting

    with (
        patch("fpstune.api.routes.settings._get_registry", return_value=registry),
        patch(
            "fpstune.api.routes.settings._context_and_applicability",
            return_value=(None, True, None),
        ),
        patch(
            "fpstune.utils.self_check.ensure_checked_before_first_apply",
            return_value=None,
        ),
        patch("fpstune.api.routes.settings._create_restore_point_async"),
        patch(
            "fpstune.settings.executors.CommandExecutor.apply",
            side_effect=machine.apply,
        ),
        patch(
            "fpstune.api.routes.settings.DetectionEngine.detect_one",
            side_effect=machine.detect,
        ),
    ):
        first = client.post("/api/settings/system:h6_probe/apply", json={"value": "tuned"})
        second = client.post("/api/settings/system:h6_probe/apply", json={"value": "tuned"})
    return first.json(), second.json()


class TestApplyTwiceEqualsApplyOnce:
    def test_the_second_apply_changes_nothing_and_verify_agrees(self, client) -> None:
        machine = _FakeMachine()
        first, second = _double_apply(client, machine)

        assert first["success"] is True and first["verified"] is True
        assert second["success"] is True and second["verified"] is True
        # Apply twice equals apply once: same machine state, same read-back.
        assert machine.state["system:h6_probe"] == "tuned"
        assert second["new_value"] == first["new_value"] == "tuned"

    def test_the_gate_catches_an_accumulating_writer(self, client) -> None:
        """The in-suite red proof: handed the defect class this gate exists
        for, the same assertions must fail — otherwise the harness is
        measuring nothing. The pipeline's own verify is what catches it:
        the first apply already reads back 'stock+tuned' != 'tuned'."""
        machine = _FakeMachine(accumulating=True)
        first, second = _double_apply(client, machine)

        assert first["success"] is False, "verify let an accumulated value pass"
        assert second["success"] is False
        assert machine.state["system:h6_probe"] != "tuned"
