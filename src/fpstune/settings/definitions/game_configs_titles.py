"""Fortnite, Apex Legends, Overwatch 2 and Rainbow Six Siege config settings.

Few keys per game, by design. A key ships only when its file, its value range
and its effect are each on record from at least two independent sources (the
URLs sit beside each setting); a game whose keys are not on record that way is
not here at all. Valorant was left out for that reason: its GameUserSettings.ini
carries ``FrameRateLimit`` and ``bUseVSync``, but nothing on record shows the
game reading them back, and its frame limits live in the account's cloud
settings — a write there would pass verify and change nothing.

What every game here gets is the same pair the rest of the product already
holds coherent (CLAUDE.md coherence table): in-game V-Sync off, because the
driver owns synchronisation, and — where the file has a frame cap the game
honours — the one cap rule (``frame_cap_for_refresh``) on a VRR panel and no cap
on a fixed one. Beyond that, only decoration whose removal also clears the view.

The games' own stock values for these keys are not documented anywhere on
record, so each V-Sync row is a drift guard (default == recommended == off):
reset writes off, which costs nothing, rather than a stock value fpstune would
be guessing.
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
from fpstune.settings.performance_headroom import frame_cap_for_refresh

_FORTNITE_SOURCES = [
    "https://www.esportstales.com/fortnite/how-to-increase-fps-video-options-gameusersettings",
    "https://optimizer.byens-it.dk/en/games/fortnite",
    "https://forums.guru3d.com/threads/best-use-of-gsync-in-competitive-fps.453839/",
]
_APEX_SOURCES = [
    "https://note.com/ebi_suuuuuu/n/nd51daeac3755",
    "https://github.com/V3nilla/Apex-Legends-Config-And-Tweaks/blob/main/videoconfig.txt",
    "https://www.prosettings.com/best-apex-legends-settings/",
    "https://www.gamingpcbuilder.com/best-graphics-settings-for-apex-legends/",
]
_OVERWATCH_SOURCES = [
    "https://filepathgeek.com/posts/overwatch-2-settings-screenshots-location/",
    "https://gist.github.com/3c9015c65a1fad6f0ddd5ebc44473155",
]
_SIEGE_SOURCES = [
    "https://github.com/cjLGH/game-settings/blob/master/r6siege/GameSettings.ini",
    "https://steamcommunity.com/app/359550/discussions/0/1741094390482176657/",
    "https://pastebin.com/TuDZ9V8u",
]


def _make(
    *,
    game: str,
    name: str,
    key: str,
    display_name: str,
    description: str,
    choices: tuple[str, ...],
    default_value: str | int,
    recommended_value: str | int,
    value_map: dict[Any, Any],
    apply_value_map: dict[str, str],
    current_impact: str,
    recommended_impact: str,
    effect: str,
    impact_scores: dict[str, str | float],
    category_order: int,
    sources: list[str],
    scope: SettingScope = SettingScope.RECOMMENDED,
    evidence_level: str = "likely",
    value_type: SettingValueType = SettingValueType.CHOICE,
    min_value: int | None = None,
    max_value: int | None = None,
) -> SettingExecutor:
    """One setting backed by one line of the game's own config file."""
    detect_args: dict[str, Any] = {"game": game, "key": key}
    apply_args: dict[str, Any] = {"game": game, "key": key}
    if value_type == SettingValueType.INT:
        detect_args["integer"] = True
        apply_args["min"] = min_value
        apply_args["max"] = max_value
    else:
        apply_args["allowed"] = ",".join(sorted(set(apply_value_map.values())))
    return SettingExecutor(
        id=f"game_config:{game}:{name}",
        category=SettingCategory.GAME_CONFIG,
        display_name=display_name,
        short_name=display_name,
        description=description,
        value_type=value_type,
        choices=choices,
        default_value=default_value,
        recommended_value=recommended_value,
        min_value=min_value,
        max_value=max_value,
        requires_reboot=False,
        risk_level="low",
        evidence_level=evidence_level,
        sources=sources,
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        scope=scope,
        category_order=category_order,
        effect=effect,
        impact_scores=impact_scores,
        detect_type=DetectType.POWERSHELL,
        detect_command="game_ini_read",
        detect_args=detect_args,
        value_map=value_map,
        apply_type=DetectType.POWERSHELL,
        apply_command="game_ini_write",
        apply_args=apply_args,
        apply_value_map=apply_value_map,
    )


