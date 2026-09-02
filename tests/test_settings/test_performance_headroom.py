"""Tests for scoping quality raises by what the machine actually achieves.

The defect this exists to prevent shipped once: fpstune recommended a sharper
image to a system running at a fifth of its display's refresh. Measured on that
machine — MW4 at 59 fps against a 300 Hz panel — the raises it recommended would
have cost roughly half of the frame rate that was already short.

Nothing here reads the developer's machine or the real state directory.
"""

from __future__ import annotations

import json

import pytest

from fpstune.settings.base import SettingScope
from fpstune.settings.performance_headroom import (
    MAX_AGE_SECONDS,
    PerformanceHeadroom,
    read_headroom,
    record_headroom,
)
from fpstune.settings.registry import SettingsRegistry

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Point the state file at a temp dir so no test reads or writes the real one."""
    path = tmp_path / "headroom.json"
    monkeypatch.setattr("fpstune.settings.performance_headroom.HEADROOM_PATH", path, raising=True)
    return path


class TestTheQuestionItAnswers:
    def test_at_target_there_is_room_to_spend(self) -> None:
        h = PerformanceHeadroom("mw4", measured_fps=297.0, target_fps=297)
        assert h.has_headroom is True
        assert h.shortfall_percent is None

    def test_above_target_there_is_room(self) -> None:
        h = PerformanceHeadroom("mw4", measured_fps=320.0, target_fps=297)
        assert h.has_headroom is True

    def test_below_target_there_is_not(self) -> None:
        """The measured case that started this: 59 fps against a 300 Hz panel."""
        h = PerformanceHeadroom("mw4", measured_fps=59.0, target_fps=297)
        assert h.has_headroom is False
        assert h.shortfall_percent == 80

    def test_unmeasured_is_treated_as_no_room(self) -> None:
        """Silence is not evidence. A change that costs frames has to earn its
        recommendation, so the absence of a measurement cannot grant one."""
        assert PerformanceHeadroom("mw4").has_headroom is False
        assert PerformanceHeadroom("mw4", measured_fps=300.0).has_headroom is False
        assert PerformanceHeadroom("mw4", target_fps=297).has_headroom is False

    def test_a_missing_target_is_not_an_excuse_to_assume_one(self) -> None:
        """A panel whose refresh could not be read gives no target, and guessing
        60 there would recommend quality to a 240 Hz machine running at 90."""
        h = PerformanceHeadroom("mw4", measured_fps=90.0)
        assert h.is_measured is False
        assert h.has_headroom is False


class TestPersistence:
    @pytest.mark.usefixtures("state_dir")
    def test_a_recorded_measurement_reads_back(self) -> None:
        assert record_headroom(
            "mw4", measured_fps=312.5, target_fps=297, fps_1_percent_low=280.0, measured_at=NOW
        )

        h = read_headroom("mw4")
        assert h.measured_fps == 312.5
        assert h.target_fps == 297
        assert h.fps_1_percent_low == 280.0
        assert h.has_headroom is True

    @pytest.mark.usefixtures("state_dir")
    def test_each_game_is_measured_separately(self) -> None:
        """A machine that holds 300 fps in one title holds 60 in another, and a
        recommendation built from the wrong game's numbers is worse than none."""
        record_headroom("mw4", measured_fps=59.0, target_fps=297, measured_at=NOW)
        record_headroom("cs2", measured_fps=310.0, target_fps=297, measured_at=NOW)

        assert read_headroom("mw4").has_headroom is False
        assert read_headroom("cs2").has_headroom is True

    @pytest.mark.usefixtures("state_dir")
    def test_recording_one_game_does_not_erase_another(self) -> None:
        record_headroom("mw4", measured_fps=59.0, target_fps=297, measured_at=NOW)
        record_headroom("mw3", measured_fps=280.0, target_fps=297, measured_at=NOW)

        assert read_headroom("mw4").measured_fps == 59.0
        assert read_headroom("mw3").measured_fps == 280.0

    @pytest.mark.usefixtures("state_dir")
    def test_a_stale_measurement_stops_counting(self) -> None:
        """Drivers change and games patch. A recommendation built on an old
        number is the same defect as one built on a guess, only harder to spot."""
        record_headroom("mw4", measured_fps=310.0, target_fps=297, measured_at=NOW)

        fresh = read_headroom("mw4", now=NOW + MAX_AGE_SECONDS - 1)
        assert fresh.has_headroom is True

        stale = read_headroom("mw4", now=NOW + MAX_AGE_SECONDS + 1)
        assert stale.is_measured is False
        assert stale.has_headroom is False

    def test_an_absent_file_is_unmeasured_rather_than_an_error(self, state_dir) -> None:
        assert not state_dir.exists()
        assert read_headroom("mw4").has_headroom is False

    def test_a_corrupt_file_is_unmeasured_rather_than_a_crash(self, state_dir) -> None:
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text("{not json", encoding="utf-8")
        assert read_headroom("mw4").has_headroom is False

    @pytest.mark.usefixtures("state_dir")
    def test_a_nonsense_measurement_is_refused(self) -> None:
        assert record_headroom("mw4", measured_fps=0.0, target_fps=297, measured_at=NOW) is False
        assert record_headroom("mw4", measured_fps=100.0, target_fps=0, measured_at=NOW) is False
        assert read_headroom("mw4").is_measured is False

    def test_the_write_is_atomic(self, state_dir) -> None:
        """An interrupted write must not leave a half-file that reads as garbage."""
        record_headroom("mw4", measured_fps=310.0, target_fps=297, measured_at=NOW)
        assert json.loads(state_dir.read_text(encoding="utf-8"))["mw4"]["target_fps"] == 297
        assert list(state_dir.parent.glob("*.tmp")) == []


