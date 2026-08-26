"""Contract tests for the MW4 (cod26) setting definitions.

These guard the properties that are easy to break by copying a neighbouring
setting: the scope index that makes a key unambiguous, the inverted texture
scale, and the guards whose whole job is that recommended equals default.

Nothing here reads the developer's machine. The one test that compares declared
choices against a real config builds its own config file (C9).
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions.game_configs_mw4 import MW4_SETTINGS
from fpstune.settings.executors.game_config_cache import NOT_INSTALLED
from fpstune.settings.executors.ps_batch import init_scan_cache, reset_scan_cache
from fpstune.settings.registry import SettingsRegistry


@pytest.fixture
def scan_cache():
    _, token = init_scan_cache()
    yield
    reset_scan_cache(token)


def _keys_of(setting) -> list[str]:
    """Every key a setting addresses. A named-compound declares several."""
    key = setting.detect_args["batch_key"]
    return [str(k) for k in key] if isinstance(key, (list, tuple)) else [str(key)]


class TestEveryKeyIsUnambiguous:
    """`Name` alone is not a key — the scope index is part of the identity."""

    @pytest.mark.parametrize("setting", MW4_SETTINGS, ids=lambda s: s.id)
    def test_key_carries_a_scope_index(self, setting) -> None:
        for key in _keys_of(setting):
            name, sep, scope = key.rpartition("@")
            assert sep, f"{setting.id}: key {key!r} has no @<scope> suffix"
            assert scope.isdigit(), f"{setting.id}: {scope!r} is not a scope index"
            assert name, f"{setting.id}: key {key!r} has no name"

    @pytest.mark.parametrize("setting", MW4_SETTINGS, ids=lambda s: s.id)
    def test_key_carries_no_hash_suffix(self, setting) -> None:
        """The `;61129;7764` part is read from the file, never declared.

        Declaring it would pin the setting to one build's hashes, and the file
        is the only place they are correct.
        """
        for key in _keys_of(setting):
            assert ";" not in key

    @pytest.mark.parametrize("setting", MW4_SETTINGS, ids=lambda s: s.id)
    def test_detect_and_apply_address_the_same_key_and_file(self, setting) -> None:
        """A mismatch would verify one key after writing another."""
        assert setting.detect_args["batch_config"] == "mw4"
        assert setting.apply_args["batch_key"] == setting.detect_args["batch_key"]
        assert setting.apply_args["batch_source"] == setting.detect_args["batch_source"]
        assert setting.detect_args["batch_source"] in ("global", "profile", "both")

    def test_ids_are_unique(self) -> None:
        ids = [s.id for s in MW4_SETTINGS]
        assert len(ids) == len(set(ids))

    def test_no_key_is_claimed_by_two_settings(self) -> None:
        """Two settings writing the same key would each undo the other on apply."""
        seen: dict[str, str] = {}
        for setting in MW4_SETTINGS:
            for key in _keys_of(setting):
                assert key not in seen, f"{key} claimed by both {seen.get(key)} and {setting.id}"
                seen[key] = setting.id

    def test_a_named_compound_shares_one_value_list(self) -> None:
        """C8 allows several keys only when they are one concept.

        `SSRQuality@0` and `@1` qualify because they hold the same list.
        `DxrMode@0` (Off/On) and `@1` (Off..Ultra) do not, which is why they ship
        as two settings — writing `Ultra` into the master switch would be a value
        the game rejects.
        """
        compounds = [s for s in MW4_SETTINGS if len(_keys_of(s)) > 1]
        assert compounds, "the SSR compound should be in this set"
        for setting in compounds:
            names = {k.rpartition("@")[0] for k in _keys_of(setting)}
            assert len(names) == 1, f"{setting.id} compounds unrelated keys: {names}"

        dxr = {s.id for s in MW4_SETTINGS if "DxrMode" in str(s.detect_args["batch_key"])}
        assert dxr == {"game_config:mw4:dxr_mode", "game_config:mw4:dxr_quality"}

    @pytest.mark.parametrize("setting", MW4_SETTINGS, ids=lambda s: s.id)
    def test_recommended_and_default_are_offered_choices(self, setting) -> None:
        """C6: detection must never return a value outside `choices`."""
        if not setting.choices:
            return
        assert str(setting.default_value) in setting.choices
        assert str(setting.recommended_value) in setting.choices


class TestTheJudgementsThatAreEasyToInvert:
    def _by_name(self, name: str):
        return next(s for s in MW4_SETTINGS if s.id == f"game_config:mw4:{name}")

    def test_texture_quality_is_read_on_its_inverted_scale(self) -> None:
        """0 is the highest resolution, so a naive "lower is cheaper" edit inverts it.

        Tier 1 rather than 0: the information is surface detail on a player model,
        and 1 still carries it. 0 was recommended on an 8 GB card, where the
        largest texture set is what turns a VRAM budget into a 1%-low problem.
        """
        setting = self._by_name("texture_quality")
        assert setting.recommended_value == "1"
        assert "invert" in setting.description.lower()

    def test_render_resolution_recommends_full_scale(self) -> None:
        """The config shipped at 50 with DLSS also upscaling — two stacked downscales."""
        setting = self._by_name("render_resolution")
        assert setting.recommended_value == "100"

    @pytest.mark.parametrize(
        "name", ["dlss_perf_mode", "amd_fsr_quality", "amd_fsr1_quality", "xess_quality"]
    )
    def test_no_upscaler_is_pinned_to_its_most_expensive_tier(self, name: str) -> None:
        """An upscaler exists to buy frames; its top tier gives that back.

        All four shipped at `Maximum Quality` / `Ultra Quality`, which is the
        setting turned on and then asked not to do its job — up to 30% of the
        frame rate on a machine measured at 19% of its own target. `Balanced` is
        the floor that still resolves a distant player, and the floor is the
        answer (product consequence 5).
        """
        setting = self._by_name(name)
        assert setting.recommended_value == "Balanced"

    def test_anisotropic_is_not_raised_above_the_game_default(self) -> None:
        """Was `aniso 16x` on the claim that it "costs almost nothing", against
        its own declared `-1-2%`. Almost nothing is not nothing, and what it
        sharpens is ground texture — scenery, not a target."""
        setting = self._by_name("anisotropic")
        assert setting.recommended_value == setting.default_value == "aniso 8x"

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            # Each of these is an information channel, and each is set to the
            # lowest tier that still carries the information rather than to the
            # top of its list. A shadow at Low still gives a corner away; a
            # particle at low still tells a grenade from a muzzle flash; a model
            # at Medium is still identifiable at range.
            ("shadow_quality", "Low"),
            ("particle_quality", "low"),
            ("model_quality", "Medium Quality"),
            # Low rather than Off, and deliberately not because this file is sure.
            # MW4 calls contact shadowing decoration; MW3 calls the same key
            # "critical for enemy silhouette visibility". Nobody has measured
            # which is right, and `Low` is the answer under either reading — it
            # is the lowest tier at which the channel still exists.
            ("screen_space_shadows", "Low"),
        ],
    )
    def test_an_information_channel_sits_at_its_own_minimum(self, name: str, expected: str) -> None:
        setting = self._by_name(name)
        assert setting.recommended_value == expected

    # Every recommendation still allowed to cost frames, and what it buys.
    #
    # Frames first means a frame cost is the exception, not that there are none:
    # some channels really are read by the player and really do cost something to
    # keep. What the rule forbids is a cost nobody wrote down. Each entry here is
    # a decision on the record, and a new one cannot appear without landing in
    # this list first.
    FRAME_COST_IS_ARGUED = {
        "render_resolution": "below 100 the 3D scene is downscaled and then upscaled again — "
        "the single largest loss of enemy detail in the file",
        "st_lod_skip": "every level skipped simplifies distant geometry, and distant "
        "geometry in a shooter is usually the person about to shoot",
        "dynamic_scene_resolution": "resolution drops hardest exactly when the scene gets "
        "busy, which is when a target needs resolving",
        "ambient_lighting": "Off flattens shadowed areas, and a flat scene is where a prone "
        "body stops separating from the ground",
        "bullet_impacts": "impacts near cover are how a player works out where fire is "
        "coming from before seeing anyone",
        "persistent_damage": "the marks say where fire has been coming from",
        "show_blood": "hit confirmation — whether the shot landed is information",
        "enable_hud": "the HUD is nothing but information",
        "amd_cas_strength": "sharpening recovers the definition the upscaler took, which is "
        "the same target clarity the upscaler tier is chosen for",
        "screen_space_shadows": "held at its lowest drawn tier rather than off, because MW3 "
        "and MW4 disagree in writing about whether this key carries a silhouette and "
        "nobody has measured which is right — 3% is the price of not guessing",
    }

    def test_every_remaining_frame_cost_is_one_we_argued_for(self) -> None:
        """Frames first: a recommendation that costs frames needs a reason on file.

        Ten shipped without one, four of them in `recommended` scope where the
        user never opted in. The claim is read rather than the value because the
        value alone cannot say which direction is better — a negative `fps` on a
        setting we recommend turning *off* is a gain.
        """
        offenders = []
        for setting in MW4_SETTINGS:
            name = setting.id.rsplit(":", 1)[-1]
            if name in self.FRAME_COST_IS_ARGUED:
                continue
            for metric, raw in (setting.impact_scores or {}).items():
                if not metric.startswith("fps") or not isinstance(raw, str):
                    continue
                if raw.strip().startswith("-") or " -" in raw:
                    offenders.append(f"{setting.id}: {metric}={raw!r}")

        assert not offenders, (
            "a recommendation may not cost frames unless the reason is on file. "
            "Either lower it to the tier that still carries the information, or "
            "add it to FRAME_COST_IS_ARGUED with what it buys:\n" + "\n".join(offenders)
        )

    def test_the_argued_list_does_not_outlive_the_costs_it_excuses(self) -> None:
        """An allowlist is how a rule rots. Once a setting stops costing frames,
        its excuse has to go, or it silently licenses the next cost added there."""
        stale = []
        for name in self.FRAME_COST_IS_ARGUED:
            setting = self._by_name(name)
            costs = any(
                metric.startswith("fps")
                and isinstance(raw, str)
                and (raw.strip().startswith("-") or " -" in raw)
                for metric, raw in (setting.impact_scores or {}).items()
            )
            if not costs:
                stale.append(name)

        assert not stale, f"these no longer cost frames — drop them from the list: {stale}"

    @pytest.mark.parametrize("name", ["recommended_set", "fps_cap_out_of_focus"])
    def test_guards_recommend_their_default(self, name: str) -> None:
        """A guard detects drift; changing its value would make it a tweak."""
        setting = self._by_name(name)
        assert str(setting.recommended_value) == str(setting.default_value)

    def test_recommended_set_guards_every_other_mw4_setting(self) -> None:
        """The file says a 0 here resets the game to its own recommendations."""
        setting = self._by_name("recommended_set")
        assert setting.recommended_value == "true"
        # Not ESSENTIAL despite protecting everything else: it is a guard, so on
        # a correct machine it changes nothing, and ESSENTIAL is what the
        # conservative preset applies. MW3 records the same reasoning.
        assert setting.scope.name == "RECOMMENDED"

    @pytest.mark.parametrize("name", ["render_resolution", "dlss_perf_mode", "texture_quality"])
    def test_settings_that_change_the_image_are_offered_not_assumed(self, name: str) -> None:
        """CLAUDE.md consequence 5: a setting that changes what the screen shows
        belongs in COMPLETE, with its cost written in the copy."""
        setting = self._by_name(name)
        assert setting.scope.name == "COMPLETE"


class TestVendorGating:
    """C10: a vendor-specific control must say so, or it shows up on hardware
    that cannot use it."""

    @pytest.mark.parametrize("name", ["dlss_perf_mode", "dlss_model", "nvidia_reflex"])
    def test_nvidia_only_settings_declare_the_vendor(self, name: str) -> None:
        setting = next(s for s in MW4_SETTINGS if s.id == f"game_config:mw4:{name}")
        assert setting.applicable_conditions.get("gpu_vendor") == "nvidia"

    def test_no_setting_claims_a_vendor_it_does_not_need(self) -> None:
        """Vendor-neutral controls gated to one vendor would hide them from the
        other two for no reason — the mirror of the gap C10 is about."""
        neutral = {
            "render_resolution",
            "texture_quality",
            "anisotropic",
            "volumetric_quality",
            "reflection_probe_half_res",
            "cloud_storage",
            "hw_change_detection",
            "recommended_set",
            "fps_cap_menu",
            "fps_cap_out_of_focus",
        }
        for setting in MW4_SETTINGS:
            if setting.id.split(":")[-1] in neutral:
                assert "gpu_vendor" not in setting.applicable_conditions, setting.id


@pytest.mark.usefixtures("scan_cache")
class TestRangesComeFromTheInstalledBuild:
    """C9: the declared choices are a fallback; the file is the authority."""

    def _install(self, tmp_path, monkeypatch, body: str) -> None:
        players = tmp_path / "Activision" / "Call of Duty" / "players"
        players.mkdir(parents=True)
        (players / "s.1.0.x.cod26.txt").write_bytes(body.encode("utf-8"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def test_a_build_that_adds_a_tier_widens_the_choices(self, tmp_path, monkeypatch) -> None:
        """A patch adding a quality tier should move the UI with it."""
        self._install(
            tmp_path,
            monkeypatch,
            "VolumetricQuality@0;25292;43096 = QUALITY_MEDIUM"
            " // one of QUALITY_LOW, QUALITY_MEDIUM, QUALITY_HIGH, QUALITY_ULTRA\n",
        )
        registry = SettingsRegistry()

        setting = registry.get("game_config:mw4:volumetric_quality")
        assert setting is not None
        assert "QUALITY_ULTRA" in setting.choices
        assert setting.apply_value_map["QUALITY_ULTRA"] == "QUALITY_ULTRA"

    def test_a_list_missing_our_recommendation_is_refused(self, tmp_path, monkeypatch) -> None:
        """Adopting it would leave the setting recommending a value it does not
        offer, which C6 forbids and the UI cannot render."""
        self._install(
            tmp_path,
            monkeypatch,
            "VolumetricQuality@0;25292;43096 = QUALITY_MEDIUM"
            " // one of QUALITY_MEDIUM, QUALITY_HIGH\n",
        )
        registry = SettingsRegistry()

        setting = registry.get("game_config:mw4:volumetric_quality")
        assert setting is not None
        assert setting.choices == ("QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH")

    def test_a_moved_numeric_bound_is_adopted(self, tmp_path, monkeypatch) -> None:
        self._install(tmp_path, monkeypatch, "MaxFpsOutOfFocus@0;35936;15032 = 30 // 5 to 480\n")
        registry = SettingsRegistry()

        setting = registry.get("game_config:mw4:fps_cap_out_of_focus")
        assert setting is not None
        assert (setting.min_value, setting.max_value) == (5, 480)

    def test_a_numeric_range_is_not_pinned_onto_a_choice(self, tmp_path, monkeypatch) -> None:
        """Measured on the installed build 2026-08-25: MW4 writes `// 0 to 200`
        on `ResolutionMultiplier`, which fpstune ships as seven discrete tiers.

        Adopting the range there published `min_value: 0` on a control whose
        lowest option is 50, so anything rendering a slider from the definition
        would have offered a render resolution of zero.
        """
        self._install(
            tmp_path, monkeypatch, "ResolutionMultiplier@0;64786;30730 = 100 // 0 to 200\n"
        )
        registry = SettingsRegistry()

        setting = registry.get("game_config:mw4:render_resolution")
        assert setting is not None
        assert setting.choices == ("50", "67", "75", "100", "125", "150", "200")
        assert (setting.min_value, setting.max_value) == (None, None)

    def test_an_absent_game_leaves_the_declared_ranges_alone(self, tmp_path, monkeypatch) -> None:
        """No install is not an opinion. The fallback stands."""
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        registry = SettingsRegistry()

        setting = registry.get("game_config:mw4:volumetric_quality")
        assert setting is not None
        assert setting.choices == ("QUALITY_LOW", "QUALITY_MEDIUM", "QUALITY_HIGH")


class TestDerivedFromHardware:
    """C9: the frame caps and the VRAM budget have no constant to fall back to.

    Their whole value is that the number suits the panel and the card actually
    attached, so each is built from a reading rather than declared.
    """

    def test_ingame_cap_keeps_vrr_headroom_below_the_panel(self) -> None:
        """Hz - 3 is the same rule the NVIDIA driver path uses; if the two
        disagree the lower one silently wins and the other looks broken."""
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_fps_cap_setting

        for panel_hz, expected in [(60, 57), (144, 141), (240, 237), (360, 357)]:
            setting = create_mw4_fps_cap_setting(panel_hz)
            assert setting.recommended_value == expected, f"{panel_hz} Hz panel"

    def test_ingame_cap_never_drops_below_a_playable_floor(self) -> None:
        """A 30 Hz panel would otherwise derive a 27 fps cap."""
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_fps_cap_setting

        assert create_mw4_fps_cap_setting(30).recommended_value == 30

    def test_menu_cap_never_exceeds_what_the_panel_can_show(self) -> None:
        """A fixed 120 on a 60 Hz panel never binds, so the GPU renders 60 frames
        a second that the display then discards — the waste the cap exists to stop."""
        from fpstune.settings.definitions.game_configs_mw4 import (
            create_mw4_menu_fps_cap_setting,
        )

        assert create_mw4_menu_fps_cap_setting(60).recommended_value == 60
        assert create_mw4_menu_fps_cap_setting(300).recommended_value == 90

    @pytest.mark.parametrize(
        ("vram_mb", "expected"),
        [(6144, "0.700000"), (8192, "0.700000"), (12288, "0.850000"), (24576, "0.950000")],
    )
    def test_vram_budget_scales_with_the_card(self, vram_mb: int, expected: str) -> None:
        """70% of a 24 GB card would strand 7 GB the game could have used."""
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_vram_scale_setting

        assert create_mw4_vram_scale_setting(vram_mb).recommended_value == expected

    def test_vram_budget_refuses_to_guess(self) -> None:
        """MW3's sibling once told a 6 GB card it had 10 and handed it 85%."""
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_vram_scale_setting

        with pytest.raises(ValueError, match="actual VRAM"):
            create_mw4_vram_scale_setting(0)

    def test_the_card_is_named_in_the_copy_from_the_reading(self) -> None:
        """The description states the detected size, so it cannot quietly describe
        a different card than the one the value was derived for."""
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_vram_scale_setting

        assert "24 GB" in create_mw4_vram_scale_setting(24576).description
        assert "8 GB" in create_mw4_vram_scale_setting(8192).description

    def test_none_of_them_ship_as_a_static_setting(self) -> None:
        """A static entry would be a claim about hardware fpstune has not read."""
        static_ids = {s.id for s in MW4_SETTINGS}
        for derived in ("fps_cap_ingame", "fps_cap_menu", "vram_scale"):
            assert f"game_config:mw4:{derived}" not in static_ids


