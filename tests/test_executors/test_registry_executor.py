"""Tests for RegistryExecutor."""

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
from fpstune.settings.executors.registry import RegistryExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HAGS_PATH = (
    "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games"
)
_HAGS_NAME = "GPU Priority"


def _make_reg_setting(**overrides) -> SettingExecutor:
    defaults = {
        "id": "core:gpu_priority",
        "category": SettingCategory.CORE,
        "display_name": "GPU Priority",
        "description": "Sets GPU scheduling priority.",
        "detect_type": DetectType.REGISTRY,
        "apply_type": DetectType.REGISTRY,
        "detect_command": "",
        "apply_command": "",
        "detect_args": {"path": _HAGS_PATH, "name": _HAGS_NAME, "hive": "HKLM"},
        "apply_args": {
            "path": _HAGS_PATH,
            "name": _HAGS_NAME,
            "hive": "HKLM",
            "type": "REG_DWORD",
        },
        "value_map": {},
        "apply_value_map": {},
        "value_type": SettingValueType.INT,
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)


# ---------------------------------------------------------------------------
# detect — platform guard
# ---------------------------------------------------------------------------


class TestRegistryExecutorDetectPlatform:
    def test_detect_non_windows_returns_error(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting()
        with patch("sys.platform", "linux"):
            value, error = executor.detect(setting)
        assert value is None
        assert error is not None
        assert "not available" in error.lower() or "platform" in error.lower()

    def test_detect_missing_path_returns_error(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(detect_args={"name": "foo", "hive": "HKLM"})
        with patch("sys.platform", "win32"):
            value, error = executor.detect(setting)
        assert value is None
        assert error is not None
        assert "path" in error.lower() or "name" in error.lower()

    def test_detect_missing_name_returns_error(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(detect_args={"path": _HAGS_PATH, "hive": "HKLM"})
        with patch("sys.platform", "win32"):
            value, error = executor.detect(setting)
        assert value is None
        assert error is not None


# ---------------------------------------------------------------------------
# detect — winreg mocking
# ---------------------------------------------------------------------------


class TestRegistryExecutorDetect:
    """Tests for RegistryExecutor.detect() with mocked winreg."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_detect_returns_raw_value(self):
        import winreg

        executor = RegistryExecutor()
        setting = _make_reg_setting()

        mock_key = MagicMock()
        with (
            patch("winreg.OpenKey", return_value=mock_key.__enter__.return_value),
            patch("winreg.QueryValueEx", return_value=(8, winreg.REG_DWORD)),
        ):
            value, error = executor.detect(setting)

        assert error is None
        assert value == 8

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_detect_applies_value_map(self):
        import winreg

        executor = RegistryExecutor()
        setting = _make_reg_setting(value_map={1: "enabled", 0: "disabled"})

        mock_key = MagicMock()
        with (
            patch("winreg.OpenKey", return_value=mock_key.__enter__.return_value),
            patch("winreg.QueryValueEx", return_value=(1, winreg.REG_DWORD)),
        ):
            value, error = executor.detect(setting)

        assert error is None
        assert value == "enabled"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_detect_file_not_found_returns_none(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting()

        with patch("winreg.OpenKey", side_effect=FileNotFoundError):
            value, error = executor.detect(setting)

        # Not found = (None, None) when no None mapping
        assert value is None
        assert error is None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_detect_file_not_found_with_none_mapping(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(value_map={None: "not_set", 1: "enabled"})

        with patch("winreg.OpenKey", side_effect=FileNotFoundError):
            value, error = executor.detect(setting)

        assert value == "not_set"
        assert error is None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_detect_permission_error_returns_error(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting()

        with patch("winreg.OpenKey", side_effect=PermissionError):
            value, error = executor.detect(setting)

        assert value is None
        assert error is not None
        assert "permission" in error.lower() or "administrator" in error.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_detect_generic_exception_returns_error(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting()

        with patch("winreg.OpenKey", side_effect=OSError("Registry error")):
            value, error = executor.detect(setting)

        assert value is None
        assert error is not None


# ---------------------------------------------------------------------------
# apply — platform guard
# ---------------------------------------------------------------------------


class TestRegistryExecutorApplyPlatform:
    def test_apply_non_windows_returns_false(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting()
        with patch("sys.platform", "linux"):
            success, error = executor.apply(setting, 8)
        assert success is False
        assert error is not None

    def test_apply_missing_path_returns_false(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(apply_args={"name": "foo", "hive": "HKLM", "type": "REG_DWORD"})
        with patch("sys.platform", "win32"):
            success, error = executor.apply(setting, 8)
        assert success is False
        assert error is not None

    def test_apply_missing_name_returns_false(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(
            apply_args={"path": _HAGS_PATH, "hive": "HKLM", "type": "REG_DWORD"}
        )
        with patch("sys.platform", "win32"):
            success, error = executor.apply(setting, 8)
        assert success is False
        assert error is not None


# ---------------------------------------------------------------------------
# apply — sentinel values
# ---------------------------------------------------------------------------


class TestRegistryExecutorApplySentinels:
    """Sentinel values (not_available, not_installed) must be skipped silently."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_apply_not_available_sentinel_succeeds(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(apply_value_map={"n/a": "not_available"})
        # Should return (True, None) without touching the registry
        with patch("winreg.CreateKeyEx") as mock_create:
            success, error = executor.apply(setting, "n/a")
        assert success is True
        assert error is None
        mock_create.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_apply_not_installed_sentinel_succeeds(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting(apply_value_map={"n/a": "not_installed"})
        with patch("winreg.CreateKeyEx") as mock_create:
            success, error = executor.apply(setting, "n/a")
        assert success is True
        assert error is None
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# apply — type coercion
# ---------------------------------------------------------------------------


class TestRegistryExecutorApplyTypeCoercion:
    """apply() must coerce non-int to int for REG_DWORD."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_apply_coerces_string_to_dword(self):

        executor = RegistryExecutor()
        setting = _make_reg_setting()

        mock_key = MagicMock()
        with (
            patch("winreg.CreateKeyEx", return_value=mock_key.__enter__.return_value),
            patch("winreg.SetValueEx") as mock_set,
        ):
            success, error = executor.apply(setting, "8")  # string "8", not int 8

        assert success is True
        assert error is None
        # Value written must be int 8, not string "8"
        # SetValueEx signature: (key, name, reserved, type, value)
        # positional args[4] is the value; args[3] is the reg_type constant
        args = mock_set.call_args[0]
        assert args[4] == 8

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_apply_invalid_dword_string_returns_false(self):
        executor = RegistryExecutor()
        setting = _make_reg_setting()
        with patch("sys.platform", "win32"), patch("winreg.CreateKeyEx"):
            success, error = executor.apply(setting, "not_an_int")
        assert success is False
        assert error is not None


# ---------------------------------------------------------------------------
# _delete_value
# ---------------------------------------------------------------------------


class TestRegistryExecutorDeleteValue:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_delete_value_not_found_is_ok(self):
        executor = RegistryExecutor()
        with patch("winreg.OpenKey", side_effect=FileNotFoundError):
            success, error = executor._delete_value("HKLM", _HAGS_PATH, _HAGS_NAME)
        assert success is True
        assert error is None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_delete_value_permission_error(self):
        executor = RegistryExecutor()
        with patch("winreg.OpenKey", side_effect=PermissionError):
            success, error = executor._delete_value("HKLM", _HAGS_PATH, _HAGS_NAME)
        assert success is False
        assert "permission" in error.lower() or "administrator" in error.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_delete_value_success(self):
        executor = RegistryExecutor()
        mock_key = MagicMock()
        with (
            patch("winreg.OpenKey", return_value=mock_key.__enter__.return_value),
            patch("winreg.DeleteValue"),
        ):
            success, error = executor._delete_value("HKLM", _HAGS_PATH, _HAGS_NAME)
        assert success is True
        assert error is None
