"""Call of Duty: Modern Warfare III (cod23) gamerprofile settings.

MW3 keeps **two** config files, and until now fpstune opened only the first:

* ``players/options.4.cod23.cst`` — graphics, and the 61 settings that live in
  ``game_configs.py``.
* ``players/<account>/gamerprofile*.cst`` — audio, input, aim and field of
  view. Everything in this module.

Kept apart from ``game_configs.py`` for the same reason MW4 is: a different file
format with a different reader and a different writer. Kept apart from
``game_configs_mw4.py`` because they are different games — the values below were
read from MW3's own files, and where the two disagree (``Sprint Assist Delay``
ships at 400 here and 0 there) it is MW3's number that belongs here.

Three things decide most of what follows.

**Ranges are the file's, not ours.** Every line documents its own range
(``// 0 to 12750``) or its own value list (``// one of hold, toggle``), and the
writer refuses anything the line does not allow. Where a range is declared below
it is one that was read off a line; the keys whose lines were not read carry no
range at all rather than a plausible one (C9).

**Almost all of these are guards, and that is the point.** Aim is muscle memory,
and every setting here is a way for the same hand movement to produce a
different result. A guard's ``recommended_value`` equals its ``default_value``:
it changes nothing on a correct machine and puts back what another "optimizer",
a guide, or an earlier fpstune release moved (product consequence 2).

**Field of view is deliberately absent.** MW3's line states its range and the
machines read held the maximum, so nothing available says what the game's
factory default is — and ``default_value`` is what ``reset`` writes back to a
user. Shipping a guessed one is the invented-constant bug C9 exists for, so the
setting is not registered and the gap is recorded in ``tasks.md`` instead.
"""

from __future__ import annotations

from typing import Literal

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# Every value below was read out of MW3's own gamerprofile files rather than
# taken from a guide: two account profiles on one install, which is also why
# `Sprint Assist Delay` at 400 is treated as the game's stock rather than as
# that machine's drift — both profiles hold it and neither had been tuned.
# There is no third-party benchmark for an input setting, and there is nothing
# a benchmark could measure about one, so the list stays empty rather than
# carrying a link that does not support the claim (C11 rule 4).
_MW3_PROFILE_SOURCES: list[str] = []


def _make_mw3_profile_setting(
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
    evidence_level: str = "proven",
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
    """Build one MW3 gamerprofile setting.

    ``key`` carries its scope index (``ADSSensitivity@0``) because that is what
    the current schema writes. The older schema of the same file writes the
    same key with the digit absent, and the matcher in
    ``game_config_writer.key_prefix`` accepts both — which is why one spelling
    here covers both files.

    A list of keys makes the setting a named-compound (C8): several cvars that
    are one concept between them, so the concept is only applied when every one
    of them is. The six per-zoom sensitivity multipliers are the case.

    Detection and apply both go through the Python reader/writer rather than a
    PowerShell command, so a scan costs no process per setting and the
    shape-preserving rewrite has exactly one implementation.
    """
    batch_args = {"batch_config": "mw3_profile", "batch_key": key}
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
        sources=sources if sources is not None else _MW3_PROFILE_SOURCES,
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
        detect_command="mw3_profile_read",
        detect_args=batch_args,
        apply_type=DetectType.POWERSHELL,
        apply_command="mw3_profile_write",
        apply_args=batch_args,
        apply_value_map={c: c for c in choices},
        value_hints=value_hints or {},
        applicable_conditions=applicable_conditions or {},
    )


# --------------------------------------------------------------------------
# The three real tweaks: a delay, a second delay, and an aim response that
# depends on an animation
# --------------------------------------------------------------------------

