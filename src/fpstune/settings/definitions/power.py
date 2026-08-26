"""Power setting definitions.

Contains settings for:
- Individual CPU power settings (boost, parking, EPP, scaling thresholds)
- USB selective suspend
- PCIe link state power management
- WLAN power saving

All use powercfg executor with locale-independent GUID-based commands.
"""

from __future__ import annotations

from typing import Any

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# Power setting GUIDs
# Subgroup: USB settings
USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
USB_SELECTIVE_SUSPEND_SETTING = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"

# Subgroup: PCI Express
PCIE_SUBGROUP = "501a4d13-42af-4429-9fd1-a8218c268e20"
# CORRECT GUID from Microsoft docs (previous was wrong)
PCIE_LINK_STATE_SETTING = "ee12f906-d277-404b-b6da-e5fa1a576df5"

# Subgroup: Wireless Adapter Settings
WLAN_SUBGROUP = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1"
WLAN_POWER_SAVING_SETTING = "12bbebe6-58d6-4636-95bb-3217ef867c1a"

# === USB Selective Suspend ===
USB_SELECTIVE_SUSPEND = SettingExecutor(
    id="power:usb_selective_suspend",
    category=SettingCategory.POWER,
    display_name="USB Selective Suspend",
    description="Puts idle USB devices to sleep. Can cause mouse/keyboard latency.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://forums.blurbusters.com/viewtopic.php?t=11801"],
    current_impact="Enabled: USB devices enter sleep → mouse/keyboard wake delay (1-5ms)",
    recommended_impact="Disabled: USB devices always active → no input lag, instant response",
    scope=SettingScope.ESSENTIAL,  # High impact on input lag
    category_order=1,  # Primary power setting for input latency
    effect="Disables USB power saving for consistent peripheral response",
    impact_scores={"latency_ms": -1.5, "stability": "high"},
    # Detection - uses /query SCHEME_CURRENT <subgroup> <setting>
    detect_type=DetectType.POWERCFG,
    detect_command="",  # Not used - executor builds command from args
    detect_args={
        "subgroup": USB_SUBGROUP,
        "setting": USB_SELECTIVE_SUSPEND_SETTING,
    },
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled"},
    # Apply - uses /setacvalueindex SCHEME_CURRENT <subgroup> <setting> <value>
    apply_type=DetectType.POWERCFG,
    apply_command="",  # Not used - executor builds command from args
    apply_args={
        "subgroup": USB_SUBGROUP,
        "setting": USB_SELECTIVE_SUSPEND_SETTING,
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

# === PCIe Link State Power Management ===
PCIE_LINK_STATE = SettingExecutor(
    id="power:pcie_link_state",
    category=SettingCategory.POWER,
    display_name="PCI-E Link State Power Management",
    description="Reduces PCIe link speed when idle to save power. Can cause GPU micro-stutter and frame time spikes.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "moderate", "maximum"),
    default_value="moderate",
    recommended_value="off",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://whoismcafee.com/link-state-power-management/"],
    current_impact="Moderate/Maximum: PCIe wake latency → GPU micro-stutter, frame time spikes",
    recommended_impact="Off: PCIe always at full speed → no stutter, consistent frame delivery",
    scope=SettingScope.ESSENTIAL,  # High impact on GPU stutter
    category_order=2,  # Critical for GPU performance
    effect="Keeps PCIe link at full speed to prevent GPU micro-stutter",
    impact_scores={
        "fps": "0%",
        "latency_ms": -0.5,
        "frame_time_consistency": "improved",
        "stability": "high",
    },
    # Detection - uses /query SCHEME_CURRENT <subgroup> <setting>
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={
        "subgroup": PCIE_SUBGROUP,
        "setting": PCIE_LINK_STATE_SETTING,
    },
    value_map={0: "off", "0": "off", 1: "moderate", "1": "moderate", 2: "maximum", "2": "maximum"},
    # Apply
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={
        "subgroup": PCIE_SUBGROUP,
        "setting": PCIE_LINK_STATE_SETTING,
    },
    apply_value_map={"off": 0, "moderate": 1, "maximum": 2},
)

# === WLAN Power Saving ===
WLAN_POWER_SAVING = SettingExecutor(
    id="power:wlan_power_saving",
    category=SettingCategory.POWER,
    display_name="WiFi Power Saving",
    description="Puts WiFi adapter to sleep between packets. Causes ping spikes of 20-100ms during gaming.",
    value_type=SettingValueType.CHOICE,
    choices=("maximum_performance", "low", "medium", "maximum"),
    default_value="medium",
    recommended_value="maximum_performance",
    requires_reboot=False,
    current_impact="Power saving active: WiFi sleeps → ping spikes (20-100ms), packet loss",
    recommended_impact="Maximum Performance: WiFi always active → stable ping, no lag spikes",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for WiFi users
    category_order=3,  # WiFi stability improvement
    effect="Disables WiFi power saving for stable network latency",
    # Not `latency_ms: -12.0`. That was the deterministic cap the impact_scores
    # sweep applied, and worse, it was a *mean* — this setting's own copy
    # describes occasional spikes of 20-100 ms, which is jitter. A mean of 12 ms
    # describes neither the quiet state nor the spike, and it fed the
    # user-visible latency total as though the connection were 12 ms better all
    # the time. The figure the copy already states is the honest one.
    impact_scores={
        "latency_spike_ms": "20-100 eliminated",
        "network_consistency": "high",
        "stability": "high",
    },
    # Detection - uses /query SCHEME_CURRENT <subgroup> <setting>
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={
        "subgroup": WLAN_SUBGROUP,
        "setting": WLAN_POWER_SAVING_SETTING,
    },
    value_map={
        0: "maximum_performance",
        "0": "maximum_performance",
        1: "low",
        "1": "low",
        2: "medium",
        "2": "medium",
        3: "maximum",
        "3": "maximum",
    },
    # Apply
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={
        "subgroup": WLAN_SUBGROUP,
        "setting": WLAN_POWER_SAVING_SETTING,
    },
    apply_value_map={"maximum_performance": 0, "low": 1, "medium": 2, "maximum": 3},
)

POWER_HIBERNATION = SettingExecutor(
    id="power:hibernation",
    category=SettingCategory.POWER,
    display_name="Hibernation",
    description="Saves full RAM contents to disk (hiberfil.sys) for fast wake from "
    "power-off. Disabling frees 4-16GB SSD space.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Enabled: hiberfil.sys occupies 4-16GB of SSD space constantly",
    recommended_impact="Disabled: 4-16GB SSD space freed, faster shutdown, "
    "no hibernate-related stutter",
    scope=SettingScope.RECOMMENDED,
    category_order=4,
    effect="Disables hibernation to free SSD space and eliminate hibernate-related stutter on wake",
    impact_scores={"disk_freed": "4-24GB", "latency_ms": 0, "stability": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Power",
        "name": "HibernateEnabled",
        "hive": "HKLM",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="hibernation_toggle",
    apply_args={},
    apply_value_map={"enabled": "enable", "disabled": "disable"},
)

# =============================================================================
# Individual CPU Power Settings (replace FPS_BALANCED_PROFILE compound)
# Each modifies exactly one powercfg subgroup/setting on the active plan.
# =============================================================================

# GUIDs (locale-independent)
#
# Four of these were wrong, and wrong in a way nothing could catch: powercfg answers
# "The power scheme, subgroup or setting specified does not exist." for a GUID it
# does not know, and the executor reported that as `not_available` — read by an
# earlier pass (#43) as "the active plan does not carry this subgroup". It was never
# the plan. `power:cpu_min_parking` is ESSENTIAL scope and `evidence_level="proven"`,
# and it had never detected or written anything on any machine.
#
# Every GUID below is now checked against
# HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerSettings\<subgroup>\<setting>,
# which is Windows' own catalogue of the settings it will accept, and the check is
# a test (`tests/test_windows_contract/test_powercfg_guids.py`) rather than a
# one-off. Anything missing there is a GUID powercfg will refuse.
CPU_SUBGROUP = "54533251-82be-4824-96c1-47b60b740d00"
DISK_SUBGROUP = "0012ee47-9041-4b5d-9b77-535fba8b1442"
DISK_TIMEOUT_SETTING = "6738e2c4-e8a5-4a42-b16a-e040e769756e"

# "Processor performance core parking min cores" (powrprof.dll,-767).
# Was 0cc5b647-c1df-4637-89a0-8fd6a52d4e1b, which is not a power setting at all —
# note how close it looks to the real one. 891a/dec35c318583, not 89a0/8fd6a52d4e1b.
CPU_MIN_PARKING_SETTING = "0cc5b647-c1df-4637-891a-dec35c318583"

# "Processor performance increase policy" (-391) and "decrease policy" (-393).
# Both previously carried GUIDs Windows does not publish.
PERF_INCREASE_POLICY_GUID = "465e1f50-b610-473a-ab58-00d1077dc418"
PERF_DECREASE_POLICY_GUID = "40fbefc7-2e9d-4d25-a185-0cfd8574bac6"

# "System cooling policy" (-371). The setting GUID was right all along; the subgroup
# was not — it repeated the setting's own GUID instead of naming SUB_PROCESSOR,
# which is the subgroup Windows files it under.
THERMAL_SUBGROUP = CPU_SUBGROUP
THERMAL_SETTING = "94d3a615-a899-4ac5-ae2b-e4d8f634367f"

# === CPU Boost Mode ===
POWER_CPU_BOOST = SettingExecutor(
    id="power:cpu_boost",
    category=SettingCategory.POWER,
    display_name="CPU Boost Mode",
    description="Controls how aggressively the CPU ramps to higher frequencies under load. "
    "Efficient Aggressive gives near-maximum performance with lower power overshoot.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "enabled", "efficient_enabled", "efficient_aggressive"),
    default_value="enabled",
    recommended_value="efficient_aggressive",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/performance-tuning/hardware/power/processor-power-management-tuning",
    ],
    current_impact="Enabled: Normal boost ramp-up speed",
    recommended_impact="Efficient Aggressive: Near-maximum boost with less power overshoot",
    scope=SettingScope.RECOMMENDED,
    category_order=6,
    effect="Sets CPU boost to Efficient Aggressive for fastest frequency scaling",
    impact_scores={"fps_cpu_bound": "+1-3%", "latency_ms": -0.5},
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": "be337238-0d82-4146-a960-4f3749d470c7"},
    value_map={
        0: "disabled",
        1: "enabled",
        3: "efficient_enabled",
        4: "efficient_aggressive",
        5: "efficient_aggressive",
    },
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": "be337238-0d82-4146-a960-4f3749d470c7"},
    apply_value_map={
        "disabled": 0,
        "enabled": 1,
        "efficient_enabled": 3,
        "efficient_aggressive": 4,
    },
)

# === CPU Increase Threshold ===
POWER_CPU_INCREASE_THRESHOLD = SettingExecutor(
    id="power:cpu_increase_threshold",
    category=SettingCategory.POWER,
    display_name="CPU Frequency Scale-Up Threshold",
    description="CPU utilization % that triggers frequency increase. Lower values cause faster "
    "frequency ramp-up, reducing CPU-bound frame time spikes.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=90,
    recommended_value=15,
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/performance-tuning/hardware/power/processor-power-management-tuning",
    ],
    current_impact="90%: CPU waits until nearly fully loaded before scaling up frequency",
    recommended_impact="15%: CPU scales up quickly → fewer frame time spikes",
    scope=SettingScope.RECOMMENDED,
    category_order=7,
    effect="Reduces CPU frequency scale-up threshold for faster response to load",
    impact_scores={"fps_cpu_bound": "+0-1%", "latency_ms": -0.3},
    min_value=0,
    max_value=100,
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": "06cadf0e-64ed-448a-8927-ce7bf90eb35d"},
    value_map={},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": "06cadf0e-64ed-448a-8927-ce7bf90eb35d"},
    apply_value_map={},
)

