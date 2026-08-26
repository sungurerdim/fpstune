"""Tests for NetshExecutor output parsing helpers."""

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
from fpstune.settings.executors.netsh import KNOWN_TCP_VALUES, NetshExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_netsh_setting(**overrides) -> SettingExecutor:
    defaults = {
        "id": "network:rss",
        "category": SettingCategory.NETWORK,
        "display_name": "Receive-Side Scaling",
        "description": "Enables RSS for multi-core network processing.",
        "detect_type": DetectType.NETSH,
        "apply_type": DetectType.NETSH,
        "detect_command": "int tcp show global",
        "apply_command": "int tcp set global rss=%value%",
        "detect_args": {"parse_key": "receive-side scaling state"},
        "apply_args": {},
        "value_map": {"enabled": "Enabled", "disabled": "Disabled"},
        "apply_value_map": {"Enabled": "enabled", "Disabled": "disabled"},
        "value_type": SettingValueType.CHOICE,
        "choices": ("Enabled", "Disabled"),
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)


# ---------------------------------------------------------------------------
# _parse_output
# ---------------------------------------------------------------------------


class TestNetshParseOutput:
    """Tests for NetshExecutor._parse_output()."""

    @pytest.fixture
    def executor(self):
        return NetshExecutor()

    # English locale output (exact key match, Strategy 1)
    ENGLISH_RSS_OUTPUT = (
        "TCP Global Parameters\n"
        "----------------------------------------------\n"
        "Receive-Side Scaling State          : enabled\n"
        "Receive Window Auto-Tuning Level    : normal\n"
        "Add-On Congestion Control Provider  : none\n"
        "ECN Capability                      : disabled\n"
    )

    def test_exact_key_match_english_locale(self, executor):
        result = executor._parse_output(
            self.ENGLISH_RSS_OUTPUT,
            {"parse_key": "receive-side scaling state"},
        )
        assert result == "enabled"

    def test_exact_key_match_autotune(self, executor):
        result = executor._parse_output(
            self.ENGLISH_RSS_OUTPUT,
            {"parse_key": "receive window auto-tuning level"},
        )
        assert result == "normal"

    def test_strategy2_known_value_fallback(self, executor):
        """When key not found literally, value match on known TCP values."""
        localized_output = (
            "TCP Globale Parameter\n"
            "-------------------------------\n"
            "Empfangsseitige Skalierung   : enabled\n"
        )
        result = executor._parse_output(
            localized_output,
            {"parse_key": "receive-side scaling state"},
        )
        assert result == "enabled"

    def test_strategy3_whole_output_scan(self, executor):
        """Strategy 3: scan whole output for known value as last resort."""
        output = "some text enabled more text"
        result = executor._parse_output(
            output,
            {"parse_key": "receive-side scaling state"},
        )
        assert result == "enabled"

    def test_returns_none_when_no_key_and_no_known_value(self, executor):
        result = executor._parse_output(
            "no matching content here\nsome other line",
            {"parse_key": "receive-side scaling state"},
        )
        assert result is None

    def test_empty_output_returns_none_for_known_key(self, executor):
        result = executor._parse_output("", {"parse_key": "receive-side scaling state"})
        assert result is None

    def test_no_parse_key_returns_full_output(self, executor):
        """When parse_key is absent, return full trimmed output."""
        result = executor._parse_output("  enabled  ", {})
        assert result == "enabled"

    def test_no_parse_key_empty_returns_none(self, executor):
        result = executor._parse_output("", {})
        assert result is None

    def test_value_case_insensitive_detection(self, executor):
        output = "Receive-Side Scaling State : ENABLED\n"
        result = executor._parse_output(
            output,
            {"parse_key": "receive-side scaling state"},
        )
        assert result == "enabled"

    def test_disabled_value_detected(self, executor):
        output = "Receive-Side Scaling State : disabled\n"
        result = executor._parse_output(
            output,
            {"parse_key": "receive-side scaling state"},
        )
        assert result == "disabled"

    def test_autotune_restricted_value(self, executor):
        output = "Receive Window Auto-Tuning Level : highlyrestricted\n"
        result = executor._parse_output(
            output,
            {"parse_key": "receive window auto-tuning level"},
        )
        assert result == "highlyrestricted"

    def test_teredo_type_detection(self, executor):
        output = "Type : disabled\n"
        result = executor._parse_output(output, {"parse_key": "type"})
        assert result == "disabled"


