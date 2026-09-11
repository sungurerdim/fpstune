"""The GPU scene bench, without the 1.3 GB engine and without a graphics card.

Nothing here starts Unigine Superposition. What is tested is everything around
it that decided, on the machine where this was measured, whether the number at
the end was a frame rate or a level load:

* the argument list, which is the vendor's own vocabulary and one flag away from
  a benchmark that pauses whenever anything else takes focus;
* the resolution, which has to come off the panel and never out of the source;
* the wait for the engine's own "Benchmark running" line, because the frames
  before it are a loading screen — an early capture reported 278 fps with a 1%
  low of 1.06 and a five-second frame in it;
* the install, which downloads an elevated installer and must refuse to run one
  whose hash does not match;
* and the ending, because the engine never exits on its own and PresentMon stops
  recording the moment the process it traces goes away.

The one thing not stubbed is the arithmetic: the fake capture tool is a real
`PresentMonBenchmark` with its IO replaced, so "the average of the slowest one
percent of frames" is computed here by the same code that computes it for a real
game.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fpstune.benchmark import gpu_scene
from fpstune.benchmark.gpu_scene import (
    DOWNLOAD_SIZE,
    INSTALLER_BYTES,
    INSTALLER_SHA256,
    RUNNING_MARKER,
    GpuSceneBench,
    fps_readings,
    log_tail,
)
from fpstune.benchmark.presentmon import FrameTimeStats, PresentMonBenchmark
from fpstune.benchmark.suite import Bench, SpawnsProcess
from fpstune.utils.detect import MonitorInfo

# A panel that is not the one this was written on, and a second one that is not
# primary — so a bench reading "the first monitor" instead of "the primary one"
# fails rather than passes by coincidence.
PANEL_WIDTH = 1920
PANEL_HEIGHT = 1080


def _monitors() -> list[MonitorInfo]:
    return [
        MonitorInfo(
            name="\\\\.\\DISPLAY2",
            width=3840,
            height=2160,
            refresh_rate_hz=60,
            is_primary=False,
        ),
        MonitorInfo(
            name="\\\\.\\DISPLAY1",
            width=PANEL_WIDTH,
            height=PANEL_HEIGHT,
            refresh_rate_hz=240,
            is_primary=True,
        ),
    ]


def _frametimes(count: int = 600, fast: bool = False) -> list[float]:
    """Frame times a card plausibly produced on a fixed scene, in milliseconds.

    Deterministic, because two runs of this test have to compare the same work —
    the same reason the bench renders one scene rather than a random one.
    """
    base = 2.3 if fast else 4.6
    return [base + (index % 11) * 0.15 for index in range(count)]


def _timestamps(frametimes: list[float]) -> list[float]:
    elapsed = 0.0
    stamps = []
    for frametime in frametimes:
        stamps.append(elapsed)
        elapsed += frametime
    return stamps


class _FakeEngine:
    """The engine process: a pid, a liveness answer, and a script for the log.

    `poll` is where the log grows, because `poll` is what the wait loop calls
    once per pass — so "the marker appeared on the fourth poll" is a fact the
    test states rather than a race it hopes for.
    """

    def __init__(
        self,
        *,
        log: Path,
        writes: dict[int, str] | None = None,
        exits_after_polls: int | None = None,
    ) -> None:
        self.pid = 4242
        self.polls = 0
        self.log = log
        self.writes = (
            {3: f'<div class="m">12:41:13 {RUNNING_MARKER}</div>'} if writes is None else writes
        )
        self.exits_after_polls = exits_after_polls
        self.returncode: int | None = None

    def poll(self) -> int | None:
        self.polls += 1
        line = self.writes.pop(self.polls, None)
        if line is not None:
            with open(self.log, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if self.exits_after_polls is not None and self.polls >= self.exits_after_polls:
            self.returncode = 0
        return self.returncode


class _FakePresentMon(PresentMonBenchmark):
    """A real PresentMon with its process and its file replaced.

    Subclassed rather than mocked so `_calculate_stats` — the definition of a 1%
    low that the whole product shares — is the real one. Only the four calls
    that touch a process or the disk are overridden.
    """

    def __init__(self, data_dir: Path, events: list[str], log: Path) -> None:
        super().__init__(data_dir=data_dir)
        self.events = events
        self.log = log
        self.log_when_capture_started: str | None = None
        self.capture_calls: list[dict[str, Any]] = []
        self.frametimes: list[float] | None = _frametimes()
        self.capture_started = True
        self.capture_file: Path | None = data_dir / "gpu_scene.csv"
        self.waited_for = 0.0

    def start_capture(
        self,
        process_name: str | None = None,
        output_name: str | None = None,
        duration_seconds: int = 0,
    ) -> bool:
        self.capture_calls.append(
            {
                "process_name": process_name,
                "output_name": output_name,
                "duration_seconds": duration_seconds,
            }
        )
        try:
            self.log_when_capture_started = self.log.read_text(encoding="utf-8")
        except OSError:
            self.log_when_capture_started = ""
        self.events.append("capture_started")
        return self.capture_started

    def wait_for_capture(self, timeout: float) -> bool:
        self.waited_for = timeout
        self.events.append("capture_waited")
        return True

    def stop_capture(self) -> Path | None:
        self.events.append("capture_stopped")
        if self.capture_file is not None:
            self.capture_file.write_text("csv", encoding="utf-8")
        return self.capture_file

    def analyze_capture(self, capture_file: Path) -> FrameTimeStats | None:
        if not capture_file.exists() or self.frametimes is None:
            return None
        stats = self._calculate_stats(list(self.frametimes), _timestamps(self.frametimes))
        stats.present_mode = "Composed: Copy with GPU GDI"
        return stats


class _Harness:
    """Everything the bench talks to, replaced and recorded."""

    def __init__(self, bench: GpuSceneBench, engine: _FakeEngine) -> None:
        self.bench = bench
        self.engine = engine
        self.spawned: list[tuple[list[str], Path]] = []
        self.killed: list[int] = []
        self.downloads: list[tuple[str, Path]] = []
        self.installer_runs: list[list[str]] = []
        self.events: list[str] = []

    @property
    def presentmon(self) -> _FakePresentMon:
        assert isinstance(self.bench._presentmon, _FakePresentMon)
        return self.bench._presentmon

    @property
    def engine_args(self) -> list[str]:
        assert self.spawned, "the engine was never started"
        return self.spawned[0][0]


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    log = tmp_path / "log.html"
    events: list[str] = []
    presentmon = _FakePresentMon(tmp_path / "pm", events, log)

    bench = GpuSceneBench(
        data_dir=tmp_path,
        seconds_per_sample=1.0,
        settle_seconds=0.0,
        load_budget_seconds=1.0,
        poll_seconds=0.0,
        presentmon=presentmon,
        log_path=log,
    )
    bench.bin_dir.mkdir(parents=True, exist_ok=True)
    bench.engine_path.write_text("engine", encoding="utf-8")

    engine = _FakeEngine(log=log)
    built = _Harness(bench, engine)

    def _spawn(args: list[str], cwd: Path) -> Any:
        built.spawned.append((args, cwd))
        built.events.append("engine_spawned")
        events.append("engine_spawned")
        return engine

    def _kill(pid: int) -> None:
        built.killed.append(pid)
        engine.returncode = 1
        built.events.append("killed")
        events.append("killed")

    def _download(url: str, destination: Path) -> None:
        built.downloads.append((url, destination))
        destination.write_bytes(b"not the real installer")

    def _installer(args: list[str]) -> int:
        built.installer_runs.append(args)
        return 0

    monkeypatch.setattr(gpu_scene, "_spawn_engine", _spawn)
    monkeypatch.setattr(gpu_scene, "_kill_tree", _kill)
    monkeypatch.setattr(gpu_scene, "_download", _download)
    monkeypatch.setattr(gpu_scene, "_run_installer", _installer)
    monkeypatch.setattr(gpu_scene, "running_game_label", lambda: None)
    monkeypatch.setattr(gpu_scene.sys, "platform", "win32")
    monkeypatch.setattr(
        "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
        lambda **_kwargs: _monitors(),
    )
    built.events = events
    return built


class TestTheCommandLineIsTheOneThatWasMeasured:
    def test_it_is_the_argument_list_the_engine_answered_to(self, harness: _Harness) -> None:
        """The vocabulary is `superposition_cli.exe`'s own printf templates, not
        an invention — so it is asserted whole rather than flag by flag."""
        assert harness.bench.engine_command(2560, 1440) == [
            str(harness.bench.engine_path),
            "-project_name",
            "Superposition",
            "-video_mode",
            "-1",
            "-console_command",
            "world_load superposition/superposition",
            "-extern_plugin",
            "GPUMonitor",
            "-preset",
            "0",
            "-batch",
            "1",
            "-video_app",
            "direct3d11",
            "-video_fullscreen",
            "0",
            "-video_width",
            "2560",
            "-video_height",
            "1440",
            "-shaders_quality",
            "0",
            "-textures_quality",
            "0",
            "-dof",
            "0",
            "-motion_blur",
            "0",
            "-sound",
            "0",
            "-mode",
            "0",
            "-iteration",
            "1",
            "-log_step",
            "0",
        ]

    def test_fullscreen_is_never_asked_for(self, harness: _Harness) -> None:
        """Measured twice: fullscreen pauses the scene the moment the window
        loses focus, and it loses it to anything at all. A run that pauses
        reports the frames it drew before the pause as a result."""
        command = harness.bench.engine_command(2560, 1440)

        assert command[command.index("-video_fullscreen") + 1] == "0"

    def test_the_resolution_comes_off_the_panel(self, harness: _Harness) -> None:
        """C9. A constant here measures a 1080p machine at somebody else's
        1440p and reports the difference as a result."""
        harness.bench.run(2)

        args = harness.engine_args
        assert args[args.index("-video_width") + 1] == str(PANEL_WIDTH)
        assert args[args.index("-video_height") + 1] == str(PANEL_HEIGHT)

    def test_the_panel_is_the_primary_one_not_the_first_one(self, harness: _Harness) -> None:
        """The other display in the fixture is larger and comes first."""
        harness.bench.run(2)

        assert "3840" not in harness.engine_args

    def test_the_engine_runs_from_its_own_directory(self, harness: _Harness) -> None:
        """It resolves its data paths against the working directory, so started
        from ours it finds no scene to load."""
        harness.bench.run(2)

        assert harness.spawned[0][1] == harness.bench.bin_dir

    def test_no_display_means_no_measurement(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda **_kwargs: [],
        )

        result = harness.bench.run(2)

        assert result.ran is False
        assert "no active display" in result.reason
        assert not harness.spawned


class TestWaitingForTheSceneToStart:
    def test_the_capture_does_not_start_before_the_log_says_it_is_running(
        self, harness: _Harness
    ) -> None:
        """The frames before that line are a level load. Capturing them produced
        an `fps_avg` of 278 with a 1% low of 1.06 — a loading screen wearing a
        frame rate's name."""
        harness.bench.run(2)

        started_with = harness.presentmon.log_when_capture_started
        assert started_with is not None
        assert RUNNING_MARKER in started_with

    def test_a_marker_left_by_the_last_run_does_not_count(self, harness: _Harness) -> None:
        """The log is deleted before the launch. Without that the wait returns
        on the first pass, every time, and every capture is of a level load."""
        harness.bench.log_path.write_text(
            f'<div class="m">11:00:00 {RUNNING_MARKER}</div>\n', encoding="utf-8"
        )

        harness.bench.run(2)

        # The engine's own marker is written on the third poll, so a run that
        # respected the stale one would have polled fewer times than that.
        assert harness.engine.polls >= 3

    def test_the_capture_traces_the_engine_and_stops_on_its_own_clock(
        self, harness: _Harness
    ) -> None:
        harness.bench.run(3)

        call = harness.presentmon.capture_calls[0]
        assert call["process_name"] == "superposition.exe"
        assert call["duration_seconds"] == 3  # one second per sample, three samples

    def test_an_engine_that_exits_first_reports_what_the_log_said(self, harness: _Harness) -> None:
        """There is no stderr to read — the engine's account of why it would not
        start is in that file and nowhere else."""
        harness.engine.writes = {
            1: '<div class="m">12:40:58 Set 1920x1080 windowed video mode</div>\n'
            '<div class="m">12:40:59 Can&#39;t open &quot;superposition/superposition&quot;</div>'
        }
        harness.engine.exits_after_polls = 1

        result = harness.bench.run(2)

        assert result.ran is False
        assert "exited before it started rendering" in result.reason
        assert 'Can\'t open "superposition/superposition"' in result.reason
        assert not harness.presentmon.capture_calls

    def test_a_scene_that_never_starts_is_given_up_on_and_killed(self, harness: _Harness) -> None:
        harness.engine.writes = {}

        result = harness.bench.run(2)

        assert result.ran is False
        assert "did not start rendering" in result.reason
        assert harness.killed == [harness.engine.pid]

    def test_the_reason_survives_an_empty_log(self, harness: _Harness) -> None:
        """A bench that did not run has to say why, whatever the engine left
        behind — `BenchResult` refuses an empty reason outright."""
        harness.engine.writes = {}

        result = harness.bench.run(2)

        assert result.reason.strip()


