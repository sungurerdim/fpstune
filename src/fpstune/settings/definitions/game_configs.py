"""Game-specific configuration file tweaks.

Contains settings that modify in-game config files for CS2 and MW3.
These settings edit files on disk (autoexec.cfg, gamerprofile.cst) and
create/remove firewall rules — they do NOT touch Windows registry or
network adapter properties.

Detection notes:
- CS2 settings detect the presence of fpstune marker blocks in autoexec.cfg.
- MW3 settings detect the gamerprofile.0.bASE.cst file content.
- All settings return "not_installed" when the game files are not found.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)
from fpstune.settings.performance_headroom import frame_cap_for_refresh

# === Steam / CS2 Path Helper ===
# Finds CS2's cfg dir by scanning EVERY Steam library (primary + secondary
# libraries listed in libraryfolders.vdf). CS2 frequently lives in a
# secondary library (e.g. D:\SteamLibrary) — searching only the
# primary install path misses those installs.
_CS2_CFG_PATH_PS = (
    "$sp = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Valve\\Steam' "
    "-Name 'InstallPath' -EA SilentlyContinue).InstallPath; "
    "if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\\SOFTWARE\\WOW6432Node\\Valve\\Steam' "
    "-Name 'InstallPath' -EA SilentlyContinue).InstallPath }; "
    "if (-not $sp) { Write-Output 'not_installed'; return }; "
    "$libs = @($sp); "
    "$libVdf = Join-Path $sp 'steamapps\\libraryfolders.vdf'; "
    "if (Test-Path $libVdf) { "
    "$vdf = [System.IO.File]::ReadAllText($libVdf); "
    'foreach ($_m in [regex]::Matches($vdf, \'"path"\\s+"([^"]+)"\')) { '
    "$_p = $_m.Groups[1].Value -replace '\\\\\\\\','\\\\'; "
    "if ($libs -notcontains $_p) { $libs += $_p } "
    "} "
    "}; "
    "$cfgDir = $null; "
    "foreach ($_lib in $libs) { "
    "$_c = Join-Path $_lib 'steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo\\cfg'; "
    "if (Test-Path $_c) { $cfgDir = $_c; break } "
    "}; "
    "if (-not $cfgDir) { Write-Output 'not_installed'; return }; "
    "$cfgPath = Join-Path $cfgDir 'autoexec.cfg'; "
)

# =============================================================================
# CS2 Settings
# =============================================================================

# === CS2 Network Tweaks (single-tweak, each edits one autoexec.cfg line) ===

_CS2_CFG_DETECT_BASE = (
    _CS2_CFG_PATH_PS + "if (-not (Test-Path $cfgPath)) { Write-Output 'default'; return }; "
    "$c = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8); "
)

# === CS2 cvar factory ===
# Builds a CS2 SettingExecutor that writes a single console command (cvar +
# value) into autoexec.cfg behind a unique fpstune marker block via the generic
# cs2_cvar_toggle apply command. Shared by every optimized/default cvar tweak.
_CS2_SOURCES = [
    "https://totalcsgo.com/launch-options",
    "https://csdb.gg/guides/fps-optimization-guide/",
    "https://www.thevaultohio.com/post/complete-guide-to-cs2-autoexec-commands-boost-fps-optimize-network-and-customize-your-gameplay",
]


def _make_cs2_cvar_setting(
    *,
    setting_id: str,
    display_name: str,
    short_name: str = "",
    description: str,
    cvar: str,
    cvar_value: str,
    default_cvar_value: str = "not set",
    marker: str,
    current_impact: str,
    recommended_impact: str,
    effect: str,
    impact_scores: dict[str, str | float],
    category_order: int,
    evidence_level: str = "likely",
    sources: list[str] | None = None,
    scope: SettingScope = SettingScope.RECOMMENDED,
    perceptible_cost: str | None = None,
) -> SettingExecutor:
    """Build a CS2 SettingExecutor that writes one cvar/value pair to autoexec.cfg."""
    detect_cmd = (
        _CS2_CFG_PATH_PS + "if (-not (Test-Path $cfgPath)) { Write-Output 'default'; return }; "
        "$c = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8); "
        f"if ($c -match '===fpstune-{marker}-start===') {{ Write-Output 'optimized' }} "
        "else { Write-Output 'default' }"
    )
    return SettingExecutor(
        id=setting_id,
        category=SettingCategory.GAME_CONFIG,
        display_name=display_name,
        short_name=short_name or display_name,
        description=description,
        value_type=SettingValueType.CHOICE,
        choices=("default", "optimized"),
        default_value="default",
        recommended_value="optimized",
        requires_reboot=False,
        evidence_level=evidence_level,
        sources=sources or _CS2_SOURCES,
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        # A parameter rather than a constant, for the reason the MW3 factory already
        # documents: hardcoding RECOMMENDED put every CS2 setting in one bucket, so
        # the Essential/Recommended/Complete selector did nothing for them.
        scope=scope,
        perceptible_cost=perceptible_cost,
        category_order=category_order,
        effect=effect,
        impact_scores=impact_scores,
        detect_type=DetectType.POWERSHELL,
        detect_command=detect_cmd,
        # Detection reads autoexec.cfg, which every CS2 setting shares. The
        # batch args let the executor answer from one cached read instead of
        # spawning a PowerShell per setting; detect_command stays as the
        # fallback for single-setting detects outside a scan.
        detect_args={
            "batch_config": "cs2",
            "batch_marker": marker,
            "batch_present": "optimized",
            "batch_absent": "default",
        },
        apply_type=DetectType.POWERSHELL,
        apply_command="cs2_cvar_toggle",
        apply_args={"cvar": cvar, "cvar_value": cvar_value, "marker": marker},
        apply_value_map={"default": "default", "optimized": "optimized"},
        value_hints={"default": default_cvar_value, "optimized": cvar_value},
    )


# The five settings that used to stand here — rate, cl_updaterate, cl_cmdrate,
# cl_interp_ratio and cl_interp — were CS:GO advice carried into a game that no
# longer has the mechanism they tuned. Every one of them was written into this
# machine's autoexec.cfg and reported back as "optimized".
#
# CS2 is subtick, not 128-tick, and the numbers those settings wrote were all
# derived from a tick rate that does not exist: 786432 was "the ceiling for
# 128-tick", 0.015625 was "one 128-tick period". cl_cmdrate is absent from all
# 102 shipped modules, so the line was not even parsed. Valve's own note on the
# removal is that these were "legacy networking convars that existed in CS:GO but
# never had an effect in CS2".
#
# What replaces them is cl_net_buffer_ticks, which is what CS2's own
# cl_interp_ratio help text points at, and it is deliberately not offered as a
# tweak: its right value is a property of the route, not of the machine, and the
# game exposes it in its own network settings menu. Recommending a number here
# would repeat the mistake in a new cvar.
#
# See tests/test_settings/test_cs2_cvars_exist.py for the guard.

CS2_SDR = SettingExecutor(
    id="game_config:cs2:sdr",
    category=SettingCategory.GAME_CONFIG,
    display_name="CS2 Steam Datagram Relay",
    short_name="CS2 Steam Datagram Relay",
    description="Sends match traffic over Valve's own backbone instead of the public internet, so the route "
    "to the server stops depending on whichever path your provider happens to pick.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "enabled"),
    default_value="default",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://totalcsgo.com/rates"],
    current_impact="Default: Traffic routed over public internet → variable latency and packet loss",
    recommended_impact="Enabled: Traffic on Valve's SDR backbone → more stable routing and lower jitter",
    scope=SettingScope.RECOMMENDED,
    category_order=6,
    effect="Routes CS2 traffic over Valve's SDR backbone for lower jitter",
    impact_scores={"latency_ms": -2, "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=_CS2_CFG_DETECT_BASE
    + "if ($c -match '===fpstune-cs2_sdr-start===') { Write-Output 'enabled' } "
    "else { Write-Output 'default' }",
    detect_args={
        "batch_config": "cs2",
        "batch_marker": "cs2_sdr",
        "batch_present": "enabled",
        "batch_absent": "default",
    },
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="cs2_sdr_toggle",
    apply_args={},
    apply_value_map={"enabled": "enabled", "default": "default"},
    value_hints={"default": "0", "enabled": "1"},
)

CS2_MAXPING = SettingExecutor(
    id="game_config:cs2:maxping",
    category=SettingCategory.GAME_CONFIG,
    display_name="CS2 Max Matchmaking Ping",
    short_name="CS2 Max Matchmaking Ping",
    description="Sets 'mm_dedicated_search_maxping 50' in CS2 autoexec.cfg. "
    "Prevents matchmaking from placing you on servers with >50 ms ping.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "50ms"),
    default_value="default",
    recommended_value="50ms",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://totalcsgo.com/rates"],
    current_impact="Default (150 ms): May connect to distant servers with high baseline latency",
    recommended_impact="50 ms limit: Only matches on nearby servers — consistent low-ping games",
    # latency_ms is 0.0 deliberately. This does not reduce latency; it changes which
    # servers you are matched to, and by how much depends entirely on what is nearby.
    # The old -12.0 was the sweep's clipping cap, and the frontend sums latency_ms
    # into the figure shown on Home, so it advertised a saving nobody could measure.
    scope=SettingScope.RECOMMENDED,
    category_order=7,
    effect="Limits matchmaking to servers within 50 ms for consistently low ping",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=_CS2_CFG_DETECT_BASE
    + "if ($c -match '===fpstune-cs2_maxping-start===') { Write-Output '50ms' } "
    "else { Write-Output 'default' }",
    detect_args={
        "batch_config": "cs2",
        "batch_marker": "cs2_maxping",
        "batch_present": "50ms",
        "batch_absent": "default",
    },
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="cs2_maxping_toggle",
    apply_args={},
    apply_value_map={"50ms": "50ms", "default": "default"},
    value_hints={"default": "150", "50ms": "50"},
)

CS2_QOS_TIMEOUT = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:qos_timeout",
    display_name="CS2 QoS Search Timeout",
    short_name="CS2 QoS Search Timeout",
    description="Sets 'mm_session_search_qos_timeout 20' in CS2 autoexec.cfg. "
    "Reduces the time spent waiting for QoS data before selecting a server.",
    cvar="mm_session_search_qos_timeout",
    cvar_value="20",
    default_cvar_value="30",
    marker="cs2_qos_timeout",
    current_impact="Default (30 s): Long QoS wait → slower matchmaking, may miss closer servers",
    recommended_impact="Optimized (20 s): Faster server selection → quicker match start",
    effect="Reduces QoS wait timeout to 20 s for faster matchmaking",
    impact_scores={"matchmaking_s": -10, "stability": "medium"},
    category_order=8,
    evidence_level="likely",
    sources=["https://totalcsgo.com/rates"],
)

# =============================================================================
# MW3 Settings
# =============================================================================

MW3_TEXTURE_STREAMING = SettingExecutor(
    id="game_config:mw3:texture_streaming",
    category=SettingCategory.GAME_CONFIG,
    display_name="MW3 Texture Streaming Limit",
    short_name="MW3 Texture Streaming Limit",
    description="Caps the bandwidth MW3 spends downloading textures over HTTP during a match. That download "
    "shares the line with the match's traffic, and the engine reports the delay as packet burst.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "minimal"),
    default_value="default",
    recommended_value="minimal",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    # Named compound (C8): a gate plus a cap. Activision's own description of the
    # feature is "bandwidth controls and a daily cap", which is exactly this pair
    # — HTTPStreamUsageLimit turns the cap on, HTTPStreamLimitMBytes sets it. The
    # mapping of each key to each half is still read off the names, but the
    # existence of a two-part control is documented, not guessed. Written
    # together because a cap with its gate off is what this shipped as for months.
    risk_warning="Writes HTTPStreamUsageLimit alongside the limit: Activision documents this feature as a bandwidth control plus a cap, and setting the cap without enabling the control leaves it inert. Blizzard may rename either key without notice.",
    sources=[
        "https://hone.gg/blog/stop-and-fix-packet-burst-in-warzone/",
        "https://www.dexerto.com/call-of-duty/how-to-fix-packet-burst-in-mw3-modern-warfare-3-issue-explained-2376825/",
    ],
    current_impact="1024 MB: Textures download over HTTP mid-match, sharing the line with match traffic",
    recommended_impact="0 MB: No mid-match texture download → the connection carries only the match",
    scope=SettingScope.COMPLETE,  # experimental risk is offered, never assumed (C2/#30)
    category_order=10,
    perceptible_cost=(
        "Some textures can stay at lower detail until they arrive with the next content update rather than mid-match."
    ),
    effect="Stops mid-match texture downloads competing with the match's own traffic",
    # Scored as network, not FPS. It was `{"fps_1_percent_low": "+5-15%"}` with
    # copy about texture pop-in, which put the single most-cited packet-burst fix
    # under the FPS tag — so the person searching for a packet-burst setting was
    # the one person who could not find it. The mechanism is bandwidth: players
    # report on the order of 20 GB of textures pulled in a day, and the engine
    # reports the contention as packet burst because it cannot distinguish a late
    # packet from a late frame.
    impact_scores={"latency_ms": 0.0, "bandwidth": "-20GB/day", "stability": "high"},
    # Detection: check gamerprofile HTTPStreamLimitMBytes value
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$docPath = [System.Environment]::GetFolderPath('MyDocuments'); "
        "$codPath = Join-Path $docPath 'Call of Duty MWIII\\players'; "
        "if (-not (Test-Path $codPath)) { Write-Output 'not_installed'; return }; "
        # Same file choice as the apply command, backups excluded: reading a
        # backup would report a state the game does not have.
        "$cfg = Get-ChildItem -Path $codPath -Recurse -Filter 'gamerprofile*.BASE.cst' "
        "-ErrorAction SilentlyContinue | "
        "Where-Object { $_.FullName -notmatch 'mw3fix_backup' } | "
        "Sort-Object LastWriteTime -Descending | "
        "Select-Object -First 1; "
        "if (-not $cfg) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($cfg.FullName, [System.Text.Encoding]::UTF8); "
        # Accepts BOTH shapes MW3 writes — `Key@0 = value` and `Key@ value` —
        # because which one a profile uses is a property of that profile, not of
        # the game version. Pinning either one made detection wrong on half the
        # installs while looking correct on the other half.
        "if ($c -match '(?m)^[ \\t]*HTTPStreamLimitMBytes@(?:\\d*[ \\t]*=[ \\t]*|[ \\t]+)(\\d+)') { "
        "if ($Matches[1] -eq '0') { Write-Output 'minimal' } else { Write-Output 'default' } "
        "} else { Write-Output 'default' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_texture_toggle",
    apply_args={},
    apply_value_map={"minimal": "minimal", "default": "default"},
    value_hints={"default": "1024 MB", "minimal": "0 MB"},
)

MW3_NAT_FIREWALL = SettingExecutor(
    id="game_config:mw3:nat_firewall",
    category=SettingCategory.GAME_CONFIG,
    display_name="MW3 Open NAT Firewall Rules",
    short_name="MW3 Open NAT Firewall Rules",
    description="Creates Windows Firewall rules opening every port MW3 and Warzone use (UDP 3074, 4380, "
    "27000-27036, 28950; TCP 3074, 3075, 27015-27030, 27036-27037). Open NAT means faster, more "
    "reliable matchmaking.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "open_nat"),
    default_value="default",
    recommended_value="open_nat",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://support.activision.com/cod-modern-warfare-3/articles/connectivity-troubleshooting",
        "https://www.activision.com/en/support/cod-modern-warfare-3/articles/firewall-ports-used-for-call-of-duty-games",
    ],
    current_impact="Default: Firewall may block MW3 ports → Strict/Moderate NAT → slower matchmaking",
    recommended_impact="Open NAT: All ports open → unrestricted peer connections → faster matchmaking",
    scope=SettingScope.RECOMMENDED,
    category_order=11,
    effect="Opens MW3/Warzone firewall ports for Open NAT and faster matchmaking",
    impact_scores={"latency_ms": -2, "matchmaking_s": -15, "stability": "high"},
    # Detection: check for fpstune-MW3-NAT firewall rules
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$rule = Get-NetFirewallRule -DisplayName 'fpstune-MW3-NAT-UDP-In' -ErrorAction SilentlyContinue; "
        "if ($rule) { Write-Output 'open_nat' } else { Write-Output 'default' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_nat_firewall_toggle",
    apply_args={},
    apply_value_map={
        "open_nat": "open_nat",
        "default": "default",
    },
    value_hints={"default": "blocked", "open_nat": "open"},
)

CS2_FPS_MAX = SettingExecutor(
    id="game_config:cs2:fps_max",
    category=SettingCategory.GAME_CONFIG,
    display_name="CS2 FPS Cap",
    short_name="CS2 FPS Cap",
    description="Adds 'fps_max 0' to CS2 autoexec.cfg, removing the engine FPS cap. "
    "Lets the GPU render as many frames as possible for minimum input latency.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "uncapped"),
    default_value="default",
    recommended_value="uncapped",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://totalcsgo.com/fps-commands",
    ],
    current_impact="Default (fps_max 300): Engine caps frames → unnecessary input latency floor",
    recommended_impact="Uncapped (fps_max 0): No frame cap → maximum frames → minimum input latency",
    scope=SettingScope.RECOMMENDED,
    category_order=2,
    effect="Removes CS2 engine FPS cap via autoexec.cfg for minimum input latency",
    impact_scores={"latency_ms": -1.5, "fps_cpu_bound": "+2-5%"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _CS2_CFG_PATH_PS + "if (-not (Test-Path $cfgPath)) { Write-Output 'default'; return }; "
        "$c = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8); "
        "if ($c -match '===fpstune-fps_max-start===') { Write-Output 'uncapped' } "
        "else { Write-Output 'default' }"
    ),
    detect_args={
        "batch_config": "cs2",
        "batch_marker": "fps_max",
        "batch_present": "uncapped",
        "batch_absent": "default",
    },
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="cs2_fps_max_toggle",
    apply_args={},
    apply_value_map={"uncapped": "uncapped", "default": "default"},
    value_hints={"default": "fps_max 300", "uncapped": "fps_max 0"},
)

# r_dynamic_lighting, cl_forcepreload and mat_queue_mode stood here. None of the
# three exists in CS2 — absent from all 102 shipped modules — and the copy for
# mat_queue_mode promised "the biggest single CS2 FPS lever" for a cvar the game
# does not parse.

# =============================================================================
# CS2 — Generic cvar tweaks (autoexec.cfg, cs2_cvar_toggle helper)
# =============================================================================
# These settings each write a single console command to autoexec.cfg behind
# a unique fpstune marker block, so the change is reversible.

CS2_DISABLE_RAGDOLLS = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:disable_ragdolls",
    display_name="CS2 Disable Ragdolls",
    short_name="CS2 Disable Ragdolls",
    description="Sets 'cl_disable_ragdolls 1' — kills client-side ragdoll "
    "physics on player corpses. Saves CPU cycles in firefights with multiple "
    "deaths and removes a known stutter source on entry-frag rounds.",
    cvar="cl_disable_ragdolls",
    cvar_value="1",
    default_cvar_value="0",
    marker="cs2_disable_ragdolls",
    current_impact="0 (default): Each death runs full ragdoll sim → CPU spike + brief stutter",
    recommended_impact="1: No per-death physics simulation → no CPU spike on entry frags",
    effect="Disables ragdoll physics — measurable 1% low FPS gain in fights",
    impact_scores={"fps_1_percent_low": "+1-3%", "cpu_usage": -0.5},
    category_order=11,
    evidence_level="proven",
    # Stays in the default scopes under consequence 5: a corpse falling
    # realistically decides nothing, so the physics simulation is decoration.
    # What was removed is the line "Bodies snap to static pose" — that is a claim
    # about what stays on the screen, and whether the body remains at all decides
    # whether this is decoration or the loss of a marker saying an enemy died
    # here. Nothing in this repo establishes it, and a byte scan of the shipped
    # modules recovers cvar names but not the game's own description of them, so
    # the reassurance is dropped rather than repeated. Settling it needs the game
    # running; until then the copy claims only the part that is known.
)

CS2_TRACERS_FIRSTPERSON = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:tracers_firstperson",
    display_name="CS2 Disable First-Person Tracers",
    short_name="CS2 Disable First-Person Tracers",
    description="Sets 'r_drawtracers_firstperson 0' — hides bullet tracer "
    "effects from your own weapon (third-person tracers still drawn, so enemy "
    "fire is still visible). Cleaner sight picture during sprays.",
    cvar="r_drawtracers_firstperson",
    cvar_value="0",
    default_cvar_value="1",
    marker="cs2_tracers_firstperson",
    current_impact="1 (default): Tracers from your gun obscure crosshair on full sprays",
    recommended_impact="0: Cleaner crosshair → better spray tracking, slight GPU saving",
    effect="Removes own-weapon tracer effects for cleaner spray vision",
    impact_scores={"fps_gpu_bound": "+0-1%", "stability": "unchanged"},
    category_order=12,
    evidence_level="proven",
)

CS2_LOW_LATENCY_SLEEP = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:low_latency_sleep",
    display_name="CS2 Low-Latency Sleep After Tick",
    short_name="CS2 Low-Latency Sleep After Tick",
    description="Moves the engine's low-latency sleep to after the client tick instead of before, tightening "
    "render latency with Reflex-style pacing. Pairs best with a capped fps_max.",
    cvar="engine_low_latency_sleep_after_client_tick",
    cvar_value="true",
    default_cvar_value="false",
    marker="cs2_low_latency_sleep",
    current_impact="false (default): Sleep before client tick → an extra frame of input lag",
    recommended_impact="true: Sleep after tick → tighter input → display latency",
    effect="Tightens engine frame-pacing for lower input latency",
    impact_scores={"latency_ms": -0.5},
    category_order=13,
    evidence_level="likely",
    # ESSENTIAL for the same reason as MW3's Reflex: it changes state (CS2 ships
    # false), and the effect is a frame of input lag rather than a cosmetic one.
    scope=SettingScope.ESSENTIAL,
)

CS2_AUTOHELP = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:autohelp",
    display_name="CS2 Disable Auto-Help",
    short_name="CS2 Disable Auto-Help",
    description="Sets 'cl_autohelp 0' — turns off the in-game help/hint popups "
    "(weapon pickup hints, mode tutorials). Removes UI rendering cost and "
    "reduces visual clutter.",
    cvar="cl_autohelp",
    cvar_value="0",
    default_cvar_value="1",
    marker="cs2_autohelp",
    current_impact="1 (default): Help popups render every match → minor UI overhead + clutter",
    recommended_impact="0: No popups → cleaner HUD, marginal FPS gain in match start",
    effect="Disables in-game help popups for cleaner HUD",
    impact_scores={"fps_cpu_bound": "+0-1%", "stability": "high"},
    category_order=14,
    evidence_level="proven",
)

CS2_GAME_INSTRUCTOR = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:game_instructor",
    display_name="CS2 Disable Game Instructor",
    short_name="CS2 Disable Game Instructor",
    description="Sets 'gameinstructor_enable 0' — disables the tutorial overlay "
    "system. Frees a small amount of CPU and removes intrusive instructional "
    "messages from the HUD.",
    cvar="gameinstructor_enable",
    cvar_value="0",
    default_cvar_value="1",
    marker="cs2_game_instructor",
    current_impact="1 (default): Instructor system runs lessons checks every tick",
    recommended_impact="0: Subsystem off → marginal CPU saving, no tutorial popups",
    effect="Disables tutorial overlay system",
    impact_scores={"fps_cpu_bound": "+0-1%", "stability": "high"},
    category_order=15,
    evidence_level="proven",
)

# cl_disablefreezecam stood here, and CS2 has no such cvar.

CS2_VIOLENCE_HBLOOD = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:violence_hblood",
    display_name="CS2 Disable Blood Decals",
    short_name="CS2 Disable Blood Decals",
    description="Sets violence_hblood 0 in CS2's autoexec.cfg, removing blood decals. Blood confirms a hit "
    "you could not otherwise see land and marks the wall where a fight already happened.",
    cvar="violence_hblood",
    cvar_value="0",
    default_cvar_value="1",
    marker="cs2_violence_hblood",
    current_impact="1 (default): Blood decals rendered per kill → GPU memory churn in high-kill rounds",
    recommended_impact="0: No blood decals → marginal FPS gain, and no hit confirmation on a target you cannot see",
    effect="Removes blood decals, and with them the hit confirmation they carry",
    impact_scores={"fps_1_percent_low": "+0-1%", "stability": "high"},
    category_order=17,
    perceptible_cost=("Blood effects are reduced — hit feedback is less visible on screen."),
    evidence_level="proven",
    # COMPLETE, by consequence 5, and the product was already arguing this case
    # against itself. game_config:mw3:persistent_effects locks MW3's bullet decals
    # ON with the reason written out — "the decals reveal recent enemy fire and
    # prior engagements — competitive intel, not pure cosmetic" — and then CS2
    # turned the same class of decal off by default. Blood is the CS2 version of
    # that intel: through smoke or at range it is often the only confirmation a
    # shot landed. Same rule, so the same answer.
    scope=SettingScope.COMPLETE,
)

CS2_VIOLENCE_AGIBS = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:violence_agibs",
    display_name="CS2 Disable Body Gibs",
    short_name="CS2 Disable Body Gibs",
    description="Sets 'violence_agibs 0' in CS2 autoexec.cfg, disabling player body "
    "fragmentation (gibbing) on death. Removes gib physics calculations at round end.",
    cvar="violence_agibs",
    cvar_value="0",
    default_cvar_value="1",
    marker="cs2_violence_agibs",
    current_impact="1 (default): Body gibs simulated on death → brief CPU spike at round end",
    recommended_impact="0: No gib simulation → cleaner round-end frametimes",
    effect="Disables body gib physics for cleaner round-end frametimes",
    impact_scores={"fps_1_percent_low": "+0-1%", "stability": "high"},
    category_order=18,
    evidence_level="proven",
)

CS2_DRAW_PARTICLES = _make_cs2_cvar_setting(
    setting_id="game_config:cs2:draw_particles",
    display_name="CS2 Disable Cosmetic Particles",
    short_name="CS2 Disable Cosmetic Particles",
    description="Sets r_drawparticles 0 in CS2's autoexec.cfg, turning off the particle pass. Impact sparks "
    "show where fire comes from and emitters show a molotov's area: information traded for a "
    "sliver of a frame.",
    cvar="r_drawparticles",
    cvar_value="0",
    default_cvar_value="1",
    marker="cs2_r_drawparticles",
    current_impact="1 (default): Impact sparks and fire rendered → GPU draw call overhead in firefights",
    recommended_impact="0: No particle pass → fewer draw calls, and incoming fire stops announcing itself",
    effect="Turns off the particle draw pass, including impact sparks and molotov fire",
    impact_scores={"fps_1_percent_low": "+0-1%", "fps_gpu_bound": "+0-1%"},
    category_order=19,
    perceptible_cost=("Fewer particles are drawn — some effect cues render smaller than stock."),
    evidence_level="proven",
    # COMPLETE, by consequence 5. Two things had to change here. The copy claimed
    # "smoke grenades use a separate renderer and are unaffected", which nothing
    # in this repo establishes — the cvar lives in particles.dll and a byte scan
    # of the shipped modules can confirm the name exists but not what it spares —
    # so an unverifiable reassurance is removed rather than restated. And what the
    # copy *did* admit it removes, impact sparks and fire emitters, is information:
    # sparks are the direction of incoming fire and fire is the shape of an area
    # you must not walk into. Under 1% of a frame is not the price of either, but
    # it is offered, because the player may disagree.
    scope=SettingScope.COMPLETE,
)

# cl_detail_max_sway and r_eyegloss stood here. Neither exists in CS2.

# CS2_SOUND_LATENCY was removed 2026-08-11. It wrote `snd_mixahead 0.05` into
# autoexec.cfg and claimed a 12 ms latency saving, but the command does not
# exist in CS2 — Valve dropped the Source 1 audio tuning commands
# (snd_mixahead, snd_mix_async, snd_headphone_pan_exponent, the headphone
# position pair) when the game moved to Source 2 and Steam Audio, which manages
# the buffer itself. CS2 answers "unknown command", and a dead line in an
# autoexec is simply ignored.
# It reported success because detection only looked for fpstune's own marker in
# the file rather than reading anything the game acts on, so the setting could
# never disagree with itself. #74's contradiction — copy said 100 -> 50 ms,
# impact_scores said -12 ms — had no right answer: the true figure was zero.
# Do not re-add it from a guide; several "CS2 command" lists still circulating
# are recycled CS:GO configs.


# =============================================================================
# Heroes of the Storm — Documents\Heroes of the Storm\Variables.txt
# =============================================================================
# Every key below was read off a real Variables.txt rather than taken from a
# guide, which is the only reason they are here: the file is plain key=value and
# a key the game does not read is indistinguishable from one it does until the
# game rewrites the file on exit.
#
# Two shapes appear in the same file — `vsync=true` and
# `GraphicsOptionTextureQuality[2]=0` — and the bracketed index is the game's,
# not ours. See hots_variable_set for how it is preserved.

_HOTS_SOURCES = [
    "https://us.forums.blizzard.com/en/heroes/t/performance-guide/",
]


def _make_hots_setting(
    *,
    setting_id: str,
    display_name: str,
    short_name: str = "",
    description: str,
    key: str,
    default_value: str,
    recommended_value: str,
    choices: tuple[str, ...],
    current_impact: str,
    recommended_impact: str,
    effect: str,
    impact_scores: dict[str, str | float],
    category_order: int,
    scope: SettingScope = SettingScope.RECOMMENDED,
    evidence_level: str = "likely",
    value_hints: dict[str, str] | None = None,
    value_type: SettingValueType = SettingValueType.CHOICE,
    risk_level: Literal["safe", "low", "moderate", "advanced"] = "low",
    risk_warning: str | None = None,
    perceptible_cost: str | None = None,
) -> SettingExecutor:
    """Build a Heroes of the Storm setting backed by one Variables.txt key."""
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
        requires_reboot=False,
        risk_level=risk_level,
        risk_warning=risk_warning,
        evidence_level=evidence_level,
        sources=_HOTS_SOURCES,
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        scope=scope,
        perceptible_cost=perceptible_cost,
        category_order=category_order,
        effect=effect,
        impact_scores=impact_scores,
        detect_type=DetectType.POWERSHELL,
        # No detect_command: unlike the CS2 settings there is no per-setting
        # PowerShell fallback to keep, because the batch read is the only path
        # and a second implementation is a second answer waiting to disagree.
        detect_command="",
        detect_args={"batch_config": "hots", "batch_key": key},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command="hots_variable_set",
        apply_args={"key": key},
        apply_value_map={},
        value_hints=value_hints or {},
    )


HOTS_VSYNC = _make_hots_setting(
    setting_id="game_config:hots:vsync",
    display_name="HotS Vertical Sync",
    short_name="HotS Vertical Sync",
    description="In-game frame synchronisation. On a variable-refresh panel the driver already holds the "
    "frame rate inside the G-Sync window, so a second V-Sync only adds the wait the display was "
    "chosen to remove.",
    key="vsync",
    default_value="true",
    recommended_value="false",
    choices=("true", "false"),
    current_impact="true: Frames held for the next refresh on top of what the driver already does",
    recommended_impact="false: The driver alone governs presentation → no doubled sync wait",
    effect="Leaves frame synchronisation to the driver instead of syncing twice",
    # The documented pairing is driver V-Sync on, in-game V-Sync off; two layers
    # of sync is the configuration that costs latency without removing tearing
    # the first layer did not already remove.
    impact_scores={"latency_ms": -8, "stability": "high"},
    category_order=40,
    scope=SettingScope.ESSENTIAL,
    evidence_level="proven",
)

HOTS_MOVIES = _make_hots_setting(
    setting_id="game_config:hots:movies",
    display_name="HotS Cinematics",
    short_name="HotS Cinematics",
    description="Pre-rendered movie playback in menus and at match start. These are video files "
    "decoded before a match rather than anything rendered during one.",
    key="GraphicsOptionMovies",
    default_value="1",
    recommended_value="0",
    choices=("0", "1"),
    current_impact="1: Cinematics decoded before the match → longer loads and pointless GPU work",
    recommended_impact="0: No cinematic playback → the machine reaches the match cooler",
    effect="Skips cinematic playback so the GPU is idle until the match starts",
    # Thermal, not fps: this buys nothing during a fight. It stops the card
    # arriving at one already warm, which is the category's whole point.
    impact_scores={"gpu_temp_c": "-1-3", "stability": "high"},
    category_order=41,
    value_hints={"0": "Off", "1": "On"},
)

HOTS_PORTRAITS = _make_hots_setting(
    setting_id="game_config:hots:portraits_3d",
    display_name="HotS 3D Portraits",
    short_name="HotS 3D Portraits",
    description="Renders hero portraits as live 3D models rather than flat images. The models are "
    "redrawn every frame in a corner of the screen you are not reading during a fight.",
    key="GraphicsOptionPortraits",
    default_value="1",
    recommended_value="0",
    choices=("0", "1"),
    current_impact="1: Portrait models redrawn every frame alongside the match itself",
    recommended_impact="0: Flat portraits → the frame budget goes to the fight",
    effect="Draws flat hero portraits instead of live 3D models",
    impact_scores={"fps_gpu_bound": "+0-2%", "stability": "high"},
    category_order=42,
    value_hints={"0": "Off", "1": "On"},
)

HOTS_SHADOW_QUALITY = _make_hots_setting(
    setting_id="game_config:hots:shadow_quality",
    display_name="HotS Shadow Quality",
    short_name="HotS Shadow Quality",
    description="Resolution and filtering of cast shadows. Shadows are consistently the most "
    "expensive per-frame effect in this engine and the least useful for reading a teamfight.",
    key="GraphicsOptionShadowQuality",
    default_value="2",
    recommended_value="0",
    choices=("0", "1", "2", "3"),
    current_impact="Higher: Shadow maps re-rendered per light every frame → GPU time in fights",
    recommended_impact="0: No shadow map passes → the largest single frame-time saving here",
    effect="Removes shadow map rendering, the engine's most expensive per-frame pass",
    impact_scores={"fps_gpu_bound": "+3-8%", "stability": "high"},
    category_order=43,
    # Decorative in this game, and that is a per-game judgement rather than a
    # global one. Heroes of the Storm is played from a fixed isometric camera:
    # a shadow never reveals an enemy who is not already on screen, the way one
    # cast around a corner does in a first-person shooter. Nothing here tells the
    # player something they could not otherwise see, so it is spendable.
    scope=SettingScope.RECOMMENDED,
    value_hints={"0": "Low", "1": "Medium", "2": "High", "3": "Ultra"},
)

HOTS_POST_PROCESSING = _make_hots_setting(
    setting_id="game_config:hots:post_processing",
    display_name="HotS Post-Processing",
    short_name="HotS Post-Processing",
    description="Full-screen effects applied after the scene is drawn, such as bloom and depth of "
    "field. Each one is another pass over every pixel, and several of them actively obscure the "
    "board.",
    key="GraphicsOptionPostProcessing",
    default_value="2",
    recommended_value="0",
    choices=("0", "1", "2", "3"),
    current_impact="Higher: Extra full-screen passes per frame, some of which blur the board",
    recommended_impact="0: No post passes → clearer read of the fight and frame time back",
    effect="Removes full-screen post-processing passes",
    impact_scores={"fps_gpu_bound": "+2-5%", "stability": "high"},
    category_order=44,
    value_hints={"0": "Low", "1": "Medium", "2": "High", "3": "Ultra"},
)

HOTS_SSAO = _make_hots_setting(
    setting_id="game_config:hots:ssao",
    display_name="HotS Ambient Occlusion",
    short_name="HotS Ambient Occlusion",
    description="Screen-space ambient occlusion, the soft contact shadowing where objects meet the "
    "ground. It is a per-pixel pass whose entire output is subtle shading.",
    key="GraphicsOptionSSAO",
    default_value="1",
    recommended_value="0",
    # 0-3 across every GraphicsOption* key rather than a per-key range: the
    # engine's own levels were read off one machine's file, where all of them sat
    # at 0, so the upper bound is inferred. A choices tuple narrower than the
    # game's real range would make a legitimate reading illegal (C6).
    choices=("0", "1", "2", "3"),
    current_impact="On: A per-pixel occlusion pass every frame for subtle contact shading",
    recommended_impact="0: No occlusion pass → frame time back for no loss of information",
    effect="Disables the screen-space ambient occlusion pass",
    impact_scores={"fps_gpu_bound": "+2-4%", "stability": "high"},
    category_order=45,
    value_hints={"0": "Off", "1": "On", "2": "High"},
)

HOTS_REFLECTIONS = _make_hots_setting(
    setting_id="game_config:hots:reflections",
    display_name="HotS Reflections",
    short_name="HotS Reflections",
    description="Water and other reflective surfaces re-render part of the scene a second time to produce the "
    "reflection. Nothing in that second image is ever acted on.",
    key="GraphicsOptionReflections",
    default_value="1",
    recommended_value="0",
    choices=("0", "1", "2", "3"),
    current_impact="On: Reflective surfaces re-render the scene a second time",
    recommended_impact="0: No reflection pass → one scene drawn per frame instead of two",
    effect="Disables the second scene pass reflective surfaces require",
    impact_scores={"fps_gpu_bound": "+1-4%", "stability": "high"},
    category_order=46,
    value_hints={"0": "Off", "1": "On", "2": "High"},
)

HOTS_PHYSICS_QUALITY = _make_hots_setting(
    setting_id="game_config:hots:physics_quality",
    display_name="HotS Physics Quality",
    short_name="HotS Physics Quality",
    description="Cloth, ragdoll and debris simulation on hero models. None of it affects what "
    "happens in a match — it is decoration that costs CPU time during fights.",
    key="GraphicsOptionPhysicsQuality",
    default_value="1",
    recommended_value="0",
    choices=("0", "1", "2", "3"),
    current_impact="On: Cloth and ragdoll simulated per frame, heaviest exactly during teamfights",
    recommended_impact="0: No physics simulation → CPU time back when the fight is busiest",
    effect="Stops simulating cloth and ragdoll decoration during fights",
    # CPU-bound rather than GPU: this competes with the simulation work that
    # actually decides the match, and it peaks when the most models are on screen.
    impact_scores={"fps_cpu_bound": "+1-4%", "stability": "high"},
    category_order=47,
    value_hints={"0": "Off", "1": "On", "2": "High"},
)

HOTS_EFFECTS_DETAIL = _make_hots_setting(
    setting_id="game_config:hots:effects_detail",
    display_name="HotS Effects Detail",
    short_name="HotS Effects Detail",
    description="Detail of ability and spell effects. In this game an ability announces itself by "
    "its effect, so this is the one graphics setting that decides what the player can read rather "
    "than how good it looks.",
    key="GraphicsOptionEffectsDetail",
    # High rather than Ultra, deliberately. The rule is enough to tell what was
    # cast, not the maximum the engine offers: Ultra adds density to effects that
    # are already fully legible at High, and pays frames for it.
    default_value="2",
    recommended_value="2",
    choices=("0", "1", "2", "3"),
    current_impact="0 (Low): Spell effects are simplified → an enemy cast is harder to read",
    recommended_impact="2 (High): Abilities read at a glance, at a few frames in a teamfight",
    effect="Restores ability effects to the detail that keeps a cast readable",
    # No fps key at all, in either sign. This setting costs frames and buys
    # information, and putting a negative percentage under a key the UI renders
    # as a gain is how a cost gets read as a benefit — the same conflation
    # consequence 4 forbids, running backwards. The cost is stated in the copy
    # instead, where it cannot be mistaken for a win.
    impact_scores={"ability_readability": "restored", "stability": "high"},
    category_order=48,
    evidence_level="likely",
    value_hints={"0": "Low", "1": "Medium", "2": "High", "3": "Ultra"},
)


def create_hots_sound_sample_rate_setting(device_hz: int) -> SettingExecutor:
    """Build the HotS audio sample rate, derived from this machine's output device.

    22050 Hz carries nothing above about 11 kHz, and the cues that tell a player
    *where* a sound came from live in exactly that band — so a mix rate below the
    output device is a functional loss the same way a flattened spell effect is,
    and raising it is a tweak by consequence 5. Observed in the wild: a config
    holding ``SoundSampleRate=22050`` on a system whose every active render
    endpoint ran at 48000.

    The rate comes from the device rather than a constant because resampling to a
    rate the endpoint does not run at is work for no gain: matching what Windows
    already outputs is both the highest useful value and the cheapest one.
    """
    # The engine's own ladder. 48000 is the endpoint rate on essentially every
    # modern device; 96000 endpoints are fed from 48000 without losing anything a
    # game emits, so the ladder stops there rather than inventing a level.
    target = "48000" if device_hz >= 48000 else "44100" if device_hz >= 44100 else "22050"
    return _make_hots_setting(
        setting_id="game_config:hots:sound_sample_rate",
        display_name="HotS Audio Sample Rate",
        short_name="HotS Audio Sample Rate",
        description=f"The rate the game mixes audio at. This machine's output device runs at "
        f"{device_hz} Hz, and a game mixing below that throws away the high frequencies that "
        "carry direction before Windows ever sees them.",
        key="SoundSampleRate",
        default_value="44100",
        recommended_value=target,
        choices=("22050", "44100", "48000"),
        current_impact="22050: Nothing above ~11 kHz survives → footstep direction is degraded",
        recommended_impact=f"{target}: The game mixes at the rate the device actually outputs",
        effect="Mixes game audio at the output device's own rate instead of below it",
        impact_scores={"footstep_clarity": "restored", "fps": "0%"},
        category_order=49,
        scope=SettingScope.RECOMMENDED,
        evidence_level="likely",
        risk_level="moderate",
        risk_warning=(
            "Heroes of the Storm rewrites Variables.txt on exit and may clamp this to a rate its "
            "own audio menu offers. Launch the game once and re-scan: if it reads lower again, "
            "the ladder is the game's and this machine cannot go higher."
        ),
        value_hints={"22050": "22.05 kHz", "44100": "44.1 kHz", "48000": "48 kHz"},
    )


HOTS_SETTINGS: list[SettingExecutor] = [
    HOTS_VSYNC,
    HOTS_MOVIES,
    HOTS_PORTRAITS,
    HOTS_SHADOW_QUALITY,
    HOTS_POST_PROCESSING,
    HOTS_SSAO,
    HOTS_REFLECTIONS,
    HOTS_PHYSICS_QUALITY,
    HOTS_EFFECTS_DETAIL,
]


def create_hots_refresh_rate_setting(max_hz: int) -> SettingExecutor:
    """Build the HotS refresh rate, derived from the attached panel.

    The game caps its own output to whatever this key says, regardless of what
    the display or the machine can do, so a stale value here is a ceiling no
    graphics setting in the product can win back.

    Two things were measured before this shipped, because writing a file is not
    the same as the game honouring it. On a system whose panel reported 300 Hz —
    with Windows offering it and the desktop already running at it — the file
    held 270 and the game's own options menu offered nothing above 270. After
    ``refreshrate=300`` was written, the game kept the value *and* began offering
    300 in its menu, where it had not appeared before.

    That is the strongest form this setting can take: it is not correcting a
    number the player could have fixed themselves, because the interface did not
    expose the panel's own rate until the file said so. The value is still
    derived per machine — the observation is that the game accepts a derived one.
    """
    target = str(max_hz)
    return _make_hots_setting(
        setting_id="game_config:hots:refresh_rate",
        display_name="HotS Refresh Rate",
        short_name="HotS Refresh Rate",
        description=f"The rate Heroes of the Storm drives the display at. This panel reports "
        f"{max_hz} Hz, and the game caps its own output to whatever is set here no matter what "
        "the machine can render.",
        key="refreshrate",
        # Derived, so default equals recommended: there is no stock value to
        # restore, and the setting's job is to catch the panel changing.
        default_value=target,
        recommended_value=target,
        # Deliberately not a CHOICE of one. Detection reads whatever the file
        # holds — 270 on this machine — and a single-entry choices tuple would
        # make the reading illegal the moment it disagreed with the panel, which
        # is precisely the case the setting exists to report.
        choices=(),
        value_type=SettingValueType.STRING,
        current_impact=f"Below {max_hz} Hz: The panel is driven under its own capability",
        recommended_impact=f"{max_hz} Hz: The game drives the panel at its full rate",
        effect=f"Drives the display at its full {max_hz} Hz",
        impact_scores={"fps": f"up to +{max_hz}Hz ceiling", "latency_ms": -2.0},
        category_order=39,
        scope=SettingScope.ESSENTIAL,
        # Proven on hardware, both halves of it: the panel reports the rate, and
        # the game was observed accepting it and then offering it in its own
        # menu, which it had not done before the file was written.
        evidence_level="proven",
        value_hints={target: f"{max_hz} Hz"},
    )


# =============================================================================
# Exports
# =============================================================================

CS2_SETTINGS: list[SettingExecutor] = [
    CS2_SDR,
    CS2_MAXPING,
    CS2_QOS_TIMEOUT,
    CS2_FPS_MAX,
    CS2_DISABLE_RAGDOLLS,
    CS2_TRACERS_FIRSTPERSON,
    CS2_LOW_LATENCY_SLEEP,
    CS2_AUTOHELP,
    CS2_GAME_INSTRUCTOR,
    CS2_VIOLENCE_HBLOOD,
    CS2_VIOLENCE_AGIBS,
    CS2_DRAW_PARTICLES,
]

MW3_WORLD_STREAMING = SettingExecutor(
    id="game_config:mw3:world_streaming_quality",
    category=SettingCategory.GAME_CONFIG,
    display_name="MW3 On-Demand Texture Streaming",
    short_name="MW3 On-Demand Texture Streaming",
    description="How much MW3 downloads on demand during a match, the in-game Minimal and Optimized labels. "
    "Season 5 Reloaded removed Off, so Low is the least this build downloads, keeping the line "
    "clear.",
    value_type=SettingValueType.CHOICE,
    choices=("Low", "High"),
    default_value="High",
    recommended_value="Low",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Streaming quality reduction may cause blurry textures on the first visit to each area until the cache warms up.",
    sources=[
        "https://hone.gg/blog/stop-and-fix-packet-burst-in-warzone/",
        "https://www.sportskeeda.com/call-of-duty-game/best-on-demand-texture-streaming-setting-mw3-warzone",
    ],
    current_impact="High (Optimized): Downloads high-quality textures mid-match, competing with match traffic",
    recommended_impact="Low (Minimal): Downloads only what the match needs → fewer hitches and less contention",
    # COMPLETE, by consequence 5. This is the streaming pair's *quality* half, and
    # its own warning names the cost: textures stay blurry on the first visit to
    # each area. A blurred surface is a surface an enemy is harder to pick out of,
    # so it is offered rather than assumed. The bandwidth benefit that made this
    # worth shipping does not go with it — game_config:mw3:texture_streaming caps
    # the mid-match download itself and stays in the default scopes, so the
    # packet-burst fix is still applied without spending what the player sees.
    scope=SettingScope.COMPLETE,
    category_order=12,
    perceptible_cost=("Distant scenery streams in later — brief pop-in when the view swings."),
    effect="Downloads only essential textures so the line stays free for the match",
    # Network first, frames second — the hitches are downstream of the download,
    # not of the rendering. See the note on game_config:mw3:texture_streaming.
    impact_scores={"bandwidth": "reduced", "fps_1_percent_low": "+2-8%", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$docPath = [System.Environment]::GetFolderPath('MyDocuments'); "
        "$optPath = Join-Path $docPath 'Call of Duty MWIII\\players\\options.4.cod23.cst'; "
        "if (-not (Test-Path $optPath)) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($optPath, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'(?m)^\\s*WorldStreamingQuality:[\\d.]+\\s*=\\s*"([^"]+)"\') { '
        "Write-Output $Matches[1] } else { Write-Output 'not_installed' }"
    ),
    detect_args={"batch_config": "mw3", "batch_key": "WorldStreamingQuality"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_options_toggle",
    apply_args={"key": "WorldStreamingQuality:0.0"},
    apply_value_map={"Low": "Low", "High": "High"},
)

MW3_LOCAL_TEXTURE_QUALITY = SettingExecutor(
    id="game_config:mw3:local_texture_quality",
    category=SettingCategory.GAME_CONFIG,
    display_name="MW3 Local Texture Streaming Quality",
    short_name="MW3 Local Texture Streaming Quality",
    description="How many textures fit in the local streaming cache, as virtual texture memory slots. Lower "
    "means less VRAM pressure.",
    value_type=SettingValueType.CHOICE,
    choices=("Extra Small", "Small", "Medium", "Large", "Extra Large"),
    default_value="Large",
    recommended_value="Medium",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Reducing texture slots below your VRAM capacity may cause lower-resolution textures until the streaming cache stabilises.",
    sources=[
        "https://www.reddit.com/r/CODWarzone/comments/texture_streaming_fix",
    ],
    current_impact="Large: 1024 texture slots → higher VRAM usage, may cause stutters on 8 GB cards",
    recommended_impact="Medium: 529 slots → lower VRAM pressure, more stable frametimes on 8 GB VRAM",
    # COMPLETE, by consequence 5, and for a second reason as well. Texture detail
    # on an enemy model is the first thing on the functional side of that rule,
    # and this setting's own warning says cutting slots leaves textures at lower
    # resolution until the cache settles. The second reason is that it was being
    # recommended on every machine while its own copy justifies it by 8 GB of
    # VRAM: on a larger card Large costs nothing and Medium buys nothing but a
    # softer picture. Deriving the slot count from the card the way
    # game_config:mw3:vram_scale already derives its own is the better answer and
    # is not this change; until then the trade is offered, not made for the user.
    scope=SettingScope.COMPLETE,
    category_order=13,
    perceptible_cost=(
        "Fewer textures stay cached — occasional softer surfaces while they restream."
    ),
    effect="Reducing local texture slots lowers VRAM pressure for stable frametimes",
    impact_scores={"fps_1_percent_low": "+2-8%", "vram_mb": -500, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$docPath = [System.Environment]::GetFolderPath('MyDocuments'); "
        "$optPath = Join-Path $docPath 'Call of Duty MWIII\\players\\options.4.cod23.cst'; "
        "if (-not (Test-Path $optPath)) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($optPath, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'(?m)^\\s*VirtualTexturingMemoryMode:[\\d.]+\\s*=\\s*"([^"]+)"\') { '
        "Write-Output $Matches[1] } else { Write-Output 'not_installed' }"
    ),
    detect_args={"batch_config": "mw3", "batch_key": "VirtualTexturingMemoryMode"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_options_toggle",
    apply_args={"key": "VirtualTexturingMemoryMode:0.1"},
    apply_value_map={
        "Extra Small": "Extra Small",
        "Small": "Small",
        "Medium": "Medium",
        "Large": "Large",
        "Extra Large": "Extra Large",
    },
)

# =============================================================================
# MW3 — options.4.cod23.cst In-Game Settings (helper-based)
# =============================================================================
# All settings below edit Documents\Call of Duty MWIII\players\options.4.cod23.cst
# via the generic mw3_options_toggle apply command. Detect reads the cst file
# and extracts the key's current value.

# (?m)^\s* anchors to start-of-line so 'ShadowQuality' does not match
# the suffix of longer keys like 'ScreenSpaceShadowQuality'. Without this,
# ShadowQuality would incorrectly read ScreenSpaceShadowQuality's value.
_MW3_CST_DETECT_TEMPLATE = (
    "$docPath = [System.Environment]::GetFolderPath('MyDocuments'); "
    "$optPath = Join-Path $docPath 'Call of Duty MWIII\\players\\options.4.cod23.cst'; "
    "if (-not (Test-Path $optPath)) {{ Write-Output 'not_installed'; return }}; "
    "$c = [System.IO.File]::ReadAllText($optPath, [System.Text.Encoding]::UTF8); "
    'if ($c -match \'(?m)^\\s*{key_name}:[\\d.]+\\s*=\\s*"([^"]+)"\') {{ '
    "Write-Output $Matches[1] }} else {{ Write-Output 'not_installed' }}"
)


def _make_mw3_cst_setting(
    *,
    setting_id: str,
    display_name: str,
    short_name: str = "",
    description: str,
    cst_key: str,
    choices: tuple[str, ...],
    default_value: str | int,
    recommended_value: str | int,
    current_impact: str,
    recommended_impact: str,
    effect: str,
    impact_scores: dict[str, str | float],
    category_order: int,
    evidence_level: str = "likely",
    sources: list[str] | None = None,
    risk_level: Literal["safe", "low", "moderate", "advanced"] = "low",
    risk_warning: str | None = None,
    value_hints: dict[str, str] | None = None,
    applicable_conditions: dict[str, str] | None = None,
    value_type: SettingValueType = SettingValueType.CHOICE,
    scope: SettingScope = SettingScope.RECOMMENDED,
    min_value: int | None = None,
    max_value: int | None = None,
    perceptible_cost: str | None = None,
) -> SettingExecutor:
    """Build a SettingExecutor that reads/writes a single options.4.cod23.cst key.

    ``value_type`` and ``scope`` are parameters rather than constants because the
    cst file holds numeric keys (frame caps, LOD levels) as well as enumerations,
    and because hardcoding RECOMMENDED put all 73 MW3 settings in one bucket,
    which made the Essential/Recommended/Complete selector inert for the largest
    category in the product.
    """
    key_name = cst_key.split(":", 1)[0]
    detect_cmd = _MW3_CST_DETECT_TEMPLATE.format(key_name=key_name)
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
        sources=sources or [],
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
        detect_command=detect_cmd,
        # All MW3 settings read the same options.4.cod23.cst; the batch args
        # serve them from one cached read. detect_command remains the fallback
        # for single-setting detects outside a scan.
        detect_args={"batch_config": "mw3", "batch_key": key_name},
        apply_type=DetectType.POWERSHELL,
        apply_command="mw3_options_toggle",
        apply_args={"key": cst_key},
        apply_value_map={c: c for c in choices},
        value_hints=value_hints or {},
        applicable_conditions=applicable_conditions or {},
    )


_MW3_SOURCES = [
    "https://www.charlieintel.com/call-of-duty/best-modern-warfare-3-pc-settings-279371/",
    "https://www.dexerto.com/call-of-duty/modern-warfare-3-best-settings-on-pc-for-fps-graphics-visibility-more-2336306/",
    "https://www.digitaltrends.com/computing/call-of-duty-modern-warfare-3-best-settings-pc-benchmarks-performance/",
]


MW3_NVIDIA_REFLEX = _make_mw3_cst_setting(
    setting_id="game_config:mw3:nvidia_reflex",
    display_name="MW3 NVIDIA Reflex",
    short_name="MW3 NVIDIA Reflex",
    description="NVIDIA Reflex Low Latency. 'Enabled + boost' forces the GPU to maximum clock "
    "regardless of workload, reducing render queue latency. Free input lag reduction on RTX cards.",
    cst_key="NvidiaReflex:0.0",
    choices=("Disabled", "Enabled", "Enabled + boost"),
    default_value="Disabled",
    recommended_value="Enabled + boost",
    current_impact="Disabled: Render queue accumulates → ~10-20 ms extra input lag",
    recommended_impact="Enabled + boost: Forces max GPU clock + Reflex pipeline → ~5-15 ms lower input lag",
    effect="Free input latency reduction on NVIDIA RTX GPUs (no FPS cost)",
    impact_scores={"latency_ms": -3, "stability": "high"},
    category_order=14,
    # ESSENTIAL: it genuinely changes state (the game ships Reflex Disabled), it is
    # proven, and its effect is first-order input latency at no FPS cost. Most of the
    # other latency-named MW3 settings turned out to already sit at their ideal
    # default, so promoting them would fill the conservative preset with no-ops.
    scope=SettingScope.ESSENTIAL,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW3_DLSS_FRAME_GENERATION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dlss_frame_generation",
    display_name="MW3 DLSS Frame Generation",
    short_name="MW3 DLSS Frame Generation",
    description="DLSS 3 Frame Generation inserts AI-generated frames. The counter rises and input latency "
    "rises with it, so it stays off for competitive multiplayer.",
    cst_key="DLSSFrameGeneration:0.0",
    choices=("true", "false"),
    default_value="false",
    recommended_value="false",
    current_impact="true: Interpolated frames add ~10-20 ms input latency in multiplayer",
    recommended_impact="false: Real frames only → minimum input latency for competitive play",
    effect="Disables interpolated frames to keep input latency minimum in multiplayer",
    impact_scores={"latency_ms": -12.0, "stability": "high"},
    category_order=15,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW3_DLSS_PERF_MODE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dlss_perf_mode",
    display_name="MW3 DLSS Performance Mode",
    short_name="MW3 DLSS Performance Mode",
    description="DLSS internal render scale: Quality renders at 67% of native, Balanced at 58%, Performance "
    "at 50%. An upscaler exists to buy frames, so its top tier gives back most of what it was "
    "turned on for.",
    cst_key="DLSSPerfMode:0.0",
    choices=("Ultra Performance", "Maximum Performance", "Balanced", "Maximum Quality"),
    default_value="Maximum Quality",
    recommended_value="Balanced",
    current_impact="Maximum Quality: 67% internal render — the tier that buys the fewest frames",
    recommended_impact="Balanced: 58% internal render — frames back, distant targets still sharp",
    effect="Moves DLSS to the tier that buys frames without softening a target",
    impact_scores={"fps_gpu_bound": "+35-50%", "stability": "high"},
    category_order=16,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

#: Which anti-aliasing path each vendor's own hardware accelerates. The value is
#: whatever the game's own list spells, and every one of these four appears in
#: ``AATechniquePreferred``'s choices — this picks between them, it invents none.
_MW3_AA_BY_VENDOR = {"nvidia": "DLSS", "amd": "FSR AA", "intel": "XeSS"}


def create_mw3_aa_technique_setting(gpu_vendor: str) -> SettingExecutor:
    """Build MW3's anti-aliasing choice for the detected card.

    This shipped as a single static entry recommending ``DLSS`` on every machine,
    which is wrong on two thirds of them: an AMD or Intel card cannot run DLSS, so
    the recommendation left those owners on ``Filmic SMAA T2x`` — no upscale at
    all — while MW4's sibling had already been derived per vendor. That is the
    measurable ceiling C10 is about, and it was ~25-35% of a frame rate.

    Args:
        gpu_vendor: Lowercase vendor from detection: ``nvidia``, ``amd``, ``intel``.

    Returns:
        The setting, recommending the path this card has hardware for.
    """
    preferred = _MW3_AA_BY_VENDOR[gpu_vendor]
    return _make_mw3_cst_setting(
        setting_id="game_config:mw3:aa_technique",
        display_name="MW3 Anti-Aliasing Preset",
        short_name="MW3 Anti-Aliasing Preset",
        description="Which anti-aliasing path the game uses. Each vendor's upscaler doubles as "
        "its best anti-aliasing, so the right answer is a property of the card rather than a "
        "preference — and the wrong one leaves dedicated hardware idle on a software path.",
        cst_key="AATechniquePreferred:0.3",
        choices=("Filmic SMAA T2x", "DLSS", "XeSS", "FSR AA"),
        default_value="Filmic SMAA T2x",
        recommended_value=preferred,
        current_impact="Filmic SMAA T2x: software AA, no upscale, and blurry in motion",
        recommended_impact=f"{preferred}: the upscale path this card has hardware for",
        effect=f"Selects the anti-aliasing this {gpu_vendor} card is built for",
        impact_scores={"fps_gpu_bound": "+25-35%", "stability": "high"},
        category_order=17,
        evidence_level="proven",
        sources=_MW3_SOURCES,
    )


MW3_DEPTH_OF_FIELD = _make_mw3_cst_setting(
    setting_id="game_config:mw3:depth_of_field",
    display_name="MW3 Depth of Field",
    short_name="MW3 Depth of Field",
    description="Camera lens blur on out-of-focus regions, strongest while aiming down sights. It blurs "
    "distant enemies, so it stays off for competitive play.",
    cst_key="DepthOfField:0.0",
    choices=("true", "false"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Distant enemies blurred when ADS → harder to spot targets",
    recommended_impact="false: Sharp focus everywhere → better enemy visibility",
    effect="Disables ADS depth-of-field blur for clearer target acquisition",
    impact_scores={"fps_gpu_bound": "+1-2%"},
    category_order=18,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

# NOTE: 'EnableVelocityBasedBlur:0.0' was investigated as the cst key for the
# in-game UI's 'World Motion Blur' toggle, but observation showed the cst
# value remains "true" even when the UI shows OFF — meaning that key controls
# something else (likely campaign/killcam radial blur), not the MP toggle.
# UI's World Motion Blur appears to be persisted in settingspresets.cdb
# (binary). Until a verified mapping is found, no setting is exposed here.

MW3_SHADOW_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:shadow_quality",
    display_name="MW3 Shadow Quality",
    short_name="MW3 Shadow Quality",
    description="World shadow detail level. Low keeps shadows visible, so you still read enemy "
    "silhouettes, at lower GPU cost.",
    cst_key="ShadowQuality:0.0",
    choices=("Very_Low", "Low", "Medium", "High", "Very_High"),
    default_value="High",
    recommended_value="Low",
    current_impact="High/Very_High: Shadow maps cost GPU time with no visibility benefit",
    recommended_impact="Low: Enemy shadows still cast, 3.6% measured FPS gain",
    effect="Low shadow quality keeps enemy silhouettes visible but cuts GPU shadow load",
    # Measured 3.6% at Low in a per-option benchmark (RTX 4080 Super + i7-14700KF).
    # The previous "+3-8%" invented the top of that range, the prose claimed
    # "~10-20% FPS gain" — five times the measurement — and the description called
    # this one of the biggest levers, which it is not: shader_quality measures 11%
    # and SSR 5-10%. Users read the tooltip, so an overclaim there is the one that
    # actually misleads.
    impact_scores={"fps_gpu_bound": "+3-4%"},
    category_order=20,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_SCREEN_SPACE_SHADOWS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:screen_space_shadows",
    display_name="MW3 Screen Space Shadows",
    short_name="MW3 Screen Space Shadows",
    description="Self-shadowing on characters and weapons. What matters is that a body is shadowed at all, "
    "which separates it from the environment; how sharply that shadow resolves is not something a "
    "player reads.",
    cst_key="ScreenSpaceShadowQuality:0.0",
    choices=("Off", "Low", "High"),
    default_value="High",
    recommended_value="Low",
    current_impact="High: Self-shadows resolved past the tier at which a silhouette separates",
    recommended_impact="Low: Bodies still shadowed and still separate — sharpness is what goes",
    effect="Holds self-shadowing at the tier that keeps a silhouette readable",
    # Was High, on "keep ON even when other shadow settings are Low" — which is
    # an argument for Off being wrong, not for High being right. `Low` is the
    # lowest tier at which the channel exists, and that is where an information
    # channel belongs (product consequence 5).
    #
    # MW4's sibling disagrees with this description outright: it says the shadow
    # that gives a position away comes from the shadow maps and calls contact
    # shadowing decoration. Same key family, same engine family, opposite
    # readings, and nobody has measured which is right — both sit at `Low`,
    # which is correct either way. See tasks.md D4.
    impact_scores={"fps_gpu_bound": "0 to -2%", "stability": "high"},
    category_order=21,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_VOLUMETRIC_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:volumetric_quality",
    display_name="MW3 Volumetric Quality",
    short_name="MW3 Volumetric Quality",
    description="God rays, volumetric fog and atmospheric scattering. A very expensive GPU effect with no "
    "competitive benefit, so Low.",
    cst_key="VolumetricQuality:0.0",
    choices=("QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH"),
    default_value="QUALITY_HIGH",
    recommended_value="QUALITY_LOW",
    current_impact="QUALITY_HIGH: Expensive volumetric raymarching → ~5-15% GPU time",
    recommended_impact="QUALITY_LOW: Minimal volumetric pass → big FPS gain",
    effect="Lowers volumetric fog cost — no visibility benefit lost",
    impact_scores={"fps_gpu_bound": "+5-12%", "fps_1_percent_low": "+3-8%"},
    category_order=22,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_PARTICLE_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:particle_quality",
    display_name="MW3 Particle Resolution",
    short_name="MW3 Particle Resolution",
    description="Resolution and density of smoke, fire, explosion and impact particles, the in-game Particle "
    "Resolution option. Low keeps effects readable while cutting their CPU and GPU cost.",
    cst_key="ParticleQuality:0.0",
    choices=("very low", "low", "medium", "high"),
    default_value="medium",
    recommended_value="low",
    current_impact="High/medium: Heavy particle simulation in firefights → frame drops in chaos",
    recommended_impact="Low: 1.3% measured FPS gain; Very low reaches 4% if you accept flatter effects",
    effect="Reduces particle simulation load for stable frametimes during firefights",
    # Measured 1.3% at Low and 4% at Very Low in the same per-option benchmark. The
    # previous "+2-5%" 1%-low figure was never measured at all — the benchmark
    # reported average FPS — so it is dropped rather than restated, and the range
    # now matches the recommended value instead of the best case.
    impact_scores={"fps_gpu_bound": "+1-2%"},
    category_order=23,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_SSAO = _make_mw3_cst_setting(
    setting_id="game_config:mw3:ssao",
    display_name="MW3 Ambient Occlusion (SSAO)",
    short_name="MW3 Ambient Occlusion (SSAO)",
    description="Screen-space ambient occlusion adds soft contact shadows. Off recommended — "
    "darkens corners (where enemies hide), no competitive benefit, costs GPU.",
    cst_key="SSAOTechnique:0.0",
    choices=("Off", "GTAO", "MDAO", "GTAO & MDAO"),
    default_value="GTAO",
    recommended_value="Off",
    current_impact="GTAO/MDAO: Darkens crevices and corners → enemies in shadow harder to spot",
    recommended_impact="Off: Brighter scene → enemies more visible in dark areas, ~3-5% FPS gain",
    effect="Disables SSAO for brighter scene + better enemy visibility in shadows",
    impact_scores={"fps_gpu_bound": "+3-6%"},
    category_order=24,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_SSR = _make_mw3_cst_setting(
    setting_id="game_config:mw3:ssr",
    display_name="MW3 Screen Space Reflections",
    short_name="MW3 Screen Space Reflections",
    description="Real-time reflections on metallic and wet surfaces. One of the two heaviest "
    "options in the Quality menu, and reflections are not visible information in a firefight.",
    cst_key="SSRMode:0.0",
    choices=("Off", "Deferred LQ", "Deferred HQ"),
    default_value="Deferred LQ",
    recommended_value="Off",
    current_impact="Deferred LQ: Per-pixel reflection raymarching every frame → up to 10% GPU time",
    recommended_impact="Off: Static cubemap reflections only → 5-10% FPS gain",
    effect="Disables screen-space reflections — one of the two biggest FPS levers in the menu",
    impact_scores={"fps_gpu_bound": "+5-10%"},
    category_order=25,
    evidence_level="likely",
    sources=[
        "https://detonated.com/modern-warfare-3-warzone-best-pc-settings-for-fps-graphics-visibility/",
        *_MW3_SOURCES,
    ],
)

MW3_SHADER_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:shader_quality",
    display_name="MW3 Shader Quality",
    short_name="MW3 Shader Quality",
    description="Material shader complexity. Low simplifies surface shading without touching geometry or "
    "visibility, and shortens shader compilation after a driver update.",
    cst_key="ShaderQuality:0.0",
    choices=("Default", "Medium", "Low"),
    default_value="Default",
    recommended_value="Low",
    current_impact="Default: Heavy material shaders → up to 11% GPU time, longer shader pre-loads",
    recommended_impact="Low: Simpler shaders → faster pre-load + 11% measured FPS gain",
    effect="Lower shader complexity speeds up post-driver-update pre-load and gains FPS",
    # The prose said ~3-5% while the score said +5-11%, so the tooltip and the
    # number under it told the player two different things. The 11% is the one
    # with a measurement behind it — the same per-option benchmark that put
    # shadow_quality at 3.6% (see the note there) — so the prose is corrected up
    # to meet the score rather than the score trimmed down to meet the prose.
    impact_scores={"fps_gpu_bound": "+5-11%", "stability": "high"},
    category_order=26,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_DXR_MODE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dxr_mode",
    display_name="MW3 Ray Tracing (DXR)",
    short_name="MW3 Ray Tracing (DXR)",
    description="DirectX ray tracing for shadows and reflections. It costs 20-40% of the frame rate and gives "
    "no competitive advantage, so it is off for multiplayer.",
    cst_key="DxrMode:0.0",
    choices=("Off", "On"),
    default_value="Off",
    recommended_value="Off",
    current_impact="On: Ray-traced shadows/reflections cost 20-40% FPS, no competitive benefit",
    recommended_impact="Off: Rasterized shadows/reflections → 20-40% higher FPS",
    effect="Disables ray tracing — biggest single FPS lever for max-FPS configs",
    impact_scores={"fps_gpu_bound": "+25-35%"},
    category_order=27,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_AUDIO_MIX = _make_mw3_cst_setting(
    setting_id="game_config:mw3:audio_mix",
    display_name="MW3 Audio Mix",
    short_name="MW3 Audio Mix",
    description="Which frequencies the mix favours. Treble Boost lifts footsteps and weapon foley above music "
    "and explosions, which is the difference between hearing someone and hearing the scene.",
    cst_key="AudioMix:0.0",
    choices=("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"),
    default_value="0",
    recommended_value="5",
    current_impact="0 (Home Theater): Bass-heavy mix → footsteps drowned by explosions",
    recommended_impact="5 (Treble Boost): High-frequency emphasis → footsteps and reloads stand out",
    effect="Treble-emphasized mix for clearer footstep audio cues",
    impact_scores={"footstep_clarity": "improved", "latency_ms": 0},
    category_order=28,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_DETAIL_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:detail_quality",
    display_name="MW3 Detail Quality Level",
    short_name="MW3 Detail Quality Level",
    description="Geometry and model level of detail, the in-game Detail Quality Level option. Low simplifies "
    "clutter such as foliage, rocks and decals without touching enemy character models.",
    cst_key="ModelQuality:0.0",
    choices=("Low Quality", "Medium Quality", "High Quality"),
    default_value="Medium Quality",
    recommended_value="Low Quality",
    current_impact="Medium/High: Detailed clutter and foliage → ~3-7% GPU + slight VRAM",
    recommended_impact="Low: Simpler clutter → ~3-7% FPS, characters unaffected",
    effect="Lowers world clutter detail without touching enemy character meshes",
    impact_scores={"fps_gpu_bound": "+2-4%"},
    category_order=29,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_PERSISTENT_EFFECTS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:persistent_effects",
    display_name="MW3 Persistent Effects",
    short_name="MW3 Persistent Effects",
    description="Bullet impact decals and explosion marks that linger on surfaces, the in-game Persistent "
    "Effects option. They reveal recent enemy fire and past engagements, so they stay on; the "
    "cost is VRAM only.",
    cst_key="PersistentDamageLayer:0.0",
    choices=("true", "false"),
    default_value="true",
    recommended_value="true",
    current_impact="false: No decals → loses visual cue for 'enemy was just here / shooting from there'",
    recommended_impact="true: Decals persist → enemy fire trails reveal positions, no FPS cost",
    effect="Locks persistent decals ON — competitive intel from bullet/explosion marks",
    impact_scores={"fps_gpu_bound": "0%", "stability": "high"},
    category_order=30,
    evidence_level="proven",
    sources=[
        "https://pcoptimizedsettings.com/call-off-duty-modern-warfare-3-season-6-pc-optimized-settings-every-graphics-option-benchmarked/",
        *_MW3_SOURCES,
    ],
)

MW3_STATIC_REFLECTION_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:static_reflection_quality",
    display_name="MW3 Static Reflection Quality",
    short_name="MW3 Static Reflection Quality",
    description="How often cubemap reflection probes are relit, the in-game Static Reflection Quality option, "
    "1 (Low) to 4 (High). Dropping to 1 measured 0-1% fps, so the game default is kept.",
    cst_key="ReflectionProbeRelighting:0.0",
    choices=("1", "2", "3", "4"),
    default_value="4",
    recommended_value="4",
    current_impact="4 (High): Probes relight at full frequency → 0-1% GPU time",
    recommended_impact="4 (High): Reflection accuracy kept — dropping to 1 would gain only 0-1%",
    effect="Keeps full reflection probe relighting — the measured gain does not justify the loss",
    impact_scores={"fps_gpu_bound": "0%", "vram_mb": 0},
    category_order=31,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_DEFERRED_PHYSICS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:deferred_physics",
    display_name="MW3 Deferred Physics Quality",
    short_name="MW3 Deferred Physics Quality",
    description="Environmental physics such as debris and smoke deformation, the in-game Deferred Physics "
    "Quality option. The cost lands on the CPU, so CPU-limited machines gain the most from Low.",
    cst_key="DeferredPhysics:0.0",
    choices=("Low Quality", "Medium Quality", "High Quality", "Developer"),
    default_value="Medium Quality",
    recommended_value="Low Quality",
    current_impact="Medium: CPU-side physics for cosmetic debris and water → frametime spikes when CPU-bound",
    recommended_impact="Low: Minimal physics sim → steadier frametimes on CPU-limited systems",
    effect="Minimises environmental physics — the cost is CPU-side, so it helps 1% lows most",
    impact_scores={"fps_1_percent_low": "+1-3%", "cpu_usage": -1},
    category_order=32,
    evidence_level="likely",
    sources=[
        "https://detonated.com/modern-warfare-3-warzone-best-pc-settings-for-fps-graphics-visibility/",
        *_MW3_SOURCES,
    ],
)

MW3_RENDER_RESOLUTION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:render_resolution",
    display_name="MW3 Render Resolution Multiplier",
    short_name="MW3 Render Resolution Multiplier",
    description="Render scale as a percentage of the display, applied before the upscaler, the in-game Render "
    "Resolution option. Keep 100 with DLSS Quality, which already renders at 67%; 75 only for "
    "native targets.",
    cst_key="ResolutionMultiplier:0.0",
    choices=("25", "50", "67", "75", "100", "125", "150"),
    default_value="100",
    recommended_value="100",
    current_impact="<100 with DLSS: stacks two scales (e.g. 50% × DLSS 67% = 33% internal — visibly blurry)",
    recommended_impact="100 with DLSS Quality: clean 67% internal render, sharp distant targets",
    effect="Lets DLSS handle scaling alone — no double-downscale, sharp image at high FPS",
    impact_scores={"fps_gpu_bound": "0%", "stability": "high"},
    category_order=33,
    evidence_level="proven",
    sources=[
        "https://pcoptimizedsettings.com/call-off-duty-modern-warfare-3-season-6-pc-optimized-settings-every-graphics-option-benchmarked/",
        *_MW3_SOURCES,
    ],
)


def create_mw3_vram_scale_setting(vram_mb: int) -> SettingExecutor:
    """Build the MW3 VRAM target for the detected card.

    The headroom a card needs is not a constant. On an 8 GB card the OS, the
    desktop and any overlay leave little room, and running out is one of the
    documented triggers of the packet-burst warning — the stall gets reported as
    a network problem because the engine cannot tell the two apart. Guides
    converge on ~70% for 8 GB cards, while the same 70% on a 24 GB card would
    hand back 7 GB for nothing.

    This shipped as a hardcoded "0.850000" for every card, which is the defect
    the product rules name directly: a constant waiting for hardware that
    disagrees with it.

    Raises when the card's VRAM is unknown, because there is no honest answer
    then. The fallback that used to exist here passed a fabricated 10 GB, so a
    machine whose GPU could not be read was told "the card detected here has
    10 GB" and given 85% — which on a real 6 GB card is the VRAM saturation this
    setting exists to prevent, and the packet-burst trigger named above.
    """
    if not vram_mb or vram_mb <= 0:
        raise ValueError(
            "vram_scale needs the card's actual VRAM; the caller must read it "
            "rather than register a guess about the user's hardware"
        )

    gb = vram_mb / 1024
    if gb and gb <= 8:
        target, pct = "0.700000", 70
    elif gb and gb <= 12:
        target, pct = "0.850000", 85
    else:
        # Plenty of headroom in absolute terms even at 95%, and a larger share
        # keeps more of the working set resident.
        target, pct = "0.950000", 95

    label = f"{gb:.0f} GB"
    return _make_mw3_cst_setting(
        setting_id="game_config:mw3:vram_scale",
        display_name="MW3 VRAM Scale Target",
        short_name="MW3 VRAM Scale Target",
        description=f"Share of GPU VRAM the game may consume (in-game UI label: 'VRAM Scale "
        f"Target'). The card detected here has {label}, so {pct}% leaves the OS and overlays "
        f"the room they need without stranding memory the game could be using.",
        cst_key="VideoMemoryScale:1.0",
        choices=("0.500000", "0.700000", "0.850000", "0.950000", "1.000000"),
        # Derived, so there is no separate stock value to restore.
        default_value=target,
        recommended_value=target,
        current_impact="Too high for the card: VRAM saturates → texture swapping, stutter, packet-burst warnings",
        recommended_impact=f"{pct}%: Headroom sized to a {label} card → no swapping, nothing stranded",
        effect=f"Sizes the VRAM target to the detected {label} card",
        impact_scores={"fps_1_percent_low": "+2-5%", "vram_mb": 0.0, "stability": "high"},
        category_order=34,
        evidence_level="likely",
        sources=[
            "https://hone.gg/blog/stop-and-fix-packet-burst-in-warzone/",
            *_MW3_SOURCES,
        ],
        value_hints={target: f"{pct}% of {label}"},
    )


# No static fallback. Discovery registers this from the detected card, and a
# machine whose VRAM cannot be read gets no setting rather than a sentence about
# a card it does not have. Same rule as network:<n>:rss_queues.

MW3_WEATHER_GRID = _make_mw3_cst_setting(
    setting_id="game_config:mw3:weather_grid",
    display_name="MW3 Weather Grid Volumes",
    short_name="MW3 Weather Grid Volumes",
    description="Volumetric weather effects (rain, snow, fog density grids). Per-option "
    "benchmarking shows almost no FPS difference, so this is kept off for target visibility "
    "rather than for frame rate.",
    cst_key="WeatherGridVolumesQuality:0.0",
    choices=("Ultra", "High", "Medium", "Low", "Off"),
    default_value="Low",
    recommended_value="Off",
    current_impact="Low: Volumetric rain and fog between you and the target → obscured enemies",
    recommended_impact="Off: Clear line of sight → enemies stay visible through weather, 0-1% FPS",
    effect="Disables weather grid volumes for clearer target visibility",
    impact_scores={"fps_gpu_bound": "+0-1%", "target_visibility": "improved"},
    category_order=35,
    evidence_level="likely",
    sources=[
        "https://pcoptimizedsettings.com/call-off-duty-modern-warfare-3-season-6-pc-optimized-settings-every-graphics-option-benchmarked/",
        *_MW3_SOURCES,
    ],
)

MW3_TESSELLATION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:tessellation",
    display_name="MW3 Tessellation",
    short_name="MW3 Tessellation",
    description="GPU tessellation for terrain and model surface detail. Off is the "
    "competitive-standard setting — visible only on close-up surfaces, costly on GPU.",
    cst_key="Tessellation:0.0",
    choices=("0_Off", "1_Near", "2_All"),
    default_value="0_Off",
    recommended_value="0_Off",
    current_impact="Near/All: GPU subdivides surfaces → 2-5% GPU cost for cosmetic detail",
    recommended_impact="Off: No surface tessellation → ~2-5% FPS, identical at typical distances",
    effect="Locks tessellation off — cosmetic surface detail with measurable GPU cost",
    impact_scores={"fps_gpu_bound": "+0-1%", "vram_mb": -30, "stability": "high"},
    category_order=36,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_MENU_RENDER_RESOLUTION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:menu_render_resolution",
    display_name="MW3 Menu Render Resolution",
    short_name="MW3 Menu Render Resolution",
    description="How far MW3 drops the render resolution in menus and the lobby, the in-game Menu Render "
    "Resolution option. The value is the size of the reduction, so full is the cheapest and off "
    "the most expensive.",
    cst_key="SustainabilityMenuSceneResolution:0.0",
    choices=("off", "min", "full"),
    # The value is the amount of REDUCTION, confirmed against the in-game labels:
    #   off  = Native   = no reduction       (most power)
    #   min  = Optimal  = slight reduction
    #   full = Maximal  = maximum reduction  (least power)
    # fpstune previously recommended "min" and described "full" as rendering at
    # native resolution — it read the label Maximal and wrote the meaning of
    # Native. So it moved every machine from maximum reduction to slight
    # reduction while claiming to cool the GPU, doing the exact opposite.
    # Corroborated independently: the game's own "Low consumption" Eco preset —
    # its most aggressive power-saving option — writes "full".
    default_value="full",
    # Equals default_value on purpose: MW3 ships at maximum reduction, so this
    # setting's only job now is to detect and undo the "min" an earlier fpstune
    # release wrote, or the "off" a guide talked someone into.
    recommended_value="full",
    current_impact="off/min (Native/Optimal): Menus rendered at or near full resolution → GPU works for a static screen",
    recommended_impact="full (Maximal): Menus rendered at the largest reduction → least GPU spent between matches",
    effect="Restores the maximum menu resolution reduction — menus only, no gameplay effect",
    # 0.0, not the old -2: the direction is certain but the magnitude was never
    # measured, and the figure it replaces was attached to the wrong value anyway.
    impact_scores={"gpu_temp_c": 0.0, "stability": "high"},
    value_hints={"off": "Native", "min": "Optimal", "full": "Maximal"},
    category_order=37,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_DISPLAY_MODE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:display_mode",
    display_name="MW3 Display Mode",
    short_name="MW3 Display Mode",
    description="Window mode, the in-game Display Mode option. Borderless keeps MW3 on the flip-model path, "
    "which on Windows 11 costs no measurable latency over exclusive fullscreen and alt-tabs "
    "instantly.",
    cst_key="DisplayMode:0.0",
    choices=(
        "Windowed",
        "Fullscreen",
        "Fullscreen borderless window",
        "Fullscreen borderless extended window",
    ),
    default_value="Fullscreen borderless window",
    recommended_value="Fullscreen borderless window",
    current_impact="Windowed or forced exclusive: Mode switching on alt-tab, or a window that is not full-screen",
    recommended_impact="Borderless: Flip-model presentation → instant alt-tab, VRR intact, no measurable latency cost",
    effect="Keeps MW3 on borderless flip-model presentation for instant alt-tab",
    # recommended_value equals default_value on purpose: this is a drift guard. An
    # earlier fpstune release forced exclusive "Fullscreen" here, so the setting's
    # job now is to detect that and put the machine back.
    #
    # latency_ms is 0.0, not the old -3.5. That figure came from the pre-flip-model
    # era: Windows 10 1709+ upgrades windowed swapchains to flip model
    # (SwapEffectUpgradeEnable), so borderless no longer goes through a DWM copy,
    # and G-Sync works in it as long as NVCP's VRR mode is "on" rather than
    # "fullscreen" — which is what gpu-nvidia:vrr_mode already recommends. The
    # frontend sums latency_ms into the figure shown on Home, and this setting and
    # preferred_display_mode each claimed -3.5, so one physical mode change was
    # advertised twice at a value nobody had measured.
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=38,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    value_hints={
        "Windowed": "Windowed",
        "Fullscreen": "Fullscreen",
        "Fullscreen borderless window": "Borderless",
        "Fullscreen borderless extended window": "Ext. Borderless",
    },
)


MW3_ANISOTROPIC = _make_mw3_cst_setting(
    setting_id="game_config:mw3:anisotropic",
    display_name="MW3 Texture Filter Anisotropic",
    short_name="MW3 Texture Filter Anisotropic",
    description="Anisotropic filtering for textures seen at an angle, the in-game Texture Filter Anisotropic "
    "option. Normal (4x) keeps ground and wall texture sharp at a fraction of High's cost.",
    cst_key="TextureFilterAnisotropic:0.0",
    choices=("Low", "Normal", "High", "Extra"),
    default_value="Normal",
    recommended_value="Normal",
    current_impact="High/Extra: 8x-16x aniso → 2-3% GPU overhead with negligible visual gain over Normal",
    recommended_impact="Normal (4x): Sharp angled textures at minimal GPU cost",
    effect="Keeps anisotropic filtering at 4x — best clarity-to-cost ratio",
    impact_scores={"fps_gpu_bound": "+0-1%", "stability": "high"},
    category_order=40,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_BULLET_IMPACTS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:bullet_impacts",
    display_name="MW3 Bullet Impact Markers",
    short_name="MW3 Bullet Impact Markers",
    description="Bullet impact marks on surfaces (in-game UI label: 'Bullet Impacts'). "
    "Keeping these on reveals where enemies are shooting from, providing tactical information "
    "about shot origin direction.",
    cst_key="BulletImpacts:0.0",
    choices=("true", "false"),
    default_value="true",
    recommended_value="true",
    current_impact="false: No surface bullet marks → lose directional cue for incoming fire",
    recommended_impact="true: Impact marks visible → identify enemy fire direction, no FPS cost",
    effect="Keeps bullet impact markers on for tactical fire-direction information",
    impact_scores={"fps_gpu_bound": "0%", "stability": "high"},
    category_order=41,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

# Named-compound (C8): PauseRenderingEnabled and SustainabilityPauseRendering are
# two cst keys for one concept — "stop rendering when the window is not focused".
# Either one alone switches the behaviour on, so managing only the first left the
# game still pausing with the setting reported as off. The in-game Eco Mode preset
# writes this pair, which is what makes the drift guard worth having.
MW3_PAUSE_RENDERING = SettingExecutor(
    id="game_config:mw3:pause_rendering",
    category=SettingCategory.GAME_CONFIG,
    display_name="MW3 Pause Game Rendering",
    short_name="MW3 Pause Game Rendering",
    description="Pauses rendering whenever the window loses focus, not only when minimized. On a "
    "multi-monitor setup the still-visible MW3 window then freezes on a stale frame while you "
    "work on another screen.",
    value_type=SettingValueType.CHOICE,
    choices=("false", "true"),
    default_value="false",
    # Was "true", described as having "zero gameplay impact — only affects rendering
    # during alt-tab". That is wrong on the multi-monitor borderless setup this
    # product targets: focus loss is not the same as minimize, so the visible game
    # window freezes on alt-tab. What it bought in exchange was real — GPU heat
    # saved while you are not playing is heat the card is not carrying into the
    # next match — but MaxFpsOutOfFocus buys the same thing without freezing a
    # visible window, so this trades a real cost for a saving already collected.
    #
    # recommended_value now equals default_value, deliberately: the setting's job is
    # to detect and undo the "true" an earlier fpstune release wrote.
    recommended_value="false",
    current_impact="true: Window freezes on a stale frame whenever it loses focus, even while fully visible",
    recommended_impact="false: The game keeps rendering when unfocused → no frozen window on a second monitor",
    effect="Keeps MW3 rendering when unfocused so a visible window never freezes",
    # gpu_temp_c is 0.0 because this setting, at its recommended "false", saves
    # nothing — not because an idle saving would be worthless. MaxFpsOutOfFocus
    # collects that saving already, and collects it without freezing a window
    # that is still on screen. Scoring a saving here too would count it twice.
    impact_scores={"gpu_temp_c": 0.0, "stability": "high"},
    category_order=43,
    evidence_level="likely",
    sources=_MW3_SOURCES,
    requires_reboot=False,
    scope=SettingScope.RECOMMENDED,
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$docPath = [System.Environment]::GetFolderPath('MyDocuments'); "
        "$optPath = Join-Path $docPath 'Call of Duty MWIII\\players\\options.4.cod23.cst'; "
        "if (-not (Test-Path $optPath)) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($optPath, [System.Text.Encoding]::UTF8); "
        "$found = $false; $anyTrue = $false; "
        "foreach ($k in @('PauseRenderingEnabled', 'SustainabilityPauseRendering')) { "
        'if ($c -match "(?m)^\\s*$k`:[0-9.]+\\s*=\\s*`"([^`"]*)`"") { '
        "$found = $true; if ($Matches[1] -eq 'true') { $anyTrue = $true } } }; "
        "if (-not $found) { Write-Output 'not_installed' } "
        "elseif ($anyTrue) { Write-Output 'true' } else { Write-Output 'false' }"
    ),
    # A list of keys, not one: the compound is off only when every key is off.
    detect_args={
        "batch_config": "mw3",
        "batch_key": ["PauseRenderingEnabled", "SustainabilityPauseRendering"],
    },
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_pause_rendering_toggle",
    apply_args={},
    apply_value_map={"false": "false", "true": "true"},
)

# The in-game counterpart to gpu-nvidia:bg_app_fps, and the reason that one stays
# off. Both cap an unfocused game, but MW3 knows its own focus state while the
# NVIDIA driver only guesses it, and it guesses wrong for any title rendering
# under an overlay — MW3 ships with three. So the cap belongs here, where a wrong
# guess is impossible, not in the driver.
MW3_FPS_CAP_OUT_OF_FOCUS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:fps_cap_out_of_focus",
    display_name="MW3 Unfocused Frame Rate Limit",
    short_name="MW3 Unfocused Frame Rate Limit",
    description="Frame cap while the game window is not focused. It reclaims the GPU for whatever you "
    "alt-tabbed to without freezing the game window, which pausing rendering outright would do.",
    cst_key="MaxFpsOutOfFocus:0.0",
    choices=(),
    value_type=SettingValueType.INT,
    # MW3's stock value for this key is not documented, and reading it off a machine
    # that has run any optimizer proves nothing. So default equals recommended and
    # reset is a no-op by design: this is a drift guard, not a stock restore.
    default_value=30,
    recommended_value=30,
    min_value=5,
    max_value=300,
    current_impact="Uncapped: The unfocused game keeps rendering at full rate, taking GPU from the foreground app",
    recommended_impact="30: Game stays visible and current on a second monitor at a fraction of the GPU cost",
    effect="Caps the unfocused game at 30 FPS instead of freezing it",
    # A ceiling, not a measured gain — the GPU saved depends entirely on what the
    # uncapped rate would have been. Stating the cap is the only honest figure
    # here. Thermal rather than fps: alt-tabbed for twenty minutes between
    # matches, an uncapped game holds the card at full load the whole time, and
    # the match that follows starts from that temperature.
    impact_scores={"fps_unfocused_ceiling": 30, "stability": "high"},
    category_order=44,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_DLSS_SHARPNESS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dlss_sharpness",
    display_name="MW3 DLSS Sharpness",
    short_name="MW3 DLSS Sharpness",
    description="Post-process sharpening applied on top of DLSS output. "
    "0.25 adds subtle sharpening that improves distant enemy silhouette clarity without introducing haloing artifacts.",
    cst_key="DLSSSharpness:0.0",
    choices=("0.000000", "0.250000", "0.500000", "0.750000", "1.000000"),
    default_value="0.000000",
    recommended_value="0.250000",
    current_impact="0.0: No sharpening → DLSS output is softened at distance",
    recommended_impact="0.25: Subtle sharpening → crisper distant targets without haloing artifacts",
    effect="Adds subtle DLSS sharpening for better distant enemy silhouette clarity",
    impact_scores={"fps_gpu_bound": "0%", "stability": "high"},
    category_order=44,
    evidence_level="likely",
    sources=_MW3_SOURCES,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW3_PATH_TRACING = _make_mw3_cst_setting(
    setting_id="game_config:mw3:path_tracing",
    display_name="MW3 Path Tracing",
    short_name="MW3 Path Tracing",
    description="Full hardware path tracing, active only in Gunsmith, the Firing Range and the lobby, never "
    "in a match. It costs GPU power there and changes nothing in-match.",
    cst_key="PathTracing:0.0",
    choices=("true", "false"),
    default_value="false",
    recommended_value="false",
    current_impact="true: Path tracing active in Gunsmith/lobby → high GPU load and heat outside of matches",
    recommended_impact="false: No path tracing → lower GPU load in lobby, cooler GPU when match starts",
    effect="Disables Path Tracing — reduces GPU heat and power draw in lobby and Gunsmith",
    impact_scores={"gpu_temp_c": -8, "stability": "high"},
    category_order=45,
    # The claim is "keep this off", and that is proven rather than
    # experimental: the feature is a large, well-measured GPU cost and this
    # is a performance-first tool. `risk_level` follows the recommendation,
    # and applying "keep it off" costs nothing — the warning stays because it
    # describes what turning it ON would cost.
    evidence_level="proven",
    risk_level="low",
    sources=_MW3_SOURCES,
    risk_warning="CST key name may differ across game builds. If the setting fails to apply, disable Path Tracing manually in-game.",
)

MW3_DLSS_RAY_RECONSTRUCTION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dlss_ray_reconstruction",
    display_name="MW3 DLSS Ray Reconstruction",
    short_name="MW3 DLSS Ray Reconstruction",
    description="DLSS 3.5 AI denoiser for ray-traced frames — experimental key, active only in Gunsmith, Firing Range, and lobby alongside Path Tracing. "
    "Has no effect during matches or without ray tracing active.",
    cst_key="DlssRR:0.0",
    choices=("true", "false"),
    default_value="false",
    recommended_value="false",
    current_impact="true: AI denoiser active in lobby/Gunsmith → additional GPU overhead outside of matches",
    recommended_impact="false: No denoiser overhead → lower GPU load in non-match areas",
    effect="Disables DLSS Ray Reconstruction — no gameplay impact, reduces lobby GPU overhead",
    impact_scores={"gpu_temp_c": -1, "fps_gpu_bound": "+0-1%", "stability": "high"},
    category_order=46,
    # The claim is "keep this off", and that is proven rather than
    # experimental: the feature is a large, well-measured GPU cost and this
    # is a performance-first tool. `risk_level` follows the recommendation,
    # and applying "keep it off" costs nothing — the warning stays because it
    # describes what turning it ON would cost.
    evidence_level="proven",
    risk_level="low",
    sources=_MW3_SOURCES,
    risk_warning="CST key name is unconfirmed across all build versions. If it fails to apply, disable DLSS Ray Reconstruction manually in Graphics > Advanced.",
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW3_TEXTURE_RESOLUTION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:texture_resolution",
    display_name="MW3 Texture Resolution",
    short_name="MW3 Texture Resolution",
    description="Texture detail level for world surfaces and objects. "
    "VRAM-bound, not compute-bound — lowering from High to Normal saves 1-2 GB VRAM and eliminates saturation stutters on 8 GB cards.",
    cst_key="TextureResolution:0.0",
    choices=("Minimal", "Low", "Normal", "High", "Extra", "Auto"),
    default_value="Normal",
    recommended_value="Normal",
    current_impact="High/Extra: 1-3 GB extra VRAM usage → saturation stutters on 8 GB cards",
    recommended_impact="Normal: ~4-6 GB VRAM → stable frametimes with good surface detail",
    effect="Sets texture resolution to Normal — best VRAM/quality balance for 8 GB cards",
    impact_scores={"fps_1_percent_low": "+2-6%", "vram_mb": -1536},
    category_order=47,
    evidence_level="proven",
    sources=[
        "https://pcoptimizedsettings.com/call-off-duty-modern-warfare-3-season-6-pc-optimized-settings-every-graphics-option-benchmarked/",
        *_MW3_SOURCES,
    ],
)

MW3_WATER_QUALITY = _make_mw3_cst_setting(
    setting_id="game_config:mw3:water_quality",
    display_name="MW3 Water Quality",
    short_name="MW3 Water Quality",
    description="Simulation detail for water surfaces, including reflections, displacement and caustics. "
    "Per-option benchmarking measured no gain from lowering it, so the game default is kept.",
    cst_key="WaterQuality:0.0",
    choices=("Low", "Medium", "High", "Very High"),
    default_value="High",
    recommended_value="High",
    current_impact="High: Full water displacement and reflections → no measurable GPU cost",
    recommended_impact="High: Water detail kept at zero FPS cost — lowering it gains nothing",
    effect="Keeps water detail — benchmarking found no frame rate to gain from lowering it",
    impact_scores={"fps_gpu_bound": "0%"},
    category_order=48,
    evidence_level="likely",
    sources=[
        "https://pcoptimizedsettings.com/call-off-duty-modern-warfare-3-season-6-pc-optimized-settings-every-graphics-option-benchmarked/",
        *_MW3_SOURCES,
    ],
)

MW3_WEAPON_MOTION_BLUR = _make_mw3_cst_setting(
    setting_id="game_config:mw3:weapon_motion_blur",
    display_name="MW3 Weapon Motion Blur",
    short_name="MW3 Weapon Motion Blur",
    description="Motion blur applied to the held weapon model during fast movement and camera rotation. "
    "Off keeps weapon irons and sights sharp at all times — critical for quick target acquisition while moving.",
    cst_key="WeaponMotionBlur:0.0",
    choices=("true", "false"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Weapon blurs during strafe and sprint → obscured irons mid-movement",
    recommended_impact="false: Sharp weapon irons at all times → cleaner sight picture while moving",
    effect="Disables weapon motion blur — sharp sights and irons during movement",
    impact_scores={"fps_gpu_bound": "+0-1%", "ux": "improved"},
    category_order=51,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)


MW3_FSR_FRAME_INTERPOLATION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:fsr_frame_interpolation",
    display_name="MW3 FSR 3 Frame Interpolation",
    short_name="MW3 FSR 3 Frame Interpolation",
    description="AMD FidelityFX Super Resolution 3 frame interpolation (FSR-FI). "
    "Like DLSS Frame Generation, this adds interpolated frames and input latency — OFF mandatory for competitive multiplayer.",
    cst_key="FSRFrameInterpolation:0.0",
    choices=("true", "false"),
    default_value="false",
    recommended_value="false",
    current_impact="true: Interpolated frames add ~10-20 ms input latency in multiplayer",
    recommended_impact="false: Real frames only → minimum input latency for competitive play",
    effect="Disables FSR 3 frame interpolation — keeps input latency minimum in multiplayer",
    impact_scores={"latency_ms": -12.0},
    category_order=55,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_DLSS_MODE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dlss_mode",
    display_name="MW3 DLSS Mode",
    short_name="MW3 DLSS Mode",
    description="Which DLSS sub-mode runs when DLSS is the upscaler. DLSS upscales and anti-aliases for the "
    "fps gain; DLAA anti-aliases at full resolution with no gain; DLSS-D adds Ray Reconstruction.",
    cst_key="DLSSMode:0.0",
    choices=("DLSS", "DLAA", "DLSS-D"),
    default_value="DLSS",
    recommended_value="DLSS",
    current_impact="DLAA/DLSS-D: No upscaling or RT denoiser → lower FPS or RT overhead for no competitive gain",
    recommended_impact="DLSS: Standard upscaling + AA → maximum FPS with clean image",
    effect="Locks DLSS to standard upscaling mode for best FPS",
    impact_scores={"fps_gpu_bound": "+25-55%", "stability": "high"},
    category_order=56,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW3_SUN_SHADOW_CASCADE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:sun_shadow_cascade",
    display_name="MW3 Sun Shadow Cascades",
    short_name="MW3 Sun Shadow Cascades",
    description="How far out sun shadows are still drawn, in distance bands. Dropping to one band keeps "
    "shadows near you and stops drawing the shadow of someone standing where you cannot yet see "
    "them.",
    cst_key="SunShadowCascade:0.0",
    choices=("Low    (1 cascade)", "Medium (1-2 cascades)", "High   (2-3 cascades)"),
    default_value="High   (2-3 cascades)",
    recommended_value="Low    (1 cascade)",
    current_impact="High (2-3 cascades): Shadows drawn at distance → ~5-8% GPU time on shadow maps",
    recommended_impact="Low (1 cascade): ~5-8% FPS, and distant shadows stop being drawn",
    effect="Draws sun shadows only near the player, which is where the GPU cost is worth paying",
    impact_scores={"fps_gpu_bound": "+3-8%"},
    category_order=57,
    perceptible_cost=("Sun shadows render in a single cascade — distant shadows lose definition."),
    evidence_level="proven",
    # COMPLETE rather than RECOMMENDED, and this is consequence 5 applied to a
    # shooter. In an isometric MOBA a shadow reveals nothing the camera does not
    # already show; here a shadow cast around a corner or over a ridge is often
    # the only warning available, and this setting's own copy admitted the cost
    # while recommending it anyway ("minor distance shadow loss"). Whether those
    # frames are worth that warning is the player's call, so it is offered.
    scope=SettingScope.COMPLETE,
    risk_level="moderate",
    risk_warning=(
        "Cascades are distance bands. At Low, sun shadows stop being drawn beyond the nearest "
        "band, so an enemy far enough away casts no shadow you can spot them by. Worth taking "
        "for the frames on a machine that needs them, not worth taking by default."
    ),
    sources=_MW3_SOURCES,
)

MW3_WATER_WAVE_WETNESS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:water_wave_wetness",
    display_name="MW3 Water Wave Wetness",
    short_name="MW3 Water Wave Wetness",
    description="Persistent surface wetness on static geometry near water bodies. "
    "Off removes wet-surface shader pass from terrain near water with no competitive impact.",
    cst_key="WaterWaveWetness:0.0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="true: Wet-surface shader applied to geometry near water → minor GPU overhead",
    recommended_impact="false: No wetness pass → marginal GPU saving near water-heavy maps",
    effect="Disables water wave wetness — removes wet surface shader with no gameplay impact",
    impact_scores={"fps_gpu_bound": "+0-1%", "stability": "high"},
    category_order=58,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_VELOCITY_BLUR = _make_mw3_cst_setting(
    setting_id="game_config:mw3:velocity_blur",
    display_name="MW3 Velocity-Based Blur",
    short_name="MW3 Velocity-Based Blur",
    description="Applies a velocity-based motion blur pass to moving objects in the scene. "
    "Disabling removes blur from fast-moving targets and improves clarity during gunfights.",
    cst_key="EnableVelocityBasedBlur:0.0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Motion blur applied to moving objects → reduced target clarity",
    recommended_impact="false: No velocity blur → sharper enemy tracking during movement",
    effect="Disables velocity-based motion blur — cleaner visuals on fast-moving targets",
    impact_scores={"fps_gpu_bound": "+0-1%", "target_clarity": "high"},
    category_order=59,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_VSYNC = _make_mw3_cst_setting(
    setting_id="game_config:mw3:vsync",
    display_name="MW3 VSync (In-Game)",
    short_name="MW3 VSync (In-Game)",
    description="Vertical sync inside the game engine, separate from the driver's. MW3's own sync loop is not "
    "VRR-aware: it queues frames and charges a frame of input lag even while G-Sync is pacing the "
    "display.",
    cst_key="VSync:0.1",
    choices=("disabled", "100%", "50%", "33%", "25%"),
    default_value="disabled",
    recommended_value="disabled",
    current_impact="50%/100%: The engine's own sync queue → 1-frame latency penalty on every input",
    # NOT "use G-Sync instead". That phrasing is the myth that VRR replaces
    # V-Sync, and it is what talked fpstune into recommending driver V-Sync off
    # as well — where the answer is the opposite (see gpu-nvidia:vsync). The two
    # are different mechanisms: the engine's sync always costs a frame, while the
    # driver's is dormant inside the VRR window and only catches the overshoot.
    recommended_impact="disabled: Sync left to the driver and G-Sync, which do it without the per-frame penalty",
    effect="Disables the engine's own VSync so sync is handled by the driver instead",
    impact_scores={"latency_ms": -6},
    category_order=60,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_VSYNC_MENU = _make_mw3_cst_setting(
    setting_id="game_config:mw3:vsync_menu",
    display_name="MW3 VSync (Menu)",
    short_name="MW3 VSync (Menu)",
    description="Vertical sync applied in menus and lobby screens (in-game UI label: 'VSync (Menu)'). "
    "100% caps the menu frame rate to the monitor refresh rate, preventing unnecessary GPU load while not in a match.",
    cst_key="VSyncInMenu:1.1",
    choices=("disabled", "100%", "50%", "33%", "25%"),
    default_value="100%",
    recommended_value="100%",
    current_impact="disabled: GPU runs uncapped in menus → wasted power, excess heat, louder fans",
    recommended_impact="100%: Menu frames capped to refresh rate → lower GPU load and temperature in lobby",
    effect="Caps menu frame rate to refresh rate — reduces GPU heat and fan noise in lobby",
    impact_scores={"gpu_temp_c": -3, "stability": "high"},
    category_order=61,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_CLOUD_SAVEGAME = _make_mw3_cst_setting(
    setting_id="game_config:mw3:cloud_savegame",
    display_name="MW3 Cloud Config Savegame",
    short_name="MW3 Cloud Config Savegame",
    description="Syncs the config files to the Activision cloud on launch. When on, the cloud copy is "
    "downloaded at startup and overwrites local changes, so tuned settings revert after every "
    "restart.",
    cst_key="ConfigCloudSavegameEnabled:0.0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Cloud settings overwrite local config on every game launch → optimised values reset",
    recommended_impact="false: Local config is authoritative — settings applied by this tool persist across restarts",
    effect="Disables cloud config savegame sync so local settings are not overwritten on launch",
    # Stops the cloud copy overwriting local tweaks. That is a config-integrity
    # benefit with no latency component at all — the -12.0 was the sweep's clipping
    # cap, and the frontend adds latency_ms into the total shown on Home.
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=62,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_CLOUD_STORAGE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:cloud_storage",
    display_name="MW3 Cloud Config Storage",
    short_name="MW3 Cloud Config Storage",
    description="Uploads and downloads config data to Activision cloud storage. "
    "Disabling prevents the game from pulling cloud-stored settings that overwrite local optimisations.",
    cst_key="ConfigCloudStorageEnabled:1.0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="false",
    current_impact="true: Config uploaded/downloaded from cloud → remote copy can overwrite local tweaks",
    recommended_impact="false: Cloud storage inactive — local config file is the single source of truth",
    effect="Disables cloud storage for config so remote values cannot overwrite local settings",
    # Same as the savegame sibling: config integrity, not latency.
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=63,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_DLSS_RR_PERF_MODE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:dlss_rr_perf_mode",
    display_name="MW3 DLSS Ray Reconstruction Mode",
    short_name="MW3 DLSS Ray Reconstruction Mode",
    description="Internal render scale used by DLSS Ray Reconstruction denoiser when active. "
    "Maximum Quality gives the best denoising result; only relevant when DLSS RR is enabled.",
    cst_key="DLSSRRPerfMode:1.0",
    choices=(
        "Ultra Performance",
        "Maximum Performance",
        "Balanced",
        "Maximum Quality",
        "Native Resolution",
    ),
    default_value="Maximum Performance",
    recommended_value="Maximum Performance",
    current_impact="Maximum Quality: Denoising bought for a path fpstune recommends leaving off",
    recommended_impact="Maximum Performance: The game's own tier, spent on nothing that is running",
    effect="Holds ray-reconstruction denoising at the game's own tier",
    # Was raised to Maximum Quality for "the cleanest RT image". Ray tracing is
    # recommended off and `dlss_ray_reconstruction` is recommended false, so this
    # was frames spent sharpening something fpstune has already turned off — and
    # raising above the game's default is the exception, not the default.
    impact_scores={"fps_gpu_bound": "+1-4%", "stability": "high"},
    category_order=52,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    applicable_conditions={"gpu_vendor": "nvidia"},
)

MW3_WATER_CAUSTICS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:water_caustics",
    display_name="MW3 Water Caustics",
    short_name="MW3 Water Caustics",
    description="Light caustic patterns projected on surfaces near water bodies. "
    "Purely cosmetic GPU effect with no competitive benefit — Off recommended.",
    cst_key="WaterCausticsMode:0.0",
    choices=("Off", "Low Quality", "High Quality"),
    default_value="Off",
    recommended_value="Off",
    current_impact="Low/High Quality: Caustic light projection on surfaces → ~1-2% GPU overhead",
    recommended_impact="Off: No caustic pass → ~1-2% FPS, no gameplay impact",
    effect="Disables water caustic projections — purely cosmetic, no gameplay value",
    impact_scores={"fps_gpu_bound": "+0-1%"},
    category_order=53,
    evidence_level="proven",
    sources=_MW3_SOURCES,
)

MW3_REFLECTION_PROBE_HALF_RES = _make_mw3_cst_setting(
    setting_id="game_config:mw3:reflection_probe_half_res",
    display_name="MW3 Half Resolution Reflection Probes",
    short_name="MW3 Half Resolution Reflection Probes",
    description="Renders reflection probe cubemaps at half resolution. "
    "Reduces VRAM usage for reflection data with negligible visual difference in multiplayer.",
    cst_key="ReflectionProbeHalfResolution:0.0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Full-resolution reflection probes → higher VRAM usage, no visible benefit in MP",
    recommended_impact="true: Half-res probes → lower VRAM + marginal FPS, no visible difference at typical distances",
    effect="Halves reflection probe resolution — free VRAM saving with no visible MP impact",
    impact_scores={"fps_gpu_bound": "+0-1%", "vram_mb": -150},
    category_order=54,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)


MW3_SHADER_CACHE_CLEANUP = SettingExecutor(
    id="game_cleanup:mw3:shader_cache_cleanup",
    category=SettingCategory.MAINTENANCE,
    display_name="MW3 Shader Cache Cleanup",
    short_name="MW3 Shader Cache Cleanup",
    description="Deletes MW3's PSO shader cache and its telescope and xpak caches from the install folder. "
    "Fixes launch crashes and black screens after a driver update; shaders recompile on next "
    "launch, 5-15 min.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    current_impact="Current: Stale PSO shaders may cause launch crashes or black screens after driver updates",
    recommended_impact="Clean: Shader cache deleted → shaders recompile fresh on next launch → fixes driver-related crashes",
    scope=SettingScope.COMPLETE,
    category_order=90,
    effect="Clears MW3 PSO shader and content caches to fix post-driver-update crashes",
    impact_scores={"stability": "high", "disk_freed": "0.5-6GB"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "mw3_shader"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_shader_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

MW3_CRASH_CLEANUP = SettingExecutor(
    id="game_cleanup:mw3:crash_cleanup",
    category=SettingCategory.MAINTENANCE,
    display_name="MW3 Crash Dumps Cleanup",
    short_name="MW3 Crash Dumps Cleanup",
    description="Deletes accumulated MW3 crash dump files from the Documents folder. "
    "These serve no purpose after crashes are resolved and can occupy hundreds of MB.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=_MW3_SOURCES,
    current_impact="Current: Crash dump files accumulating disk space",
    recommended_impact="Clean: Crash dumps deleted → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=91,
    effect="Clears MW3 crash dump files from the Documents folder",
    impact_scores={"disk_freed": "0-500MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "mw3_crash"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mw3_crash_cleanup",
    apply_args={},
    apply_value_map={},
)


MW3_PREFERRED_DISPLAY_MODE = _make_mw3_cst_setting(
    setting_id="game_config:mw3:preferred_display_mode",
    display_name="MW3 Preferred Display Mode",
    short_name="MW3 Preferred Display Mode",
    description="The mode MW3 returns to when it re-enters fullscreen, stored apart from the active Display "
    "Mode. If the two disagree the game drifts back to this one, so it must match Display Mode.",
    cst_key="PreferredDisplayMode:0.0",
    choices=("Fullscreen", "Fullscreen borderless window", "Fullscreen borderless extended window"),
    default_value="Fullscreen borderless window",
    recommended_value="Fullscreen borderless window",
    current_impact="Disagrees with Display Mode: Game drifts back to the preferred mode after alt-tab",
    recommended_impact="Borderless: Matches Display Mode → the chosen mode survives alt-tab and restarts",
    effect="Aligns the fullscreen preference with Display Mode so the mode cannot drift",
    # The mode change itself is scored on display_mode; scoring it again here would
    # double-count one physical change in the Home total. See that setting's note.
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    category_order=39,
    evidence_level="likely",
    sources=_MW3_SOURCES,
)

MW3_HW_CHANGE_DETECTION = _make_mw3_cst_setting(
    setting_id="game_config:mw3:hw_change_detection",
    display_name="MW3 Hardware Change Autodetect",
    short_name="MW3 Hardware Change Autodetect",
    description="Re-runs MW3's automatic settings detection on any hardware or driver change, overwriting "
    "every graphics option with its own guesses. Off keeps applied tweaks from reverting after a "
    "driver update.",
    cst_key="DisableHWChangeDetection:0.0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: A driver update re-runs autodetect → every applied tweak is overwritten",
    recommended_impact="true: Autodetect disabled → applied settings survive driver and hardware changes",
    effect="Stops MW3 from overwriting applied settings after a driver or hardware change",
    impact_scores={"fps_retained": "100%", "stability": "high"},
    category_order=40,
    evidence_level="likely",
    sources=_MW3_SOURCES,
    value_hints={"false": "Autodetect on", "true": "Autodetect off"},
)

MW3_VRS = _make_mw3_cst_setting(
    setting_id="game_config:mw3:vrs",
    display_name="MW3 Variable Rate Shading",
    short_name="MW3 Variable Rate Shading",
    description="Shades screen regions the driver judges less noticeable at a reduced rate. "
    "Reported gains range from roughly 10% down to negligible depending on the GPU, and some "
    "systems see instability.",
    cst_key="VRS:0.0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="true",
    current_impact="false: Every pixel shaded at full rate → highest GPU shading cost",
    recommended_impact="true: Peripheral regions shaded at reduced rate → 0-10% FPS, GPU-dependent",
    effect="Enables variable rate shading — largest gains when GPU-limited",
    impact_scores={"fps_gpu_bound": "+0-10%"},
    category_order=44,
    perceptible_cost=(
        "Peripheral screen regions shade at a reduced rate — the edges of the view soften slightly."
    ),
    # COMPLETE, by consequence 5. VRS spends shading rate exactly where a flanker
    # appears — the periphery — and its own warning already says so ("blocky or
    # shimmering shading in peripheral areas and on fast-moving textures"). It was
    # recommending that trade by default for a gain the same copy calls anywhere
    # from 10% to negligible depending on the GPU. A cost the player can see, for
    # a benefit that may be zero, is the player's call to make.
    scope=SettingScope.COMPLETE,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Reported to cause instability on some machines, and it can introduce blocky or "
    "shimmering shading in peripheral areas and on fast-moving textures. Disable this first if "
    "the game starts crashing, and verify the gain with the in-game benchmark — it is negligible "
    "on some GPUs.",
    sources=[
        "https://www.dexerto.com/call-of-duty/modern-warfare-3-best-settings-on-pc-for-fps-graphics-visibility-more-2336306/",
        "https://warzoneloadout.games/modern-warfare-iii/the-best-graphics-settings-for-mwiii-for-high-fps-modern-warfare-3-settings/",
    ],
    value_hints={"false": "Off", "true": "On"},
)


# =============================================================================
# MW3 hardware-derived display settings (registered dynamically)
# =============================================================================
# These three cannot be static: their correct value is a property of the
# attached monitor, not of the game. Writing a literal is exactly how this
# machine ended up capped at 162 FPS and 120 Hz on a 300 Hz panel — both values
# were correct for a 165 Hz monitor that is no longer connected. The registry
# rebuilds them from hardware_manager on every discovery pass, so swapping the
# monitor re-derives the recommendation instead of leaving a stale literal.


def create_mw3_refresh_rate_setting(max_hz: int, monitor_label: str) -> SettingExecutor:
    """Build the MW3 refresh-rate setting for the detected monitor."""
    # MW3 writes this key as a bare 3-decimal number ("300.000"), not "300 Hz".
    # fpstune wrote "300 Hz" for months and detection agreed, because the
    # read-only lock it placed on options.4.cod23.cst meant the game could never
    # write its own value back to disagree with. The moment the lock came off,
    # MW3 rewrote the key as "300.000" on its next exit — same self-confirming
    # trap as HTTPStreamLimitMBytes. The format below is the game's own output,
    # observed after it was free to write.
    target = f"{max_hz:.3f}"
    return _make_mw3_cst_setting(
        setting_id="game_config:mw3:refresh_rate",
        display_name="MW3 Refresh Rate",
        short_name="MW3 Refresh Rate",
        description=f"Refresh rate MW3 drives the display at. The attached monitor "
        f"({monitor_label}) supports {max_hz} Hz, and the game caps its own frame output to "
        f"whatever is set here regardless of what the GPU can render.",
        cst_key="RefreshRate:0.0",
        choices=(),
        value_type=SettingValueType.STRING,
        default_value=target,
        recommended_value=target,
        current_impact=f"Below {max_hz} Hz: Frame output capped under the panel's capability",
        recommended_impact=f"{max_hz} Hz: Game drives the panel at its full rate",
        value_hints={target: f"{max_hz} Hz"},
        effect=f"Sets MW3 to drive the display at its full {max_hz} Hz",
        impact_scores={"fps": f"up to +{max_hz}Hz ceiling", "latency_ms": -2.0},
        category_order=36,
        evidence_level="proven",
        scope=SettingScope.ESSENTIAL,
        sources=_MW3_SOURCES,
    )


def create_mw3_fps_cap_setting(max_hz: int) -> SettingExecutor:
    """Build the MW3 in-game frame cap, derived from the monitor's max refresh."""
    # The same VRR headroom rule the driver cap derives from, taken from the one
    # function rather than written out again, so the two cannot disagree.
    target = frame_cap_for_refresh(max_hz)
    return _make_mw3_cst_setting(
        setting_id="game_config:mw3:fps_cap_ingame",
        display_name="MW3 In-Game Frame Rate Limit",
        short_name="MW3 In-Game Frame Rate Limit",
        description="Maximum frames per second while in a match. Set just below the monitor's "
        "refresh rate so a variable-refresh display never hits its ceiling, which is where "
        "tearing and latency spikes return.",
        cst_key="MaxFpsInGame:0.0",
        choices=(),
        value_type=SettingValueType.INT,
        default_value=target,
        recommended_value=target,
        min_value=30,
        max_value=300,
        current_impact="Below the panel rate: Frames discarded that the GPU already rendered",
        recommended_impact=f"{target}: Full use of the panel with VRR headroom kept",
        effect="Matches the in-game frame cap to the attached monitor",
        impact_scores={"fps": f"ceiling {target}", "latency_ms": -2.0},
        category_order=37,
        evidence_level="proven",
        scope=SettingScope.ESSENTIAL,
        sources=_MW3_SOURCES,
    )


