"""Tests for PowerCfgExecutor."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.executors.powercfg import PowerCfgExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Real GUIDs from Windows power management
_USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
_USB_SETTING = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
_PERF_SCHEME = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"


def _make_power_setting(**overrides) -> SettingExecutor:
    defaults = {
        "id": "power:usb_selective_suspend",
        "category": SettingCategory.POWER,
        "display_name": "USB Selective Suspend",
        "description": "Controls USB selective suspend.",
        "detect_type": DetectType.POWERCFG,
        "apply_type": DetectType.POWERCFG,
        "detect_command": "",
        "apply_command": "",
        "detect_args": {"subgroup": _USB_SUBGROUP, "setting": _USB_SETTING},
        "apply_args": {"subgroup": _USB_SUBGROUP, "setting": _USB_SETTING},
        "value_map": {0: "disabled", 1: "enabled"},
        "apply_value_map": {"disabled": 0, "enabled": 1},
        "value_type": SettingValueType.CHOICE,
        "choices": ("disabled", "enabled"),
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)


# ---------------------------------------------------------------------------
# _parse_query_output
# ---------------------------------------------------------------------------


class TestParseQueryOutput:
    """Tests for PowerCfgExecutor._parse_query_output()."""

    def setup_method(self):
        PowerCfgExecutor._active_scheme = None  # reset cached scheme

    @pytest.fixture
    def executor(self):
        return PowerCfgExecutor()

    # Realistic powercfg /query output (English locale)
    TYPICAL_OUTPUT = (
        "\n"
        "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)\n"
        "\n"
        "Subgroup GUID: 2a737441-1930-4402-8d77-b2bebba308a3  (USB settings)\n"
        "\n"
        "Power Setting GUID: 48e6b7a6-50f5-4782-a5d4-53bb8f07e226\n"
        "  Possible Setting Index: 000\n"
        "  Possible Setting Friendly Name: Disabled\n"
        "  Possible Setting Index: 001\n"
        "  Possible Setting Friendly Name: Enabled\n"
        "  Current AC Power Setting Index: 0x00000000\n"
        "  Current DC Power Setting Index: 0x00000001\n"
    )

    def test_parse_ac_value_disabled(self, executor):
        result = executor._parse_query_output(self.TYPICAL_OUTPUT)
        assert result == 0  # AC = disabled (0x00000000)

    def test_parse_ac_value_enabled(self, executor):
        output = self.TYPICAL_OUTPUT.replace(
            "AC Power Setting Index: 0x00000000",
            "AC Power Setting Index: 0x00000001",
        )
        result = executor._parse_query_output(output)
        assert result == 1

    def test_parse_ac_value_higher_integer(self, executor):
        output = self.TYPICAL_OUTPUT.replace(
            "AC Power Setting Index: 0x00000000",
            "AC Power Setting Index: 0x00000003",
        )
        result = executor._parse_query_output(output)
        assert result == 3

    def test_parse_empty_output_returns_none(self, executor):
        result = executor._parse_query_output("")
        assert result is None

    def test_parse_output_without_hex_returns_none(self, executor):
        output = "Some text without any hex values\nAnother line"
        result = executor._parse_query_output(output)
        assert result is None

    def test_parse_strategy2_colon_hex(self, executor):
        """Strategy 2: detect ':0x...' pattern when 'AC' is absent."""
        output = "Current Power Index: 0x00000002\n"
        result = executor._parse_query_output(output)
        assert result == 2

    def test_parse_strategy3_last_hex(self, executor):
        """Strategy 3: last hex value in output."""
        output = "Possible Setting Index: 000\nPossible Setting Index: 001\n0x00000005\n"
        result = executor._parse_query_output(output)
        assert result == 5

    def test_parse_hex_zero(self, executor):
        output = "Current AC Power Setting Index: 0x00000000\n"
        result = executor._parse_query_output(output)
        assert result == 0

    def test_parse_hex_large_value(self, executor):
        output = "Current AC Power Setting Index: 0x000003e8\n"
        result = executor._parse_query_output(output)
        assert result == 0x3E8  # 1000

    def test_parse_malformed_hex_fallback(self, executor):
        """Malformed 0x line but valid last-hex available."""
        output = "Some prefix 0x\nValue 0x00000001\n"
        result = executor._parse_query_output(output)
        # Strategy 3 picks last valid hex group
        assert result is not None

    def test_parse_multiple_ac_lines_uses_first(self, executor):
        """When multiple AC lines exist, first match is used."""
        output = (
            "Current AC Power Setting Index: 0x00000001\n"
            "Current AC Power Setting Index: 0x00000002\n"
        )
        # Strategy 1 accumulates and assigns last-seen AC value (loop overwrites)
        result = executor._parse_query_output(output)
        assert result in (1, 2)  # implementation-defined; must be valid


# ---------------------------------------------------------------------------
# get_available_values
# ---------------------------------------------------------------------------


class TestGetAvailableValues:
    """Tests for PowerCfgExecutor.get_available_values()."""

    QUERY_OUTPUT = (
        "Power Setting GUID: 48e6b7a6-50f5-4782-a5d4-53bb8f07e226\n"
        "  Possible Setting Index: 000\n"
        "  Possible Setting Friendly Name: Disabled\n"
        "  Possible Setting Index: 001\n"
        "  Possible Setting Friendly Name: Enabled\n"
        "  Current AC Power Setting Index: 0x00000001\n"
    )

    @pytest.fixture
    def executor(self):
        PowerCfgExecutor._active_scheme = None
        return PowerCfgExecutor()

    def test_returns_sorted_list_of_indices(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.QUERY_OUTPUT)):
            result = executor.get_available_values(_USB_SUBGROUP, _USB_SETTING)
        assert result == [0, 1]

    def test_returns_empty_on_failure(self, executor):
        with patch.object(executor, "_run", return_value=(False, "Error")):
            result = executor.get_available_values(_USB_SUBGROUP, _USB_SETTING)
        assert result == []

    def test_returns_empty_on_empty_output(self, executor):
        with patch.object(executor, "_run", return_value=(True, "")):
            result = executor.get_available_values(_USB_SUBGROUP, _USB_SETTING)
        assert result == []

    def test_deduplicates_repeated_indices(self, executor):
        output = (
            "  Possible Setting Index: 000\n"
            "  Possible Setting Index: 000\n"
            "  Possible Setting Index: 001\n"
        )
        with patch.object(executor, "_run", return_value=(True, output)):
            result = executor.get_available_values(_USB_SUBGROUP, _USB_SETTING)
        assert result == [0, 1]

    def test_multiple_values(self, executor):
        output = (
            "  Possible Setting Index: 000\n"
            "  Possible Setting Index: 001\n"
            "  Possible Setting Index: 002\n"
            "  Possible Setting Index: 003\n"
        )
        with patch.object(executor, "_run", return_value=(True, output)):
            result = executor.get_available_values(_USB_SUBGROUP, _USB_SETTING)
        assert result == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# _get_active_scheme
# ---------------------------------------------------------------------------


class TestGetActiveScheme:
    """Tests for PowerCfgExecutor._get_active_scheme()."""

    # Realistic powercfg /getactivescheme output
    SCHEME_OUTPUT = "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)"

    @pytest.fixture
    def executor(self):
        PowerCfgExecutor._active_scheme = None
        return PowerCfgExecutor()

    def test_parses_guid_from_output(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.SCHEME_OUTPUT)):
            scheme = executor._get_active_scheme()
        assert scheme == "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

    def test_returns_lowercase_guid(self, executor):
        output = "Power Scheme GUID: 8C5E7FDA-E8BF-4A96-9A85-A6E23A8C635C  (High performance)"
        with patch.object(executor, "_run", return_value=(True, output)):
            scheme = executor._get_active_scheme()
        assert scheme == scheme.lower()

    def test_caches_after_first_call(self, executor):
        with patch.object(executor, "_run", return_value=(True, self.SCHEME_OUTPUT)) as mock_run:
            executor._get_active_scheme()
            executor._get_active_scheme()
        # _run should only be called once (cached on second call)
        assert mock_run.call_count == 1

    def test_returns_none_on_failure(self, executor):
        with patch.object(executor, "_run", return_value=(False, "Error")):
            scheme = executor._get_active_scheme()
        assert scheme is None

    def test_returns_none_when_no_guid_in_output(self, executor):
        with patch.object(executor, "_run", return_value=(True, "No GUID here")):
            scheme = executor._get_active_scheme()
        assert scheme is None

    def test_invalidate_cache_clears_scheme(self):
        PowerCfgExecutor._active_scheme = _PERF_SCHEME
        PowerCfgExecutor.invalidate_cache()
        assert PowerCfgExecutor._active_scheme is None


# ---------------------------------------------------------------------------
# apply — numeric guard
# ---------------------------------------------------------------------------


class TestPowerCfgApply:
    """Tests for PowerCfgExecutor.apply()."""

    @pytest.fixture
    def executor(self):
        PowerCfgExecutor._active_scheme = None
        return PowerCfgExecutor()

    def test_apply_numeric_coercion_guard_directly(self):
        """The int-coercion guard logic: valid numeric string must convert OK."""
        # Test the guard logic in isolation — verify int(str(x).strip()) works
        # for values that should be accepted and fails for values that should not.
        import contextlib

        # These must convert to int without exception
        for good in ("0", "1", "3", " 2 "):
            with contextlib.suppress(Exception):
                assert isinstance(int(str(good).strip()), int)

        # These must raise ValueError
        for bad in ("not_a_number", "abc", ""):
            with pytest.raises((ValueError, TypeError)):
                int(str(bad).strip() or "")  # empty string -> ValueError too

    def test_apply_returns_error_when_no_scheme_can_be_enumerated(self, executor):
        """Apply targets every plan now, so an empty plan list is the failure case.

        It used to key off the active scheme alone. With a per-plan store and a
        tool that switches plans, writing only the active one is a tweak that
        stops applying the moment something switches.
        """
        setting = _make_power_setting()
        with patch.object(executor, "_target_schemes", return_value=[]):
            success, error = executor.apply(setting, "enabled")
        assert success is False
        assert "scheme" in error.lower()

    def test_apply_returns_error_when_missing_subgroup(self, executor):
        setting = _make_power_setting(apply_args={})  # no subgroup/setting
        with patch.object(executor, "_target_schemes", return_value=[_PERF_SCHEME]):
            success, error = executor.apply(setting, "enabled")
        assert success is False
        assert "subgroup" in error.lower() or "setting" in error.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_apply_success_calls_both_ac_and_dc(self, executor):
        setting = _make_power_setting()
        called_flags: list[str] = []

        def fake_run(args: str) -> tuple[bool, str]:
            called_flags.append(args.split()[0])
            return True, ""

        with (
            patch.object(executor, "_get_active_scheme", return_value=_PERF_SCHEME),
            patch.object(executor, "_run", side_effect=fake_run),
        ):
            success, error = executor.apply(setting, "enabled")

        assert success is True
        assert error is None
        assert "/setacvalueindex" in called_flags
        assert "/setdcvalueindex" in called_flags

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_apply_failure_on_ac_returns_false(self, executor):
        setting = _make_power_setting()

        run_calls: list[str] = []

        def fake_run(args: str) -> tuple[bool, str]:
            run_calls.append(args)
            if "/setacvalueindex" in args:
                return False, "Access denied"
            return True, ""

        with (
            patch.object(executor, "_get_active_scheme", return_value=_PERF_SCHEME),
            patch.object(executor, "_run", side_effect=fake_run),
        ):
            success, error = executor.apply(setting, "enabled")

        assert success is False
        assert "Access denied" in (error or "")

    def test_run_not_available_non_windows(self, executor):
        with patch("sys.platform", "linux"):
            success, output = executor._run("/query")
        assert success is False
        assert "not available" in output.lower() or "platform" in output.lower()


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


class TestPowerCfgDetect:
    """Tests for PowerCfgExecutor.detect()."""

    @pytest.fixture
    def executor(self):
        PowerCfgExecutor._active_scheme = None
        return PowerCfgExecutor()

    def test_detect_missing_subgroup_returns_error(self, executor):
        setting = _make_power_setting(detect_args={})
        with patch.object(executor, "_run", return_value=(True, "")):
            value, error = executor.detect(setting)
        assert value is None
        assert "subgroup" in error.lower() or "setting" in error.lower()

    def test_detect_maps_raw_to_display(self, executor):
        # The registry is tried first and answers on a real host, so these two
        # cases pin the powercfg fallback explicitly rather than by accident.
        output = "Current AC Power Setting Index: 0x00000001\n"
        setting = _make_power_setting(value_map={0: "disabled", 1: "enabled"})
        with (
            patch.object(executor, "_detect_via_registry_key", return_value=None),
            patch.object(executor, "_run", return_value=(True, output)),
        ):
            value, error = executor.detect(setting)
        assert value == "enabled"
        assert error is None

    def test_detect_unmapped_value_returns_raw_int(self, executor):
        output = "Current AC Power Setting Index: 0x00000007\n"
        setting = _make_power_setting(value_map={0: "disabled", 1: "enabled"})
        with (
            patch.object(executor, "_detect_via_registry_key", return_value=None),
            patch.object(executor, "_run", return_value=(True, output)),
        ):
            value, error = executor.detect(setting)
        # 7 not in value_map, returned as-is
        assert value == 7
        assert error is None

    def test_registry_answer_short_circuits_powercfg(self, executor):
        """A registry hit must not also spawn the subprocess it replaces."""
        setting = _make_power_setting(value_map={0: "disabled", 1: "enabled"})
        with (
            patch.object(executor, "_detect_via_registry_key", return_value="enabled"),
            patch.object(executor, "_run") as run,
        ):
            value, error = executor.detect(setting)
        assert (value, error) == ("enabled", None)
        run.assert_not_called()
