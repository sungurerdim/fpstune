"""Visual setting definitions.

Contains settings for animations, transparency, smooth scrolling.
Uses registry executor.
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
DESKTOP_KEY = r"Control Panel\Desktop"
WINDOW_METRICS_KEY = r"Control Panel\Desktop\WindowMetrics"
PERSONALIZE_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
DWM_KEY = r"SOFTWARE\Microsoft\Windows\DWM"

# === Animations ===
# MenuShowDelay is REG_SZ (string), not DWORD
ANIMATIONS = SettingExecutor(
    id="visual:animations",
    category=SettingCategory.VISUAL,
    display_name="Animations",
    short_name="Window animations",
    description="Controls Windows UI animations and menu display delays. Disabling them eliminates visual lag and frees GPU/CPU cycles that games can use instead.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="On: window animations spend GPU and CPU time and delay each action",
    recommended_impact="Off: window actions are instant and the GPU is free for the game",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=1,
    perceptible_cost=(
        "Windows UI animations are turned off — menus and windows snap instead of gliding."
    ),  # Primary visual effect
    effect="Disables window animations and menu delays for instant UI response",
    impact_scores={
        "fps": "0%",
        "fps_1_percent_low": "+0-1%",
        "latency_ms": -0.5,
        "stability": "high",
    },
    # Detection - MenuShowDelay is REG_SZ: "0" = disabled, "400" = enabled (default)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": DESKTOP_KEY,
        "name": "MenuShowDelay",
        "hive": "HKCU",
    },
    # Registry returns string values for REG_SZ, None = key doesn't exist (default 400ms)
    value_map={"0": "disabled", "400": "enabled", None: "enabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": DESKTOP_KEY,
        "name": "MenuShowDelay",
        "hive": "HKCU",
        "type": "REG_SZ",
    },
    apply_value_map={"disabled": "0", "enabled": "400"},
)

# === Transparency ===
TRANSPARENCY = SettingExecutor(
    id="visual:transparency",
    category=SettingCategory.VISUAL,
    display_name="Transparency",
    short_name="Transparency effects",
    description="Whether windows and menus draw with transparency, which uses the GPU continuously.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="On: transparency spends GPU time continuously",
    recommended_impact="Off: solid windows free the GPU for gaming",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=2,
    perceptible_cost=(
        "Windows translucency effects are turned off — the taskbar and menus render solid."
    ),  # GPU resource usage
    effect="Disables window transparency effects to reduce GPU load",
    impact_scores={
        "fps": "0%",
        "fps_1_percent_low": "+0-1%",
        "latency_ms": -0.3,
        "stability": "high",
    },
    # Detection - EnableTransparency (1 = enabled, 0 = disabled)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": PERSONALIZE_KEY,
        "name": "EnableTransparency",
        "hive": "HKCU",
    },
    value_map={1: "enabled", 0: "disabled", "1": "enabled", "0": "disabled", None: "enabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": PERSONALIZE_KEY,
        "name": "EnableTransparency",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# === Smooth Scrolling ===
SMOOTH_SCROLLING = SettingExecutor(
    id="visual:smooth_scrolling",
    category=SettingCategory.VISUAL,
    display_name="Smooth Scrolling",
    short_name="Smooth scrolling",
    description="Controls animated scroll interpolation in Windows Explorer and apps. Disabling delivers instant scroll response with no animation overhead.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="On: each scroll is animated, adding slight input lag",
    recommended_impact="Off: instant scrolling with no animation delay",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=3,
    perceptible_cost=(
        "List scrolling loses its glide — content jumps line to line."
    ),  # Input responsiveness
    effect="Disables smooth scrolling for instant scroll response",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "high"},
    # Detection - SmoothScroll (1 = enabled, 0 = disabled)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": DESKTOP_KEY,
        "name": "SmoothScroll",
        "hive": "HKCU",
    },
    value_map={
        1: "enabled",
        0: "disabled",
        "1": "enabled",
        "0": "disabled",
        None: "enabled",
    },  # Default is enabled
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": DESKTOP_KEY,
        "name": "SmoothScroll",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# All visual settings
VISUAL_SETTINGS: list[SettingExecutor] = [
    ANIMATIONS,
    TRANSPARENCY,
    SMOOTH_SCROLLING,
]
