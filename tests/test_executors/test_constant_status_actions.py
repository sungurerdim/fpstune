"""A detect that can only answer one thing must not start a process to say it.

Three settings — purge the standby list, run SFC, run DISM health — describe an
operation that is always available rather than a state the machine holds. Their
detect script is the literal ``Write-Output $true``, so each one started a
PowerShell process to learn a constant. Measured on a cold scan: three of
twenty-five processes, for no information at all.

The value still goes through ``value_map``, so it is the same value reached the
same way; only the process is gone.

The question is asked of the *resolved* script and not of the command name,
because one name now covers both kinds. ``maintenance_status`` is the literal for
SFC and the DISM health check and a real reading for ``maintenance:ssd_retrim``,
which asks the machine when Windows last optimized each SSD volume. A table keyed
on the name would have answered ``True`` for the one reading that has something
to say.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from fpstune.settings.executors import CommandExecutor
from fpstune.settings.executors.powershell_actions import (
    ACTION_COMMANDS,
    constant_status_reading,
    detect_script,
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


class TestTheAnswerIsDerivedNotHandKept:
    def test_it_answers_exactly_the_scripts_that_are_a_literal(self) -> None:
        """Derived from the shipped scripts, so the two cannot disagree.

        A hand-kept list would go on claiming a constant for a script that had
        started asking the machine something — answering from a stale literal
        while the real state drifted underneath it.
        """
        literals = {
            key for key, script in ACTION_COMMANDS.items() if script.strip() == "Write-Output $true"
        }
        assert literals, "no constant-status action commands found; has the shape changed?"
        for key, script in ACTION_COMMANDS.items():
            expected = "True" if key in literals else None
            assert constant_status_reading(key, {}) == expected, key
            assert detect_script(key, {}) == script, key

    def test_the_constant_is_what_the_script_would_have_printed(self) -> None:
        """`Write-Output $true` puts "True" on stdout, and the value_maps key on it."""
        assert constant_status_reading("sfc_scan", {}) is None
        assert constant_status_reading("maintenance_status", {"type": "sfc"}) == "True"

    def test_a_type_with_its_own_script_is_not_answered_from_the_literal(self) -> None:
        """The failure this rewrite exists to prevent.

        `maintenance_status` still holds the literal for the types that have
        nothing to read, so resolving on the name alone stayed green while the
        SSD retrim reading was silently replaced by `True`.
        """
        assert ACTION_COMMANDS["maintenance_status"].strip() == "Write-Output $true"
        assert constant_status_reading("maintenance_status", {"type": "ssd_trim"}) is None
        assert (
            detect_script("maintenance_status", {"type": "ssd_trim"})
            != (ACTION_COMMANDS["maintenance_status"])
        )

    def test_an_unknown_command_names_no_script(self) -> None:
        assert detect_script("no_such_action", {}) is None
        assert constant_status_reading("no_such_action", {}) is None


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
        assert constant_status_reading("cleanup_status", {"type": "temp_files"}) is None
        assert constant_status_reading("rebar_detect", {}) is None