# === CPU Decrease Threshold ===
POWER_CPU_DECREASE_THRESHOLD = SettingExecutor(
    id="power:cpu_decrease_threshold",
    category=SettingCategory.POWER,
    display_name="CPU Frequency Scale-Down Threshold",
    description="CPU utilization % below which frequency decreases. Higher values keep "
    "the CPU at speed longer, reducing frequency yo-yo during gaming.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=5,
    recommended_value=8,
    requires_reboot=False,
    evidence_level="proven",
    current_impact="5%: CPU scales down quickly when utilization drops below 5%",
    recommended_impact="8%: CPU stays at speed a bit longer → reduces frequency oscillation",
    scope=SettingScope.RECOMMENDED,
    category_order=8,
    effect="Slightly raises CPU scale-down threshold to reduce frequency oscillation",
    impact_scores={"fps_cpu_bound": "+0-1%", "latency_ms": -0.1},
    min_value=0,
    max_value=100,
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": "12a0ab44-fe28-4fa9-b3bd-4b64f44960a6"},
    value_map={},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": "12a0ab44-fe28-4fa9-b3bd-4b64f44960a6"},
    apply_value_map={},
)

# === CPU Frequency Increase Policy ===
# GUID and value set both read off this machine's own PowerSettings key rather than
# recalled — see the note on PERF_INCREASE_POLICY_GUID. `1` is Single, not Rocket;
# the previous map would have written the wrong policy had the GUID been valid.
POWER_CPU_INCREASE_POLICY = SettingExecutor(
    id="power:cpu_increase_policy",
    category=SettingCategory.POWER,
    display_name="CPU Scale-Up Policy",
    description="Algorithm used when scaling CPU frequency up. Rocket jumps immediately "
    "to the highest needed frequency; Ideal uses gradual steps.",
    value_type=SettingValueType.CHOICE,
    # All four states Windows publishes. A machine sitting on Single or
    # IdealAggressive must read as itself, not fall outside `choices` (C6).
    choices=("ideal", "single", "rocket", "ideal_aggressive"),
    default_value="ideal",
    recommended_value="rocket",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Ideal: CPU steps up frequency gradually under increasing load",
    recommended_impact="Rocket: CPU jumps to target frequency immediately → no ramp-up delay",
    scope=SettingScope.RECOMMENDED,
    category_order=9,
    effect="Sets CPU frequency scale-up to Rocket policy for instant response",
    impact_scores={"fps_cpu_bound": "+0-1%", "latency_ms": -0.3},
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": PERF_INCREASE_POLICY_GUID},
    value_map={0: "ideal", 1: "single", 2: "rocket", 3: "ideal_aggressive"},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": PERF_INCREASE_POLICY_GUID},
    apply_value_map={"ideal": 0, "single": 1, "rocket": 2, "ideal_aggressive": 3},
)