MW3_SPRINT_ASSIST_DELAY_KBM = _make_mw3_profile_setting(
    setting_id="game_config:mw3:sprint_assist_delay_kbm",
    display_name="MW3 Sprint Assist Delay",
    short_name="MW3 Sprint Assist Delay",
    description="How long the player must hold a direction before sprint engages automatically. "
    "Any delay is time spent walking while intending to run, at the start of every rotation.",
    key="Sprint Assist Delay KBM@0",
    choices=(),
    value_type=SettingValueType.INT,
    # 400 is MW3's own stock, not this machine's drift: two independent account
    # profiles on one install both hold it and neither had been tuned. MW4 ships
    # the same key at 0, which is the value this recommends.
    default_value=400,
    recommended_value=0,
    min_value=0,
    max_value=12750,
    current_impact="400: The game waits before sprint engages, every time a rotation starts",
    recommended_impact="0: Sprint engages the moment the direction is held",
    effect="Removes the wait before sprint engages",
    impact_scores={"input_precision": "improved", "latency_ms": 0.0},
    category_order=200,
)

MW3_SPRINT_ASSIST_DELAY_GAMEPAD = _make_mw3_profile_setting(
    setting_id="game_config:mw3:sprint_assist_delay_gamepad",
    display_name="MW3 Sprint Assist Delay (Gamepad)",
    short_name="MW3 Sprint Assist Delay (Gamepad)",
    description="How long the player must hold a direction before sprint engages automatically on "
    "a gamepad. Any delay is time spent walking while intending to run, at every rotation.",
    key="Sprint Assist Delay Gamepad@0",
    choices=(),
    value_type=SettingValueType.INT,
    default_value=400,
    recommended_value=0,
    min_value=0,
    max_value=12750,
    current_impact="400: The game waits before sprint engages, every time a rotation starts",
    recommended_impact="0: Sprint engages the moment the direction is held",
    effect="Removes the wait before sprint engages on a gamepad",
    impact_scores={"input_precision": "improved", "latency_ms": 0.0},
    category_order=201,
)

MW3_ADS_TIMING_SENSITIVITY = _make_mw3_profile_setting(
    setting_id="game_config:mw3:ads_timing_sensitivity",
    display_name="MW3 ADS Timing Sensitivity",
    short_name="MW3 ADS Timing Sensitivity",
    description="How closely aim tracks the mouse during the aim-down-sights transition. Delayed "
    "and interpolated both make an identical movement land differently depending on how far "
    "into the animation it lands.",
    key="ADSTimingSensitivity@0",
    choices=(),
    value_type=SettingValueType.INT,
    default_value=1,
    recommended_value=0,
    min_value=0,
    max_value=2,
    current_impact="1: Aim response is stretched across the ADS animation",
    recommended_impact="0: Aim tracks the mouse from the first frame of the transition",
    effect="Makes aim response immediate through the ADS transition",
    # Same defect class as mouse acceleration and smoothing, which this file
    # already guards against: the on-screen result of a given mouse movement
    # depends on something other than the movement itself. Here the something
    # is how far into the ADS animation the movement arrives, which the player
    # cannot see and cannot practise against.
    #
    # The enum is measured, not assumed (tasks.md, "Measured facts"). MW3 stores
    # 0..2 while MW4 spells the same setting `immediately, interpolated,
    # delayed`, and the Touch sibling agrees across both games — MW3
    # `ADSTimingSensitivityTouch@0 = 1` against MW4's `= interpolated`.
    impact_scores={"input_precision": "improved", "latency_ms": 0.0},
    category_order=202,
    value_hints={
        "0": "immediately — aim tracks the mouse from the first frame",
        "1": "interpolated — the response is stretched across the animation",
        "2": "delayed — the response waits on the animation",
    },
)


# --------------------------------------------------------------------------
# The guards: recommended equals default, and the job is to notice drift
#
# None of these changes anything on a machine that is already correct. What
# they do is detect a value another "optimizer", a guide or an earlier fpstune
# release moved, and put it back (product consequence 2).
# --------------------------------------------------------------------------