class TestTheEngineIsAlwaysLetGo:
    def test_the_tree_is_killed_after_the_capture_and_not_before(self, harness: _Harness) -> None:
        """PresentMon is started with `--terminate_on_proc_exit`, so killing the
        engine first ends the recording early and the last window is short."""
        harness.bench.run(2)

        assert harness.events.index("capture_stopped") < harness.events.index("killed")

    def test_it_is_killed_as_a_tree(self, harness: _Harness) -> None:
        """A child left holding the card is what the next bench would measure."""
        harness.bench.run(2)

        assert harness.killed == [harness.engine.pid]

    def test_a_capture_that_will_not_start_still_lets_the_engine_go(
        self, harness: _Harness
    ) -> None:
        harness.presentmon.capture_started = False
        harness.presentmon.last_error = "access denied"

        result = harness.bench.run(2)

        assert result.ran is False
        assert "access denied" in result.reason
        assert harness.killed == [harness.engine.pid]

    def test_terminate_child_stops_the_scene_for_a_caller_that_gave_up(
        self, harness: _Harness
    ) -> None:
        """`suite.SpawnsProcess`, called after a missed deadline. Without it the
        scene keeps rendering at full speed behind the rest of the run."""
        harness.bench._engine = harness.engine  # type: ignore[assignment]

        harness.bench.terminate_child()

        assert harness.killed == [harness.engine.pid]


