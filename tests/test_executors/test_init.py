"""Tests for CommandExecutor dispatch and coerce_value_type."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.executors import CommandExecutor, coerce_value_type


@pytest.fixture(autouse=True)
def _restore_executor_cache():
    """Keep this module's mocks out of the rest of the pytest session.

    `CommandExecutor._executors` is a class attribute, and several tests below
    assign a MagicMock straight into it. `setup_method` clears it *before* each
    test, so nothing ran after the last one and the cache was left holding a mock
    for "registry" and "powershell" for the remainder of the session. Any later
    test doing a real detect then received that mock: the Windows contract scan
    reported all 320 settings as failed, in 10 seconds, because no command ran.
    """
    saved = dict(CommandExecutor._executors)
    yield
    CommandExecutor._executors = saved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_setting(**overrides) -> SettingExecutor:
    """Build a minimal SettingExecutor for testing.

    Uses STRING value_type by default to avoid the CHOICE/choices validation.
    Pass value_type=SettingValueType.CHOICE + choices=(...) explicitly when needed.
    """
    defaults = {
        "id": "test:setting",
        "category": SettingCategory.CORE,
        "display_name": "Test Setting",
        "description": "A test setting.",
        # STRING avoids the __post_init__ CHOICE → non-empty choices constraint
        "value_type": SettingValueType.STRING,
        "detect_type": DetectType.REGISTRY,
        "apply_type": DetectType.REGISTRY,
        "detect_command": "",
        "apply_command": "",
        "detect_args": {},
        "apply_args": {},
        "value_map": {},
        "apply_value_map": {},
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)


# ---------------------------------------------------------------------------
# coerce_value_type
# ---------------------------------------------------------------------------


class TestCoerceValueType:
    """Tests for the coerce_value_type function."""

    # --- None passthrough ---
    def test_none_returns_none(self):
        assert coerce_value_type(None, SettingValueType.INT) is None

    def test_none_returns_none_bool(self):
        assert coerce_value_type(None, SettingValueType.BOOL) is None

    # --- INT ---
    def test_int_from_plain_string(self):
        assert coerce_value_type("42", SettingValueType.INT) == 42

    def test_int_from_float_string(self):
        assert coerce_value_type("165.0", SettingValueType.INT) == 165

    def test_int_from_hex_string(self):
        assert coerce_value_type("0x1", SettingValueType.INT) == 1

    def test_int_from_hex_uppercase(self):
        assert coerce_value_type("0xFF", SettingValueType.INT) == 255

    def test_int_from_zero_hex(self):
        assert coerce_value_type("0x00000000", SettingValueType.INT) == 0

    def test_int_from_int(self):
        assert coerce_value_type(7, SettingValueType.INT) == 7

    def test_int_from_float(self):
        assert coerce_value_type(3.0, SettingValueType.INT) == 3

    def test_int_empty_string_returns_none(self):
        assert coerce_value_type("   ", SettingValueType.INT) is None

    def test_int_invalid_string_returns_original(self):
        # Non-numeric string cannot be parsed; original returned
        result = coerce_value_type("notanumber", SettingValueType.INT)
        assert result == "notanumber"

    def test_int_strips_whitespace(self):
        assert coerce_value_type("  10  ", SettingValueType.INT) == 10

    # --- FLOAT ---
    def test_float_from_string(self):
        assert coerce_value_type("3.14", SettingValueType.FLOAT) == pytest.approx(3.14)

    def test_float_from_int_string(self):
        assert coerce_value_type("100", SettingValueType.FLOAT) == pytest.approx(100.0)

    def test_float_empty_string_returns_none(self):
        assert coerce_value_type("", SettingValueType.FLOAT) is None

    def test_float_from_float(self):
        result = coerce_value_type(1.5, SettingValueType.FLOAT)
        assert result == pytest.approx(1.5)

    def test_float_invalid_returns_original(self):
        result = coerce_value_type("abc", SettingValueType.FLOAT)
        assert result == "abc"

    # --- BOOL ---
    def test_bool_true_bool(self):
        assert coerce_value_type(True, SettingValueType.BOOL) is True

    def test_bool_false_bool(self):
        assert coerce_value_type(False, SettingValueType.BOOL) is False

    def test_bool_from_string_true_variants(self):
        for s in ("true", "1", "yes", "on", "enabled"):
            assert coerce_value_type(s, SettingValueType.BOOL) is True, f"Failed for {s!r}"

    def test_bool_from_string_false_variants(self):
        for s in ("false", "0", "no", "off", "disabled"):
            assert coerce_value_type(s, SettingValueType.BOOL) is False, f"Failed for {s!r}"

    def test_bool_from_int_nonzero(self):
        assert coerce_value_type(1, SettingValueType.BOOL) is True

    def test_bool_from_int_zero(self):
        assert coerce_value_type(0, SettingValueType.BOOL) is False

    def test_bool_unknown_string_returns_original(self):
        result = coerce_value_type("maybe", SettingValueType.BOOL)
        assert result == "maybe"

    def test_bool_case_insensitive(self):
        assert coerce_value_type("TRUE", SettingValueType.BOOL) is True
        assert coerce_value_type("False", SettingValueType.BOOL) is False
        assert coerce_value_type("YES", SettingValueType.BOOL) is True

    # --- STRING / CHOICE (passthrough) ---
    def test_string_passthrough(self):
        assert coerce_value_type("hello", SettingValueType.STRING) == "hello"

    def test_choice_passthrough(self):
        assert coerce_value_type("enabled", SettingValueType.CHOICE) == "enabled"

    def test_int_passthrough_for_string_type(self):
        assert coerce_value_type(42, SettingValueType.STRING) == 42


# ---------------------------------------------------------------------------
# CommandExecutor._get_executor dispatch
# ---------------------------------------------------------------------------


class TestCommandExecutorGetExecutor:
    """Tests for CommandExecutor._get_executor dispatch."""

    def setup_method(self):
        """Clear the executor cache before each test."""
        CommandExecutor._executors = {}

    def test_returns_powercfg_executor(self):
        from fpstune.settings.executors.powercfg import PowerCfgExecutor

        executor = CommandExecutor._get_executor("powercfg")
        assert isinstance(executor, PowerCfgExecutor)

    def test_returns_registry_executor(self):
        from fpstune.settings.executors.registry import RegistryExecutor

        executor = CommandExecutor._get_executor("registry")
        assert isinstance(executor, RegistryExecutor)

    def test_returns_powershell_executor(self):
        from fpstune.settings.executors.powershell import PowerShellExecutor

        executor = CommandExecutor._get_executor("powershell")
        assert isinstance(executor, PowerShellExecutor)

    def test_returns_netsh_executor(self):
        from fpstune.settings.executors.netsh import NetshExecutor

        executor = CommandExecutor._get_executor("netsh")
        assert isinstance(executor, NetshExecutor)

    def test_returns_bcdedit_executor(self):
        from fpstune.settings.executors.bcdedit import BcdEditExecutor

        executor = CommandExecutor._get_executor("bcdedit")
        assert isinstance(executor, BcdEditExecutor)

    def test_returns_nvprofile_executor(self):
        from fpstune.settings.executors.nvprofile import NvProfileExecutor

        executor = CommandExecutor._get_executor("nvprofile")
        assert isinstance(executor, NvProfileExecutor)

    def test_returns_none_for_unknown_type(self):
        executor = CommandExecutor._get_executor("unknown_type_xyz")
        assert executor is None

    def test_returns_none_for_empty_string(self):
        executor = CommandExecutor._get_executor("")
        assert executor is None

    def test_executors_cached_after_first_call(self):
        # Call twice; second call must use the same executor instance
        e1 = CommandExecutor._get_executor("registry")
        e2 = CommandExecutor._get_executor("registry")
        assert e1 is e2

    def test_all_six_executor_types_registered(self):
        # After first call the map must have all 6 types
        CommandExecutor._get_executor("registry")
        assert "powercfg" in CommandExecutor._executors
        assert "registry" in CommandExecutor._executors
        assert "powershell" in CommandExecutor._executors
        assert "netsh" in CommandExecutor._executors
        assert "bcdedit" in CommandExecutor._executors
        assert "nvprofile" in CommandExecutor._executors


# ---------------------------------------------------------------------------
# CommandExecutor.detect / apply (high-level routing)
# ---------------------------------------------------------------------------


class TestCommandExecutorDetect:
    """Tests for CommandExecutor.detect routing."""

    def setup_method(self):
        CommandExecutor._executors = {}

    def test_detect_unknown_type_returns_error(self):
        """When _get_executor returns None (unknown type), detect() must error."""
        setting = _make_setting(detect_type=DetectType.REGISTRY)
        # Simulate an unknown executor type by making _get_executor return None
        with patch.object(CommandExecutor, "_get_executor", return_value=None):
            value, error = CommandExecutor.detect(setting)
        assert value is None
        assert error is not None

    def test_detect_routes_to_executor(self):
        """detect() should call the matching executor's detect()."""
        setting = _make_setting(detect_type=DetectType.REGISTRY)
        mock_exec = MagicMock()
        mock_exec.detect.return_value = (42, None)
        CommandExecutor._executors = {"registry": mock_exec}

        value, error = CommandExecutor.detect(setting)

        mock_exec.detect.assert_called_once_with(setting)
        assert error is None

    def test_detect_coerces_int_value(self):
        """detect() should coerce string '5' to int 5 for INT type."""
        setting = _make_setting(
            detect_type=DetectType.REGISTRY,
            value_type=SettingValueType.INT,
        )
        mock_exec = MagicMock()
        mock_exec.detect.return_value = ("5", None)
        CommandExecutor._executors = {"registry": mock_exec}

        value, error = CommandExecutor.detect(setting)
        assert value == 5
        assert error is None

    def test_detect_does_not_coerce_on_error(self):
        """detect() must not coerce when executor returns an error."""
        setting = _make_setting(
            detect_type=DetectType.REGISTRY,
            value_type=SettingValueType.INT,
        )
        mock_exec = MagicMock()
        mock_exec.detect.return_value = (None, "some error")
        CommandExecutor._executors = {"registry": mock_exec}

        value, error = CommandExecutor.detect(setting)
        assert value is None
        assert error == "some error"


