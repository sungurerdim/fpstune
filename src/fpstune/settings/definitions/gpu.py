"""GPU setting definitions.

Contains settings for NVIDIA and AMD GPUs.
These settings use the nv_profile executor for NVIDIA DRS settings.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)
from fpstune.settings.performance_headroom import MIN_FRAME_CAP, frame_cap_for_refresh

# =============================================================================
# NVIDIA GPU Settings
# =============================================================================
# Note: NVIDIA settings are applied via nvidiaProfileInspector (DRS)
# Detection reads from saved profile or returns None (unknown)

NVIDIA_LOW_LATENCY = SettingExecutor(
    id="gpu-nvidia:low_latency",
    category=SettingCategory.GPU,
    display_name="Low Latency Mode",
    short_name="Low latency mode",
    description="NVIDIA Reflex / Ultra Low Latency mode. Controls pre-rendered frames.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on", "ultra"),
    default_value="off",
    recommended_value="on",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.nvidia.com/en-us/geforce/news/reflex-low-latency-platform/",
        "https://www.pcworld.com/article/393646/tested-how-nvidia-reflex-can-make-you-a-better-esports-gamer.html",
    ],
    current_impact="Off: GPU pre-renders 2-3 frames → 33-50ms input delay",
    recommended_impact="On: 1 frame buffer → 15-20% lower input lag, safe for all games",
    # The one anti-cheat fact this product knows, carried where the user
    # reads it rather than in a checker nothing called (H8): 'ultra' hooks
    # deeper into the driver than some anti-cheat likes; 'on' — the
    # recommended value — is safe everywhere.
    risk_warning=(
        "The 'ultra' tier may conflict with some anti-cheat software "
        "(BattlEye FAQ); the recommended 'on' is safe in every game."
    ),
    scope=SettingScope.ESSENTIAL,  # High impact on input latency
    category_order=1,  # Primary latency setting
    effect="Reduces GPU pre-rendered frames for lower input delay",
    impact_scores={"fps": "-1-2%", "latency_ms": -8, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    # Detection via NVIDIA Profile cache
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "low_latency"},
    value_map={},
    # Apply via NVIDIA Profile Inspector
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "low_latency"},
    apply_value_map={},
)

NVIDIA_POWER_MODE = SettingExecutor(
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    id="gpu-nvidia:power_mode",
    category=SettingCategory.GPU,
    display_name="Power Management Mode",
    short_name="GPU power mode",
    description="Decides when the GPU is allowed to leave its highest clock state. Optimal "
    "already runs full clocks whenever a game is running, so forcing maximum only changes what "
    "the card does at an idle desktop.",
    value_type=SettingValueType.CHOICE,
    choices=("optimal", "adaptive", "maximum"),
    default_value="optimal",
    # "Prefer maximum performance" is one of the most repeated NVIDIA tweaks
    # there is, and this setting exists mainly to undo it. Under load the card
    # boosts to its top state either way — that is what boost does — so what the
    # setting actually decides is whether it *also* holds that state through the
    # desktop, the browser and the launcher. The frame rate is identical and the
    # card spends the whole session hot, which is the one thing that does reach
    # the match: a GPU already at its thermal limit throttles sooner in it.
    #
    # So recommended equals default here on purpose. Same shape as
    # power:cpu_min_state — full speed when it is wanted, nothing when it is not.
    recommended_value="optimal",
    requires_reboot=False,
    current_impact="Maximum: The card holds top clocks at an idle desktop → heat all session, no extra frames",
    recommended_impact="Optimal: Full clocks under load, and a card that is not already hot when the match starts",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for GPU performance
    category_order=3,  # Power management
    effect="Keeps full clocks under load without holding them through an idle desktop",
    # A drift guard, so 0.0: on a card nobody forced to maximum this changes
    # nothing, and what it is worth otherwise depends entirely on that card's
    # idle draw. power_watts is what carries the gain, which is why this is a
    # heat setting and not a frame-rate one.
    impact_scores={"fps": "0%", "power_watts": 0.0, "stability": "high"},
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "power_mode"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "power_mode"},
    apply_value_map={},
)

NVIDIA_THREADED_OPT = SettingExecutor(
    id="gpu-nvidia:threaded_opt",
    category=SettingCategory.GPU,
    display_name="Threaded Optimization",
    short_name="Driver multi-threading",
    description="Whether the driver spreads its own work across threads. Auto lets the driver decide; forcing "
    "it on can stutter in OpenGL games.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on", "auto"),
    default_value="auto",
    recommended_value="auto",
    requires_reboot=False,
    current_impact="Auto: Driver decides threading per-application (safest)",
    recommended_impact="Auto: Driver optimizes per-game → no stutter risk, optimal threading",
    scope=SettingScope.COMPLETE,  # Marginal benefit, risk of stutter
    category_order=4,  # Multi-threading optimization
    effect="Lets NVIDIA driver choose optimal threading per application",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "threaded_opt"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "threaded_opt"},
    apply_value_map={},
)


def create_nvidia_vsync_setting(vrr_available: bool) -> SettingExecutor:
    """Build the driver V-Sync setting, whose correct value depends on the panel.

    The "V-Sync costs 8-16 ms" figure is real, but only on a fixed-refresh
    display. On a VRR panel the frame cap (gpu/MW3 both use refresh - 3) keeps
    the frame rate inside the G-Sync window, where G-Sync governs presentation
    and V-Sync never engages — so it costs nothing and serves purely as the
    safety net for the moments the cap is overshot. Turning it off there buys no
    latency and reintroduces tearing above the refresh rate.

    fpstune already builds that exact configuration (vrr_mode "on" plus a
    refresh - 3 cap) and then recommended the one setting that undoes it, which
    is why this is derived rather than a constant.
    """
    if vrr_available:
        return SettingExecutor(
            id="gpu-nvidia:vsync",
            category=SettingCategory.GPU,
            display_name="Vertical Sync",
            short_name="V-Sync",
            description="Frame synchronisation in the driver. With a VRR panel and a frame cap "
            "below the refresh rate, V-Sync never engages during play and acts only as the "
            "safety net that keeps tearing away if the cap is briefly overshot.",
            value_type=SettingValueType.CHOICE,
            choices=("off", "on", "adaptive"),
            default_value="on",
            recommended_value="on",
            requires_reboot=False,
            current_impact="Off: Tearing returns whenever the frame rate leaves the G-Sync window",
            recommended_impact="On: Tear-free inside and above the VRR range, with no added latency under the cap",
            scope=SettingScope.ESSENTIAL,
            category_order=2,
            effect="Completes the VRR configuration — tear-free without the latency cost",
            # latency_ms is 0.0 and that is the point: under the frame cap V-Sync
            # is never reached, so it neither adds nor removes latency here. The
            # -10 belongs to the fixed-refresh branch below.
            impact_scores={"latency_ms": 0.0, "stability": "high"},
            applicable_conditions={"gpu_vendor": "nvidia", "requires_vrr": True},
            detect_type=DetectType.NVPROFILE,
            detect_command="",
            detect_args={"setting": "vsync"},
            value_map={},
            apply_type=DetectType.NVPROFILE,
            apply_command="",
            apply_args={"setting": "vsync"},
            apply_value_map={},
        )

    return SettingExecutor(
        id="gpu-nvidia:vsync",
        category=SettingCategory.GPU,
        display_name="Vertical Sync",
        short_name="V-Sync",
        description="Frame synchronisation in the driver. On a fixed-refresh panel V-Sync holds "
        "finished frames back until the next refresh, which is a direct addition to input lag.",
        value_type=SettingValueType.CHOICE,
        choices=("off", "on", "adaptive"),
        default_value="on",
        recommended_value="off",
        requires_reboot=False,
        current_impact="On: Frames held for the next refresh → 8-16 ms extra input lag",
        recommended_impact="Off: Frames presented as soon as they are ready → minimum input lag",
        scope=SettingScope.ESSENTIAL,
        category_order=2,
        effect="Disables frame sync to monitor refresh for minimum latency",
        impact_scores={
            "fps": "+0-5%",
            "fps_gpu_bound": "+0-3%",
            "latency_ms": -10,
            "stability": "high",
        },
        applicable_conditions={"gpu_vendor": "nvidia"},
        detect_type=DetectType.NVPROFILE,
        detect_command="",
        detect_args={"setting": "vsync"},
        value_map={},
        apply_type=DetectType.NVPROFILE,
        apply_command="",
        apply_args={"setting": "vsync"},
        apply_value_map={},
    )


# Static fallback for the registry's own list. Discovery re-registers the VRR
# variant over this one when a VRR panel is found; if monitor detection fails we
# are left recommending "off", which costs tearing rather than latency — the safe
# direction to be wrong in.
NVIDIA_VSYNC = create_nvidia_vsync_setting(vrr_available=False)

NVIDIA_SHADER_CACHE = SettingExecutor(
    id="gpu-nvidia:shader_cache",
    category=SettingCategory.GPU,
    display_name="Shader Cache",
    short_name="Shader cache",
    description="Saves compiled shaders to disk. Speeds up game loading.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on"),
    default_value="on",
    recommended_value="on",
    requires_reboot=False,
    current_impact="Off: Shaders recompile on every game launch",
    recommended_impact="On: Shaders cached → fast startup, reduced stutter",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for stutter reduction
    category_order=5,  # Stutter reduction
    effect="Caches compiled shaders for faster startup and reduced stutter",
    impact_scores={"fps": "0%", "stutter_reduction": "high", "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "shader_cache"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "shader_cache"},
    apply_value_map={},
)

NVIDIA_TEXTURE_QUALITY = SettingExecutor(
    id="gpu-nvidia:texture_quality",
    category=SettingCategory.GPU,
    display_name="Texture Filtering Quality",
    short_name="Texture filtering quality",
    description="Texture filtering quality. Quality is visually identical to High Quality in most games.",
    value_type=SettingValueType.CHOICE,
    choices=("high_quality", "quality", "performance", "high_performance"),
    default_value="quality",
    recommended_value="quality",
    requires_reboot=False,
    current_impact="Quality: Standard filtering, visually identical to High Quality",
    recommended_impact="Quality: Best balance of visual quality and performance",
    scope=SettingScope.COMPLETE,  # Marginal visual/perf difference
    category_order=7,  # Visual quality
    effect="Standard texture filtering quality (no visual compromise)",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "texture_quality"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "texture_quality"},
    apply_value_map={},
)


def create_nvidia_fps_limiter_setting(vrr_available: bool, max_hz: int = 0) -> SettingExecutor:
    """Build the driver frame cap, whose correct value comes from the panel.

    On a VRR panel the cap is the third of the three settings that make up the
    documented low-latency configuration: VRR on, driver V-Sync on, and a cap a
    few frames below the refresh rate. Without the cap the frame rate leaves the
    G-Sync window whenever the GPU can exceed the panel, V-Sync engages, and the
    latency the other two were chosen to avoid arrives anyway.

    Hz minus three is the margin Blur Busters' G-SYNC 101 measurements settle
    on, and it is the same rule the MW3 in-game cap already derives from, so the
    driver cap and the game cap cannot disagree.

    On a fixed-refresh panel there is no window to stay inside, so a driver cap
    only lowers the ceiling — which the project's own rule forbids — and the
    honest recommendation is no cap at all.
    """
    if vrr_available and max_hz > MIN_FRAME_CAP:
        target = frame_cap_for_refresh(max_hz)
        return SettingExecutor(
            id="gpu-nvidia:fps_limit",
            category=SettingCategory.GPU,
            display_name="Frame Rate Limiter",
            short_name="Frame rate cap",
            description=f"Driver-level frame cap. Held just below this panel's {max_hz} Hz so "
            "the frame rate stays inside the G-Sync window, where the display governs "
            "presentation and V-Sync never engages.",
            value_type=SettingValueType.INT,
            choices=(),
            # Derived rather than stock, so default equals recommended and the
            # setting acts as a drift guard: a cap left behind by another tool at
            # some other panel's rate reads as a disagreement and gets corrected.
            default_value=target,
            recommended_value=target,
            min_value=30,
            max_value=1000,
            requires_reboot=False,
            evidence_level="proven",
            sources=[
                "https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/",
            ],
            current_impact=f"Uncapped: Above {max_hz} FPS the G-Sync window is left and V-Sync "
            "latency returns",
            recommended_impact=f"{target}: Frame rate stays inside the VRR window with the "
            "panel fully used",
            scope=SettingScope.RECOMMENDED,
            category_order=8,  # FPS control
            effect=f"Caps frames just under the panel's {max_hz} Hz to keep VRR engaged",
            # 0.0 rather than a negative number, and for the same reason the VRR
            # V-Sync variant carries 0.0: under the cap V-Sync is never reached,
            # so what the cap buys is the absence of the spike that appears when
            # the window is left, not a steady latency saving to claim credit for.
            impact_scores={
                "fps": f"ceiling {target}",
                "latency_spike_ms": 0.0,
                "stability": "high",
            },
            applicable_conditions={"gpu_vendor": "nvidia", "requires_vrr": True},
            detect_type=DetectType.NVPROFILE,
            detect_command="",
            detect_args={"setting": "fps_limit"},
            value_map={},
            apply_type=DetectType.NVPROFILE,
            apply_command="",
            apply_args={"setting": "fps_limit"},
            apply_value_map={},
        )

    return SettingExecutor(
        id="gpu-nvidia:fps_limit",
        category=SettingCategory.GPU,
        display_name="Frame Rate Limiter",
        short_name="Frame rate cap",
        description="Driver-level frame cap. On a fixed-refresh panel there is no variable "
        "refresh window to stay inside, so a cap here only removes frames the machine was "
        "able to produce.",
        value_type=SettingValueType.INT,
        choices=(),
        default_value=0,
        recommended_value=0,
        min_value=0,
        max_value=1000,
        requires_reboot=False,
        evidence_level="proven",
        current_impact="Any limit: Frames the GPU already rendered are discarded → lower ceiling",
        recommended_impact="0: No driver cap, so the machine reaches whatever rate it can",
        scope=SettingScope.RECOMMENDED,
        category_order=8,  # FPS control
        effect="Removes a driver frame cap so the ceiling is the machine's own",
        impact_scores={"fps": "no ceiling", "latency_spike_ms": 0.0, "stability": "high"},
        applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
        detect_type=DetectType.NVPROFILE,
        detect_command="",
        detect_args={"setting": "fps_limit"},
        value_map={},
        apply_type=DetectType.NVPROFILE,
        apply_command="",
        apply_args={"setting": "fps_limit"},
        apply_value_map={},
    )


# Static fallback, same arrangement as NVIDIA_VSYNC above: discovery re-registers
# the derived variant once a VRR panel and its refresh rate are known. Being left
# with "no cap" when the monitor cannot be read costs nothing the machine had.
NVIDIA_FPS_LIMITER = create_nvidia_fps_limiter_setting(vrr_available=False)

NVIDIA_VRR_MODE = SettingExecutor(
    id="gpu-nvidia:vrr_mode",
    category=SettingCategory.GPU,
    display_name="G-Sync / VRR Mode",
    short_name="G-Sync",
    description="Variable Refresh Rate mode, mirroring NVIDIA Control Panel's G-SYNC scope. "
    "'on' covers windowed and borderless as well as exclusive fullscreen. Requires a "
    "G-Sync/FreeSync compatible monitor.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on", "fullscreen"),
    default_value="off",
    # 'on' rather than 'fullscreen', and not interchangeable with it. 'fullscreen' is
    # NVCP's "Enable G-SYNC for full screen mode", which silently drops VRR in
    # borderless — the mode game_config:mw3:display_mode now recommends, and the mode
    # most modern titles default to. Choosing 'fullscreen' here would disable G-Sync
    # for those games with nothing in the UI to say so.
    recommended_value="on",
    requires_reboot=False,
    current_impact="Off: Monitor runs at fixed refresh rate, may cause screen tearing",
    recommended_impact="On: Tear-free adaptive refresh in borderless and exclusive fullscreen alike",
    scope=SettingScope.RECOMMENDED,
    category_order=6,  # Sync technology
    effect="Enables variable refresh rate for tear-free play on a G-Sync or compatible monitor",
    impact_scores={"fps": "0%", "latency_ms": -8, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia", "requires_vrr": True},  # NVIDIA + VRR monitor
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "vrr_mode"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "vrr_mode"},
    apply_value_map={},
)

NVIDIA_BG_APP_FPS = SettingExecutor(
    id="gpu-nvidia:bg_app_fps",
    category=SettingCategory.GPU,
    display_name="Background App Max FPS",
    short_name="Background app frame cap",
    description="NVIDIA's frame cap for unfocused windows, which the driver also applies to "
    "focused games whose overlays confuse its foreground detection. Keep it off.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=0,
    # Was 30. Reverted to off (NVIDIA's own recommended value) because the
    # driver's foreground detection is unreliable: an application that renders
    # under an overlay, in a separate process, or from an executable with no
    # driver profile is treated as permanently backgrounded, so the background
    # cap becomes the game's cap. Reported on the dev machine as MW3 running at
    # background speed, and documented across unrelated software — Portal RTX
    # (explicitly attributed to its overlay), VS Code, Electron apps, TETR.IO,
    # Chromium browsers. MW3 ships with Battle.net/Steam/CoD HQ overlays, which
    # is exactly the Portal RTX shape.
    # It stays as a setting rather than being deleted so fpstune can turn the cap
    # off for the users its own earlier recommendation switched on.
    recommended_value=0,
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://steamcommunity.com/sharedfiles/filedetails/?id=2899411695",
        "https://github.com/microsoft/vscode/issues/112857",
        "https://github.com/electron/electron/issues/50469",
    ],
    current_impact="Any limit: a focused game can be capped at the background rate → severe FPS loss",
    recommended_impact="Off: the driver never caps your game by mistake → full frame rate",
    scope=SettingScope.ESSENTIAL,
    category_order=9,  # Background optimization
    effect="Removes a frame cap the driver can apply to a focused game by mistake",
    # Not an FPS percentage: the loss is a hard ceiling, not a proportion, and it
    # is either absent or catastrophic. 30 is the cap fpstune's own earlier
    # recommendation imposed, so it is the figure most affected users are lifting.
    impact_scores={"fps_cap_removed": 30, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "bg_app_fps"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "bg_app_fps"},
    apply_value_map={},
)

NVIDIA_ANISO_SAMPLE_OPT = SettingExecutor(
    id="gpu-nvidia:aniso_sample_opt",
    category=SettingCategory.GPU,
    display_name="Anisotropic Sample Optimization",
    short_name="Anisotropic shortcut",
    description="Optimizes anisotropic filtering samples for minor performance gain.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on"),
    default_value="off",
    recommended_value="on",
    requires_reboot=False,
    current_impact="Off: Full anisotropic filtering samples",
    recommended_impact="On: Optimized samples → 1-2% FPS gain, minimal visual difference",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=10,
    perceptible_cost=(
        "Anisotropic samples are trimmed — oblique surfaces sharpen slightly less than stock filtering."
    ),  # Texture optimization
    effect="Reduces anisotropic filtering samples for slight performance boost",
    impact_scores={"fps": "+0-1%", "latency_ms": 0, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "aniso_sample_opt"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "aniso_sample_opt"},
    apply_value_map={},
)

NVIDIA_TEXTURE_LOD_BIAS = SettingExecutor(
    id="gpu-nvidia:texture_lod_bias",
    category=SettingCategory.GPU,
    display_name="Texture LOD Bias",
    short_name="Texture sharpness bias",
    description="Controls negative LOD bias for texture filtering. Clamp prevents blurry textures.",
    value_type=SettingValueType.CHOICE,
    choices=("allow", "clamp"),
    default_value="allow",
    recommended_value="clamp",
    requires_reboot=False,
    current_impact="Allow: Games can apply negative LOD bias → potentially blurry textures",
    recommended_impact="Clamp: Prevents negative LOD bias → sharper textures at distance",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=11,  # Texture optimization
    effect="Clamps LOD bias to prevent blurry distant textures",
    impact_scores={"fps": "0%", "visual_quality": "improved", "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "texture_lod_bias"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "texture_lod_bias"},
    apply_value_map={},
)

NVIDIA_OGL_THREAD_OPT = SettingExecutor(
    id="gpu-nvidia:ogl_thread_opt",
    category=SettingCategory.GPU,
    display_name="OpenGL Threading Optimization",
    short_name="OpenGL threading",
    description="Whether the driver spreads OpenGL work across threads. Auto lets the driver decide, and most "
    "games use DirectX rather than OpenGL.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on", "auto"),
    default_value="auto",
    recommended_value="auto",
    requires_reboot=False,
    current_impact="Auto: Driver decides OpenGL threading per-application",
    recommended_impact="Auto: Driver optimizes per-game → no stutter risk",
    scope=SettingScope.COMPLETE,  # OpenGL is rare, marginal benefit
    category_order=12,  # OpenGL optimization
    effect="Lets NVIDIA driver choose optimal OpenGL threading",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "ogl_thread_opt"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "ogl_thread_opt"},
    apply_value_map={},
)

NVIDIA_CUDA_FORCE_P2 = SettingExecutor(
    id="gpu-nvidia:cuda_force_p2",
    category=SettingCategory.GPU,
    display_name="CUDA Force P2 State",
    short_name="CUDA memory clock cap",
    description="Forces higher GPU power state for CUDA applications. Useful for GPU compute.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on"),
    default_value="off",
    recommended_value="off",  # Only useful for CUDA workloads
    requires_reboot=False,
    current_impact="Off: GPU uses adaptive power state for CUDA",
    recommended_impact="On: Forces P2 state → more stable CUDA performance",
    scope=SettingScope.COMPLETE,  # Specialized use case
    category_order=13,  # CUDA optimization
    effect="Forces higher GPU power state for consistent CUDA performance",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "medium"},
    applicable_conditions={"gpu_vendor": "nvidia"},  # NVIDIA only
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "cuda_force_p2"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "cuda_force_p2"},
    apply_value_map={},
)

# =============================================================================
# NVIDIA - Maximum Pre-rendered Frames
# =============================================================================

NVIDIA_MAX_PRERENDERED = SettingExecutor(
    id="gpu-nvidia:max_prerendered",
    category=SettingCategory.GPU,
    display_name="Maximum Pre-rendered Frames",
    short_name="Frames queued ahead",
    description="How many frames the CPU may queue ahead of the GPU. Fewer means less input latency at some "
    "cost to throughput, and it works alongside Low Latency Mode.",
    value_type=SettingValueType.INT,
    choices=(),
    default_value=3,
    recommended_value=1,
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/",
    ],
    current_impact="3 frames: Higher throughput but more input lag",
    recommended_impact="1 frame: Minimum input latency, slight throughput reduction",
    scope=SettingScope.RECOMMENDED,
    category_order=14,
    effect="Reduces pre-render queue to 1 frame for minimum input latency in competitive games",
    impact_scores={"latency_ms": -3, "fps": "-0-1%"},
    applicable_conditions={"gpu_vendor": "nvidia"},
    min_value=1,
    max_value=4,
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "max_prerendered"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "max_prerendered"},
    apply_value_map={},
)

# =============================================================================
# NVIDIA - Triple Buffering
# =============================================================================

NVIDIA_TRIPLE_BUFFER = SettingExecutor(
    id="gpu-nvidia:triple_buffer",
    category=SettingCategory.GPU,
    display_name="Triple Buffering",
    short_name="Triple buffering",
    description="Adds a third frame buffer for VSync. It smooths VSync-on play but adds a frame of latency, "
    "so it stays off for competitive games.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on"),
    default_value="off",
    recommended_value="off",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Off: Standard double-buffered rendering",
    recommended_impact="Off: Minimum latency, standard rendering",
    scope=SettingScope.RECOMMENDED,
    category_order=15,
    effect="Controls triple buffering for VSync scenarios",
    impact_scores={"latency_ms": 0, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "triple_buffer"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "triple_buffer"},
    apply_value_map={},
)

# =============================================================================
# NVIDIA - G-Sync Application Override
# =============================================================================

NVIDIA_VRR_APP_OVERRIDE = SettingExecutor(
    id="gpu-nvidia:vrr_app_override",
    category=SettingCategory.GPU,
    display_name="G-Sync Application Override",
    short_name="G-Sync per-app override",
    description="Per-application G-Sync override. Driver default lets the global setting apply; forcing it on "
    "keeps G-Sync active for borderless windowed games.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "driver_default", "force_on"),
    default_value="driver_default",
    recommended_value="driver_default",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Driver default: Uses global G-Sync setting",
    recommended_impact="Driver default: Consistent with global VRR configuration",
    scope=SettingScope.RECOMMENDED,
    category_order=16,
    effect="Controls per-application G-Sync override behavior",
    impact_scores={"latency_ms": 0, "stability": "high"},
    applicable_conditions={
        "gpu_vendor": "nvidia",
        "requires_vrr": True,
    },
    detect_type=DetectType.NVPROFILE,
    detect_command="",
    detect_args={"setting": "vrr_app_override"},
    value_map={},
    apply_type=DetectType.NVPROFILE,
    apply_command="",
    apply_args={"setting": "vrr_app_override"},
    apply_value_map={},
)

# =============================================================================
# NVIDIA - Fan Curve Advisory (Detect-Only)
# =============================================================================

NVIDIA_FAN_CURVE = SettingExecutor(
    id="gpu-nvidia:fan_curve",
    category=SettingCategory.GPU,
    display_name="GPU Thermal / Fan Curve",
    short_name="GPU fan curve",
    description="Compares the GPU's hotspot temperature with its core. A hotspot more than 20°C above the "
    "core means the fan curve is too passive for this card.",
    value_type=SettingValueType.CHOICE,
    choices=("ok", "hotspot_warning", "thermal_warning"),
    default_value="ok",
    recommended_value="ok",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://gpubottleneckcalculator.com/blog/fan-curves-case-pressure-thermal-throttling/",
    ],
    current_impact="Unknown: GPU thermal data not yet read",
    recommended_impact="OK: Core and hotspot temps within safe range, no thermal throttling",
    scope=SettingScope.COMPLETE,
    category_order=17,
    effect="In MSI Afterburner or GPU Tweak, set a fan curve that keeps the core under 60°C and the "
    "hotspot under 70°C",
    impact_scores={"fps_sustained": "+0-30%", "gpu_temp_c": -10, "stability": "high"},
    applicable_conditions={"gpu_vendor": "nvidia"},
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        # Search nvidia-smi in PATH and the standard NVSMI install directory
        "$smiPaths = @('nvidia-smi.exe', "
        '"$env:ProgramFiles\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe"); '
        "$smiBin = $null; "
        "foreach ($p in $smiPaths) { "
        "  $c = Get-Command $p -EA SilentlyContinue; "
        "  if ($c) { $smiBin = $c.Source; break } "
        "  if (Test-Path $p) { $smiBin = $p; break } "
        "}; "
        "if (-not $smiBin) { "
        "  Write-Host 'FPSTUNE_WARN: nvidia-smi not found in PATH or "
        "C:\\Program Files\\NVIDIA Corporation\\NVSMI\\. "
        "Reinstall NVIDIA drivers to enable GPU thermal monitoring.'; "
        "  'not_available' "
        "} else { "
        "  $out = & $smiBin --query-gpu=temperature.gpu,temperature.memory "
        "  --format=csv,noheader,nounits 2>$null; "
        "  if ($out -match '(\\d+),\\s*(\\d+)') { "
        "    $core=[int]$matches[1]; $mem=[int]$matches[2]; "
        "    if ($mem - $core -gt 20) { 'hotspot_warning' } "
        "    elseif ($core -gt 83) { 'thermal_warning' } "
        "    else { 'ok' } "
        "  } else { "
        # temperature.memory (hotspot) is not exposed by nvidia-smi on most GeForce
        # cards (only datacenter GPUs report it). Fall back to core-only evaluation
        # instead of warning — this is expected, not a driver fault.
        "    $core2 = & $smiBin --query-gpu=temperature.gpu "
        "    --format=csv,noheader,nounits 2>$null; "
        "    if ($core2 -match '(\\d+)') { "
        "      if ([int]$matches[1] -gt 83) { 'thermal_warning' } else { 'ok' } "
        "    } else { 'not_available' } "
        "  } "
        "}"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="",
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# Cross-Vendor GPU Hardware Settings
# =============================================================================

GPU_RESIZABLE_BAR = SettingExecutor(
    id="gpu-hardware:resizable_bar",
    category=SettingCategory.GPU,
    display_name="Resizable BAR / Smart Access Memory",
    short_name="Resizable BAR",
    description="Lets the CPU address the GPU's whole VRAM at once, set in BIOS as Resizable BAR plus Above "
    "4G Decoding. NVIDIA may leave it off at driver level even when BIOS has it on.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.tomshardware.com/pc-components/gpus/"
        "nvidia-gpu-owners-may-be-losing-performance",
    ],
    current_impact="Disabled: CPU limited to 256MB GPU VRAM "
    "window, causing asset streaming bottleneck",
    recommended_impact="Enabled: Full VRAM access, 5-21% FPS gain in streaming-heavy titles",
    scope=SettingScope.RECOMMENDED,
    category_order=18,
    effect="In BIOS, under Advanced > PCI, set Resizable BAR and Above 4G Decoding to Enabled",
    impact_scores={"fps": "+2-10%", "fps_1_percent_low": "+1-5%"},
    applicable_conditions={"gpu_vendors": ["nvidia", "amd"]},
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    detect_command="rebar_detect",
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="",
    apply_args={},
    apply_value_map={},
)

# The games fpstune already manages, located the way each launcher records them,
# so both detect and apply walk exactly the same list (#56).
#
# CS2 comes from Steam's own library index — the game is often on a secondary
# library, so the install path alone is not enough. MW3 comes from its uninstall
# entry, which Battle.net writes with an `InstallLocation`; measured on the dev
# machine, where it reads the game's own folder on a secondary drive, matching
# the path already present in UserGpuPreferences.
#
# Each candidate is checked against the disk before it counts. An entry for a game
# that is not installed would make the setting permanently unsatisfiable, which is
# the failure class this codebase keeps paying for.
_GAME_EXE_SCAN = (
    "$fpsGames = @(); "
    "$steam = (Get-ItemProperty 'HKLM:\\SOFTWARE\\WOW6432Node\\Valve\\Steam' "
    "-EA SilentlyContinue).InstallPath; "
    "if (-not $steam) { $steam = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Valve\\Steam' "
    "-EA SilentlyContinue).InstallPath }; "
    "$roots = @(); "
    "if ($steam) { $roots += $steam; "
    "$vdf = Join-Path $steam 'steamapps\\libraryfolders.vdf'; "
    "if (Test-Path $vdf) { "
    "foreach ($m in [regex]::Matches((Get-Content $vdf -Raw -EA SilentlyContinue), "
    "'\"path\"\\s+\"([^\"]+)\"')) { $roots += $m.Groups[1].Value.Replace('\\\\','\\') } } }; "
    "foreach ($r in $roots) { "
    "$c = Join-Path $r "
    "'steamapps\\common\\Counter-Strike Global Offensive\\game\\bin\\win64\\cs2.exe'; "
    "if (Test-Path $c) { $fpsGames += $c } }; "
    "foreach ($u in @('HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall',"
    "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall')) { "
    "foreach ($k in (Get-ChildItem $u -EA SilentlyContinue)) { "
    "$q = Get-ItemProperty $k.PSPath -EA SilentlyContinue; "
    "if ($q.DisplayName -eq 'Call of Duty Modern Warfare III' -and $q.InstallLocation) { "
    "$c = Join-Path $q.InstallLocation '_retail_\\cod23-cod.exe'; "
    "if (Test-Path $c) { $fpsGames += $c } } } }; "
    "$fpsGames = @($fpsGames | Select-Object -Unique); "
    "$fpsKey = 'HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences'; "
)

# Both commands answer 'single_gpu' on a machine with one adapter, so neither acts
# on a system where the question does not arise.
_HYBRID_GUARD = (
    "$gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue; "
    "$igpu = $gpus | Where-Object { $_.Name -match 'Intel|UHD|Iris' }; "
    "$dgpu = $gpus | Where-Object { $_.Name -match 'NVIDIA|GeForce|Radeon' -and "
    "$_.Name -notmatch 'Intel' }; "
)

GPU_LAPTOP_ASSIGNMENT = SettingExecutor(
    id="gpu-hardware:gpu_assignment",
    category=SettingCategory.GPU,
    display_name="GPU Assignment (Hybrid Graphics)",
    short_name="Which GPU runs games",
    description="Which GPU your games run on when the machine has both an integrated and a "
    "discrete one. Landing on the integrated chip costs most of the frame rate the machine has.",
    value_type=SettingValueType.CHOICE,
    choices=("single_gpu", "dgpu_preferred", "not_configured"),
    default_value="not_configured",
    recommended_value="dgpu_preferred",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="low",
    current_impact="Not configured: a game may run on the integrated GPU",
    recommended_impact="dGPU preferred: every game fpstune knows about runs on the discrete GPU",
    scope=SettingScope.COMPLETE,
    category_order=19,
    effect="Points the games fpstune knows about at the discrete GPU",
    # Deliberately no invented percentage. The gap is not a percentage — it is the
    # difference between running on the right chip and the wrong one.
    impact_scores={"fps": "15 vs 120+ FPS if wrong GPU", "latency_ms": 0},
    # Covers the games fpstune can locate, and says so. A game it cannot find is
    # still set the same way through Windows Settings > Display > Graphics.
    risk_warning="This covers the games fpstune can locate — Counter-Strike 2 through Steam's "
    "library index, and Modern Warfare III through its Battle.net install entry. For any other "
    "game, set it yourself in Windows Settings > Display > Graphics by adding the .exe and "
    "choosing High performance. Reset removes fpstune's entries, returning those games to "
    "'Let Windows decide'.",
    detect_type=DetectType.POWERSHELL,
    # Read the per-application values, not DirectXUserGlobalSettings.
    #
    # That value cannot answer this question and never could: Windows stores a GPU
    # preference as its own value per executable path, while
    # DirectXUserGlobalSettings holds the three global toggles from the same page.
    # Measured on the dev machine, a hybrid laptop with the preference set for
    # three games:
    #     DirectXUserGlobalSettings = VRROptimizeEnable=1;SwapEffectUpgradeEnable=1;
    #                                 AutoHDREnable=1;          <- no GpuPreference
    #     ...\cod23-cod.exe         = GpuPreference=2;
    #     ...\cs2.exe               = GpuPreference=2;
    #     ...\HeroesOfTheStorm_x64.exe = GpuPreference=2;
    # so the old test for '*GpuPreference=2*' in the global value read
    # `not_configured` on a machine that was configured — on every hybrid machine,
    # however it was set up. GpuPreference=2 is "High performance", 1 is
    # "Power saving", 0 is "Let Windows decide".
    detect_command=(
        _HYBRID_GUARD
        + "if (-not $igpu -or -not $dgpu) { 'single_gpu'; return }; "
        + _GAME_EXE_SCAN
        + "if ($fpsGames.Count -eq 0) { 'not_available'; return }; "
        "$p = Get-ItemProperty -Path $fpsKey -ErrorAction SilentlyContinue; "
        # Every game fpstune located must be on the discrete GPU, not merely one of
        # them — the same rule the DNS setting had to learn (#56). One game left on
        # 'Let Windows decide' is the whole problem this setting exists for.
        "foreach ($exe in $fpsGames) { "
        "$v = if ($p) { [string]$p.$exe } else { '' }; "
        "if ($v -notlike '*GpuPreference=2*') { 'not_configured'; return } }; "
        "'dgpu_preferred'"
    ),
    detect_args={},
    value_map={},
    # Writes exactly the executables detect inspects. `GpuPreference=2;` is the
    # literal Windows writes for High performance — verified by reading back what
    # the Settings UI had already stored for three games on this machine, rather
    # than composing a string that looked plausible.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        _HYBRID_GUARD + "if (-not $igpu -or -not $dgpu) "
        "{ 'error: this machine has a single GPU, nothing to assign'; return }; "
        + _GAME_EXE_SCAN
        + "if ($fpsGames.Count -eq 0) { 'error: none of the games fpstune knows about "
        "are installed'; return }; "
        "if (-not (Test-Path $fpsKey)) { New-Item -Path $fpsKey -Force -EA Stop | Out-Null }; "
        "$want = '%value%'; $changed = 0; $failed = 0; "
        "foreach ($exe in $fpsGames) { "
        "try { "
        "if ($want -eq 'dgpu_preferred') { "
        "Set-ItemProperty -Path $fpsKey -Name $exe -Value 'GpuPreference=2;' -Force -EA Stop } "
        # Reset removes the entry rather than writing GpuPreference=0. No entry is
        # Windows' own state for an app nobody has configured; a 0 would leave
        # fpstune's fingerprint behind and read as a deliberate choice.
        "else { Remove-ItemProperty -Path $fpsKey -Name $exe -Force -EA SilentlyContinue }; "
        "$changed++ } catch { $failed++ } }; "
        "if ($failed -gt 0) { 'error: ' + $failed + ' game(s) could not be written' } "
        "else { 'ok:' + $changed }"
    ),
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# AMD GPU Settings
# =============================================================================

AMD_ANTI_LAG = SettingExecutor(
    id="gpu-amd:anti_lag",
    category=SettingCategory.GPU,
    display_name="Anti-Lag",
    short_name="Anti-Lag",
    description="AMD Anti-Lag reduces input latency by synchronizing CPU and GPU workloads.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://www.amd.com/en/products/software/adrenalin/anti-lag-2.html"],
    current_impact="Disabled: Normal render queue → 20-40ms input delay",
    recommended_impact="Enabled: Synchronized CPU/GPU → reduced input latency",
    scope=SettingScope.ESSENTIAL,  # High impact on input latency
    category_order=1,  # Primary AMD latency setting
    effect="Synchronizes CPU and GPU workloads for reduced input latency",
    impact_scores={"fps": "0%", "latency_ms": -10, "stability": "high"},
    applicable_conditions={"gpu_vendor": "amd"},  # AMD only
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "AntiLag",
        "hive": "HKCU",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "AntiLag",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

AMD_SHADER_CACHE = SettingExecutor(
    id="gpu-amd:shader_cache",
    category=SettingCategory.GPU,
    display_name="Shader Cache",
    short_name="Shader cache",
    description="Cache compiled shaders to disk for faster game loading.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Disabled: Shaders recompile on every game launch",
    recommended_impact="Enabled: Shaders cached → faster startup, reduced stutter",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for stutter reduction
    category_order=3,  # Stutter reduction
    effect="Caches compiled shaders for faster startup and reduced stutter",
    impact_scores={"fps": "0%", "fps_1_percent_low": "+5-20%", "stutter_reduction": "high"},
    applicable_conditions={"gpu_vendor": "amd"},  # AMD only
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "ShaderCache",
        "hive": "HKCU",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "ShaderCache",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

AMD_VSYNC = SettingExecutor(
    id="gpu-amd:vsync",
    category=SettingCategory.GPU,
    display_name="Vertical Sync",
    short_name="V-Sync",
    description="Syncs frames to monitor refresh rate. Prevents tearing but adds input lag.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on"),
    default_value="on",
    recommended_value="off",
    requires_reboot=False,
    current_impact="On: Frames sync to monitor → 8-16ms extra input lag",
    recommended_impact="Off: Free frame rendering → minimum input lag",
    scope=SettingScope.ESSENTIAL,  # High impact on input latency
    category_order=2,  # Critical for input lag
    effect="Disables frame sync to monitor refresh for minimum latency",
    impact_scores={"fps": "0%", "latency_ms": -12.0, "visual_quality": "may tear"},
    applicable_conditions={"gpu_vendor": "amd"},  # AMD only
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "WaitForVerticalRefresh",
        "hive": "HKCU",
    },
    value_map={1: "on", "1": "on", 0: "off", "0": "off", None: "on"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "WaitForVerticalRefresh",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"on": 1, "off": 0},
)

# === AMD Radeon Boost (T1 AMD Source) ===
# Dynamically lowers resolution during motion for FPS gains.
# T1 evidence: AMD official documentation confirms 5-15% FPS improvement.
# Scope is COMPLETE, not RECOMMENDED (decided 2026-09-02): the resolution drop
# lands exactly while the camera moves fast, which is the moment a player is
# tracking a target. That is a perceptible cost to an information channel, so
# consequence 5 puts it where it is offered with the cost in the copy, never
# applied by the safe button. Chill sits in the same category for the same
# reason. No lab measurement of the tracking cost exists either way; Calypto's
# competitive-latency guide lists Boost off.
AMD_RADEON_BOOST = SettingExecutor(
    id="gpu-amd:radeon_boost",
    category=SettingCategory.GPU,
    display_name="Radeon Boost",
    short_name="Radeon Boost",
    description="Lowers render resolution while the camera moves fast and restores it when the view settles, "
    "for 5-15% more frames. The sharpness is lost exactly while tracking a target.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Disabled: Full resolution at all times, including while tracking a target",
    recommended_impact="Enabled: 5-15% more frames during motion, at the cost of a softer image while you track a target",
    scope=SettingScope.COMPLETE,  # Perceptible cost during tracking: offered, never assumed
    category_order=4,  # After Anti-Lag and Shader Cache
    effect="Enables dynamic resolution scaling during motion for higher FPS",
    impact_scores={"fps": "+10-25%", "latency_ms": -2, "stability": "high"},
    applicable_conditions={"gpu_vendor": "amd"},  # AMD only
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableRBoost",
        "hive": "HKCU",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableRBoost",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# === AMD Enhanced Sync ===
# Alternative to VSync - reduces tearing without adding input lag.
AMD_ENHANCED_SYNC = SettingExecutor(
    id="gpu-amd:enhanced_sync",
    category=SettingCategory.GPU,
    display_name="Enhanced Sync",
    short_name="Enhanced Sync",
    description="VSync alternative that reduces tearing without adding input lag. Best for FPS > refresh rate.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",  # Only useful when FPS > refresh rate
    requires_reboot=False,
    current_impact="Disabled: No tear reduction (unless VSync is on)",
    recommended_impact="Disabled: no tear reduction, and no extra latency; enable only when fps exceeds the refresh "
    "rate",
    scope=SettingScope.COMPLETE,  # Situational benefit
    category_order=5,
    perceptible_cost=(
        "Without a sync method, tearing can appear in the moments frames overrun the refresh rate."
    ),  # After Radeon Boost
    effect="Reduces screen tearing when FPS exceeds refresh rate without VSync lag",
    impact_scores={"fps": "0%", "latency_ms": -8, "visual_quality": "reduced tearing"},
    applicable_conditions={"gpu_vendor": "amd"},  # AMD only
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableEnhancedSync",
        "hive": "HKCU",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableEnhancedSync",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# All GPU settings (all managed via Optimizations tab)
# =============================================================================
# NVIDIA - Battery Boost Exposure (Detect-Only, portable machines)
# =============================================================================

NVIDIA_BATTERY_BOOST = SettingExecutor(
    id="gpu-nvidia:battery_boost",
    category=SettingCategory.GPU,
    display_name="Battery Boost Frame Cap",
    short_name="Battery frame cap",
    description="Whether the NVIDIA App can hold your games near 30 FPS while the laptop runs "
    "on battery. The cap is a feature, not a fault, but it is a ceiling nobody asked for in the "
    "middle of a match.",
    value_type=SettingValueType.CHOICE,
    # Reports a condition rather than offering a change, the same shape as the
    # fan-curve advisory above.
    choices=("no_cap_possible", "cap_possible"),
    default_value="no_cap_possible",
    recommended_value="no_cap_possible",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="low",
    current_impact="Cap possible: A match on battery can be held near 30 FPS without warning",
    recommended_impact="No cap possible: Nothing here holds the frame rate down on battery",
    scope=SettingScope.RECOMMENDED,
    category_order=21,
    effect="Turn Battery Boost off under Graphics in the NVIDIA App if you would rather spend the "
    "battery",
    # A ceiling, not a gain — the same honest shape as MW3's unfocused cap, and
    # the verification engine will report it unmeasurable for the same reason:
    # a ceiling cannot move the right way.
    impact_scores={"fps_battery_ceiling": 30, "stability": "high"},
    # Portable *and* NVIDIA. Either alone is the wrong audience: a desktop has no
    # battery state to boost, and an AMD laptop has no NVIDIA App to read.
    applicable_conditions={"gpu_vendor": "nvidia", "feature": "mobile"},
    # fpstune cannot write this. The toggle lives in the NVIDIA App's own UI, and
    # the whole NvBackend directory was searched on 2026-08-23 without finding
    # anywhere it persists the on/off state — only the criteria that decide
    # whether the feature can run at all. So this reports the exposure and names
    # where to act, exactly like the BIOS advisories.
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    detect_command="",
    detect_args={"batch_config": "nvidia_app"},
    value_map={},
)

NVIDIA_SETTINGS: list[SettingExecutor] = [
    NVIDIA_LOW_LATENCY,
    NVIDIA_VSYNC,
    NVIDIA_POWER_MODE,
    NVIDIA_THREADED_OPT,
    NVIDIA_SHADER_CACHE,
    NVIDIA_TEXTURE_QUALITY,
    NVIDIA_VRR_MODE,
    NVIDIA_FPS_LIMITER,
    NVIDIA_BG_APP_FPS,
    NVIDIA_ANISO_SAMPLE_OPT,
    NVIDIA_TEXTURE_LOD_BIAS,
    NVIDIA_OGL_THREAD_OPT,
    NVIDIA_CUDA_FORCE_P2,
    NVIDIA_MAX_PRERENDERED,
    NVIDIA_TRIPLE_BUFFER,
    NVIDIA_VRR_APP_OVERRIDE,
    NVIDIA_FAN_CURVE,
    NVIDIA_BATTERY_BOOST,
]

# =============================================================================
# AMD - Chill (Dynamic FPS Limiter)
# =============================================================================

AMD_CHILL = SettingExecutor(
    id="gpu-amd:chill",
    category=SettingCategory.GPU,
    display_name="Radeon Chill",
    short_name="Radeon Chill",
    description="Lowers the frame rate whenever on-screen motion drops, including in the middle "
    "of a match. The cap lifts again once you move, but it lifts after the frame you needed it "
    "for.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.amd.com/en/products/software/adrenalin.html",
    ],
    current_impact="Enabled: Frames are cut while you hold still → the flick off that corner starts from a lower rate",
    recommended_impact="Disabled: The frame rate never depends on how much you were moving a moment ago",
    scope=SettingScope.RECOMMENDED,
    category_order=6,
    effect="Stops the driver cutting frames based on how much you were moving",
    # Was `{"fps": "+0-40%", "gpu_temp_c": 5}`. The 40% was the ceiling Chill
    # imposes on a *static* scene reported as a gain — the same conflation the
    # menu frame caps carried — and a static scene is precisely when those frames
    # are worth nothing. What disabling Chill really buys is not more frames on
    # average, it is frames that do not depend on the previous second of input.
    #
    # The +5 C is honest and it is the real cost: this gives up a genuine heat
    # saving. It is given up because Chill binds *during* a match, where a cap
    # can arrive on the frame you flick, and the same saving is collected by
    # settings that only bind when you are not playing — the menu and unfocused
    # caps. Trading an in-match risk for an out-of-match saving is the whole
    # rule, and this is the one place the trade runs the expensive way.
    impact_scores={"latency_spike_ms": 0.0, "gpu_temp_c": 5, "stability": "high"},
    applicable_conditions={"gpu_vendor": "amd"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableChill",
        "hive": "HKCU",
    },
    value_map={
        1: "enabled",
        "1": "enabled",
        0: "disabled",
        "0": "disabled",
        None: "disabled",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableChill",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# =============================================================================
# AMD - Frame Rate Target Control (FRTC)
# =============================================================================

AMD_FRTC = SettingExecutor(
    id="gpu-amd:frtc",
    category=SettingCategory.GPU,
    display_name="Frame Rate Target Control (FRTC)",
    short_name="Frame rate cap (FRTC)",
    description="A driver-wide frame cap for AMD GPUs, applied regardless of game settings. Off leaves "
    "performance uncapped.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Disabled: No global FPS cap from FRTC",
    recommended_impact="Disabled: GPU renders at maximum possible framerate",
    scope=SettingScope.RECOMMENDED,
    category_order=7,
    effect="Disables global FPS cap for uncapped GPU performance",
    impact_scores={"fps": "0%", "latency_ms": -1},
    applicable_conditions={"gpu_vendor": "amd"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableFRTC",
        "hive": "HKCU",
    },
    value_map={
        1: "enabled",
        "1": "enabled",
        0: "disabled",
        "0": "disabled",
        None: "disabled",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\AMD\CN",
        "name": "EnableFRTC",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

AMD_SETTINGS: list[SettingExecutor] = [
    AMD_ANTI_LAG,
    AMD_SHADER_CACHE,
    AMD_VSYNC,
    AMD_RADEON_BOOST,
    AMD_ENHANCED_SYNC,
    AMD_CHILL,
    AMD_FRTC,
]

GPU_MSI_MODE = SettingExecutor(
    id="gpu-hardware:msi_mode",
    category=SettingCategory.GPU,
    display_name="GPU Message-Signaled Interrupts",
    short_name="GPU interrupt mode",
    description="Delivers GPU interrupts per device via MSI instead of a shared legacy IRQ line. RTX "
    "40-series ships with MSI on; older cards often default to a shared line that adds DPC "
    "latency.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "enabled"),
    default_value="default",
    recommended_value="enabled",
    requires_reboot=True,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Edits the GPU's Interrupt Management registry key and needs a reboot to take "
    "effect. If the card does not handle MSI correctly the display driver can fail to start — "
    "reset this setting and reboot to restore line-based interrupts. Change this for the GPU "
    "only; raising interrupt priority for the network adapter at the same time is reported to "
    "cause instability.",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/enabling-message-signaled-interrupts-in-the-registry",
        "https://hackingpc.com/pc-optimization/windows-11-msi-mode-interrupt-guide/",
    ],
    current_impact="Default: Shared line-based IRQ → cross-device interrupt latency and DPC spikes",
    recommended_impact="Enabled: Per-device MSI → lower DPC latency, steadier 1% lows",
    scope=SettingScope.COMPLETE,
    category_order=20,
    effect="Enables MSI interrupt delivery for the graphics adapter",
    impact_scores={"fps_1_percent_low": "+0-3%", "latency_ms": -1.0},
    applicable_conditions={"gpu_vendors": ["nvidia", "amd"]},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$gpu = Get-PnpDevice -Class Display -ErrorAction SilentlyContinue "
        "| Where-Object { $_.InstanceId -match 'VEN_10DE|VEN_1002' } "
        "| Select-Object -First 1; "
        "if (-not $gpu) { 'not_supported' } else { "
        '$rp = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($gpu.InstanceId)\\Device Parameters'
        '\\Interrupt Management\\MessageSignaledInterruptProperties"; '
        "$v = (Get-ItemProperty -Path $rp -Name 'MSISupported' "
        "-ErrorAction SilentlyContinue).MSISupported; "
        "if ($v -eq 1) { 'enabled' } else { 'default' } }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "try { "
        "$gpu = Get-PnpDevice -Class Display -ErrorAction SilentlyContinue "
        "| Where-Object { $_.InstanceId -match 'VEN_10DE|VEN_1002' } "
        "| Select-Object -First 1; "
        "if (-not $gpu) { 'not_supported' } else { "
        '$rp = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($gpu.InstanceId)\\Device Parameters'
        '\\Interrupt Management\\MessageSignaledInterruptProperties"; '
        "if ('%value%' -eq 'enabled') { "
        "if (-not (Test-Path $rp)) { New-Item -Path $rp -Force | Out-Null }; "
        "Set-ItemProperty -Path $rp -Name 'MSISupported' -Value 1 -Type DWord -Force "
        "} else { "
        "Remove-ItemProperty -Path $rp -Name 'MSISupported' -ErrorAction SilentlyContinue "
        "}; 'ok' } "
        "} catch { 'error:' + $_.Exception.Message }"
    ),
    apply_args={},
    apply_value_map={},
)


GPU_HARDWARE_SETTINGS: list[SettingExecutor] = [
    GPU_RESIZABLE_BAR,
    GPU_LAPTOP_ASSIGNMENT,
    GPU_MSI_MODE,
]

GPU_SETTINGS: list[SettingExecutor] = [
    *NVIDIA_SETTINGS,
    *AMD_SETTINGS,
    *GPU_HARDWARE_SETTINGS,
]
