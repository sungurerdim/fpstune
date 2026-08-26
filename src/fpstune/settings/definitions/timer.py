"""Timer setting definitions.

Only one timer setting survives: the global timer-resolution registry key.

HPET (``useplatformclock``), platform tick (``useplatformtick``), dynamic tick
(``disabledynamictick``) and TSC sync policy were removed in the 2026-08 audit.
All four recommended the Windows default, so applying them did nothing, while
the alternative choice they exposed was actively harmful:

- The FPS "gains" attributed to these are largely a measurement artifact.
  FRAPS/Afterburner/RTSS count frames against a Windows timer, so changing the
  clock source changes what the tool believes a second is. A longer "fake
  second" inflates the counter without the game rendering any faster.
- ``useplatformtick`` forces the RTC, an outdated tick with no dynamic
  behaviour, and is reported to reduce performance and disturb mouse
  consistency.
- ``disabledynamictick`` is the most defensible of the three and still
  inconsistent: it can alter mouse feel and disrupt frametimes.
- ``tscsyncpolicy`` is documented as a debugging setting; a reported
  combination including ``tscsyncpolicy enhanced`` took a system from a stable
  165 FPS to fluctuating around 100 with drops to 3 FPS.
- On Windows 11 24H2 the OS already chooses the timer source itself, and most
  2024+ boards ship with HPET disabled in BIOS anyway.

The same research validates keeping ``timer:global_timer_resolution``: timer
*resolution* — how often the scheduler ticks — is the knob that actually
affects frame pacing and responsiveness, as opposed to which hardware clock
source the OS reads.

Sources:
- https://sites.google.com/view/melodystweaks/misconceptions-about-timers
- https://bottleneck-calculator.us/stop-disabling-hpet-the-truth-about-the-2-fps-boost-myth-in/
- https://forums.blurbusters.com/viewtopic.php?t=13842
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# === Global Timer Resolution Requests (Windows 11) ===
# Windows 10 v2004+ changed timer resolution to per-process instead of system-wide.
# This registry key restores the old behavior where any process requesting
# a lower timer resolution affects the entire system.
# Essential for gaming: games request 1ms, tools like ISLC can reduce to 0.5ms.
# Without this, only the requesting process benefits from lower resolution.
GLOBAL_TIMER_RESOLUTION = SettingExecutor(
    id="timer:global_timer_resolution",
    category=SettingCategory.TIMER,
    display_name="Global Timer Resolution (Win11)",
    short_name="Windows timer precision",
    description="Makes timer resolution requests system-wide instead of per-process.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=True,
    evidence_level="proven",
    sources=["https://forums.blurbusters.com/viewtopic.php?t=13842"],
    current_impact="Disabled: Timer resolution is per-process (15.6ms default for others)",
    recommended_impact="Enabled: All processes benefit from lowest requested resolution (0.5-1ms)",
    scope=SettingScope.ESSENTIAL,  # High impact on system-wide timing
    category_order=2,  # Second most important timer setting
    applicable_conditions={"min_windows_build": 19041},  # Windows 10 2004+
    effect="Enables system-wide 0.5-1ms timer resolution for smoother gameplay",
    impact_scores={
        "fps": "+0-5%",
        "fps_cpu_bound": "+0-3%",
        "fps_1_percent_low": "+1-6%",
        "latency_ms": -1.5,
        "stability": "high",
    },
    # Detection - Registry based
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\kernel",
        "name": "GlobalTimerResolutionRequests",
        "hive": "HKLM",
    },
    # 0 or None = disabled (Windows default), 1 = enabled
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "disabled"},
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\kernel",
        "name": "GlobalTimerResolutionRequests",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# All timer settings
TIMER_SETTINGS: list[SettingExecutor] = [
    GLOBAL_TIMER_RESOLUTION,
]
