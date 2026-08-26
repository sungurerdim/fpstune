"""VRR is one configuration made of three settings, and they must agree.

The documented low-latency setup for a variable-refresh panel is VRR on, driver
V-Sync on, and a frame cap a few frames below the refresh rate. Each piece is
useless or harmful without the other two:

  * no cap  -> the frame rate leaves the VRR window and V-Sync latency arrives
  * no V-Sync -> tearing returns in the moments the cap is overshot
  * VRR scoped to fullscreen only -> none of it applies in borderless

fpstune shipped two answers to this question. ``gpu-nvidia:vrr_mode`` and
``gpu-nvidia:vsync`` derived the configuration correctly, while the display
panel's own ``get_vrr_optimization_info_for_monitor`` handed back "fullscreen"
and V-Sync "off" — telling the user, in a different part of the same product, to
undo it. These tests exist so the two paths cannot drift apart again.

Source for the -3 margin and the V-Sync pairing:
https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingScope, SettingValueType
from fpstune.settings.definitions.game_configs import create_mw3_fps_cap_setting
from fpstune.settings.definitions.gpu import (
    NVIDIA_VRR_MODE,
    create_nvidia_fps_limiter_setting,
    create_nvidia_vsync_setting,
)
from fpstune.settings.discovery.display import discover_vrr_dependent_settings
from fpstune.settings.executors.nvprofile import NvProfileExecutor


class TestDriverFpsCapFollowsThePanel:
    def test_vrr_panel_gets_the_refresh_minus_three_cap(self) -> None:
        assert create_nvidia_fps_limiter_setting(True, 300).recommended_value == 297

    @pytest.mark.parametrize(
        ("hz", "expected"), [(60, 57), (144, 141), (165, 162), (240, 237), (300, 297)]
    )
    def test_tracks_whatever_panel_is_attached(self, hz: int, expected: int) -> None:
        # The defect this guards: a cap that was right for the monitor that used
        # to be plugged in. 162 on a 300 Hz panel throws away 135 frames a second.
        assert create_nvidia_fps_limiter_setting(True, hz).recommended_value == expected

    def test_fixed_refresh_panel_gets_no_cap_at_all(self) -> None:
        # With no VRR window to stay inside, a driver cap only lowers the ceiling,
        # which the project's third consequence forbids outright.
        assert create_nvidia_fps_limiter_setting(False, 300).recommended_value == 0

    def test_unknown_refresh_rate_gets_no_cap_rather_than_a_guess(self) -> None:
        # 0 means "not detected". Turning that into 60 - 3 would cap a 300 Hz
        # machine at 57 on the strength of a reading that never happened.
        assert create_nvidia_fps_limiter_setting(True, 0).recommended_value == 0

    def test_floors_at_thirty_for_a_panel_below_the_margin(self) -> None:
        assert create_nvidia_fps_limiter_setting(True, 31).recommended_value == 30

    def test_both_variants_keep_the_same_id_so_one_overrides_the_other(self) -> None:
        assert (
            create_nvidia_fps_limiter_setting(True, 300).id
            == create_nvidia_fps_limiter_setting(False).id
        )

    def test_vrr_variant_is_gated_on_a_vrr_monitor(self) -> None:
        s = create_nvidia_fps_limiter_setting(True, 300)
        assert s.applicable_conditions["requires_vrr"] is True
        assert s.applicable_conditions["gpu_vendor"] == "nvidia"

    def test_the_cap_is_recommended_scope_not_buried_in_complete(self) -> None:
        # It shipped as COMPLETE with a static recommended_value of 0, so the one
        # setting that completes the VRR configuration was never offered by the
        # scope most users run.
        assert create_nvidia_fps_limiter_setting(True, 300).scope is SettingScope.RECOMMENDED
        assert create_nvidia_fps_limiter_setting(False).scope is SettingScope.RECOMMENDED

    def test_is_an_int_not_a_choice(self) -> None:
        assert create_nvidia_fps_limiter_setting(True, 300).value_type is SettingValueType.INT

    def test_copy_states_the_derived_number_not_a_stale_zero(self) -> None:
        # The concrete defect: recommended_value was mutated to 297 at runtime
        # while recommended_impact still read "0: Unlimited FPS", so the row
        # showed a recommendation and a description that contradicted it.
        s = create_nvidia_fps_limiter_setting(True, 300)
        assert "297" in s.recommended_impact
        assert "Unlimited FPS" not in s.recommended_impact

    def test_the_driver_cap_and_the_mw3_cap_are_the_same_number(self) -> None:
        # Two caps built from one panel must not disagree; whichever is lower
        # would silently become the real ceiling.
        for hz in (60, 144, 165, 240, 300):
            assert (
                create_nvidia_fps_limiter_setting(True, hz).recommended_value
                == create_mw3_fps_cap_setting(hz).recommended_value
            )


class TestTheVrrPanelAgreesWithTheSettings:
    """The display panel and the settings registry answer the same question."""

    def test_vrr_mode_is_never_scoped_to_fullscreen_only(self) -> None:
        # "fullscreen" is NVCP's "Enable G-SYNC for full screen mode", which
        # leaves borderless without VRR entirely.
        info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(300, True)
        assert info["recommended_vrr_mode"] != "fullscreen"

    def test_vrr_mode_matches_the_setting_that_writes_it(self) -> None:
        info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(300, True)
        assert info["recommended_vrr_mode"] == NVIDIA_VRR_MODE.recommended_value

    def test_vsync_matches_the_setting_that_writes_it(self) -> None:
        for hz, vrr in ((300, True), (60, False)):
            info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(hz, vrr)
            assert info["recommended_vsync"] == create_nvidia_vsync_setting(vrr).recommended_value

    def test_fps_limit_matches_the_setting_that_writes_it(self) -> None:
        for hz in (60, 144, 300):
            info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(hz, True)
            assert (
                info["recommended_fps_limit"]
                == create_nvidia_fps_limiter_setting(True, hz).recommended_value
            )

    def test_a_fixed_refresh_panel_is_told_to_turn_everything_off(self) -> None:
        info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(144, False)
        assert info["recommended_vrr_mode"] == "off"
        assert info["recommended_vsync"] == "off"
        assert info["recommended_fps_limit"] == 0

    def test_the_explanation_does_not_advertise_the_setting_it_no_longer_makes(self) -> None:
        # It used to read "VSync off eliminates input lag" while recommending
        # V-Sync on two modules away.
        info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(300, True)
        assert "VSync off eliminates input lag" not in info["explanation"]


class TestDiscoveryRegistersTheDerivedCap:
    def test_a_vrr_panel_registers_both_vsync_and_the_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import registry as registry_mod

        class VrrPanel:
            supports_vrr = True
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 300
            native_refresh_rate_hz = 300

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [VrrPanel()],
        )
        assert discover_vrr_dependent_settings(reg, reg._probes) == 2
        cap = reg.get("gpu-nvidia:fps_limit")
        assert cap is not None and cap.recommended_value == 297

    def test_an_unreadable_refresh_rate_still_registers_vsync(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One unknown must not suppress the setting that did not depend on it.
        from fpstune.settings import registry as registry_mod

        class VrrPanelNoRate:
            supports_vrr = True
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 0
            native_refresh_rate_hz = 0

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [VrrPanelNoRate()],
        )
        assert discover_vrr_dependent_settings(reg, reg._probes) == 1
        cap = reg.get("gpu-nvidia:fps_limit")
        assert cap is not None and cap.recommended_value == 0

    def test_a_fixed_refresh_panel_leaves_the_static_uncapped_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import registry as registry_mod

        class FixedRefresh:
            supports_vrr = False
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 144
            native_refresh_rate_hz = 144

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [FixedRefresh()],
        )
        assert discover_vrr_dependent_settings(reg, reg._probes) == 0

    def test_an_unknown_panel_registers_neither_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # supports_vrr None means the EDID could not be read. Registering the
        # VRR variants on it would put V-Sync and a frame cap on a panel that
        # may be a plain fixed-refresh display — the exact harm the old
        # maxHz > 60 guess did to a 75 Hz office monitor.
        from fpstune.settings import registry as registry_mod

        class UnknownPanel:
            supports_vrr = None
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 240
            native_refresh_rate_hz = 0

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [UnknownPanel()],
        )
        assert discover_vrr_dependent_settings(reg, reg._probes) == 0
        # The static uncapped default stays — a drift guard, not a VRR cap.
        cap = reg.get("gpu-nvidia:fps_limit")
        assert cap is not None and cap.recommended_value == 0
        cap = reg.get("gpu-nvidia:fps_limit")
        assert cap is not None and cap.recommended_value == 0


class TestQualityGates:
    @pytest.fixture
    def settings(self) -> list:
        return [
            create_nvidia_fps_limiter_setting(True, 300),
            create_nvidia_fps_limiter_setting(False),
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


class TestTheSixthDerivationIsGone:
    """B5: nvprofile no longer derives the panel itself, and never invents 60."""

    def test_an_unknown_rate_stays_zero_and_never_becomes_sixty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(NvProfileExecutor, "_primary_monitor_info", None)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [],
        )
        refresh, supports_vrr = NvProfileExecutor()._get_primary_monitor_info()
        assert (refresh, supports_vrr) == (0, None)

    def test_an_unknown_is_not_cached_so_the_next_caller_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(NvProfileExecutor, "_primary_monitor_info", None)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [],
        )
        NvProfileExecutor()._get_primary_monitor_info()
        assert NvProfileExecutor._primary_monitor_info is None

    def test_a_vrr_panel_with_an_unknown_rate_gets_no_fabricated_cap(self) -> None:
        # frame_cap_for_refresh(0) floors at 30 — a ceiling nothing measured.
        info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(0, True)
        assert info["recommended_fps_limit"] == 0

    def test_a_parked_inactive_panel_is_not_the_panel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """panel.py's active-only rule now governs this module too."""

        class Parked:
            is_active = False
            is_primary = True
            max_refresh_rate_hz = 60
            native_refresh_rate_hz = 60
            refresh_rate_hz = 60
            supports_vrr = False
            friendly_name = "internal"
            name = "AAA0001"

        class External:
            is_active = True
            is_primary = False
            max_refresh_rate_hz = 300
            native_refresh_rate_hz = 60
            refresh_rate_hz = 120
            supports_vrr = True
            friendly_name = "external"
            name = r"\.\DISPLAY5"

        monkeypatch.setattr(NvProfileExecutor, "_primary_monitor_info", None)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: [Parked(), External()],
        )
        refresh, supports_vrr = NvProfileExecutor()._get_primary_monitor_info()
        monkeypatch.setattr(NvProfileExecutor, "_primary_monitor_info", None)
        assert (refresh, supports_vrr) == (300, True)
