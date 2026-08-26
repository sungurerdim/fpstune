"""Display setting definitions: how Windows presents, not what the panel runs at.

Per-monitor resolution and refresh rate are *not* here. Those two settings used
to be built by factories in this file, and the discovery pass that called them
was commented out long before the registry refactor removed the method
entirely — so `display:{id}:resolution` and `display:{id}:refresh_rate` had
stopped reaching the registry while the factories still looked live. The
capability itself did not disappear with them: setting a panel back to its
native mode is `POST /display/{index}/auto`, which `MonitorCard` calls from the
Hardware panel. The factories were the dead half of a working feature.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# === Windowed Games Optimization (Flip-Model Presentation) ===
# Microsoft T1 source: Windows 11 enables flip-model presentation for DX10-DX11
# windowed/borderless games, providing measurable lower frame latency + Auto HDR + VRR.
# Registry: HKCU\SOFTWARE\Microsoft\DirectX\UserGpuPreferences
WINDOWED_FLIP_MODEL = SettingExecutor(
    id="display:windowed_flip_model",
    category=SettingCategory.GPU,
    display_name="Windowed Games Optimization",
    description="Enables flip-model presentation for DX10-DX11 windowed/borderless games. Provides lower latency + enables Auto HDR + VRR.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Disabled: Legacy blt-model presentation for windowed games",
    recommended_impact="Enabled: Flip-model → 5-10ms lower frame latency + Auto HDR + VRR support",
    scope=SettingScope.ESSENTIAL,  # High impact on windowed game latency
    category_order=52,  # After refresh rate
    applicable_conditions={"is_windows_11": True},  # Windows 11 only
    effect="Reduces frame latency in windowed/borderless games via modern flip-model presentation",
    impact_scores={"latency_ms": -3.5, "fps": "0%", "stability": "high"},
    # Detection - PowerShell to parse DirectXUserGlobalSettings semicolon-separated string
    # Registry value is REG_SZ like "SwapEffectUpgradeEnable=1;AutoHDREnable=1;VRROptimizeEnable=1"
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$val = Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences' "
        "-Name 'DirectXUserGlobalSettings' -ErrorAction SilentlyContinue; "
        "if ($val -and $val.DirectXUserGlobalSettings -like '*SwapEffectUpgradeEnable=1*') { 'enabled' } "
        "elseif ($val -and $val.DirectXUserGlobalSettings -like '*SwapEffectUpgradeEnable=0*') { 'disabled' } "
        "else { 'disabled' }"
    ),
    detect_args={},
    value_map={},  # PowerShell returns choice names directly
    # Apply - PowerShell to set/modify DirectXUserGlobalSettings string (preserves other keys)
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$path = 'HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences'; "
        "$name = 'DirectXUserGlobalSettings'; "
        "if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }; "
        "$current = (Get-ItemProperty -Path $path -Name $name -ErrorAction SilentlyContinue).$name; "
        "$newVal = if ('%value%' -eq 'enabled') { '1' } else { '0' }; "
        "if ($current -match 'SwapEffectUpgradeEnable=\\d') { "
        "$updated = $current -replace 'SwapEffectUpgradeEnable=\\d', \"SwapEffectUpgradeEnable=$newVal\"; "
        "} elseif ($current) { "
        '$updated = "$current;SwapEffectUpgradeEnable=$newVal"; '
        "} else { "
        '$updated = "SwapEffectUpgradeEnable=$newVal"; '
        "}; "
        "Set-ItemProperty -Path $path -Name $name -Value $updated -Type String"
    ),
    apply_args={},
    apply_value_map={},
)


# === Multi-Plane Overlay (MPO) ===
# The build at which the DWM keys stop being honoured and the GraphicsDrivers
# value takes over. 25H2 is 26200; 24H2 is 26100; 23H2 is 22631.
_MPO_GRAPHICSDRIVERS_BUILD = 26200


def create_mpo_setting(build: int) -> SettingExecutor:
    """Build the MPO switch for the Windows version actually running.

    Which registry value disables MPO is a property of the Windows build, and
    writing the wrong one is silent: the value lands, detection reads it back and
    reports success, and MPO stays on. fpstune wrote the GraphicsDrivers value
    unconditionally, so on 23H2 and 24H2 the tweak did nothing and said it had
    worked.

    - 25H2 (26200+): the DWM values are ignored; ``GraphicsDrivers\\DisableOverlays``
      is the value that takes effect.
    - Earlier builds: ``Dwm\\OverlayTestMode = 5``.

    Neither value is documented by Microsoft. Reverting deletes the value rather
    than zeroing it, because removing the override is what restores Windows'
    own behaviour — a 0 is still an override.
    """
    if build >= _MPO_GRAPHICSDRIVERS_BUILD:
        path, name, on_value = (
            r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
            "DisableOverlays",
            1,
        )
        where = "GraphicsDrivers\\DisableOverlays (Windows 25H2 and later)"
    else:
        path, name, on_value = r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5
        where = "Dwm\\OverlayTestMode (Windows 24H2 and earlier)"

    return SettingExecutor(
        id="display:mpo_disable",
        category=SettingCategory.GPU,
        display_name="Multi-Plane Overlay (MPO)",
        description="Whether the GPU's display engine composites windows in hardware. It can "
        f"cause flicker and frame-pacing problems, most often on multi-monitor setups with mixed "
        f"refresh rates. Written to {where}.",
        value_type=SettingValueType.CHOICE,
        choices=("enabled", "disabled"),
        default_value="enabled",
        recommended_value="disabled",
        requires_reboot=True,
        # Demoted from "proven". The value is undocumented by Microsoft, absent
        # from NVIDIA's current instructions, and changes between Windows
        # builds — that is the definition of experimental, whatever the blogs
        # quoting a 20-40% figure say. C1's promotion rule then requires
        # advanced + a warning.
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "Undocumented, and the value that works changes between Windows builds. At least one "
            "report has it breaking variable refresh rate; on a G-Sync/FreeSync display, verify "
            "VRR still engages after the reboot and revert this if it does not."
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
        # The old "+0-15%" and "-1.5 ms" came from a single blog post. The honest
        # statement is that this fixes a defect when the defect is present and
        # does nothing when it is not — a range implies it always pays.
        impact_scores={
            "frame_time_consistency": "fixes flicker/stutter when present",
            "latency_ms": 0.0,
        },
        detect_type=DetectType.REGISTRY,
        detect_command="",
        detect_args={"path": path, "name": name, "hive": "HKLM"},
        value_map={
            on_value: "disabled",
            str(on_value): "disabled",
            0: "enabled",
            "0": "enabled",
            None: "enabled",
        },
        apply_type=DetectType.REGISTRY,
        apply_command="",
        apply_args={"path": path, "name": name, "hive": "HKLM", "type": "REG_DWORD"},
        # None deletes the value: removing the override is what hands the
        # decision back to Windows, where a 0 is still an override.
        apply_value_map={"disabled": on_value, "enabled": None},
    )


# Static fallback for the registry list; discovery re-registers it from the
# detected build. 25H2 is the current shipping build, so it is the safer default
# for a machine whose version could not be read.
MPO_DISABLE = create_mpo_setting(_MPO_GRAPHICSDRIVERS_BUILD)


# Static list - Flip-Model is static, display resolution/refresh are dynamic
DISPLAY_SETTINGS: list[SettingExecutor] = [
    WINDOWED_FLIP_MODEL,
    MPO_DISABLE,
]
