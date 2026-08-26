"""MW3 display settings must be derived from the attached monitor, never hardcoded.

Guards the concrete defect these settings were added for: on a machine whose
165 Hz monitor was replaced by a 300 Hz one, both the driver frame cap and the
in-game cap stayed at 162 and the in-game refresh rate stayed at 120 Hz. Every
one of those was a literal that was correct for hardware no longer attached.
"""

from __future__ import annotations

import re

import pytest

from fpstune.settings.base import SettingScope, SettingValueType
from fpstune.settings.definitions.game_configs import (
    MW3_MENU_RENDER_RESOLUTION,
    MW3_PAUSE_RENDERING,
    create_mw3_fps_cap_setting,
    create_mw3_menu_fps_cap_setting,
    create_mw3_refresh_rate_setting,
    create_mw3_resolution_setting,
    create_mw3_vram_scale_setting,
)
from fpstune.settings.definitions.gpu import create_nvidia_vsync_setting
from fpstune.settings.discovery.display import discover_vrr_dependent_settings
from fpstune.settings.discovery.games_mw3 import discover_mw3_display_settings


class TestRefreshRateDerivation:
    def test_recommends_the_monitor_max(self) -> None:
        setting = create_mw3_refresh_rate_setting(300, "AW2725DF")
        assert setting.recommended_value == "300.000"

    def test_writes_the_bare_decimal_the_game_writes_not_a_hz_string(self) -> None:
        # This assertion used to read `== "165 Hz"`, citing options.4.cod23.cst.
        # The file did say "300 Hz" — because fpstune had written it there and
        # then locked the file read-only, so MW3 could never write its own value
        # back. Unlocked, the game rewrote the key as "300.000" on its next exit.
        # A "165 Hz" string is what would now be silently rejected.
        setting = create_mw3_refresh_rate_setting(165, "VG27AQ")
        assert setting.recommended_value == "165.000"
        assert setting.value_type is SettingValueType.STRING

    def test_the_hz_reading_survives_as_a_display_hint(self) -> None:
        # "300.000" alone is unreadable in a row; the hint restores the unit
        # without putting it back into the value written to disk.
        setting = create_mw3_refresh_rate_setting(300, "AW2725DF")
        assert setting.value_hints["300.000"] == "300 Hz"

    @pytest.mark.parametrize("hz", [60, 120, 144, 165, 240, 300, 360])
    def test_tracks_whatever_monitor_is_attached(self, hz: int) -> None:
        assert create_mw3_refresh_rate_setting(hz, "panel").recommended_value == f"{hz}.000"

    def test_monitor_label_reaches_the_description(self) -> None:
        setting = create_mw3_refresh_rate_setting(300, "AW2725DF")
        assert "AW2725DF" in setting.description

    def test_is_essential_scope(self) -> None:
        # A frame ceiling below the panel's capability outweighs every graphics
        # tweak in the product, so it belongs in the most conservative preset.
        assert create_mw3_refresh_rate_setting(300, "p").scope is SettingScope.ESSENTIAL


class TestFpsCapDerivation:
    def test_leaves_vrr_headroom_below_the_panel_rate(self) -> None:
        assert create_mw3_fps_cap_setting(300).recommended_value == 297

    def test_regression_the_stale_162_case(self) -> None:
        # 162 came from 165 - 3 and was still in place on a 300 Hz panel.
        assert create_mw3_fps_cap_setting(165).recommended_value == 162
        assert create_mw3_fps_cap_setting(300).recommended_value != 162

    def test_matches_the_nvidia_path_formula(self) -> None:
        # NvProfileExecutor.get_vrr_optimization_info_for_monitor uses
        # max(refresh - 3, 30); the two caps must not disagree.
        from fpstune.settings.executors.nvprofile import NvProfileExecutor

        for hz in (60, 144, 165, 300):
            driver_side = NvProfileExecutor().get_vrr_optimization_info_for_monitor(
                refresh_rate=hz, supports_vrr=True
            )["recommended_fps_limit"]
            assert create_mw3_fps_cap_setting(hz).recommended_value == driver_side

    def test_floors_at_30_for_low_refresh_panels(self) -> None:
        # MaxFpsInGame's own range is 30-300; 30 - 3 would fall outside it.
        setting = create_mw3_fps_cap_setting(30)
        assert setting.recommended_value == 30
        assert setting.min_value == 30

    def test_stays_inside_the_cst_range(self) -> None:
        setting = create_mw3_fps_cap_setting(300)
        assert setting.min_value is not None and setting.max_value is not None
        assert setting.min_value <= int(setting.recommended_value) <= setting.max_value

    def test_is_an_int_not_a_choice(self) -> None:
        assert create_mw3_fps_cap_setting(240).value_type is SettingValueType.INT