def create_mw3_menu_fps_cap_setting(max_hz: int) -> SettingExecutor:
    """Build the MW3 menu frame cap, derived from the monitor's max refresh."""
    # 90 is enough for a menu to feel responsive, but it is a ceiling and not a
    # constant: on a 60 Hz panel a 90 cap never binds, so the GPU renders 30
    # frames a second the display then throws away. Deriving keeps the cap
    # meaningful on every panel instead of only on high-refresh ones.
    target = min(90, max_hz)
    return _make_mw3_cst_setting(
        setting_id="game_config:mw3:fps_cap_menu",
        display_name="MW3 Menu Frame Rate Limit",
        short_name="MW3 Menu Frame Rate Limit",
        description="Maximum frames per second in menus and the lobby. Menus are static "
        "scenes, so rendering them at the full in-match rate spends GPU power and fan noise "
        "on frames that show nothing new.",
        cst_key="MaxFpsInMenu:1.0",
        choices=(),
        value_type=SettingValueType.INT,
        # Derived, so there is no separate stock value to restore — default equals
        # recommended and the setting acts as a drift guard.
        default_value=target,
        recommended_value=target,
        min_value=30,
        max_value=300,
        current_impact="Uncapped: Static menus render at full rate, so the GPU is already hot when the match loads",
        recommended_impact=f"{target}: Menus stay responsive and the GPU enters the match with thermal headroom",
        effect="Caps the menu frame rate so a static lobby stops driving the GPU",
        # A ceiling, not a measured saving: how much heat this avoids depends on
        # what the uncapped menu rate would have been on that GPU. Filed under
        # thermal rather than fps — it raises nobody's frame rate, it stops the
        # card arriving at the match already near the temperature where it
        # throttles, which is where a decaying frame rate comes from.
        impact_scores={"fps_menu_ceiling": target, "stability": "high"},
        category_order=45,
        evidence_level="likely",
        sources=_MW3_SOURCES,
    )