# === CPU Frequency Decrease Policy ===
# Three states here, not four — IdealAggressive is increase-only. Read off the
# machine rather than assumed symmetric with the setting above.
POWER_CPU_DECREASE_POLICY = SettingExecutor(
    id="power:cpu_decrease_policy",
    category=SettingCategory.POWER,
    display_name="CPU Scale-Down Policy",
    description="Algorithm used when scaling CPU frequency down. Rocket drops immediately; "
    "Ideal uses gradual steps. Rocket allows faster re-ramp when needed.",
    value_type=SettingValueType.CHOICE,
    choices=("ideal", "single", "rocket"),
    default_value="ideal",
    recommended_value="rocket",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Ideal: CPU steps down frequency gradually",
    recommended_impact="Rocket: CPU drops to idle frequency immediately → allows faster re-ramp",
    scope=SettingScope.RECOMMENDED,
    category_order=10,
    effect="Sets CPU frequency scale-down to Rocket policy",
    impact_scores={"fps_cpu_bound": "+0-1%", "latency_ms": -0.1},
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": PERF_DECREASE_POLICY_GUID},
    value_map={0: "ideal", 1: "single", 2: "rocket"},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": PERF_DECREASE_POLICY_GUID},
    apply_value_map={"ideal": 0, "single": 1, "rocket": 2},
)

# === CPU Core Parking (Min Unparked %) ===
POWER_CPU_MIN_PARKING = SettingExecutor(
    id="power:cpu_min_parking",
    category=SettingCategory.POWER,
    display_name="CPU Core Parking (Min Unparked Cores)",
    description="Minimum percentage of CPU cores that stay active. Setting to 100% disables "
    "core parking, eliminating wake latency when parked cores are needed.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=0,
    recommended_value=100,
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/performance-tuning/hardware/power/processor-power-management-tuning",
    ],
    current_impact="0%: Windows may park most CPU cores → 1-5ms wake latency per frame",
    recommended_impact="100%: All cores always active → no parking wake latency",
    scope=SettingScope.ESSENTIAL,
    category_order=6,
    effect="Disables CPU core parking by keeping 100% of cores unparked",
    impact_scores={"fps_cpu_bound": "+0-1%", "latency_ms": -0.5, "stability": "marginal"},
    min_value=0,
    max_value=100,
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": CPU_MIN_PARKING_SETTING},
    value_map={},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": CPU_MIN_PARKING_SETTING},
    apply_value_map={},
)

