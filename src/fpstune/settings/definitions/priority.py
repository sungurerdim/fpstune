"""Priority setting definitions.

Contains settings for GPU priority, game priority, system responsiveness.
All use registry executor.
"""

from __future__ import annotations

from fpstune.settings.base import (
    UNMAPPED,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# Registry paths
GAMES_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
SYSTEM_PROFILE_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
PRIORITY_CONTROL_KEY = r"SYSTEM\CurrentControlSet\Control\PriorityControl"

# === Game Priority ===
GAME_PRIORITY = SettingExecutor(
    id="priority:game_priority",
    category=SettingCategory.CORE,
    display_name="Game Priority",
    short_name="CPU priority for games",
    description="The priority MMCSS gives threads registered with its Games task. Under the High category "
    "Windows treats every value as 2, so the stock value is kept.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=2,
    recommended_value=2,
    requires_reboot=False,
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service"
    ],
    current_impact="Changed: a value Windows does not ship, left by another tool",
    recommended_impact="2 (Windows default): MMCSS behaves as Windows ships it",
    scope=SettingScope.RECOMMENDED,
    category_order=2,
    effect="Keeps the MMCSS Games task priority at Windows' own value",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    min_value=1,
    max_value=8,
    # Detection
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": GAMES_KEY,
        "name": "Priority",
        "hive": "HKLM",
    },
    value_map={None: 2},  # Default Windows value when key doesn't exist
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": GAMES_KEY,
        "name": "Priority",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={},
)

# === System Responsiveness ===
SYSTEM_RESPONSIVENESS = SettingExecutor(
    id="priority:system_responsiveness",
    category=SettingCategory.CORE,
    display_name="System Responsiveness",
    short_name="Reserved CPU for background",
    description="CPU time MMCSS reserves for low-priority work while it boosts registered multimedia threads. "
    "Windows clamps values below 10 to 20, so the popular 0 changes nothing; the stock 20 is kept.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=20,
    recommended_value=20,
    requires_reboot=False,
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service"
    ],
    current_impact="Changed: a value Windows does not ship, left by another tool",
    recommended_impact="20 (Windows default): the reservation Windows ships",
    scope=SettingScope.RECOMMENDED,
    category_order=3,  # System-wide responsiveness
    effect="Keeps the MMCSS background reservation at Windows' own value",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    min_value=0,  # 0% = full foreground priority
    max_value=100,  # 100% = full system priority (no foreground boost)
    # Detection
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": SYSTEM_PROFILE_KEY,
        "name": "SystemResponsiveness",
        "hive": "HKLM",
    },
    value_map={None: 20},  # Default Windows value when key doesn't exist
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": SYSTEM_PROFILE_KEY,
        "name": "SystemResponsiveness",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={},
)

# === Scheduling Category ===
SCHEDULING_CATEGORY = SettingExecutor(
    id="priority:scheduling_category",
    category=SettingCategory.CORE,
    display_name="Scheduling Category",
    short_name="Game scheduling class",
    description="Sets the MMCSS scheduling category that games are assigned by the multimedia class scheduler. Higher categories receive preferential CPU access and lower scheduling latency.",
    value_type=SettingValueType.CHOICE,
    choices=("Low", "Medium", "High"),
    default_value="Medium",
    # High makes MMCSS treat every Priority as 2, cancelling the tweak this
    # used to pair with; Windows ships Medium. A guard.
    recommended_value="Medium",
    requires_reboot=False,
    current_impact="Changed: a category Windows does not ship, left by another tool",
    recommended_impact="Medium (Windows default): the Games task as Windows ships it",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for MMCSS scheduling
    category_order=4,  # MMCSS scheduling category
    effect="Keeps the MMCSS Games task category at Windows' own value",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    # Detection
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": GAMES_KEY,
        "name": "Scheduling Category",
        "hive": "HKLM",
    },
    value_map={"Low": "Low", "Medium": "Medium", "High": "High", None: "Medium"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": GAMES_KEY,
        "name": "Scheduling Category",
        "hive": "HKLM",
        "type": "REG_SZ",
    },
    apply_value_map={},
)

# === Win32 Priority Separation ===
# The low six bits of Win32PrioritySeparation (Windows Internals): bits 4-5 the
# quantum length (short/long), bits 2-3 fixed or variable, bits 0-1 the
# foreground boost. Client Windows ships 2, which behaves as 0x26: short,
# variable quanta with a 3:1 foreground boost. 0x18, which earlier releases
# wrote as "standard", is long fixed quanta with no boost — the Server
# "Background services" choice — and 0x2A only lengthens background slices
# while leaving the foreground's unchanged. So this is a guard on stock.
WIN32_PRIORITY_SEPARATION = SettingExecutor(
    id="priority:win32_priority_separation",
    category=SettingCategory.CORE,
    display_name="CPU Quantum Allocation",
    short_name="Foreground CPU share",
    description="How Windows splits CPU time between the program in front and the rest. Windows already "
    "favours the foreground three to one; other tools' values only shift time away from it.",
    value_type=SettingValueType.CHOICE,
    choices=("standard", "changed"),
    default_value="standard",
    recommended_value="standard",
    requires_reboot=False,
    sources=["https://learn.microsoft.com/en-us/previous-versions/cc976120(v=technet.10)"],
    current_impact="Changed: the foreground program gets less of the CPU than Windows gives it",
    recommended_impact="Windows default: short variable slices with a 3:1 foreground boost",
    scope=SettingScope.ESSENTIAL,
    category_order=5,
    effect="Restores Windows' own foreground CPU priority",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": PRIORITY_CONTROL_KEY,
        "name": "Win32PrioritySeparation",
        "hive": "HKLM",
    },
    value_map={2: "standard", 38: "standard", None: "standard", UNMAPPED: "changed"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": PRIORITY_CONTROL_KEY,
        "name": "Win32PrioritySeparation",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"standard": 2},
)

# All priority settings
PRIORITY_SETTINGS: list[SettingExecutor] = [
    GAME_PRIORITY,
    SYSTEM_RESPONSIVENESS,
    SCHEDULING_CATEGORY,
    WIN32_PRIORITY_SEPARATION,
]