class TestResolutionDerivation:
    def test_recommends_native_in_cst_format(self) -> None:
        assert create_mw3_resolution_setting(2560, 1440).recommended_value == "2560x1440"

    @pytest.mark.parametrize(
        ("w", "h", "expected"),
        [(1920, 1080, "1920x1080"), (3440, 1440, "3440x1440"), (3840, 2160, "3840x2160")],
    )
    def test_tracks_the_attached_panel(self, w: int, h: int, expected: str) -> None:
        assert create_mw3_resolution_setting(w, h).recommended_value == expected


class TestMenuFpsCapDerivation:
    """The menu cap is a ceiling, so it must never exceed the panel it renders to."""

    def test_uses_ninety_on_a_high_refresh_panel(self) -> None:
        assert create_mw3_menu_fps_cap_setting(300).recommended_value == 90

    @pytest.mark.parametrize(("hz", "expected"), [(60, 60), (75, 75), (90, 90), (144, 90)])
    def test_never_exceeds_the_panel_rate(self, hz: int, expected: int) -> None:
        # A fixed 90 on a 60 Hz panel renders 30 menu frames a second that the
        # display then discards — the hardcoded-constant defect this file exists
        # to guard against, in its cheapest form.
        assert create_mw3_menu_fps_cap_setting(hz).recommended_value == expected

    def test_is_an_int_within_the_keys_own_range(self) -> None:
        # MaxFpsInMenu is documented in the cst file as "30 to 300"; a value
        # outside it is rejected by the game rather than clamped.
        setting = create_mw3_menu_fps_cap_setting(300)
        assert setting.value_type is SettingValueType.INT
        assert setting.min_value == 30
        assert setting.max_value == 300

    def test_stays_below_the_in_match_cap(self) -> None:
        # The whole point is that menus cost less than matches. If these ever
        # converge the setting has stopped doing anything.
        assert create_mw3_menu_fps_cap_setting(300).recommended_value < (
            create_mw3_fps_cap_setting(300).recommended_value
        )


class TestPauseRenderingIsACompound:
    """Both cst keys pause rendering, so managing only one leaves it switched on."""

    def test_detection_reads_both_keys_not_just_the_first(self) -> None:
        keys = MW3_PAUSE_RENDERING.detect_args["batch_key"]
        assert isinstance(keys, list)
        assert set(keys) == {"PauseRenderingEnabled", "SustainabilityPauseRendering"}

    def test_apply_uses_the_compound_action_not_the_single_key_toggle(self) -> None:
        # mw3_options_toggle writes exactly one key; using it here is what left
        # SustainabilityPauseRendering switched on with the setting reporting off.
        assert MW3_PAUSE_RENDERING.apply_command == "mw3_pause_rendering_toggle"

    def test_recommends_off_so_a_visible_window_never_freezes(self) -> None:
        assert MW3_PAUSE_RENDERING.recommended_value == "false"

    def test_the_compound_action_writes_every_key_detection_reads(self) -> None:
        # If the two lists ever drift apart, apply silently stops clearing a key
        # that detect still reports on, and the setting can never read "false".
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        script = ACTION_COMMANDS["mw3_pause_rendering_toggle"]
        for key in MW3_PAUSE_RENDERING.detect_args["batch_key"]:
            assert key in script, key