# === CPU Energy Performance Preference ===
POWER_CPU_EPP = SettingExecutor(
    id="power:cpu_epp",
    category=SettingCategory.POWER,
    display_name="CPU Energy Performance Preference",
    description="Hint to the CPU hardware scheduler balancing performance vs efficiency. "
    "Lower values bias toward performance; 0 = maximum performance, 100 = maximum efficiency.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=50,
    recommended_value=25,
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.phoronix.com/review/intel-meteorlake-epp/",
    ],
    current_impact="50: Balanced between performance and efficiency",
    recommended_impact="25: Performance-biased → faster frequency ramp, better frame pacing",
    scope=SettingScope.RECOMMENDED,
    category_order=11,
    effect="Biases CPU scheduler toward performance for better frame pacing",
    impact_scores={"fps_cpu_bound": "+1-3%", "latency_ms": -0.5},
    min_value=0,
    max_value=100,
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": CPU_SUBGROUP, "setting": "36687f9e-e3a5-4dbf-b1dc-15eb381c6863"},
    value_map={},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": CPU_SUBGROUP, "setting": "36687f9e-e3a5-4dbf-b1dc-15eb381c6863"},
    apply_value_map={},
)

# === Disk Idle Timeout ===
POWER_DISK_TIMEOUT = SettingExecutor(
    id="power:disk_timeout",
    category=SettingCategory.POWER,
    display_name="Disk Idle Timeout",
    description="Seconds before spinning the HDD down when idle. Setting to 0 disables "
    "spin-down, eliminating the re-spin delay when accessing files during gaming.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=600,
    recommended_value=0,
    requires_reboot=False,
    evidence_level="proven",
    current_impact="600s: HDD spins down after 10 minutes of idle → stutter on first access",
    recommended_impact="0 (never): Disk stays ready → no spin-up stutter during gaming",
    # What this avoids is a spin-up stall on a mechanical disk, measured in seconds
    # and only on an HDD — not a millisecond input-latency saving. The -12.0 was the
    # sweep's clipping cap and the frontend adds latency_ms into Home's total.
    scope=SettingScope.RECOMMENDED,
    category_order=12,
    effect="Disables disk spin-down timeout to prevent stutter on access after idle",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    min_value=0,
    max_value=86400,
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": DISK_SUBGROUP, "setting": DISK_TIMEOUT_SETTING},
    value_map={},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": DISK_SUBGROUP, "setting": DISK_TIMEOUT_SETTING},
    apply_value_map={},
)

# === Thermal Active Cooling ===
POWER_THERMAL_COOLING = SettingExecutor(
    id="power:thermal_cooling",
    category=SettingCategory.POWER,
    display_name="Thermal Cooling Mode",
    description="Controls whether the system uses the fan (active) or throttles the CPU (passive) "
    "first when temperatures rise. Active cooling prevents thermal throttling.",
    value_type=SettingValueType.CHOICE,
    choices=("passive", "active"),
    default_value="passive",
    recommended_value="active",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Passive: CPU throttles first before fan increases → performance loss under load",
    recommended_impact="Active: Fan increases first → CPU maintains full clock speed",
    scope=SettingScope.RECOMMENDED,
    category_order=13,
    effect="Enables active thermal cooling so the fan runs first, preventing CPU throttle",
    impact_scores={"fps_cpu_bound": "+0-15%", "stability": "high"},
    detect_type=DetectType.POWERCFG,
    detect_command="",
    detect_args={"subgroup": THERMAL_SUBGROUP, "setting": THERMAL_SETTING},
    value_map={0: "passive", 1: "active"},
    apply_type=DetectType.POWERCFG,
    apply_command="",
    apply_args={"subgroup": THERMAL_SUBGROUP, "setting": THERMAL_SETTING},
    apply_value_map={"passive": 0, "active": 1},
)

# =============================================================================
# Ryzen Balanced Power Plan
# =============================================================================
#
# Shipped as advisory; it need not be. `powercfg /setactive <guid>` is the whole
# mechanism, and fpstune already drives powercfg for a dozen other settings.
#
# The reason to be careful is not the switch, it is what the switch takes with it.
# Every powercfg setting is stored PER SCHEME —
#     ...\Power\User\PowerSchemes\<scheme>\<subgroup>\<setting>\ACSettingIndex
# — so activating a different plan leaves every applied CPU tweak behind on the old
# one. That is C3 territory: a tweak that can lower the ceiling is not a tweak.
#
# Resolved by ordering rather than by refusing to act. This setting is
# `category_order=0`, ahead of every per-scheme setting in this file, so a bulk
# apply switches the plan first and then writes the tweaks onto it. Applied on its
# own it still leaves the others behind — but detection then reports them as
# needing apply, which is visible and true rather than silent.
#
# NOT VERIFIED ON HARDWARE: the dev machine is Intel, so no AMD Ryzen plan exists
# to activate. The mechanism is proven (powercfg /setactive returns 0 here for an
# existing scheme) and the plan lookup degrades to an error rather than a wrong
# write, but the first real confirmation needs a Ryzen host.
_WINDOWS_BALANCED_SCHEME = "381b4222-f694-41f0-9685-ff5bb260df2e"