class TestTheRegistryActsOnIt:
    """The scoping is what the user sees; the reading above only informs it.

    The quality tiers below are the ones D1b lowered to their frames-first value.
    Two different things happen to them, and the band decides which: at target the
    value goes back up and the setting becomes a recommendation; below target the
    value stays frames-first and only its *scope* can move, so a frame the user
    did not ask for stops being hidden behind an opt-in.

    `render_resolution` is deliberately not in this list. Its recommendation is
    the game's own default, so promoting it would put a row in front of the user
    that asks them to apply the value they already have.
    """

    QUALITY_RAISES = (
        "game_config:mw4:dlss_perf_mode",
        "game_config:mw4:texture_quality",
        "game_config:mw4:model_quality",
    )

    @pytest.mark.usefixtures("state_dir")
    def test_below_target_the_value_stays_frames_first(self) -> None:
        """19% of target: nothing here may recommend a more expensive tier."""
        record_headroom("mw4", measured_fps=59.0, target_fps=297, measured_at=NOW)
        registry = SettingsRegistry()

        upscaler = registry.get("game_config:mw4:dlss_perf_mode")
        texture = registry.get("game_config:mw4:texture_quality")
        assert upscaler is not None and texture is not None
        assert upscaler.recommended_value == "Balanced"
        assert texture.recommended_value == "1"

    @pytest.mark.usefixtures("state_dir")
    def test_below_target_a_frame_buying_setting_stops_being_opt_in(self) -> None:
        """The band's own work: at 19% of target these are not a trade to offer,
        they are the answer, so the user should not have to go looking for them."""
        record_headroom(
            "mw4", measured_fps=59.0, target_fps=297, measured_at=NOW, bottleneck="both"
        )
        registry = SettingsRegistry()

        for setting_id in ("game_config:mw4:dlss_perf_mode", "game_config:mw4:texture_quality"):
            setting = registry.get(setting_id)
            assert setting is not None
            assert setting.scope is SettingScope.RECOMMENDED, setting_id

    @pytest.mark.usefixtures("state_dir")
    def test_at_target_they_are_recommended(self) -> None:
        """A machine already holding its panel's rate has frames going unused;
        turning them into image quality is what the ceiling means there."""
        record_headroom("mw4", measured_fps=300.0, target_fps=297, measured_at=NOW)
        registry = SettingsRegistry()

        for setting_id in self.QUALITY_RAISES:
            setting = registry.get(setting_id)
            assert setting is not None
            assert setting.scope is SettingScope.RECOMMENDED, setting_id

        # And the value moves with the scope: promoting a frames-first tier while
        # calling it a quality raise would be the scope saying one thing and the
        # value another.
        upscaler = registry.get("game_config:mw4:dlss_perf_mode")
        assert upscaler is not None
        assert upscaler.recommended_value == "Maximum Quality"

    @pytest.mark.usefixtures("state_dir")
    def test_unmeasured_changes_nothing_at_all(self) -> None:
        """Silence is not evidence — neither for spending frames nor for saving
        them. An unmeasured machine gets exactly what shipped."""
        registry = SettingsRegistry()

        for setting_id in self.QUALITY_RAISES:
            setting = registry.get(setting_id)
            assert setting is not None
            assert setting.scope is SettingScope.COMPLETE, setting_id

        upscaler = registry.get("game_config:mw4:dlss_perf_mode")
        assert upscaler is not None
        assert upscaler.recommended_value == "Balanced"

    @pytest.mark.usefixtures("state_dir")
    def test_settings_that_return_frames_are_never_held_back(self) -> None:
        """Headroom decides what quality *costs*. It has nothing to say about a
        setting that gives frames away for free, and must not gate one."""
        record_headroom("mw4", measured_fps=59.0, target_fps=297, measured_at=NOW)
        registry = SettingsRegistry()

        for setting_id in (
            "game_config:mw4:shader_quality",
            "game_config:mw4:volumetric_quality",
            "game_config:mw4:weather_grid",
            "game_config:mw4:motion_blur",
        ):
            setting = registry.get(setting_id)
            assert setting is not None
            assert setting.scope is SettingScope.RECOMMENDED, setting_id

    @pytest.mark.usefixtures("state_dir")
    def test_settings_that_cost_information_stay_opt_in_regardless(self) -> None:
        """Headroom is about frames. A setting that removes something the player
        reads is opt-in whether or not the machine is fast."""
        record_headroom("mw4", measured_fps=400.0, target_fps=297, measured_at=NOW)
        registry = SettingsRegistry()

        for setting_id in (
            "game_config:mw4:marks_player_only",
            "game_config:mw4:music_volume",
            "game_config:mw4:fov",
        ):
            setting = registry.get(setting_id)
            assert setting is not None
            assert setting.scope is SettingScope.COMPLETE, setting_id