_VSYNC_DESCRIPTION = (
    "In-game frame synchronisation. The driver already owns synchronisation (and keeps a "
    "variable-refresh panel inside its window), so a second V-Sync in the game only adds a wait."
)

# =============================================================================
# Fortnite — %LOCALAPPDATA%\FortniteGame\Saved\Config\WindowsClient\GameUserSettings.ini
# =============================================================================

FORTNITE_VSYNC = _make(
    game="fortnite",
    name="vsync",
    key="bUseVSync",
    display_name="Fortnite Vertical Sync",
    description=_VSYNC_DESCRIPTION,
    choices=("off", "on"),
    default_value="off",
    recommended_value="off",
    value_map={"False": "off", "false": "off", "True": "on", "true": "on"},
    apply_value_map={"off": "False", "on": "True"},
    current_impact="On: Each frame waits for the next refresh on top of the driver's own sync",
    recommended_impact="Off: The driver alone governs presentation, so no doubled sync wait",
    effect="Leaves frame synchronisation to the driver",
    impact_scores={"latency_ms": -8, "stability": "high"},
    category_order=40,
    sources=_FORTNITE_SOURCES,
)


def _cap_copy(game_label: str, max_hz: int, vrr: bool) -> tuple[int, str, str, str]:
    if vrr:
        target = frame_cap_for_refresh(max_hz)
        return (
            target,
            f"Maximum frames per second in {game_label}. Held below this variable-refresh "
            "panel's rate, so the frame rate never leaves the VRR window, where tearing and "
            "V-Sync latency return.",
            "Above or far below the cap: VRR window left, or the panel underused",
            f"{target}: Full use of the panel with VRR headroom kept",
        )
    return (
        0,
        f"Maximum frames per second in {game_label}. This panel has no variable refresh, so "
        "any cap only lowers the frame rate and adds latency; 0 removes it.",
        "Capped: Frames the GPU could render are never drawn",
        "0 (uncapped): The cap never binds before the hardware does",
    )


def create_fortnite_fps_cap_setting(max_hz: int, *, vrr: bool) -> SettingExecutor:
    """Fortnite's ``FrameRateLimit``: the one cap rule on VRR, uncapped otherwise.

    The file accepts any number, including ones the menu does not offer (the
    138 fps on a 144 Hz VRR panel in the guru3d thread), and 0 means no cap.
    """
    target, description, current, recommended = _cap_copy("Fortnite", max_hz, vrr)
    return _make(
        game="fortnite",
        name="fps_cap",
        key="FrameRateLimit",
        display_name="Fortnite Frame Rate Limit",
        description=description,
        choices=(),
        default_value=target,
        recommended_value=target,
        value_map={},
        apply_value_map={},
        current_impact=current,
        recommended_impact=recommended,
        effect="Matches the frame cap to the attached monitor",
        impact_scores={"fps": f"ceiling {target or 'removed'}", "latency_ms": -2.0},
        category_order=37,
        sources=_FORTNITE_SOURCES,
        scope=SettingScope.ESSENTIAL,
        value_type=SettingValueType.INT,
        min_value=0,
        max_value=max(1000, max_hz),
    )


# =============================================================================
# Apex Legends — %USERPROFILE%\Saved Games\Respawn\Apex\local\videoconfig.txt
# =============================================================================

APEX_VSYNC = _make(
    game="apex",
    name="vsync",
    key="setting.mat_vsync_mode",
    display_name="Apex Vertical Sync",
    description=_VSYNC_DESCRIPTION,
    # The menu's own order: Disabled, Double Buffered, Triple Buffered,
    # Adaptive, Adaptive (1/2 Rate).
    choices=("disabled", "double", "triple", "adaptive", "adaptive_half"),
    default_value="disabled",
    recommended_value="disabled",
    value_map={
        "0": "disabled",
        "1": "double",
        "2": "triple",
        "3": "adaptive",
        "4": "adaptive_half",
    },
    apply_value_map={
        "disabled": "0",
        "double": "1",
        "triple": "2",
        "adaptive": "3",
        "adaptive_half": "4",
    },
    current_impact="Synced: Each frame waits for a refresh on top of the driver's own sync",
    recommended_impact="Disabled: The driver alone governs presentation, so no doubled sync wait",
    effect="Leaves frame synchronisation to the driver",
    impact_scores={"latency_ms": -8, "stability": "high"},
    category_order=40,
    sources=_APEX_SOURCES,
)