RYZEN_BALANCED_PLAN = SettingExecutor(
    id="power:ryzen_balanced_plan",
    category=SettingCategory.POWER,
    display_name="AMD Ryzen Balanced Plan",
    description="Whether AMD's own power plan is the active one. Ryzen 1000-3000 CPUs need it "
    "for Precision Boost 2 to behave as AMD intends.",
    value_type=SettingValueType.CHOICE,
    choices=(
        "ryzen_balanced",
        "not_using_ryzen_plan",
        "no_ryzen_plan",
    ),
    # Windows' own default is its Balanced plan, which is what reset restores.
    # `no_ryzen_plan` stays a reading — "AMD's plan is not installed" — and apply
    # reports it rather than pretending to write it.
    default_value="not_using_ryzen_plan",
    recommended_value="ryzen_balanced",
    requires_reboot=False,
    evidence_level="likely",
    risk_level="moderate",
    risk_warning="Switching the active power plan leaves every other power tweak behind on the "
    "old plan, because Windows stores them per plan. Applied together with the rest of the power "
    "settings this is handled — the plan is switched first — but if you apply only this one, "
    "re-apply the other power tweaks afterwards. Needs AMD chipset drivers installed; without "
    "them the plan does not exist and fpstune reports that instead of guessing.",
    sources=[
        "https://www.ofzenandcomputing.com/amd-ryzen-balanced-vs-high-performance-power-plans/",
    ],
    current_impact="Not using it: Precision Boost 2 runs under a plan not tuned for it",
    recommended_impact="Ryzen Balanced active: correct CPU boost behavior for AMD Ryzen",
    applicable_conditions={"cpu_vendor": "amd"},
    scope=SettingScope.COMPLETE,
    # Ahead of every per-scheme setting in this file — see the note above.
    category_order=0,
    effect="Activates AMD's own power plan so Precision Boost 2 behaves as designed",
    impact_scores={"fps_cpu_bound": "+0-5%"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$active = ((powercfg /getactivescheme 2>$null) "
        "-split ' ')[3]; "
        "$list = powercfg /list 2>$null; "
        "$activeIsRyzen = $list | Where-Object { "
        "$_ -match $active -and $_ -match 'AMD Ryzen' }; "
        "if ($activeIsRyzen) { 'ryzen_balanced' } "
        "elseif ($list -match 'AMD Ryzen') "
        "{ 'not_using_ryzen_plan' } "
        "else { 'no_ryzen_plan' }"
    ),
    detect_args={},
    value_map={},
    # The GUID is resolved from powercfg's own listing rather than hardcoded: AMD
    # has shipped this plan under more than one GUID across chipset driver
    # versions, and a hardcoded one is the #45 mistake in a different subsystem.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$want = '%value%'; "
        "$list = powercfg /list 2>$null; "
        "if ($want -eq 'ryzen_balanced') { "
        "$line = $list | Where-Object { $_ -match 'AMD Ryzen' } | Select-Object -First 1; "
        "if (-not $line) { 'error: AMD Ryzen power plan is not installed - "
        "install the AMD chipset drivers first'; return }; "
        "$guid = ([regex]::Match($line, "
        "'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')).Value "
        "} else { "
        f"$guid = '{_WINDOWS_BALANCED_SCHEME}' }}; "
        "if (-not $guid) { 'error: could not read the power plan GUID'; return }; "
        "powercfg /setactive $guid 2>&1 | Out-Null; "
        # Read the active scheme back instead of trusting the exit code, the same
        # discipline the audio settings had to learn.
        "$now = ((powercfg /getactivescheme 2>$null) -split ' ')[3]; "
        "if ($now -eq $guid) { 'ok' } "
        "else { 'error: plan did not become active (still ' + $now + ')' }"
    ),
    apply_args={},
    apply_value_map={},
)

# All power settings (individual, single-responsibility tweaks)
POWER_THROTTLING = SettingExecutor(
    id="power:power_throttling",
    category=SettingCategory.POWER,
    display_name="CPU Power Throttling",
    description="Windows throttles processes it considers background work to save power, which "
    "on a laptop can include a game's secondary processes such as audio, shader compilation, and "
    "anti-cheat. Disabling it keeps those threads at full clock.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=True,
    evidence_level="likely",
    risk_level="moderate",
    risk_warning="Raises power draw and heat because Windows stops clocking background threads "
    "down. On a laptop this shortens battery runtime and can push the CPU into thermal limits "
    "sooner. The frame-rate benefit is directional — it is not independently benchmarked — so "
    "prefer this only while on AC power.",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/procthread/quality-of-service",
    ],
    current_impact="Enabled: Windows clocks down background game threads → frametime spikes on laptops",
    recommended_impact="Disabled: All game threads stay at full clock → steadier 1% lows",
    scope=SettingScope.COMPLETE,
    category_order=15,
    effect="Stops Windows from throttling the game's background threads",
    impact_scores={"fps_1_percent_low": "+0-5%", "battery_life": "reduced"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling",
        "name": "PowerThrottlingOff",
        "hive": "HKLM",
    },
    value_map={0: "enabled", 1: "disabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling",
        "name": "PowerThrottlingOff",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 0, "disabled": 1},
)


