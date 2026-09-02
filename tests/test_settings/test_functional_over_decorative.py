"""Consequence 5: cut the decorative, keep the functional.

"Optimizing" a game is not a synonym for turning everything to zero. The line
runs between information and decoration:

  * enough visual quality to tell an opponent apart
  * enough audio quality to hear where a sound came from and what it was
  * everything above that line is spectacle, and spectacle is what gets spent

A preset that flattens spell effects buys frames and loses the fight, and a
config that ships at ``SoundSampleRate=22050`` has already lost footstep
direction — so the rule cuts upward as often as down.

Which side a setting falls on is decided per game. Shadows are decoration in an
isometric MOBA, where the camera never hides an enemy behind a corner, and
information in a first-person shooter, where one cast around that corner is the
only warning available. These tests therefore assert per game, never globally.
"""

from __future__ import annotations

import pathlib

from fpstune.settings.base import SettingScope
from fpstune.settings.definitions.game_configs import CS2_SETTINGS, HOTS_SETTINGS

ROOT = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_SCOPES = (SettingScope.ESSENTIAL, SettingScope.RECOMMENDED)

# Keys whose whole purpose is to tell the player something. Lowering one is a
# loss of information, not a quality trade, so no shipped setting may recommend
# a smaller value for it than the game's own default.
FUNCTIONAL_KEYS = {
    "GraphicsOptionEffectsDetail": "a cast is announced by its particles",
    "GraphicsOptionTextureQuality": "enemy models have to be tellable apart",
    "SoundSampleRate": "footstep direction is information",
    "SoundQuality": "a sound has to be identifiable, not just audible",
    "soundchannels": "dropped channels are dropped events",
}


class TestTheRuleIsWrittenDown:
    """A rule that lives only in a commit message is a rule nobody applies next."""

    def test_claude_md_carries_the_fifth_consequence(self) -> None:
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Six consequences" in text, "the consequence list lost its own count"
        assert "information and decoration" in text

    def test_it_puts_frames_first_and_makes_raising_the_exception(self) -> None:
        """The rule is only useful if it says who carries the burden of proof.

        Stated as "keep the functional" alone it reads as permission to leave a
        quality tier where the game's default put it. The user's instruction,
        2026-08-24, is the other way round and covers every tweak in the product:
        the minimum is the default answer and raising one is the exception.
        """
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Frame rate is priority one" in text
        assert "the minimum is the default answer" in text.lower()

    def test_it_names_the_upward_direction_too(self) -> None:
        # Without this the rule reads as "turn less off", which is not the point.
        # Raising a lowered functional setting is a tweak by the same rule.
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "SoundSampleRate" in text
        assert "Minimum is not zero" in text

    def test_it_ties_the_spend_to_a_measurement(self) -> None:
        """A quality tier is bought with frames, so the budget has to be real.

        Without this the rule can be satisfied by a recommendation that costs
        frames on a machine measured at 19% of its target — which is what the
        shipped MW4 set did.
        """
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "headroom you have measured" in text


class TestNoShippedSettingSpendsInformation:
    def test_no_game_setting_lowers_a_functional_key(self) -> None:
        offenders = []
        for setting in HOTS_SETTINGS:
            key = str(setting.apply_args.get("key", ""))
            if key not in FUNCTIONAL_KEYS:
                continue
            try:
                recommended = float(str(setting.recommended_value))
                default = float(str(setting.default_value))
            except ValueError:
                continue
            if recommended < default:
                offenders.append(
                    f"{setting.id} recommends {setting.recommended_value} "
                    f"over {setting.default_value} — {FUNCTIONAL_KEYS[key]}"
                )
        assert not offenders, "\n".join(offenders)

    def test_the_guard_knows_what_it_is_looking_for(self) -> None:
        # Proves the loop above can fire rather than being vacuously true because
        # no setting touches a functional key at all.
        assert FUNCTIONAL_KEYS
        pretend_key, pretend_reason = next(iter(FUNCTIONAL_KEYS.items()))
        assert pretend_key in FUNCTIONAL_KEYS and pretend_reason


