"""An apply_command can be a Python function; the executor never spawns a shell for it.

``memory:purge_standby`` used to be a PowerShell script that compiled a C# class
to call ntdll — the Add-Type pattern Windows Defender flags — and passed the
command value as a pointer, so it never worked. It is now the first entry in
``PYTHON_ACTIONS``. These tests prove the dispatch (no PowerShell process for a
Python action), the message (megabytes measured before and after, never a
claim), and the refusal shape when the kernel says no.
"""

from __future__ import annotations

import subprocess

import pytest

from fpstune.settings.executors import python_actions
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.executors.python_actions import PYTHON_ACTIONS
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.winapi.memory import MemoryLists, PurgeOutcome


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


def _lists(standby_pages: int) -> MemoryLists:
    return MemoryLists(
        zero_pages=0,
        free_pages=0,
        modified_pages=0,
        standby_pages_by_priority=(standby_pages, 0, 0, 0, 0, 0, 0, 0),
        page_size=4096,
    )


class TestTheTableAndTheScriptsDoNotOverlap:
    def test_a_python_action_is_not_also_a_powershell_script(self) -> None:
        """Two implementations of one key would let a stale script win silently."""
        assert not set(PYTHON_ACTIONS) & set(ACTION_COMMANDS)

    def test_the_purge_is_a_python_action(self, registry: SettingsRegistry) -> None:
        setting = registry.get("memory:purge_standby")
        assert setting is not None
        assert setting.apply_command.strip() in PYTHON_ACTIONS


class TestDispatch:
    def test_apply_runs_the_function_and_starts_no_process(
        self, registry: SettingsRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        setting = registry.get("memory:purge_standby")
        assert setting is not None

        def no_process(*_a: object, **_k: object) -> None:
            raise AssertionError("a Python action must not start PowerShell")

        monkeypatch.setattr(subprocess, "run", no_process)
        monkeypatch.setattr(
            python_actions,
            "purge_standby_list",
            lambda: PurgeOutcome(status=0, before=_lists(512_000), after=_lists(12_000)),
        )

        ok, message = PowerShellExecutor().apply(setting, setting.recommended_value)

        assert ok is True
        assert message == (
            "Standby list purged: 1954 MB released (standby 2000 MB before, 46 MB after)"
        )

    def test_a_kernel_refusal_is_reported_not_swallowed(
        self, registry: SettingsRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The old script printed success whatever NtSetSystemInformation returned."""
        setting = registry.get("memory:purge_standby")
        assert setting is not None
        monkeypatch.setattr(
            python_actions,
            "purge_standby_list",
            lambda: PurgeOutcome(status=0xC0000061, before=None, after=None),
        )

        ok, message = PowerShellExecutor().apply(setting, setting.recommended_value)

        assert ok is False
        assert message is not None
        assert "0xc0000061" in message and "SeProfileSingleProcessPrivilege" in message

    def test_unreadable_counts_still_report_the_purge_without_a_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No measurement, no megabyte figure — but the purge did run (C11)."""
        monkeypatch.setattr(
            python_actions,
            "purge_standby_list",
            lambda: PurgeOutcome(status=0, before=None, after=None),
        )
        ok, message = python_actions.purge_standby({})
        assert ok is True
        assert message is not None and "MB" not in message