# ===========================================================================
# Full speed when it is needed, nothing when it is not
# ===========================================================================
# The settings above make the CPU respond faster. These decide what it does the
# rest of the time, and that turns out to be a performance question rather than
# an electricity one.
#
# Heat is not a comfort metric. A CPU that spent the last twenty minutes at its
# maximum multiplier because a "gaming optimizer" pinned it there arrives at the
# match already close to its thermal limit, and what happens next is the thing
# every one of these tweaks was supposed to prevent: it throttles. The frame rate
# does not drop at the moment of the tweak, which is why this class of damage
# survives so well — it drops in minute forty, and by then nobody is measuring.
#
# So the target here is narrow, and it is not "save power":
#
#   * ramp up the instant load appears
#   * do not step down while there is still work
#   * when the machine is genuinely idle, cost nothing
#   * and give up no performance at all for the third point
#
# The fourth clause is what separates this from a power plan. Windows' Balanced
# trades response time for efficiency; "High performance" and "Ultimate
# performance" trade the idle state away entirely. Neither is what a gaming
# machine wants. It wants both halves, and Windows will do both halves — it just
# files the controls under a subgroup it hides from its own UI.
#
# Half of what follows is therefore a drift guard rather than a change: on a
# clean install several of these already hold the right value, and the setting
# exists to notice when a guide, another tool, or an older fpstune release moved
# them. `Processor idle disable` is the clearest case. Setting it to 1 is one of
# the most widely repeated "gaming tweaks" there is; what it does is forbid every
# core from ever entering a C-state, which produces continuous heat, measurably
# shortens the part's life, and buys no frame rate whatsoever.
#
# Every GUID, range and Windows default below was read off this machine's own
# registry rather than recalled — `PowerSettings\<subgroup>\<setting>` for the
# range, `\DefaultPowerSchemeValues\<Balanced>` for the default — and
# `test_powercfg_guids.py` re-checks the GUIDs against Windows' own catalogue.
# All of them carry ATTRIBUTE_HIDE, so `powercfg /query` prints nothing for them;
# the executor reads the per-scheme registry key, which is why they work anyway.

_MS_PPM_DOC = (
    "https://learn.microsoft.com/en-us/windows-server/administration/"
    "performance-tuning/hardware/power/processor-power-management-tuning"
)

# Minimum/maximum processor state (-360 / -361). The only two in this block that
# Windows shows in its own UI.
CPU_MIN_STATE_SETTING = "893dee8e-2bef-41e0-89c6-b55d0929964c"
CPU_MAX_STATE_SETTING = "bc5038f7-23e0-4960-96da-33abaf5935ec"
# "Processor idle disable" — enum, 0 = Enable idle, 1 = Disable idle.
CPU_IDLE_DISABLE_SETTING = "5d76a2ca-e8c0-402f-a133-2158492d58ad"
# "Processor performance time check interval", in milliseconds, 1..5000.
CPU_PERF_CHECK_SETTING = "4d2b0152-7d5c-498b-88e2-34345392a2c5"
# "Processor performance increase/decrease time", counted in check intervals.
CPU_INCREASE_TIME_SETTING = "984cf492-3bed-4488-a8f9-4286c97bf5aa"
CPU_DECREASE_TIME_SETTING = "d8edeb9b-95cf-4f95-a73c-b061973693c8"
# The two latency-sensitivity hints: what the machine does when Windows knows the
# running workload cares about response time rather than throughput.
CPU_LATENCY_HINT_PERF_SETTING = "619b7505-003b-4e82-b7a6-4dd29c300971"
CPU_LATENCY_HINT_UNPARK_SETTING = "616cdaa5-695e-4545-97ad-97dc2d1bdd88"
# Core parking: how eagerly cores come back, not how eagerly they go away.
CPU_PARKING_INC_POLICY_SETTING = "c7be0679-2817-4d69-9d02-519a537ed0c6"
CPU_PARKING_INC_TIME_SETTING = "2ddd5a84-5a71-437e-912a-db0b8c788732"


def _cpu_power_setting(
    *,
    setting_id: str,
    guid: str,
    display_name: str,
    description: str,
    default_value: object,
    recommended_value: object,
    current_impact: str,
    recommended_impact: str,
    effect: str,
    impact_scores: dict[str, str | float],
    category_order: int,
    scope: SettingScope,
    choices: tuple[str, ...] = (),
    value_map: dict[Any, Any] | None = None,
    apply_value_map: dict[Any, Any] | None = None,
    min_value: int | None = None,
    max_value: int | None = None,
    evidence_level: str = "proven",
) -> SettingExecutor:
    """Build one processor-power setting.

    Ten settings differing only in a GUID and a pair of numbers would otherwise
    be ten copies of the same thirty lines, which is ten places for the subgroup
    or the executor wiring to drift apart. Everything identical lives here; the
    parameters are exactly what genuinely differs.
    """
    args = {"subgroup": CPU_SUBGROUP, "setting": guid}
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.POWER,
        display_name=display_name,
        description=description,
        value_type=SettingValueType.CHOICE if choices else SettingValueType.INT,
        choices=choices,
        default_value=default_value,
        recommended_value=recommended_value,
        min_value=min_value,
        max_value=max_value,
        requires_reboot=False,
        evidence_level=evidence_level,
        sources=[_MS_PPM_DOC],
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        scope=scope,
        category_order=category_order,
        effect=effect,
        impact_scores=impact_scores,
        detect_type=DetectType.POWERCFG,
        detect_command="",
        detect_args=dict(args),
        value_map=value_map if value_map is not None else {},
        apply_type=DetectType.POWERCFG,
        apply_command="",
        apply_args=dict(args),
        apply_value_map=apply_value_map if apply_value_map is not None else {},
    )