class TestHotsSpendsOnlyDecoration:
    """Everything HotS recommends by default must be invisible to the player.

    HotS is played from a fixed isometric camera, so the decorative side is
    unusually wide here — but each entry is listed by name rather than inferred,
    because "it looked decorative" is how spell effects nearly got spent.
    """

    DECORATIVE = {
        "GraphicsOptionMovies": "cinematics play outside the match entirely",
        "GraphicsOptionPortraits": "a 3D portrait tells the player nothing a flat one does not",
        "GraphicsOptionShadowQuality": "a fixed overhead camera hides nothing behind a shadow",
        "GraphicsOptionPostProcessing": "bloom and depth of field only obscure the board",
        "GraphicsOptionSSAO": "contact shading carries no information",
        "GraphicsOptionReflections": "water reflections are scenery",
        "GraphicsOptionPhysicsQuality": "cloth and ragdoll decide nothing",
        "vsync": "the driver already governs presentation; this only adds a wait",
    }

    @staticmethod
    def _lowers_the_value(setting: object) -> bool:
        """True when the recommendation sits numerically below the game's default."""
        try:
            recommended = float(str(setting.recommended_value))  # type: ignore[attr-defined]
            default = float(str(setting.default_value))  # type: ignore[attr-defined]
        except ValueError:
            return False
        return recommended < default

    def test_a_default_recommendation_spends_decoration_or_restores_information(self) -> None:
        # Two legitimate shapes, and only two. A setting in the default scopes may
        # spend something the player cannot perceive, or it may put back something
        # that was taken from them. What it may not do is spend information.
        unjustified = [
            (s.id, s.apply_args.get("key"))
            for s in HOTS_SETTINGS
            if s.scope in (SettingScope.ESSENTIAL, SettingScope.RECOMMENDED)
            and str(s.apply_args.get("key", "")) not in self.DECORATIVE
            and self._lowers_the_value(s)
        ]
        assert not unjustified, (
            f"these lower a value by default without being named decoration: {unjustified}"
        )

    def test_spell_effects_are_restored_rather_than_spent(self) -> None:
        # The concrete near-miss: GraphicsOptionEffectsDetail shipped recommending
        # 0 in RECOMMENDED scope, which trades the readability of an enemy cast
        # for frames — by default, on the player's behalf. It may ship, but only
        # pointing the other way.
        effects = next(
            (s for s in HOTS_SETTINGS if s.apply_args.get("key") == "GraphicsOptionEffectsDetail"),
            None,
        )
        assert effects is not None, "effects detail is not shipped at all; see consequence 5"
        assert not self._lowers_the_value(effects), (
            "effects detail recommends below the game's default, which spends the "
            "readability of an enemy cast"
        )
        assert "fps" not in effects.impact_scores, (
            "a setting that costs frames to buy information must not be scored as "
            "though it gave frames"
        )

    def test_the_decorative_list_is_not_a_rubber_stamp(self) -> None:
        # It must describe the settings that exist, not accumulate dead entries
        # that make the check above pass for absent settings.
        shipped = {str(s.apply_args.get("key", "")) for s in HOTS_SETTINGS}
        stale = set(self.DECORATIVE) - shipped
        assert not stale, f"listed as decorative but no longer shipped: {sorted(stale)}"


class TestASettingMayNotAdmitAVisualCostAndApplyItAnyway:
    """The general form, and the one that does not need a per-game judgement.

    When a setting's own ``risk_warning`` says the picture gets worse — blurrier,
    blockier, lower resolution — the product has already conceded the thing
    consequence 5 asks about. Deciding that trade for the player anyway, by
    leaving it in a scope that applies without being chosen, is the failure. It
    may still ship; it has to be offered.

    Red-proven on 2026-08-23: three settings matched before the audit moved them
    — mw3:vrs ("blocky", "shimmering"), mw3:world_streaming_quality ("blurry")
    and mw3:local_texture_quality ("lower-resolution").
    """

    # Words a warning uses when it is describing a worse picture rather than a
    # risk of breakage. Deliberately about the image, not about crashes: a
    # setting that warns it may destabilise a machine is a different rule.
    VISUAL_COST = (
        "blurry",
        "lower-resolution",
        "lower resolution",
        "shimmering",
        "blocky",
        "pop-in",
        "flatter",
        "grainy",
        "washed out",
        "less detail",
        "reduced detail",
    )

    @staticmethod
    def _registry_settings() -> list[object]:
        from fpstune.settings.registry import SettingsRegistry

        # Static definitions only: the dynamic half is built from whatever
        # hardware the runner happens to have, and a guard that reads the host
        # passes or fails by machine rather than by code.
        return list(SettingsRegistry(discover_dynamic=False).get_all())

    def _offenders(self) -> list[str]:
        offenders = []
        for setting in self._registry_settings():
            warning = (getattr(setting, "risk_warning", None) or "").lower()
            named = [w for w in self.VISUAL_COST if w in warning]
            if named and getattr(setting, "scope", None) in DEFAULT_SCOPES:
                offenders.append(f"{getattr(setting, 'id', '?')} warns of {named}")
        return offenders

    def test_no_default_scope_setting_warns_about_the_picture(self) -> None:
        offenders = self._offenders()
        assert not offenders, (
            "these apply without being chosen while their own warning concedes a "
            "visual cost; consequence 5 says offer that trade, do not make it:\n"
            + "\n".join(offenders)
        )

    def test_the_guard_reads_something(self) -> None:
        # Without this the check above passes just as happily on an empty
        # registry or a renamed field, which is how a guard quietly stops
        # guarding.
        settings = self._registry_settings()
        assert settings, "the registry produced no settings; the scan proves nothing"
        assert any(getattr(s, "risk_warning", None) for s in settings), (
            "no setting carries a risk_warning at all; the field has moved or emptied"
        )

    def test_the_word_list_can_actually_match(self) -> None:
        pretend = "may cause blurry textures on the first visit to each area"
        assert [w for w in self.VISUAL_COST if w in pretend] == ["blurry"]


