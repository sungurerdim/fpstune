"""Tests for scoping quality raises by what the machine actually reaches.

The defect this exists to prevent shipped once: fpstune recommended a sharper
image to a system running at a fifth of its display's refresh. Measured on that
machine — 59 fps against a 300 Hz panel — the raises it recommended would have
cost roughly half of the frame rate that was already short.

The reading is one band for the machine, taken from `benchmark.gpu_scene`'s
fixed scene. It used to be one per game, captured from whatever match happened
to be running, and that had two costs the owner's decision of 2026-09-11 settled
against: a machine with no game open never got a band at all, and two captures
of two firefights are two different workloads, so one title could report two
bands in an hour.

Nothing here reads the developer's machine or the real state directory.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from fpstune.benchmark.suite import BenchReading, BenchResult
from fpstune.settings.base import SettingScope
from fpstune.settings.performance_headroom import (
    BUSY,
    MAX_AGE_SECONDS,
    MEASURE_FAILED,
    MEASURED,
    PANEL_UNKNOWN,
    SCENE_UNAVAILABLE,
    PerformanceHeadroom,
    measure_now,
    read_headroom,
    record_headroom,
    record_scene_result,
)
from fpstune.settings.registry import SettingsRegistry

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Point the state file at a temp dir so no test reads or writes the real one."""
    path = tmp_path / "headroom.json"
    monkeypatch.setattr("fpstune.settings.performance_headroom.HEADROOM_PATH", path, raising=True)
    return path


def scene_result(
    averages: list[float],
    *,
    lows: list[float] | None = None,
    detail: dict[str, Any] | None = None,
) -> BenchResult:
    """A `gpu_scene` result shaped the way the bench actually returns one."""
    readings = {"fps_avg": BenchReading("fps_avg", averages, "fps", higher_is_better=True)}
    if lows is not None:
        readings["fps_1_percent_low"] = BenchReading("fps_1_percent_low", lows, "fps")
    return BenchResult(
        bench="gpu_scene",
        label="GPU scene",
        ran=True,
        readings=readings,
        detail=detail if detail is not None else {},
    )


class TestTheQuestionItAnswers:
    def test_at_target_there_is_room_to_spend(self) -> None:
        h = PerformanceHeadroom(measured_fps=297.0, target_fps=297)
        assert h.has_headroom is True
        assert h.shortfall_percent is None

    def test_above_target_there_is_room(self) -> None:
        h = PerformanceHeadroom(measured_fps=320.0, target_fps=297)
        assert h.has_headroom is True

    def test_below_target_there_is_not(self) -> None:
        """The measured case that started this: 59 fps against a 300 Hz panel."""
        h = PerformanceHeadroom(measured_fps=59.0, target_fps=297)
        assert h.has_headroom is False
        assert h.shortfall_percent == 80

    def test_unmeasured_is_treated_as_no_room(self) -> None:
        """Silence is not evidence. A change that costs frames has to earn its
        recommendation, so the absence of a measurement cannot grant one."""
        assert PerformanceHeadroom().has_headroom is False
        assert PerformanceHeadroom(measured_fps=300.0).has_headroom is False
        assert PerformanceHeadroom(target_fps=297).has_headroom is False

    def test_a_missing_target_is_not_an_excuse_to_assume_one(self) -> None:
        """A panel whose refresh could not be read gives no target, and guessing
        60 there would recommend quality to a 240 Hz machine running at 90."""
        h = PerformanceHeadroom(measured_fps=90.0)
        assert h.is_measured is False
        assert h.has_headroom is False