MW3_ADS_SENSITIVITY = _make_mw3_profile_setting(
    setting_id="game_config:mw3:ads_sensitivity",
    display_name="MW3 ADS Sensitivity Multiplier",
    short_name="MW3 ADS Sensitivity Multiplier",
    description="Multiplier on how fast the view turns while scoped — not on how fast the weapon "
    "comes up. Anything but 1.00 changes the turn rate mid-flick as ADS engages, which is what "
    "breaks a quick-scope arc.",
    key="ADSSensitivity@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    # The range the line itself documents: `// 0.100000 to 4.000000`.
    min_value=0.1,
    max_value=4.0,
    current_impact="1.000000: The scoped turn rate matches the hipfire one — the correct state",
    recommended_impact="1.000000: Puts a moved multiplier back, so a flick lands where it was aimed",
    effect="Keeps the scoped turn rate matched to the hipfire one",
    # A guard, and one that will fire: the profiles read held 0.850000, which
    # detection surfaces as drift rather than as a second correct answer
    # (tasks.md decision 1, owner-confirmed). At 1.0 the multiplier layer adds
    # nothing and the player feels exactly what the game's own monitor-distance
    # scaling produces; any other value is a per-player offset stacked on that
    # scaling, and it has to be re-learned at every zoom level.
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=203,
)

MW3_ADS_ZOOM_SENSITIVITY = _make_mw3_profile_setting(
    setting_id="game_config:mw3:ads_zoom_sensitivity",
    display_name="MW3 Per-Zoom ADS Sensitivity",
    short_name="MW3 Per-Zoom ADS Sensitivity",
    description="Sensitivity multiplier for each individual optic zoom level. All six share one "
    "value and one meaning — a per-zoom offset the player has to re-learn — so they move "
    "together or not at all.",
    # Named-compound (C8): six differently-named cvars at one scope index, one
    # concept. They must carry the same guard value together, or a drifted zoom
    # level hides behind five correct ones — the failure MW3 already had once,
    # reading `PauseRenderingEnabled` while a sibling kept pausing rendering.
    key=[
        "ADS2xZoomSensitivity@0",
        "ADS4xZoomSensitivity@0",
        "ADS6xZoomSensitivity@0",
        "ADS8xZoomSensitivity@0",
        "ADSHighZoomSensitivity@0",
        "ADSLowZoomSensitivity@0",
    ],
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    current_impact="1.000000: Every zoom level neutral — the correct state",
    recommended_impact="1.000000: Puts any zoom level that has drifted back beside the other five",
    effect="Keeps every per-zoom ADS sensitivity neutral",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=204,
)

MW3_ADS_HOLD_BREATH_SENSITIVITY = _make_mw3_profile_setting(
    setting_id="game_config:mw3:ads_hold_breath_sensitivity",
    display_name="MW3 Hold-Breath ADS Sensitivity",
    short_name="MW3 Hold-Breath ADS Sensitivity",
    description="Sensitivity multiplier while holding breath to steady aim. At 1.00 holding "
    "breath changes nothing about how the mouse translates to aim, only the sway it removes.",
    key="ADSHoldBreathSensitivity@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    current_impact="1.000000: Aim response unchanged while holding breath — the correct state",
    recommended_impact="1.000000: Puts back an offset that would appear only while steadying aim",
    effect="Keeps hold-breath sensitivity neutral",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=205,
)

MW3_TACTICAL_ADS_SENSITIVITY = _make_mw3_profile_setting(
    setting_id="game_config:mw3:tactical_ads_sensitivity",
    display_name="MW3 Tactical Stance ADS Sensitivity",
    short_name="MW3 Tactical Stance ADS Sensitivity",
    description="Sensitivity multiplier while aiming from the tactical stance. At 1.00 the stance "
    "changes nothing about how the mouse translates to aim.",
    key="TacticalAdsMouseSensitivityMultiplier@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    current_impact="1.000000: Aim response unchanged in tactical stance — the correct state",
    recommended_impact="1.000000: Puts back an offset that would appear only in tactical stance",
    effect="Keeps tactical stance ADS sensitivity neutral",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=206,
)