class TestCompoundAnyTrueSemantics:
    """A compound is off only once every one of its keys is off."""

    @pytest.fixture
    def cst(self) -> str:
        return 'PauseRenderingEnabled:0.0 = "{a}"\nSustainabilityPauseRendering:0.0 = "{b}"\n'

    def _read(self, monkeypatch: pytest.MonkeyPatch, content: str) -> object:
        from fpstune.settings.executors import game_config_cache as gcc

        monkeypatch.setattr(gcc, "_snapshot", lambda: {"mw3": content})
        return gcc.get_mw3_options_any_true(
            ["PauseRenderingEnabled", "SustainabilityPauseRendering"]
        )

    def test_both_off_reads_false(self, monkeypatch: pytest.MonkeyPatch, cst: str) -> None:
        assert self._read(monkeypatch, cst.format(a="false", b="false")) == "false"

    def test_both_on_reads_true(self, monkeypatch: pytest.MonkeyPatch, cst: str) -> None:
        assert self._read(monkeypatch, cst.format(a="true", b="true")) == "true"

    def test_a_single_sibling_still_reads_true(
        self, monkeypatch: pytest.MonkeyPatch, cst: str
    ) -> None:
        # The concrete defect: MW3 kept pausing rendering while fpstune read
        # PauseRenderingEnabled alone and reported the setting already off.
        assert self._read(monkeypatch, cst.format(a="false", b="true")) == "true"
        assert self._read(monkeypatch, cst.format(a="true", b="false")) == "true"

    def test_absent_keys_report_not_installed_not_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "false" would claim the behaviour is off on a machine with no MW3.
        from fpstune.settings.executors import game_config_cache as gcc

        assert self._read(monkeypatch, 'SomeOtherKey:0.0 = "1"\n') == gcc.NOT_INSTALLED


class TestMenuSceneResolutionSemantics:
    """The cst value names the size of the reduction, not the resolution."""

    def test_recommends_the_maximum_reduction(self) -> None:
        # "full" = Maximal = maximum reduction = least GPU. fpstune used to
        # recommend "min", having read the label Maximal as meaning native
        # resolution, and so moved every machine to a *smaller* reduction while
        # claiming to cool the GPU.
        assert MW3_MENU_RENDER_RESOLUTION.recommended_value == "full"

    def test_never_recommends_the_no_reduction_end(self) -> None:
        assert MW3_MENU_RENDER_RESOLUTION.recommended_value not in ("off", "min")

    def test_value_hints_carry_the_games_own_labels(self) -> None:
        # Without these the UI shows "off/min/full", which reads as the opposite
        # of what the game's own menu calls them.
        assert MW3_MENU_RENDER_RESOLUTION.value_hints["off"] == "Native"
        assert MW3_MENU_RENDER_RESOLUTION.value_hints["min"] == "Optimal"
        assert MW3_MENU_RENDER_RESOLUTION.value_hints["full"] == "Maximal"

    def test_copy_does_not_call_full_a_native_resolution_render(self) -> None:
        # The exact wording of the original defect, kept as a guard because the
        # inversion is easy to reintroduce from any settings guide.
        text = (
            f"{MW3_MENU_RENDER_RESOLUTION.current_impact} "
            f"{MW3_MENU_RENDER_RESOLUTION.recommended_impact}"
        ).lower()
        assert "full (maximal): menus render at native res" not in text


