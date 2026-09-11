"""What this graphics card reaches, on a scene nobody has to be playing.

Every frame-rate number fpstune could produce until now needed a game already
running. `presentmon` captures one, `headroom_watch` waits for one, and both are
the right shape for the question "how is this machine doing in the game you
actually play". Neither can answer the other question — *did that change make
the GPU faster* — because the load was a match, and a match is different every
time it is played. Two captures of two firefights are two different workloads,
and `measure_pair` comparing them is comparing the scenery.

This bench is the fixed load. Unigine Superposition draws the same scene, in the
same order, for the same 177 seconds, on every run and on every card — so the
only thing that can differ between a before and an after is the machine. The
frame data still comes from PresentMon, which is the point: C11 rule 7 wants one
vendor-neutral instrument, and using the engine's own score instead would mean a
second definition of a frame rate that only this bench could produce. The load
varies, the instrument does not.

**Superposition Basic, driven directly, and every part of that was measured**
(2026-09-11, evidence in the issue this landed under):

*The engine needs no launcher and no licence.* `superposition_cli.exe` is where
the "Command Line Automation" gate lives — it looks for a licence file and exits
silently without one. `superposition.exe` owns the whole vocabulary and runs it.
The argument list below is `superposition_cli`'s own printf templates, which is
why it is spelled the way it is rather than invented here.

*Windowed, never fullscreen.* `-video_fullscreen 1` pauses the benchmark the
moment its window loses focus, which turned a measured run into twelve minutes
of a paused scene rendering nothing. Windowed does not: with Notepad opened over
it, the capture recorded 1426 frames in 8 seconds and the largest gap was
14.9 ms. So the harness also spawns no window of its own while capturing —
every subprocess it starts during a run is created with `CREATE_NO_WINDOW`, and
the run is watched by reading a file rather than by enumerating processes.

*The engine never exits.* It parks on a results screen when the scene ends, so
the run is ended here: the capture finishes on its own clock and the process
tree is killed afterwards. Killing it first would end the capture early —
PresentMon is started with `--terminate_on_proc_exit`.

*It says where it is in its own log.* `%USERPROFILE%\\Superposition\\log.html`
gains a "Benchmark running" line 8-16 s after launch, once the scene is loaded
and the camera is moving. Before that line the frames are a loading screen: an
early capture produced `fps_avg` 278 with a 1% low of 1.06 and a 5.2-second
frame in it, which is a measurement of a level load wearing a frame rate's name.
So the log is polled, the line is waited for, and the capture starts three
seconds after it.

**Why the samples are windows of one run rather than several runs.** C11 rule 2
wants a list of samples, and the obvious way to get one is to launch the engine
`repeats` times — which at about fifty seconds a launch is two and a half
minutes of rendering for three samples, most of it spent loading the same scene
again. Instead one launch is captured for `seconds_per_sample * repeats`, and
the capture is cut into that many consecutive windows, each scored on its own.
They are genuinely repeated measurements of one fixed load, taken seconds apart,
which is what a noise floor is made of; what they cannot see is variation
between two loads of the scene, and that is written here rather than hidden.

**Licence.** Superposition Basic may be installed and executed on an unlimited
number of computers by private individuals for their own use, and derivative
works are prohibited (EULA 2.1, 2.1.1, 3.3). fpstune ships none of Unigine's
files, redistributes nothing, and modifies nothing: it downloads the vendor's
own installer from the vendor's own URL, checks it against a pinned SHA-256, and
drives the unmodified engine through its documented command line. The download
is 1.3 GB and never starts unasked — an automatic run on a machine without it
reports that it is not installed, which is C11 rule 3.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import urlretrieve

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.settings.executors.game_processes import (
    GAME_LABELS,
    GAME_PROCESSES,
    game_is_running,
)
from fpstune.settings.panel import primary_monitor
from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fpstune.benchmark.presentmon import FrameTimeStats, PresentMonBenchmark

logger = get_logger()

INSTALLER_URL = "https://assets.unigine.com/d/Unigine_Superposition-1.1.exe"
"""The vendor's own download, taken from the vendor's own host.