MW3_MOUSE_MONITOR_DISTANCE_COEFF = _make_mw3_profile_setting(
    setting_id="game_config:mw3:mouse_monitor_distance_coeff",
    display_name="MW3 Mouse Monitor-Distance Coefficient",
    short_name="MW3 Mouse Monitor-Distance Coefficient",
    description="The game's own scaling factor between mouse movement and aim, tuned for its "
    "monitor-distance model. Owner decision: this stays where the game sets it and fpstune never "
    "moves it.",
    key="MouseMonitorDistanceCoeff@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.333333",
    recommended_value="1.333333",
    min_value=0.0,
    max_value=5.0,
    current_impact="1.333333: The game's own scaling factor — the correct state",
    recommended_impact="1.333333: Puts back the one number every other sensitivity scales against",
    effect="Leaves the monitor-distance coefficient untouched",
    # Drift guard only (tasks.md decision 2, owner-confirmed 2026-09-09): every
    # other sensitivity setting in this file is a multiplier layered on top of
    # this coefficient, so moving it would silently rescale all of them at once.
    # fpstune never changes this value, in either direction.
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=207,
)

MW3_MOUSE_VERTICAL_SENSIBILITY = _make_mw3_profile_setting(
    setting_id="game_config:mw3:mouse_vertical_sensibility",
    display_name="MW3 Mouse Vertical Sensitivity Ratio",
    short_name="MW3 Mouse Vertical Sensitivity Ratio",
    description="Vertical aim sensitivity as a ratio of horizontal. At 1.00 the vertical axis "
    "matches the horizontal, so a diagonal flick lands where the hand aimed.",
    key="MouseVerticalSensibility@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="1.000000",
    recommended_value="1.000000",
    current_impact="1.000000: Vertical matches horizontal — the correct state",
    recommended_impact="1.000000: Puts back a ratio that would land a diagonal flick off-axis",
    effect="Keeps vertical sensitivity matched to horizontal",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=208,
)

MW3_MOUSE_ACCELERATION = _make_mw3_profile_setting(
    setting_id="game_config:mw3:mouse_acceleration",
    display_name="MW3 Mouse Acceleration",
    short_name="MW3 Mouse Acceleration",
    description="Scales aim by how fast the mouse moves, so the same distance turns differently "
    "at different speeds. It is why a flick that worked once does not work again, and practice "
    "never makes it consistent.",
    key="MouseAcceleration@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=10.0,
    current_impact="0.000000: Aim is one-to-one with hand movement — the correct state",
    recommended_impact="0.000000: Puts back the property muscle memory is built on",
    effect="Keeps aim one-to-one with hand movement",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=209,
)

MW3_MOUSE_FILTER = _make_mw3_profile_setting(
    setting_id="game_config:mw3:mouse_filter",
    display_name="MW3 Mouse Filtering",
    short_name="MW3 Mouse Filtering",
    description="Averages mouse input over several samples. Averaging means the aim lags the "
    "hand, and the lag grows with the filter strength.",
    key="MouseFilter@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="0.000000",
    recommended_value="0.000000",
    min_value=0.0,
    max_value=10.0,
    current_impact="0.000000: Every sample used as reported — the correct state",
    recommended_impact="0.000000: Puts back unfiltered input, so the aim does not lag the hand",
    effect="Keeps mouse input unfiltered",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=210,
)

MW3_MOUSE_SMOOTHING = _make_mw3_profile_setting(
    setting_id="game_config:mw3:mouse_smoothing",
    display_name="MW3 Mouse Smoothing",
    short_name="MW3 Mouse Smoothing",
    description="Interpolates between mouse samples to make movement look smoother. What it "
    "smooths out is the small fast correction at the end of a flick, which is the part that "
    "lands the shot.",
    key="MouseSmoothing@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: Corrections register as made — the correct state",
    recommended_impact="false: Puts back the fine correction at the end of a movement",
    effect="Keeps small aim corrections from being smoothed away",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=211,
)

MW3_ADS_FOV_SCALING = _make_mw3_profile_setting(
    setting_id="game_config:mw3:ads_fov_scaling",
    display_name="MW3 ADS Field of View Scaling",
    short_name="MW3 ADS Field of View Scaling",
    description="Keeps the field of view at the player's setting while aiming down sights. Off, "
    "aiming narrows the view and moves every target, so the next one has to be found again.",
    key="ADSFovScaling@0",
    choices=("false", "true"),
    default_value="true",
    recommended_value="true",
    current_impact="true: The view is the same scoped as it is hipfired — the correct state",
    recommended_impact="true: Puts back the view that keeps a second target where it already was",
    # Two things this guard protects, and the second is the one usually missed.
    # Off narrows the view to a fixed default and hides whatever was at the
    # edges, exactly when the player can least turn. It also *moves* everything
    # still on screen, so re-acquiring a second target means finding it again —
    # which is the quick-scope case, and the reason this sits beside the
    # sensitivity guards rather than with the graphics settings.
    effect="Keeps the field of view while aiming down sights",
    impact_scores={"target_visibility": "preserved", "fps": "0%"},
    category_order=212,
    evidence_level="likely",
)