class TestPersistence:
    @pytest.mark.usefixtures("state_dir")
    def test_a_recorded_measurement_reads_back(self) -> None:
        assert record_headroom(
            measured_fps=312.5, target_fps=297, fps_1_percent_low=280.0, measured_at=NOW
        )

        h = read_headroom()
        assert h.measured_fps == 312.5
        assert h.target_fps == 297
        assert h.fps_1_percent_low == 280.0
        assert h.has_headroom is True

    @pytest.mark.usefixtures("state_dir")
    def test_the_newest_measurement_replaces_the_last_one(self) -> None:
        """One current answer for this machine, and no archive. A second run on
        a re-tuned machine has to be the answer, not an entry beside the old
        one that a reader has to date-sort."""
        record_headroom(measured_fps=59.0, target_fps=297, measured_at=NOW)
        record_headroom(measured_fps=197.0, target_fps=297, measured_at=NOW + 60)

        assert read_headroom().measured_fps == 197.0

    @pytest.mark.usefixtures("state_dir")
    def test_a_stale_measurement_stops_counting(self) -> None:
        """Drivers change and panels get swapped. A recommendation built on an
        old number is the same defect as one built on a guess, only harder to
        spot."""
        record_headroom(measured_fps=310.0, target_fps=297, measured_at=NOW)

        fresh = read_headroom(now=NOW + MAX_AGE_SECONDS - 1)
        assert fresh.has_headroom is True

        stale = read_headroom(now=NOW + MAX_AGE_SECONDS + 1)
        assert stale.is_measured is False
        assert stale.has_headroom is False

    def test_an_absent_file_is_unmeasured_rather_than_an_error(self, state_dir) -> None:
        assert not state_dir.exists()
        assert read_headroom().has_headroom is False

    def test_a_corrupt_file_is_unmeasured_rather_than_a_crash(self, state_dir) -> None:
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text("{not json", encoding="utf-8")
        assert read_headroom().has_headroom is False

    def test_a_file_from_the_per_game_build_reads_as_unmeasured(self, state_dir) -> None:
        """A machine upgrading from the in-game capture has `{"mw4": {...}}` on
        disk. It carries no machine-wide reading, so it must produce none —
        silently reusing a game's number as the machine's would be a band from a
        load nothing here ran, and the conservative answer costs one scene run.
        """
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text(
            json.dumps({"mw4": {"measured_fps": 300.0, "target_fps": 297, "measured_at": NOW}}),
            encoding="utf-8",
        )

        h = read_headroom()
        assert h.is_measured is False
        assert h.has_headroom is False

    def test_the_next_write_clears_what_the_old_shape_left(self, state_dir) -> None:
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text(json.dumps({"mw4": {"measured_fps": 300.0}}), encoding="utf-8")

        record_headroom(measured_fps=197.0, target_fps=297, measured_at=NOW)

        assert "mw4" not in json.loads(state_dir.read_text(encoding="utf-8"))
        assert read_headroom().measured_fps == 197.0

    @pytest.mark.usefixtures("state_dir")
    def test_a_nonsense_measurement_is_refused(self) -> None:
        assert record_headroom(measured_fps=0.0, target_fps=297, measured_at=NOW) is False
        assert record_headroom(measured_fps=100.0, target_fps=0, measured_at=NOW) is False
        assert read_headroom().is_measured is False

    def test_the_write_is_atomic(self, state_dir) -> None:
        """An interrupted write must not leave a half-file that reads as garbage."""
        record_headroom(measured_fps=310.0, target_fps=297, measured_at=NOW)
        assert json.loads(state_dir.read_text(encoding="utf-8"))["target_fps"] == 297
        assert list(state_dir.parent.glob("*.tmp")) == []


