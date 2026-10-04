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
from fpstune.settings.definitions.display import directx_flag_scripts

# === Game Mode ===
# Windows feature that prioritizes games, blocks Windows Update interrupts
GAME_MODE = SettingExecutor(
    id="game:game_mode",
    category=SettingCategory.GAME,
    display_name="Game Mode",
    short_name="Game Mode",
    description="Keeps Windows from starting updates and background installs mid-match, and gives the game "
    "first call on the GPU. Off, an update can land in the middle of a round.",
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
# Two values, one concept (C8 named compound): AppCaptureEnabled is Settings'
# "Record what happens" switch, and GameConfigStore\GameDVR_Enabled is the one
# the capture hook in every game process checks. Writing only the first left
# the hook loading into every game while the row read "disabled".
GAME_BAR = SettingExecutor(
    id="game:game_bar",
    category=SettingCategory.GAME,
    display_name="Xbox Game Bar Capture",
    short_name="Xbox Game Bar capture",
    description="Game Bar hooks every game so it can record on demand. Off, that hook and its background "
    "capture stop costing frames you never asked to spend.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: The capture hook loads into every game",
    recommended_impact="Disabled: No capture hook, use dedicated recording tools instead",
    scope=SettingScope.RECOMMENDED,
    category_order=3,
    effect="Turns off Game Bar capture and the hook it loads into games",
    impact_scores={
        "fps": "+0-2%",
        "fps_cpu_bound": "+1-3%",
        "latency_ms": -0.5,
        "stability": "high",
    },
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$c = (Get-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\GameDVR' "
        "-Name 'AppCaptureEnabled' -ErrorAction SilentlyContinue).AppCaptureEnabled; "
        "$d = (Get-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' "
        "-Name 'GameDVR_Enabled' -ErrorAction SilentlyContinue).GameDVR_Enabled; "
        "if ($c -eq 0 -and $d -eq 0) { 'disabled' } else { 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$v = if ('%value%' -eq 'enabled') { 1 } else { 0 }; "
        "foreach ($t in @(@('HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\GameDVR', "
        "'AppCaptureEnabled'), @('HKCU:\\System\\GameConfigStore', 'GameDVR_Enabled'))) { "
        "if (-not (Test-Path $t[0])) { New-Item -Path $t[0] -Force | Out-Null }; "
        "Set-ItemProperty -Path $t[0] -Name $t[1] -Value $v -Type DWord -Force }"
    ),
    apply_args={},
    apply_value_map={},
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
# Research (Gamers Nexus, BabelTechReviews) shows minimal gaming benefit; the
# main reason is that DLSS 3 Frame Generation requires it. Needs a WDDM 2.7+
# driver. With HwSchMode absent the driver decides — on current drivers and
# Windows 11 that is often "on" — so an absent value is its own reading, never
# "disabled", and reset deletes the value to hand the choice back.
HAGS = SettingExecutor(
    id="game:hags",
    category=SettingCategory.GAME,
    display_name="Hardware-Accelerated GPU Scheduling",
    short_name="GPU hardware scheduling",
    description="Lets the GPU schedule its own work instead of the CPU. DLSS 3 Frame Generation needs it on; "
    "pair it with an fps cap for the lowest latency.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled", "driver_default"),
    default_value="driver_default",
    recommended_value="enabled",  # Keep enabled for DLSS 3 compatibility
    requires_reboot=True,
    current_impact="Not enabled: the driver or the CPU decides how GPU work is scheduled",
    recommended_impact="Enabled: Required for DLSS 3 Frame Gen. Minimal FPS impact otherwise.",
    scope=SettingScope.RECOMMENDED,
    category_order=2,
    effect="Enables GPU-side scheduling, which DLSS 3 Frame Generation requires",
    impact_scores={
        "fps": "+0-1%",
        "fps_1_percent_low": "+0-2%",
        "latency_ms": -1.5,
        "stability": "high",
    },
    applicable_conditions={"min_windows_build": 19041},  # WDDM 2.7, Windows 10 2004+
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "name": "HwSchMode",
        "hive": "HKLM",
    },
    value_map={
        2: "enabled",
        1: "disabled",
        "2": "enabled",
        "1": "disabled",
        None: "driver_default",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "name": "HwSchMode",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 2, "disabled": 1, "driver_default": None},
)

_VRR_DETECT, _VRR_APPLY = directx_flag_scripts("VRROptimizeEnable")

# === Variable Refresh Rate (VRR) - Windows System Setting ===
# Generic VRR for DirectX 11 games without native VRR support
# Works with FreeSync, G-Sync Compatible, and Adaptive-Sync monitors
WINDOWS_VRR = SettingExecutor(
    id="game:vrr",
    category=SettingCategory.GAME,
    display_name="Variable Refresh Rate (VRR)",
    short_name="Windowed VRR",
    description="Lets the display change its refresh rate to match the frames the GPU produces, so DX11 games "
    "stop tearing without the input lag V-Sync costs. Needs a FreeSync or G-Sync monitor.",
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
    detect_type=DetectType.POWERSHELL,
    detect_command=_VRR_DETECT,
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=_VRR_APPLY,
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
