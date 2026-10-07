"""The NVIDIA DRS key table: IDs and values pinned to NVIDIA's header.

Every literal below is copied from NvApiDriverSettings.h (github.com/NVIDIA/nvapi).
The previous table invented eight setting IDs in a 0x007070xx range the driver
never reads, swapped G-SYNC's fullscreen/windowed values and wrote FORCE_OFF for
"force on"; these tests exist so none of that can come back unnoticed.
"""

from __future__ import annotations

import pytest

from fpstune.core import nv_drs, nvapi
from fpstune.core.nv_drs import KEYS, EnumKey, NumberKey, accepts, refused_writes
from fpstune.core.nvapi import AvailableValues


class TestIdsMatchTheHeader:
    @pytest.mark.parametrize(
        ("name", "header_value"),
        [
            ("PREFERRED_PSTATE", 0x1057EB71),
            ("PRERENDERLIMIT", 0x007BA09E),
            ("OGL_THREAD_CONTROL", 0x20C1221E),
            ("VSYNCMODE", 0x00A879CF),
            ("PS_SHADERDISKCACHE", 0x00198FFF),
            ("QUALITY_ENHANCEMENTS", 0x00CE2691),
            ("OGL_TRIPLE_BUFFER", 0x20FDD1F9),
            ("FRL_FPS", 0x10835002),
            ("VRR_MODE", 0x1194F158),
            ("VRR_APP_OVERRIDE", 0x10A879CF),
            ("PS_TEXFILTER_ANISO_OPTS2", 0x00E73211),
            ("PS_TEXFILTER_NO_NEG_LODBIAS", 0x0019BB68),
        ],
    )
    def test_published_id(self, name: str, header_value: int) -> None:
        assert getattr(nv_drs, name) == header_value

    def test_no_invented_id_range_survives(self) -> None:
        for key in KEYS.values():
            for setting_id in key.ids:
                assert not 0x00707000 <= setting_id <= 0x007070FF, (key.key, hex(setting_id))


class TestValuesMatchTheHeader:
    def test_vrr_mode_fullscreen_is_1_and_windowed_is_2(self) -> None:
        vrr = KEYS["vrr_mode"]
        assert isinstance(vrr, EnumKey)
        assert vrr.values["fullscreen"] == {nv_drs.VRR_MODE: 1}  # FULLSCREEN_ONLY
        assert vrr.values["on"] == {nv_drs.VRR_MODE: 2}  # FULLSCREEN_AND_WINDOWED
        assert vrr.stock == "fullscreen"  # VRR_MODE_DEFAULT

    def test_vrr_app_override_never_writes_force_off(self) -> None:
        override = KEYS["vrr_app_override"]
        assert isinstance(override, EnumKey)
        written = {v[nv_drs.VRR_APP_OVERRIDE] for v in override.values.values()}
        assert 1 not in written  # VRR_APP_OVERRIDE_FORCE_OFF

    def test_vsync_modes(self) -> None:
        vsync = KEYS["vsync"]
        assert isinstance(vsync, EnumKey)
        assert vsync.values["app"] == {nv_drs.VSYNCMODE: 0x60925292}  # PASSIVE
        assert vsync.values["off"] == {nv_drs.VSYNCMODE: 0x08416747}  # FORCEOFF
        assert vsync.values["on"] == {nv_drs.VSYNCMODE: 0x47814940}  # FORCEON
        assert vsync.stock == "app"

    def test_texture_quality_uses_the_real_enum(self) -> None:
        quality = KEYS["texture_quality"]
        assert isinstance(quality, EnumKey)
        assert quality.values["high_quality"][nv_drs.QUALITY_ENHANCEMENTS] == 0xFFFFFFF6
        assert quality.values["performance"][nv_drs.QUALITY_ENHANCEMENTS] == 0x0A
        assert quality.values["high_performance"][nv_drs.QUALITY_ENHANCEMENTS] == 0x14

    def test_power_mode_stock_is_optimal_power(self) -> None:
        power = KEYS["power_mode"]
        assert isinstance(power, EnumKey)
        assert power.values[power.stock] == {nv_drs.PREFERRED_PSTATE: 5}

    def test_frame_limiter_range(self) -> None:
        fps = KEYS["fps_limit"]
        assert isinstance(fps, NumberKey)
        assert (fps.stock, fps.maximum) == (0, 0x3FF)


