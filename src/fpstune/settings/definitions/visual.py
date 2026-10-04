"""Visual setting definitions.

Contains settings for animations and transparency.
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
PERSONALIZE_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# === Animations ===
# What Settings > Accessibility > Visual effects > "Animation effects" switches:
# the window minimize/maximize animation and the in-window (client area) ones.
# This used to write MenuShowDelay, a hover delay that animates nothing, so the
# row said "animations off" while every window still animated. Read and written
# through SystemParametersInfo (utils/winapi/spi.py), because the client-area
# flag has no registry value of its own to read.
ANIMATIONS = SettingExecutor(
    id="visual:animations",
    category=SettingCategory.VISUAL,
    display_name="Animations",
    short_name="Window animations",
    description="Windows animates opening, minimizing and switching windows. Off, windows and menus "
    "appear at once, and the compositor stops drawing the in-between frames.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="On: window animations spend GPU and CPU time and delay each action",
    recommended_impact="Off: window actions are instant and the GPU is free for the game",
    scope=SettingScope.COMPLETE,
    category_order=1,
    perceptible_cost=(
        "Windows UI animations are turned off — menus and windows snap instead of gliding."
    ),
    effect="Turns off window and in-window animations for instant UI response",
    impact_scores={
        "fps": "0%",
        "fps_1_percent_low": "+0-1%",
        "latency_ms": -0.5,
        "stability": "high",
    },
    detect_type=DetectType.POWERSHELL,
    detect_command="animations_status",
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="animations_toggle",
    apply_args={},
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

# === Transparency ===
TRANSPARENCY = SettingExecutor(
    id="visual:transparency",
    category=SettingCategory.VISUAL,
    display_name="Transparency",
    short_name="Transparency effects",
    description="The blur behind windows and menus is redrawn by the GPU the whole time it is on screen, "
    "including while a game runs behind it. Off, that work goes to the game instead.",
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

# All visual settings
VISUAL_SETTINGS: list[SettingExecutor] = [
    ANIMATIONS,
    TRANSPARENCY,
]