APEX_VOLUMETRIC_LIGHTING = _make(
    game="apex",
    name="volumetric_lighting",
    key="setting.volumetric_lighting",
    display_name="Apex Volumetric Lighting",
    description="Light shafts drawn through dust and haze. They cost frames and wash out the "
    "part of the scene a player has to read, so they are decoration in a shooter.",
    choices=("off", "on"),
    default_value="off",
    recommended_value="off",
    value_map={"0": "off", "1": "on"},
    apply_value_map={"off": "0", "on": "1"},
    current_impact="On: Sunbeams drawn across the scene, at a cost in frames",
    recommended_impact="Off: No light shafts over targets, and the frames back",
    effect="Removes volumetric light shafts",
    impact_scores={"fps": "+3-7%", "target_visibility": "improved"},
    category_order=41,
    sources=_APEX_SOURCES,
)

# =============================================================================
# Overwatch 2 — Documents\Overwatch\Settings\Settings_v0.ini, [Render.13]
# =============================================================================

OVERWATCH_VSYNC = _make(
    game="overwatch",
    name="vsync",
    key="VerticalSyncEnabled",
    display_name="Overwatch 2 Vertical Sync",
    description=_VSYNC_DESCRIPTION,
    choices=("off", "on"),
    default_value="off",
    recommended_value="off",
    value_map={"0": "off", "1": "on"},
    apply_value_map={"off": "0", "on": "1"},
    current_impact="On: Each frame waits for the next refresh on top of the driver's own sync",
    recommended_impact="Off: The driver alone governs presentation, so no doubled sync wait",
    effect="Leaves frame synchronisation to the driver",
    impact_scores={"latency_ms": -8, "stability": "high"},
    category_order=40,
    sources=_OVERWATCH_SOURCES,
)

# =============================================================================
# Rainbow Six Siege — Documents\My Games\Rainbow Six - Siege\<account>\GameSettings.ini
# The file documents its own keys: ";VSync => 0 disabled / 1 frame / 2 frames" and
# ";FPSLimit => Limit the game's fps. Minimum of 30fps. Anything below will
# disable the fps limit."
# =============================================================================

SIEGE_VSYNC = _make(
    game="r6siege",
    name="vsync",
    key="VSync",
    display_name="Rainbow Six Siege Vertical Sync",
    description=_VSYNC_DESCRIPTION,
    choices=("off", "every_frame", "every_second_frame"),
    default_value="off",
    recommended_value="off",
    value_map={"0": "off", "1": "every_frame", "2": "every_second_frame"},
    apply_value_map={"off": "0", "every_frame": "1", "every_second_frame": "2"},
    current_impact="Synced: Frames wait for a refresh, or run at half the panel's rate",
    recommended_impact="Off: The driver alone governs presentation, so no doubled sync wait",
    effect="Leaves frame synchronisation to the driver",
    impact_scores={"latency_ms": -8, "stability": "high"},
    category_order=40,
    sources=_SIEGE_SOURCES,
    evidence_level="proven",
)


def create_siege_fps_cap_setting(max_hz: int, *, vrr: bool) -> SettingExecutor:
    """Siege's ``FPSLimit``: the one cap rule on VRR, 0 (off) otherwise.

    The file's own comment sets the floor: below 30 means no limit, and
    ``frame_cap_for_refresh`` never derives under 30.
    """
    target, description, current, recommended = _cap_copy("Rainbow Six Siege", max_hz, vrr)
    return _make(
        game="r6siege",
        name="fps_cap",
        key="FPSLimit",
        display_name="Rainbow Six Siege Frame Rate Limit",
        description=description,
        choices=(),
        default_value=target,
        recommended_value=target,
        value_map={},
        apply_value_map={},
        current_impact=current,
        recommended_impact=recommended,
        effect="Matches the frame cap to the attached monitor",
        impact_scores={"fps": f"ceiling {target or 'removed'}", "latency_ms": -2.0},
        category_order=37,
        sources=_SIEGE_SOURCES,
        scope=SettingScope.ESSENTIAL,
        evidence_level="proven",
        value_type=SettingValueType.INT,
        min_value=0,
        max_value=max(1000, max_hz),
    )


TITLE_SETTINGS: list[SettingExecutor] = [
    FORTNITE_VSYNC,
    APEX_VSYNC,
    APEX_VOLUMETRIC_LIGHTING,
    OVERWATCH_VSYNC,
    SIEGE_VSYNC,
]