class TestTheSceneResultBecomesTheBand:
    """`gpu_scene` produces the reading, and the translation is where it can go
    wrong quietly: the wrong window, or a bottleneck nobody measured."""

    @pytest.mark.usefixtures("state_dir")
    def test_the_band_is_the_median_of_the_runs_own_windows(self) -> None:
        """The live run of 2026-09-11 produced 219 / 197 / 188 fps from three
        windows of one flythrough — the windows see different parts of the
        scene. Taking the first would make the band depend on which second of
        the scene the capture happened to open on."""
        assert record_scene_result(
            scene_result([219.0, 197.0, 188.0]), target_fps=297, measured_at=NOW
        )

        assert read_headroom().measured_fps == 197.0

    @pytest.mark.usefixtures("state_dir")
    def test_a_scene_that_reported_no_side_says_unknown_rather_than_guessing(self) -> None:
        """PresentMon publishes a GPU/CPU split only for a run it could
        attribute. Naming a side the scene never established would move
        frame-buying settings on a guess."""
        record_scene_result(scene_result([197.0]), target_fps=297, measured_at=NOW)

        assert read_headroom().bottleneck == "unknown"

    @pytest.mark.usefixtures("state_dir")
    def test_a_scene_that_did_report_a_side_keeps_it(self) -> None:
        record_scene_result(
            scene_result([197.0], detail={"bottleneck": "gpu"}), target_fps=297, measured_at=NOW
        )

        assert read_headroom().bottleneck == "gpu"

    @pytest.mark.usefixtures("state_dir")
    def test_the_resolution_it_rendered_at_is_kept_with_the_number(self) -> None:
        """The band compares a frame rate to the panel's own ceiling, so it only
        means anything if the load was the panel's own resolution (C9)."""
        record_scene_result(
            scene_result(
                [197.0],
                lows=[120.0],
                detail={
                    "width": 2560,
                    "height": 1440,
                    "present_mode": "Composed: Copy with GPU GDI",
                },
            ),
            target_fps=297,
            measured_at=NOW,
        )

        h = read_headroom()
        assert (h.width, h.height) == (2560, 1440)
        assert h.fps_1_percent_low == 120.0
        assert h.present_mode == "Composed: Copy with GPU GDI"

    @pytest.mark.usefixtures("state_dir")
    def test_a_bench_that_did_not_run_records_nothing(self) -> None:
        """`ran=False` carries a reason and no readings (C11 rule 3). Writing a
        band from it would turn "we could not check" into a measurement."""
        refused = BenchResult(
            bench="gpu_scene", label="GPU scene", ran=False, reason="a game is running"
        )

        assert record_scene_result(refused, target_fps=297, measured_at=NOW) is False
        assert read_headroom().is_measured is False