class TestCs2SpendsOnlyDecoration:
    """CS2 is the mirror image of HotS: a first-person shooter, so the line moves.

    A shadow, a decal or a spark carries information here that the same thing
    does not carry under a fixed isometric camera. So every CS2 setting that
    switches a game feature *off* by default has to be named as decoration, with
    the reason, rather than assumed to be safe because it is small.
    """

    DECORATIVE = {
        "r_drawtracers_firstperson": (
            "only your own tracers go; enemy tracers still draw, so this removes "
            "something that covers the crosshair rather than something that informs"
        ),
        "cl_autohelp": "pickup and mode hints are UI, not the map",
        "gameinstructor_enable": "a tutorial overlay tells an experienced player nothing",
        "violence_agibs": "a body fragmenting decides nothing the killfeed has not said",
    }

    @staticmethod
    def _switches_a_feature_off(setting: object) -> bool:
        """True when the setting writes 0 over a cvar the game ships at 1."""
        args = getattr(setting, "apply_args", None) or {}
        return str(args.get("cvar_value", "")) == "0"

    def test_every_default_cs2_setting_that_turns_something_off_is_named(self) -> None:
        unjustified = [
            (s.id, (s.apply_args or {}).get("cvar"))
            for s in CS2_SETTINGS
            if s.scope in DEFAULT_SCOPES
            and self._switches_a_feature_off(s)
            and str((s.apply_args or {}).get("cvar", "")) not in self.DECORATIVE
        ]
        assert not unjustified, (
            f"these turn a CS2 feature off by default without being named decoration: {unjustified}"
        )

    def test_the_two_that_were_moved_stay_offered(self) -> None:
        # The concrete pair this audit found, pinned by name so a later edit
        # cannot quietly put them back into the default scopes. Blood is hit
        # confirmation the product already argues for in MW3, and the particle
        # pass carries impact sparks and molotov fire.
        by_cvar = {(s.apply_args or {}).get("cvar"): s for s in CS2_SETTINGS}
        for cvar in ("violence_hblood", "r_drawparticles"):
            setting = by_cvar.get(cvar)
            assert setting is not None, f"{cvar} is no longer shipped; update this guard"
            assert setting.scope == SettingScope.COMPLETE, (
                f"{setting.id} spends information, so it is offered rather than applied"
            )

    def test_the_decorative_list_is_not_a_rubber_stamp(self) -> None:
        shipped = {str((s.apply_args or {}).get("cvar", "")) for s in CS2_SETTINGS}
        stale = set(self.DECORATIVE) - shipped
        assert not stale, f"listed as decorative but no longer shipped: {sorted(stale)}"

    def test_the_off_detector_can_tell_the_two_apart(self) -> None:
        # cs2:disable_ragdolls writes 1 to *disable*, so "writes 0" is not a
        # synonym for "turns a feature off" and the guard must not be read as one.
        by_cvar = {(s.apply_args or {}).get("cvar"): s for s in CS2_SETTINGS}
        ragdolls = by_cvar.get("cl_disable_ragdolls")
        assert ragdolls is not None
        assert not self._switches_a_feature_off(ragdolls)
        assert self._switches_a_feature_off(by_cvar["cl_autohelp"])