Pinned rather than resolved from a release feed the way `presentmon.py` asks
GitHub: there is no such feed here, and the hash below is only worth something
if it belongs to a file whose URL cannot change underneath it.
"""

INSTALLER_SHA256 = "de5dbf4f7ad284b709c5db318dbedc1b025a41e50326595a444ee9cbd4a17182"
"""Measured 2026-09-11 over the 1339177360-byte download.

The check fails closed, like `nv_profile._verify_download`: this file is an
installer that runs elevated, so a mismatch means the installer is deleted and
never executed, and the bench reports why instead of proceeding.
"""

INSTALLER_BYTES = 1_339_177_360

DOWNLOAD_SIZE = "1.3 GB"
"""How large the install is, in the sentence a user reads before agreeing to it."""

INSTALLER_NAME = "Unigine_Superposition-1.1.exe"

SCENE = "superposition/superposition"
"""The world the engine loads. One scene, so two runs are the same work."""

ENGINE_NAME = "superposition.exe"

SCENE_SECONDS = 177.0
"""How long the scene runs between its own "Benchmark running" and "Benchmark
stopped" lines, measured twice on 2026-09-11 and identical both times. The
capture window has to fit inside it, or the tail of the recording is a results
screen."""

RUNNING_MARKER = "Benchmark running"
"""The engine's own word for "the scene is loaded and the camera is moving"."""

DEFAULT_SECONDS_PER_SAMPLE = 10.0
"""Long enough that a 0.1% low is a real frame: at the 200 fps this machine
measured, one window holds about two thousand of them."""

DEFAULT_SETTLE_SECONDS = 3.0
"""Between the log saying the benchmark is running and the first recorded frame.

The marker is written when the scene starts, and the first frames after a level
load are still faulting textures in. Three seconds of those belong to the load,
not to the card."""

DEFAULT_LOAD_BUDGET_SECONDS = 45.0
"""How long the engine may take to reach its own "Benchmark running" line.

Measured at 13-14 s from launch, twice. Three times that leaves room for a cold
shader cache and a slow disk, and is still short enough that a machine where the
engine never starts reports a reason inside the bench's own minute and a half.
"""

DEFAULT_POLL_SECONDS = 1.0
"""How often the log file is read. A file read, deliberately: enumerating
processes or asking the driver for a GPU reading opens a window, and a window
that takes focus stops the benchmark."""

MINIMUM_FRAMES_PER_SAMPLE = 30
"""Below this a window is not a measurement.

A capture that recorded a handful of frames is a capture of something going
wrong — the scene paused, the wrong process was traced, the window was minimised
— and averaging six frames into an `fps_avg` would publish that as a result.
"""

_CAPTURE_GRACE_SECONDS = 10.0
"""How long past its own duration a timed capture may take to exit."""

_KILL_TIMEOUT_SECONDS = 15.0

_TAG = re.compile(r"<[^>]+>")
"""The engine's log is HTML, one `<div>` per line."""


def engine_log_path() -> Path:
    """Where the engine writes its log, from the environment rather than a path.

    The engine puts it under the running user's own profile directory, so the
    location is read back from the same variable Windows gave it (C9). Falls
    back to the home directory where that variable is not set, which is every
    non-Windows machine and no real one.
    """
    profile = os.environ.get("USERPROFILE")
    home = Path(profile) if profile else Path.home()
    return home / "Superposition" / "log.html"


def running_game_label() -> str | None:
    """The name of a game holding the GPU right now, or None.

    A label rather than a key, because the only thing this is used for is a
    sentence somebody reads.
    """
    for game in GAME_PROCESSES:
        if game_is_running(game):
            return GAME_LABELS.get(game, game.upper())
    return None


