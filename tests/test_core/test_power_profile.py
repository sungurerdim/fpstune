"""Tests for fpstune.core.power_profile.

Covers: constant/GUID values, PowerPlan/PowerProfileResult dataclasses,
list_plans output parsing (regex), find_fps_balanced cache, get_active_plan,
is_fps_balanced_active, create/activate/revert/delete command builders and
error paths, status dict shape, and the singleton accessor.

All subprocess.run calls are mocked.  Windows-only code is guarded with
skipif where the platform check cannot be patched cleanly.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from fpstune.core.power_profile import (
    BALANCED_GUID,
    DISK_SUBGROUP,
    DISK_TIMEOUT,
    FPS_BALANCED_DESCRIPTION,
    FPS_BALANCED_NAME,
    HIGH_PERFORMANCE_GUID,
    OPTIMIZATIONS,
    PCIE_LINK_STATE,
    PCIE_SUBGROUP,
    POWER_SAVER_GUID,
    USB_SELECTIVE_SUSPEND,
    USB_SUBGROUP,
    PowerPlan,
    PowerProfileManager,
    PowerProfileResult,
    get_power_profile_manager,
)

# ---------------------------------------------------------------------------
# Constants and GUIDs
# ---------------------------------------------------------------------------

WELL_KNOWN_BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
WELL_KNOWN_HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
WELL_KNOWN_POWER_SAVER_GUID = "a1841308-3541-4fab-bc81-f71556f20b4a"


class TestConstants:
    def test_balanced_guid(self) -> None:
        assert BALANCED_GUID == WELL_KNOWN_BALANCED_GUID

    def test_high_performance_guid(self) -> None:
        assert HIGH_PERFORMANCE_GUID == WELL_KNOWN_HIGH_PERF_GUID

    def test_power_saver_guid(self) -> None:
        assert POWER_SAVER_GUID == WELL_KNOWN_POWER_SAVER_GUID

    def test_fps_balanced_name(self) -> None:
        assert FPS_BALANCED_NAME == "FPS Balanced"

    def test_fps_balanced_description_nonempty(self) -> None:
        assert FPS_BALANCED_DESCRIPTION and isinstance(FPS_BALANCED_DESCRIPTION, str)

    def test_usb_subgroup_guid_format(self) -> None:
        import re

        pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(pattern, USB_SUBGROUP)

    def test_pcie_subgroup_guid_format(self) -> None:
        import re

        pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(pattern, PCIE_SUBGROUP)

    def test_disk_subgroup_guid_format(self) -> None:
        import re

        pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(pattern, DISK_SUBGROUP)

    def test_optimizations_list_has_three_entries(self) -> None:
        assert len(OPTIMIZATIONS) == 3

    def test_optimizations_pcie_entry(self) -> None:
        subgroup, setting, value, desc = OPTIMIZATIONS[0]
        assert subgroup == PCIE_SUBGROUP
        assert setting == PCIE_LINK_STATE
        assert value == 0
        assert isinstance(desc, str) and desc

    def test_optimizations_usb_entry(self) -> None:
        subgroup, setting, value, desc = OPTIMIZATIONS[1]
        assert subgroup == USB_SUBGROUP
        assert setting == USB_SELECTIVE_SUSPEND
        assert value == 0
        assert isinstance(desc, str) and desc

    def test_optimizations_disk_entry(self) -> None:
        subgroup, setting, value, desc = OPTIMIZATIONS[2]
        assert subgroup == DISK_SUBGROUP
        assert setting == DISK_TIMEOUT
        assert value == 0
        assert isinstance(desc, str) and desc

    def test_all_optimization_ac_values_are_zero(self) -> None:
        for _, _, value, _ in OPTIMIZATIONS:
            assert value == 0, "All AC optimization values must be 0 (disabled)"


# ---------------------------------------------------------------------------
# PowerPlan dataclass
# ---------------------------------------------------------------------------


class TestPowerPlan:
    def test_fields(self) -> None:
        plan = PowerPlan(
            guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            name="Balanced",
            is_active=True,
        )
        assert plan.guid == "381b4222-f694-41f0-9685-ff5bb260df2e"
        assert plan.name == "Balanced"
        assert plan.is_active is True

    def test_inactive_plan(self) -> None:
        plan = PowerPlan(guid="aaaa-bbbb", name="High performance", is_active=False)
        assert plan.is_active is False


# ---------------------------------------------------------------------------
# PowerProfileResult dataclass
# ---------------------------------------------------------------------------


class TestPowerProfileResult:
    def test_success_result(self) -> None:
        r = PowerProfileResult(
            success=True,
            message="OK",
            profile_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
        )
        assert r.success is True
        assert r.message == "OK"
        assert r.profile_guid == "381b4222-f694-41f0-9685-ff5bb260df2e"

    def test_failure_result(self) -> None:
        r = PowerProfileResult(success=False, message="Something went wrong")
        assert r.success is False
        assert r.profile_guid is None
        assert r.details is None

    def test_details_field(self) -> None:
        r = PowerProfileResult(success=True, message="OK", details=["step1", "step2"])
        assert r.details == ["step1", "step2"]


# ---------------------------------------------------------------------------
# Helpers: powercfg /list output samples
# ---------------------------------------------------------------------------

POWERCFG_LIST_OUTPUT = """\
Existing Power Schemes (* Active)
-----------------------------------
Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *
Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)
Power Scheme GUID: a1841308-3541-4fab-bc81-f71556f20b4a  (Power saver)
"""

POWERCFG_LIST_WITH_FPS_BALANCED = """\
Existing Power Schemes (* Active)
-----------------------------------
Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)
Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)
Power Scheme GUID: deadbeef-dead-beef-dead-beefdeadbeef  (FPS Balanced) *
"""


def _mock_run(stdout: str = "", returncode: int = 0) -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = ""
    return r


# ---------------------------------------------------------------------------
# list_plans — output parser
# ---------------------------------------------------------------------------


class TestListPlans:
    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_parses_three_standard_plans(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            plans = mgr.list_plans()
        assert len(plans) == 3
        names = {p.name for p in plans}
        assert "Balanced" in names
        assert "High performance" in names
        assert "Power saver" in names

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_active_plan_marked_correctly(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            plans = mgr.list_plans()
        active = [p for p in plans if p.is_active]
        assert len(active) == 1
        assert active[0].name == "Balanced"
        assert active[0].guid == BALANCED_GUID

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_inactive_plans_not_marked_active(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            plans = mgr.list_plans()
        inactive = [p for p in plans if not p.is_active]
        assert len(inactive) == 2

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_guid_lowercased(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            plans = mgr.list_plans()
        for p in plans:
            assert p.guid == p.guid.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_fps_balanced_detected(self) -> None:
        mgr = PowerProfileManager()
        with patch(
            "subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_WITH_FPS_BALANCED)
        ):
            plans = mgr.list_plans()
        names = {p.name for p in plans}
        assert "FPS Balanced" in names

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_fps_balanced_active(self) -> None:
        mgr = PowerProfileManager()
        with patch(
            "subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_WITH_FPS_BALANCED)
        ):
            plans = mgr.list_plans()
        fps = next(p for p in plans if p.name == "FPS Balanced")
        assert fps.is_active is True

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_empty_output_returns_empty_list(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout="")):
            plans = mgr.list_plans()
        assert plans == []

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_subprocess_error_returns_empty_list(self) -> None:
        import subprocess

        mgr = PowerProfileManager()
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("fail")):
            plans = mgr.list_plans()
        assert plans == []

    def test_returns_empty_list_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            plans = mgr.list_plans()
        assert plans == []


# ---------------------------------------------------------------------------
# get_active_plan
# ---------------------------------------------------------------------------


class TestGetActivePlan:
    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_returns_active_plan(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            active = mgr.get_active_plan()
        assert active is not None
        assert active.name == "Balanced"

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_returns_none_when_none_active(self) -> None:
        mgr = PowerProfileManager()
        # Output without '*'
        output = """\
Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)
"""
        with patch("subprocess.run", return_value=_mock_run(stdout=output)):
            active = mgr.get_active_plan()
        assert active is None

    def test_returns_none_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            active = mgr.get_active_plan()
        assert active is None


# ---------------------------------------------------------------------------
# find_fps_balanced — caching behaviour
# ---------------------------------------------------------------------------


class TestFindFpsBalanced:
    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_returns_none_when_not_present(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            guid = mgr.find_fps_balanced()
        assert guid is None

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_returns_guid_when_present(self) -> None:
        mgr = PowerProfileManager()
        with patch(
            "subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_WITH_FPS_BALANCED)
        ):
            guid = mgr.find_fps_balanced()
        assert guid == "deadbeef-dead-beef-dead-beefdeadbeef"

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_cached_guid_is_returned_without_subprocess(self) -> None:
        mgr = PowerProfileManager()
        mgr._fps_balanced_guid = "cached-guid-value"
        with patch("subprocess.run") as mock_run:
            guid = mgr.find_fps_balanced()
        assert guid == "cached-guid-value"
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# is_fps_balanced_active
# ---------------------------------------------------------------------------


class TestIsFpsBalancedActive:
    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_true_when_fps_balanced_active(self) -> None:
        mgr = PowerProfileManager()
        with patch(
            "subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_WITH_FPS_BALANCED)
        ):
            assert mgr.is_fps_balanced_active() is True

    @pytest.mark.skipif(sys.platform != "win32", reason="list_plans only runs on win32")
    def test_false_when_balanced_is_active(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(stdout=POWERCFG_LIST_OUTPUT)):
            assert mgr.is_fps_balanced_active() is False

    def test_false_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            assert mgr.is_fps_balanced_active() is False


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

NEW_GUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
DUPLICATE_OUTPUT = f"Power Scheme GUID: {NEW_GUID}"


class TestCreate:
    def test_returns_failure_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            result = mgr.create()
        assert result.success is False
        assert "Windows" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_returns_existing_guid_when_already_present(self) -> None:
        mgr = PowerProfileManager()
        with patch.object(mgr, "find_fps_balanced", return_value="existing-guid"):
            result = mgr.create()
        assert result.success is True
        assert result.profile_guid == "existing-guid"
        assert "already exists" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_calls_duplicatescheme_with_balanced_guid(self) -> None:
        mgr = PowerProfileManager()
        duplicate_result = _mock_run(stdout=DUPLICATE_OUTPUT)
        opt_result = _mock_run()

        call_count = {"n": 0}

        def run_side_effect(cmd: list[str], **_: object) -> MagicMock:
            call_count["n"] += 1
            if "/duplicatescheme" in cmd:
                assert BALANCED_GUID in cmd
                return duplicate_result
            return opt_result

        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = mgr.create()

        assert result.success is True
        assert result.profile_guid == NEW_GUID

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_renames_profile(self) -> None:
        mgr = PowerProfileManager()
        calls_seen: list[list[str]] = []

        def run_side_effect(cmd: list[str], **_: object) -> MagicMock:
            calls_seen.append(list(cmd))
            if "/duplicatescheme" in cmd:
                return _mock_run(stdout=DUPLICATE_OUTPUT)
            return _mock_run()

        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            mgr.create()

        rename_calls = [c for c in calls_seen if "/changename" in c]
        assert len(rename_calls) == 1
        rename_cmd = rename_calls[0]
        assert NEW_GUID in rename_cmd
        assert FPS_BALANCED_NAME in rename_cmd

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_applies_all_optimizations(self) -> None:
        mgr = PowerProfileManager()
        ac_calls: list[list[str]] = []

        def run_side_effect(cmd: list[str], **_: object) -> MagicMock:
            if "/duplicatescheme" in cmd:
                return _mock_run(stdout=DUPLICATE_OUTPUT)
            if "/setacvalueindex" in cmd:
                ac_calls.append(list(cmd))
            return _mock_run()

        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = mgr.create()

        assert result.success is True
        assert len(ac_calls) == len(OPTIMIZATIONS)

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_ac_commands_use_correct_subgroup_and_setting(self) -> None:
        mgr = PowerProfileManager()
        ac_calls: list[list[str]] = []

        def run_side_effect(cmd: list[str], **_: object) -> MagicMock:
            if "/duplicatescheme" in cmd:
                return _mock_run(stdout=DUPLICATE_OUTPUT)
            if "/setacvalueindex" in cmd:
                ac_calls.append(list(cmd))
            return _mock_run()

        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            mgr.create()

        for idx, (subgroup, setting, value, _) in enumerate(OPTIMIZATIONS):
            cmd = ac_calls[idx]
            assert subgroup in cmd
            assert setting in cmd
            assert str(value) in cmd

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_returns_failure_when_duplicate_fails(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="")),
        ):
            result = mgr.create()
        assert result.success is False
        assert "Failed to duplicate" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_returns_failure_when_guid_not_in_output(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", return_value=_mock_run(returncode=0, stdout="no guid here")),
        ):
            result = mgr.create()
        assert result.success is False
        assert "GUID" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_details_list_populated(self) -> None:
        mgr = PowerProfileManager()

        def run_side_effect(cmd: list[str], **_: object) -> MagicMock:
            if "/duplicatescheme" in cmd:
                return _mock_run(stdout=DUPLICATE_OUTPUT)
            return _mock_run()

        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = mgr.create()

        assert result.details is not None
        assert len(result.details) >= 2  # At minimum: created + renamed

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_create_subprocess_error_returns_failure(self) -> None:
        import subprocess

        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch("subprocess.run", side_effect=subprocess.SubprocessError("boom")),
        ):
            result = mgr.create()
        assert result.success is False
        assert "Error" in result.message


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------


class TestActivate:
    def test_returns_failure_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            result = mgr.activate()
        assert result.success is False
        assert "Windows" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_activate_calls_setactive_with_guid(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch("subprocess.run", return_value=_mock_run()) as mock_run,
        ):
            result = mgr.activate()
        assert result.success is True
        assert result.profile_guid == NEW_GUID
        called_cmd = mock_run.call_args[0][0]
        assert "/setactive" in called_cmd
        assert NEW_GUID in called_cmd

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_activate_creates_profile_when_not_found(self) -> None:
        mgr = PowerProfileManager()
        create_result = PowerProfileResult(success=True, message="Created", profile_guid=NEW_GUID)
        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch.object(mgr, "create", return_value=create_result),
            patch("subprocess.run", return_value=_mock_run()),
        ):
            result = mgr.activate()
        assert result.success is True

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_activate_returns_failure_when_create_fails(self) -> None:
        mgr = PowerProfileManager()
        create_result = PowerProfileResult(success=False, message="Creation failed")
        with (
            patch.object(mgr, "find_fps_balanced", return_value=None),
            patch.object(mgr, "create", return_value=create_result),
        ):
            result = mgr.activate()
        assert result.success is False

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_activate_returns_failure_on_setactive_error(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="")),
        ):
            result = mgr.activate()
        assert result.success is False
        assert "Failed to activate" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_activate_subprocess_error_returns_failure(self) -> None:
        import subprocess

        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch("subprocess.run", side_effect=subprocess.SubprocessError("boom")),
        ):
            result = mgr.activate()
        assert result.success is False
        assert "Error" in result.message


# ---------------------------------------------------------------------------
# revert
# ---------------------------------------------------------------------------


class TestRevert:
    def test_returns_failure_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            result = mgr.revert()
        assert result.success is False
        assert "Windows" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_revert_calls_setactive_with_balanced_guid(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run()) as mock_run:
            result = mgr.revert()
        assert result.success is True
        assert result.profile_guid == BALANCED_GUID
        called_cmd = mock_run.call_args[0][0]
        assert "/setactive" in called_cmd
        assert BALANCED_GUID in called_cmd

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_revert_returns_failure_on_error(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="")):
            result = mgr.revert()
        assert result.success is False
        assert "Failed to revert" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_revert_subprocess_error_returns_failure(self) -> None:
        import subprocess

        mgr = PowerProfileManager()
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("boom")):
            result = mgr.revert()
        assert result.success is False

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_revert_message_contains_balanced(self) -> None:
        mgr = PowerProfileManager()
        with patch("subprocess.run", return_value=_mock_run()):
            result = mgr.revert()
        assert "Balanced" in result.message


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_returns_failure_on_non_windows(self) -> None:
        mgr = PowerProfileManager()
        with patch("sys.platform", "linux"):
            result = mgr.delete()
        assert result.success is False
        assert "Windows" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_returns_success_when_profile_not_found(self) -> None:
        mgr = PowerProfileManager()
        with patch.object(mgr, "find_fps_balanced", return_value=None):
            result = mgr.delete()
        assert result.success is True
        assert "does not exist" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_delete_calls_powercfg_delete_with_guid(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch.object(mgr, "is_fps_balanced_active", return_value=False),
            patch("subprocess.run", return_value=_mock_run()) as mock_run,
        ):
            result = mgr.delete()
        assert result.success is True
        called_cmd = mock_run.call_args[0][0]
        assert "/delete" in called_cmd
        assert NEW_GUID in called_cmd

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_delete_reverts_when_fps_balanced_is_active(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch.object(mgr, "is_fps_balanced_active", return_value=True),
            patch.object(mgr, "revert") as mock_revert,
            patch("subprocess.run", return_value=_mock_run()),
        ):
            mgr.delete()
        mock_revert.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_delete_does_not_revert_when_fps_balanced_not_active(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch.object(mgr, "is_fps_balanced_active", return_value=False),
            patch.object(mgr, "revert") as mock_revert,
            patch("subprocess.run", return_value=_mock_run()),
        ):
            mgr.delete()
        mock_revert.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_delete_clears_cached_guid_on_success(self) -> None:
        mgr = PowerProfileManager()
        mgr._fps_balanced_guid = NEW_GUID
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch.object(mgr, "is_fps_balanced_active", return_value=False),
            patch("subprocess.run", return_value=_mock_run()),
        ):
            result = mgr.delete()
        assert result.success is True
        assert mgr._fps_balanced_guid is None

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_delete_returns_failure_on_nonzero_returncode(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch.object(mgr, "is_fps_balanced_active", return_value=False),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="")),
        ):
            result = mgr.delete()
        assert result.success is False
        assert "Failed to delete" in result.message

    @pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
    def test_delete_subprocess_error_returns_failure(self) -> None:
        import subprocess

        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "find_fps_balanced", return_value=NEW_GUID),
            patch.object(mgr, "is_fps_balanced_active", return_value=False),
            patch("subprocess.run", side_effect=subprocess.SubprocessError("boom")),
        ):
            result = mgr.delete()
        assert result.success is False
        assert "Error" in result.message


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    @pytest.mark.skipif(sys.platform != "win32", reason="get_active_plan only on win32")
    def test_status_when_fps_balanced_active(self) -> None:
        mgr = PowerProfileManager()
        fps_plan = PowerPlan(
            guid="deadbeef-dead-beef-dead-beefdeadbeef", name=FPS_BALANCED_NAME, is_active=True
        )
        with (
            patch.object(mgr, "get_active_plan", return_value=fps_plan),
            patch.object(mgr, "find_fps_balanced", return_value=fps_plan.guid),
        ):
            s = mgr.status()
        assert s["active_plan"] == FPS_BALANCED_NAME
        assert s["fps_balanced_active"] is True
        assert s["fps_balanced_exists"] is True
        assert isinstance(s["optimizations"], list)
        assert len(s["optimizations"]) == len(OPTIMIZATIONS)

    @pytest.mark.skipif(sys.platform != "win32", reason="get_active_plan only on win32")
    def test_status_when_balanced_active(self) -> None:
        mgr = PowerProfileManager()
        balanced_plan = PowerPlan(guid=BALANCED_GUID, name="Balanced", is_active=True)
        with (
            patch.object(mgr, "get_active_plan", return_value=balanced_plan),
            patch.object(mgr, "find_fps_balanced", return_value=None),
        ):
            s = mgr.status()
        assert s["active_plan"] == "Balanced"
        assert s["fps_balanced_active"] is False
        assert s["fps_balanced_exists"] is False
        assert s["optimizations"] == []

    @pytest.mark.skipif(sys.platform != "win32", reason="get_active_plan only on win32")
    def test_status_when_no_active_plan(self) -> None:
        mgr = PowerProfileManager()
        with (
            patch.object(mgr, "get_active_plan", return_value=None),
            patch.object(mgr, "find_fps_balanced", return_value=None),
        ):
            s = mgr.status()
        assert s["active_plan"] == "Unknown"
        assert s["active_guid"] == ""

    @pytest.mark.skipif(sys.platform != "win32", reason="get_active_plan only on win32")
    def test_status_keys_present(self) -> None:
        mgr = PowerProfileManager()
        balanced_plan = PowerPlan(guid=BALANCED_GUID, name="Balanced", is_active=True)
        with (
            patch.object(mgr, "get_active_plan", return_value=balanced_plan),
            patch.object(mgr, "find_fps_balanced", return_value=None),
        ):
            s = mgr.status()
        assert set(s.keys()) == {
            "active_plan",
            "active_guid",
            "fps_balanced_exists",
            "fps_balanced_active",
            "optimizations",
        }


# ---------------------------------------------------------------------------
# get_power_profile_manager singleton
# ---------------------------------------------------------------------------


class TestGetPowerProfileManager:
    def test_returns_power_profile_manager_instance(self) -> None:
        import fpstune.core.power_profile as pp_mod

        # Reset singleton for test isolation
        original = pp_mod._power_profile_manager
        pp_mod._power_profile_manager = None
        try:
            mgr = get_power_profile_manager()
            assert isinstance(mgr, PowerProfileManager)
        finally:
            pp_mod._power_profile_manager = original

    def test_returns_same_instance_on_second_call(self) -> None:
        import fpstune.core.power_profile as pp_mod

        original = pp_mod._power_profile_manager
        pp_mod._power_profile_manager = None
        try:
            mgr1 = get_power_profile_manager()
            mgr2 = get_power_profile_manager()
            assert mgr1 is mgr2
        finally:
            pp_mod._power_profile_manager = original