class TestCommandExecutorApply:
    """Tests for CommandExecutor.apply routing."""

    def setup_method(self):
        CommandExecutor._executors = {}

    def test_apply_routes_to_executor(self):
        setting = _make_setting(apply_type=DetectType.REGISTRY)
        mock_exec = MagicMock()
        mock_exec.apply.return_value = (True, None)
        CommandExecutor._executors = {"registry": mock_exec}

        success, error = CommandExecutor.apply(setting, "enabled")

        mock_exec.apply.assert_called_once_with(setting, "enabled")
        assert success is True

    def test_apply_action_false_skips_executor(self):
        """is_action=True with falsy value must skip execution and return True."""
        setting = _make_setting(
            apply_type=DetectType.POWERSHELL,
            is_action=True,
        )
        mock_exec = MagicMock()
        CommandExecutor._executors = {"powershell": mock_exec}

        success, error = CommandExecutor.apply(setting, False)

        mock_exec.apply.assert_not_called()
        assert success is True
        assert error is None

    def test_apply_action_truthy_runs_executor(self):
        """is_action=True with truthy value must call executor."""
        setting = _make_setting(
            apply_type=DetectType.POWERSHELL,
            is_action=True,
        )
        mock_exec = MagicMock()
        mock_exec.apply.return_value = (True, None)
        CommandExecutor._executors = {"powershell": mock_exec}

        success, error = CommandExecutor.apply(setting, True)

        mock_exec.apply.assert_called_once()
        assert success is True

    def test_apply_unknown_type_returns_error(self):
        setting = _make_setting(apply_type=DetectType.REGISTRY)
        # Empty executor map so "registry" is not found
        CommandExecutor._executors = {"powercfg": MagicMock()}

        success, error = CommandExecutor.apply(setting, "enabled")

        assert success is False
        assert error is not None
