"""Timer setting definitions.

One timer *tweak* survives: the global timer-resolution registry key. Three more rows
are guards over the boot configuration (consequences 2 and 6 of the product goal).

HPET (``useplatformclock``), platform tick (``useplatformtick``), dynamic tick
(``disabledynamictick``) and TSC sync policy were removed as tweaks in the 2026-08
audit. All four recommended the Windows default, so applying them did nothing, while
the alternative choice they exposed was actively harmful. Machines that already carry
a forced value keep carrying it, so three of them came back as guards whose only
written state is Windows' own (the element absent): ``timer:boot_platform_clock``,
``timer:boot_dynamic_tick`` and ``timer:boot_tsc_sync_policy``. They are three rows, not one:
each is a different boot element on a different subsystem (clock source, tick
delivery, cross-core TSC alignment), and C8 forbids bundling unrelated subsystems.
``useplatformtick`` has no guard: no source the evidence names recommends touching it.

Why the forcing versions stay retired:

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
    description="Whether a program asking for a finer timer gets it for the whole system or only for itself. "
    "System-wide keeps frame pacing even when the game is not the one that asked.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=True,
    evidence_level="proven",
    sources=["https://forums.blurbusters.com/viewtopic.php?t=13842"],
    current_impact="Disabled: Timer resolution is per-process (15.6ms default for others)",
    recommended_impact="Enabled: All processes benefit from lowest requested resolution",
    scope=SettingScope.ESSENTIAL,  # High impact on system-wide timing
    category_order=2,  # Second most important timer setting
    # The registry key is honoured on Windows 11 only.
    applicable_conditions={"is_windows_11": True},
    effect="Enables system-wide timer resolution for smoother gameplay",
    impact_scores={"latency_ms": -0.5, "power_watts": "+1-3", "stability": "high"},
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

# === Boot-configuration guards ===
# The boot configuration store is read from the registry hive Windows mounts at
# HKLM\BCD00000000, never from the boot editor's printed output: that prints its element
# names and its Yes/No in the system language, and the hive is numbers. Each boot object
# is a subkey of Objects named by its GUID; `Description\Type` says what kind it is
# (0x10200003 a Windows boot loader, 0x20200003 an inheritable settings group a loader
# takes values from), and `Elements\<8 hex digits>\Element` holds one value as bytes: one
# byte for a boolean, eight for an integer. An element that is absent is Windows' own
# behaviour. `{current}` and `{default}` are aliases the boot editor resolves and name no
# key, so a guard looks at every entry that could boot and the groups they inherit from,
# and removes the value from each one that carries it. The location is two arguments
# (`root`, `store`) so a test can run the shipped script over a copy of the tree.
_BCD_ENTRY_TYPES = f"{0x10200003}, {0x20200003}"  # a Windows boot loader, a group it inherits
_BCD_STORE_ARGS = {"root": "LocalMachine", "store": "BCD00000000\\Objects"}


def _bcd_walk(element: str, act: str) -> str:
    """PowerShell that visits each boot entry carrying a non-zero `element`.

    `act` runs once per such entry with its GUID in `$n`. A store that cannot be read
    throws, which is "could not read" and never "not set": the two must not look alike.
    """
    return (
        "$root = [Microsoft.Win32.Registry]::%root%.OpenSubKey('%store%'); "
        "if ($null -eq $root) { throw 'The boot configuration store is not readable.' }; "
        "foreach ($n in $root.GetSubKeyNames()) { "
        "$d = $root.OpenSubKey($n + '\\Description'); if ($null -eq $d) { continue }; "
        f"if (@({_BCD_ENTRY_TYPES}) -notcontains $d.GetValue('Type')) {{ continue }}; "
        f"$k = $root.OpenSubKey($n + '\\Elements\\{element}'); "
        "if ($null -eq $k) { continue }; "
        "$b = [byte[]]$k.GetValue('Element'); "
        f"if (@($b | Where-Object {{ $_ -ne 0 }}).Count -gt 0) {{ {act} }} }}"
    )


def _bcd_detect(element: str) -> str:
    return (
        "$changed = $false; "
        + _bcd_walk(element, "$changed = $true")
        + "; if ($changed) { 'changed' } else { 'stock' }"
    )


def _bcd_restore(element: str, name: str) -> str:
    walk = _bcd_walk(
        element,
        f"$out = bcdedit /deletevalue $n {name} 2>&1; "
        "if ($LASTEXITCODE -ne 0) { $failed += ($n + ': ' + ($out | Out-String).Trim()) }",
    )
    return (
        "try { $failed = @(); "
        + walk
        + "; if ($failed.Count -gt 0) { throw ('Windows refused: ' + ($failed -join ' | ')) }; "
        "'ok' } catch { 'error:' + ($_.Exception.Message -replace '\\s+', ' ') }"
    )


def _boot_guard(
    *,
    setting_id: str,
    display_name: str,
    short_name: str,
    description: str,
    current_impact: str,
    recommended_impact: str,
    effect: str,
    element: str,
    name: str,
    order: int,
) -> SettingExecutor:
    """One guard over one boot element: stock is absent, `changed` is another tool's drift."""
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.TIMER,
        display_name=display_name,
        short_name=short_name,
        description=description,
        value_type=SettingValueType.CHOICE,
        choices=("stock", "changed"),
        default_value="stock",
        recommended_value="stock",
        # The boot configuration is read once, at start-up.
        requires_reboot=True,
        evidence_level="likely",
        sources=[
            "https://github.com/valleyofdoom/PC-Tuning/blob/main/docs/research.md",
            "https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/bcdedit--set",
        ],
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        # Not ESSENTIAL: the conservative preset stays small, and this row edits the boot
        # configuration, needs a reboot and does nothing on a machine no other tool touched.
        scope=SettingScope.RECOMMENDED,
        category_order=order,
        effect=effect,
        # A guard puts a stock state back: it claims no gain, because the gain belongs
        # to the opposite action's row.
        impact_scores={"latency_ms": 0.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=_bcd_detect(element),
        detect_args=dict(_BCD_STORE_ARGS),
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=_bcd_restore(element, name),
        apply_args=dict(_BCD_STORE_ARGS),
        apply_value_map={},
        # The script removes the value whatever it is asked for, so "changed" is
        # something to detect, never something to restore.
        unwritable_values=("changed",),
    )


