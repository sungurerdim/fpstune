"""A power tweak has to survive whatever switches the power plan.

Every powercfg setting is stored per plan:

    ...\\Power\\User\\PowerSchemes\\<scheme>\\<subgroup>\\<setting>\\ACSettingIndex

so writing only the active plan leaves the tweak behind the moment anything
switches. That is not hypothetical. On the machine this was measured on, Process
Lasso switches to "Bitsum Highest Performance" while a game runs and back to "FPS
Balanced" afterwards — two readings taken minutes apart in the same session
disagreed for exactly that reason, and only one of the two plans carried the
core-parking override. The user games on the plan that did not have it.

Two rules come out of that, and both are tested here:

  - apply writes every plan the machine actually uses, active plan first
  - detect reports the recommended value only when EVERY one of those plans carries
    it, which is the #56 rule: an observation narrower than the action lets
    verification pass over a state that was never reached

"Plans the machine actually uses" is the active plan plus every plan that is not
one of Windows' own, so stock Balanced and Power saver keep shipping behaviour.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from fpstune.settings.base import DetectType, SettingCategory, SettingExecutor, SettingValueType
from fpstune.settings.executors.powercfg import PowerCfgExecutor

ACTIVE = "f0b769e8-7b04-4cb9-ae25-9c2a28918d23"  # a custom plan, active
CUSTOM = "b76bc4cb-3219-417b-a2fb-682acfbabcdc"  # a tool's plan, not active
BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"  # Windows' own
SUBGROUP = "54533251-82be-4824-96c1-47b60b740d00"
SETTING = "0cc5b647-c1df-4637-891a-dec35c318583"


@pytest.fixture
def executor() -> PowerCfgExecutor:
    return PowerCfgExecutor()


def _setting(**overrides) -> SettingExecutor:
    args = {"subgroup": SUBGROUP, "setting": SETTING}
    defaults: dict = {
        "id": "power:test_setting",
        "category": SettingCategory.POWER,
        "display_name": "Test",
        "description": "A test setting.",
        "value_type": SettingValueType.CHOICE,
        "choices": ("off", "on"),
        "default_value": "off",
        "recommended_value": "on",
        "requires_reboot": False,
        "current_impact": "",
        "recommended_impact": "",
        "effect": "",
        "impact_scores": {"fps": "+1%"},
        "detect_type": DetectType.POWERCFG,
        "detect_command": "",
        "detect_args": args,
        "value_map": {0: "off", 1: "on"},
        "apply_type": DetectType.POWERCFG,
        "apply_command": "",
        "apply_args": args,
        "apply_value_map": {"off": 0, "on": 1},
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)  # type: ignore[arg-type]


class TestWhichPlansAreTargeted:
    def test_the_active_plan_comes_first(self, executor) -> None:
        """So a non-uniform reading names the plan the user is on, and apply fixes it first."""
        with (
            patch.object(executor, "_active_scheme_from_registry", return_value=ACTIVE),
            patch.object(executor, "_is_windows_scheme", side_effect=lambda g: g == BALANCED),
            patch(
                "winreg.EnumKey",
                side_effect=[CUSTOM, BALANCED, ACTIVE, OSError()],
            ),
            patch("winreg.OpenKey"),
        ):
            schemes = executor._target_schemes()

        assert schemes[0] == ACTIVE

    def test_windows_own_plans_are_left_alone(self, executor) -> None:
        """Switching to Balanced for quiet or battery must still get Balanced."""
        with (
            patch.object(executor, "_active_scheme_from_registry", return_value=ACTIVE),
            patch.object(executor, "_is_windows_scheme", side_effect=lambda g: g == BALANCED),
            patch(
                "winreg.EnumKey",
                side_effect=[CUSTOM, BALANCED, ACTIVE, OSError()],
            ),
            patch("winreg.OpenKey"),
        ):
            schemes = executor._target_schemes()

        assert BALANCED not in schemes
        assert set(schemes) == {ACTIVE, CUSTOM}

    def test_a_stock_plan_is_still_written_when_it_is_the_active_one(self, executor) -> None:
        """A machine running stock Balanced still deserves the tweak on the plan it uses."""
        with (
            patch.object(executor, "_active_scheme_from_registry", return_value=BALANCED),
            patch.object(executor, "_is_windows_scheme", return_value=True),
            patch(
                "winreg.EnumKey",
                side_effect=[BALANCED, OSError()],
            ),
            patch("winreg.OpenKey"),
        ):
            schemes = executor._target_schemes()

        assert schemes == [BALANCED]

    @pytest.mark.skipif(sys.platform != "win32", reason="reads the real registry")
    def test_windows_plans_are_told_apart_structurally_not_by_name(self, executor) -> None:
        """Balanced and Power saver ship on every Windows and store an MUI indirect name.

        Matching the word "Balanced" would not survive a Turkish install, where the
        same plan reads "Dengeli". The '@' prefix is the indirect-string marker.
        """
        assert executor._is_windows_scheme(BALANCED) is True
        assert executor._is_windows_scheme("a1841308-3541-4fab-bc81-f71556f20b4a") is True

    def test_an_unreadable_plan_is_treated_as_windows_own(self, executor) -> None:
        """The safe direction: miss a tweak on one plan rather than rewrite a stock one."""
        with patch("winreg.OpenKey", side_effect=OSError()):
            assert executor._is_windows_scheme(CUSTOM) is True


class TestDetectAcrossPlans:
    def _detect(self, executor, readings: dict[str, int | None], setting=None):
        setting = setting or _setting()
        with (
            patch.object(executor, "_target_schemes", return_value=list(readings)),
            patch.object(executor, "_scheme_index", side_effect=lambda s, _sub, _set: readings[s]),
        ):
            return executor._detect_via_registry_key(setting)

    def test_agreement_reports_the_shared_value(self, executor) -> None:
        assert self._detect(executor, {ACTIVE: 1, CUSTOM: 1}) == "on"

    def test_one_plan_left_behind_is_not_reported_as_applied(self, executor) -> None:
        """The exact failure: applied on the plan you are on, absent on the one you game on."""
        assert self._detect(executor, {ACTIVE: 1, CUSTOM: 0}) == "off"

    def test_a_plan_with_no_override_reads_as_the_windows_default(self, executor) -> None:
        """Not `not_available`.

        Absent means the plan inherits Windows' default, which is what
        `default_value` is curated to hold. Answering "not available" for it is why
        four settings read as inapplicable on every machine and never appeared in
        the UI at all — there was nothing to tune, said the code, about a setting
        that was simply unset.
        """
        assert self._detect(executor, {ACTIVE: None, CUSTOM: 1}) == "off"

    def test_all_plans_unset_reports_the_default_not_an_absence(self, executor) -> None:
        assert self._detect(executor, {ACTIVE: None, CUSTOM: None}) == "off"

    def test_it_never_reports_the_recommendation_while_plans_disagree(self, executor) -> None:
        # Reversed order: the recommended value is first, the outlier second. A
        # first-wins reading would call this done.
        assert self._detect(executor, {ACTIVE: 1, CUSTOM: None}) == "off"

    def test_an_unreadable_plan_list_defers_to_powercfg(self, executor) -> None:
        """None means "ask powercfg", not a sentinel. A sentinel on every failure is
        indistinguishable from a working read."""
        with patch.object(executor, "_target_schemes", return_value=[]):
            assert executor._detect_via_registry_key(_setting()) is None

    def test_plans_that_agree_across_types_are_not_called_a_disagreement(self, executor) -> None:
        """The two readings do not come from the same place, so they can differ in type.

        A plan holding an override yields whatever `value_map` makes of its
        integer index; a plan holding none yields the curated `default_value`.
        For a free-form setting with an empty map those are 100 and "100" — the
        same value, written twice. Compared with `==` that reads as "the plans
        disagree", and the UI reports a fully-tuned machine as half-tuned.

        This is the codebase's single-comparison-truth rule (`values_equal`,
        never `==`) applied where it had been missed.
        """
        free_form = _setting(
            value_type=SettingValueType.INT,
            choices=(),
            value_map={},
            apply_value_map={},
            default_value="100",  # curated as text
            recommended_value=100,
            min_value=0,
            max_value=100,
        )
        # ACTIVE holds the override as the integer the registry stores; CUSTOM
        # holds none, so it reads back as the curated default.
        assert self._detect(executor, {ACTIVE: 100, CUSTOM: None}, free_form) == 100

    def test_a_genuine_disagreement_across_types_is_still_reported(self, executor) -> None:
        """The guard above must not turn every disagreement into agreement."""
        free_form = _setting(
            value_type=SettingValueType.INT,
            choices=(),
            value_map={},
            apply_value_map={},
            default_value="50",
            recommended_value=100,
            min_value=0,
            max_value=100,
        )
        # One plan is at the recommendation, the other inherits 50. The reading
        # must name the plan that is behind, never the recommendation.
        assert self._detect(executor, {ACTIVE: 100, CUSTOM: None}, free_form) == "50"


class TestApplyAcrossPlans:
    def test_it_writes_every_plan(self, executor) -> None:
        calls: list[str] = []
        with (
            patch.object(executor, "_target_schemes", return_value=[ACTIVE, CUSTOM]),
            patch.object(
                executor, "_run", side_effect=lambda cmd: (calls.append(cmd), (True, ""))[1]
            ),
        ):
            success, error = executor.apply(_setting(), "on")

        assert success is True and error is None
        assert any(ACTIVE in c and "/setacvalueindex" in c for c in calls)
        assert any(CUSTOM in c and "/setacvalueindex" in c for c in calls)

    def test_it_writes_the_active_plan_before_any_other(self, executor) -> None:
        """If a later plan fails, the machine the user is on is already correct."""
        calls: list[str] = []
        with (
            patch.object(executor, "_target_schemes", return_value=[ACTIVE, CUSTOM]),
            patch.object(
                executor, "_run", side_effect=lambda cmd: (calls.append(cmd), (True, ""))[1]
            ),
        ):
            executor.apply(_setting(), "on")

        writes = [c for c in calls if "valueindex" in c]
        assert ACTIVE in writes[0]

    def test_it_writes_battery_as_well_as_mains(self, executor) -> None:
        calls: list[str] = []
        with (
            patch.object(executor, "_target_schemes", return_value=[ACTIVE]),
            patch.object(
                executor, "_run", side_effect=lambda cmd: (calls.append(cmd), (True, ""))[1]
            ),
        ):
            executor.apply(_setting(), "on")

        assert any("/setacvalueindex" in c for c in calls)
        assert any("/setdcvalueindex" in c for c in calls)

    def test_a_failure_on_the_active_plan_sinks_the_apply(self, executor) -> None:
        def run(cmd: str):
            return (False, "denied") if ACTIVE in cmd else (True, "")

        with (
            patch.object(executor, "_target_schemes", return_value=[ACTIVE, CUSTOM]),
            patch.object(executor, "_run", side_effect=run),
        ):
            success, error = executor.apply(_setting(), "on")

        assert success is False
        assert "active plan" in (error or "")

    def test_a_failure_on_another_plan_is_reported_without_sinking_it(self, executor) -> None:
        """The user's own plan changed; saying it failed outright would be false."""

        def run(cmd: str):
            return (False, "denied") if CUSTOM in cmd else (True, "")

        with (
            patch.object(executor, "_target_schemes", return_value=[ACTIVE, CUSTOM]),
            patch.object(executor, "_run", side_effect=run),
        ):
            success, error = executor.apply(_setting(), "on")

        assert success is True
        assert error and CUSTOM in error