class TestTheBands:
    """One threshold cannot express both "is quality affordable" and "how hard
    should this try". A machine at 95% of its panel needs a nudge; one at 19%
    needs everything the config can give."""

    @pytest.mark.parametrize(
        ("measured", "target", "expected"),
        [
            (300.0, 297, "met"),
            (297.0, 297, "met"),
            (280.0, 297, "near"),
            (253.0, 297, "near"),
            (200.0, 297, "short"),
            (149.0, 297, "short"),
            (57.4, 297, "critical"),
            (10.0, 297, "critical"),
        ],
    )
    def test_the_band_follows_the_fraction_of_target(
        self, measured: float, target: int, expected: str
    ) -> None:
        assert PerformanceHeadroom("mw4", measured_fps=measured, target_fps=target).tier == expected

    def test_the_bands_are_ratios_so_they_travel_between_panels(self) -> None:
        """Half of a 60 Hz panel and half of a 500 Hz panel are the same
        situation, and a band expressed in frames per second would not say so."""
        slow = PerformanceHeadroom("mw4", measured_fps=28.0, target_fps=57)
        fast = PerformanceHeadroom("mw4", measured_fps=245.0, target_fps=497)
        assert slow.tier == fast.tier == "critical"

    def test_unmeasured_has_no_band(self) -> None:
        h = PerformanceHeadroom("mw4")
        assert h.tier == "unknown"
        assert h.achievement is None
        assert h.has_headroom is False

    def test_the_measured_case_that_prompted_this(self) -> None:
        """MW4, live session, 679 frames: 57.4 fps against a 297 fps target."""
        h = PerformanceHeadroom("mw4", measured_fps=57.39, target_fps=297)
        assert h.tier == "critical"
        assert round(h.achievement * 100) == 19
        assert h.shortfall_percent == 81


class TestTheBottleneckIsCarriedSeparately:
    """How far short the machine fell and which side it waited on are different
    questions with different answers."""

    @pytest.mark.usefixtures("state_dir")
    def test_it_survives_a_round_trip(self) -> None:
        record_headroom(
            "mw4",
            measured_fps=57.39,
            target_fps=297,
            measured_at=NOW,
            bottleneck="both",
            cpu_busy_ms=17.177,
            gpu_time_ms=17.328,
            input_latency_ms=18.828,
            present_mode="Hardware: Independent Flip",
        )

        h = read_headroom("mw4")
        assert h.bottleneck == "both"
        assert h.cpu_busy_ms == 17.177
        assert h.gpu_time_ms == 17.328
        assert h.input_latency_ms == 18.828
        assert h.present_mode == "Hardware: Independent Flip"

    def test_an_old_record_without_it_still_reads(self, state_dir) -> None:
        """A measurement taken before the breakdown existed is still a valid
        frame rate; it just has no verdict about where the time went."""
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text(
            json.dumps({"mw4": {"measured_fps": 300.0, "target_fps": 297, "measured_at": NOW}}),
            encoding="utf-8",
        )

        h = read_headroom("mw4")
        assert h.has_headroom is True
        assert h.bottleneck == "unknown"
        assert h.cpu_busy_ms is None
        assert h.present_mode is None

    @pytest.mark.usefixtures("state_dir")
    def test_the_bottleneck_does_not_decide_whether_quality_is_affordable(self) -> None:
        """A GPU-bound machine at target has room; a GPU-bound machine below it
        does not. The verdict about where time went cannot answer that."""
        for bottleneck in ("gpu", "cpu", "both", "unknown"):
            record_headroom(
                "mw4", measured_fps=57.0, target_fps=297, measured_at=NOW, bottleneck=bottleneck
            )
            assert read_headroom("mw4").has_headroom is False

            record_headroom(
                "mw4", measured_fps=300.0, target_fps=297, measured_at=NOW, bottleneck=bottleneck
            )
            assert read_headroom("mw4").has_headroom is True