def create_mw3_resolution_setting(width: int, height: int) -> SettingExecutor:
    """Build the MW3 fullscreen resolution setting from the monitor's native mode."""
    target = f"{width}x{height}"
    return _make_mw3_cst_setting(
        setting_id="game_config:mw3:resolution",
        display_name="MW3 Fullscreen Resolution",
        short_name="MW3 Fullscreen Resolution",
        description=f"Resolution MW3 renders at in fullscreen. The attached panel is native "
        f"{target}; anything else is rescaled by the display, which costs sharpness and adds "
        f"scaler latency.",
        cst_key="Resolution:0.0",
        choices=(),
        value_type=SettingValueType.STRING,
        default_value=target,
        recommended_value=target,
        current_impact="Non-native: Display rescales every frame → softer image, scaler latency",
        recommended_impact=f"{target}: 1:1 pixel mapping → sharpest image, no scaler in the path",
        effect="Matches MW3 to the panel's native resolution",
        impact_scores={"fps": "0%", "latency_ms": -1.0},
        category_order=35,
        evidence_level="proven",
        scope=SettingScope.RECOMMENDED,
        sources=_MW3_SOURCES,
    )


MW3_SETTINGS: list[SettingExecutor] = [
    MW3_PREFERRED_DISPLAY_MODE,
    MW3_HW_CHANGE_DETECTION,
    MW3_VRS,
    MW3_TEXTURE_STREAMING,
    MW3_NAT_FIREWALL,
    MW3_WORLD_STREAMING,
    MW3_LOCAL_TEXTURE_QUALITY,
    MW3_NVIDIA_REFLEX,
    MW3_DLSS_FRAME_GENERATION,
    MW3_DLSS_PERF_MODE,
    MW3_DEPTH_OF_FIELD,
    MW3_SHADOW_QUALITY,
    MW3_SCREEN_SPACE_SHADOWS,
    MW3_VOLUMETRIC_QUALITY,
    MW3_PARTICLE_QUALITY,
    MW3_SSAO,
    MW3_SSR,
    MW3_SHADER_QUALITY,
    MW3_DXR_MODE,
    MW3_AUDIO_MIX,
    MW3_DETAIL_QUALITY,
    MW3_PERSISTENT_EFFECTS,
    MW3_STATIC_REFLECTION_QUALITY,
    MW3_DEFERRED_PHYSICS,
    MW3_RENDER_RESOLUTION,
    # MW3_VRAM_SCALE is absent deliberately: it is registered by discovery from
    # the detected card, because there is no honest value without one.
    MW3_WEATHER_GRID,
    MW3_TESSELLATION,
    MW3_MENU_RENDER_RESOLUTION,
    MW3_DISPLAY_MODE,
    MW3_ANISOTROPIC,
    MW3_BULLET_IMPACTS,
    MW3_PAUSE_RENDERING,
    MW3_FPS_CAP_OUT_OF_FOCUS,
    MW3_DLSS_SHARPNESS,
    MW3_PATH_TRACING,
    MW3_DLSS_RAY_RECONSTRUCTION,
    MW3_TEXTURE_RESOLUTION,
    MW3_WATER_QUALITY,
    MW3_WEAPON_MOTION_BLUR,
    MW3_DLSS_RR_PERF_MODE,
    MW3_WATER_CAUSTICS,
    MW3_REFLECTION_PROBE_HALF_RES,
    MW3_FSR_FRAME_INTERPOLATION,
    MW3_DLSS_MODE,
    MW3_SUN_SHADOW_CASCADE,
    MW3_WATER_WAVE_WETNESS,
    MW3_VELOCITY_BLUR,
    MW3_VSYNC,
    MW3_VSYNC_MENU,
    MW3_CLOUD_SAVEGAME,
    MW3_CLOUD_STORAGE,
    MW3_SHADER_CACHE_CLEANUP,
    MW3_CRASH_CLEANUP,
]

GAME_CONFIG_SETTINGS: list[SettingExecutor] = [*CS2_SETTINGS, *MW3_SETTINGS, *HOTS_SETTINGS]