# ---------------------------------------------------------------------------
# _get_known_values_for_key
# ---------------------------------------------------------------------------


class TestGetKnownValuesForKey:
    """Tests for NetshExecutor._get_known_values_for_key()."""

    @pytest.fixture
    def executor(self):
        return NetshExecutor()

    def test_empty_key_returns_empty(self, executor):
        assert executor._get_known_values_for_key("") == []

    def test_auto_tuning_key(self, executor):
        vals = executor._get_known_values_for_key("receive window auto-tuning level")
        assert set(vals) == set(KNOWN_TCP_VALUES["autotuninglevel"])

    def test_rss_key(self, executor):
        vals = executor._get_known_values_for_key("receive-side scaling state")
        assert set(vals) == set(KNOWN_TCP_VALUES["rss"])

    def test_rsc_key(self, executor):
        vals = executor._get_known_values_for_key("receive segment coalescing state")
        assert set(vals) == set(KNOWN_TCP_VALUES["rsc"])

    def test_teredo_key(self, executor):
        vals = executor._get_known_values_for_key("teredo state")
        assert "disabled" in vals
        assert "default" in vals

    def test_randomize_key(self, executor):
        vals = executor._get_known_values_for_key("randomize identifiers")
        assert set(vals) == set(KNOWN_TCP_VALUES["randomizeidentifiers"])

    def test_unknown_key_returns_empty(self, executor):
        vals = executor._get_known_values_for_key("some_unknown_tcp_setting")
        assert vals == []


# ---------------------------------------------------------------------------
# KNOWN_TCP_VALUES sanity
# ---------------------------------------------------------------------------


class TestKnownTcpValues:
    """Sanity tests for the KNOWN_TCP_VALUES constant."""

    def test_autotuninglevel_has_normal(self):
        assert "normal" in KNOWN_TCP_VALUES["autotuninglevel"]

    def test_autotuninglevel_has_disabled(self):
        assert "disabled" in KNOWN_TCP_VALUES["autotuninglevel"]

    def test_rss_has_enabled_and_disabled(self):
        assert "enabled" in KNOWN_TCP_VALUES["rss"]
        assert "disabled" in KNOWN_TCP_VALUES["rss"]

    def test_teredo_has_expected_values(self):
        expected = {"default", "disabled", "client", "enterpriseclient", "server"}
        assert expected.issubset(set(KNOWN_TCP_VALUES["teredo"]))


# ---------------------------------------------------------------------------
# _run — platform guard
# ---------------------------------------------------------------------------


class TestNetshRun:
    """Tests for NetshExecutor._run() platform guard."""

    def test_run_non_windows_returns_false(self):
        executor = NetshExecutor()
        with patch("sys.platform", "linux"):
            success, output = executor._run("int tcp show global")
        assert success is False
        assert "not available" in output.lower() or "platform" in output.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_calls_netsh(self):
        executor = NetshExecutor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            success, output = executor._run("int tcp show global")
        assert success is True
        mock_run.assert_called_once()
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "netsh"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_timeout_returns_false(self):
        import subprocess

        executor = NetshExecutor()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["netsh"], 10)):
            success, output = executor._run("int tcp show global")
        assert success is False
        assert "timed out" in output.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_run_exception_returns_false(self):
        executor = NetshExecutor()
        with patch("subprocess.run", side_effect=OSError("No such file")):
            success, output = executor._run("int tcp show global")
        assert success is False