class TestDriverVsyncFollowsThePanel:
    """V-Sync's cost depends on the display, so a single literal cannot be right."""

    def test_fixed_refresh_panel_keeps_vsync_off(self) -> None:
        s = create_nvidia_vsync_setting(vrr_available=False)
        assert s.recommended_value == "off"
        assert s.impact_scores["latency_ms"] == -10

    def test_vrr_panel_turns_vsync_on(self) -> None:
        # With G-Sync plus a below-refresh cap, V-Sync never engages during play;
        # leaving it off buys no latency and lets tearing back in above the cap.
        s = create_nvidia_vsync_setting(vrr_available=True)
        assert s.recommended_value == "on"

    def test_vrr_variant_claims_no_latency_cost(self) -> None:
        # The 8-16 ms figure belongs to fixed-refresh displays. Carrying it over
        # to the VRR branch is what made "off" look mandatory everywhere.
        s = create_nvidia_vsync_setting(vrr_available=True)
        assert s.impact_scores["latency_ms"] == 0.0

    def test_both_variants_keep_the_same_id_so_one_overrides_the_other(self) -> None:
        assert (
            create_nvidia_vsync_setting(vrr_available=True).id
            == create_nvidia_vsync_setting(vrr_available=False).id
        )

    def test_vrr_variant_is_gated_on_a_vrr_monitor(self) -> None:
        s = create_nvidia_vsync_setting(vrr_available=True)
        assert s.applicable_conditions["requires_vrr"] is True
        assert s.applicable_conditions["gpu_vendor"] == "nvidia"

    def test_discovery_leaves_the_fixed_refresh_default_without_a_vrr_panel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import registry as registry_mod

        class FixedRefresh:
            supports_vrr = False

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [FixedRefresh()],
        )
        assert discover_vrr_dependent_settings(reg, reg._probes) == 0

    def test_discovery_overrides_with_the_vrr_variant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import registry as registry_mod

        class VrrPanel:
            supports_vrr = True
            # A real monitor always reports these; a fake without them tested a
            # shape the product never sees.
            is_primary = True
            max_refresh_rate_hz = 300
            native_refresh_rate_hz = 300

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        before = reg.get("gpu-nvidia:vsync")
        assert before is not None and before.recommended_value == "off"
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [VrrPanel()],
        )
        # Two now: driver V-Sync and the frame cap are both panel-dependent, and
        # they are two thirds of one configuration. See test_vrr_configuration.py.
        assert discover_vrr_dependent_settings(reg, reg._probes) == 2
        after = reg.get("gpu-nvidia:vsync")
        assert after is not None and after.recommended_value == "on"

    def test_detection_failure_falls_back_instead_of_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import registry as registry_mod

        def boom(*_a: object, **_k: object) -> list:
            raise OSError("WMI unavailable")

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr("fpstune.utils.hardware_manager.hardware_manager.detect_monitors", boom)
        assert discover_vrr_dependent_settings(reg, reg._probes) == 0
        fallback = reg.get("gpu-nvidia:vsync")
        assert fallback is not None and fallback.recommended_value == "off"


class TestGamerprofileAcceptsBothShapes:
    """MW3 writes gamerprofile two ways; pinning either breaks half the installs.

    Measured on one install: one account's gamerprofile.0.BASE.cst uses
    ``Key@0 = value`` for all 60 keys, another's gamerprofile.pc.0.BASE.cst uses
    ``Key@ value`` for all 60. Two fpstune releases in a row each assumed one
    shape — the first appended a junk key when it missed, the second failed to
    apply at all with a verify error.
    """

    # Mirrors the pattern embedded in both the detect command and the apply
    # action; the tests below pin that both places still carry it.
    PATTERN = re.compile(r"(?m)^[ \t]*HTTPStreamLimitMBytes@(?:\d*[ \t]*=[ \t]*|[ \t]+)(\d+)")

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("HTTPStreamLimitMBytes@0 = 0", "0"),
            ("HTTPStreamLimitMBytes@ 0", "0"),
            ("HTTPStreamLimitMBytes@0 = 1024", "1024"),
            ("HTTPStreamLimitMBytes@ 1024", "1024"),
            ("  HTTPStreamLimitMBytes@0   =   512", "512"),
        ],
    )
    def test_pattern_reads_the_value_from_either_shape(self, line: str, expected: str) -> None:
        m = self.PATTERN.search(line)
        assert m is not None, line
        assert m.group(1) == expected

    def test_replacement_preserves_whichever_separator_the_file_uses(self) -> None:
        # The separator is captured, not chosen: rewriting `@0 = ` as `@ ` would
        # leave a key the game no longer reads.
        for line, want in (
            ("HTTPStreamLimitMBytes@0 = 1024", "HTTPStreamLimitMBytes@0 = 0"),
            ("HTTPStreamLimitMBytes@ 1024", "HTTPStreamLimitMBytes@ 0"),
        ):
            assert self.PATTERN.sub(r"\g<0>", line) == line
            prefix = re.compile(
                r"(?m)(^[ \t]*HTTPStreamLimitMBytes@(?:\d*[ \t]*=[ \t]*|[ \t]+))\d+"
            )
            assert prefix.sub(r"\g<1>0", line) == want

    def test_both_shipped_commands_carry_the_two_shape_alternation(self) -> None:
        from fpstune.settings.definitions.game_configs import MW3_TEXTURE_STREAMING
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        alternation = r"\d*[ \t]*=[ \t]*|[ \t]+"
        assert alternation in MW3_TEXTURE_STREAMING.detect_command.replace("\\\\", "\\")
        assert alternation in ACTION_COMMANDS["mw3_texture_toggle"]

    def test_backups_are_excluded_from_the_profile_choice(self) -> None:
        from fpstune.settings.definitions.game_configs import MW3_TEXTURE_STREAMING
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        # A backup copy can be the newest file on disk; writing to it changes
        # nothing for the game while reporting success.
        assert "mw3fix_backup" in MW3_TEXTURE_STREAMING.detect_command
        assert "mw3fix_backup" in ACTION_COMMANDS["mw3_texture_toggle"]