class TestTheReadings:
    def test_it_produces_the_three_frame_rate_readings(self, harness: _Harness) -> None:
        result = harness.bench.run(2)

        assert result.ran is True, result.reason
        assert set(result.readings) == {"fps_avg", "fps_1_percent_low", "fps_0_1_percent_low"}

    def test_one_sample_per_repeat(self, harness: _Harness) -> None:
        """`noise_floor` is infinite on one sample, so a run that returned a
        single number could never be called a change in either direction."""
        result = harness.bench.run(3)

        for reading in result.readings.values():
            assert len(reading.samples) == 3

    def test_the_noise_floor_is_a_number_rather_than_infinity(self, harness: _Harness) -> None:
        result = harness.bench.run(2)

        assert result.readings["fps_avg"].noise < float("inf")

    def test_fps_avg_knows_which_way_is_better(self, harness: _Harness) -> None:
        """`verify_round` does not know the name — it knows `fps`, which belongs
        to a capture of a real game — so this reading declares its own direction
        or gets no verdict at all."""
        result = harness.bench.run(2)

        assert result.readings["fps_avg"].improves_upward is True
        assert result.readings["fps_1_percent_low"].improves_upward is True

    def test_each_window_is_scored_on_its_own_frames(self, harness: _Harness) -> None:
        """Two halves at two different speeds have to come back as two different
        samples. Scoring the whole capture and repeating the answer would give a
        noise floor of zero, and a noise floor of zero calls everything a win."""
        slow = _frametimes(300)
        fast = _frametimes(300, fast=True)
        harness.presentmon.frametimes = slow + fast

        result = harness.bench.run(2)

        first, second = result.readings["fps_avg"].samples
        assert second > first * 1.5

    def test_the_detail_carries_the_run_a_reader_would_ask_about(self, harness: _Harness) -> None:
        result = harness.bench.run(2)

        assert result.detail["width"] == PANEL_WIDTH
        assert result.detail["height"] == PANEL_HEIGHT
        assert result.detail["present_mode"] == "Composed: Copy with GPU GDI"
        assert result.detail["frame_count"] == 600
        assert result.detail["load_seconds"] >= 0

    def test_a_capture_with_too_few_frames_is_not_a_measurement(self, harness: _Harness) -> None:
        """A handful of frames is a capture of something going wrong — the
        window minimised, the wrong process traced — and averaging six of them
        into an `fps_avg` publishes that as a result."""
        harness.presentmon.frametimes = _frametimes(20)

        result = harness.bench.run(2)

        assert result.ran is False
        assert "20 frames" in result.reason

    def test_an_empty_capture_says_so_rather_than_reporting_zero(self, harness: _Harness) -> None:
        harness.presentmon.frametimes = None
        harness.presentmon.last_error = "access denied"

        result = harness.bench.run(2)

        assert result.ran is False
        assert "recorded no frames" in result.reason
        assert "access denied" in result.reason

    def test_the_readings_are_computed_by_presentmons_own_definition(self, tmp_path: Path) -> None:
        """One definition of "the average of the slowest one percent of frames"
        in the build. A second one here is how the suite panel and the capture
        panel come to disagree about the same machine."""
        presentmon = PresentMonBenchmark(data_dir=tmp_path)
        frametimes = _frametimes(400)

        readings = fps_readings(presentmon, frametimes, _timestamps(frametimes), 1)
        whole = presentmon._calculate_stats(frametimes, _timestamps(frametimes))

        assert readings["fps_avg"].samples == [whole.fps_avg]
        assert readings["fps_1_percent_low"].samples == [whole.fps_1_percent_low]


