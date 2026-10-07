"""`power:fps_balanced_plan`: the FPS Balanced plan is an ordinary setting row.

It replaced three bespoke routes (`/power-profile/{status,activate,revert}`) and a
Hardware-panel card that the settings lifecycle — detect, apply, verify, reset to
default, bulk — never saw. These tests run the row through the same executor the
single-setting and bulk paths use, against a fake `powercfg` that keeps the plan
list and the active plan, so every state is read back the way the machine would
answer it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from fpstune.core import power_profile
from fpstune.core.power_profile import (
    BALANCED_GUID,
    FPS_BALANCED_NAME,
    HIGH_PERFORMANCE_GUID,
    PowerProfileManager,
)
from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.settings.base import DefaultSource, DetectType
from fpstune.settings.definitions.power import FPS_BALANCED_PLAN, POWER_SETTINGS
from fpstune.settings.executors.powershell import PowerShellExecutor

NEW_GUID = "0f9d8a6b-1c2d-4e5f-8a9b-0c1d2e3f4a5b"


class FakePowercfg:
    """The plan list and the active plan, answering the verbs the manager uses."""

    def __init__(self, plans: dict[str, str], active: str | None) -> None:
        self.plans = dict(plans)
        self.active = active
        self.failing: set[str] = set()
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *_a: Any, **_k: Any) -> SimpleNamespace:
        self.calls.append(list(args))
        verb = args[1]
        if verb in self.failing:
            return SimpleNamespace(returncode=1, stdout="", stderr="Access is denied.")
        out = ""
        if verb == "/list":
            out = "\n".join(
                f"Power Scheme GUID: {guid}  ({name})" + (" *" if guid == self.active else "")
                for guid, name in self.plans.items()
            )
        elif verb == "/duplicatescheme":
            self.plans[NEW_GUID] = "Balanced"
            out = f"Power Scheme GUID: {NEW_GUID}  (Balanced)"
        elif verb == "/changename":
            self.plans[args[2]] = args[3]
        elif verb == "/setactive":
            self.active = args[2]
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch):
    """A Windows host with stock plans and Balanced active; nothing real is touched."""
    fake = FakePowercfg(
        {
            BALANCED_GUID: "Balanced",
            HIGH_PERFORMANCE_GUID: "High performance",
        },
        active=BALANCED_GUID,
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(power_profile, "_power_profile_manager", PowerProfileManager())
    with (
        patch.object(power_profile.process_watch, "run", side_effect=fake),
        # The plan's own values are `PowerCfgExecutor`'s business and covered by
        # `test_fps_balanced_scope.py`; this row is about which plan is active.
        patch.object(power_profile, "_registry_powercfg_settings", return_value=[]),
    ):
        yield fake


def _detect() -> Any:
    value, error = PowerShellExecutor().detect(FPS_BALANCED_PLAN)
    assert error is None
    return value


class TestDetect:
    @pytest.mark.usefixtures("machine")
    def test_stock_machine_reads_balanced(self) -> None:
        assert _detect() == "balanced"

    def test_fps_balanced_active_reads_fps_balanced(self, machine: FakePowercfg) -> None:
        machine.plans[NEW_GUID] = FPS_BALANCED_NAME
        machine.active = NEW_GUID
        assert _detect() == "fps_balanced"

    def test_any_other_plan_reads_other_not_balanced(self, machine: FakePowercfg) -> None:
        machine.active = HIGH_PERFORMANCE_GUID
        assert _detect() == "other"

    def test_a_localized_balanced_name_is_still_balanced(self, machine: FakePowercfg) -> None:
        machine.plans[BALANCED_GUID] = "Dengeli"
        assert _detect() == "balanced"

    def test_no_active_plan_is_no_reading(self, machine: FakePowercfg) -> None:
        machine.active = None
        assert _detect() == NOT_AVAILABLE

    def test_every_reading_is_one_of_the_choices(self, machine: FakePowercfg) -> None:
        for active in (BALANCED_GUID, HIGH_PERFORMANCE_GUID):
            machine.active = active
            assert _detect() in FPS_BALANCED_PLAN.choices


class TestLifecycle:
    def test_apply_creates_and_activates_the_plan_then_detect_reads_it(
        self, machine: FakePowercfg
    ) -> None:
        ok, message = PowerShellExecutor().apply(FPS_BALANCED_PLAN, "fps_balanced")

        assert ok, message
        assert machine.plans[NEW_GUID] == FPS_BALANCED_NAME
        assert machine.active == NEW_GUID
        assert _detect() == "fps_balanced"

    def test_reset_to_default_returns_to_windows_balanced(self, machine: FakePowercfg) -> None:
        executor = PowerShellExecutor()
        assert executor.apply(FPS_BALANCED_PLAN, "fps_balanced")[0]

        ok, message = executor.apply(FPS_BALANCED_PLAN, FPS_BALANCED_PLAN.default_value)

        assert ok, message
        assert machine.active == BALANCED_GUID
        assert _detect() == "balanced"

    def test_applying_twice_reuses_the_plan(self, machine: FakePowercfg) -> None:
        executor = PowerShellExecutor()
        assert executor.apply(FPS_BALANCED_PLAN, "fps_balanced")[0]
        assert executor.apply(FPS_BALANCED_PLAN, "balanced")[0]
        assert executor.apply(FPS_BALANCED_PLAN, "fps_balanced")[0]

        duplicates = [c for c in machine.calls if c[1] == "/duplicatescheme"]
        assert len(duplicates) == 1

    def test_a_refused_switch_is_a_failure_with_the_reason(self, machine: FakePowercfg) -> None:
        machine.failing.add("/setactive")

        ok, message = PowerShellExecutor().apply(FPS_BALANCED_PLAN, "balanced")

        assert ok is False
        assert message and "Access is denied" in message
        assert machine.active == BALANCED_GUID

    def test_the_reading_other_is_never_written(self, machine: FakePowercfg) -> None:
        assert FPS_BALANCED_PLAN.can_write("other") is False

        ok, message = PowerShellExecutor().apply(FPS_BALANCED_PLAN, "other")

        assert ok is False
        assert message and "cannot be written" in message
        assert not [c for c in machine.calls if c[1] == "/setactive"]


class TestRowContract:
    def test_it_is_registered(self) -> None:
        assert FPS_BALANCED_PLAN in POWER_SETTINGS

    def test_default_is_windows_own_balanced_plan(self) -> None:
        assert FPS_BALANCED_PLAN.default_value == "balanced"
        assert FPS_BALANCED_PLAN.default_source is DefaultSource.WINDOWS_STOCK
        assert FPS_BALANCED_PLAN.can_write(FPS_BALANCED_PLAN.default_value)

    def test_recommendation_is_writable_and_differs_from_the_default(self) -> None:
        assert FPS_BALANCED_PLAN.recommended_value in FPS_BALANCED_PLAN.choices
        assert FPS_BALANCED_PLAN.can_write(FPS_BALANCED_PLAN.recommended_value)
        assert FPS_BALANCED_PLAN.recommended_value != FPS_BALANCED_PLAN.default_value

    def test_the_plan_is_not_one_of_the_per_plan_rows_it_carries(self) -> None:
        """`create()` writes the powercfg rows onto the new plan; recursing into itself is a loop."""
        assert FPS_BALANCED_PLAN.detect_type is not DetectType.POWERCFG

    def test_it_claims_a_measurable_heat_gain_rather_than_a_zero_placeholder(self) -> None:
        """C2 + C11: the claim names a metric an instrument reads, and says a real number.

        The row once carried `power_watts: 0.0`, a padding entry the GPU sensor
        could never have confirmed for a CPU-side change.
        """
        from fpstune.benchmark.sources import source_for
        from fpstune.settings.impact_categories import derive_impact_categories

        claims = {k: v for k, v in FPS_BALANCED_PLAN.impact_scores.items() if k != "stability"}
        assert claims, "C2: at least one performance or resource metric"
        for metric, value in claims.items():
            assert value not in (0, 0.0, "0", "0%"), metric
            assert source_for(metric) is not None, metric
        assert "thermal" in derive_impact_categories(FPS_BALANCED_PLAN.impact_scores)

    def test_every_choice_label_exists_in_both_catalogues(self) -> None:
        i18n = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
        assert set(FPS_BALANCED_PLAN.choice_labels) == set(FPS_BALANCED_PLAN.choices)
        for name in ("en", "tr"):
            text = (i18n / f"{name}.ts").read_text(encoding="utf-8")
            for label in FPS_BALANCED_PLAN.choice_labels.values():
                assert re.search(rf'^\s*"{re.escape(label)}":', text, re.M), (name, label)