class TestVramScaleFollowsTheCard:
    """Headroom is a property of the card, so a constant is wrong on most of them."""

    @pytest.mark.parametrize(
        ("gb", "expected"),
        [(6, "0.700000"), (8, "0.700000"), (12, "0.850000"), (16, "0.950000"), (24, "0.950000")],
    )
    def test_target_scales_with_vram(self, gb: int, expected: str) -> None:
        assert create_mw3_vram_scale_setting(gb * 1024).recommended_value == expected

    def test_eight_gigabyte_cards_get_the_documented_seventy_percent(self) -> None:
        # This shipped as a hardcoded 0.850000 for every card. On 8 GB — the card
        # every packet-burst guide is written about — that is the saturation the
        # setting exists to prevent.
        assert create_mw3_vram_scale_setting(8 * 1024).recommended_value == "0.700000"

    def test_large_cards_are_not_given_the_small_card_number(self) -> None:
        # 70% of 24 GB hands back 7 GB for nothing.
        assert create_mw3_vram_scale_setting(24 * 1024).recommended_value != "0.700000"

    def test_target_is_always_one_of_the_games_own_choices(self) -> None:
        for gb in (4, 6, 8, 10, 12, 16, 20, 24, 32):
            s = create_mw3_vram_scale_setting(gb * 1024)
            assert s.recommended_value in s.choices, gb

    def test_unknown_vram_produces_no_setting_at_all(self) -> None:
        """0 means "not detected", and there is no honest answer to give for it.

        This used to return a setting built from a fabricated 10 GB card, so a
        machine whose GPU could not be read was told in as many words that "the
        card detected here has 10 GB" and handed 85% — which on a real 6 GB card
        is the VRAM saturation this setting exists to prevent, and one of the
        documented packet-burst triggers.

        Refusing is what the rest of the codebase does with a value the hardware
        did not supply: network:<n>:rss_queues is not registered on an adapter
        whose driver publishes no queue counts, rather than offered a guess.
        """
        import pytest

        for unknown in (0, None, -1):
            with pytest.raises(ValueError, match="actual VRAM"):
                create_mw3_vram_scale_setting(unknown)  # type: ignore[arg-type]

    def test_a_real_card_is_still_described_by_its_own_size(self) -> None:
        """The refusal above must not have taken the working path with it."""
        s = create_mw3_vram_scale_setting(8 * 1024)
        assert "8 GB" in s.effect
        assert s.recommended_value == "0.700000"