class TestEveryChoiceRoundTrips:
    """What a choice writes must read back as that choice."""

    @staticmethod
    def _apply(changes: dict[int, int | None]) -> dict[int, int]:
        return {i: v for i, v in changes.items() if v is not None}

    @pytest.mark.parametrize(
        ("key", "choice"),
        [(k.key, c) for k in KEYS.values() if isinstance(k, EnumKey) for c in k.values],
    )
    def test_enum_choice(self, key: str, choice: str) -> None:
        drs = KEYS[key]
        assert drs.decode(self._apply(drs.changes_for(choice))) == choice

    @pytest.mark.parametrize("value", [0, 141, 237, 0x3FF])
    def test_frame_cap(self, value: int) -> None:
        drs = KEYS["fps_limit"]
        assert drs.decode(self._apply(drs.changes_for(value))) == value


class TestStockIsTheDriversOwn:
    @pytest.mark.parametrize("key", list(KEYS))
    def test_stock_deletes_every_key(self, key: str) -> None:
        drs = KEYS[key]
        assert set(drs.changes_for(drs.stock).values()) == {None}

    @pytest.mark.parametrize("key", list(KEYS))
    def test_an_untouched_profile_reads_as_stock(self, key: str) -> None:
        drs = KEYS[key]
        assert drs.decode({}) == drs.stock


class TestLowLatency:
    def test_ultra_writes_the_prerender_limit_and_the_ultra_switch(self) -> None:
        changes = KEYS["low_latency"].changes_for("ultra")
        assert changes[nv_drs.PRERENDERLIMIT] == 1
        assert changes[nv_drs.ULL_ENABLED] == 1

    def test_the_control_panel_state_is_ignored_when_reading(self) -> None:
        """A tool that set the pre-render limit without NVCP's bookkeeping key
        still runs Low Latency On, and must read as on."""
        assert KEYS["low_latency"].decode({nv_drs.PRERENDERLIMIT: 1}) == "on"

    def test_a_limit_no_tier_describes_is_not_guessed(self) -> None:
        assert KEYS["low_latency"].decode({nv_drs.PRERENDERLIMIT: 3}) is None


class TestRejections:
    def test_unknown_choice(self) -> None:
        with pytest.raises(ValueError):
            KEYS["vsync"].changes_for("adaptive")

    def test_cap_beyond_the_driver_limit(self) -> None:
        with pytest.raises(ValueError):
            KEYS["fps_limit"].changes_for(0x400)

    def test_unmapped_raw_power_state_is_not_guessed(self) -> None:
        # PREFERRED_PSTATE_PREFER_CONSISTENT_PERFORMANCE: no choice describes it.
        assert KEYS["power_mode"].decode({nv_drs.PREFERRED_PSTATE: 3}) is None


class TestDefinitionsMatchTheTable:
    """Each NVIDIA setting's choices and stock value must be the table's."""

    def test_every_nvidia_setting_has_a_key_and_agrees_on_stock(self) -> None:
        from fpstune.settings.base import DetectType
        from fpstune.settings.definitions.gpu import GPU_SETTINGS

        nvidia = [s for s in GPU_SETTINGS if s.detect_type == DetectType.NVPROFILE]
        assert nvidia
        for setting in nvidia:
            drs = KEYS[setting.detect_args["setting"]]
            assert setting.default_value == drs.stock, setting.id
            if isinstance(drs, EnumKey):
                assert set(setting.choices) == set(drs.values), setting.id