PLATFORM_CLOCK = _boot_guard(
    setting_id="timer:boot_platform_clock",
    display_name="Forced HPET Clock Source",
    short_name="Forced HPET clock",
    description="Whether the boot configuration forces Windows to read time from the HPET chip. "
    "Windows picks the clock itself; forcing HPET makes every time read slower.",
    current_impact="Changed: every time read goes to the slow HPET chip",
    recommended_impact="Windows default: Windows picks the fastest clock the machine has",
    effect="Removes a forced HPET clock source from the boot configuration",
    element="260000a2",  # BcdOSLoaderBoolean_UsePlatformClock
    name="useplatformclock",
    order=2,
)

DYNAMIC_TICK = _boot_guard(
    setting_id="timer:boot_dynamic_tick",
    display_name="Disabled Dynamic Tick",
    short_name="Forced constant tick",
    description="Whether the boot configuration stops Windows from pausing its timer tick when idle. "
    "Forcing it on keeps cores awake and can disturb mouse feel and frame timing.",
    current_impact="Changed: the timer tick never pauses, so idle cores stay busy",
    recommended_impact="Windows default: the tick pauses when idle, so cores can rest",
    effect="Removes a forced constant timer tick from the boot configuration",
    element="260000a5",  # BcdOSLoaderBoolean_DisableDynamicTick
    name="disabledynamictick",
    order=3,
)

TSC_SYNC_POLICY = _boot_guard(
    setting_id="timer:boot_tsc_sync_policy",
    display_name="TSC Sync Policy",
    short_name="Forced TSC sync policy",
    description="Whether the boot configuration overrides how Windows aligns each core's time counter. "
    "Windows' own choice is the tested one; forcing legacy or enhanced has cost stability.",
    current_impact="Changed: the core time counters are aligned by a forced policy",
    recommended_impact="Windows default: Windows aligns the counters by its own policy",
    effect="Removes a forced TSC sync policy from the boot configuration",
    element="250000a6",  # BcdOSLoaderInteger_TscSyncPolicy
    name="tscsyncpolicy",
    order=4,
)

# All timer settings
TIMER_SETTINGS: list[SettingExecutor] = [
    GLOBAL_TIMER_RESOLUTION,
    PLATFORM_CLOCK,
    DYNAMIC_TICK,
    TSC_SYNC_POLICY,
]