# ---------------------------------------------------------------------------
# detect / apply — platform guard
# ---------------------------------------------------------------------------


class TestNetshDetectApplyPlatform:
    """Platform-guard tests for NetshExecutor.detect() / apply()."""

    def test_detect_non_windows_returns_error(self):
        executor = NetshExecutor()
        setting = _make_netsh_setting()
        with patch("sys.platform", "linux"):
            value, error = executor.detect(setting)
        assert value is None
        assert error is not None
        assert "not available" in error.lower() or "platform" in error.lower()

    def test_apply_non_windows_returns_false(self):
        executor = NetshExecutor()
        setting = _make_netsh_setting()
        with patch("sys.platform", "linux"):
            success, error = executor.apply(setting, "Enabled")
        assert success is False
        assert error is not None


# ---------------------------------------------------------------------------
# apply — argument injection (issue #20)
# ---------------------------------------------------------------------------


class TestNetshApplyValueIsOneToken:
    """`_run` builds argv with `args.split()`, so a value carrying whitespace
    used to append netsh arguments to an elevated command line — the same defect
    class the bcdedit token check closes."""

    @pytest.fixture
    def executor(self):
        return NetshExecutor()

    @pytest.mark.parametrize(
        "hostile",
        [
            "enabled store=persistent",
            "enabled\ninterface tcp set global rss=disabled",
            "enabled;shutdown",
            "enabled|more",
            "$(whoami)",
            "en`abled",
            "en'abled",
            'en"abled',
            "",
            "   ",
            "x" * 500 + " extra",
            " interface tcp set global rss=disabled",
            "有効",
        ],
    )
    def test_wide_value_is_refused_before_any_subprocess(self, executor, hostile):
        setting = _make_netsh_setting(apply_value_map={})
        with patch("sys.platform", "win32"), patch("subprocess.run") as run:
            success, error = executor.apply(setting, hostile)

        assert success is False
        assert error is not None
        run.assert_not_called()

    def test_every_shipped_netsh_value_is_accepted(self, executor):
        """The rule must refuse nothing the product itself applies."""
        shipped = [
            "normal",
            "disabled",
            "enabled",
            "highlyrestricted",
            "restricted",
            "experimental",
            "default",
            "1500",
        ]
        for value in shipped:
            setting = _make_netsh_setting(apply_value_map={})
            with (
                patch("sys.platform", "win32"),
                patch("subprocess.run") as run,
            ):
                run.return_value = MagicMock(returncode=0, stdout="Ok.", stderr="")
                success, error = executor.apply(setting, value)

            assert success is True, f"{value!r} was refused: {error}"
            assert run.call_args.args[0] == [
                "netsh",
                "int",
                "tcp",
                "set",
                "global",
                f"rss={value}",
            ]

    def test_unquoted_substitution_failure_is_a_rejection_not_a_crash(self, executor):
        """substitute_placeholders raises ValueError for a value it cannot place;
        the executor must answer in its own (False, reason) shape so the route
        reports a rejection instead of a 500."""
        setting = _make_netsh_setting(
            apply_command="int ipv4 set subinterface %ifindex% mtu=%value%",
            apply_args={"ifindex": "5 extra-token"},
            apply_value_map={},
        )
        with patch("sys.platform", "win32"), patch("subprocess.run") as run:
            success, error = executor.apply(setting, "1500")

        assert success is False
        assert error is not None and "rejected" in error
        run.assert_not_called()

    def test_detect_substitution_failure_is_a_rejection_not_a_crash(self, executor):
        setting = _make_netsh_setting(
            detect_command="int ipv4 show subinterface %ifindex%",
            detect_args={"ifindex": "5; whoami"},
        )
        with patch("sys.platform", "win32"), patch("subprocess.run") as run:
            value, error = executor.detect(setting)

        assert value is None
        assert error is not None and "rejected" in error
        run.assert_not_called()
