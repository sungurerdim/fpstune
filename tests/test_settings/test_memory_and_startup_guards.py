"""Memory compression and SysMain agree, and the startup advisory stays advisory.

Disabling SysMain switches every MMAgent feature off, memory compression
included, and enabling memory compression starts SysMain again (Winhance #261,
tested with Get-MMAgent either side). fpstune used to recommend SysMain
disabled; with a memory-compression guard beside it, one bulk apply would undo
the other and each verify would report the other's write as drift.
"""

from __future__ import annotations

from fpstune.settings.applicability import ABSENT_READINGS
from fpstune.settings.definitions.system import (
    MEMORY_COMPRESSION,
    MEMORY_SETTINGS,
    SERVICE_SYSMAIN,
    SYSTEM_CONFIG_SETTINGS,
    SYSTEM_STARTUP_APPS,
)


def test_sysmain_and_memory_compression_recommend_the_same_side() -> None:
    assert SERVICE_SYSMAIN.recommended_value == "enabled"
    assert MEMORY_COMPRESSION.recommended_value == "enabled"


def test_both_are_drift_guards_on_windows_own_state() -> None:
    for setting in (SERVICE_SYSMAIN, MEMORY_COMPRESSION):
        assert setting.recommended_value == setting.default_value, setting.id


def test_memory_compression_is_registered_and_writes_through_mmagent() -> None:
    assert MEMORY_COMPRESSION in MEMORY_SETTINGS
    assert "Enable-MMAgent -MemoryCompression" in MEMORY_COMPRESSION.apply_command
    assert "Disable-MMAgent -MemoryCompression" in MEMORY_COMPRESSION.apply_command
    # A failed write must reach the user as a failure, not as "ok".
    assert "'error:' +" in MEMORY_COMPRESSION.apply_command
    assert MEMORY_COMPRESSION.requires_reboot


def test_an_unreadable_compression_state_is_a_sentinel_not_a_choice() -> None:
    assert "not_available" in ABSENT_READINGS
    assert "not_available" not in MEMORY_COMPRESSION.choices
    assert "'not_available'" in MEMORY_COMPRESSION.detect_command


def test_the_startup_advisory_changes_nothing() -> None:
    assert SYSTEM_STARTUP_APPS in SYSTEM_CONFIG_SETTINGS
    assert SYSTEM_STARTUP_APPS.is_readonly
    assert SYSTEM_STARTUP_APPS.apply_command == ""
    # No write verb anywhere in what it runs.
    for verb in ("Set-ItemProperty", "Remove-Item", "New-ItemProperty", "Remove-ItemProperty"):
        assert verb not in SYSTEM_STARTUP_APPS.detect_command, verb


def test_the_startup_advisory_carries_its_numbers_and_no_placeholders() -> None:
    command = SYSTEM_STARTUP_APPS.detect_command
    assert "FPSTUNE_FINDING:" in command
    assert "kind='startup_apps'" in command
    # %name% is the executor's placeholder syntax; a stray % would be substituted.
    assert "%" not in command
    # Security software is filtered by what Security Center reports, not a list.
    assert "root/SecurityCenter2" in command
    assert "SecurityHealth" in command