def log_tail(path: Path, lines: int = 5) -> str:
    """The last few lines the engine wrote, as plain text.

    What the engine says when it refuses to start is the only account of why,
    and it is written to this file and nowhere else — there is no stderr to
    read. Tags are stripped and entities unescaped so the reason reads as a
    sentence rather than as markup.
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    text: list[str] = []
    for line in raw.splitlines():
        stripped = html.unescape(_TAG.sub("", line)).strip()
        if stripped:
            text.append(stripped)
    return " | ".join(text[-lines:])


def _sha256(path: Path) -> str:
    """The file's hash, read in blocks — it is 1.3 GB."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _no_window() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _spawn_engine(args: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    """Start the engine, with its output discarded and its window its own.

    No `CREATE_NO_WINDOW` here and nowhere else: the engine *is* the window, and
    it has to be on screen to render. Everything else this module starts is
    created without one.
    """
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _kill_tree(pid: int) -> None:
    """Kill the engine and whatever it started.

    `/T` because the engine is not always the only process in its own tree, and
    a child left holding the GPU is the leftover the next run would measure.
    """
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=_KILL_TIMEOUT_SECONDS,
            creationflags=_no_window(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("The scene engine would not be killed: %s", exc)


def _download(url: str, destination: Path) -> None:
    urlretrieve(url, destination)  # noqa: S310 - a pinned https URL, hashed after


def _run_installer(args: list[str]) -> int:
    completed = subprocess.run(
        args,
        capture_output=True,
        timeout=900,
        creationflags=_no_window(),
    )
    return completed.returncode


def _windows(
    frametimes: list[float], timestamps: list[float], count: int
) -> Iterator[tuple[list[float], list[float]]]:
    """Cut a capture into `count` consecutive windows of equal frame count.

    By frames rather than by wall clock, so every window carries the same number
    of samples: a window cut by time would hold twice as many frames where the
    scene was fast, and its percentile lows would then be computed over a
    different population than its neighbour's.
    """
    size = len(frametimes) // count
    for index in range(count):
        start = index * size
        stop = len(frametimes) if index == count - 1 else start + size
        yield frametimes[start:stop], timestamps[start:stop]


def fps_readings(
    presentmon: PresentMonBenchmark,
    frametimes: list[float],
    timestamps: list[float],
    samples: int,
) -> dict[str, BenchReading]:
    """One capture, cut into `samples` windows, as the three frame-rate readings.

    Scored by `presentmon`'s own `_calculate_stats`, deliberately. "The average
    of the slowest one percent of frames" is a definition, this build already
    has one, and writing a second one here is how the number on the suite panel
    and the number on the capture panel come to disagree about the same machine.
    The bench already holds a `PresentMonBenchmark` for the capture itself, so
    nothing is constructed to reach it.

    `fps_avg` declares its own direction because `verify_round` does not know
    that name — it knows `fps`, which belongs to a capture of a real game. This
    is a fixed synthetic scene, and letting it answer under the name a game's
    claim is judged by would be two quantities wearing one name.
    """
    if samples < 1:
        raise ValueError("a reading needs at least one window to be measured over")

    averages: list[float] = []
    lows_1: list[float] = []
    lows_01: list[float] = []
    for window_frametimes, window_timestamps in _windows(frametimes, timestamps, samples):
        stats: FrameTimeStats = presentmon._calculate_stats(window_frametimes, window_timestamps)
        averages.append(stats.fps_avg)
        lows_1.append(stats.fps_1_percent_low)
        lows_01.append(stats.fps_0_1_percent_low)

    return {
        "fps_avg": BenchReading("fps_avg", averages, "fps", higher_is_better=True),
        "fps_1_percent_low": BenchReading("fps_1_percent_low", lows_1, "fps"),
        "fps_0_1_percent_low": BenchReading("fps_0_1_percent_low", lows_01, "fps"),
    }


class GpuSceneBench:
    """The GPU's own ceiling, on a fixed scene, with no game running."""

    key = "gpu_scene"
    label = "GPU scene"
    requires = (
        "Unigine Superposition Basic installed, and no game running — "
        "the scene renders full speed and would take the card from the game"
    )

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        seconds_per_sample: float = DEFAULT_SECONDS_PER_SAMPLE,
        settle_seconds: float = DEFAULT_SETTLE_SECONDS,
        load_budget_seconds: float = DEFAULT_LOAD_BUDGET_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        allow_download: bool = False,
        presentmon: PresentMonBenchmark | None = None,
        log_path: Path | None = None,
    ) -> None:
        if seconds_per_sample <= 0:
            raise ValueError("seconds_per_sample has to be positive to record anything")
        self._data_dir = data_dir
        self.seconds_per_sample = seconds_per_sample
        self.settle_seconds = settle_seconds
        self.load_budget_seconds = load_budget_seconds
        self.poll_seconds = poll_seconds
        self.allow_download = allow_download
        """Whether this instance may spend 1.3 GB of somebody's line.

        False by default and False for every automatic run. The install is a
        decision a user makes once, not something a background measurement does
        on their behalf — `benches.py`'s rule about what a default run may
        spend, applied to a download instead of an upload.
        """
        self._presentmon = presentmon
        self._log_path = log_path
        self._engine: subprocess.Popen[bytes] | None = None
        self._install_error = ""

    # -- where things are -------------------------------------------------

    @property
    def data_dir(self) -> Path:
        return self._data_dir or get_config_dir() / "benchmarks"

    @property
    def install_dir(self) -> Path:
        return self.data_dir / "superposition"

    @property
    def bin_dir(self) -> Path:
        """The engine's own directory, which is also the working directory.

        The engine resolves its data paths relative to the process's working
        directory, so it is started from here and not from ours.
        """
        return self.install_dir / "bin"

    @property
    def engine_path(self) -> Path:
        return self.bin_dir / ENGINE_NAME

    @property
    def installer_path(self) -> Path:
        return self.install_dir / INSTALLER_NAME

    @property
    def log_path(self) -> Path:
        return self._log_path or engine_log_path()

    @property
    def presentmon(self) -> PresentMonBenchmark:
        """The capture tool, built on first use.

        Lazily, because constructing one creates directories and the registry in
        `benches.py` builds every bench fresh each time anybody asks what exists.
        """
        if self._presentmon is None:
            from fpstune.benchmark.presentmon import PresentMonBenchmark

            self._presentmon = PresentMonBenchmark(data_dir=self.data_dir)
        return self._presentmon

    def is_installed(self) -> bool:
        return self.engine_path.exists()

    # -- the command lines, kept where they can be read and tested --------

    def engine_command(self, width: int, height: int) -> list[str]:
        """The measured argument list, with the panel's own resolution in it.

        Width and height come from the display (C9). A constant here would
        measure a 1080p machine at somebody else's 1440p and call the difference
        a result.

        Everything visual is at its floor — `-shaders_quality 0`,
        `-textures_quality 0`, no depth of field, no motion blur. That is not
        the product's information-preserving minimum (consequence 5), which is
        about what a player has to see; nothing here is played. It is the
        setting that puts the load where the question is and keeps the run
        short.
        """
        return [
            str(self.engine_path),
            "-project_name",
            "Superposition",
            "-video_mode",
            "-1",
            "-console_command",
            f"world_load {SCENE}",
            "-extern_plugin",
            "GPUMonitor",
            "-preset",
            "0",
            "-batch",
            "1",
            "-video_app",
            "direct3d11",
            # Never 1. Fullscreen pauses the benchmark when the window loses
            # focus, and loses it to anything at all — measured, twice.
            "-video_fullscreen",
            "0",
            "-video_width",
            str(width),
            "-video_height",
            str(height),
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

    def installer_command(self, installer: Path, install_log: Path) -> list[str]:
        """Inno Setup 5.5.7's own silent switches, measured at rc 0 in 82 s.

        `/NOICONS` because a benchmark fpstune drives does not belong on
        somebody's desktop, and `/LOG` because an install that fails silently is
        an install nobody can be told about.
        """
        return [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/NOICONS",
            f"/DIR={self.install_dir}",
            f"/LOG={install_log}",
        ]

    # -- the suite protocol -----------------------------------------------

    def capture_seconds(self, repeats: int) -> float:
        """How long the recording runs: one window per repeat.

        Held inside the scene's own length, because past that the engine is
        parked on a results screen and the frames would be of a menu.
        """
        return min(self.seconds_per_sample * max(repeats, 1), SCENE_SECONDS - 20.0)

    def budget_seconds(self, repeats: int) -> float:
        """The bench's own limit: what a healthy run can take, start to finish."""
        return (
            self.load_budget_seconds
            + self.settle_seconds
            + self.capture_seconds(repeats)
            + _CAPTURE_GRACE_SECONDS
        )

    def timeout_seconds(self, repeats: int) -> float:
        """The suite's net, which has to sit outside this bench's own budget.

        `budget_seconds` is what the bench enforces on itself and is where a
        stuck engine is reported with a reason. This is the deadline for the
        case where the bench itself stops answering, so it is the same budget
        with the suite's standard grace on top — a net that fired first would
        replace every readable reason with "timed out".
        """
        return deadline_for(self.budget_seconds(repeats) / max(repeats, 1), repeats)

    def is_available(self) -> tuple[bool, str]:
        """Whether this is a machine, and a moment, that can answer."""
        if sys.platform != "win32":
            return False, "the scene engine is a Windows build"

        playing = running_game_label()
        if playing is not None:
            return False, (
                f"{playing} is running. The scene renders at full speed and would "
                "take the card away from the game, so it waits until you are done."
            )

        if not self.is_installed():
            if not self.allow_download:
                return False, (
                    f"Unigine Superposition Basic is not installed; installing it is a "
                    f"{DOWNLOAD_SIZE} download, which fpstune never starts on its own."
                )
            return True, ""

        return True, ""

    def terminate_child(self) -> None:
        """Let go of the engine, for a caller that has stopped waiting.

        `suite.SpawnsProcess`. Without it a bench that missed its deadline
        leaves a 3D scene rendering at full speed behind it — which the next
        bench in the run would then be measured against.
        """
        engine = self._engine
        self._engine = None
        if engine is not None and engine.poll() is None:
            _kill_tree(engine.pid)
        try:
            self.presentmon.terminate_child()
        except Exception as exc:  # noqa: BLE001 - a failed kill must not mask the timeout
            logger.debug("The capture would not be stopped: %s", exc)

    # -- installing --------------------------------------------------------

    def install(self) -> bool:
        """Download the vendor's installer, check it, and run it silently.

        Fails closed at every step and records why in `_install_error`, so the
        bench can report a sentence rather than a bare False. A download whose
        hash does not match is deleted without being executed: it is an
        installer, and it runs elevated.
        """
        self._install_error = ""
        if sys.platform != "win32":
            self._install_error = "the scene engine is a Windows build"
            return False

        installer = self.installer_path
        try:
            self.install_dir.mkdir(parents=True, exist_ok=True)
            # An installer already on disk at the pinned size is one an earlier
            # attempt fetched and could not run (the checksum below still has
            # to pass before it is executed); spending the download again
            # would be the only thing a retry achieved.
            if not (installer.exists() and installer.stat().st_size == INSTALLER_BYTES):
                logger.info("Downloading Unigine Superposition Basic (%s)...", DOWNLOAD_SIZE)
                _download(INSTALLER_URL, installer)
        except Exception as exc:  # noqa: BLE001 - reported, never raised at the suite
            self._install_error = f"the {DOWNLOAD_SIZE} download did not finish: {exc}"
            installer.unlink(missing_ok=True)
            return False

        size = installer.stat().st_size
        if size != INSTALLER_BYTES:
            installer.unlink(missing_ok=True)
            self._install_error = (
                f"the download is {size} bytes and the pinned installer is "
                f"{INSTALLER_BYTES}, so it was deleted unrun"
            )
            logger.error(self._install_error)
            return False

        digest = _sha256(installer)
        if digest != INSTALLER_SHA256:
            installer.unlink(missing_ok=True)
            self._install_error = (
                "the downloaded installer does not match its pinned checksum "
                f"(expected {INSTALLER_SHA256}, got {digest}), so it was deleted unrun"
            )
            logger.error(self._install_error)
            return False

        install_log = self.install_dir / "install.log"
        try:
            code = _run_installer(self.installer_command(installer, install_log))
        except Exception as exc:  # noqa: BLE001 - reported, never raised at the suite
            self._install_error = f"the installer could not be started: {exc}"
            return False
        finally:
            installer.unlink(missing_ok=True)

        if code != 0 or not self.is_installed():
            self._install_error = (
                f"the installer exited with code {code} and left no engine at "
                f"{self.engine_path.name}"
            )
            return False

        logger.info("Unigine Superposition Basic installed")
        return True

    # -- measuring ---------------------------------------------------------

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        def failed(reason: str) -> BenchResult:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=reason,
                duration_seconds=time.perf_counter() - started,
            )

        playing = running_game_label()
        if playing is not None:
            return failed(
                f"{playing} is running. The scene renders at full speed and would "
                "take the card away from the game, so it waits until you are done."
            )

        if not self.is_installed():
            if not self.allow_download:
                return failed(
                    f"Unigine Superposition Basic is not installed; installing it is a "
                    f"{DOWNLOAD_SIZE} download, which fpstune never starts on its own."
                )
            if not self.install():
                return failed(
                    f"Unigine Superposition Basic could not be installed: {self._install_error}"
                )

        from fpstune.utils.hardware_manager import hardware_manager

        monitor = primary_monitor(hardware_manager.detect_monitors())
        if monitor is None or monitor.width <= 0 or monitor.height <= 0:
            return failed(
                "no active display reported a resolution, and the scene has to be "
                "rendered at the panel's own size for the result to mean anything"
            )

        return self._measure(monitor.width, monitor.height, repeats, started)

    def _measure(self, width: int, height: int, repeats: int, started: float) -> BenchResult:
        """One launch, one capture, one set of readings."""

        def failed(reason: str) -> BenchResult:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=reason,
                duration_seconds=time.perf_counter() - started,
            )

        log = self.log_path
        # Deleted before the launch so a marker from the last run cannot be read
        # as this one's. Without it the poll below returns instantly, and the
        # capture records a level load.
        try:
            log.unlink(missing_ok=True)
        except OSError as exc:
            return failed(f"the engine's own log could not be cleared: {exc}")

        try:
            engine = _spawn_engine(self.engine_command(width, height), self.bin_dir)
        except OSError as exc:
            return failed(f"the scene engine would not start: {exc}")
        self._engine = engine

        try:
            load_seconds = self._wait_for_scene(engine, log)
            if load_seconds is None:
                tail = log_tail(log)
                if engine.poll() is not None:
                    return failed(
                        "the scene engine exited before it started rendering"
                        + (f": {tail}" if tail else "")
                    )
                return failed(
                    f"the scene did not start rendering within {self.load_budget_seconds:.0f} s"
                    + (f": {tail}" if tail else "")
                )

            time.sleep(self.settle_seconds)

            seconds = self.capture_seconds(repeats)
            presentmon = self.presentmon
            if not presentmon.start_capture(
                process_name=ENGINE_NAME,
                output_name="gpu_scene",
                duration_seconds=int(seconds),
            ):
                return failed(
                    "the frame capture would not start"
                    + (f": {presentmon.last_error}" if presentmon.last_error else "")
                )

            presentmon.wait_for_capture(timeout=seconds + _CAPTURE_GRACE_SECONDS)
            capture = presentmon.stop_capture()
        finally:
            # After the capture, never before: PresentMon is started with
            # `--terminate_on_proc_exit`, so killing the engine first ends the
            # recording early and the last window is short.
            self._engine = None
            if engine.poll() is None:
                _kill_tree(engine.pid)

        if capture is None:
            return failed(
                "the frame capture produced no file"
                + (f": {presentmon.last_error}" if presentmon.last_error else "")
            )

        stats = presentmon.analyze_capture(capture)
        if stats is None or not stats.frametimes:
            return failed(
                "the frame capture recorded no frames"
                + (f": {presentmon.last_error}" if presentmon.last_error else "")
            )

        needed = MINIMUM_FRAMES_PER_SAMPLE * repeats
        if len(stats.frametimes) < needed:
            return failed(
                f"the capture recorded {len(stats.frametimes)} frames, and "
                f"{repeats} comparable windows need at least {needed}"
            )

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=fps_readings(presentmon, stats.frametimes, stats.timestamps, repeats),
            detail={
                "width": width,
                "height": height,
                "present_mode": stats.present_mode,
                "frame_count": stats.frame_count,
                "load_seconds": round(load_seconds, 1),
                "capture_seconds": round(self.capture_seconds(repeats), 1),
                "seconds_per_sample": self.seconds_per_sample,
                "scene": SCENE,
            },
            duration_seconds=time.perf_counter() - started,
        )

    def _wait_for_scene(self, engine: subprocess.Popen[bytes], log: Path) -> float | None:
        """Seconds until the engine said it was rendering, or None if it never did.

        The log file and nothing else. Asking Windows which processes exist, or
        the driver how hot the card is, opens a window; a window takes focus;
        and focus is what this benchmark stops for.
        """
        started = time.perf_counter()
        while True:
            elapsed = time.perf_counter() - started
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""

            if RUNNING_MARKER in text:
                return elapsed
            if engine.poll() is not None:
                return None
            if elapsed >= self.load_budget_seconds:
                return None

            time.sleep(self.poll_seconds)
