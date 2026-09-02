"""Game Mode setting definitions.

Contains settings for Windows Game Mode, Game Bar, and Xbox features.
These settings optimize Windows for gaming with zero risk.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# === Game Mode ===
# Windows feature that prioritizes games, blocks Windows Update interrupts
GAME_MODE = SettingExecutor(
    id="game:game_mode",
    category=SettingCategory.GAME,
    display_name="Game Mode",
    short_name="Game Mode",
    description="Windows gaming optimization. Prioritizes GPU, blocks updates during gameplay.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Enabled: Windows prioritizes game processes and GPU",
    recommended_impact="Enabled: +5-7% better 1% lows, no Windows Update interrupts",
    scope=SettingScope.ESSENTIAL,  # High impact on game performance
    category_order=1,  # Primary game optimization
    effect="Enables Windows Game Mode for automatic game optimization and update blocking",
    impact_scores={
        "fps": "+1-3%",
        "fps_1_percent_low": "+2-4%",
        "fps_cpu_bound": "+2-4%",
        "latency_ms": -0.5,
        "stability": "high",
    },
    # Detection - Registry
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\GameBar",
        "name": "AutoGameModeEnabled",
        "hive": "HKCU",
    },
    # 1 = enabled (default), 0 = disabled
    value_map={1: "enabled", 0: "disabled", "1": "enabled", "0": "disabled", None: "enabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\GameBar",
        "name": "AutoGameModeEnabled",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# === Game Bar ===
# Xbox Game Bar overlay - can add overhead
GAME_BAR = SettingExecutor(
    id="game:game_bar",
    category=SettingCategory.GAME,
    display_name="Xbox Game Bar",
    short_name="Xbox Game Bar",
    description="Xbox overlay for screenshots, recording, performance widgets.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Overlay always running in background",
    recommended_impact="Disabled: No overlay overhead, use dedicated tools instead",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for overhead reduction
    category_order=3,  # Overlay overhead
    effect="Disables Xbox Game Bar overlay to reduce background CPU and GPU overhead",
    impact_scores={
        "fps": "+0-2%",
        "fps_cpu_bound": "+1-3%",
        "latency_ms": -0.5,
        "stability": "high",
    },
    # Detection - Registry
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR",
        "name": "AppCaptureEnabled",
        "hive": "HKCU",
    },
    # 1 = enabled, 0 = disabled
    value_map={1: "enabled", 0: "disabled", "1": "enabled", "0": "disabled", None: "enabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR",
        "name": "AppCaptureEnabled",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# === Background Recording (Game DVR) ===
# Records last X minutes in background - uses GPU and disk
GAME_DVR_BACKGROUND = SettingExecutor(
    id="game:background_recording",
    category=SettingCategory.GAME,
    display_name="Background Recording",
    short_name="Background recording",
    description="Records gameplay in background for instant replay. Uses GPU and disk.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Constant GPU encoding + disk writes",
    recommended_impact="Disabled: No background recording overhead",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for GPU/disk overhead
    category_order=4,  # Recording overhead
    effect="Disables background game recording to free GPU encoding resources and disk I/O",
    impact_scores={
        "fps": "+1-3%",
        "fps_cpu_bound": "+3-5%",
        "latency_ms": -1.5,
        "ram_saved": "200-600MB",
        "vram_mb": -50,
    },
    # Detection - Registry
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR",
        "name": "HistoricalCaptureEnabled",
        "hive": "HKCU",
    },
    # 1 = enabled, 0 = disabled
    value_map={1: "enabled", 0: "disabled", "1": "enabled", "0": "disabled", None: "disabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR",
        "name": "HistoricalCaptureEnabled",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# === Hardware-Accelerated GPU Scheduling (HAGS) ===
# Note: Research (Gamer Nexus, BabelTechReviews) shows minimal gaming benefit.
# Main use case: Required for DLSS 3 Frame Generation.
# Content creation (After Effects) sees up to 10% improvement.
# Requires WDDM 2.7+ driver and Windows 10 2004+ (build 19041+)
HAGS = SettingExecutor(
    id="game:hags",
    category=SettingCategory.GAME,
    display_name="Hardware-Accelerated GPU Scheduling",
    short_name="GPU hardware scheduling",
    description="Lets the GPU schedule its own work instead of the CPU. DLSS 3 Frame Generation needs it on; "
    "pair it with an fps cap for the lowest latency.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",  # Keep enabled for DLSS 3 compatibility
    requires_reboot=True,
    current_impact="Disabled: CPU handles GPU task scheduling",
    recommended_impact="Enabled: Required for DLSS 3 Frame Gen. Minimal FPS impact otherwise.",
    scope=SettingScope.RECOMMENDED,  # Not ESSENTIAL - minimal gaming benefit per benchmarks
    category_order=2,  # GPU scheduling feature
    effect="Enables GPU-side scheduling, which DLSS 3 Frame Generation requires",
    impact_scores={
        "fps": "+0-1%",
        "fps_1_percent_low": "+0-2%",
        "latency_ms": -1.5,
        "stability": "high",
    },
    applicable_conditions={"min_windows_build": 19041},  # Windows 10 2004+
    # Detection - Registry
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "name": "HwSchMode",
        "hive": "HKLM",
    },
    # 2 = enabled, 1 = disabled, None = depends on Windows default
    value_map={2: "enabled", 1: "disabled", "2": "enabled", "1": "disabled", None: "disabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "name": "HwSchMode",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 2, "disabled": 1},
)

# === Variable Refresh Rate (VRR) - Windows System Setting ===
# Generic VRR for DirectX 11 games without native VRR support
# Works with FreeSync, G-Sync Compatible, and Adaptive-Sync monitors
WINDOWS_VRR = SettingExecutor(
    id="game:vrr",
    category=SettingCategory.GAME,
    display_name="Variable Refresh Rate (VRR)",
    short_name="Windowed VRR",
    description="System-wide VRR for DX11 games. Works with FreeSync, G-Sync Compatible, Adaptive-Sync.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Disabled: DX11 fullscreen games may have tearing",
    recommended_impact="Enabled: Smooth VRR for DX11 games (requires VRR monitor)",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for tearing elimination
    category_order=5,  # Display sync technology
    effect="Enables system-wide VRR for DX11 games that lack native VRR support",
    impact_scores={"fps": "0%", "latency_ms": -1.5, "stability": "high", "ux": "no tearing"},
    applicable_conditions={"requires_vrr": True},  # Only useful with VRR monitor
    # Detection - PowerShell to parse DirectXUserGlobalSettings string
    # 'disabled' is the Windows default when key doesn't exist
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$val = Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences' "
        "-Name 'DirectXUserGlobalSettings' -ErrorAction SilentlyContinue; "
        "if ($val -and $val.DirectXUserGlobalSettings -like '*VRROptimizeEnable=1*') { 'enabled' } "
        "elseif ($val -and $val.DirectXUserGlobalSettings -like '*VRROptimizeEnable=0*') { 'disabled' } "
        "else { 'disabled' }"
    ),
    detect_args={},
    value_map={},  # Direct pass-through
    # Apply - PowerShell to set/modify DirectXUserGlobalSettings string
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$path = 'HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences'; "
        "$name = 'DirectXUserGlobalSettings'; "
        "if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }; "
        "$current = (Get-ItemProperty -Path $path -Name $name -ErrorAction SilentlyContinue).$name; "
        "$newVal = if ('%value%' -eq 'enabled') { '1' } else { '0' }; "
        "if ($current -match 'VRROptimizeEnable=\\d') { "
        "$updated = $current -replace 'VRROptimizeEnable=\\d', \"VRROptimizeEnable=$newVal\"; "
        "} elseif ($current) { "
        '$updated = "$current;VRROptimizeEnable=$newVal"; '
        "} else { "
        '$updated = "VRROptimizeEnable=$newVal"; '
        "}; "
        "Set-ItemProperty -Path $path -Name $name -Value $updated -Type String"
    ),
    apply_args={},
    apply_value_map={},
)

# All game settings
GAME_SETTINGS: list[SettingExecutor] = [
    GAME_MODE,
    GAME_BAR,
    GAME_DVR_BACKGROUND,
    HAGS,
    WINDOWS_VRR,
]