class TestMeasuringOnDemand:
    """The UI's button. Every refusal is named, because "install the scene" and
    "close the game first" are different instructions to the person waiting."""

    @pytest.fixture
    def bench(self, monkeypatch):
        """A stand-in engine, and the lock taken, unless a test says otherwise."""

        class FakeBench:
            available: tuple[bool, str] = (True, "")
            result: BenchResult = scene_result([219.0, 197.0, 188.0])
            samples: int | None = None

            def __init__(self, **kwargs: Any) -> None:
                FakeBench.kwargs = kwargs

            def is_available(self) -> tuple[bool, str]:
                return FakeBench.available

            def run(self, repeats: int) -> BenchResult:
                FakeBench.samples = repeats
                return FakeBench.result

        import contextlib

        @contextlib.contextmanager
        def taken(*_args: Any, **_kwargs: Any):
            yield True

        monkeypatch.setattr("fpstune.benchmark.gpu_scene.GpuSceneBench", FakeBench)
        monkeypatch.setattr("fpstune.benchmark.operation_lock.operation_lock", taken)
        monkeypatch.setattr("fpstune.settings.performance_headroom.panel_target_fps", lambda: 297)
        return FakeBench

    @pytest.mark.usefixtures("bench")
    def test_a_successful_run_is_recorded_and_reported(self) -> None:
        outcome = measure_now(now=NOW)

        assert outcome.outcome == MEASURED
        assert outcome.measured is True
        assert "297 fps target" in outcome.detail
        assert outcome.headroom is not None
        assert outcome.headroom.measured_fps == 197.0
        assert read_headroom().measured_fps == 197.0

    def test_it_asks_for_several_windows_so_a_noise_floor_exists(self, bench) -> None:
        """One window is one sample, and `verify_round` gives a single sample an
        infinite noise floor on purpose (C11 rule 2)."""
        measure_now(now=NOW)

        assert bench.samples is not None and bench.samples >= 2

    def test_it_never_spends_the_download_on_the_users_behalf(self, bench) -> None:
        """1.3 GB is a decision made once, on its own screen — not something a
        "measure now" press starts."""
        measure_now(now=NOW)

        assert bench.kwargs["allow_download"] is False

    @pytest.mark.usefixtures("bench")
    def test_a_panel_that_reports_no_refresh_is_named_rather_than_guessed(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr("fpstune.settings.performance_headroom.panel_target_fps", lambda: None)

        outcome = measure_now(now=NOW)

        assert outcome.outcome == PANEL_UNKNOWN
        assert outcome.measured is False

    def test_the_scenes_own_refusal_is_passed_through_verbatim(self, bench) -> None:
        """ "Not installed, and that is a 1.3 GB download" is the sentence the
        user has to act on, and paraphrasing it here would lose the size."""
        bench.available = (
            False,
            "Unigine Superposition Basic is not installed; installing it is a "
            "1.3 GB download, which fpstune never starts on its own.",
        )

        outcome = measure_now(now=NOW)

        assert outcome.outcome == SCENE_UNAVAILABLE
        assert "1.3 GB" in outcome.detail

    @pytest.mark.usefixtures("bench")
    def test_it_refuses_while_another_operation_holds_the_lock(self, monkeypatch) -> None:
        """An apply, a cleanup and a bench must never overlap: the scene renders
        at full speed and would measure a machine halfway between two states."""
        import contextlib

        @contextlib.contextmanager
        def refused(*_args: Any, **_kwargs: Any):
            yield False

        monkeypatch.setattr("fpstune.benchmark.operation_lock.operation_lock", refused)

        outcome = measure_now(now=NOW)

        assert outcome.outcome == BUSY
        assert read_headroom().is_measured is False

    def test_presentmons_own_refusal_is_translated_into_something_fixable(self, bench) -> None:
        """Measured live on 2026-08-25: an unelevated capture cannot open an ETW
        session, and the product reported "it may have been in a menu" over the
        top of it — a fixable problem told as an unfixable one."""
        bench.result = BenchResult(
            bench="gpu_scene",
            label="GPU scene",
            ran=False,
            reason=(
                "the frame capture would not start: error: failed to start trace session: "
                "access denied. PresentMon requires either administrative privileges"
            ),
        )

        outcome = measure_now(now=NOW)

        assert outcome.outcome == MEASURE_FAILED
        assert "administrator" in outcome.detail.lower()
        assert "menu" not in outcome.detail.lower()

    def test_a_failed_run_keeps_the_last_reading_on_screen(self, bench) -> None:
        """Losing a number because the newest attempt declined is strictly less
        information than the old number plus the reason."""
        record_headroom(measured_fps=197.0, target_fps=297, measured_at=NOW)
        bench.result = BenchResult(
            bench="gpu_scene",
            label="GPU scene",
            ran=False,
            reason="the scene engine would not start",
        )

        outcome = measure_now(now=NOW)

        assert outcome.measured is False
        assert outcome.headroom is not None
        assert outcome.headroom.measured_fps == 197.0


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
        record_headroom(measured_fps=59.0, target_fps=297, measured_at=NOW)
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
        record_headroom(measured_fps=59.0, target_fps=297, measured_at=NOW, bottleneck="both")
        registry = SettingsRegistry()

        for setting_id in ("game_config:mw4:dlss_perf_mode", "game_config:mw4:texture_quality"):
            setting = registry.get(setting_id)
            assert setting is not None
            assert setting.scope is SettingScope.RECOMMENDED, setting_id

    @pytest.mark.usefixtures("state_dir")
    def test_one_band_reaches_every_games_rules(self) -> None:
        """The scene measures the machine, not a title, so a machine at its
        ceiling has frames to spend in MW3 as well as MW4 — and before this the
        MW3 rules only ever fired if MW3 itself had been captured."""
        record_headroom(measured_fps=300.0, target_fps=297, measured_at=NOW)
        registry = SettingsRegistry()

        mw3 = registry.get("game_config:mw3:dlss_perf_mode")
        mw4 = registry.get("game_config:mw4:dlss_perf_mode")
        assert mw3 is not None and mw4 is not None
        assert mw3.recommended_value == "Maximum Quality"
        assert mw4.recommended_value == "Maximum Quality"

    @pytest.mark.usefixtures("state_dir")
    def test_at_target_they_are_recommended(self) -> None:
        """A machine already holding its panel's rate has frames going unused;
        turning them into image quality is what the ceiling means there."""
        record_headroom(measured_fps=300.0, target_fps=297, measured_at=NOW)
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
        record_headroom(measured_fps=59.0, target_fps=297, measured_at=NOW)
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
        record_headroom(measured_fps=400.0, target_fps=297, measured_at=NOW)
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
        assert PerformanceHeadroom(measured_fps=measured, target_fps=target).tier == expected

    def test_the_bands_are_ratios_so_they_travel_between_panels(self) -> None:
        """Half of a 60 Hz panel and half of a 500 Hz panel are the same
        situation, and a band expressed in frames per second would not say so."""
        slow = PerformanceHeadroom(measured_fps=28.0, target_fps=57)
        fast = PerformanceHeadroom(measured_fps=245.0, target_fps=497)
        assert slow.tier == fast.tier == "critical"

    def test_unmeasured_has_no_band(self) -> None:
        h = PerformanceHeadroom()
        assert h.tier == "unknown"
        assert h.achievement is None
        assert h.has_headroom is False

    def test_the_scene_measured_on_this_machine(self) -> None:
        """The live product run of 2026-09-11: fps_avg median 197 over windows of
        219 / 197 / 188, against this panel's 297 fps target."""
        h = PerformanceHeadroom(measured_fps=197.0, target_fps=297)
        assert h.tier == "short"
        assert round(h.achievement * 100) == 66
        assert h.shortfall_percent == 34


class TestTheBottleneckIsCarriedSeparately:
    """How far short the machine fell and which side it waited on are different
    questions with different answers."""

    @pytest.mark.usefixtures("state_dir")
    def test_it_survives_a_round_trip(self) -> None:
        record_headroom(
            measured_fps=197.0,
            target_fps=297,
            measured_at=NOW,
            bottleneck="gpu",
            present_mode="Hardware: Independent Flip",
            width=2560,
            height=1440,
        )

        h = read_headroom()
        assert h.bottleneck == "gpu"
        assert h.present_mode == "Hardware: Independent Flip"
        assert (h.width, h.height) == (2560, 1440)

    def test_a_record_without_it_still_reads(self, state_dir) -> None:
        """A measurement with no side attributed is still a valid frame rate; it
        just has no verdict about where the time went."""
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        state_dir.write_text(
            json.dumps({"measured_fps": 300.0, "target_fps": 297, "measured_at": NOW}),
            encoding="utf-8",
        )

        h = read_headroom()
        assert h.has_headroom is True
        assert h.bottleneck == "unknown"
        assert h.present_mode is None

    @pytest.mark.usefixtures("state_dir")
    def test_the_bottleneck_does_not_decide_whether_quality_is_affordable(self) -> None:
        """A GPU-bound machine at target has room; a GPU-bound machine below it
        does not. The verdict about where time went cannot answer that."""
        for bottleneck in ("gpu", "cpu", "both", "unknown"):
            record_headroom(
                measured_fps=57.0, target_fps=297, measured_at=NOW, bottleneck=bottleneck
            )
            assert read_headroom().has_headroom is False

            record_headroom(
                measured_fps=300.0, target_fps=297, measured_at=NOW, bottleneck=bottleneck
            )
            assert read_headroom().has_headroom is True