@pytest.mark.usefixtures("scan_cache")
class TestNamedCompoundWrites:
    """C8: several keys, one concept — so all of them move or none does."""

    SAMPLE = (
        "1\n"
        "SSRQuality@0;63075;11445 = Off // one of Off, Low, Medium, High\n"
        "SSRQuality@1;63075;43096 = High // one of Off, Low, Medium, High\n"
    )

    def _install(self, tmp_path, monkeypatch, body: str):
        players = tmp_path / "Activision" / "Call of Duty" / "players"
        players.mkdir(parents=True)
        config = players / "s.1.0.x.cod26.txt"
        config.write_bytes(body.encode("utf-8"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        return config

    def test_a_disagreeing_scope_is_reported_not_hidden(self, tmp_path, monkeypatch) -> None:
        """The guard exists to notice drift. Reading only the first key would let
        a drifted second one hide behind a correct first — MW3's own bug, where
        it read `PauseRenderingEnabled` and kept pausing rendering anyway."""
        from fpstune.settings.executors.game_config_cache import get_mw4_options_agreed

        self._install(tmp_path, monkeypatch, self.SAMPLE)

        assert get_mw4_options_agreed(["SSRQuality@0", "SSRQuality@1"]) == "High"

    def test_writing_moves_every_scope(self, tmp_path, monkeypatch) -> None:
        from fpstune.settings.executors.mw4_config import set_mw4_options

        config = self._install(tmp_path, monkeypatch, self.SAMPLE)

        assert set_mw4_options(["SSRQuality@0", "SSRQuality@1"], "Off") == "Off"

        text = config.read_text(encoding="utf-8")
        assert "SSRQuality@0;63075;11445 = Off" in text
        assert "SSRQuality@1;63075;43096 = Off" in text

    def test_agreement_reports_the_shared_value(self, tmp_path, monkeypatch) -> None:
        from fpstune.settings.executors.game_config_cache import get_mw4_options_agreed

        self._install(tmp_path, monkeypatch, self.SAMPLE.replace("= High", "= Off"))

        assert get_mw4_options_agreed(["SSRQuality@0", "SSRQuality@1"]) == "Off"

    def test_a_value_the_second_key_rejects_leaves_the_first_alone(
        self, tmp_path, monkeypatch
    ) -> None:
        """Validation runs over every key before any is written, so a compound
        cannot end up half-applied by a value only one scope accepts."""
        from fpstune.settings.executors.mw4_config import Mw4ValueRejected, set_mw4_options

        config = self._install(
            tmp_path,
            monkeypatch,
            "1\n"
            "SSRQuality@0;63075;11445 = Off // one of Off, Low, Medium, High\n"
            "SSRQuality@1;63075;43096 = Off // one of Off, Low\n",
        )
        before = config.read_bytes()

        with pytest.raises(Mw4ValueRejected):
            set_mw4_options(["SSRQuality@0", "SSRQuality@1"], "High")

        assert config.read_bytes() == before

    def test_absent_install_reports_not_installed(self, tmp_path, monkeypatch) -> None:
        from fpstune.settings.executors.mw4_config import set_mw4_options

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert set_mw4_options(["SSRQuality@0", "SSRQuality@1"], "Off") == NOT_INSTALLED


class TestAudioSplitsInformationFromDecoration:
    """Consequence 5 in the audio channel: footstep direction is information,
    a soundtrack is not. The split is not loud/quiet."""

    def _by_name(self, name: str):
        return next(s for s in MW4_SETTINGS if s.id == f"game_config:mw4:{name}")

    @pytest.mark.parametrize(
        "name", ["music_volume", "wartracks_volume", "telescope_volume", "cinematic_volume"]
    )
    def test_masking_channels_are_silenced(self, name: str) -> None:
        setting = self._by_name(name)
        assert setting.recommended_value == "0.000000"

    @pytest.mark.parametrize("name", ["effects_volume", "hitmarkers_volume", "voice_volume"])
    def test_channels_that_carry_information_are_guarded_at_full(self, name: str) -> None:
        """Silencing effects would remove footsteps — the thing the rest of this
        phase exists to keep audible."""
        setting = self._by_name(name)
        assert setting.recommended_value == "1.000000"
        assert setting.default_value == setting.recommended_value

    def test_mono_audio_is_guarded_off(self) -> None:
        """Mono removes the left/right difference direction is read from."""
        assert self._by_name("mono_sound").recommended_value == "false"

    def test_silencing_what_the_player_hears_is_offered_not_assumed(self) -> None:
        """CLAUDE.md is explicit that a setting changing what the player can hear
        belongs in COMPLETE with the cost written."""
        for name in ("music_volume", "wartracks_volume", "mute_licensed_music"):
            assert self._by_name(name).scope.name == "COMPLETE", name

    def test_the_one_audio_change_that_gains_information_is_recommended(self) -> None:
        """Muting the tinnitus effect does not trade anything away — the ringing
        it replaces sits on top of footsteps for seconds after every flash."""
        setting = self._by_name("alt_shell_shock")
        assert setting.recommended_value == "true"
        assert setting.scope.name == "RECOMMENDED"

    @pytest.mark.parametrize(
        "name",
        [
            "music_volume",
            "wartracks_volume",
            "telescope_volume",
            "cinematic_volume",
            "effects_volume",
            "hitmarkers_volume",
            "voice_volume",
        ],
    )
    def test_every_volume_writes_both_files(self, name: str) -> None:
        """Measured: changing the music volume in-game wrote 0.000000 to the
        global file and to the profile. A one-file write is half-applied, and
        which copy the game prefers is not something fpstune knows."""
        setting = self._by_name(name)
        assert setting.detect_args["batch_source"] == "both"


class TestInputGuardsProtectMuscleMemory:
    """Aim is muscle memory, and each of these is a way for the same hand
    movement to produce a different result."""

    def _by_name(self, name: str):
        return next(s for s in MW4_SETTINGS if s.id == f"game_config:mw4:{name}")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("mouse_acceleration", "0.000000"),
            ("mouse_filter", "0.000000"),
            ("mouse_smoothing", "false"),
            ("ads_fov_scaling", "true"),
            ("free_look", "true"),
            ("gamepad_aim", "false"),
        ],
    )
    def test_the_guard_holds_the_consistent_value(self, name: str, expected: str) -> None:
        setting = self._by_name(name)
        assert str(setting.recommended_value) == expected
        assert str(setting.default_value) == expected

    def test_sprint_engages_without_a_wait(self) -> None:
        setting = self._by_name("sprint_assist_delay")
        assert setting.recommended_value == 0

    def test_the_key_with_spaces_survives(self) -> None:
        """Sprint Assist Delay KBM@1 cannot be tokenised on whitespace."""
        assert (
            self._by_name("sprint_assist_delay").detect_args["batch_key"]
            == "Sprint Assist Delay KBM@1"
        )

    def test_field_of_view_is_left_as_a_preference(self) -> None:
        """Wider sees more and shrinks targets. Nothing measured here says which
        side a given player should take, so it is guarded rather than moved."""
        setting = self._by_name("fov")
        assert setting.recommended_value == setting.default_value
        assert setting.scope.name == "COMPLETE"

    def test_the_three_that_break_aim_are_guards_not_preset_entries(self) -> None:
        """Acceleration, filtering and smoothing each make a repeated movement
        produce a different result, which practice cannot compensate for — but
        all three already ship off, so promoting them to ESSENTIAL would fill the
        conservative preset with settings that change nothing. They guard instead.
        """
        for name in ("mouse_acceleration", "mouse_filter", "mouse_smoothing"):
            setting = self._by_name(name)
            assert setting.scope.name == "RECOMMENDED", name
            assert str(setting.recommended_value) == str(setting.default_value), name