class TestInstalling:
    def test_the_silent_switches_are_the_ones_that_returned_zero(
        self, harness: _Harness, tmp_path: Path
    ) -> None:
        """Inno Setup 5.5.7, measured at rc 0 in 82 s under elevation."""
        command = harness.bench.installer_command(tmp_path / "setup.exe", tmp_path / "install.log")

        assert command[0] == str(tmp_path / "setup.exe")
        assert command[1:5] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS"]
        assert f"/DIR={harness.bench.install_dir}" in command
        assert f"/LOG={tmp_path / 'install.log'}" in command

    def test_the_install_goes_where_the_bench_looks_for_the_engine(self, harness: _Harness) -> None:
        """The `/DIR` and the path the engine is later started from are one
        answer, not two that have to be kept in step."""
        command = harness.bench.installer_command(Path("setup.exe"), Path("install.log"))

        assert harness.bench.engine_path.parent.parent == harness.bench.install_dir
        assert f"/DIR={harness.bench.install_dir}" in command

    def test_a_download_of_the_wrong_size_is_never_hashed_into_an_install(
        self, harness: _Harness
    ) -> None:
        """The fixture's download writes a few bytes rather than 1.3 GB, which
        is what a truncated transfer looks like."""
        harness.bench.engine_path.unlink()
        harness.bench.allow_download = True

        assert harness.bench.install() is False
        assert str(INSTALLER_BYTES) in harness.bench._install_error
        assert harness.installer_runs == []

    def test_a_checksum_mismatch_leaves_the_installer_unrun_and_deleted(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It is an installer and it runs elevated, so the gate fails closed:
        the same rule `nv_profile._verify_download` applies to the NVIDIA one."""
        harness.bench.engine_path.unlink()
        harness.bench.allow_download = True

        def _download_right_size(url: str, destination: Path) -> None:
            harness.downloads.append((url, destination))
            destination.write_bytes(b"\0" * 16)

        monkeypatch.setattr(gpu_scene, "_download", _download_right_size)
        monkeypatch.setattr(gpu_scene, "INSTALLER_BYTES", 16)

        assert harness.bench.install() is False
        assert INSTALLER_SHA256 in harness.bench._install_error
        assert harness.installer_runs == []
        assert not harness.bench.installer_path.exists()

    def test_an_installer_already_on_disk_at_the_pinned_size_is_not_downloaded_again(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retry after a failed install would otherwise spend the 1.3 GB a
        second time. The checksum gate still runs on the file that is there."""
        harness.bench.engine_path.unlink()
        harness.bench.allow_download = True
        harness.bench.install_dir.mkdir(parents=True, exist_ok=True)
        harness.bench.installer_path.write_bytes(b"\0" * 16)
        monkeypatch.setattr(gpu_scene, "INSTALLER_BYTES", 16)

        harness.bench.install()

        assert harness.downloads == []
        assert INSTALLER_SHA256 in harness.bench._install_error

    def test_the_bench_reports_the_refusal_instead_of_measuring_anyway(
        self, harness: _Harness
    ) -> None:
        harness.bench.engine_path.unlink()
        harness.bench.allow_download = True

        result = harness.bench.run(2)

        assert result.ran is False
        assert "could not be installed" in result.reason
        assert not harness.spawned

    def test_an_automatic_run_never_starts_the_download(self, harness: _Harness) -> None:
        """1.3 GB is not something a background measurement spends on somebody's
        behalf — `benches.py`'s rule about the default run, over a download."""
        harness.bench.engine_path.unlink()

        available, why = harness.bench.is_available()
        result = harness.bench.run(2)

        assert available is False
        assert DOWNLOAD_SIZE in why
        assert result.ran is False
        assert DOWNLOAD_SIZE in result.reason
        assert harness.downloads == []


class TestWhenItMustNotRun:
    def test_a_running_game_keeps_it_out(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scene renders at full speed. Beside a match, that is the card
        being taken away from the person playing on it — a tweak that lowers the
        ceiling (C1), arriving as a benchmark."""
        monkeypatch.setattr(gpu_scene, "running_game_label", lambda: "Modern Warfare IV")

        available, why = harness.bench.is_available()
        result = harness.bench.run(2)

        assert available is False
        assert "Modern Warfare IV is running" in why
        assert result.ran is False
        assert "Modern Warfare IV is running" in result.reason
        assert not harness.spawned

    def test_it_is_available_on_a_machine_that_has_the_engine_and_no_game(
        self, harness: _Harness
    ) -> None:
        assert harness.bench.is_available() == (True, "")


class TestItFitsTheSuite:
    def test_it_satisfies_the_bench_protocol(self, harness: _Harness) -> None:
        assert isinstance(harness.bench, Bench)

    def test_it_declares_that_it_spawns_a_process(self, harness: _Harness) -> None:
        """A bench that spawns and does not implement this is a bench whose
        child survives its own deadline."""
        assert isinstance(harness.bench, SpawnsProcess)

    def test_the_deadline_sits_outside_the_benchs_own_budget(self) -> None:
        """A net that fired first would replace every readable reason with
        "timed out"."""
        bench = GpuSceneBench()

        assert bench.timeout_seconds(3) > bench.budget_seconds(3)

    def test_the_default_run_stays_inside_a_minute_and_a_half(self) -> None:
        """What the bench allows itself, start to finish, at the suite's own
        repeat count: engine load, settle, capture, and the capture's grace."""
        assert GpuSceneBench().budget_seconds(3) <= 90.0

    def test_the_deadline_grows_with_the_repeat_count(self) -> None:
        """Derived from its own work — more windows, more capture, more time."""
        bench = GpuSceneBench()

        assert bench.timeout_seconds(10) > bench.timeout_seconds(2)

    def test_the_capture_stays_inside_the_scene(self) -> None:
        """Past the scene's own 177 seconds the engine is parked on a results
        screen, and the frames would be of a menu."""
        assert GpuSceneBench(seconds_per_sample=60.0).capture_seconds(10) < 177.0

    def test_a_configuration_that_could_not_record_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to record anything"):
            GpuSceneBench(seconds_per_sample=0)


class TestTheLogIsReadAsText:
    def test_the_tags_come_off_and_the_entities_come_back(self, tmp_path: Path) -> None:
        """The reason a user reads is the engine's own last words, and they are
        wrapped in the HTML it writes them in."""
        log = tmp_path / "log.html"
        log.write_text(
            '<div class="m">12:40:59 Can&#39;t open &quot;data&quot;</div>\n',
            encoding="utf-8",
        )

        assert log_tail(log) == '12:40:59 Can\'t open "data"'

    def test_a_log_that_is_not_there_is_not_an_error(self, tmp_path: Path) -> None:
        assert log_tail(tmp_path / "missing.html") == ""

    def test_only_the_last_lines_are_carried(self, tmp_path: Path) -> None:
        log = tmp_path / "log.html"
        log.write_text(
            "".join(f'<div class="m">line {index}</div>\n' for index in range(40)),
            encoding="utf-8",
        )

        tail = log_tail(log, lines=3)

        assert tail == "line 37 | line 38 | line 39"