class TestKeysTheDriverLacks:
    """The pure rules: which choices survive when the driver lacks a key."""

    def _low_latency(self) -> EnumKey:
        key = KEYS["low_latency"]
        assert isinstance(key, EnumKey)
        return key

    def test_ultra_needs_the_key_whose_value_is_what_makes_it_ultra(self) -> None:
        key = self._low_latency()

        assert key.choices({nv_drs.ULL_ENABLED}) == ("off", "on")

    def test_on_and_off_want_zero_from_a_key_that_absent_already_reads_as(self) -> None:
        key = self._low_latency()

        assert key.expressible("on", {nv_drs.ULL_ENABLED})
        assert key.expressible("off", {nv_drs.ULL_ENABLED})

    def test_a_write_only_key_is_never_what_a_choice_means(self) -> None:
        key = self._low_latency()

        assert key.choices({nv_drs.ULL_CPL_STATE}) == ("off", "on", "ultra")
        assert key.changes_for("ultra", {nv_drs.ULL_CPL_STATE}) == {
            nv_drs.PRERENDERLIMIT: 1,
            nv_drs.ULL_ENABLED: 1,
        }

    def test_missing_keys_are_left_out_of_the_write_not_written_anyway(self) -> None:
        key = self._low_latency()

        assert key.changes_for("on", {nv_drs.ULL_ENABLED}) == {
            nv_drs.PRERENDERLIMIT: 1,
            nv_drs.ULL_CPL_STATE: 1,
        }
        assert key.changes_for("off", {nv_drs.ULL_ENABLED}) == {
            nv_drs.PRERENDERLIMIT: None,
            nv_drs.ULL_CPL_STATE: None,
        }

    def test_a_choice_that_lived_in_the_missing_key_raises_in_words(self) -> None:
        with pytest.raises(ValueError, match="not available on this driver"):
            self._low_latency().changes_for("ultra", {nv_drs.ULL_ENABLED})

    def test_nothing_missing_changes_nothing(self) -> None:
        key = self._low_latency()

        assert key.choices() == ("off", "on", "ultra")
        assert key.changes_for("ultra") == {
            nv_drs.PRERENDERLIMIT: 1,
            nv_drs.ULL_ENABLED: 1,
            nv_drs.ULL_CPL_STATE: 2,
        }

    def test_a_setting_with_only_its_stock_choice_left_is_not_supported(self) -> None:
        key = self._low_latency()

        assert key.supports()
        assert key.supports({nv_drs.ULL_ENABLED})
        assert not key.supports({nv_drs.PRERENDERLIMIT})

    def test_a_number_setting_is_supported_only_with_its_key(self) -> None:
        fps = KEYS["fps_limit"]
        assert isinstance(fps, NumberKey)

        assert fps.supports()
        assert not fps.supports({nv_drs.FRL_FPS})
        with pytest.raises(ValueError, match="does not have the NVIDIA setting"):
            fps.changes_for(141, {nv_drs.FRL_FPS})

    @pytest.mark.parametrize("name", sorted(KEYS))
    def test_every_setting_without_any_of_its_keys_is_not_supported(self, name: str) -> None:
        key = KEYS[name]

        assert not key.supports(set(key.ids))


