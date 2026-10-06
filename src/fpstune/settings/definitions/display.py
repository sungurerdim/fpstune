"""Display setting definitions: how Windows presents, and what each panel runs at.

Per-monitor mode is one setting per connected monitor, built by
`create_monitor_mode_setting` and registered by `discovery.display`. It replaces
an older pair (`display:{id}:resolution`, `display:{id}:refresh_rate`) whose
discovery pass had been commented out long before the registry refactor removed
it, leaving the fix reachable only as a Hardware-panel button that Home, the bulk
apply and the change history never saw. Detect and apply are Python
(`settings.display_mode`), and every write keeps the button's two guards: the
driver's CDS_TEST first, and a revert unless the user keeps the new mode.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

_DX_PATH = "HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences"


def directx_flag_scripts(flag: str) -> tuple[str, str]:
    """Detect and apply scripts for one ``Name=0|1`` entry in DirectXUserGlobalSettings.

    The value is one REG_SZ of ``;``-terminated entries that Windows itself
    writes as ``SwapEffectUpgradeEnable=1;VRROptimizeEnable=0;``. The entry is
    matched as a whole token: a substring match read ``XSwapEffectUpgradeEnable=1``
    as this flag, and appending to a value that already ended in ``;`` wrote
    ``;;``. Every other entry is kept verbatim, in order.
    """
    token = f"'^\\s*{flag}='"
    read = (
        f"$cur = (Get-ItemProperty -Path '{_DX_PATH}' -Name 'DirectXUserGlobalSettings' "
        "-ErrorAction SilentlyContinue).DirectXUserGlobalSettings; "
    )
    detect = (
        read + f"$t = @(\"$cur\" -split ';' | Where-Object {{ $_ -match {token} }}) | "
        "Select-Object -Last 1; "
        "if ($t -and ($t -split '=', 2)[1].Trim() -eq '1') { 'enabled' } else { 'disabled' }"
    )
    apply = (
        f"if (-not (Test-Path '{_DX_PATH}')) {{ New-Item -Path '{_DX_PATH}' -Force -ErrorAction Stop | Out-Null }}; "
        + read
        + f"$keep = @(\"$cur\" -split ';' | Where-Object {{ $_.Trim() -and $_ -notmatch {token} }}); "
        "$bit = if ('%value%' -eq 'enabled') { '1' } else { '0' }; "
        f"$updated = ((@($keep) + \"{flag}=$bit\") -join ';') + ';'; "
        f"Set-ItemProperty -Path '{_DX_PATH}' -Name 'DirectXUserGlobalSettings' "
        "-Value $updated -Type String -ErrorAction Stop"
    )
    return detect, apply


_FLIP_DETECT, _FLIP_APPLY = directx_flag_scripts("SwapEffectUpgradeEnable")


# === Windowed Games Optimization (Flip-Model Presentation) ===
# Microsoft T1 source: Windows 11 enables flip-model presentation for DX10-DX11
# windowed/borderless games, providing measurable lower frame latency + Auto HDR + VRR.
# Registry: HKCU\SOFTWARE\Microsoft\DirectX\UserGpuPreferences
WINDOWED_FLIP_MODEL = SettingExecutor(
    id="display:windowed_flip_model",
    category=SettingCategory.GPU,
    display_name="Windowed Games Optimization",
    short_name="Windowed game fast-path",
    description="Borderless and windowed games hand frames straight to the display engine instead of through "
    "an extra copy. Off, every windowed frame costs latency and neither Auto HDR nor VRR can "
    "work.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Disabled: Legacy blt-model presentation for windowed games",
    recommended_impact="Enabled: Flip-model → lower frame latency + Auto HDR + VRR support",
    scope=SettingScope.ESSENTIAL,  # High impact on windowed game latency
    category_order=52,  # After refresh rate
    applicable_conditions={"is_windows_11": True},  # Windows 11 only
    effect="Reduces frame latency in windowed/borderless games via modern flip-model presentation",
    impact_scores={"latency_ms": -3.5, "fps": "0%", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=_FLIP_DETECT,
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=_FLIP_APPLY,
    apply_args={},
    apply_value_map={},
)


# === Multi-Plane Overlay (MPO) ===
# 24H2 is 26100, 25H2 is 26200; 23H2 is 22631. From 24H2 on, builds have been
# seen honouring either value depending on the servicing update, so both are
# written there; before 24H2 only the DWM value exists.
_MPO_BOTH_VALUES_BUILD = 26100

_DWM_VALUE = (r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5)
_GRAPHICS_VALUE = (r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "DisableOverlays", 1)


def _mpo_values(build: int) -> tuple[tuple[str, str, int], ...]:
    if build >= _MPO_BOTH_VALUES_BUILD:
        return (_DWM_VALUE, _GRAPHICS_VALUE)
    return (_DWM_VALUE,)


def _mpo_scripts(values: tuple[tuple[str, str, int], ...]) -> tuple[str, str]:
    """Detect and apply scripts over every value this build may honour.

    Disabled means every value is in place; anything less is still MPO on.
    Re-enabling deletes the values rather than zeroing them, because removing
    the override is what restores Windows' own behaviour — a 0 is still one.
    """
    # One `+= ,@(...)` per value: `@(@(a, b, c))` with a single inner array
    # unrolls into a flat three-item array, which a one-value build would hit.
    targets = "$targets = @(); " + "".join(
        f"$targets += ,@('HKLM:\\{path}', '{name}', {on}); " for path, name, on in values
    )
    detect = (
        targets + "$set = @($targets | Where-Object { "
        "(Get-ItemProperty -Path $_[0] -Name $_[1] -ErrorAction SilentlyContinue).($_[1]) -eq $_[2] "
        "}).Count; "
        "if ($set -eq $targets.Count) { 'disabled' } else { 'enabled' }"
    )
    apply = (
        targets + "foreach ($t in $targets) { "
        "if ('%value%' -eq 'disabled') { "
        "if (-not (Test-Path $t[0])) { New-Item -Path $t[0] -Force -ErrorAction Stop | Out-Null }; "
        "Set-ItemProperty -Path $t[0] -Name $t[1] -Value $t[2] -Type DWord -Force -ErrorAction Stop "
        # A value that is not there is the goal; one that refuses to go is named.
        "} elseif (Get-ItemProperty -Path $t[0] -Name $t[1] -ErrorAction SilentlyContinue) { "
        "Remove-ItemProperty -Path $t[0] -Name $t[1] -ErrorAction Stop } }"
    )
    return detect, apply


def create_mpo_setting(build: int) -> SettingExecutor:
    """Build the MPO switch for the Windows version actually running.

    Which registry value disables MPO is a property of the Windows build, and
    writing the wrong one is silent: the value lands, detection reads it back and
    reports success, and MPO stays on. fpstune once wrote the GraphicsDrivers
    value unconditionally, so on 23H2 the tweak did nothing and said it had
    worked. Neither value is documented by Microsoft.

    Not offered on a VRR panel: MPO is part of how a windowed game's frames
    reach a G-Sync/FreeSync display directly, and switching it off has been
    reported to stop VRR engaging — the one place the tweak costs more than the
    flicker it fixes.
    """
    values = _mpo_values(build)
    where = " and ".join(f"{path.rsplit(chr(92), 1)[-1]}\\{name}" for path, name, _ in values)
    detect, apply = _mpo_scripts(values)

    return SettingExecutor(
        id="display:mpo_disable",
        category=SettingCategory.GPU,
        display_name="Multi-Plane Overlay (MPO)",
        short_name="Multi-plane overlay",
        description="Whether the GPU's display engine composites windows in hardware. It can "
        f"flicker and mis-pace frames on mixed-refresh multi-monitor setups ({where}).",
        value_type=SettingValueType.CHOICE,
        choices=("enabled", "disabled"),
        default_value="enabled",
        recommended_value="disabled",
        requires_reboot=True,
        # Undocumented by Microsoft, absent from NVIDIA's current instructions,
        # and changes between Windows builds: experimental, so C1's promotion
        # rule requires advanced + a warning.
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "Undocumented, and the value that works changes between Windows builds. Only offered "
            "without a G-Sync/FreeSync display, because on one it can stop variable refresh rate "
            "from engaging."
        ),
        sources=[
            "https://nvidia.custhelp.com/app/answers/detail/a_id/5157/~/what-is-multi-plane-overlay-%28mpo%29-in-windows-11",
            "https://github.com/RedDot-3ND7355/MPO-GPU-FIX/issues/26",
            "https://forums.guru3d.com/threads/disabling-mpo-multiplane-overlay-in-2025.455222/",
        ],
        current_impact="Enabled: Hardware plane compositing → flicker and frame-pacing issues on some setups",
        recommended_impact="Disabled: DWM composites instead → steadier frame delivery where MPO misbehaves",
        scope=SettingScope.COMPLETE,  # experimental risk is offered, never assumed (C2/#30)
        category_order=5,
        effect="Stops the display engine compositing in hardware where that misbehaves",
        # This fixes a defect when the defect is present and does nothing when it
        # is not — a range would imply it always pays.
        impact_scores={
            "frame_time_consistency": "fixes flicker/stutter when present",
            "latency_ms": 0.0,
        },
        applicable_conditions={"requires_vrr": False},
        detect_type=DetectType.POWERSHELL,
        detect_command=detect,
        detect_args={},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=apply,
        apply_args={},
        apply_value_map={},
    )


# Static fallback for the registry list; discovery re-registers it from the
# detected build. Both values is the safer default for a machine whose version
# could not be read: the extra one is a value nothing reads.
MPO_DISABLE = create_mpo_setting(_MPO_BOTH_VALUES_BUILD)


# Static list - Flip-Model is static, display resolution/refresh are dynamic
DISPLAY_SETTINGS: list[SettingExecutor] = [
    WINDOWED_FLIP_MODEL,
    MPO_DISABLE,
]


def create_monitor_mode_setting(key: str, subject: str, *, primary: bool) -> SettingExecutor:
    """One monitor's mode: its own native resolution at its own maximum refresh.

    The primary monitor's is RECOMMENDED — it is where the game runs. Every other
    monitor's is COMPLETE: optional, offered with what it fixes, never assumed.
    The numbers in the copy are this panel's own (C9); the row explains the
    current state from the detect's finding, in the user's language.
    """
    from fpstune.settings.display_mode import NATIVE, NOT_AVAILABLE, NOT_NATIVE

    where = "the main monitor, where games run" if primary else "a secondary monitor"
    return SettingExecutor(
        id=f"display:{key}:mode",
        category=SettingCategory.GPU,
        display_name=f"Display Mode ({subject})",
        short_name=f"Native resolution and refresh ({subject})",
        subject=subject,
        description=(
            f"Whether {where} runs at its own native resolution and its own maximum "
            "refresh rate. Below either, the image is scaled or every frame waits longer "
            "on screen than the panel needs."
        ),
        value_type=SettingValueType.CHOICE,
        choices=(NATIVE, NOT_NATIVE),
        # Windows labels a panel's native resolution as its recommended one, so
        # "Windows default" is the same native mode apply writes.
        default_value=NATIVE,
        recommended_value=NATIVE,
        requires_reboot=False,
        current_impact="Below native: a scaled image or a lower refresh than the panel can show",
        recommended_impact="Native: every pixel the panel has, at the fastest refresh it supports",
        scope=SettingScope.RECOMMENDED if primary else SettingScope.COMPLETE,
        category_order=50,
        effect="Sets the monitor to its native resolution and maximum refresh rate",
        # A guard: the native mode is this panel's own default, so keeping it claims no
        # latency saved. The frame interval a lower refresh would add is the opposite
        # action's cost, derived from this panel's two readings but not a gain to claim.
        impact_scores={"latency_ms": 0.0, "target_visibility": "preserved"},
        detect_type=DetectType.POWERSHELL,
        detect_command="display_mode_status",
        detect_args={"monitor": key},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command="display_mode_native",
        apply_args={"monitor": key, "setting_id": f"display:{key}:mode"},
        apply_value_map={},
        value_hints={NATIVE: "native", NOT_NATIVE: "below native", NOT_AVAILABLE: ""},
    )