# === Minimum Processor State ===
POWER_CPU_MIN_STATE = _cpu_power_setting(
    setting_id="power:cpu_min_state",
    guid=CPU_MIN_STATE_SETTING,
    display_name="Minimum Processor State",
    description="Lowest clock speed the CPU is allowed to drop to when nothing is asking for "
    "work. Raising it to 100 pins every core at maximum multiplier around the clock, which "
    "produces constant heat and no frame rate at all.",
    default_value=5,
    recommended_value=5,
    min_value=0,
    max_value=100,
    current_impact="100%: Cores hold maximum clock even at an idle desktop → heat with nothing to show for it",
    recommended_impact="5%: Idle cores drop to 5% and the thermal budget is still there when the match starts",
    effect="Lets idle cores clock down so the thermal budget is intact when a game needs it",
    # A drift guard, so 0.0 rather than an invented saving: on a machine that
    # never had this raised, applying it changes nothing. What it is worth is
    # entirely a function of how wrong the machine was, and "set minimum
    # processor state to 100" is advice this tweak exists to undo.
    impact_scores={"power_watts": 0.0, "stability": "high"},
    category_order=13,
    scope=SettingScope.RECOMMENDED,
)

# === Maximum Processor State ===
POWER_CPU_MAX_STATE = _cpu_power_setting(
    setting_id="power:cpu_max_state",
    guid=CPU_MAX_STATE_SETTING,
    display_name="Maximum Processor State",
    description="Highest clock speed the CPU is allowed to reach. The common advice to set it "
    "to 99 in order to run cooler works by switching off turbo entirely, which costs far more "
    "performance than the heat it saves.",
    default_value=100,
    recommended_value=100,
    min_value=0,
    max_value=100,
    current_impact="Below 100%: Turbo is disabled → every CPU-bound frame is slower, permanently",
    recommended_impact="100%: Full turbo available, so peak frames are not being given away",
    effect="Keeps full turbo available instead of capping the CPU below its rated speed",
    # Also a guard. When it fires the gain is large, but its size is whatever
    # turbo range that particular chip has, which is not ours to state.
    impact_scores={"fps_cpu_bound": 0.0, "stability": "high"},
    category_order=14,
    scope=SettingScope.RECOMMENDED,
)

# === Processor Idle States ===
POWER_CPU_IDLE_DISABLE = _cpu_power_setting(
    setting_id="power:cpu_idle_states",
    guid=CPU_IDLE_DISABLE_SETTING,
    display_name="CPU Idle States",
    description="Whether cores may enter low-power C-states when they have no work. Disabling "
    "them is a widely repeated gaming tweak that produces continuous heat and shortens the "
    "part's life without gaining a single frame.",
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    current_impact="Disabled: No core is ever allowed to rest → continuous heat, no frame rate gained",
    recommended_impact="Enabled: Idle cores rest, so the cooler is not already saturated when a match starts",
    effect="Allows idle cores to enter low-power states instead of running hot around the clock",
    # 0 = "Enable idle" and 1 = "Disable idle" in Windows' own enum, so the
    # display values read the opposite way round from the raw ones. Named for
    # what the user is choosing rather than for the negation Windows stores.
    value_map={0: "enabled", 1: "disabled"},
    apply_value_map={"enabled": 0, "disabled": 1},
    impact_scores={"power_watts": 0.0, "stability": "high"},
    category_order=15,
    scope=SettingScope.RECOMMENDED,
)

# === Processor Performance Time Check Interval ===
POWER_CPU_PERF_CHECK = _cpu_power_setting(
    setting_id="power:cpu_perf_check_interval",
    guid=CPU_PERF_CHECK_SETTING,
    display_name="CPU Load Re-check Interval",
    description="How often Windows looks at processor load to decide whether to change clock "
    "speed. The interval bounds how long a core can sit at the wrong speed after load changes, "
    "in both directions.",
    default_value=30,
    recommended_value=15,
    min_value=1,
    max_value=5000,
    current_impact="30ms: Up to 30ms can pass before clocks react to load appearing or ending",
    recommended_impact="15ms: Windows re-checks twice as often → half the worst-case delay, either way",
    effect="Halves how long the CPU can sit at the wrong clock speed after load changes",
    # The 30 -> 15 arithmetic is exact, and it bounds the *decision* delay rather
    # than measured frame time. Scoring it as a 15 ms latency saving would claim
    # the bound as the effect, so the number stays in the text where it is true
    # and out of the score where it would not be.
    impact_scores={"latency_spike_ms": 0.0, "stability": "high"},
    category_order=16,
    scope=SettingScope.RECOMMENDED,
)

# === Processor Performance Decrease Time ===
POWER_CPU_DECREASE_TIME = _cpu_power_setting(
    setting_id="power:cpu_decrease_time",
    guid=CPU_DECREASE_TIME_SETTING,
    display_name="CPU Scale-Down Delay",
    description="How many consecutive load checks must come back idle before the CPU drops to a "
    "lower clock. At the default of one, a single quiet interval between frames is enough to "
    "start a downshift the next frame has to pay to undo.",
    default_value=1,
    recommended_value=3,
    min_value=1,
    max_value=100,
    current_impact="1 check: One quiet interval drops the clock → the next frame waits for it to come back",
    recommended_impact="3 checks: Clocks hold through short lulls and still fall once the machine is really idle",
    effect="Requires sustained idle before clocking down, so brief lulls do not cost the next frame",
    impact_scores={"latency_spike_ms": 0.0, "stability": "high"},
    category_order=17,
    scope=SettingScope.RECOMMENDED,
)

# === Latency Sensitivity Hint: Unparked Cores ===
POWER_CPU_LATENCY_HINT_UNPARK = _cpu_power_setting(
    setting_id="power:cpu_latency_hint_unpark",
    guid=CPU_LATENCY_HINT_UNPARK_SETTING,
    display_name="Latency-Sensitive Workload Core Unparking",
    description="Share of cores Windows brings back online the moment it detects a workload that "
    "cares about response time. This is what makes idle core parking safe: cores may rest, but a "
    "game gets all of them back at once rather than one at a time.",
    default_value=50,
    recommended_value=100,
    min_value=0,
    max_value=100,
    current_impact="50%: A game wakes half the cores immediately and waits for the rest",
    recommended_impact="100%: Every core is back online the moment a latency-sensitive workload starts",
    effect="Wakes every core at once for latency-sensitive work instead of half of them",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=18,
    scope=SettingScope.RECOMMENDED,
)