class TestStreamingIsScoredAsNetwork:
    """The most-cited packet-burst fix has to be findable by someone hunting it."""

    def test_texture_streaming_carries_a_network_category(self) -> None:
        from fpstune.settings.definitions.game_configs import MW3_TEXTURE_STREAMING
        from fpstune.settings.impact_categories import derive_impact_categories

        cats = derive_impact_categories(MW3_TEXTURE_STREAMING.impact_scores)
        assert "network" in cats

    def test_world_streaming_carries_a_network_category(self) -> None:
        from fpstune.settings.definitions.game_configs import MW3_WORLD_STREAMING
        from fpstune.settings.impact_categories import derive_impact_categories

        assert "network" in derive_impact_categories(MW3_WORLD_STREAMING.impact_scores)

    def test_the_gate_is_written_with_the_limit(self) -> None:
        # A cap whose gate is off is what this setting shipped as for months.
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        script = ACTION_COMMANDS["mw3_texture_toggle"]
        assert "HTTPStreamUsageLimit" in script
        assert "HTTPStreamLimitMBytes" in script

    def test_the_inference_is_labelled_as_one(self) -> None:
        # The gate relationship is read off the key names, not documentation.
        # Saying so is the difference between a warning and a claim.
        from fpstune.settings.definitions.game_configs import MW3_TEXTURE_STREAMING

        assert MW3_TEXTURE_STREAMING.risk_warning is not None
        assert "inert" in MW3_TEXTURE_STREAMING.risk_warning.lower()


class TestQualityGates:
    """The new settings must satisfy the project's own C2/C3 gates."""

    @pytest.fixture
    def settings(self) -> list:
        return [
            create_mw3_refresh_rate_setting(300, "AW2725DF"),
            create_mw3_fps_cap_setting(300),
            create_mw3_resolution_setting(2560, 1440),
            create_mw3_menu_fps_cap_setting(300),
            MW3_PAUSE_RENDERING,
        ]

    def test_c2_every_setting_carries_a_non_stability_metric(self, settings: list) -> None:
        for s in settings:
            assert any(k != "stability" for k in s.impact_scores), s.id

    def test_c3_description_is_a_sentence_and_effect_is_a_phrase(self, settings: list) -> None:
        for s in settings:
            assert s.description.rstrip().endswith("."), s.id
            assert not s.effect.rstrip().endswith("."), s.id

    def test_c4_no_turkish_characters_in_user_facing_strings(self, settings: list) -> None:
        forbidden = set("çğıİöşüÇĞÖŞÜ")
        for s in settings:
            for text in (s.display_name, s.description, s.effect, s.recommended_impact):
                assert not (forbidden & set(str(text))), s.id


class TestDiscoveryDegradesSafely:
    """A monitor that cannot be read must not produce a wrong recommendation."""

    def test_no_monitors_registers_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fpstune.settings import registry as registry_mod

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [],
        )
        assert discover_mw3_display_settings(reg, reg._probes) == 0
        assert reg.get("game_config:mw3:refresh_rate") is None

    def test_detection_failure_is_swallowed_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import registry as registry_mod

        def boom(*_a: object, **_k: object) -> list:
            raise OSError("WMI unavailable")

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr("fpstune.utils.hardware_manager.hardware_manager.detect_monitors", boom)
        assert discover_mw3_display_settings(reg, reg._probes) == 0

    def test_unknown_refresh_still_registers_resolution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A zero refresh rate means "not detected". It must not become 60, and it
        # must not suppress the resolution setting, which was detected fine.
        from fpstune.settings import registry as registry_mod

        class FakeMonitor:
            is_primary = True
            name = "FAKE"
            friendly_name = "Fake Panel"
            max_refresh_rate_hz = 0
            native_refresh_rate_hz = 0
            width = 1920
            height = 1080
            native_width = 1920
            native_height = 1080

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [FakeMonitor()],
        )
        assert discover_mw3_display_settings(reg, reg._probes) == 1
        assert reg.get("game_config:mw3:refresh_rate") is None
        assert reg.get("game_config:mw3:resolution") is not None
