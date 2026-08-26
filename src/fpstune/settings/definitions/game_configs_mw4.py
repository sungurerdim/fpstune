"""Call of Duty: Modern Warfare IV (cod26) settings.

Kept apart from ``game_configs.py`` because MW4's plumbing shares nothing with
MW3's beyond the vendor: a different file format, two files rather than one, and
a key whose scope index is part of its identity.

**Ranges are the file's, not ours.** Every line in MW4's config documents its own
range (``// 0 to 3``) or its own value list (``// one of Low, High``). The
``choices`` below are what those comments held when this was written, and
:func:`fpstune.settings.discovery.games_mw4.adopt_mw4_ranges`
replaces them at startup with whatever the installed build actually says. The
writer refuses anything the file does not allow, so a build that moves a range
gets a refused write rather than a value MW4 answers by resetting the key.

Three things about this game that decide several settings below:

* ``TextureQuality`` is **inverted** — 0..3 where 0 is the highest resolution.
* The shipped config on the machine this was read from had the 3D scene at half
  window resolution *and* DLSS at Maximum Performance. That is two upscales
  stacked, and it is the largest single loss of enemy detail in the file.
* **The ``GraphicsQuality`` preset does not re-assert itself over individual
  keys, and this was measured rather than assumed.** Third-party guides say
  MW4's presets re-enable ray tracing and advise switching to Custom first,
  which the file's own list (``Minimum, Basic, Balanced, Ultra, Extreme``) does
  not offer — so if it were true, the graphics half of these settings would be
  inert. Tested 2026-08-24: with the game closed, ``ShadowFilteringQuality`` was
  written from ``Medium`` to ``Low`` against a standing ``GraphicsQuality =
  Balanced``, the game was launched, brought to the menu and quit. It rewrote
  the file, and of 158 keys exactly one had changed: ours, still ``Low``.

  What that does **not** cover, because it is a thing the player does rather
  than a thing the game does: picking a preset in the graphics menu. That is
  presumably what the guides describe, and it would overwrite these keys the
  same way any manual change does. There is no preset setting registered here —
  fpstune never writes ``GraphicsQuality``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)
from fpstune.settings.performance_headroom import frame_cap_for_refresh

if TYPE_CHECKING:
    pass

# MW4 is in beta as this is written, so there are no settled third-party
# benchmarks for it. Everything here is sourced from one of three places, and
# the `evidence_level` on each setting says which:
#   * the config file's own documentation (ranges, value lists, descriptions),
#   * MW3, which runs the same engine family and whose values were measured,
#   * nothing yet — those are marked `experimental` and carry a risk warning.
_MW4_SOURCES: list[str] = []

_MW3_MEASURED = [
    "https://pcoptimizedsettings.com/call-off-duty-modern-warfare-3-season-6-pc-optimized-settings-every-graphics-option-benchmarked/",
]


def _make_mw4_setting(
    *,
    setting_id: str,
    display_name: str,
    short_name: str = "",
    description: str,
    key: str | list[str],
    choices: tuple[str, ...],
    default_value: str | int,
    recommended_value: str | int,
    current_impact: str,
    recommended_impact: str,
    effect: str,
    impact_scores: dict[str, str | float],
    category_order: int,
    source_file: Literal["global", "profile", "both"] = "global",
    evidence_level: str = "likely",
    sources: list[str] | None = None,
    risk_level: Literal["safe", "low", "moderate", "advanced"] = "low",
    risk_warning: str | None = None,
    value_hints: dict[str, str] | None = None,
    applicable_conditions: dict[str, str] | None = None,
    value_type: SettingValueType = SettingValueType.CHOICE,
    scope: SettingScope = SettingScope.RECOMMENDED,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    perceptible_cost: str | None = None,
) -> SettingExecutor:
    """Build one MW4 setting.

    ``key`` carries its scope index (``TextureQuality@0``) because the index is
    part of the identity, not decoration: ``DxrMode@0`` is Off/On while
    ``DxrMode@1`` is Off..Ultra, and writing one's value into the other hands
    the game something it will not accept.

    A list of keys makes the setting a named-compound (C8): several scopes that
    hold the same value list and mean the same thing, so the concept is only
    applied when every one of them is. `SSRQuality` is the case; `DxrMode` is
    not, because its two scopes offer different values.

    Detection and apply both go through the Python reader/writer rather than a
    PowerShell command, so a scan costs no process per setting and the
    suffix-preserving rewrite has exactly one implementation.
    """
    batch_args = {"batch_config": "mw4", "batch_key": key, "batch_source": source_file}
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.GAME_CONFIG,
        display_name=display_name,
        short_name=short_name or display_name,
        description=description,
        value_type=value_type,
        choices=choices,
        default_value=default_value,
        recommended_value=recommended_value,
        min_value=min_value,
        max_value=max_value,
        requires_reboot=False,
        evidence_level=evidence_level,
        sources=sources if sources is not None else _MW4_SOURCES,
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        scope=scope,
        perceptible_cost=perceptible_cost,
        category_order=category_order,
        effect=effect,
        impact_scores=impact_scores,
        risk_level=risk_level,
        risk_warning=risk_warning,
        detect_type=DetectType.POWERSHELL,
        # Never reached in practice: the batch args above serve every read from
        # the one cached file. Spelled as a no-op rather than left empty so a
        # single-setting detect outside a scan fails loudly instead of running
        # something that looks like a PowerShell command and is not.
        detect_command="mw4_config_read",
        detect_args=batch_args,
        apply_type=DetectType.POWERSHELL,
        apply_command="mw4_config_write",
        apply_args=batch_args,
        apply_value_map={c: c for c in choices},
        value_hints=value_hints or {},
        applicable_conditions=applicable_conditions or {},
    )


# --------------------------------------------------------------------------
# The two settings that cost the most enemy detail, and cost it together
# --------------------------------------------------------------------------

MW4_RENDER_RESOLUTION = _make_mw4_setting(
    setting_id="game_config:mw4:render_resolution",
    display_name="MW4 Render Resolution Multiplier",
    short_name="MW4 Render Resolution Multiplier",
    description="Percentage of the window resolution the 3D scene is drawn at, applied before "
    "any upscaler. Below 100 the game renders fewer pixels and then stretches them, which is "
    "what makes a distant enemy hard to separate from the terrain.",
    key="ResolutionMultiplier@0",
    choices=("50", "67", "75", "100", "125", "150", "200"),
    default_value="100",
    recommended_value="100",
    current_impact="50: Scene drawn at a quarter of the pixels, then upscaled again by DLSS",
    recommended_impact="100: Full-resolution scene into the upscaler — distant targets stay separable",
    effect="Stops the double downscale that blurs targets at range",
    # Negative because this is the direction that costs frames: the source below
    # measured the same control in MW3 at +89% fps going from 100 to 50, so
    # undoing it is the other half of that trade. Not measured on MW4.
    impact_scores={"fps": "-35-47%", "stability": "high"},
    category_order=10,
    # COMPLETE: it changes what the screen shows, and it costs frames on a card
    # already asked for 297 of them. Offered with the price written, never
    # assumed — CLAUDE.md consequence 5.
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    value_hints={
        "50": "Quarter the pixels — cheapest and blurriest",
        "100": "Native into the upscaler — recommended when DLSS is on",
        "150": "Supersampled — sharpest, very expensive",
    },
)

MW4_DLSS_PERF_MODE = _make_mw4_setting(
    setting_id="game_config:mw4:dlss_perf_mode",
    display_name="MW4 DLSS Quality Mode",
    short_name="MW4 DLSS Quality Mode",
    description="Internal resolution DLSS renders at before upscaling to the output. "
    "An upscaler exists to buy frames, so its most expensive tier gives back most of what "
    "it was turned on for.",
    key="DLSSPerfModeMP@0",
    choices=("Ultra Performance", "Maximum Performance", "Balanced", "Maximum Quality"),
    default_value="Maximum Quality",
    recommended_value="Balanced",
    current_impact="Maximum Quality: ~67% internal render — the tier that buys the fewest frames",
    recommended_impact="Balanced: ~58% internal render — frames back, distant shapes still resolved",
    effect="Moves DLSS to the tier that buys frames without softening a target",
    impact_scores={"fps": "+10-18%", "stability": "high"},
    category_order=11,
    perceptible_cost=(
        "The image is rendered below native resolution and upscaled — fine detail softens, most visibly in motion and at distance."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    applicable_conditions={"gpu_vendor": "nvidia"},
    value_hints={
        "Ultra Performance": "~33% render — distant players stop being identifiable",
        "Balanced": "~58% render — recommended",
        "Maximum Quality": "~67% render — for a machine already at its target",
    },
)

MW4_DLSS_MODEL = _make_mw4_setting(
    setting_id="game_config:mw4:dlss_model",
    display_name="MW4 DLSS Model",
    short_name="MW4 DLSS Model",
    description="Which DLSS neural model does the upscaling. The transformer model holds fine "
    "detail together in motion better than the older convolutional one, and it costs up to 3% "
    "of the frame rate to do it.",
    key="DLSSModelUI@0",
    choices=("CNN", "TRANSFORMER"),
    default_value="CNN",
    recommended_value="CNN",
    current_impact="TRANSFORMER: Steadier detail in motion, bought with up to 3% of the frames",
    recommended_impact="CNN: The game's own model — detail resolved, nothing spent to do it",
    effect="Keeps DLSS on the model that costs no frames",
    # Was TRANSFORMER, in RECOMMENDED, on the claim that it cost nothing. The
    # description said "at the same render cost" while `impact_scores` said
    # "0 to -3%", and both cannot be true. The measured cost is the one that
    # survives, which makes raising this the exception rather than the default:
    # steadier motion detail is real, and a machine below its target has no
    # frames to buy it with.
    impact_scores={"fps": "+0-3%", "stability": "high"},
    category_order=12,
    scope=SettingScope.RECOMMENDED,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "nvidia"},
    value_hints={
        "CNN": "The shipped model — recommended below your frame-rate target",
        "TRANSFORMER": "Steadier in motion, for a machine already at its target",
    },
)

MW4_TEXTURE_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:texture_quality",
    display_name="MW4 Texture Quality",
    short_name="MW4 Texture Quality",
    description="Resolution of the textures the game loads, on an inverted scale where 0 is the "
    "highest and 3 the lowest. Texture detail on player models is how an opponent is told apart "
    "from the scenery, so it is spent last rather than first — but spent last is not never.",
    key="TextureQuality@0",
    choices=("0", "1", "2", "3"),
    default_value="0",
    recommended_value="1",
    current_impact="0: The largest texture set — costs 1% lows when the VRAM budget is tight",
    recommended_impact="1: Player models still carry the detail that tells them from scenery",
    effect="Holds texture detail one tier below the largest set",
    # Textures are a VRAM cost first and a 1%-low cost second, and the second
    # only bites when the budget does not hold. Tier 0 was recommended on a
    # machine with 8 GB of VRAM, where it does. Tier 1 keeps the channel the
    # description is about — surface detail on a player model — and hands back
    # the stutter that comes from streaming a set that does not fit.
    impact_scores={"fps_1_percent_low": "+2-6%", "vram_mb": "-300-800"},
    category_order=13,
    perceptible_cost=("Textures render a tier lower — surfaces read softer up close."),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    value_hints={
        "0": "Largest set — for a card with VRAM to spare, note the scale is inverted",
        "1": "Recommended — player-model detail intact, budget honoured",
        "3": "Lowest resolution — models start blending into scenery",
    },
)

MW4_ANISOTROPIC = _make_mw4_setting(
    setting_id="game_config:mw4:anisotropic",
    display_name="MW4 Texture Filtering",
    short_name="MW4 Texture Filtering",
    description="Anisotropic filtering level applied to surfaces viewed at an angle. It sharpens "
    "ground and wall texture into the distance, which is scenery — an opponent is resolved by "
    "model and texture detail, not by how crisp the floor they stand on is.",
    key="TextureFilter@0",
    choices=("aniso 2x", "aniso 4x", "aniso 8x", "aniso 16x"),
    default_value="aniso 8x",
    recommended_value="aniso 8x",
    current_impact="aniso 16x: Maximum filtering, spent on surfaces nobody reads a target off",
    recommended_impact="aniso 8x: The game's own tier — distant ground stays legible, frames stay",
    effect="Holds anisotropic filtering at the game's own tier",
    # Was raised to 16x on "costs almost nothing", against its own
    # `fps_gpu_bound: -1-2%`. Almost nothing is not nothing, and raising above
    # the game's default is the exception that has to be argued as something the
    # player reads. Ground texture at range is not that.
    impact_scores={"fps_gpu_bound": "+1-2%", "stability": "high"},
    category_order=14,
    scope=SettingScope.RECOMMENDED,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)


# --------------------------------------------------------------------------
# Decoration that can be spent without costing information
# --------------------------------------------------------------------------

MW4_VOLUMETRIC_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:volumetric_quality",
    display_name="MW4 Volumetric Quality",
    short_name="MW4 Volumetric Quality",
    description="Quality of volumetric fog, god rays and light shafts. Lowering it both returns "
    "frames and clears the air between the player and anything moving in it.",
    key="VolumetricQuality@0",
    choices=("QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"),
    default_value="QUALITY_MEDIUM",
    recommended_value="QUALITY_LOW",
    current_impact="QUALITY_MEDIUM: Dense fog volumes cost frames and obscure movement at range",
    recommended_impact="QUALITY_LOW: Clearer sightlines through fog and smoke, frames returned",
    effect="Thins volumetric fog so movement stays visible through it",
    impact_scores={"fps": "+4-8%", "stability": "high"},
    category_order=20,
    # One of the rare settings that gains information and frames at once, so it
    # is not held back to COMPLETE despite changing the image.
    scope=SettingScope.RECOMMENDED,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_REFLECTION_PROBE_HALF_RES = _make_mw4_setting(
    setting_id="game_config:mw4:reflection_probe_half_res",
    display_name="MW4 Half-Resolution Reflection Probes",
    short_name="MW4 Half-Resolution Reflection Probes",
    description="Renders the cubemap reflections on glass, metal and water at half resolution. "
    "Reflections carry nothing a player acts on, which makes them one of the cheapest things "
    "in the file to spend.",
    key="ReflectionProbeHalfResolution@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Full-resolution probes updating every frame for a decorative effect",
    recommended_impact="true: Half-resolution probes — reflections stay present, cost halves",
    effect="Halves reflection probe resolution",
    impact_scores={"fps": "+2-5%", "stability": "high"},
    category_order=21,
    scope=SettingScope.RECOMMENDED,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)


# --------------------------------------------------------------------------
# Guards: settings already correct, kept so drift is detected and undone
# --------------------------------------------------------------------------

MW4_RECOMMENDED_SET = _make_mw4_setting(
    setting_id="game_config:mw4:recommended_set",
    display_name="MW4 Keep Custom Settings",
    short_name="MW4 Keep Custom Settings",
    description="Marks the config as user-configured. The file's own comment states that a "
    "value of 0 makes the game reset every setting back to its recommended defaults, which "
    "would discard the whole tuned configuration on the next launch.",
    key="RecommendedSet@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Custom settings survive launch — this is the safe state",
    recommended_impact="true: Guards every other MW4 tweak against being reset by the game",
    effect="Keeps the game from resetting settings to its own recommendations",
    impact_scores={"fps_retained": "100%", "stability": "high"},
    category_order=1,
    # RECOMMENDED, not ESSENTIAL, even though it protects every other setting
    # here. It is a guard: recommended equals default by design, so it changes
    # nothing on a machine that is already correct. MW3 learned the same rule —
    # promoting no-ops fills the conservative preset with settings that do not
    # do anything, which is what `test_essential_stays_small` exists to catch.
    evidence_level="proven",
)

MW4_CLOUD_STORAGE = _make_mw4_setting(
    setting_id="game_config:mw4:cloud_storage",
    display_name="MW4 Cloud Config Storage",
    short_name="MW4 Cloud Config Storage",
    description="Syncs the local config with Activision's cloud copy. While it is on, a cloud "
    "copy written from another machine or an earlier session can overwrite the settings applied "
    "here without warning.",
    key="ConfigCloudStorageEnabled@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: A remote copy can overwrite local settings on launch",
    recommended_impact="false: The local file is the single source of truth",
    effect="Stops cloud sync from overwriting local settings",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=2,
    scope=SettingScope.RECOMMENDED,
    evidence_level="proven",
)

MW4_HW_CHANGE_DETECTION = _make_mw4_setting(
    setting_id="game_config:mw4:hw_change_detection",
    display_name="MW4 Hardware Change Auto-Detect",
    short_name="MW4 Hardware Change Auto-Detect",
    description="Re-runs the game's automatic quality detection whenever it notices a hardware "
    "or driver change. A driver update is enough to trigger it, and the re-detect overwrites "
    "tuned values with the game's own preset.",
    key="DisableHWChangeDetection@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: A driver update can silently reset graphics settings to a preset",
    recommended_impact="true: Auto-detect disabled — tuned values survive driver updates",
    effect="Stops automatic re-detection from overwriting tuned settings",
    impact_scores={"fps_retained": "100%", "stability": "high"},
    category_order=3,
    scope=SettingScope.RECOMMENDED,
    evidence_level="proven",
)


def create_mw4_menu_fps_cap_setting(max_hz: int) -> SettingExecutor:
    """Build the MW4 menu frame cap from the attached panel's own maximum.

    The cap is thermal, not visual: a menu is a static screen, and frames spent
    on it are heat still in the chassis when the match starts (consequence 4).

    Derived rather than fixed for the reason a constant is always wrong
    somewhere — a 120 cap on a 60 Hz panel never binds, so the GPU renders 60
    frames a second the display then discards, which is the exact waste the cap
    exists to stop. 90 is the ceiling because a menu does not get more
    responsive above it.
    """
    target = min(90, max_hz)
    return _make_mw4_setting(
        setting_id="game_config:mw4:fps_cap_menu",
        display_name="MW4 Menu Frame Cap",
        short_name="MW4 Menu Frame Cap",
        description="Frame limit while sitting in a menu or lobby. Menus are static screens, so "
        "frames spent on them buy nothing and leave heat the machine is still carrying when the "
        "match starts.",
        key="MaxFpsInMenu@0",
        choices=(),
        value_type=SettingValueType.INT,
        default_value=target,
        recommended_value=target,
        min_value=30,
        max_value=300,
        current_impact="Uncapped or above the panel rate: heat spent rendering a static screen",
        recommended_impact=f"{target}: Menu rendering capped to what the panel can show",
        effect="Caps menu rendering so heat is not spent before the match",
        # Thermal, not fps: this buys no frames. The figure carried is the cap
        # itself, because how much heat it avoids depends on what the uncapped
        # rate would have been on that particular GPU — which is not measured.
        impact_scores={"fps_menu_ceiling": target, "stability": "high"},
        category_order=30,
        scope=SettingScope.RECOMMENDED,
        evidence_level="proven",
    )


def create_mw4_fps_cap_setting(max_hz: int) -> SettingExecutor:
    """Build the MW4 in-game frame cap from the attached panel's max refresh.

    The cap comes from ``frame_cap_for_refresh`` rather than being written out
    here, so the driver cap, the in-game cap and the measurement target are one
    rule — when they disagree, the lower one silently wins and the other looks
    broken.
    """
    target = frame_cap_for_refresh(max_hz)
    return _make_mw4_setting(
        setting_id="game_config:mw4:fps_cap_ingame",
        display_name="MW4 In-Game Frame Rate Limit",
        short_name="MW4 In-Game Frame Rate Limit",
        description="Maximum frames per second during a match. Held just below the panel's "
        "refresh rate so a variable-refresh display never reaches its ceiling, which is where "
        "tearing and latency spikes come back.",
        key="MaxFpsInGame@0",
        choices=(),
        value_type=SettingValueType.INT,
        default_value=target,
        recommended_value=target,
        min_value=30,
        max_value=300,
        current_impact="Above or far below the panel rate: frames discarded, or the panel underused",
        recommended_impact=f"{target}: Full use of the panel with VRR headroom kept",
        effect="Matches the in-game frame cap to the attached monitor",
        impact_scores={"fps": f"ceiling {target}", "latency_ms": -2.0},
        category_order=29,
        scope=SettingScope.ESSENTIAL,
        evidence_level="proven",
    )


def create_mw4_vram_scale_setting(vram_mb: int) -> SettingExecutor:
    """Build the MW4 VRAM budget for the detected card.

    The share a card can safely hand the game is not a constant. On an 8 GB card
    the OS, the desktop and any overlay leave little room and saturation shows up
    as texture swapping and stutter; the same 70% on a 24 GB card strands 7 GB
    the game could have used.

    Raises when VRAM is unknown, because there is no honest answer then — the
    same rule MW3's sibling learned, where a fabricated fallback told a 6 GB card
    it had 10.
    """
    if not vram_mb or vram_mb <= 0:
        raise ValueError(
            "vram_scale needs the card's actual VRAM; the caller must read it "
            "rather than register a guess about the user's hardware"
        )

    gb = vram_mb / 1024
    if gb <= 8:
        target, pct = "0.700000", 70
    elif gb <= 12:
        target, pct = "0.850000", 85
    else:
        target, pct = "0.950000", 95

    label = f"{gb:.0f} GB"
    return _make_mw4_setting(
        setting_id="game_config:mw4:vram_scale",
        display_name="MW4 VRAM Budget",
        short_name="MW4 VRAM Budget",
        description=f"Share of GPU memory the game may consume. The card detected here has "
        f"{label}, so {pct}% leaves the desktop and any overlay the room they need without "
        f"stranding memory the game could be using for textures.",
        key="VideoMemoryScaleMP@0",
        # A range, not an enumeration — the file says `// 0.000000 to 2.000000`
        # and never `one of`. Declaring a list of tidy fractions here made the
        # setting unverifiable on the first machine that held a value between
        # them: this config read 0.750000, which no such list contains, and
        # detection is forbidden from returning a value outside `choices` (C6).
        choices=(),
        value_type=SettingValueType.FLOAT,
        min_value=0.0,
        max_value=2.0,
        # Derived, so there is no separate stock value to restore to.
        default_value=target,
        recommended_value=target,
        current_impact="Too high for the card: VRAM saturates → texture swapping and stutter",
        recommended_impact=f"{pct}%: Headroom sized to a {label} card — nothing swapped, nothing stranded",
        effect=f"Sizes the VRAM budget to the detected {label} card",
        impact_scores={"fps_1_percent_low": "+2-5%", "vram_mb": 0.0, "stability": "high"},
        category_order=35,
        scope=SettingScope.RECOMMENDED,
        evidence_level="likely",
        sources=_MW3_MEASURED,
    )


MW4_FPS_CAP_OUT_OF_FOCUS = _make_mw4_setting(
    setting_id="game_config:mw4:fps_cap_out_of_focus",
    display_name="MW4 Unfocused Frame Cap",
    short_name="MW4 Unfocused Frame Cap",
    description="Frame limit while the game window is not in focus. A game alt-tabbed to a "
    "browser has no reason to render at full rate, and every frame it does costs heat and "
    "power the foreground application wants.",
    key="MaxFpsOutOfFocus@0",
    choices=("5", "10", "30", "60", "120"),
    default_value="30",
    recommended_value="30",
    current_impact="30: Already capped when alt-tabbed — no heat spent on a hidden window",
    recommended_impact="30: Guards the cap against being raised by a patch or another tool",
    effect="Keeps an alt-tabbed match from rendering at full rate",
    impact_scores={"fps_unfocused_ceiling": 30, "stability": "high"},
    category_order=31,
    value_type=SettingValueType.INT,
    min_value=5,
    max_value=300,
    scope=SettingScope.RECOMMENDED,
    evidence_level="proven",
)

MW4_NVIDIA_REFLEX = _make_mw4_setting(
    setting_id="game_config:mw4:nvidia_reflex",
    display_name="MW4 NVIDIA Reflex",
    short_name="MW4 NVIDIA Reflex",
    description="NVIDIA's low-latency mode, which keeps the render queue short instead of "
    "letting frames accumulate ahead of the GPU. 'Enabled + boost' additionally holds GPU "
    "clocks up so a sudden frame does not wait for the card to spin back up.",
    key="NvidiaReflex@0",
    choices=("Disabled", "Enabled", "Enabled + boost"),
    default_value="Disabled",
    recommended_value="Enabled + boost",
    current_impact="Disabled: Render queue accumulates — roughly 10-20 ms of added input lag",
    recommended_impact="Enabled + boost: Short render queue and held clocks — lower input lag",
    effect="Shortens the render queue and holds GPU clocks for input latency",
    impact_scores={"latency_ms": -3, "stability": "high"},
    category_order=4,
    scope=SettingScope.ESSENTIAL,
    evidence_level="proven",
    sources=_MW3_MEASURED,
    applicable_conditions={"gpu_vendor": "nvidia"},
)


# No static entries for the frame caps or the VRAM budget. Their whole value is
# that the number suits *this* panel and *this* card, so a machine whose monitor
# or VRAM cannot be read gets no setting rather than a sentence about hardware it
# does not have — the same rule as `network:<n>:rss_queues` and MW3's siblings.
# `fpstune.settings.discovery.games_mw4.discover_mw4_display_settings` registers them.
# --------------------------------------------------------------------------
# Phase B2 — decoration, spent because nothing a player acts on is in it
# --------------------------------------------------------------------------

MW4_MOTION_BLUR = _make_mw4_setting(
    setting_id="game_config:mw4:motion_blur",
    display_name="MW4 Motion Blur",
    short_name="MW4 Motion Blur",
    description="Smears the scene along the direction of movement. It is the clearest case in "
    "the file of an effect that costs frames to make a moving target harder to resolve.",
    key="MotionBlur@0",
    choices=("Off", "On", "Cinematic Only"),
    default_value="Cinematic Only",
    recommended_value="Off",
    current_impact="Cinematic Only: Blur still applied during scripted sequences",
    recommended_impact="Off: Nothing smeared — a turning player stays sharp",
    effect="Removes scene motion blur",
    impact_scores={"fps": "+2-4%", "target_clarity": "improved"},
    category_order=40,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_WEAPON_MOTION_BLUR = _make_mw4_setting(
    setting_id="game_config:mw4:weapon_motion_blur",
    display_name="MW4 Weapon Motion Blur",
    short_name="MW4 Weapon Motion Blur",
    description="Applies motion blur to the weapon model itself while it moves. It blurs the "
    "part of the screen the player is aiming with and returns nothing for it.",
    key="WeaponMotionBlur@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: The weapon smears whenever the view turns",
    recommended_impact="false: Weapon stays sharp through every turn",
    effect="Removes weapon motion blur",
    impact_scores={"fps": "+1-3%", "target_clarity": "improved"},
    category_order=41,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_VELOCITY_BLUR = _make_mw4_setting(
    setting_id="game_config:mw4:velocity_blur",
    display_name="MW4 Velocity-Based Blur",
    short_name="MW4 Velocity-Based Blur",
    description="Adds a radial blur that grows with player speed. Sprinting is exactly when a "
    "player most needs to read the edges of the screen, and this is what softens them.",
    key="EnableVelocityBasedBlur@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Screen edges blur while sprinting — peripheral movement lost",
    recommended_impact="false: Full clarity at speed",
    effect="Removes speed-based radial blur",
    impact_scores={"fps": "+1-2%", "target_visibility": "improved"},
    category_order=42,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_DEPTH_OF_FIELD = _make_mw4_setting(
    setting_id="game_config:mw4:depth_of_field",
    display_name="MW4 Depth of Field",
    short_name="MW4 Depth of Field",
    description="Blurs whatever the camera is not focused on. In a first-person shooter the "
    "thing out of focus is usually the distance, which is where the targets are.",
    key="DofEnable@0",
    choices=("Off", "On", "Script"),
    default_value="Script",
    recommended_value="Off",
    current_impact="Script: The game blurs the distance whenever a scripted moment asks it to",
    recommended_impact="Off: The whole depth of the scene stays readable",
    effect="Disables depth of field entirely",
    impact_scores={"fps": "+2-5%", "target_visibility": "improved"},
    category_order=43,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_DOF_WEAPON = _make_mw4_setting(
    setting_id="game_config:mw4:dof_weapon",
    display_name="MW4 Weapon Depth of Field",
    short_name="MW4 Weapon Depth of Field",
    description="Blurs the weapon model when the view focus shifts. Separate from world depth "
    "of field, and left enabled it keeps blurring even after the world effect is off.",
    key="DofWeaponDisable@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Weapon still blurs on focus changes",
    recommended_impact="true: Weapon depth of field off — iron sights stay legible",
    effect="Disables weapon depth of field",
    impact_scores={"fps": "+1-2%", "target_clarity": "improved"},
    category_order=44,
    evidence_level="likely",
)

MW4_DOF_WORLD = _make_mw4_setting(
    setting_id="game_config:mw4:dof_world",
    display_name="MW4 World Depth of Field",
    short_name="MW4 World Depth of Field",
    description="Blurs the world outside the focal plane. This is the switch that survives when "
    "the main depth-of-field control is set to Script rather than Off.",
    key="DofWorldDisable@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: The world still blurs outside the focal plane",
    recommended_impact="true: Distance stays sharp regardless of focus",
    effect="Disables world depth of field",
    impact_scores={"fps": "+1-3%", "target_visibility": "improved"},
    category_order=45,
    evidence_level="likely",
)

MW4_DOF_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:dof_quality",
    display_name="MW4 Depth of Field Quality",
    short_name="MW4 Depth of Field Quality",
    description="Sample count of the depth-of-field filter. It only costs anything while depth "
    "of field is on, which makes High the most expensive setting in the file to leave behind.",
    key="DepthOfFieldQuality@0",
    choices=("Low", "High"),
    default_value="High",
    recommended_value="Low",
    current_impact="High: Full-quality filter running on an effect that hides targets",
    recommended_impact="Low: Cheapest filter — matters only if depth of field is re-enabled",
    effect="Lowers the depth-of-field filter cost",
    impact_scores={"fps": "+1-2%", "stability": "high"},
    category_order=46,
    evidence_level="likely",
)

MW4_WEATHER_GRID = _make_mw4_setting(
    setting_id="game_config:mw4:weather_grid",
    display_name="MW4 Weather Grid Volumes",
    short_name="MW4 Weather Grid Volumes",
    description="Volumetric rain, snow and fog density grids. Weather volumes sit between the "
    "player and everything else, so turning them off returns both frames and sightlines.",
    key="WeatherGridVolumesQuality@0",
    choices=("Off", "Low", "Medium", "High", "Ultra"),
    default_value="Low",
    recommended_value="Off",
    current_impact="Low: Weather volumes still drawn between the player and the target",
    recommended_impact="Off: Clear air — movement at range stays visible",
    effect="Removes volumetric weather effects",
    impact_scores={"fps": "+2-4%", "target_visibility": "improved"},
    category_order=47,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_SUBDIVISION = _make_mw4_setting(
    setting_id="game_config:mw4:subdivision",
    display_name="MW4 Geometry Subdivision",
    short_name="MW4 Geometry Subdivision",
    description="Catmull-Clark subdivision level, which smooths model silhouettes by adding "
    "geometry. It rounds edges the player never inspects and costs geometry throughput to do it.",
    key="SubdivisionLevel@0",
    choices=("0", "1", "2", "3", "4", "5", "6", "7", "8"),
    default_value="2",
    recommended_value="0",
    current_impact="2: Extra geometry generated to round silhouettes nobody reads",
    recommended_impact="0: No subdivision — geometry throughput returned to the frame",
    effect="Disables geometry subdivision",
    impact_scores={"fps": "+2-5%", "stability": "high"},
    category_order=48,
    evidence_level="likely",
)

MW4_SHADOW_FILTERING = _make_mw4_setting(
    setting_id="game_config:mw4:shadow_filtering",
    display_name="MW4 Shadow Filtering",
    short_name="MW4 Shadow Filtering",
    description="How softly shadow edges are blended. The shadow itself is information — one "
    "cast around a corner announces someone — but how soft its edge looks is not.",
    key="ShadowFilteringQuality@0",
    choices=("Low", "Medium", "High"),
    default_value="Medium",
    recommended_value="Low",
    current_impact="Medium: Filtering samples spent softening edges, not on the shadow existing",
    recommended_impact="Low: Shadows still cast and still readable, edges cheaper",
    effect="Lowers shadow edge filtering while keeping the shadows",
    impact_scores={"fps": "+2-4%", "stability": "high"},
    category_order=49,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_SHADER_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:shader_quality",
    display_name="MW4 Shader Quality",
    short_name="MW4 Shader Quality",
    description="Complexity of the material shaders the game compiles. Lowering it simplifies "
    "how surfaces respond to light, which changes how the scene looks without hiding anything "
    "that moves.",
    key="ShaderQuality@0",
    choices=("Default", "Medium", "Low"),
    default_value="Medium",
    recommended_value="Low",
    current_impact="Medium: Full material shading cost on surfaces, including static ones",
    recommended_impact="Low: Simpler materials — the largest single shading saving in the file",
    effect="Simplifies material shaders",
    impact_scores={"fps": "+4-8%", "visual_quality": "reduced"},
    category_order=50,
    # RECOMMENDED, corrected from COMPLETE. It changes how surfaces look, but it
    # *returns* frames and takes nothing a player acts on — no model, no shadow,
    # no effect that announces something. COMPLETE is for a setting that costs
    # the player information or spends frames; this does neither, and holding it
    # back was confusing "changes the image" with "costs the player something".
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_CINEMATIC_EMISSIVE = _make_mw4_setting(
    setting_id="game_config:mw4:cinematic_emissive",
    display_name="MW4 In-Game Cinematics",
    short_name="MW4 In-Game Cinematics",
    description="Plays the scripted cinematic sequences that interrupt gameplay. They are "
    "spectacle by definition and nothing in them is acted on.",
    key="CinematicEmissive@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Cinematic sequences play and are rendered in full",
    recommended_impact="false: Cinematics skipped — no render spent on a scene with no opponent",
    effect="Stops in-game cinematics from playing",
    impact_scores={"fps": "+0-2%", "stability": "high"},
    category_order=51,
    evidence_level="likely",
)

MW4_SHOW_BRASS = _make_mw4_setting(
    setting_id="game_config:mw4:show_brass",
    display_name="MW4 Ejected Casings",
    short_name="MW4 Ejected Casings",
    description="Draws the spent casings a weapon ejects while firing. They appear at the exact "
    "moment the player is tracking a target and carry nothing about where anyone is.",
    key="ShowBrass@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Casings spawn and physics-simulate during every burst",
    recommended_impact="false: No casings — fewer moving objects across the aim point",
    effect="Removes ejected weapon casings",
    impact_scores={"fps": "+1-2%", "target_clarity": "improved"},
    category_order=52,
    evidence_level="likely",
)

MW4_BLOOD_LIMIT = _make_mw4_setting(
    setting_id="game_config:mw4:blood_limit",
    display_name="MW4 Blood Effect Limit",
    short_name="MW4 Blood Effect Limit",
    description="Caps how quickly blood effects can stack, using the interval the game already "
    "carries. Blood confirms a hit, which is information — but stacked blood covers the target "
    "it confirms.",
    key="BloodLimit@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Effects stack without limit — sustained fire can obscure the target",
    recommended_impact="true: Hit confirmation kept, the pile-up that hides the target removed",
    effect="Limits how fast blood effects stack",
    impact_scores={"fps": "+1-3%", "target_visibility": "improved"},
    category_order=53,
    evidence_level="likely",
)

MW4_CORPSE_LIMIT = _make_mw4_setting(
    setting_id="game_config:mw4:corpse_limit",
    display_name="MW4 Corpse Limit",
    short_name="MW4 Corpse Limit",
    description="How many bodies stay in the world at once. Each is a full model still being "
    "drawn, and in a contested objective they accumulate exactly where the sightlines are.",
    key="CorpseLimit@0",
    choices=(),
    value_type=SettingValueType.INT,
    default_value=8,
    recommended_value=8,
    min_value=0,
    max_value=28,
    current_impact="28: Every body in a contested area stays drawn and stays in the way",
    recommended_impact="8: Recent bodies still shown, the pile that blocks sightlines is not",
    effect="Caps how many bodies remain drawn",
    impact_scores={"fps_1_percent_low": "+2-5%", "target_visibility": "improved"},
    category_order=54,
    evidence_level="likely",
)

MW4_CORPSES_CULLING = _make_mw4_setting(
    setting_id="game_config:mw4:corpses_culling",
    display_name="MW4 Corpse Culling Threshold",
    short_name="MW4 Corpse Culling Threshold",
    description="How aggressively bodies are removed before the limit is reached. A lower value "
    "clears them sooner, which is the same gain as the limit above applied continuously.",
    key="CorpsesCullingThreshold@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.500000",
    recommended_value="0.500000",
    min_value=0.5,
    max_value=1.0,
    current_impact="0.750000: Bodies linger until the scene is already crowded",
    recommended_impact="0.500000: Cleared sooner — the earliest the game allows",
    effect="Culls bodies as early as the game permits",
    impact_scores={"fps_1_percent_low": "+1-3%", "target_visibility": "improved"},
    category_order=55,
    evidence_level="likely",
)

MW4_SKIP_SEASON_INTRO = _make_mw4_setting(
    setting_id="game_config:mw4:skip_season_intro",
    display_name="MW4 Season Intro Video",
    short_name="MW4 Season Intro Video",
    description="Plays the season trailer on launch. It costs load time on every session and "
    "nothing in it affects a match.",
    key="SkipSeasonIntroVideo@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: The season video plays before the menu is reachable",
    recommended_impact="true: Straight to the menu",
    effect="Skips the season intro video",
    impact_scores={"startup_speed": "+5-15s", "stability": "high"},
    category_order=56,
    evidence_level="proven",
)

MW4_MARKS_PLAYER_ONLY = _make_mw4_setting(
    setting_id="game_config:mw4:marks_player_only",
    display_name="MW4 Bullet Marks on Characters",
    short_name="MW4 Bullet Marks on Characters",
    description="Restricts bullet marks on characters to the local player's own shots. It "
    "removes decals, but it also removes the marks left by other players, which is a signal "
    "about who has been firing and from where.",
    key="MarksEntsPlayerOnly@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Every player's marks are drawn on every character",
    recommended_impact="true: Only your own marks drawn — fewer decals, and less about others",
    effect="Draws bullet marks on characters from your shots only",
    impact_scores={"fps": "+1-2%", "visual_quality": "reduced"},
    category_order=57,
    perceptible_cost=(
        "Other players' bullet marks stop appearing on characters — a signal about who has been firing, and from where, goes away."
    ),
    # COMPLETE, and stated plainly: unlike the rest of B2 this one can remove
    # information, so it is offered with that written down rather than applied by
    # default. Wall impacts (`BulletImpacts`) are a separate guard and stay on.
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)


# --------------------------------------------------------------------------
# Guards: already correct, kept so another optimiser's drift is caught
# --------------------------------------------------------------------------

MW4_SSR = _make_mw4_setting(
    setting_id="game_config:mw4:ssr",
    display_name="MW4 Screen Space Reflections",
    short_name="MW4 Screen Space Reflections",
    description="Reflections computed from what is already on screen, used on wet ground, glass "
    "and metal. They are expensive, they carry nothing a player acts on, and MW4 keeps the "
    "setting under two scope indices that have to agree.",
    # Named-compound (C8): two scopes, identical value lists, one concept.
    # Writing one and not the other leaves the setting half-applied.
    key=["SSRQuality@0", "SSRQuality@1"],
    choices=("Off", "Low", "Medium", "High"),
    default_value="Off",
    recommended_value="Off",
    current_impact="Off: No screen-space reflection pass — this is the correct state",
    recommended_impact="Off: Guards both scopes against a preset switching them back on",
    effect="Keeps screen-space reflections off in both scopes",
    impact_scores={"fps": "+3-6%", "stability": "high"},
    category_order=60,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_DXR_MODE = _make_mw4_setting(
    setting_id="game_config:mw4:dxr_mode",
    display_name="MW4 Ray Tracing",
    short_name="MW4 Ray Tracing",
    description="The master switch for DirectX Raytracing. Ray-traced lighting is the most "
    "expensive option the game offers and changes nothing about what a player can see coming.",
    key="DxrMode@0",
    choices=("Off", "On"),
    default_value="Off",
    recommended_value="Off",
    current_impact="Off: No ray tracing — the correct state for a competitive target",
    recommended_impact="Off: Guards against a driver preset or a patch enabling it",
    effect="Keeps ray tracing off",
    impact_scores={"fps": "+25-45%", "stability": "high"},
    category_order=61,
    evidence_level="proven",
    sources=_MW3_MEASURED,
)

MW4_DXR_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:dxr_quality",
    display_name="MW4 Ray Tracing Quality",
    short_name="MW4 Ray Tracing Quality",
    description="Quality tier used when ray tracing is on. MW4 stores it under a second scope "
    "with its own value list, so it can sit at a high tier while the master switch reads Off.",
    key="DxrMode@1",
    choices=("Off", "Low", "Medium", "High", "Ultra"),
    default_value="Off",
    recommended_value="Off",
    current_impact="Off: No quality tier armed behind the master switch",
    recommended_impact="Off: Guards the second scope, which the master switch does not cover",
    effect="Keeps the ray tracing quality tier off",
    impact_scores={"fps": "+25-45%", "stability": "high"},
    category_order=62,
    evidence_level="likely",
)

MW4_TESSELLATION = _make_mw4_setting(
    setting_id="game_config:mw4:tessellation",
    display_name="MW4 Tessellation",
    short_name="MW4 Tessellation",
    description="Adds surface geometry to make flat textures look raised. It costs geometry "
    "throughput to change the shape of walls, and nothing a player reacts to is on a wall.",
    key="Tessellation@0",
    choices=("0_Off", "1_Near", "2_All"),
    default_value="0_Off",
    recommended_value="0_Off",
    current_impact="0_Off: No tessellation pass — this is the correct state",
    recommended_impact="0_Off: Guards against a preset re-enabling it",
    effect="Keeps tessellation off",
    impact_scores={"fps": "+3-7%", "stability": "high"},
    category_order=63,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_WATER_CAUSTICS = _make_mw4_setting(
    setting_id="game_config:mw4:water_caustics",
    display_name="MW4 Water Caustics",
    short_name="MW4 Water Caustics",
    description="Simulates the rippling light patterns water casts on nearby surfaces. It is one "
    "of the purest decorations in the file — an effect with no gameplay consequence at all.",
    key="WaterCausticsMode@0",
    choices=("Off", "Low Quality", "High Quality"),
    default_value="Off",
    recommended_value="Off",
    current_impact="Off: No caustics simulation — this is the correct state",
    recommended_impact="Off: Guards against a preset switching it back on",
    effect="Keeps water caustics off",
    impact_scores={"fps": "+1-3%", "stability": "high"},
    category_order=64,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_WATER_WAVE_WETNESS = _make_mw4_setting(
    setting_id="game_config:mw4:water_wave_wetness",
    display_name="MW4 Persistent Wave Wetness",
    short_name="MW4 Persistent Wave Wetness",
    description="Keeps static geometry visibly wet after waves wash over it. The effect persists "
    "long after the wave, so it is still being maintained while nothing is happening.",
    key="WaterWaveWetness@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: No persistent wetness maintained — this is the correct state",
    recommended_impact="false: Guards against a preset re-enabling it",
    effect="Keeps persistent wave wetness off",
    impact_scores={"fps": "+0-2%", "stability": "high"},
    category_order=65,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_PERSISTENT_DAMAGE = _make_mw4_setting(
    setting_id="game_config:mw4:persistent_damage",
    display_name="MW4 Persistent Damage Layer",
    short_name="MW4 Persistent Damage Layer",
    description="Keeps bullet holes and scorch marks on surfaces instead of fading them out. "
    "The marks say where fire has been coming from, which makes this information rather than "
    "decoration despite looking like the latter.",
    key="PersistentDamageLayer@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Damage marks persist — a wall shows where it has been shot from",
    recommended_impact="true: Guards a signal an aggressive preset would remove",
    effect="Keeps persistent damage marks on surfaces",
    # MW3 guards this at true and was right to. The B2 plan listed it as a tweak;
    # reading the setting again, what turning it off removes is where fire came
    # from, which is consequence 5's own example of information.
    impact_scores={"fps": "0 to -2%", "target_visibility": "preserved"},
    category_order=66,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)
# --------------------------------------------------------------------------
# Phase B3 — what must not be lowered, and the one thing to raise
#
# These exist to catch another optimiser, a guide, or an earlier fpstune release
# lowering something the player needs. Consequence 2: leaving a default alone is
# a legitimate answer, and a guard that never fires is still doing its job.
#
# The ruling behind this phase (2026-08-23): where MW3's shipped value and
# CLAUDE.md's consequence 5 disagreed, the product contract wins, and MW3 is
# corrected rather than copied. The distinction doing the work is that **the
# presence of a shadow is information and its softness is decoration** — which
# is why `ShadowFilteringQuality` is lowered in B2 and `ShadowQuality` is guarded
# here.
# --------------------------------------------------------------------------

MW4_MODEL_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:model_quality",
    display_name="MW4 Model Quality",
    short_name="MW4 Model Quality",
    description="Geometric detail on character and weapon models. This decides how much of an "
    "opponent is actually drawn at range, which makes it information rather than polish — and "
    "information has a tier at which it is carried, not a tier at the top of the list.",
    key="ModelQuality@0",
    choices=("Low Quality", "Medium Quality", "High Quality"),
    default_value="Medium Quality",
    recommended_value="Medium Quality",
    current_impact="High Quality: Detail past what identifies a shape, bought with 3-6% of frames",
    recommended_impact="Medium Quality: A shape at range stays identifiable, at the game's own tier",
    effect="Holds character model detail at the tier that keeps a target identifiable",
    # Was High Quality. Raising above the game's own default is the exception,
    # and this one did not clear the bar: Medium already draws an opponent as an
    # identifiable shape, so High buys geometry the player does not read. Low is
    # the wrong direction — that is where the channel actually starts to go.
    impact_scores={"fps": "+3-6%", "target_visibility": "preserved"},
    category_order=70,
    perceptible_cost=(
        "Characters and objects render at reduced model detail; at long range, identification takes a beat longer."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    value_hints={
        "Low Quality": "Distant models simplified to where a shape stops being readable",
        "Medium Quality": "Recommended — identifiable at range, nothing spent above that",
        "High Quality": "For a machine already at its frame-rate target",
    },
)

MW4_PARTICLE_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:particle_quality",
    display_name="MW4 Particle Quality",
    short_name="MW4 Particle Quality",
    description="Detail of smoke, tracers, muzzle flash and grenade effects. A thrown grenade "
    "and a fired weapon are both announced by their particles, so this is a channel the player "
    "reads rather than an effect they merely see.",
    key="ParticleQuality@0",
    choices=("very low", "low", "medium", "high"),
    default_value="medium",
    recommended_value="low",
    current_impact="medium: Effect density past what tells smoke from flash from tracer",
    recommended_impact="low: Each effect still reads as what it is, at a tier below the default",
    effect="Holds effect detail at the tier that still announces a grenade",
    # The channel is which effect it is, not how many particles it has. `low`
    # still draws smoke, tracer and muzzle flash distinctly; `very low` is where
    # the game starts culling them, and culling is what loses the fight.
    impact_scores={"fps": "+0-3%", "ability_readability": "preserved"},
    category_order=71,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    value_hints={
        "very low": "Effects start being culled — the announcement goes with them",
        "low": "Recommended — smoke, flash and tracer still tell themselves apart",
    },
)

MW4_WORLD_STREAMING = _make_mw4_setting(
    setting_id="game_config:mw4:world_streaming",
    display_name="MW4 World Streaming Quality",
    short_name="MW4 World Streaming Quality",
    description="How aggressively the game streams world geometry and textures in ahead of the "
    "player. What pop-in costs is a moment of blurred scenery when the view swings; what it "
    "does not cost is a player model, which is streamed on its own budget.",
    key="WorldStreamingQuality@0",
    choices=("Low", "High"),
    default_value="High",
    recommended_value="Low",
    current_impact="High: Streaming runs further ahead than the view uses, for 2% of frames",
    recommended_impact="Low: Scenery may settle a moment later — an opponent is unaffected",
    effect="Lowers how far world streaming runs ahead of the view",
    # Held at High on a pop-in argument, and pop-in is scenery. The information
    # case never applied: MW3 recommends Low for the same concept, and that
    # disagreement between two games running the same engine family was the tell.
    impact_scores={"fps": "+0-2%", "target_visibility": "preserved"},
    category_order=72,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_SHADOW_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:shadow_quality",
    display_name="MW4 Shadow Quality",
    short_name="MW4 Shadow Quality",
    description="Resolution and draw distance of the shadow maps. A shadow cast around a corner "
    "is one of the few ways a player learns about someone they cannot see, so the shadow "
    "existing is information — how softly its edge is filtered is not, and that is lowered "
    "separately.",
    key="ShadowQuality@0",
    choices=("Very_Low", "Low", "Medium", "High", "Very_High"),
    default_value="Medium",
    recommended_value="Low",
    current_impact="Medium: Shadow map resolution past what makes a corner shadow readable",
    recommended_impact="Low: A shadow around a corner still announces someone, drawn cheaper",
    effect="Holds shadows at the tier that still gives a corner away",
    # The information is *that a shadow is there*, and `Low` still casts and
    # still draws at distance. `Very_Low` is where the draw distance collapses
    # and the corner stops announcing anything, which is the floor rather than
    # the target.
    impact_scores={"fps": "+0-4%", "target_visibility": "preserved"},
    category_order=73,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    value_hints={
        "Very_Low": "Draw distance collapses — the corner stops giving anyone away",
        "Low": "Recommended — the shadow is there, nothing spent sharpening it",
    },
)

MW4_SCREEN_SPACE_SHADOWS = _make_mw4_setting(
    setting_id="game_config:mw4:screen_space_shadows",
    display_name="MW4 Screen Space Shadows",
    short_name="MW4 Screen Space Shadows",
    description="Fine contact shadows where a model meets a surface, computed from the screen "
    "buffer. These sharpen how a body sits in the world; they are not the corner shadow that "
    "gives a position away, which comes from the shadow maps instead.",
    key="ScreenSpaceShadowQuality@0",
    choices=("Off", "Low", "High"),
    default_value="Low",
    recommended_value="Low",
    current_impact="High: Contact shadowing past the tier at which a silhouette reads",
    recommended_impact="Low: The cheapest tier that still keeps the channel, whatever it carries",
    effect="Holds contact shadowing at its lowest drawn tier",
    impact_scores={"fps": "0 to -3%", "target_visibility": "preserved"},
    category_order=74,
    # Held at `Low` rather than `Off`, and the reason is an unresolved
    # disagreement rather than confidence. This description says the shadow that
    # gives a position away comes from the shadow maps, so contact shadowing is
    # decoration. MW3's sibling says the opposite — "critical for enemy
    # silhouette visibility" — about the same key in the same engine family, and
    # one of the two is wrong. Nobody has measured which.
    #
    # `Low` is the answer that does not depend on winning that argument: it is
    # the lowest tier at which the channel still exists, so it is correct under
    # the sharpened rule either way. `Off` would have bet on this file's reading.
    # See tasks.md D4 — this needs a measurement, not a stronger opinion.
    evidence_level="likely",
)

MW4_AMBIENT_LIGHTING = _make_mw4_setting(
    setting_id="game_config:mw4:ambient_lighting",
    display_name="MW4 Ambient Lighting Quality",
    short_name="MW4 Ambient Lighting Quality",
    description="Quality of the indirect, bounced lighting that fills shadowed areas. Turning "
    "it off flattens the scene, and a flat scene is where a prone body stops separating from "
    "the ground it is lying on.",
    key="AmbientLightingQuality@0",
    choices=("Off", "Low", "Medium", "High", "Ultra"),
    default_value="Low",
    recommended_value="Low",
    current_impact="Low: Indirect light present at its cheapest tier — shape still readable",
    recommended_impact="Low: Guards against Off, which flattens shadowed areas entirely",
    effect="Keeps enough indirect light for shapes to separate from the ground",
    impact_scores={"fps": "0 to -3%", "target_visibility": "preserved"},
    category_order=75,
    evidence_level="likely",
)

MW4_BULLET_IMPACTS = _make_mw4_setting(
    setting_id="game_config:mw4:bullet_impacts",
    display_name="MW4 Bullet Impacts",
    short_name="MW4 Bullet Impacts",
    description="Draws the impact effects where rounds strike surfaces. Impacts near cover are "
    "how a player works out the direction fire is coming from before seeing anyone.",
    key="BulletImpacts@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Impacts visible — incoming fire has a readable direction",
    recommended_impact="true: Guards a signal that a frames-first preset removes",
    effect="Keeps bullet impact effects visible",
    impact_scores={"fps": "0 to -2%", "target_visibility": "preserved"},
    category_order=76,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_SHOW_BLOOD = _make_mw4_setting(
    setting_id="game_config:mw4:show_blood",
    display_name="MW4 Blood Effects",
    short_name="MW4 Blood Effects",
    description="Draws blood on hit, which is the game's confirmation that a shot connected. "
    "The stacking that obscures a target is capped separately, so the confirmation can be kept "
    "without the pile-up.",
    key="ShowBlood@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Hits confirmed visually as well as through the hit marker",
    recommended_impact="true: Guards the confirmation; the blood limit handles the excess",
    effect="Keeps hit confirmation visible",
    impact_scores={"fps": "0 to -1%", "target_visibility": "preserved"},
    category_order=77,
    evidence_level="likely",
)

MW4_ST_LOD_SKIP = _make_mw4_setting(
    setting_id="game_config:mw4:st_lod_skip",
    display_name="MW4 LOD Skip",
    short_name="MW4 LOD Skip",
    description="How many levels of detail the renderer is allowed to skip on distant geometry. "
    "Every level skipped simplifies something further away, and what is further away in a "
    "shooter is usually the person about to shoot.",
    key="STLodSkip@0",
    choices=("0", "1", "2", "3", "4", "5"),
    default_value="0",
    recommended_value="0",
    current_impact="0: Nothing skipped — distant geometry drawn at its proper detail",
    recommended_impact="0: Guards against a guide that raises this for frames",
    effect="Keeps distant geometry at full detail",
    impact_scores={"fps": "0 to -4%", "target_visibility": "preserved"},
    category_order=78,
    evidence_level="likely",
)

MW4_SHADER_PRELOAD = _make_mw4_setting(
    setting_id="game_config:mw4:shader_preload",
    display_name="MW4 Offline Shader Preload",
    short_name="MW4 Offline Shader Preload",
    description="Compiles shaders ahead of time instead of during play. Without it the first "
    "encounter with an effect compiles its shader mid-frame, which is the traversal stutter "
    "that arrives in the middle of a fight.",
    key="EnableOfflineGameUpdater@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Shaders compiled before the match — no mid-fight compile stall",
    recommended_impact="true: Guards against an optimiser disabling it to save disk",
    effect="Keeps shaders compiled ahead of play",
    impact_scores={"stutter_reduction": "significant", "fps_1_percent_low": "+5-15%"},
    category_order=79,
    evidence_level="proven",
)

MW4_GPU_UPLOAD_HEAPS = _make_mw4_setting(
    setting_id="game_config:mw4:gpu_upload_heaps",
    display_name="MW4 GPU Upload Heaps",
    short_name="MW4 GPU Upload Heaps",
    description="Uses the Resizable BAR fast path to push more data straight into VRAM when the "
    "hardware supports it. It is a free win on any machine with the feature and inert on one "
    "without.",
    key="GPUUploadHeaps@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Resizable BAR path in use where the hardware offers it",
    recommended_impact="true: Guards a free transfer path against being switched off",
    effect="Keeps the Resizable BAR upload path enabled",
    impact_scores={"fps_1_percent_low": "+2-6%", "stability": "high"},
    category_order=80,
    evidence_level="likely",
)

MW4_VRS = _make_mw4_setting(
    setting_id="game_config:mw4:vrs",
    display_name="MW4 Variable Rate Shading",
    short_name="MW4 Variable Rate Shading",
    description="Shades low-contrast areas at a coarser rate while keeping detail where the eye "
    "is looking. It returns frames from regions a player is not reading anyway.",
    key="VRS@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Coarser shading on flat regions, full rate where detail matters",
    recommended_impact="true: Guards a saving that costs nothing a player looks at",
    effect="Keeps variable rate shading enabled",
    impact_scores={"fps": "+3-8%", "stability": "high"},
    category_order=81,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_DYNAMIC_SCENE_RESOLUTION = _make_mw4_setting(
    setting_id="game_config:mw4:dynamic_scene_resolution",
    display_name="MW4 Dynamic Resolution",
    short_name="MW4 Dynamic Resolution",
    description="Drops render resolution on the fly to hold a frame time target. It trades a "
    "steady image for a steady number, and the resolution drops hardest exactly when the scene "
    "gets busy — which is when a target needs to be resolved.",
    key="DynamicSceneResolution@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Resolution constant — the image does not soften under load",
    recommended_impact="false: Guards against a preset trading clarity for a smoother counter",
    effect="Keeps render resolution constant under load",
    impact_scores={"fps": "0 to -5%", "target_clarity": "preserved"},
    category_order=82,
    evidence_level="likely",
)

MW4_ABSOLUTE_TARGET_RESOLUTION = _make_mw4_setting(
    setting_id="game_config:mw4:absolute_target_resolution",
    display_name="MW4 Absolute Target Resolution",
    short_name="MW4 Absolute Target Resolution",
    description="Overrides the render target with a fixed resolution regardless of the display. "
    "Left at none the game renders for the panel it is on, which is what the rest of the "
    "display settings assume.",
    key="AbsoluteTargetResolution@0",
    choices=("540P", "640P", "720P", "900P", "1080P", "1440P", "native", "none"),
    default_value="none",
    recommended_value="none",
    current_impact="none: Render target follows the display — no override in effect",
    recommended_impact="none: Guards against an override that ignores the panel's resolution",
    effect="Keeps the render target following the display",
    impact_scores={"fps": "0%", "target_clarity": "preserved"},
    category_order=83,
    evidence_level="likely",
)

MW4_WEAPON_CYCLE_DELAY = _make_mw4_setting(
    setting_id="game_config:mw4:weapon_cycle_delay",
    display_name="MW4 Weapon Cycle Delay",
    short_name="MW4 Weapon Cycle Delay",
    description="Minimum delay enforced between mouse wheel weapon switches. Any value above "
    "zero puts a deliberate wait between the input and the swap, which is input latency added "
    "on purpose.",
    key="WeaponCycleDelay@0",
    choices=(),
    value_type=SettingValueType.INT,
    default_value=0,
    recommended_value=0,
    min_value=0,
    max_value=5000,
    current_impact="0: Weapon switches register as fast as the wheel is turned",
    recommended_impact="0: Guards against a delay being introduced between input and swap",
    effect="Keeps weapon switching free of an artificial delay",
    impact_scores={"latency_ms": 0.0, "input_precision": "preserved"},
    category_order=84,
    evidence_level="proven",
)
# --------------------------------------------------------------------------
# Phase B4 — audio: direction is information, a soundtrack is not
#
# Footstep direction is the single most acted-on channel in a shooter, and it
# competes for the same output as everything else. So the split here is not
# loud/quiet, it is **what tells you where someone is** versus what does not.
#
# Every volume control appears in *both* config files, under the same scope
# index and a different hash — so these carry `source_file="both"`. Measured
# 2026-08-23: changing the music volume in-game wrote 0.000000 to both files,
# which is how we know the game keeps them in step and a one-file write would be
# half-applied.
#
# All four reductions are COMPLETE, not RECOMMENDED. CLAUDE.md consequence 5 is
# explicit that a setting changing what the player can *hear* is offered with its
# cost written, never assumed — someone may well want the soundtrack.
# --------------------------------------------------------------------------

MW4_MUSIC_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:music_volume",
    display_name="MW4 Music Volume",
    short_name="MW4 Music Volume",
    description="Volume of the game's soundtrack. Music occupies the same output as footsteps "
    "and reloads, and it is the one competing sound the player never needs to locate.",
    key="MusicVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Soundtrack at full volume, masking quiet positional cues",
    recommended_impact="0.000000: Nothing between the player and a footstep",
    effect="Silences the soundtrack so positional audio is unmasked",
    impact_scores={"footstep_clarity": "improved", "fps": "0%"},
    category_order=90,
    perceptible_cost=(
        "In-game music goes silent — nothing tactical is lost, but the soundscape is barer."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)

MW4_WARTRACKS_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:wartracks_volume",
    display_name="MW4 War Tracks Volume",
    short_name="MW4 War Tracks Volume",
    description="Volume of the music tracks played from vehicles. It is a cosmetic feature "
    "players buy, and it masks the same cues the soundtrack does.",
    key="WarTracksVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Vehicle music competes with positional audio",
    recommended_impact="0.000000: War tracks silent",
    effect="Silences vehicle music tracks",
    impact_scores={"footstep_clarity": "improved", "fps": "0%"},
    category_order=91,
    perceptible_cost=(
        "War tracks go silent — nothing tactical is lost, but the soundscape is barer."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)

MW4_TELESCOPE_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:telescope_volume",
    display_name="MW4 Menu Feed Volume",
    short_name="MW4 Menu Feed Volume",
    description="Volume of the message-of-the-day feed that plays in the menus. It is "
    "promotional audio and never plays during a match.",
    key="TelescopeVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Menu feed plays over whatever else is running",
    recommended_impact="0.000000: Menus stay quiet",
    effect="Silences the menu message feed",
    impact_scores={"footstep_clarity": "unaffected", "fps": "0%"},
    category_order=92,
    perceptible_cost=(
        "Telescope ambience goes silent — nothing tactical is lost, but the soundscape is barer."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)

MW4_CINEMATIC_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:cinematic_volume",
    display_name="MW4 Cinematic Volume",
    short_name="MW4 Cinematic Volume",
    description="Volume of the scripted cinematic sequences. Pairs with the setting that stops "
    "those cinematics rendering at all, so that one is not left audible with no picture.",
    key="CinematicVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Cinematic audio plays at full volume",
    recommended_impact="0.000000: Cinematics silent, matching them not being rendered",
    effect="Silences cinematic audio",
    impact_scores={"footstep_clarity": "unaffected", "fps": "0%"},
    category_order=93,
    perceptible_cost=(
        "Cinematic audio goes silent — nothing tactical is lost, but the soundscape is barer."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)

MW4_ALT_SHELL_SHOCK = _make_mw4_setting(
    setting_id="game_config:mw4:alt_shell_shock",
    display_name="MW4 Muted Shell Shock",
    short_name="MW4 Muted Shell Shock",
    description="Replaces the ringing tinnitus effect after a flash or explosion with a muted "
    "one. The stock ringing sits directly on top of footstep frequencies for several seconds — "
    "which is exactly the window after a flashbang when knowing where someone is matters most.",
    key="AltShellShock@0",
    source_file="profile",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Ringing masks positional audio for seconds after every flash",
    recommended_impact="true: Muted effect — footsteps stay audible through a flash",
    effect="Replaces post-flash ringing with a muted effect",
    # RECOMMENDED, unlike the volume reductions above: this one *gains*
    # information rather than trading it, so there is nothing to offer a choice
    # about beyond preference for the effect itself.
    impact_scores={"footstep_clarity": "improved", "fps": "0%"},
    category_order=94,
    evidence_level="likely",
)

MW4_MUTE_LICENSED_MUSIC = _make_mw4_setting(
    setting_id="game_config:mw4:mute_licensed_music",
    display_name="MW4 Licensed Music",
    short_name="MW4 Licensed Music",
    description="Mutes the licensed tracks the game plays separately from its own score. It is "
    "a second music channel, unaffected by the soundtrack volume.",
    key="MuteLicensedMusic@0",
    source_file="profile",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Licensed tracks still play even with the score silenced",
    recommended_impact="true: The second music channel is off too",
    effect="Mutes licensed music tracks",
    impact_scores={"footstep_clarity": "improved", "fps": "0%"},
    category_order=95,
    perceptible_cost=(
        "Licensed music tracks go silent — nothing tactical is lost, but the soundscape is barer."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)

MW4_EFFECTS_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:effects_volume",
    display_name="MW4 Effects Volume",
    short_name="MW4 Effects Volume",
    description="Volume of the sound effects channel, which is where footsteps, reloads and "
    "weapon fire live. This is the channel every other audio setting exists to keep clear.",
    key="EffectsVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Positional audio at full volume — the correct state",
    recommended_impact="1.000000: Guards the channel the rest of the audio work protects",
    effect="Keeps positional audio at full volume",
    impact_scores={"footstep_clarity": "preserved", "fps": "0%"},
    category_order=96,
    evidence_level="proven",
)

MW4_HITMARKERS_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:hitmarkers_volume",
    display_name="MW4 Hit Marker Volume",
    short_name="MW4 Hit Marker Volume",
    description="Volume of the hit confirmation tone. It is the fastest feedback the game gives "
    "that a shot connected, which is what tells a player whether to keep firing at a shape.",
    key="HitMarkersVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Hits confirmed audibly — the correct state",
    recommended_impact="1.000000: Guards the fastest hit feedback the game has",
    effect="Keeps hit confirmation audible",
    impact_scores={"footstep_clarity": "unaffected", "fps": "0%"},
    category_order=97,
    evidence_level="proven",
)

MW4_VOICE_VOLUME = _make_mw4_setting(
    setting_id="game_config:mw4:voice_volume",
    display_name="MW4 Voice Volume",
    short_name="MW4 Voice Volume",
    description="Volume of character dialogue and the announcer. Announcer callouts carry "
    "information a player acts on — an enemy UAV overhead, a captured objective — so this is a "
    "channel rather than flavour.",
    key="VoiceVolume@0",
    source_file="both",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    min_value=0.0,
    max_value=1.0,
    current_impact="1.000000: Callouts audible — the correct state",
    recommended_impact="1.000000: Guards announcements that report the state of the match",
    effect="Keeps announcer callouts audible",
    impact_scores={"footstep_clarity": "unaffected", "fps": "0%"},
    category_order=98,
    evidence_level="proven",
)

MW4_MONO_SOUND = _make_mw4_setting(
    setting_id="game_config:mw4:mono_sound",
    display_name="MW4 Mono Audio",
    short_name="MW4 Mono Audio",
    description="Collapses stereo output to a single channel. It exists for accessibility, and "
    "turning it on removes the left/right difference that direction is read from — the single "
    "most destructive audio setting in the file for locating anyone.",
    key="MonoSound@0",
    source_file="profile",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Stereo separation intact — direction is readable",
    recommended_impact="false: Guards the channel separation direction depends on",
    effect="Keeps stereo separation so direction stays readable",
    impact_scores={"footstep_clarity": "preserved", "fps": "0%"},
    category_order=99,
    evidence_level="proven",
)


# --------------------------------------------------------------------------
# Phase B5 — input: what makes the same movement produce the same aim
#
# Almost all guards. Aim is muscle memory, and every setting here is a way for
# the same hand movement to produce a different result — which is the one thing
# practice cannot compensate for.
# --------------------------------------------------------------------------

MW4_MOUSE_ACCELERATION = _make_mw4_setting(
    setting_id="game_config:mw4:mouse_acceleration",
    display_name="MW4 Mouse Acceleration",
    short_name="MW4 Mouse Acceleration",
    description="Scales aim by how fast the mouse is moved, so the same distance produces a "
    "different turn depending on speed. It is the reason a flick that worked once does not "
    "work again, and no amount of practice makes it consistent.",
    key="MouseAcceleration@1",
    source_file="profile",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=10.0,
    current_impact="0.000000: Aim is one-to-one with hand movement — the correct state",
    recommended_impact="0.000000: Guards the property muscle memory is built on",
    effect="Keeps aim one-to-one with hand movement",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=100,
    evidence_level="proven",
)

MW4_MOUSE_FILTER = _make_mw4_setting(
    setting_id="game_config:mw4:mouse_filter",
    display_name="MW4 Mouse Filtering",
    short_name="MW4 Mouse Filtering",
    description="Averages mouse input over several samples. Averaging means the aim lags the "
    "hand, and the lag grows with the filter strength.",
    key="MouseFilter@1",
    source_file="profile",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=10.0,
    current_impact="0.000000: Every sample used as reported — the correct state",
    recommended_impact="0.000000: Guards against averaging that delays the aim",
    effect="Keeps mouse input unfiltered",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=101,
    evidence_level="proven",
)

MW4_MOUSE_SMOOTHING = _make_mw4_setting(
    setting_id="game_config:mw4:mouse_smoothing",
    display_name="MW4 Mouse Smoothing",
    short_name="MW4 Mouse Smoothing",
    description="Interpolates between mouse samples to make movement look smoother. What it "
    "smooths out is the small fast correction at the end of a flick, which is the part that "
    "lands the shot.",
    key="MouseSmoothing@1",
    source_file="profile",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Corrections register as made — the correct state",
    recommended_impact="false: Guards the fine correction at the end of a movement",
    effect="Keeps small aim corrections from being smoothed away",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=102,
    evidence_level="proven",
)

MW4_SPRINT_ASSIST_DELAY = _make_mw4_setting(
    setting_id="game_config:mw4:sprint_assist_delay",
    display_name="MW4 Sprint Assist Delay",
    short_name="MW4 Sprint Assist Delay",
    description="How long the player must hold a direction before sprint engages automatically. "
    "Any delay is time spent walking while intending to run, at the start of every rotation.",
    key="Sprint Assist Delay KBM@1",
    source_file="profile",
    choices=(),
    value_type=SettingValueType.INT,
    default_value=0,
    recommended_value=0,
    min_value=0,
    max_value=12750,
    current_impact="0: Sprint engages immediately — the correct state",
    recommended_impact="0: Guards against a delay between intent and movement",
    effect="Keeps sprint engaging without a wait",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=103,
    evidence_level="proven",
)

MW4_ADS_FOV_SCALING = _make_mw4_setting(
    setting_id="game_config:mw4:ads_fov_scaling",
    display_name="MW4 ADS Field of View Scaling",
    short_name="MW4 ADS Field of View Scaling",
    description="Keeps the field of view scaled with the player's setting while aiming down "
    "sights. With it off, aiming narrows the view to a fixed default and hides whatever was at "
    "the edges — at the moment the player is least able to turn.",
    key="ADSFovScaling@0",
    source_file="profile",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Field of view preserved while aiming — the correct state",
    recommended_impact="true: Guards peripheral vision at the moment of least mobility",
    effect="Keeps the field of view while aiming down sights",
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=104,
    evidence_level="likely",
)

MW4_FREE_LOOK = _make_mw4_setting(
    setting_id="game_config:mw4:free_look",
    display_name="MW4 Free Look",
    short_name="MW4 Free Look",
    description="Allows the view to turn independently of movement direction. Without it a "
    "player cannot check behind while retreating, which is when checking behind matters.",
    key="FreeLook@0",
    source_file="profile",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: View turns independently of movement — the correct state",
    recommended_impact="true: Guards the ability to look where you are not going",
    effect="Keeps view and movement independent",
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=105,
    evidence_level="proven",
)

MW4_GAMEPAD_AIM = _make_mw4_setting(
    setting_id="game_config:mw4:gamepad_aim",
    display_name="MW4 Gamepad Aiming",
    short_name="MW4 Gamepad Aiming",
    description="Restricts aiming to a gamepad stick rather than the mouse. Enabled on a "
    "mouse-and-keyboard machine it makes the mouse stop aiming entirely, which reads as the "
    "game being broken rather than as a setting.",
    key="EnableGamepad@0",
    source_file="profile",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Mouse aims — the correct state on this input setup",
    recommended_impact="false: Guards against aiming being handed to a stick",
    effect="Keeps aiming on the mouse",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=106,
    evidence_level="proven",
)

MW4_FOV = _make_mw4_setting(
    setting_id="game_config:mw4:fov",
    display_name="MW4 Field of View",
    short_name="MW4 Field of View",
    description="How much of the world is visible at once, from 60 to 120 degrees. A wider view "
    "shows more of what is beside the player and makes everything in it smaller and further "
    "away, so there is no value here that is correct for everyone.",
    key="Fov@1",
    source_file="profile",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="90.000000",
    recommended_value="90.000000",
    min_value=60.0,
    max_value=120.0,
    current_impact="90.000000: A middle setting — more than the console default, short of the maximum",
    recommended_impact="90.000000: Left where it is; the trade here is a preference, not a defect",
    effect="Leaves the field of view as a deliberate choice",
    # Guarded rather than recommended in either direction. Raising it gains
    # peripheral information and costs target size and frames; nothing measured
    # here says which side a given player should take, and consequence 5 says a
    # setting like that is offered, never assumed.
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=107,
    perceptible_cost=(
        "A wider view renders more of the world — targets appear smaller at the same distance."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)
# --------------------------------------------------------------------------
# Phase B6 — derived from this machine, and the heat settings
#
# Two things are deliberately *not* registered here, and the reasons matter more
# than the settings would have:
#
# `RendererWorkerCount` — the game computes it from the CPU it detected and
# documents no formula. fpstune would be inventing one, and a worker count that
# does not suit the machine is a stutter source rather than a frame gain. There
# is no honest derivation, so there is no setting.
#
# `HDR` — deciding it needs the panel's HDR capability, which is not in the
# monitor data fpstune reads. The game's own `Automatic` already asks the
# display, so it is guarded there rather than overridden by something that knows
# less than the game does.
# --------------------------------------------------------------------------


def create_mw4_resolution_setting(width: int, height: int) -> SettingExecutor:
    """Build the MW4 fullscreen resolution from the panel's native mode.

    Anything below native is upscaled by the display, and a display's scaler is
    the one in the chain nobody chose. Rendering at the panel's own mode is the
    only setting that skips it.
    """
    if width <= 0 or height <= 0:
        raise ValueError("resolution needs the panel's actual native mode")

    target = f"{width}x{height}"
    return _make_mw4_setting(
        setting_id="game_config:mw4:resolution",
        display_name="MW4 Fullscreen Resolution",
        short_name="MW4 Fullscreen Resolution",
        description="Resolution the game presents at. Below the panel's native mode the display "
        "scales the image itself, which softens every edge before the player sees it and costs "
        "nothing back.",
        key="Resolution@0",
        choices=(),
        value_type=SettingValueType.STRING,
        default_value=target,
        recommended_value=target,
        current_impact="Below native: the panel's own scaler softens the image after rendering",
        recommended_impact=f"{target}: The panel's native mode — no display-side scaling",
        effect="Matches the game resolution to the panel's native mode",
        impact_scores={"target_clarity": "preserved", "fps": "0%"},
        category_order=110,
        evidence_level="proven",
    )


def create_mw4_refresh_rate_setting(max_hz: int) -> SettingExecutor:
    """Build the MW4 refresh rate from the panel's own maximum.

    MW4 writes this as ``Auto:<hz>`` with three decimals, and the prefix is kept
    because it is the game's own spelling — the line carries no value list, so
    nothing here can validate a shape it invented.
    """
    if max_hz <= 0:
        raise ValueError("refresh rate needs the panel's actual maximum")

    target = f"Auto:{float(max_hz):.3f}"
    return _make_mw4_setting(
        setting_id="game_config:mw4:refresh_rate",
        display_name="MW4 Refresh Rate",
        short_name="MW4 Refresh Rate",
        description="Refresh rate the game drives the display at. Set below the panel's maximum "
        "it discards frames the monitor could have shown, which is the one loss no graphics "
        "setting can win back.",
        key="RefreshRate@0",
        choices=(),
        value_type=SettingValueType.STRING,
        default_value=target,
        recommended_value=target,
        current_impact="Below the panel's maximum: frames rendered and then never displayed",
        recommended_impact=f"{max_hz} Hz: Every frame the panel can show is shown",
        effect="Drives the panel at its own maximum refresh rate",
        impact_scores={"fps": f"ceiling {max_hz}", "latency_ms": -1.0},
        category_order=111,
        evidence_level="proven",
    )


MW4_ASPECT_RATIO = _make_mw4_setting(
    setting_id="game_config:mw4:aspect_ratio",
    display_name="MW4 Aspect Ratio",
    short_name="MW4 Aspect Ratio",
    description="Forces a specific aspect ratio regardless of the window. Anything other than "
    "auto either stretches the image or crops away the sides, and the sides are where movement "
    "is noticed first.",
    key="AspectRatio@0",
    choices=(
        "auto",
        "standard",
        "5:4",
        "wide 16:10",
        "wide 16:9",
        "wide 18:9",
        "wide 19.5:9",
        "wide 21:9",
        "wide 32:9",
    ),
    default_value="auto",
    recommended_value="auto",
    current_impact="auto: Ratio follows the display — the correct state",
    recommended_impact="auto: Guards against a forced ratio that stretches or crops",
    effect="Keeps the aspect ratio following the display",
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=112,
    evidence_level="proven",
)

MW4_DISPLAY_MODE = _make_mw4_setting(
    setting_id="game_config:mw4:display_mode",
    display_name="MW4 Display Mode",
    short_name="MW4 Display Mode",
    description="How the game occupies the screen. Borderless keeps the desktop compositor in "
    "the path but alt-tabs instantly and follows the desktop's resolution and refresh rate; "
    "exclusive fullscreen removes the compositor and costs those.",
    key="DisplayMode@0",
    choices=(
        "Windowed",
        "Fullscreen",
        "Fullscreen borderless window",
        "Fullscreen borderless extended window",
    ),
    default_value="Fullscreen borderless window",
    recommended_value="Fullscreen borderless window",
    current_impact="Fullscreen borderless window: instant alt-tab, VRR intact",
    recommended_impact="Fullscreen borderless window: guards against a mode switch that breaks alt-tab",
    effect="Keeps the game in borderless fullscreen",
    impact_scores={"latency_ms": 0.0, "ux": "high"},
    category_order=113,
    evidence_level="proven",
)

MW4_PREFERRED_DISPLAY_MODE = _make_mw4_setting(
    setting_id="game_config:mw4:preferred_display_mode",
    display_name="MW4 Preferred Display Mode",
    short_name="MW4 Preferred Display Mode",
    description="The mode the game returns to after a display change or a driver reset. It is "
    "read separately from the active mode, so leaving it behind undoes the mode above the next "
    "time the display is touched.",
    key="PreferredDisplayMode@0",
    choices=(
        "Fullscreen",
        "Fullscreen borderless window",
        "Fullscreen borderless extended window",
    ),
    default_value="Fullscreen borderless window",
    recommended_value="Fullscreen borderless window",
    current_impact="Fullscreen borderless window: matches the active mode",
    recommended_impact="Fullscreen borderless window: guards the mode across display changes",
    effect="Keeps the preferred mode matching the active one",
    impact_scores={"latency_ms": 0.0, "ux": "high"},
    category_order=114,
    evidence_level="likely",
)

MW4_VSYNC = _make_mw4_setting(
    setting_id="game_config:mw4:vsync",
    display_name="MW4 V-Sync",
    short_name="MW4 V-Sync",
    description="Holds each frame until the display is ready for it. On a variable-refresh panel "
    "the display already waits for the frame, so V-Sync only adds a queue — up to a full frame "
    "of input latency for tearing that was not happening.",
    key="VSync@0",
    choices=("disabled", "100%", "50%", "33%", "25%"),
    default_value="disabled",
    recommended_value="disabled",
    current_impact="disabled: No added frame queue — the correct state with VRR",
    recommended_impact="disabled: Guards against a preset adding a frame of input latency",
    effect="Keeps V-Sync off so no frame queue is added",
    impact_scores={"latency_ms": -8.0, "stability": "high"},
    category_order=115,
    evidence_level="proven",
    sources=_MW3_MEASURED,
)

MW4_VSYNC_MENU = _make_mw4_setting(
    setting_id="game_config:mw4:vsync_menu",
    display_name="MW4 Menu V-Sync",
    short_name="MW4 Menu V-Sync",
    description="V-Sync applied only in menus. Input latency does not matter on a menu, and "
    "capping there is one of the cheapest ways to stop the GPU heating the chassis before the "
    "match starts.",
    key="VSyncInMenu@0",
    choices=("disabled", "100%", "50%", "33%", "25%"),
    default_value="100%",
    recommended_value="100%",
    current_impact="100%: Menus synced — GPU idles instead of running flat out",
    recommended_impact="100%: Guards a thermal saving that costs nothing in a match",
    effect="Keeps menu rendering synced to the display",
    impact_scores={"fps_menu_ceiling": 0, "stability": "high"},
    category_order=116,
    evidence_level="proven",
    sources=_MW3_MEASURED,
)

MW4_CAP_FPS = _make_mw4_setting(
    setting_id="game_config:mw4:cap_fps",
    display_name="MW4 Custom Frame Cap",
    short_name="MW4 Custom Frame Cap",
    description="The master switch for every frame limit in this game. With it off the in-game, "
    "menu and unfocused caps are all inert, which is how a machine ends up rendering 900 frames "
    "a second of a lobby.",
    key="CapFps@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: The frame caps are in effect — the correct state",
    recommended_impact="true: Guards the switch every other cap depends on",
    effect="Keeps the frame limiter enabled",
    impact_scores={"fps_menu_ceiling": 0, "stability": "high"},
    category_order=117,
    evidence_level="proven",
)

MW4_DISPLAY_GAMMA = _make_mw4_setting(
    setting_id="game_config:mw4:display_gamma",
    display_name="MW4 Colour Space",
    short_name="MW4 Colour Space",
    description="Colour space the game outputs in. sRGB is what an ordinary SDR panel expects; "
    "the alternative targets a different transfer curve and makes shadowed areas read wrong on a "
    "display that is not set up for it.",
    key="DisplayGamma@0",
    choices=("BT709_sRGB", "BT709_BT1886"),
    default_value="BT709_sRGB",
    recommended_value="BT709_sRGB",
    current_impact="BT709_sRGB: Matches an ordinary SDR panel",
    recommended_impact="BT709_sRGB: Guards against a curve that darkens what is in shadow",
    effect="Keeps output in the colour space an SDR panel expects",
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=118,
    evidence_level="likely",
)

MW4_HDR = _make_mw4_setting(
    setting_id="game_config:mw4:hdr",
    display_name="MW4 HDR",
    short_name="MW4 HDR",
    description="Whether the game outputs high dynamic range. Automatic asks the display and "
    "acts on the answer, which is more than fpstune can do — the panel's HDR capability is not "
    "in the monitor data it reads.",
    key="HDR@0",
    choices=("Off", "On", "Automatic"),
    default_value="Automatic",
    recommended_value="Automatic",
    current_impact="Automatic: The game asks the display and acts on what it says",
    recommended_impact="Automatic: Guards against On being forced onto an SDR panel",
    effect="Leaves HDR to the game's own display query",
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=119,
    evidence_level="likely",
)


# --- Heat and wear: consequence 4, none of these buys a frame -------------

MW4_MENU_SCENE_RESOLUTION = _make_mw4_setting(
    setting_id="game_config:mw4:menu_scene_resolution",
    display_name="MW4 Menu Scene Resolution",
    short_name="MW4 Menu Scene Resolution",
    description="Drops the render resolution of the 3D scene behind non-interactive menus. "
    "Nothing in a menu is aimed at, so the pixels spent there are heat the machine still carries "
    "into the match.",
    key="SustainabilityMenuSceneResolution@0",
    choices=("off", "min", "full"),
    default_value="min",
    recommended_value="min",
    current_impact="min: Menu backdrops rendered cheaply — the correct state",
    recommended_impact="min: Guards a thermal saving with no in-match cost",
    effect="Keeps menu backdrops rendered at reduced resolution",
    # MW3's sibling recommends `full`. Kept at `min` here and the disagreement is
    # deliberate: nothing in a menu is a target, so the argument that protects
    # in-match clarity does not reach it, and consequence 4 says the heat is real.
    impact_scores={"fps_menu_ceiling": 0, "stability": "high"},
    category_order=120,
    evidence_level="likely",
)

MW4_REDUCE_QUALITY_IDLE = _make_mw4_setting(
    setting_id="game_config:mw4:reduce_quality_idle",
    display_name="MW4 Idle Quality Reduction",
    short_name="MW4 Idle Quality Reduction",
    description="Lowers rendering quality once the player has been idle. An idle player is by "
    "definition not looking for anyone, so the quality has nothing to show them.",
    key="SustainabilityReduceQualityIdle@0",
    choices=("off", "min", "full"),
    default_value="full",
    recommended_value="full",
    current_impact="full: Quality drops while idle — the correct state",
    recommended_impact="full: Guards a saving that only applies when nothing is happening",
    effect="Keeps quality reduction active while idle",
    impact_scores={"fps_unfocused_ceiling": 0, "stability": "high"},
    category_order=121,
    evidence_level="likely",
)

MW4_REDUCE_QUALITY_IDLE_DELAY = _make_mw4_setting(
    setting_id="game_config:mw4:reduce_quality_idle_delay",
    display_name="MW4 Idle Quality Delay",
    short_name="MW4 Idle Quality Delay",
    description="How long the player must be idle before quality drops. MW4 keeps this under a "
    "second scope of the same name as the switch above, with its own list of durations.",
    key="SustainabilityReduceQualityIdle@1",
    choices=("off", "10 minutes", "5 minutes", "1 minute", "30 seconds"),
    default_value="30 seconds",
    recommended_value="30 seconds",
    current_impact="30 seconds: The shortest wait the game offers — the correct state",
    recommended_impact="30 seconds: Guards the delay against being lengthened to no benefit",
    effect="Keeps the idle wait as short as the game allows",
    impact_scores={"fps_unfocused_ceiling": 0, "stability": "high"},
    category_order=122,
    evidence_level="likely",
)

MW4_PAUSE_RENDERING = _make_mw4_setting(
    setting_id="game_config:mw4:pause_rendering",
    display_name="MW4 Pause Rendering",
    short_name="MW4 Pause Rendering",
    description="Stops rendering entirely at the pause menu or when the window loses focus. The "
    "unfocused frame cap already covers the same ground at 30 fps, and a full stop has to rebuild "
    "the frame on the way back — a stutter at exactly the moment of returning to a match.",
    key="SustainabilityPauseRendering@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Unfocused rendering capped rather than stopped — no return stutter",
    recommended_impact="false: The frame cap covers this without the cost of resuming",
    effect="Leaves unfocused rendering to the frame cap rather than stopping it",
    impact_scores={"fps_unfocused_ceiling": 30, "stability": "high"},
    category_order=123,
    evidence_level="likely",
    sources=_MW3_MEASURED,
)

MW4_ECO_LOW_BATTERY = _make_mw4_setting(
    setting_id="game_config:mw4:eco_low_battery",
    display_name="MW4 Low Battery Mode",
    short_name="MW4 Low Battery Mode",
    description="Lowers high-impact settings when the battery runs down, to extend a session. It "
    "is a frame-rate ceiling that binds during a match, on a laptop, without announcing itself — "
    "the shape of tweak that costs more than any setting in this file gains.",
    key="UserEcoLowBatteryModeUI@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: No hidden ceiling during a match — the correct state",
    recommended_impact="false: Guards against a cap that binds mid-fight on battery",
    effect="Keeps the battery-saver ceiling off during a match",
    # Consequence 3 with teeth: this one lowers the ceiling rather than raising
    # it, which is why turning it *off* is the tweak.
    impact_scores={"fps_battery_ceiling": "removed", "stability": "high"},
    category_order=124,
    # Only exists as a decision on a machine with a battery.
    applicable_conditions={"feature": "mobile"},
    evidence_level="likely",
)

MW4_ECO_BATTERY_THRESHOLD = _make_mw4_setting(
    setting_id="game_config:mw4:eco_battery_threshold",
    display_name="MW4 Low Battery Threshold",
    short_name="MW4 Low Battery Threshold",
    description="Battery level at which the saver above engages. MW4 keeps it under two scope "
    "indices with the same range, so both have to agree or the threshold that binds is not the "
    "one the menu shows.",
    # Named-compound (C8): two scopes, one range, one concept.
    key=["UserEcoLowBatteryThresholdUI@0", "UserEcoLowBatteryThresholdUI@1"],
    choices=(),
    value_type=SettingValueType.INT,
    default_value=100,
    recommended_value=100,
    min_value=10,
    max_value=100,
    current_impact="100: Inert while the saver above is off",
    recommended_impact="100: Guards both scopes so the threshold cannot disagree with itself",
    effect="Keeps both copies of the battery threshold in agreement",
    impact_scores={"fps_battery_ceiling": "unbound", "stability": "high"},
    category_order=125,
    applicable_conditions={"feature": "mobile"},
    evidence_level="likely",
)


# --- Interface: what the game shows before and during a match ------------

MW4_SKIP_INTRO = _make_mw4_setting(
    setting_id="game_config:mw4:skip_intro",
    display_name="MW4 Startup Intro",
    short_name="MW4 Startup Intro",
    description="Skips the publisher and engine logos on launch. They cost the same seconds "
    "every session and there is nothing in them to see twice.",
    key="SkipIntro@1",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Logos skipped — the correct state",
    recommended_impact="true: Guards against a patch restoring them",
    effect="Keeps the startup logos skipped",
    impact_scores={"startup_speed": "+3-8s", "stability": "high"},
    category_order=126,
    evidence_level="proven",
)

MW4_SKIP_SEASON_VIDEO = _make_mw4_setting(
    setting_id="game_config:mw4:skip_season_video",
    display_name="MW4 Repeat Season Video",
    short_name="MW4 Repeat Season Video",
    description="Skips the season video on every login after the first. It is a separate switch "
    "from the one that skips it initially, so leaving this behind brings the video back on the "
    "second session.",
    key="SkipSeasonVideo@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Video shown once, not every login — the correct state",
    recommended_impact="true: Guards against it returning on every session",
    effect="Keeps the season video from replaying each login",
    impact_scores={"startup_speed": "+5-15s", "stability": "high"},
    category_order=127,
    evidence_level="proven",
)

MW4_ENABLE_HUD = _make_mw4_setting(
    setting_id="game_config:mw4:enable_hud",
    display_name="MW4 Heads-Up Display",
    short_name="MW4 Heads-Up Display",
    description="Draws the HUD — health, ammo, the minimap, killstreak state. Every element of "
    "it is information the player acts on, which makes turning it off for frames the clearest "
    "possible false economy.",
    key="EnableHUD@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: Health, ammo and minimap visible — the correct state",
    recommended_impact="true: Guards the densest source of information on the screen",
    effect="Keeps the HUD visible",
    impact_scores={"target_visibility": "preserved", "fps": "0 to -1%"},
    category_order=128,
    evidence_level="proven",
)
# --------------------------------------------------------------------------
# Phase B7 — vendor completeness (C10)
#
# "The best that machine is capable of" is a promise to every machine, so a
# feature that only works on the developer's silicon is unfinished rather than
# shipped. MW4 exposes the full matrix, so it is registered in full:
#
#   upscaler quality   DLSSPerfModeMP / AMDSuperResolution2Quality / XeSSQuality
#   frame generation   DLSSFrameGeneration / FSRFrameInterpolation / IntelXeFG
#   low latency        NvidiaReflex / AmdAntilag2 / IntelXeLL
#   sharpening         DLSSSharpnessMP / AMDContrastAdaptiveSharpening
#
# The AMD and Intel entries cannot be verified on this machine, which has an
# NVIDIA card — they are gated so they never appear on hardware that cannot use
# them, and their values follow the same reasoning as their NVIDIA siblings
# rather than a separate measurement. That is stated rather than hidden.
# --------------------------------------------------------------------------


def create_mw4_aa_technique_setting(gpu_vendor: str) -> SettingExecutor:
    """Build the anti-aliasing choice for the detected card.

    One setting, three right answers: each vendor's own upscaler doubles as its
    best AA, and picking another vendor's leaves the card running a generic path
    while its hardware sits idle. Recommending "DLSS" unconditionally — which is
    what a single static entry would do — is wrong on two thirds of machines.
    """
    preferred = {"nvidia": "DLSS", "amd": "FSR AA", "intel": "XeSS"}.get(gpu_vendor, "SMAA")
    return _make_mw4_setting(
        setting_id="game_config:mw4:aa_technique",
        display_name="MW4 Anti-Aliasing Technique",
        short_name="MW4 Anti-Aliasing Technique",
        description="Which anti-aliasing path the game uses. Each vendor's upscaler doubles as "
        "its best anti-aliasing, so the right answer here is a property of the card rather than "
        "a preference — and the wrong one leaves dedicated hardware unused.",
        key="AATechniquePreferredMP@0",
        choices=("SMAA", "DLSS", "XeSS", "FSR AA"),
        default_value=preferred,
        recommended_value=preferred,
        current_impact="A technique from another vendor: generic path, dedicated hardware idle",
        recommended_impact=f"{preferred}: The path this card has hardware for",
        effect=f"Selects the anti-aliasing this {gpu_vendor} card is built for",
        impact_scores={"fps": "+3-8%", "target_clarity": "improved"},
        category_order=130,
        evidence_level="likely",
    )


# --- AMD ------------------------------------------------------------------

MW4_AMD_ANTILAG = _make_mw4_setting(
    setting_id="game_config:mw4:amd_antilag",
    display_name="MW4 AMD Anti-Lag 2",
    short_name="MW4 AMD Anti-Lag 2",
    description="AMD's low-latency mode, which keeps the render queue short instead of letting "
    "frames accumulate ahead of the GPU. It is the counterpart of NVIDIA Reflex, and leaving it "
    "off is the same cost on AMD hardware that Reflex being off is on NVIDIA.",
    key="AmdAntilag2@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Render queue accumulates — roughly 10-20 ms of added input lag",
    recommended_impact="true: Short render queue — the AMD equivalent of Reflex",
    effect="Enables AMD Anti-Lag 2",
    impact_scores={"latency_ms": -3, "stability": "high"},
    category_order=131,
    scope=SettingScope.ESSENTIAL,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "amd"},
)

MW4_AMD_FSR_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:amd_fsr_quality",
    display_name="MW4 FSR Quality Mode",
    short_name="MW4 FSR Quality Mode",
    description="Internal resolution FSR 2/3 renders at before upscaling. An upscaler exists to "
    "buy frames, so its most expensive tier gives back most of what it was turned on for — the "
    "same trade DLSS makes, decided the same way.",
    key="AMDSuperResolution2Quality@0",
    choices=(
        "Ultra Performance",
        "Maximum Performance",
        "Balanced",
        "Maximum Quality",
        "Native Resolution",
    ),
    default_value="Maximum Quality",
    recommended_value="Balanced",
    current_impact="Maximum Quality: the tier that buys the fewest frames FSR can buy",
    recommended_impact="Balanced: frames back, and a distant player still resolves as one",
    effect="Moves FSR to the tier that buys frames without softening a target",
    impact_scores={"fps": "+10-18%", "target_clarity": "preserved"},
    category_order=132,
    perceptible_cost=(
        "The image is rendered below native resolution and upscaled — fine detail softens, most visibly in motion and at distance."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "amd"},
)

MW4_AMD_FSR1_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:amd_fsr1_quality",
    display_name="MW4 FSR 1 Quality Mode",
    short_name="MW4 FSR 1 Quality Mode",
    description="Quality tier for the older spatial FSR 1 path, kept separate from FSR 2/3. It "
    "only applies when FidelityFX is set to FSR 1, and a low tier here is a soft image with no "
    "temporal information to recover it.",
    key="AMDSuperResolutionQuality@0",
    choices=("Maximum Performance", "Balanced", "Maximum Quality", "Ultra Quality"),
    default_value="Maximum Quality",
    recommended_value="Balanced",
    current_impact="Maximum Quality: near-native render, so FSR 1 buys almost nothing back",
    recommended_impact="Balanced: frames back, and spatial softening still short of a lost target",
    effect="Moves FSR 1 to the tier that buys frames without losing a target",
    # Held one tier above the FSR 2/3 path's floor on purpose: FSR 1 is spatial,
    # so there is no temporal history to recover detail from and its lower tiers
    # go soft faster. `Maximum Performance` is where a distant player goes.
    impact_scores={"fps": "+3-9%", "target_clarity": "preserved"},
    category_order=133,
    perceptible_cost=(
        "The image is rendered below native resolution and upscaled — fine detail softens, most visibly in motion and at distance."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "amd"},
)

MW4_AMD_FIDELITYFX = _make_mw4_setting(
    setting_id="game_config:mw4:amd_fidelityfx",
    display_name="MW4 AMD FidelityFX",
    short_name="MW4 AMD FidelityFX",
    description="Which FidelityFX path is active: sharpening only, spatial FSR 1, or temporal "
    "FSR 3. MW4 keeps the choice under two scope indices with the same value list, so both have "
    "to agree or the path that runs is not the one the menu shows.",
    # Named-compound (C8): two scopes, identical lists, one concept.
    key=["AMDFidelityFX@0", "AMDFidelityFX@1"],
    choices=("Off", "CAS", "FSR 1", "FSR 3"),
    default_value="Off",
    recommended_value="Off",
    current_impact="Off: No FidelityFX path active — correct while another upscaler is chosen",
    recommended_impact="Off: Guards both scopes against a path being half-enabled",
    effect="Keeps both FidelityFX scopes in agreement",
    impact_scores={"fps": "0 to +5%", "stability": "high"},
    category_order=134,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "amd"},
)

MW4_AMD_CAS_STRENGTH = _make_mw4_setting(
    setting_id="game_config:mw4:amd_cas_strength",
    display_name="MW4 Contrast Adaptive Sharpening",
    short_name="MW4 Contrast Adaptive Sharpening",
    description="Strength of AMD's sharpening filter. Sharpening recovers some of what an "
    "upscaler softened, but past a point it draws halos around edges — which adds contrast "
    "where there is no object.",
    key="AMDContrastAdaptiveSharpeningStrength@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.500000",
    recommended_value="0.500000",
    min_value=0.0,
    max_value=1.0,
    current_impact="0.500000: Middle of the range — sharpening without ringing",
    recommended_impact="0.500000: Guards against a strength that draws halos around edges",
    effect="Keeps sharpening below the level that adds halos",
    impact_scores={"fps": "0 to -1%", "target_clarity": "preserved"},
    category_order=135,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "amd"},
)

MW4_FSR_FRAME_INTERPOLATION = _make_mw4_setting(
    setting_id="game_config:mw4:fsr_frame_interpolation",
    display_name="MW4 FSR Frame Generation",
    short_name="MW4 FSR Frame Generation",
    description="Inserts generated frames between rendered ones. The frame counter rises and "
    "the input latency rises with it, because a generated frame cannot show anything the player "
    "did — which is the opposite of what a competitive setting should do.",
    key="FSRFrameInterpolation@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Every frame is a rendered one — the correct state",
    recommended_impact="false: Guards against a higher counter that costs input latency",
    effect="Keeps frame generation off",
    impact_scores={"latency_ms": -10.0, "stability": "high"},
    category_order=136,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "amd"},
)


# --- Intel ----------------------------------------------------------------

MW4_INTEL_XELL = _make_mw4_setting(
    setting_id="game_config:mw4:intel_xell",
    display_name="MW4 Intel XeLL",
    short_name="MW4 Intel XeLL",
    description="Intel's low-latency mode, which keeps the render queue short instead of letting "
    "frames accumulate. It is the counterpart of Reflex and Anti-Lag, and an Arc owner loses the "
    "same latency without it that anyone else does.",
    key="IntelXeLL@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Render queue accumulates — roughly 10-20 ms of added input lag",
    recommended_impact="true: Short render queue — the Intel equivalent of Reflex",
    effect="Enables Intel Xe Low Latency",
    impact_scores={"latency_ms": -3, "stability": "high"},
    category_order=137,
    scope=SettingScope.ESSENTIAL,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "intel"},
)

MW4_XESS_QUALITY = _make_mw4_setting(
    setting_id="game_config:mw4:xess_quality",
    display_name="MW4 XeSS Quality Mode",
    short_name="MW4 XeSS Quality Mode",
    description="Internal resolution XeSS renders at before upscaling. An upscaler exists to buy "
    "frames, so its most expensive tier gives back most of what it was turned on for — the same "
    "trade DLSS and FSR make, decided the same way.",
    key="XeSSQuality@0",
    choices=(
        "Ultra Performance",
        "Maximum Performance",
        "Balanced",
        "Maximum Quality",
        "Ultra Quality",
        "Ultra Quality Plus",
        "Native Resolution",
    ),
    default_value="Ultra Quality",
    recommended_value="Balanced",
    current_impact="Ultra Quality: near-native render — XeSS on, and barely buying frames with it",
    recommended_impact="Balanced: frames back, and a distant player still resolves as one",
    effect="Moves XeSS to the tier that buys frames without softening a target",
    impact_scores={"fps": "+8-15%", "target_clarity": "preserved"},
    category_order=138,
    perceptible_cost=(
        "The image is rendered below native resolution and upscaled — fine detail softens, most visibly in motion and at distance."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "intel"},
)

MW4_INTEL_XEFG = _make_mw4_setting(
    setting_id="game_config:mw4:intel_xefg",
    display_name="MW4 Intel XeSS Frame Generation",
    short_name="MW4 Intel XeSS Frame Generation",
    description="Inserts generated frames between rendered ones. The counter rises and the "
    "input latency rises with it, because a generated frame cannot show anything the player did.",
    key="IntelXeFG@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Every frame is a rendered one — the correct state",
    recommended_impact="false: Guards against a higher counter that costs input latency",
    effect="Keeps XeSS frame generation off",
    impact_scores={"latency_ms": -10.0, "stability": "high"},
    category_order=139,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "intel"},
)

MW4_INTEL_XEFG_MULTI = _make_mw4_setting(
    setting_id="game_config:mw4:intel_xefg_multi",
    display_name="MW4 XeSS Frame Generation Multiplier",
    short_name="MW4 XeSS Frame Generation Multiplier",
    description="How many frames XeSS generates per rendered one. Inert while frame generation "
    "is off, and each step above 1 adds latency on top of the generation itself.",
    key="IntelXEFGMulti@0",
    choices=(),
    value_type=SettingValueType.INT,
    default_value=1,
    recommended_value=1,
    min_value=1,
    max_value=3,
    current_impact="1: No multiplication armed behind the generation switch",
    recommended_impact="1: Guards the multiplier so enabling generation cannot compound it",
    effect="Keeps the frame generation multiplier at one",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=140,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "intel"},
)


# --- NVIDIA: the rest of the matrix --------------------------------------

MW4_DLSS_MODE = _make_mw4_setting(
    setting_id="game_config:mw4:dlss_mode",
    display_name="MW4 DLSS Mode",
    short_name="MW4 DLSS Mode",
    description="Which DLSS path runs: upscaling, native-resolution anti-aliasing, or the ray "
    "reconstruction denoiser. DLSS upscaling is the one that returns frames while keeping the "
    "image resolvable.",
    key="DLSSModeMP@0",
    choices=("DLSS", "DLAA", "DLSS-D"),
    default_value="DLSS",
    recommended_value="DLSS",
    current_impact="DLSS: Upscaling path — the correct state for a frame-rate target",
    recommended_impact="DLSS: Guards against DLAA, which renders at native and costs the gain",
    effect="Keeps DLSS on its upscaling path",
    impact_scores={"fps": "+20-35%", "stability": "high"},
    category_order=141,
    evidence_level="proven",
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW4_DLSS_FRAME_GENERATION = _make_mw4_setting(
    setting_id="game_config:mw4:dlss_frame_generation",
    display_name="MW4 DLSS Frame Generation",
    short_name="MW4 DLSS Frame Generation",
    description="Inserts generated frames between rendered ones. The counter rises and the input "
    "latency rises with it, because a generated frame cannot show anything the player did — the "
    "reason it is off in every competitive configuration.",
    key="DLSSFrameGeneration@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Every frame is a rendered one — the correct state",
    recommended_impact="false: Guards against a higher counter that costs input latency",
    effect="Keeps DLSS frame generation off",
    impact_scores={"latency_ms": -10.0, "stability": "high"},
    category_order=142,
    evidence_level="proven",
    sources=_MW3_MEASURED,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW4_DLSS_SHARPNESS = _make_mw4_setting(
    setting_id="game_config:mw4:dlss_sharpness",
    display_name="MW4 DLSS Sharpness",
    short_name="MW4 DLSS Sharpness",
    description="Sharpening applied after DLSS upscaling. Some recovers what the upscaler "
    "softened; too much draws halos around edges, adding contrast where there is no object and "
    "making a distant figure harder to separate rather than easier.",
    key="DLSSSharpnessMP@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.500000",
    recommended_value="0.250000",
    min_value=0.0,
    max_value=1.0,
    current_impact="0.500000: Enough sharpening to start ringing on high-contrast edges",
    recommended_impact="0.250000: Recovers upscaler softness without drawing halos",
    effect="Lowers post-upscale sharpening below the ringing threshold",
    impact_scores={"fps": "0%", "target_clarity": "improved"},
    category_order=143,
    evidence_level="likely",
    sources=_MW3_MEASURED,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW4_NVIDIA_IMAGE_SCALING = _make_mw4_setting(
    setting_id="game_config:mw4:nvidia_image_scaling",
    display_name="MW4 NVIDIA Image Scaling",
    short_name="MW4 NVIDIA Image Scaling",
    description="A spatial upscaler with no temporal information, from before DLSS. Running it "
    "alongside DLSS stacks two upscalers, which is the same mistake as a low render resolution "
    "under a low DLSS tier.",
    key="NVIDIAImageScalingMP@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: One upscaler in the chain — the correct state",
    recommended_impact="false: Guards against a second, worse upscaler stacking on DLSS",
    effect="Keeps the legacy spatial upscaler out of the chain",
    impact_scores={"fps": "0 to +2%", "target_clarity": "preserved"},
    category_order=144,
    evidence_level="likely",
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW4_DXR_DENOISER = _make_mw4_setting(
    setting_id="game_config:mw4:dxr_denoiser",
    display_name="MW4 Ray Tracing Denoiser",
    short_name="MW4 Ray Tracing Denoiser",
    description="Which denoiser cleans up ray-traced lighting. Inert while ray tracing is off, "
    "and the vendor-specific options here each pull in their own upscaler path as a side effect.",
    key="DxrDenoiser@0",
    choices=("Default", "FSR Ray Regeneration", "DLSS Ray Reconstruction"),
    default_value="Default",
    recommended_value="Default",
    current_impact="Default: No vendor denoiser path armed behind a disabled feature",
    recommended_impact="Default: Guards against a denoiser choice that changes the upscaler",
    effect="Keeps the denoiser on its default path",
    impact_scores={"fps": "0%", "stability": "high"},
    category_order=145,
    evidence_level="likely",
)


MW4_SHADER_CACHE_CLEANUP = SettingExecutor(
    id="game_cleanup:mw4:shader_cache_cleanup",
    category=SettingCategory.MAINTENANCE,
    display_name="MW4 Shader Cache Cleanup",
    short_name="MW4 Shader Cache Cleanup",
    description="Deletes MW4's compiled shader cache and its xpak and telescope content "
    "caches from the game's own install folder. The game rebuilds all three on the next "
    "launch, which is also what clears the black screens and launch crashes a driver "
    "update leaves behind.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    current_impact="Current: Shaders compiled against an older driver are still on disk",
    recommended_impact="Clean: Caches deleted, shaders recompile on the next launch",
    scope=SettingScope.COMPLETE,
    category_order=90,
    effect="Clears MW4 shader and content caches so the game rebuilds them",
    # Measured on the machine this was written for, 2026-08-25: 2163 MB across
    # `cod26\\shadercache` (543 MB) and `xpak_cache` (1725 MB). The range is wide
    # because it grows with how much of the game has been played.
    impact_scores={"stability": "high", "disk_freed": "0.5-3GB"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "mw4_shader"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw4_shader_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

COD_CRASH_REPORTS_CLEANUP = SettingExecutor(
    id="game_cleanup:cod_crash_reports",
    category=SettingCategory.MAINTENANCE,
    display_name="Call of Duty Crash Reports",
    short_name="Call of Duty Crash Reports",
    description="Deletes the crash dumps and GPU fault reports the Call of Duty launcher "
    "writes beside the player profile. They are diagnostic files for a crash that has "
    "already happened and nothing reads them afterwards.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    current_impact="Current: Crash dumps from past sessions still on disk",
    recommended_impact="Clean: Crash report folder emptied",
    scope=SettingScope.COMPLETE,
    category_order=91,
    effect="Deletes Call of Duty crash dumps and GPU fault reports",
    # One directory shared by every COD title on the machine, which is why this
    # is not per-game: two settings writing the same folder would each report
    # freeing what the other already freed.
    impact_scores={"stability": "high", "disk_freed": "0-500MB"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "cod_crash_reports"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="cod_crash_reports_cleanup",
    apply_args={},
    apply_value_map={},
)


#: Disk actions rather than config lines, kept out of `MW4_SETTINGS` on purpose.
#:
#: Everything in that list writes one `Name@scope` key into the game's config, and
#: several tests hold it to exactly that — every entry must carry a `batch_key`
#: naming the line it owns. A cleanup owns a directory, not a key, so putting it
#: there would either break those guards or force them to grow an exception.
MW4_CLEANUP_SETTINGS: list[SettingExecutor] = [
    MW4_SHADER_CACHE_CLEANUP,
    COD_CRASH_REPORTS_CLEANUP,
]


MW4_SETTINGS: list[SettingExecutor] = [
    # B1 — guards and the settings that protect every other one
    MW4_RECOMMENDED_SET,
    MW4_CLOUD_STORAGE,
    MW4_HW_CHANGE_DETECTION,
    MW4_NVIDIA_REFLEX,
    MW4_FPS_CAP_OUT_OF_FOCUS,
    # B1 — what the config was spending that the player needed
    MW4_RENDER_RESOLUTION,
    MW4_DLSS_PERF_MODE,
    MW4_DLSS_MODEL,
    MW4_TEXTURE_QUALITY,
    MW4_ANISOTROPIC,
    MW4_VOLUMETRIC_QUALITY,
    MW4_REFLECTION_PROBE_HALF_RES,
    # B2 — decoration spent for frames
    MW4_MOTION_BLUR,
    MW4_WEAPON_MOTION_BLUR,
    MW4_VELOCITY_BLUR,
    MW4_DEPTH_OF_FIELD,
    MW4_DOF_WEAPON,
    MW4_DOF_WORLD,
    MW4_DOF_QUALITY,
    MW4_WEATHER_GRID,
    MW4_SUBDIVISION,
    MW4_SHADOW_FILTERING,
    MW4_SHADER_QUALITY,
    MW4_CINEMATIC_EMISSIVE,
    MW4_SHOW_BRASS,
    MW4_BLOOD_LIMIT,
    MW4_CORPSE_LIMIT,
    MW4_CORPSES_CULLING,
    MW4_SKIP_SEASON_INTRO,
    MW4_MARKS_PLAYER_ONLY,
    # B2 — guards on things already correct
    MW4_SSR,
    MW4_DXR_MODE,
    MW4_DXR_QUALITY,
    MW4_TESSELLATION,
    MW4_WATER_CAUSTICS,
    MW4_WATER_WAVE_WETNESS,
    MW4_PERSISTENT_DAMAGE,
    # B3 — what must not be lowered, plus the one raise
    MW4_MODEL_QUALITY,
    MW4_PARTICLE_QUALITY,
    MW4_WORLD_STREAMING,
    MW4_SHADOW_QUALITY,
    MW4_SCREEN_SPACE_SHADOWS,
    MW4_AMBIENT_LIGHTING,
    MW4_BULLET_IMPACTS,
    MW4_SHOW_BLOOD,
    MW4_ST_LOD_SKIP,
    MW4_SHADER_PRELOAD,
    MW4_GPU_UPLOAD_HEAPS,
    MW4_VRS,
    MW4_DYNAMIC_SCENE_RESOLUTION,
    MW4_ABSOLUTE_TARGET_RESOLUTION,
    MW4_WEAPON_CYCLE_DELAY,
    # B4 — audio: direction is information, a soundtrack is not
    MW4_MUSIC_VOLUME,
    MW4_WARTRACKS_VOLUME,
    MW4_TELESCOPE_VOLUME,
    MW4_CINEMATIC_VOLUME,
    MW4_ALT_SHELL_SHOCK,
    MW4_MUTE_LICENSED_MUSIC,
    MW4_EFFECTS_VOLUME,
    MW4_HITMARKERS_VOLUME,
    MW4_VOICE_VOLUME,
    MW4_MONO_SOUND,
    # B5 — input: what makes the same movement produce the same aim
    MW4_MOUSE_ACCELERATION,
    MW4_MOUSE_FILTER,
    MW4_MOUSE_SMOOTHING,
    MW4_SPRINT_ASSIST_DELAY,
    MW4_ADS_FOV_SCALING,
    MW4_FREE_LOOK,
    MW4_GAMEPAD_AIM,
    MW4_FOV,
    # B6 — display, heat and interface
    MW4_ASPECT_RATIO,
    MW4_DISPLAY_MODE,
    MW4_PREFERRED_DISPLAY_MODE,
    MW4_VSYNC,
    MW4_VSYNC_MENU,
    MW4_CAP_FPS,
    MW4_DISPLAY_GAMMA,
    MW4_HDR,
    MW4_MENU_SCENE_RESOLUTION,
    MW4_REDUCE_QUALITY_IDLE,
    MW4_REDUCE_QUALITY_IDLE_DELAY,
    MW4_PAUSE_RENDERING,
    MW4_ECO_LOW_BATTERY,
    MW4_ECO_BATTERY_THRESHOLD,
    MW4_SKIP_INTRO,
    MW4_SKIP_SEASON_VIDEO,
    MW4_ENABLE_HUD,
    # B7 — vendor completeness: all three, or it is not shipped
    MW4_AMD_ANTILAG,
    MW4_AMD_FSR_QUALITY,
    MW4_AMD_FSR1_QUALITY,
    MW4_AMD_FIDELITYFX,
    MW4_AMD_CAS_STRENGTH,
    MW4_FSR_FRAME_INTERPOLATION,
    MW4_INTEL_XELL,
    MW4_XESS_QUALITY,
    MW4_INTEL_XEFG,
    MW4_INTEL_XEFG_MULTI,
    MW4_DLSS_MODE,
    MW4_DLSS_FRAME_GENERATION,
    MW4_DLSS_SHARPNESS,
    MW4_NVIDIA_IMAGE_SCALING,
    MW4_DXR_DENOISER,
]
