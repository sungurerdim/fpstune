"""Tests for BcdEditExecutor."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.executors.bcdedit import BcdEditExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bcd_setting(**overrides) -> SettingExecutor:
    defaults = {
        "id": "timer:hpet",
        "category": SettingCategory.TIMER,
        "display_name": "HPET",
        "description": "Controls HPET platform clock.",
        "detect_type": DetectType.BCDEDIT,
        "apply_type": DetectType.BCDEDIT,
        "detect_command": "useplatformclock",
        "apply_command": "useplatformclock",
        "detect_args": {},
        "apply_args": {},
        "value_map": {"yes": "enabled", None: "disabled"},
        "apply_value_map": {"enabled": "yes", "disabled": None},
        "value_type": SettingValueType.CHOICE,
        "choices": ("enabled", "disabled"),
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)


def _clear_executor_cache():
    """Reset class-level BCD cache between tests."""
    BcdEditExecutor._cache = None


# ---------------------------------------------------------------------------
# _run — platform guard
# ---------------------------------------------------------------------------


class TestBcdEditExecutorRun:
    """Tests for BcdEditExecutor._run() platform guard."""

    def setup_method(self):
        _clear_executor_cache()

    def test_run_non_windows_returns_false(self):
        executor = BcdEditExecutor()
        with patch("sys.platform", "linux"):
            success, output = executor._run("/enum {current}")
        assert success is False
        assert "not available" in output.lower() or "platform" in output.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_success(self):
        executor = BcdEditExecutor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="The operation completed successfully.", stderr=""
            )
            success, output = executor._run("/enum {current}")
        assert success is True
        assert "completed" in output.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_failure_returncode(self):
        executor = BcdEditExecutor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Access is denied.")
            success, output = executor._run("/set {current} useplatformclock yes")
        assert success is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_timeout_returns_false(self):
        import subprocess

        executor = BcdEditExecutor()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["bcdedit"], 10)):
            success, output = executor._run("/enum {current}")
        assert success is False
        assert "timed out" in output.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_exception_returns_false(self):
        executor = BcdEditExecutor()
        with patch("subprocess.run", side_effect=OSError("No such file")):
            success, output = executor._run("/enum {current}")
        assert success is False


# ---------------------------------------------------------------------------
# _get_all_values_bcdedit
# ---------------------------------------------------------------------------


class TestGetAllValuesBcdedit:
    """Tests for BcdEditExecutor._get_all_values_bcdedit() parsing."""

    def setup_method(self):
        _clear_executor_cache()

    # Realistic bcdedit /enum {current} output
    BCDEDIT_OUTPUT_HPET_ENABLED = """\
Windows Boot Loader
-------------------
identifier              {current}
device                  partition=C:
path                    \\Windows\\system32\\winload.exe
description             Windows 11
locale                  en-US
inherit                 {bootloadersettings}
recoverysequence        {aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}
recoveryenabled         Yes
allowedinmemorysettings 0x15000075
osdevice                partition=C:
systemroot              \\Windows
resumeobject            {ffffffff-aaaa-bbbb-cccc-dddddddddddd}
nx                      OptIn
bootmenupolicy          Standard
useplatformclock        Yes
disabledynamictick      Yes
"""

    BCDEDIT_OUTPUT_NO_SETTINGS = """\
Windows Boot Loader
-------------------
identifier              {current}
device                  partition=C:
path                    \\Windows\\system32\\winload.exe
description             Windows 11
locale                  en-US
nx                      OptIn
bootmenupolicy          Standard
"""

    BCDEDIT_OUTPUT_TSC_LEGACY = """\
Windows Boot Loader
-------------------
identifier              {current}
device                  partition=C:
tscsyncpolicy           Legacy
"""

    BCDEDIT_OUTPUT_TSC_ENHANCED = """\