# === Latency Sensitivity Hint: Performance ===
POWER_CPU_LATENCY_HINT_PERF = _cpu_power_setting(
    setting_id="power:cpu_latency_hint_perf",
    guid=CPU_LATENCY_HINT_PERF_SETTING,
    display_name="Latency-Sensitive Workload Clock Speed",
    description="Clock speed Windows jumps to when it detects a latency-sensitive workload. "
    "Anything below 100 means a game asking for immediate response gets less than the machine "
    "can give.",
    default_value=99,
    recommended_value=100,
    min_value=0,
    max_value=100,
    current_impact="99%: Latency-sensitive work gets almost, but not quite, full clock speed",
    recommended_impact="100%: A game asking for immediate response gets the whole chip",
    effect="Gives latency-sensitive work full clock speed rather than almost all of it",
    # One percent, and it is here as a guard rather than as a gain — what it
    # catches is a machine where something set it to 50, not the 99 Windows
    # ships. Filed under Complete for that reason.
    impact_scores={"fps_cpu_bound": 0.0, "stability": "high"},
    category_order=19,
    scope=SettingScope.COMPLETE,
)

# === Core Parking Increase Policy ===
POWER_CPU_PARKING_INC_POLICY = _cpu_power_setting(
    setting_id="power:cpu_parking_increase_policy",
    guid=CPU_PARKING_INC_POLICY_SETTING,
    display_name="Core Unparking Policy",
    description="How many parked cores Windows brings back when load rises. Waking all of them "
    "together costs nothing once they are needed and avoids the staircase of one-at-a-time wakes "
    "a loading match produces.",
    choices=("ideal", "single", "all", "one_eighth"),
    default_value="ideal",
    recommended_value="all",
    current_impact="Ideal: Cores come back a few at a time as load builds",
    recommended_impact="All: Every parked core returns in one step when load rises",
    effect="Brings every parked core back in one step instead of a few at a time",
    value_map={0: "ideal", 1: "single", 2: "all", 3: "one_eighth"},
    apply_value_map={"ideal": 0, "single": 1, "all": 2, "one_eighth": 3},
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=20,
    scope=SettingScope.COMPLETE,
)

# === Core Parking Increase Time ===
POWER_CPU_PARKING_INC_TIME = _cpu_power_setting(
    setting_id="power:cpu_parking_increase_time",
    guid=CPU_PARKING_INC_TIME_SETTING,
    display_name="Core Unparking Delay",
    description="How many load checks must pass before a parked core is brought back. The "
    "default of three is three intervals a thread spends waiting for a core that already exists.",
    default_value=3,
    recommended_value=1,
    min_value=1,
    max_value=100,
    current_impact="3 checks: A thread waits three load checks for a core that is already there",
    recommended_impact="1 check: Parked cores return at the first sign of load",
    effect="Returns parked cores at the first load check rather than the third",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=21,
    scope=SettingScope.COMPLETE,
)

# === Processor Performance Increase Time ===
POWER_CPU_INCREASE_TIME = _cpu_power_setting(
    setting_id="power:cpu_increase_time",
    guid=CPU_INCREASE_TIME_SETTING,
    display_name="CPU Scale-Up Delay",
    description="How many consecutive load checks must show work before the CPU clocks up. "
    "Windows already ships the fastest possible value, so this exists to notice when something "
    "else has raised it.",
    default_value=1,
    recommended_value=1,
    min_value=1,
    max_value=100,
    current_impact="Above 1: Clock-up waits for repeated confirmation → load is served slowly at first",
    recommended_impact="1 check: The CPU clocks up at the first check that sees work",
    effect="Keeps clock-up on the first load check instead of waiting for confirmation",
    impact_scores={"latency_spike_ms": 0.0, "stability": "high"},
    category_order=22,
    scope=SettingScope.COMPLETE,
)


POWER_SETTINGS: list[SettingExecutor] = [
    # CPU core parking and scheduling (highest impact)
    POWER_CPU_MIN_PARKING,
    POWER_THROTTLING,
    POWER_CPU_BOOST,
    POWER_CPU_INCREASE_THRESHOLD,
    POWER_CPU_DECREASE_THRESHOLD,
    POWER_CPU_INCREASE_POLICY,
    POWER_CPU_DECREASE_POLICY,
    POWER_CPU_EPP,
    # Idle behaviour: what the machine costs when it is not being asked for
    # anything, which is a thermal-headroom question and therefore a performance
    # one. Several of these are guards rather than changes — see the block above.
    POWER_CPU_MIN_STATE,
    POWER_CPU_MAX_STATE,
    POWER_CPU_IDLE_DISABLE,
    POWER_CPU_PERF_CHECK,
    POWER_CPU_DECREASE_TIME,
    POWER_CPU_INCREASE_TIME,
    POWER_CPU_LATENCY_HINT_UNPARK,
    POWER_CPU_LATENCY_HINT_PERF,
    POWER_CPU_PARKING_INC_POLICY,
    POWER_CPU_PARKING_INC_TIME,
    # I/O latency settings
    USB_SELECTIVE_SUSPEND,
    PCIE_LINK_STATE,
    POWER_DISK_TIMEOUT,
    # Thermal management
    POWER_THERMAL_COOLING,
    # Network power saving
    WLAN_POWER_SAVING,
    # Storage space
    POWER_HIBERNATION,
    # Advisory
    RYZEN_BALANCED_PLAN,
]
