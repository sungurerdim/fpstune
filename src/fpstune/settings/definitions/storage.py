"""Storage setting definitions.

Contains settings for TRIM, 8.3 filename, last access time.
Uses registry and PowerShell executors.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# Registry paths
FILESYSTEM_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"

# === TRIM Enabled ===
TRIM_ENABLED = SettingExecutor(
    id="storage:trim_enabled",
    category=SettingCategory.STORAGE,
    display_name="TRIM",
    description="Informs the SSD which blocks are no longer in use. Maintains write speed and extends drive lifespan.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Enabled: TRIM maintains SSD performance over time",
    recommended_impact="Enabled: Keep enabled → ensures SSD performance stays optimal",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for SSD health
    category_order=1,  # Critical for SSD longevity
    effect="Maintains SSD performance by informing drive of deleted blocks",
    impact_scores={
        "fps": "0%",
        "latency_ms": 0,
        "ssd_longevity": "high",
        "storage_performance": "maintained",
    },
    # Detection - DisableDeleteNotification (0 = TRIM enabled, 1 = disabled)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": FILESYSTEM_KEY,
        "name": "DisableDeleteNotification",
        "hive": "HKLM",
    },
    value_map={0: "enabled", "0": "enabled", 1: "disabled", "1": "disabled", None: "enabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": FILESYSTEM_KEY,
        "name": "DisableDeleteNotification",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 0, "disabled": 1},
)

# === 8.3 Filename Generation ===
DISABLE_8DOT3 = SettingExecutor(
    id="storage:disable_8dot3",
    category=SettingCategory.STORAGE,
    display_name="8.3 Filename Generation",
    description="Creates legacy 8.3 DOS filenames for every file. Disabling removes unnecessary I/O overhead.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Some legacy 16-bit and older 32-bit installers, and a few applications that "
    "hardcode short paths, resolve files only through their 8.3 names and will fail to launch or "
    "install without them. The setting affects newly created files only — existing 8.3 names are "
    "kept — so re-enabling it does not restore names for files created while it was off.",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fsutil-8dot3name"
    ],
    current_impact="Enabled: Creates short names for every file → extra I/O overhead",
    recommended_impact="Disabled: No short names → reduced disk I/O, faster file operations",
    scope=SettingScope.COMPLETE,  # experimental risk is offered, never assumed (C2/#30)
    category_order=2,  # I/O overhead reduction
    effect="Eliminates legacy DOS-style filename generation overhead",
    impact_scores={"fps": "0%", "latency_ms": 0, "storage_performance": "+0-1%"},
    # Detection - NtfsDisable8dot3NameCreation (1 = disabled, 0 = enabled)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": FILESYSTEM_KEY,
        "name": "NtfsDisable8dot3NameCreation",
        "hive": "HKLM",
    },
    value_map={
        0: "enabled",
        "0": "enabled",
        1: "disabled",
        "1": "disabled",
        2: "disabled",
        "2": "disabled",
        3: "enabled",
        "3": "enabled",
        None: "enabled",
    },
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": FILESYSTEM_KEY,
        "name": "NtfsDisable8dot3NameCreation",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 0, "disabled": 1},
)

# === Last Access Time Updates ===
DISABLE_LAST_ACCESS = SettingExecutor(
    id="storage:disable_last_access",
    category=SettingCategory.STORAGE,
    display_name="Last Access Time Updates",
    description="Updates the last-access timestamp on every file read. Disabling reduces unnecessary SSD writes.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fsutil-behavior"
    ],
    current_impact="Enabled: Updates metadata on every file read → extra disk writes",
    recommended_impact="Disabled: No timestamp updates → reduced SSD writes, better performance",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for SSD writes
    category_order=3,  # Reduces disk writes
    effect="Reduces disk writes by not updating last access timestamps",
    impact_scores={
        "fps": "0%",
        "latency_ms": 0,
        "ssd_writes": "reduced",
        "storage_performance": "+0-1%",
    },
    # Detection - NtfsDisableLastAccessUpdate (1/80000001 = disabled, 0 = enabled)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": FILESYSTEM_KEY,
        "name": "NtfsDisableLastAccessUpdate",
        "hive": "HKLM",
    },
    # Windows 10 1803+ uses new value format with high bit set:
    # 0x80000000 = User Managed, enabled
    # 0x80000001 = User Managed, disabled
    # 0x80000002 = System Managed, enabled
    # 0x80000003 = System Managed, disabled
    # Legacy values: 0 = enabled, 1 = disabled
    value_map={
        0: "enabled",
        1: "disabled",
        0x80000000: "enabled",
        0x80000001: "disabled",
        0x80000002: "enabled",
        0x80000003: "disabled",
        # String versions for values that come as strings
        "0": "enabled",
        "1": "disabled",
        "2147483648": "enabled",  # 0x80000000
        "2147483649": "disabled",  # 0x80000001
        "2147483650": "enabled",  # 0x80000002
        "2147483651": "disabled",  # 0x80000003
        None: "enabled",
    },
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": FILESYSTEM_KEY,
        "name": "NtfsDisableLastAccessUpdate",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    # Use modern format (0x80000001) for disabled - sets User Managed mode
    apply_value_map={"enabled": 0x80000000, "disabled": 0x80000001},
)

# All storage settings
STORAGE_SETTINGS: list[SettingExecutor] = [
    TRIM_ENABLED,
    DISABLE_8DOT3,
    DISABLE_LAST_ACCESS,
]
