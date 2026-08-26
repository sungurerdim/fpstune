"""Mutex-group wiring must fail loudly, never skip (CC-01 regression).

The import-time loop used to guard with ``if _k in ACTION_COMMANDS``: rename an
action command without renaming its ``_MUTEX_GROUPS`` entry and the script kept
running — with no lock, so parallel bulk applies silently dropped each other's
writes to the shared file. That is a live violation of the whole-shared-file
lock invariant, and it produced no error anywhere.
"""

from __future__ import annotations

import pytest

from fpstune.settings.executors.powershell_actions import (
    _MUTEX_GROUPS,
    ACTION_COMMANDS,
    _wire_mutex_groups,
)


class TestWireMutexGroups:
    def test_renamed_key_raises_instead_of_silently_skipping(self):
        """The CC-01 defect: a group entry pointing at a renamed/removed action
        command must break the import, not strip the file of its lock."""
        commands = {"cs2_fps_max_toggle_v2": "Write-Output 'ok'"}
        groups = {"Global\\fpstune-cs2-autoexec-cfg": ["cs2_fps_max_toggle"]}
        with pytest.raises(RuntimeError, match="cs2_fps_max_toggle"):
            _wire_mutex_groups(commands, groups)

    def test_unknown_key_leaves_commands_unwrapped(self):
        """On failure nothing is mutated — no half-wired state."""
        commands = {"known": "Write-Output 'ok'"}
        groups = {"Global\\fpstune-test": ["known", "missing"]}
        with pytest.raises(RuntimeError, match="missing"):
            _wire_mutex_groups(commands, groups)
        assert commands["known"] == "Write-Output 'ok'"

    def test_matching_keys_are_wrapped_with_their_mutex(self):
        commands = {"hots_variable_set": "Write-Output 'ok'"}
        groups = {"Global\\fpstune-hots-variables-txt": ["hots_variable_set"]}
        _wire_mutex_groups(commands, groups)
        assert "System.Threading.Mutex" in commands["hots_variable_set"]
        assert "Global\\fpstune-hots-variables-txt" in commands["hots_variable_set"]

    def test_every_shipped_group_member_actually_carries_its_lock(self):
        """The invariant the loud failure protects: each script a group names is
        serialized by its named mutex in the registry callers actually read."""
        for mutex_name, keys in _MUTEX_GROUPS.items():
            for key in keys:
                script = ACTION_COMMANDS[key]
                assert "System.Threading.Mutex" in script, f"{key} lost its lock"
                assert mutex_name in script, f"{key} is not locked by {mutex_name}"
