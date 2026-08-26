"""A value the escaping layer refuses is a rejection, not a server error.

``substitute_placeholders`` raises ``ValueError`` when a value would land
outside any quotes, where it would become extra tokens of an elevated command
line. Before issue #20 neither PowerShell executor caught it, so the right
outcome — the write does not happen — arrived as a 500 out of the substitution
layer instead of the executor's own ``(False, reason)`` failure.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.executors.powershell import PowerShellExecutor

# A value that cannot be placed in a bare context: each of these would append
# tokens to, or close, the generated command.
HOSTILE_VALUES = [
    "5; Remove-Item C:\\Windows",
    "5 -Force",
    "$(whoami)",
    "5`nRemove-Item",
    "5\nRemove-Item C:\\Windows",
    "it's",
    'say "hi"',
    "",
    "有効",
]


def _setting(**overrides) -> SettingExecutor:
    defaults = {
        "id": "network:99:test_property",
        "category": SettingCategory.NETWORK,
        "display_name": "Test Property",
        "description": "A setting whose command substitutes a value outside quotes.",
        "value_type": SettingValueType.CHOICE,
        "choices": ("On", "Off"),
        "detect_type": DetectType.POWERSHELL,
        "apply_type": DetectType.POWERSHELL,
        "detect_command": "Get-NetIPInterface -InterfaceIndex %ifindex%",
        "detect_args": {"ifindex": "5"},
        "apply_command": "Set-NetIPInterface -InterfaceIndex 5 -NlMtuBytes %value%",
        "apply_args": {},
        "value_map": {},
        "apply_value_map": {},
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)


class TestApplyRejectsRatherThanRaises:
    @pytest.mark.parametrize("hostile", HOSTILE_VALUES)
    def test_unplaceable_value_returns_a_failure_and_runs_nothing(self, hostile: str) -> None:
        with (
            patch("sys.platform", "win32"),
            patch(
                "fpstune.settings.executors.game_processes.refuse_if_game_is_running",
                return_value=None,
            ),
            patch("fpstune.settings.executors.powershell.run_powershell") as run,
        ):
            success, error = PowerShellExecutor().apply(_setting(), hostile)

        assert success is False
        assert error is not None and "rejected" in error
        run.assert_not_called()

    def test_a_placeable_value_still_applies(self) -> None:
        """The rejection must not swallow the values the product actually writes."""
        with (
            patch("sys.platform", "win32"),
            patch(
                "fpstune.settings.executors.game_processes.refuse_if_game_is_running",
                return_value=None,
            ),
            patch(
                "fpstune.settings.executors.powershell.run_powershell",
                return_value=(True, ""),
            ) as run,
        ):
            success, error = PowerShellExecutor().apply(_setting(), "1500")

        assert (success, error) == (True, None)
        assert run.call_args.args[0].endswith("-NlMtuBytes 1500")


class TestDetectRejectsRatherThanRaises:
    @pytest.mark.parametrize("hostile", HOSTILE_VALUES)
    def test_unplaceable_detect_argument_returns_an_error(self, hostile: str) -> None:
        setting = _setting(detect_args={"ifindex": hostile})

        with (
            patch("sys.platform", "win32"),
            patch("fpstune.settings.executors.powershell.run_powershell") as run,
        ):
            value, error = PowerShellExecutor().detect(setting)

        assert value is None
        assert error is not None and "rejected" in error
        run.assert_not_called()