@pytest.mark.usefixtures("scan_cache")
class TestBothFilesMoveTogether:
    def _install(self, tmp_path, monkeypatch, global_body: str, profile_body: str):
        players = tmp_path / "Activision" / "Call of Duty" / "players"
        acct = players / "424242"
        acct.mkdir(parents=True)
        g = players / "s.1.0.x.cod26.txt"
        p = acct / "g.x.cod26.1.0.l.txt"
        g.write_bytes(global_body.encode("utf-8"))
        p.write_bytes(profile_body.encode("utf-8"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        return g, p

    def test_a_write_lands_in_both_with_each_hash_intact(self, tmp_path, monkeypatch) -> None:
        """The two copies carry different hashes under the same scope index, and
        neither may be rebuilt from the other."""
        from fpstune.settings.executors.mw4_config import set_mw4_option

        g, p = self._install(
            tmp_path,
            monkeypatch,
            "1\nMusicVolume@0;14317;21371 = 1.000000 // 0.000000 to 1.000000\n",
            "1\nMusicVolume@0;54363;21371 = 1.000000 // 0.000000 to 1.000000\n",
        )

        assert set_mw4_option("MusicVolume@0", "0.000000", "both") == "0.000000"

        assert "MusicVolume@0;14317;21371 = 0.000000" in g.read_text(encoding="utf-8")
        assert "MusicVolume@0;54363;21371 = 0.000000" in p.read_text(encoding="utf-8")

    def test_disagreement_between_the_files_is_reported(self, tmp_path, monkeypatch) -> None:
        """A guard asking whether anything has drifted must not let a drifted
        profile copy hide behind a correct global one."""
        from fpstune.settings.executors.game_config_cache import get_mw4_option

        self._install(
            tmp_path,
            monkeypatch,
            "1\nEffectsVolume@0;14317;21371 = 1.000000 // 0.000000 to 1.000000\n",
            "1\nEffectsVolume@0;54363;21371 = 0.200000 // 0.000000 to 1.000000\n",
        )

        assert get_mw4_option("EffectsVolume@0", "both") == "0.200000"

    def test_agreement_reports_the_shared_value(self, tmp_path, monkeypatch) -> None:
        from fpstune.settings.executors.game_config_cache import get_mw4_option

        self._install(
            tmp_path,
            monkeypatch,
            "1\nEffectsVolume@0;14317;21371 = 1.000000 // 0.000000 to 1.000000\n",
            "1\nEffectsVolume@0;54363;21371 = 1.000000 // 0.000000 to 1.000000\n",
        )

        assert get_mw4_option("EffectsVolume@0", "both") == "1.000000"

    def test_a_key_in_only_one_file_still_reads(self, tmp_path, monkeypatch) -> None:
        """Not every both-file key is guaranteed present in both builds."""
        from fpstune.settings.executors.game_config_cache import get_mw4_option

        self._install(
            tmp_path,
            monkeypatch,
            "1\nEffectsVolume@0;14317;21371 = 0.500000 // 0.000000 to 1.000000\n",
            "1\n",
        )

        assert get_mw4_option("EffectsVolume@0", "both") == "0.500000"

    def test_neither_file_present_reports_not_installed(self, tmp_path, monkeypatch) -> None:
        from fpstune.settings.executors.game_config_cache import get_mw4_option

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert get_mw4_option("EffectsVolume@0", "both") == NOT_INSTALLED


class TestDerivedDisplaySettings:
    """The panel decides these, not a constant and not the desktop's current mode."""

    def test_resolution_follows_the_panels_native_mode(self) -> None:
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_resolution_setting

        for width, height in [(1920, 1080), (2560, 1440), (3840, 2160), (3440, 1440)]:
            setting = create_mw4_resolution_setting(width, height)
            assert setting.recommended_value == f"{width}x{height}"

    def test_resolution_refuses_to_guess(self) -> None:
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_resolution_setting

        with pytest.raises(ValueError, match="native mode"):
            create_mw4_resolution_setting(0, 1440)

    def test_refresh_keeps_the_games_own_spelling(self) -> None:
        """MW4 writes `Auto:<hz>` with three decimals. The line carries no value
        list, so nothing can validate a shape fpstune invented — it has to match
        what the game already writes."""
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_refresh_rate_setting

        assert create_mw4_refresh_rate_setting(300).recommended_value == "Auto:300.000"
        assert create_mw4_refresh_rate_setting(60).recommended_value == "Auto:60.000"
        assert create_mw4_refresh_rate_setting(165).recommended_value == "Auto:165.000"

    def test_refresh_refuses_to_guess(self) -> None:
        from fpstune.settings.definitions.game_configs_mw4 import create_mw4_refresh_rate_setting

        with pytest.raises(ValueError, match="maximum"):
            create_mw4_refresh_rate_setting(0)

    def test_neither_ships_as_a_static_setting(self) -> None:
        static_ids = {s.id for s in MW4_SETTINGS}
        for derived in ("resolution", "refresh_rate"):
            assert f"game_config:mw4:{derived}" not in static_ids


class TestHeatIsTreatedAsPerformance:
    """CLAUDE.md consequence 4: none of these buys a frame, and all of them stop
    the machine reaching the match already at its limit."""

    def _by_name(self, name: str):
        return next(s for s in MW4_SETTINGS if s.id == f"game_config:mw4:{name}")

    @pytest.mark.parametrize(
        "name",
        [
            "vsync_menu",
            "menu_scene_resolution",
            "reduce_quality_idle",
            "reduce_quality_idle_delay",
            "cap_fps",
        ],
    )
    def test_thermal_settings_carry_a_ceiling_not_an_fps_claim(self, name: str) -> None:
        """A thermal setting that advertised an fps gain would be claiming
        something it does not do — the category is the claim."""
        setting = self._by_name(name)
        keys = set(setting.impact_scores)
        assert keys & {"fps_menu_ceiling", "fps_unfocused_ceiling"}, keys
        assert "fps" not in keys, f"{name} advertises frames it does not deliver"

    def test_pause_rendering_stays_off(self) -> None:
        """The unfocused cap already covers this at 30 fps, and a full stop has
        to rebuild the frame on the way back."""
        assert self._by_name("pause_rendering").recommended_value == "false"

    def test_battery_saver_is_turned_off_not_tuned(self) -> None:
        """Consequence 3: it is a ceiling that binds mid-match without saying so,
        which makes removing it the tweak."""
        setting = self._by_name("eco_low_battery")
        assert setting.recommended_value == "false"
        assert setting.impact_scores["fps_battery_ceiling"] == "removed"

    @pytest.mark.parametrize("name", ["eco_low_battery", "eco_battery_threshold"])
    def test_battery_settings_only_exist_on_a_machine_with_one(self, name: str) -> None:
        """C10: a desktop has no battery, so these are not decisions there."""
        assert self._by_name(name).applicable_conditions.get("feature") == "mobile"


class TestWhatIsDeliberatelyNotShipped:
    """Two settings have no honest answer, and the absence is the decision."""

    def test_renderer_worker_count_is_not_registered(self) -> None:
        """The game computes it from the CPU it detected and documents no
        formula. Inventing one risks a worker count that stutters rather than
        one that gains — there is no derivation, so there is no setting."""
        ids = {s.id for s in MW4_SETTINGS}
        assert "game_config:mw4:renderer_worker_count" not in ids

    def test_hdr_is_left_to_the_games_own_display_query(self) -> None:
        """Deciding it needs the panel's HDR capability, which is not in the
        monitor data fpstune reads. `Automatic` asks the display; fpstune cannot."""
        setting = next(s for s in MW4_SETTINGS if s.id == "game_config:mw4:hdr")
        assert setting.recommended_value == "Automatic"
        assert setting.recommended_value == setting.default_value

    def test_audio_mix_preset_is_not_registered(self) -> None:
        """The key is empty in the config and carries no value list, so its valid
        values are unknown. Writing a guess is the hardcoded constant C9 forbids."""
        ids = {s.id for s in MW4_SETTINGS}
        assert "game_config:mw4:audio_mix" not in ids


class TestVendorMatrixIsComplete:
    """C10: a vendor-specific concept ships for all three vendors, or the gap is
    recorded with a reason. MW3 ships 7 NVIDIA settings against 1 AMD and 0
    Intel, which is the debt this phase exists not to repeat.
    """

    def _ids(self) -> set[str]:
        return {s.id.split(":")[-1] for s in MW4_SETTINGS}

    @pytest.mark.parametrize(
        ("family", "members"),
        [
            ("upscaler quality", ("dlss_perf_mode", "amd_fsr_quality", "xess_quality")),
            (
                "frame generation",
                ("dlss_frame_generation", "fsr_frame_interpolation", "intel_xefg"),
            ),
            ("low latency", ("nvidia_reflex", "amd_antilag", "intel_xell")),
        ],
    )
    def test_each_family_covers_all_three_vendors(self, family: str, members: tuple) -> None:
        ids = self._ids()
        missing = [m for m in members if m not in ids]
        assert not missing, f"{family} is missing: {missing}"

    def test_low_latency_reads_the_same_on_every_vendor(self) -> None:
        """An AMD owner should get the same recommendation an NVIDIA owner does,
        because the setting does the same thing — a short render queue."""
        by_id = {s.id.split(":")[-1]: s for s in MW4_SETTINGS}
        assert by_id["amd_antilag"].recommended_value == "true"
        assert by_id["intel_xell"].recommended_value == "true"
        assert by_id["nvidia_reflex"].recommended_value == "Enabled + boost"
        for name in ("amd_antilag", "intel_xell", "nvidia_reflex"):
            assert by_id[name].scope.name == "ESSENTIAL", name

    def test_frame_generation_is_off_on_every_vendor(self) -> None:
        """A generated frame cannot show anything the player did, so the counter
        rises while the latency does too — the same trade on all three."""
        by_id = {s.id.split(":")[-1]: s for s in MW4_SETTINGS}
        for name in ("dlss_frame_generation", "fsr_frame_interpolation", "intel_xefg"):
            assert by_id[name].recommended_value == "false", name

    @pytest.mark.parametrize(
        ("name", "vendor"),
        [
            ("amd_antilag", "amd"),
            ("amd_fsr_quality", "amd"),
            ("amd_fsr1_quality", "amd"),
            ("amd_fidelityfx", "amd"),
            ("amd_cas_strength", "amd"),
            ("fsr_frame_interpolation", "amd"),
            ("intel_xell", "intel"),
            ("xess_quality", "intel"),
            ("intel_xefg", "intel"),
            ("intel_xefg_multi", "intel"),
            ("dlss_mode", "nvidia"),
            ("dlss_frame_generation", "nvidia"),
            ("dlss_sharpness", "nvidia"),
            ("nvidia_image_scaling", "nvidia"),
        ],
    )
    def test_each_vendor_setting_is_gated_to_its_hardware(self, name: str, vendor: str) -> None:
        """Ungated, it would show up on hardware that cannot use it and write a
        value that hardware will not take."""
        setting = next(s for s in MW4_SETTINGS if s.id == f"game_config:mw4:{name}")
        assert setting.applicable_conditions.get("gpu_vendor") == vendor

    def test_the_sharpening_gap_is_the_games_not_ours(self) -> None:
        """NVIDIA and AMD each have a sharpening control in this config; Intel
        has none because MW4 does not offer one. The asymmetry is the game's.
        """
        ids = self._ids()
        assert "dlss_sharpness" in ids
        assert "amd_cas_strength" in ids
        assert "intel_xess_sharpness" not in ids


class TestAntiAliasingFollowsTheCard:
    """One setting with three right answers. A single static entry would
    recommend NVIDIA's path on an AMD card, which is C10's whole complaint."""

    @pytest.mark.parametrize(
        ("vendor", "expected"),
        [("nvidia", "DLSS"), ("amd", "FSR AA"), ("intel", "XeSS")],
    )
    def test_each_vendor_gets_its_own_path(self, vendor: str, expected: str) -> None:
        from fpstune.settings.definitions.game_configs_mw4 import (
            create_mw4_aa_technique_setting,
        )

        setting = create_mw4_aa_technique_setting(vendor)
        assert setting.recommended_value == expected
        assert setting.default_value == expected

    def test_an_unknown_vendor_falls_back_to_the_generic_path(self) -> None:
        """SMAA runs anywhere. Recommending a vendor path to a card that has no
        hardware for it would be worse than the generic one."""
        from fpstune.settings.definitions.game_configs_mw4 import (
            create_mw4_aa_technique_setting,
        )

        assert create_mw4_aa_technique_setting("matrox").recommended_value == "SMAA"

    def test_it_names_the_card_in_its_own_copy(self) -> None:
        from fpstune.settings.definitions.game_configs_mw4 import (
            create_mw4_aa_technique_setting,
        )

        assert "amd" in create_mw4_aa_technique_setting("amd").effect.lower()

    def test_it_does_not_ship_as_a_static_setting(self) -> None:
        """A static entry could only carry one vendor's answer."""
        assert "game_config:mw4:aa_technique" not in {s.id for s in MW4_SETTINGS}