# What a real NVIDIA driver prints for NvAPI_DRS_EnumAvailableSettingValues, id ->
# (values in the driver's order, default). Ranges list their `_MIN` and `_MAX` among
# the values (the pre-render limit prints 0, 255, 0; the frame limiter 0, 0, 1023),
# and a default need not be listed (threaded optimization prints 1, 2 and defaults to 0).
REAL_DRIVER: dict[int, AvailableValues] = {
    nv_drs.PREFERRED_PSTATE: AvailableValues((0, 1, 2, 3, 4, 5, 0, 5), 5),
    nv_drs.PRERENDERLIMIT: AvailableValues((0, 0xFF, 0), 0),
    nv_drs.OGL_THREAD_CONTROL: AvailableValues((1, 2), 0),
    nv_drs.VSYNCMODE: AvailableValues(
        (0x60925292, 0x08416747, 0x47814940, 0x32610244, 0x71271021, 0x13245256, 0x18888888),
        0x60925292,
    ),
    nv_drs.PS_SHADERDISKCACHE: AvailableValues((0, 1), 1),
    nv_drs.QUALITY_ENHANCEMENTS: AvailableValues((0xFFFFFFF6, 0, 0xA, 0x14), 0),
    nv_drs.OGL_TRIPLE_BUFFER: AvailableValues((0, 1), 0),
    nv_drs.FRL_FPS: AvailableValues((0, 0, 0x3FF), 0),
    nv_drs.VRR_MODE: AvailableValues((0, 1, 2), 1),
    nv_drs.VRR_APP_OVERRIDE: AvailableValues((0, 1, 2, 3, 4), 0),
    nv_drs.PS_TEXFILTER_ANISO_OPTS2: AvailableValues((0, 1), 0),
    nv_drs.PS_TEXFILTER_NO_NEG_LODBIAS: AvailableValues((0, 1), 0),
}
# That driver does not define these four (it is the generation without the ULL keys).
REAL_DRIVER_LACKS = frozenset(
    {nv_drs.ULL_ENABLED, nv_drs.ULL_CPL_STATE, nv_drs.FRL_BACKGROUND, nv_drs.CUDA_FORCE_P2}
)


def _write(name: str, choice: int | str) -> dict[int, int | None]:
    key = KEYS[name]
    if isinstance(key, NumberKey):
        return key.changes_for(int(choice), REAL_DRIVER_LACKS)
    return key.changes_for(str(choice), REAL_DRIVER_LACKS)


class TestTheTableAgreesWithTheDriversOwnLists:
    """A value the table writes is one the driver lists, so apply never sends one it refuses."""

    @pytest.mark.parametrize("name", sorted(n for n, k in KEYS.items() if isinstance(k, EnumKey)))
    def test_every_choice_the_driver_can_hold_is_accepted(self, name: str) -> None:
        key = KEYS[name]
        assert isinstance(key, EnumKey)
        for choice in key.choices(REAL_DRIVER_LACKS):
            changes = key.changes_for(choice, REAL_DRIVER_LACKS)
            assert refused_writes(key, changes, REAL_DRIVER) == [], (name, choice)

    @pytest.mark.parametrize("fps", [0, 1, 141, 360, 1023])
    def test_every_frame_cap_inside_the_drivers_range_is_accepted(self, fps: int) -> None:
        assert refused_writes(KEYS["fps_limit"], _write("fps_limit", fps), REAL_DRIVER) == []

    def test_every_mapped_id_is_in_the_real_lists_or_declared_absent(self) -> None:
        assert nv_drs.mapped_ids() == set(REAL_DRIVER) | REAL_DRIVER_LACKS


class TestAValueOutsideTheDriversListIsRefused:
    def test_an_enum_value_the_driver_does_not_list(self) -> None:
        changes = {nv_drs.OGL_THREAD_CONTROL: 3}

        refused = refused_writes(KEYS["threaded_opt"], changes, REAL_DRIVER)

        assert [(r.setting_id, r.value) for r in refused] == [(nv_drs.OGL_THREAD_CONTROL, 3)]

    def test_the_message_quotes_the_drivers_own_list(self) -> None:
        refused = refused_writes(KEYS["power_mode"], {nv_drs.PREFERRED_PSTATE: 6}, REAL_DRIVER)

        assert len(refused) == 1
        assert "does not accept 0x6" in refused[0].message
        assert "0x1057eb71" in refused[0].message
        assert "0x0, 0x1, 0x2, 0x3, 0x4, 0x5 (default 0x5)" in refused[0].message

    def test_a_ranged_value_past_the_drivers_maximum(self) -> None:
        refused = refused_writes(KEYS["low_latency"], {nv_drs.PRERENDERLIMIT: 256}, REAL_DRIVER)

        assert len(refused) == 1
        assert "0 to 255 (default 0)" in refused[0].message

    def test_a_frame_cap_past_the_drivers_maximum(self) -> None:
        refused = refused_writes(KEYS["fps_limit"], {nv_drs.FRL_FPS: 1024}, REAL_DRIVER)

        assert len(refused) == 1
        assert "0 to 1023" in refused[0].message

    def test_every_refused_write_is_reported_not_just_the_first(self) -> None:
        changes = {nv_drs.VSYNCMODE: 0x1, nv_drs.PS_SHADERDISKCACHE: 7}

        refused = refused_writes(KEYS["vsync"], changes, REAL_DRIVER)

        assert {r.setting_id for r in refused} == {nv_drs.VSYNCMODE, nv_drs.PS_SHADERDISKCACHE}

    def test_a_ranged_id_is_tight_only_where_the_key_says_it_is_a_range(self) -> None:
        """Between the ends of an enum's list is not enough: 4 is no vsync value."""
        assert not accepts(REAL_DRIVER[nv_drs.VSYNCMODE], 0x10000000, ranged=False)
        assert accepts(REAL_DRIVER[nv_drs.VSYNCMODE], 0x10000000, ranged=True)


