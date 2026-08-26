"""Priority setting definitions.

Contains settings for GPU priority, game priority, system responsiveness.
All use registry executor.
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
GAMES_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
SYSTEM_PROFILE_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
PRIORITY_CONTROL_KEY = r"SYSTEM\CurrentControlSet\Control\PriorityControl"

# === GPU Priority ===
GPU_PRIORITY = SettingExecutor(
    id="priority:gpu_priority",
    category=SettingCategory.CORE,
    display_name="GPU Priority",
    description="GPU scheduling priority for games (0-31)",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=8,
    recommended_value=8,
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service"
    ],
    current_impact="GPU scheduling priority level",
    recommended_impact="Priority 8 = high GPU scheduling → lower render latency",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for GPU scheduling
    category_order=1,  # Primary GPU scheduling setting
    effect="Ensures high GPU scheduling priority for games",
    impact_scores={"fps": "+0-1%", "latency_ms": -0.2, "stability": "high"},
    min_value=0,  # Minimum priority (lowest)
    max_value=31,  # Maximum priority (highest)
    # Detection
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": GAMES_KEY,
        "name": "GPU Priority",
        "hive": "HKLM",
    },
    value_map={None: 8},  # Default Windows value when key doesn't exist
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": GAMES_KEY,
        "name": "GPU Priority",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={},
)

# === Game Priority ===
GAME_PRIORITY = SettingExecutor(
    id="priority:game_priority",
    category=SettingCategory.CORE,
    display_name="Game Priority",
    description="Game task priority (1-6, 6 = highest)",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=2,
    recommended_value=6,
    requires_reboot=False,
    current_impact="Priority 2 = normal process priority",
    recommended_impact="Priority 6 = above normal → better CPU scheduling",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for CPU scheduling
    category_order=2,  # Game process priority
    effect="Elevates game process CPU scheduling priority",
    impact_scores={"fps": "+0-1%", "latency_ms": -0.2, "stability": "high"},
    min_value=1,  # Minimum MMCSS priority
    max_value=6,  # Maximum MMCSS priority (above normal)
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
    description="Foreground app priority (0 = max foreground priority)",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=20,
    recommended_value=0,
    requires_reboot=False,
    current_impact="20% CPU reserved for system → may limit game performance",
    recommended_impact="0% reserved → games get full CPU priority",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for foreground priority
    category_order=3,  # System-wide responsiveness
    effect="Allocates full CPU priority to foreground games",
    impact_scores={
        "fps": "+0-1%",
        "fps_cpu_bound": "+0-2%",
        "fps_1_percent_low": "+0-1%",
        "latency_ms": -0.3,
        "stability": "high",
    },
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
    description="Sets the MMCSS scheduling category that games are assigned by the multimedia class scheduler. Higher categories receive preferential CPU access and lower scheduling latency.",
    value_type=SettingValueType.CHOICE,
    choices=("Low", "Medium", "High"),
    default_value="Medium",
    recommended_value="High",
    requires_reboot=False,
    current_impact="MMCSS scheduling category for multimedia apps",
    recommended_impact="High = better scheduling for games",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for MMCSS scheduling
    category_order=4,  # MMCSS scheduling category
    effect="Improves multimedia task scheduling for games",
    impact_scores={
        "fps": "+0-1%",
        "fps_cpu_bound": "+0-2%",
        "latency_ms": -0.2,
        "stability": "high",
    },
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
# Controls foreground process priority boost and CPU quantum allocation.
# Value is a bitmask:
#   Bits 0-1: Foreground boost (0=none, 1=medium, 2=high)
#   Bits 2-3: Quantum length (0=default, 1=short, 2=long)
#   Bits 4-5: Quantum type (0=default, 1=variable, 2=fixed)
# Common values:
#   0x18 (24): Long variable quanta, high boost (Windows default for desktop)
#   0x26 (38): Short variable quanta, high boost (common "gaming" tweak - NOT optimal)
#   0x2A (42): Short FIXED quanta, high boost (OPTIMAL for gaming - proven lower latency)
#   0x29 (41): Short fixed quanta, medium boost (good for multitasking + gaming)
WIN32_PRIORITY_SEPARATION = SettingExecutor(
    id="priority:win32_priority_separation",
    category=SettingCategory.CORE,
    display_name="CPU Quantum Allocation",
    description="Controls CPU time slice distribution. Fixed short quanta = lower input latency.",
    value_type=SettingValueType.CHOICE,
    choices=("standard", "gaming", "balanced"),
    default_value="standard",
    recommended_value="gaming",
    requires_reboot=False,
    current_impact="Default (0x18): Variable long quanta → higher input latency variance",
    recommended_impact="Gaming (0x2A): Fixed short quanta → 5-10% lower input latency, better 1% lows",
    scope=SettingScope.ESSENTIAL,  # High impact on input latency
    category_order=5,  # After scheduling category
    effect="Reduces input latency with fixed short CPU time slices",
    impact_scores={
        "fps": "+0-2%",
        "fps_cpu_bound": "+1-3%",
        "fps_1_percent_low": "+1-4%",
        "latency_ms": -1,
        "stability": "high",
    },
    # Detection - Read raw DWORD value and map to our choices
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": PRIORITY_CONTROL_KEY,
        "name": "Win32PrioritySeparation",
        "hive": "HKLM",
    },
    # Map raw registry values to our choice names
    # 0x2A (42) = short fixed + high boost = "gaming"
    # 0x29 (41) = short fixed + medium boost = "balanced"
    # 0x18 (24) = long variable + high boost = "default" (Windows desktop default)
    # Multiple values map to "default" for these reasons:
    # - 0x26 (38): Short VARIABLE quanta - common "gaming" tweak but variable quanta
    #   cause latency variance, so we treat it as non-optimal/default
    # - 0x02 (2): Legacy Windows default from older versions
    # - None: Registry key doesn't exist (treat as Windows default behavior)
    value_map={
        42: "gaming",  # 0x2A - optimal: short FIXED quanta, high boost
        41: "balanced",  # 0x29 - balanced: short fixed quanta, medium boost
        24: "standard",  # 0x18 - Windows 10+ desktop default
        38: "standard",  # 0x26 - short VARIABLE (not optimal, variable causes latency jitter)
        2: "standard",  # 0x02 - legacy Windows default (pre-Win10)
        # String versions for values that come as strings from PowerShell
        "42": "gaming",
        "41": "balanced",
        "24": "standard",
        "38": "standard",
        "2": "standard",
        None: "standard",  # Key not present: use Windows default behavior
    },
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": PRIORITY_CONTROL_KEY,
        "name": "Win32PrioritySeparation",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={
        "gaming": 42,  # 0x2A - short fixed quanta, high boost
        "balanced": 41,  # 0x29 - short fixed quanta, medium boost
        "standard": 24,  # 0x18 - Windows desktop default
    },
)

# === SFIO Priority (Scheduled File I/O) ===
SFIO_PRIORITY = SettingExecutor(
    id="priority:sfio_priority",
    category=SettingCategory.CORE,
    display_name="SFIO Priority",
    description="Scheduled File I/O priority for games. Higher = faster game asset loading.",
    value_type=SettingValueType.CHOICE,
    choices=("Normal", "High"),
    default_value="Normal",
    recommended_value="High",
    requires_reboot=False,
    current_impact="Normal: Standard I/O scheduling for games",
    recommended_impact="High: Prioritized file I/O → faster texture/asset loading",
    scope=SettingScope.RECOMMENDED,
    category_order=6,
    effect="Prioritizes game file I/O for faster asset loading",
    impact_scores={"loading_speed": "0%", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": GAMES_KEY,
        "name": "SFIO Priority",
        "hive": "HKLM",
    },
    value_map={"Normal": "Normal", "High": "High", None: "Normal"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": GAMES_KEY,
        "name": "SFIO Priority",
        "hive": "HKLM",
        "type": "REG_SZ",
    },
    apply_value_map={},
)

# All priority settings
PRIORITY_SETTINGS: list[SettingExecutor] = [
    GPU_PRIORITY,
    GAME_PRIORITY,
    SYSTEM_RESPONSIVENESS,
    SCHEDULING_CATEGORY,
    WIN32_PRIORITY_SEPARATION,
    SFIO_PRIORITY,
]