MW3_GAMEPAD_AIM = _make_mw3_profile_setting(
    setting_id="game_config:mw3:gamepad_aim",
    display_name="MW3 Gamepad Aiming",
    short_name="MW3 Gamepad Aiming",
    description="Restricts aiming to a gamepad stick rather than the mouse. On a mouse-and-"
    "keyboard machine it makes the mouse stop aiming entirely, which reads as the game being "
    "broken.",
    key="EnableGamepad@0",
    choices=("false", "true"),
    default_value="false",
    recommended_value="false",
    current_impact="false: The mouse aims — the correct state on this input setup",
    recommended_impact="false: Puts aiming back on the mouse if something handed it to a stick",
    effect="Keeps aiming on the mouse",
    impact_scores={"input_precision": "preserved", "latency_ms": 0.0},
    category_order=213,
)

MW3_FOV = _make_mw3_profile_setting(
    setting_id="game_config:mw3:fov",
    display_name="MW3 Field of View",
    short_name="MW3 Field of View",
    description="How much of the world is visible at once, from 60 to 120 degrees. Wider shows more beside "
    "the player, at the cost of a smaller apparent target and a small render cost.",
    key="Fov@0",
    choices=(),
    value_type=SettingValueType.FLOAT,
    default_value="90.000000",
    recommended_value="120.000000",
    min_value=60.0,
    max_value=120.0,
    current_impact="90.000000: The narrower default — movement beside the player can go unseen",
    recommended_impact="120.000000: The file's own maximum — nothing beside the player goes unseen",
    effect="Widens field of view to the file's own maximum",
    # Same owner decision as MW4's sibling (tasks.md decision 3): peripheral
    # information is worth more than apparent target size, offered in COMPLETE
    # rather than assumed, because it changes what the screen shows and costs
    # frames (consequence 5).
    #
    # `default_value` deserves a note, because this setting was held back for
    # it. The line states only its range, and every profile on the reference
    # machine held the maximum, so nothing readable there says what MW3 ships
    # with — and `reset` writes this value, so a guessed one would put the
    # machine in a state the game never had. 90 is here because the product
    # owner stated it on 2026-09-10, which is a source; it is not read from the
    # file and it is not MW4's 90 copied across. If a fresh, untouched profile
    # ever contradicts it, the file wins.
    impact_scores={"target_visibility": "improved", "fps": "0 to -3%"},
    category_order=214,
    perceptible_cost=(
        "A wider view renders more of the world — targets appear smaller at the same distance."
    ),
    scope=SettingScope.COMPLETE,
    evidence_level="likely",
)


MW3_PROFILE_SETTINGS: list[SettingExecutor] = [
    MW3_SPRINT_ASSIST_DELAY_KBM,
    MW3_SPRINT_ASSIST_DELAY_GAMEPAD,
    MW3_ADS_TIMING_SENSITIVITY,
    MW3_ADS_SENSITIVITY,
    MW3_ADS_ZOOM_SENSITIVITY,
    MW3_ADS_HOLD_BREATH_SENSITIVITY,
    MW3_TACTICAL_ADS_SENSITIVITY,
    MW3_MOUSE_MONITOR_DISTANCE_COEFF,
    MW3_MOUSE_VERTICAL_SENSIBILITY,
    MW3_MOUSE_ACCELERATION,
    MW3_MOUSE_FILTER,
    MW3_MOUSE_SMOOTHING,
    MW3_ADS_FOV_SCALING,
    MW3_GAMEPAD_AIM,
    MW3_FOV,
]