Windows Boot Loader
-------------------
identifier              {current}
tscsyncpolicy           Enhanced
useplatformtick         Yes
"""

    @pytest.fixture
    def executor(self):
        _clear_executor_cache()
        return BcdEditExecutor()

    def test_parses_useplatformclock_yes(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_HPET_ENABLED)):
            values = executor._get_all_values_bcdedit()
        assert values["useplatformclock"] == "yes"

    def test_parses_disabledynamictick_yes(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_HPET_ENABLED)):
            values = executor._get_all_values_bcdedit()
        assert values["disabledynamictick"] == "yes"

    def test_absent_boolean_is_none(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_NO_SETTINGS)):
            values = executor._get_all_values_bcdedit()
        assert values["useplatformclock"] is None
        assert values["disabledynamictick"] is None
        assert values["useplatformtick"] is None

    def test_parses_tscsyncpolicy_legacy(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_TSC_LEGACY)):
            values = executor._get_all_values_bcdedit()
        assert values["tscsyncpolicy"] == "legacy"

    def test_parses_tscsyncpolicy_enhanced(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_TSC_ENHANCED)):
            values = executor._get_all_values_bcdedit()
        assert values["tscsyncpolicy"] == "enhanced"

    def test_parses_useplatformtick_yes(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_TSC_ENHANCED)):
            values = executor._get_all_values_bcdedit()
        assert values["useplatformtick"] == "yes"

    def test_raises_runtime_error_on_bcdedit_failure(self, executor):
        with (
            patch.object(executor, "_run", return_value=(False, "Access is denied.")),
            pytest.raises(RuntimeError, match="bcdedit /enum"),
        ):
            executor._get_all_values_bcdedit()

    def test_all_expected_keys_present(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.BCDEDIT_OUTPUT_NO_SETTINGS)):
            values = executor._get_all_values_bcdedit()
        for key in ["useplatformclock", "useplatformtick", "disabledynamictick", "tscsyncpolicy"]:
            assert key in values

    def test_empty_output_all_none(self, executor):
        with patch.object(executor, "_run", return_value=(True, "")):
            values = executor._get_all_values_bcdedit()
        for key in ["useplatformclock", "useplatformtick", "disabledynamictick", "tscsyncpolicy"]:
            assert values[key] is None


# ---------------------------------------------------------------------------
# detect — cache behaviour
# ---------------------------------------------------------------------------


class TestBcdEditExecutorDetect:
    """Tests for BcdEditExecutor.detect() cache and value mapping."""

    def setup_method(self):
        _clear_executor_cache()

    @pytest.fixture
    def executor(self):
        _clear_executor_cache()
        return BcdEditExecutor()

    def test_detect_uses_value_map(self, executor):
        BcdEditExecutor._cache = {
            "useplatformclock": "yes",
            "useplatformtick": None,
            "disabledynamictick": None,
            "tscsyncpolicy": None,
        }
        setting = _make_bcd_setting(
            detect_command="useplatformclock",
            value_map={"yes": "enabled", None: "disabled"},
        )
        value, error = executor.detect(setting)
        assert value == "enabled"
        assert error is None

    def test_detect_maps_none_to_display(self, executor):
        BcdEditExecutor._cache = {
            "useplatformclock": None,
            "useplatformtick": None,
            "disabledynamictick": None,
            "tscsyncpolicy": None,
        }
        setting = _make_bcd_setting(
            detect_command="useplatformclock",
            value_map={"yes": "enabled", None: "disabled"},
        )
        value, error = executor.detect(setting)
        assert value == "disabled"
        assert error is None

    def test_detect_caches_after_first_call(self, executor):
        """Second detect() must not call WMI/bcdedit again."""
        BcdEditExecutor._cache = {
            "useplatformclock": "yes",
            "useplatformtick": None,
            "disabledynamictick": None,
            "tscsyncpolicy": None,
        }
        setting = _make_bcd_setting()

        with patch.object(executor, "_get_all_values_wmi") as mock_wmi:
            executor.detect(setting)
            executor.detect(setting)

        mock_wmi.assert_not_called()

    def test_detect_returns_raw_when_no_map(self, executor):
        BcdEditExecutor._cache = {
            "useplatformclock": "yes",
            "useplatformtick": None,
            "disabledynamictick": None,
            "tscsyncpolicy": "legacy",
        }
        setting = _make_bcd_setting(
            detect_command="tscsyncpolicy",
            value_map={},
        )
        value, error = executor.detect(setting)
        assert value == "legacy"
        assert error is None

    def test_detect_propagates_wmi_error(self, executor):
        """When both WMI and bcdedit fail, error is propagated."""
        with patch.object(
            executor,
            "_get_all_values_wmi",
            side_effect=RuntimeError("Admin required"),
        ):
            setting = _make_bcd_setting()
            value, error = executor.detect(setting)
        assert value is None
        assert error is not None
        assert "admin" in error.lower() or "bcd" in error.lower()


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestBcdEditExecutorApply:
    """Tests for BcdEditExecutor.apply()."""

    def setup_method(self):
        _clear_executor_cache()

    @pytest.fixture
    def executor(self):
        _clear_executor_cache()
        return BcdEditExecutor()

    def test_apply_set_value(self, executor):
        setting = _make_bcd_setting(
            apply_command="useplatformclock",
            apply_value_map={"enabled": "yes"},
        )
        with patch.object(executor, "_run", return_value=(True, "")) as mock_run:
            success, error = executor.apply(setting, "enabled")
        assert success is True
        assert error is None
        called_args = mock_run.call_args[0][0]
        assert "/set" in called_args
        assert "useplatformclock" in called_args
        assert "yes" in called_args

    def test_apply_delete_value_when_raw_is_none(self, executor):
        setting = _make_bcd_setting(
            apply_command="useplatformclock",
            apply_value_map={"disabled": None},
        )
        with patch.object(executor, "_run", return_value=(True, "")) as mock_run:
            success, error = executor.apply(setting, "disabled")
        assert success is True
        assert error is None
        called_args = mock_run.call_args[0][0]
        assert "/deletevalue" in called_args
        assert "useplatformclock" in called_args

    def test_apply_deletevalue_succeeds_when_element_not_found(self, executor):
        """bcdedit /deletevalue may fail if value was never set — this is OK."""
        setting = _make_bcd_setting(
            apply_command="useplatformclock",
            apply_value_map={"disabled": None},
        )
        with patch.object(executor, "_run", return_value=(False, "element not found")):
            success, error = executor.apply(setting, "disabled")
        assert success is True

    def test_apply_failure_on_set_returns_false(self, executor):
        setting = _make_bcd_setting(
            apply_command="useplatformclock",
            apply_value_map={"enabled": "yes"},
        )
        with patch.object(executor, "_run", return_value=(False, "Access is denied.")):
            success, error = executor.apply(setting, "enabled")
        assert success is False
        assert error is not None

    def test_apply_invalidates_cache(self, executor):
        """After apply, the class-level cache must be cleared."""
        BcdEditExecutor._cache = {"useplatformclock": "yes"}
        setting = _make_bcd_setting(
            apply_command="useplatformclock",
            apply_value_map={"enabled": "yes"},
        )
        with patch.object(executor, "_run", return_value=(True, "")):
            executor.apply(setting, "enabled")
        assert BcdEditExecutor._cache is None


# ---------------------------------------------------------------------------
# apply — token validation (SEC-21)
# ---------------------------------------------------------------------------


class TestBcdEditApplyTokenValidation:
    """SEC-21 regression: _run tokenizes the command with args.split(), so a
    value containing a space appended extra bcdedit arguments — e.g. a value of
    "legacy testsigning on" also ran "/set {current} ... testsigning on"."""

    @pytest.fixture
    def executor(self):
        _clear_executor_cache()
        return BcdEditExecutor()

    @pytest.mark.parametrize(
        "hostile_value",
        [
            "legacy testsigning on",
            "yes nointegritychecks on",
            "$(calc)",
            "enhanced\nrecoveryenabled no",
            "'quoted'",
            "",
        ],
    )
    def test_multi_token_value_is_rejected_before_running(self, executor, hostile_value):
        setting = _make_bcd_setting(apply_command="tscsyncpolicy", apply_value_map={})
        with patch.object(executor, "_run") as mock_run:
            success, error = executor.apply(setting, hostile_value)
        assert success is False
        mock_run.assert_not_called()
        assert "single-token" in (error or "")

    def test_multi_token_value_name_is_rejected(self, executor):
        setting = _make_bcd_setting(
            apply_command="useplatformclock testsigning",
            apply_value_map={"enabled": "yes"},
        )
        with patch.object(executor, "_run") as mock_run:
            success, error = executor.apply(setting, "enabled")
        assert success is False
        mock_run.assert_not_called()
        assert "value name" in (error or "")

    @pytest.mark.parametrize("value", ["yes", "no", "legacy", "enhanced", "2"])
    def test_single_token_values_still_apply(self, executor, value):
        setting = _make_bcd_setting(apply_command="tscsyncpolicy", apply_value_map={})
        with patch.object(executor, "_run", return_value=(True, "")) as mock_run:
            success, _error = executor.apply(setting, value)
        assert success is True
        assert mock_run.call_args[0][0] == f"/set {{current}} tscsyncpolicy {value}"

    def test_surrounding_whitespace_is_trimmed_not_rejected(self, executor):
        setting = _make_bcd_setting(apply_command="tscsyncpolicy", apply_value_map={})
        with patch.object(executor, "_run", return_value=(True, "")) as mock_run:
            success, _error = executor.apply(setting, " enhanced ")
        assert success is True
        assert mock_run.call_args[0][0] == "/set {current} tscsyncpolicy enhanced"


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------


class TestBcdEditInvalidateCache:
    def test_invalidate_cache_clears_class_level_cache(self):
        BcdEditExecutor._cache = {"useplatformclock": "yes"}
        BcdEditExecutor.invalidate_cache()
        assert BcdEditExecutor._cache is None

    def test_invalidate_cache_idempotent_when_already_none(self):
        BcdEditExecutor._cache = None
        BcdEditExecutor.invalidate_cache()
        assert BcdEditExecutor._cache is None
