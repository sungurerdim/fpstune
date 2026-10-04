"""The NVIDIA DRS key table: IDs and values pinned to NVIDIA's header.

Every literal below is copied from NvApiDriverSettings.h (github.com/NVIDIA/nvapi).
The previous table invented eight setting IDs in a 0x007070xx range the driver
never reads, swapped G-SYNC's fullscreen/windowed values and wrote FORCE_OFF for
"force on"; these tests exist so none of that can come back unnoticed.
"""

from __future__ import annotations

import pytest

from fpstune.core import nv_drs
from fpstune.core.nv_drs import KEYS, EnumKey, NumberKey


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
