"""A detect that can only answer one thing must not start a process to say it.

Three settings — purge the standby list, run SFC, run DISM health — describe an
operation that is always available rather than a state the machine holds. Their
detect script is the literal ``Write-Output $true``, so each one started a
PowerShell process to learn a constant. Measured on a cold scan: three of
twenty-five processes, for no information at all.

The value still goes through ``value_map``, so it is the same value reached the
same way; only the process is gone.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from fpstune.settings.executors import CommandExecutor
from fpstune.settings.executors.powershell_actions import (
    ACTION_COMMANDS,
    CONSTANT_STATUS_ACTIONS,
)
from fpstune.settings.registry import SettingsRegistry

CONSTANT_SETTINGS = (
    "memory:purge_standby",
    "maintenance:sfc_scan",
    "maintenance:dism_health",
)


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


class TestTheListIsDerivedNotHandKept:
    def test_it_names_exactly_the_scripts_that_are_a_literal(self) -> None:
        """Derived from the shipped scripts, so the two cannot disagree.

        A hand-kept list would go on claiming a constant for a script that had
        started asking the machine something — answering from a stale literal
        while the real state drifted underneath it.
        """
        expected = {
            key for key, script in ACTION_COMMANDS.items() if script.strip() == "Write-Output $true"
        }
        assert set(CONSTANT_STATUS_ACTIONS) == expected
        assert expected, "no constant-status action commands found; has the shape changed?"

    def test_the_constant_is_what_the_script_would_have_printed(self) -> None:
        """`Write-Output $true` puts "True" on stdout, and the value_maps key on it."""
        assert set(CONSTANT_STATUS_ACTIONS.values()) == {"True"}


class TestNoProcessIsStarted:
    @pytest.mark.parametrize("setting_id", CONSTANT_SETTINGS)
    def test_detect_spawns_nothing(self, registry: SettingsRegistry, setting_id: str) -> None:
        setting = registry.get(setting_id)
        assert setting is not None

        with patch.object(subprocess, "Popen", side_effect=AssertionError("spawned a process")):
            value, error = CommandExecutor.detect(setting)

        assert error is None
        assert value is True

    @pytest.mark.parametrize("setting_id", CONSTANT_SETTINGS)
    def test_the_answer_is_what_it_always_was(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """Measured against the shipped behaviour: (True, None) before and after."""
        setting = registry.get(setting_id)
        assert setting is not None
        assert CommandExecutor.detect(setting) == (True, None)

    def test_a_setting_with_a_real_script_is_not_short_circuited(self) -> None:
        """The guard has to let a genuine query through, or it is not a guard.

        `cleanup_status` is an action command too, and it asks the machine a real
        question about a real folder.
        """
        assert "cleanup_status" not in CONSTANT_STATUS_ACTIONS
        assert "rebar_detect" not in CONSTANT_STATUS_ACTIONS