class TestWhatTheDriverDoesNotContradictIsNotRefused:
    def test_the_default_is_accepted_though_the_driver_does_not_list_it(self) -> None:
        """Threaded optimization lists 1 and 2; 0 is its own auto choice and default."""
        assert 0 not in REAL_DRIVER[nv_drs.OGL_THREAD_CONTROL].values
        assert accepts(REAL_DRIVER[nv_drs.OGL_THREAD_CONTROL], 0, ranged=False)

    def test_a_deletion_is_never_refused(self) -> None:
        changes: dict[int, int | None] = {nv_drs.OGL_THREAD_CONTROL: None}

        assert refused_writes(KEYS["threaded_opt"], changes, REAL_DRIVER) == []

    def test_an_id_the_driver_gave_no_list_for_is_never_refused(self) -> None:
        changes: dict[int, int | None] = {nv_drs.ULL_ENABLED: 12345}

        assert refused_writes(KEYS["low_latency"], changes, {}) == []

    def test_a_signed_spelling_of_an_unsigned_value_is_the_same_value(self) -> None:
        assert accepts(REAL_DRIVER[nv_drs.QUALITY_ENHANCEMENTS], -10, ranged=False)

    def test_an_empty_list_is_not_a_list(self) -> None:
        assert accepts(AvailableValues((), 0), 7, ranged=False)
        assert accepts(AvailableValues((), 0), 7, ranged=True)


class TestRangedIdsAreTheOnesTheHeaderDeclaresAsRanges:
    def test_the_pre_render_limit_and_the_frame_limiters_are_ranges(self) -> None:
        assert KEYS["low_latency"].ranged == {nv_drs.PRERENDERLIMIT}
        assert KEYS["fps_limit"].ranged == {nv_drs.FRL_FPS}
        assert KEYS["bg_app_fps"].ranged == {nv_drs.FRL_BACKGROUND}

    def test_no_enum_key_other_than_low_latency_declares_a_range(self) -> None:
        declaring = {name for name, key in KEYS.items() if isinstance(key, EnumKey) and key.ranged}
        assert declaring == {"low_latency"}


class TestTheTableAgainstTheInstalledDriver:
    """The same agreement, asked of the driver that is actually installed."""

    def test_every_choice_the_installed_driver_can_hold_is_one_it_lists(self) -> None:
        ids = sorted(nv_drs.mapped_ids())
        available = nvapi.available_setting_values(ids)
        known = nvapi.known_setting_ids(ids)
        if not available or known is None:
            pytest.skip("no NVIDIA driver answering on this machine")
        missing = frozenset(ids) - known
        for name, key in KEYS.items():
            if not key.supports(missing):
                continue
            if isinstance(key, EnumKey):
                for choice in key.choices(missing):
                    changes = key.changes_for(choice, missing)
                    assert refused_writes(key, changes, available) == [], (name, choice)
