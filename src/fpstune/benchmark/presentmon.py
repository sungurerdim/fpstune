"""PresentMon integration for FPS benchmarking.

PresentMon is Microsoft's open-source tool for capturing frame timing data.
https://github.com/GameTechDev/PresentMon

This module provides:
- Automatic PresentMon download/installation
- Background capture during gameplay
- Frame time analysis and statistics
- Before/after comparison with visual charts
"""

from __future__ import annotations

import csv
import json
import shutil
import statistics
import subprocess
import sys
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from fpstune.benchmark.result_store import ResultStore
from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

# No pinned release. The URL that used to live here — v2.2.0, as a zip —
# returned 404: the project moved to v2.5.1 and now publishes a bare .exe rather
# than an archive, so the version *and* the packaging changed underneath it. A
# benchmark that cannot install its own tool never ran, and nothing said so.
# `PresentMonBenchmark.resolve_download()` asks GitHub instead.
PRESENTMON_RELEASE_API = "https://api.github.com/repos/GameTechDev/PresentMon/releases/latest"
PRESENTMON_DOWNLOAD_SIZE_MB = 1  # The console build is under a megabyte.


# PresentMon's own spellings of the swapchain presentation path, across versions.
# "Hardware: Independent Flip" is the path a borderless game should be on; a
# "Composed" mode means the desktop compositor sat between the game and the
# screen. Shared with the MPO diagnostic, which reads the same column.
PRESENT_MODE_COLUMNS = ("PresentMode", "presentMode", "Present Mode")

# A frame counts as a stutter above this multiple of the run's average frame time.
# CapFrameX draws its line at 2.5x; fpstune keeps 2x, decided 2026-09-02: the
# shorter hitch is the one a player at a high refresh rate feels, and the
# threshold is a convention either way — what matters is that it is one number,
# named here, applied to before and after alike.
STUTTER_THRESHOLD_FACTOR = 2.0

# Two costs within this band of each other cannot be told apart — see
# `FrameTimeStats.bottleneck`.
_BOTTLENECK_BAND = 1.1


@dataclass
class FrameTimeStats:
    """Frame time statistics from a benchmark run."""

    # Basic stats
    frame_count: int = 0
    duration_seconds: float = 0.0

    # FPS stats
    fps_avg: float = 0.0
    fps_min: float = 0.0
    fps_max: float = 0.0
    fps_1_percent_low: float = 0.0
    fps_0_1_percent_low: float = 0.0

    # Frame time stats (ms)
    frametime_avg: float = 0.0
    frametime_min: float = 0.0
    frametime_max: float = 0.0
    frametime_stdev: float = 0.0
    frametime_99th: float = 0.0

    # Stutter detection
    stutter_count: int = 0  # Frames > 2x average
    stutter_percent: float = 0.0

    # Where the frame time actually goes. PresentMon 2.x reports these per
    # frame, and without them a frame rate is a number with no cause attached:
    # 57 fps says nothing about whether lowering a shadow setting would help.
    #
    # Measured on the dev machine in MW4 — CPU 17.18 ms against GPU 17.33 ms,
    # which is *not* the GPU-bound picture the in-game overlay suggested. A
    # recommendation built on that assumption would have spent effort on
    # settings the machine was never waiting for.
    cpu_busy_ms: float = 0.0
    gpu_time_ms: float = 0.0
    gpu_wait_ms: float = 0.0
    # Input to photon, when the capture carries it — the number a player feels,
    # as opposed to the frame time they see.
    input_latency_ms: float = 0.0
    # The presentation path most frames took, verbatim from PresentMon
    # ("Hardware: Independent Flip", "Composed: Flip", ...). Empty when the
    # capture carried no PresentMode column. A fact about the run, not a score.
    present_mode: str = ""

    # Raw data for charts
    frametimes: list[float] = field(default_factory=list)
    timestamps: list[float] = field(default_factory=list)

    @property
    def bottleneck(self) -> str:
        """Which side the frame waited on: ``gpu``, ``cpu`` or ``unknown``.

        The 10% band matters, and inside it the answer is *unknown*, not "both".
        PresentMon's ``MsCPUBusy`` can equal the frame time on a GPU-bound system
        (PresentMon issue #222), which makes the two costs read as equal exactly
        when the GPU is the one to blame. The dev-machine reading that once
        motivated a "both" verdict — CPU 17.18 ms against GPU 17.33 ms — is that
        shape. Reporting a side from inside the band would send a user to change
        settings that cannot help them; reporting nothing is the true statement.
        """
        if self.cpu_busy_ms <= 0 or self.gpu_time_ms <= 0:
            return "unknown"
        if self.gpu_time_ms > self.cpu_busy_ms * _BOTTLENECK_BAND:
            return "gpu"
        if self.cpu_busy_ms > self.gpu_time_ms * _BOTTLENECK_BAND:
            return "cpu"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (without raw data for smaller output).

        Three keys are conditional, and the condition is the instrument's own
        evidence rather than a default value. ``fps_gpu_bound`` / ``fps_cpu_bound``
        exist only when the capture established that side, so a claim about a
        GPU-bound frame rate is never judged against a run that was not one;
        ``input_latency_ms`` exists only when PresentMon reported input-to-photon
        (it needs ``--track_input``), so a 0.0 default can never read as a
        measured zero; ``present_mode`` exists only when the column was there.
        `verify_round` falls through to *unmeasured* on an absent key, which is
        the verdict a missing reading deserves.
        """
        payload: dict[str, Any] = {
            "frame_count": self.frame_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "fps_avg": round(self.fps_avg, 2),
            "fps_min": round(self.fps_min, 2),
            "fps_max": round(self.fps_max, 2),
            "fps_1_percent_low": round(self.fps_1_percent_low, 2),
            "fps_0_1_percent_low": round(self.fps_0_1_percent_low, 2),
            "frametime_avg": round(self.frametime_avg, 3),
            "frametime_min": round(self.frametime_min, 3),
            "frametime_max": round(self.frametime_max, 3),
            "frametime_stdev": round(self.frametime_stdev, 3),
            "frametime_99th": round(self.frametime_99th, 3),
            "stutter_count": self.stutter_count,
            "stutter_percent": round(self.stutter_percent, 2),
            "cpu_busy_ms": round(self.cpu_busy_ms, 3),
            "gpu_time_ms": round(self.gpu_time_ms, 3),
            "gpu_wait_ms": round(self.gpu_wait_ms, 3),
            "bottleneck": self.bottleneck,
        }
        if self.input_latency_ms > 0:
            payload["input_latency_ms"] = round(self.input_latency_ms, 3)
        if self.bottleneck == "gpu":
            payload["fps_gpu_bound"] = round(self.fps_avg, 2)
        if self.bottleneck == "cpu":
            payload["fps_cpu_bound"] = round(self.fps_avg, 2)
        if self.present_mode:
            payload["present_mode"] = self.present_mode
        return payload


@dataclass
class BenchmarkCapture:
    """A complete benchmark capture session."""

    name: str
    timestamp: str
    game_name: str
    stats: FrameTimeStats
    system_info: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "game_name": self.game_name,
            "stats": self.stats.to_dict(),
            "system_info": self.system_info,
            "notes": self.notes,
        }


@dataclass
class BenchmarkComparison:
    """Comparison between before and after benchmarks."""

    before: BenchmarkCapture
    after: BenchmarkCapture

    @property
    def fps_improvement(self) -> float:
        """Average FPS improvement percentage."""
        if self.before.stats.fps_avg == 0:
            return 0.0
        return (
            (self.after.stats.fps_avg - self.before.stats.fps_avg) / self.before.stats.fps_avg * 100
        )

    @property
    def fps_1_low_improvement(self) -> float:
        """1% low FPS improvement percentage."""
        if self.before.stats.fps_1_percent_low == 0:
            return 0.0
        return (
            (self.after.stats.fps_1_percent_low - self.before.stats.fps_1_percent_low)
            / self.before.stats.fps_1_percent_low
            * 100
        )

    @property
    def frametime_improvement(self) -> float:
        """Frame time improvement (negative is better)."""
        if self.before.stats.frametime_avg == 0:
            return 0.0
        return (
            (self.before.stats.frametime_avg - self.after.stats.frametime_avg)
            / self.before.stats.frametime_avg
            * 100
        )

    @property
    def stutter_improvement(self) -> float:
        """Stutter reduction percentage."""
        if self.before.stats.stutter_count == 0:
            return 0.0
        return (
            (self.before.stats.stutter_count - self.after.stats.stutter_count)
            / self.before.stats.stutter_count
            * 100
        )

    def format_report(self) -> str:
        """Format a detailed comparison report."""
        lines = []
        lines.append("=" * 70)
        lines.append("FPS BENCHMARK COMPARISON")
        lines.append("=" * 70)
        lines.append(f"Before: {self.before.name} ({self.before.game_name})")
        lines.append(f"After:  {self.after.name} ({self.after.game_name})")
        lines.append("-" * 70)
        lines.append("")

        # FPS Comparison
        lines.append("FPS PERFORMANCE:")
        lines.append(f"  {'Metric':<25} {'Before':>12} {'After':>12} {'Change':>12}")
        lines.append("  " + "-" * 60)

        metrics = [
            (
                "Average FPS",
                self.before.stats.fps_avg,
                self.after.stats.fps_avg,
                self.fps_improvement,
            ),
            (
                "1% Low FPS",
                self.before.stats.fps_1_percent_low,
                self.after.stats.fps_1_percent_low,
                self.fps_1_low_improvement,
            ),
            (
                "0.1% Low FPS",
                self.before.stats.fps_0_1_percent_low,
                self.after.stats.fps_0_1_percent_low,
                None,
            ),
            ("Min FPS", self.before.stats.fps_min, self.after.stats.fps_min, None),
            ("Max FPS", self.before.stats.fps_max, self.after.stats.fps_max, None),
        ]

        for name, before, after, change in metrics:
            change_str = ""
            if change is not None:
                if change > 0:
                    change_str = f"[green]+{change:.1f}%[/green]"
                elif change < 0:
                    change_str = f"[red]{change:.1f}%[/red]"
            lines.append(f"  {name:<25} {before:>12.1f} {after:>12.1f} {change_str:>12}")

        lines.append("")
        lines.append("FRAME TIME (lower is better):")
        lines.append(f"  {'Metric':<25} {'Before':>12} {'After':>12} {'Change':>12}")
        lines.append("  " + "-" * 60)

        ft_metrics = [
            (
                "Avg Frame Time (ms)",
                self.before.stats.frametime_avg,
                self.after.stats.frametime_avg,
            ),
            (
                "99th Percentile (ms)",
                self.before.stats.frametime_99th,
                self.after.stats.frametime_99th,
            ),
            (
                "Std Deviation (ms)",
                self.before.stats.frametime_stdev,
                self.after.stats.frametime_stdev,
            ),
        ]

        for name, before, after in ft_metrics:
            diff = after - before
            if diff < 0:
                change_str = f"[green]{diff:.2f}[/green]"
            elif diff > 0:
                change_str = f"[red]+{diff:.2f}[/red]"
            else:
                change_str = "0.00"
            lines.append(f"  {name:<25} {before:>12.2f} {after:>12.2f} {change_str:>12}")

        lines.append("")
        lines.append("STUTTER ANALYSIS:")
        lines.append(
            f"  Stutter Count: {self.before.stats.stutter_count} -> {self.after.stats.stutter_count}"
        )
        if self.stutter_improvement != 0:
            lines.append(f"  Stutter Reduction: {self.stutter_improvement:.1f}%")

        lines.append("")
        lines.append("=" * 70)
        lines.append("SUMMARY:")

        if self.fps_improvement > 0:
            lines.append(f"  [green]✓ Average FPS improved by {self.fps_improvement:.1f}%[/green]")
        else:
            lines.append(f"  [yellow]! Average FPS changed by {self.fps_improvement:.1f}%[/yellow]")

        if self.fps_1_low_improvement > 0:
            lines.append(
                f"  [green]✓ 1% Lows improved by {self.fps_1_low_improvement:.1f}%[/green]"
            )

        if self.frametime_improvement > 0:
            lines.append(
                f"  [green]✓ Frame times improved by {self.frametime_improvement:.1f}%[/green]"
            )

        lines.append("=" * 70)

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "improvements": {
                "fps_avg_percent": round(self.fps_improvement, 2),
                "fps_1_low_percent": round(self.fps_1_low_improvement, 2),
                "frametime_percent": round(self.frametime_improvement, 2),
                "stutter_percent": round(self.stutter_improvement, 2),
            },
        }


class PresentMonBenchmark:
    """PresentMon-based FPS benchmarking."""

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize PresentMon benchmark.

        Args:
            data_dir: Directory to store benchmark data.
        """
        self._data_dir = data_dir or get_config_dir() / "benchmarks"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._presentmon_dir = self._data_dir / "presentmon"
        self._captures_dir = self._data_dir / "captures"
        self._captures_dir.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger()
        self._store = ResultStore(self._data_dir, self._logger)
        self._process: subprocess.Popen[bytes] | None = None
        self._current_output: Path | None = None
        #: Whatever PresentMon printed to stderr on the last capture. Its
        #: refusals name their own cause ("requires administrative privileges",
        #: "unrecognized option") and a caller reporting an empty capture should
        #: pass that on rather than guess at one.
        self.last_error: str = ""

    @property
    def presentmon_path(self) -> Path:
        """Path to PresentMon executable."""
        return self._presentmon_dir / "PresentMon.exe"

    def is_installed(self) -> bool:
        """Check if PresentMon is installed."""
        return self.presentmon_path.exists()

    def resolve_download(self) -> tuple[str, str] | None:
        """Ask GitHub what the current PresentMon release actually is.

        The pinned URL this used to carry — v2.2.0, as a zip — returns 404. The
        project is on v2.5.1 and now publishes a bare ``.exe`` rather than an
        archive, so the version *and* the packaging both moved. A benchmark that
        cannot install its own tool is a benchmark that never ran, and nothing
        said so.

        Same rule the rest of the product follows: ask the source rather than
        hold a constant. Returns ``(version, url)``, or None when the API cannot
        be reached — offline is not an error worth failing loudly for.
        """
        import urllib.request

        api = PRESENTMON_RELEASE_API
        try:
            request = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
                release = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            self._logger.debug(f"Could not reach the PresentMon release API: {exc}")
            return None

        version = str(release.get("tag_name") or "").lstrip("v")
        assets = release.get("assets") or []

        # Prefer the console x64 executable. The installer .msi is 150 MB and
        # would need elevation to unpack; the bare exe is what this needs.
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower().endswith(".exe") and "x64" in name.lower():
                return version, str(asset.get("browser_download_url"))

        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower().endswith(".zip") and "symbol" not in name.lower():
                return version, str(asset.get("browser_download_url"))

        self._logger.debug("PresentMon release carries no asset this can use")
        return None

    def install(self, progress_callback: Callable[[int], None] | None = None) -> bool:
        """Download and install PresentMon.

        Args:
            progress_callback: Optional callback for download progress.

        Returns:
            True if installed successfully.
        """
        if sys.platform != "win32":
            self._logger.warning("PresentMon only works on Windows")
            return False

        resolved = self.resolve_download()
        if resolved is None:
            self._logger.error(
                "Could not determine a PresentMon download; benchmarks stay unavailable"
            )
            return False
        version, url = resolved

        try:
            self._presentmon_dir.mkdir(parents=True, exist_ok=True)
            self._logger.info(f"Downloading PresentMon {version}...")

            def reporthook(count: int, block_size: int, total_size: int) -> None:
                if progress_callback and total_size > 0:
                    progress = int(count * block_size * 100 / total_size)
                    progress_callback(progress)

            # The release publishes a bare executable now; older ones shipped a
            # zip. Both shapes are handled because a machine that installed the
            # old one should not be stuck with it.
            if url.lower().endswith(".exe"):
                urlretrieve(url, self.presentmon_path, reporthook)  # noqa: S310
            else:
                archive = self._presentmon_dir / "presentmon.zip"
                urlretrieve(url, archive, reporthook)  # noqa: S310
                self._logger.info("Extracting PresentMon...")
                with zipfile.ZipFile(archive, "r") as zf:
                    zf.extractall(self._presentmon_dir)
                for exe in self._presentmon_dir.rglob("PresentMon*.exe"):
                    if "Console" in exe.name or exe.name == "PresentMon.exe":
                        if exe.parent != self._presentmon_dir:
                            shutil.move(str(exe), str(self.presentmon_path))
                        break
                archive.unlink(missing_ok=True)

            if not self.is_installed():
                self._logger.error("PresentMon download finished but no executable is present")
                return False

            self._logger.info(f"PresentMon {version} installed successfully")
            return True

        except Exception as e:
            self._logger.error(f"Failed to install PresentMon: {e}")
            return False

    def start_capture(
        self,
        process_name: str | None = None,
        output_name: str | None = None,
        duration_seconds: int = 0,
    ) -> bool:
        """Start capturing frame data.

        Args:
            process_name: Target process name (e.g., "game.exe"). If None, captures all.
            output_name: Name for the capture file.
            duration_seconds: Capture duration. 0 = until stopped.

        Returns:
            True if capture started successfully.
        """
        if not self.is_installed() and not self.install():
            return False

        if self._process is not None:
            self._logger.warning("Capture already in progress")
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = output_name or f"capture_{timestamp}"
        output_file = self._captures_dir / f"{output_name}.csv"

        # PresentMon 2.x flags. The 1.x spelling `--no_top` is not merely
        # ignored by 2.x — it is rejected: `error: unrecognized option`, and the
        # process exits before recording anything. Measured 2026-08-25 against
        # PresentMon 2.5.1 with a game running: every capture produced an empty
        # file, and the product reported it as "the game may have been in a
        # menu". `--no_console_stats` is 2.x's name for the same suppression.
        cmd = [
            str(self.presentmon_path),
            "--output_file",
            str(output_file),
            "--terminate_on_proc_exit",
            "--no_console_stats",
        ]

        if process_name:
            cmd.extend(["--process_name", process_name])

        if duration_seconds > 0:
            # `--timed` stops the *recording*; without `--terminate_after_timed`
            # PresentMon keeps running afterwards, so a caller waiting for it to
            # finish waits forever and then kills it.
            cmd.extend(["--timed", str(duration_seconds), "--terminate_after_timed"])

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW  # Windows-only
                if sys.platform == "win32"
                else 0,
            )
            self._current_output = output_file
            self._logger.info(f"Started capture: {output_file}")
            return True

        except Exception as e:
            self._logger.error(f"Failed to start capture: {e}")
            return False

    def stop_capture(self) -> Path | None:
        """Stop the current capture.

        Returns:
            Path to the capture file, or None if no capture was running.
        """
        if self._process is None:
            return None

        # Read what PresentMon said before letting the process go. Its refusals
        # are specific and actionable — "access denied ... requires
        # administrative privileges", "unrecognized option" — and discarding
        # them is what left the product guessing that an empty capture meant the
        # game was in a menu.
        try:
            if self._process.poll() is None:
                self._process.terminate()
            _, stderr = self._process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            _, stderr = self._process.communicate()
        self.last_error = (stderr or b"").decode("utf-8", errors="replace").strip()
        if self.last_error:
            self._logger.debug("PresentMon said: %s", self.last_error)

        output_file = self._current_output
        self._process = None
        self._current_output = None

        if output_file is not None and output_file.exists():
            self._logger.info(f"Capture saved: {output_file}")
            return output_file

        return None

    def wait_for_capture(self, timeout: float) -> bool:
        """Wait for a `--timed` capture to end by itself.

        A capture started with `duration_seconds` exits on its own when the time
        is up. Without this the caller's only tool is `stop_capture`, which
        terminates the process — and terminating it immediately after starting
        it is exactly what happened: measured 2026-08-25 against a running game,
        a ten-second probe returned in 0.6 s having recorded no frames at all,
        and reported "it may have been in a menu".

        Args:
            timeout: Seconds to wait before giving up. Give the capture its own
                duration plus a margin for PresentMon's startup.

        Returns:
            True if the capture finished on its own, False if it is still going
            (in which case `stop_capture` is the right next call).
        """
        if self._process is None:
            return False
        try:
            self._process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def is_capturing(self) -> bool:
        """Check if a capture is in progress."""
        return self._process is not None and self._process.poll() is None

    def analyze_capture(self, capture_file: Path) -> FrameTimeStats | None:
        """Analyze a PresentMon capture file.

        Args:
            capture_file: Path to CSV capture file.

        Returns:
            FrameTimeStats with analyzed data.
        """
        if not capture_file.exists():
            return None

        frametimes = []
        timestamps = []
        # Per-frame cost breakdown. Column names differ across PresentMon
        # majors, so each is looked up by a list of spellings and simply stays
        # empty on a version that does not report it — an older capture loses
        # the breakdown, not the frame rate.
        breakdown: dict[str, list[float]] = {
            "cpu_busy": [],
            "gpu_time": [],
            "gpu_wait": [],
            "input_latency": [],
        }
        present_modes: Counter[str] = Counter()
        breakdown_columns = {
            "cpu_busy": ("MsCPUBusy", "msCPUBusy"),
            "gpu_time": ("MsGPUTime", "msGPUTime", "MsGPUBusy"),
            "gpu_wait": ("MsGPUWait", "msGPUWait"),
            "input_latency": (
                "MsAllInputToPhotonLatency",
                "MsClickToPhotonLatency",
                "MsRenderPresentLatency",
            ),
        }

        def _read(row: dict[str, str], names: tuple[str, ...]) -> float | None:
            for name in names:
                raw = row.get(name)
                if raw is None or raw in ("", "NA"):
                    continue
                try:
                    value = float(raw)
                except (ValueError, TypeError):
                    continue
                # PresentMon writes negative sentinels for frames it could not
                # attribute; averaging those in would understate the real cost.
                if value >= 0:
                    return value
            return None

        try:
            with open(capture_file, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # PresentMon columns vary by version
                    # Common: MsBetweenPresents, MsBetweenDisplayChange
                    frametime = _read(row, ("MsBetweenPresents", "msBetweenPresents", "FrameTime"))

                    if frametime and frametime > 0:
                        frametimes.append(frametime)

                        for key, names in breakdown_columns.items():
                            value = _read(row, names)
                            if value is not None:
                                breakdown[key].append(value)

                        for column in PRESENT_MODE_COLUMNS:
                            mode = (row.get(column) or "").strip()
                            if mode:
                                present_modes[mode] += 1
                                break

                        # Get timestamp if available
                        for tcol in ["TimeInSeconds", "Time", "TimeInMs"]:
                            if tcol in row:
                                try:
                                    timestamps.append(float(row[tcol]))
                                    break
                                except (ValueError, TypeError):
                                    pass

        except Exception as e:
            self._logger.error(f"Failed to parse capture: {e}")
            return None

        if not frametimes:
            return None

        return self._calculate_stats(frametimes, timestamps, breakdown, present_modes)

    def _calculate_stats(
        self,
        frametimes: list[float],
        timestamps: list[float],
        breakdown: dict[str, list[float]] | None = None,
        present_modes: Counter[str] | None = None,
    ) -> FrameTimeStats:
        """Calculate statistics from frame time data.

        Args:
            frametimes: List of frame times in milliseconds.
            timestamps: List of timestamps (optional).
            breakdown: Per-frame CPU/GPU/input costs, where the capture had them.
            present_modes: How many frames took each presentation path.

        Returns:
            FrameTimeStats with calculated values.
        """
        stats = FrameTimeStats()
        stats.frametimes = frametimes
        stats.timestamps = timestamps
        stats.frame_count = len(frametimes)
        if present_modes:
            stats.present_mode = present_modes.most_common(1)[0][0]

        # Where the frame time went. Averages rather than medians so a run with
        # a few very expensive frames reports the cost it actually paid — the
        # median would hide exactly the frames a player notices.
        if breakdown:
            if breakdown.get("cpu_busy"):
                stats.cpu_busy_ms = statistics.mean(breakdown["cpu_busy"])
            if breakdown.get("gpu_time"):
                stats.gpu_time_ms = statistics.mean(breakdown["gpu_time"])
            if breakdown.get("gpu_wait"):
                stats.gpu_wait_ms = statistics.mean(breakdown["gpu_wait"])
            if breakdown.get("input_latency"):
                stats.input_latency_ms = statistics.mean(breakdown["input_latency"])

        if not frametimes:
            return stats

        # Duration
        if timestamps and len(timestamps) > 1:
            stats.duration_seconds = timestamps[-1] - timestamps[0]
        else:
            stats.duration_seconds = sum(frametimes) / 1000.0

        # Frame time stats
        stats.frametime_avg = statistics.mean(frametimes)
        stats.frametime_min = min(frametimes)
        stats.frametime_max = max(frametimes)
        stats.frametime_stdev = statistics.stdev(frametimes) if len(frametimes) > 1 else 0

        # Percentiles
        sorted_ft = sorted(frametimes)
        idx_99 = int(len(sorted_ft) * 0.99)
        stats.frametime_99th = sorted_ft[idx_99] if idx_99 < len(sorted_ft) else sorted_ft[-1]

        # FPS stats (1000 / frametime_ms = FPS)
        fps_values = [1000.0 / ft for ft in frametimes if ft > 0]

        if fps_values:
            stats.fps_avg = statistics.mean(fps_values)
            stats.fps_min = min(fps_values)
            stats.fps_max = max(fps_values)

            # 1% and 0.1% lows (based on frame time, not FPS)
            sorted_fps = sorted(fps_values)
            idx_1 = int(len(sorted_fps) * 0.01)
            idx_01 = int(len(sorted_fps) * 0.001)

            # 1% low is average of bottom 1%
            low_1_percent = sorted_fps[: max(1, idx_1)]
            stats.fps_1_percent_low = statistics.mean(low_1_percent)

            low_01_percent = sorted_fps[: max(1, idx_01)]
            stats.fps_0_1_percent_low = statistics.mean(low_01_percent)

        # Stutter detection: frames above the named multiple of the average.
        stutter_threshold = stats.frametime_avg * STUTTER_THRESHOLD_FACTOR
        stats.stutter_count = sum(1 for ft in frametimes if ft > stutter_threshold)
        stats.stutter_percent = (stats.stutter_count / len(frametimes)) * 100

        return stats

    def create_capture(
        self,
        name: str,
        game_name: str = "Unknown",
        capture_file: Path | None = None,
        notes: str = "",
    ) -> BenchmarkCapture | None:
        """Create a benchmark capture object.

        Args:
            name: Name for the capture (e.g., "before", "after").
            game_name: Name of the game being benchmarked.
            capture_file: Path to PresentMon CSV file.
            notes: Additional notes.

        Returns:
            BenchmarkCapture object.
        """
        if capture_file is None:
            # Look for most recent capture
            captures = sorted(self._captures_dir.glob("*.csv"), reverse=True)
            if captures:
                capture_file = captures[0]
            else:
                return None

        stats = self.analyze_capture(capture_file)
        if stats is None:
            return None

        # Get system info
        from fpstune.utils.detect import get_cpu_info, get_gpu_info, get_os_info

        os_info = get_os_info()
        gpu_info = get_gpu_info()
        cpu_info = get_cpu_info()

        system_info = {
            "os": os_info.edition,
            "os_version": os_info.version,
            "cpu": cpu_info.get("cpu_name", "Unknown"),
            "gpu": gpu_info.name if gpu_info else "Unknown",
            "gpu_driver": gpu_info.driver_version if gpu_info else "Unknown",
        }

        return BenchmarkCapture(
            name=name,
            timestamp=datetime.now().isoformat(),
            game_name=game_name,
            stats=stats,
            system_info=system_info,
            notes=notes,
        )

    def compare(
        self,
        before: BenchmarkCapture,
        after: BenchmarkCapture,
    ) -> BenchmarkComparison:
        """Compare two benchmark captures.

        Args:
            before: Baseline capture.
            after: Post-optimization capture.

        Returns:
            BenchmarkComparison with analysis.
        """
        return BenchmarkComparison(before=before, after=after)

    def save_capture(self, capture: BenchmarkCapture) -> Path:
        """Save a benchmark capture to disk.

        Args:
            capture: BenchmarkCapture to save.

        Returns:
            Path to saved file.
        """
        # The game's name is part of the filename and is read off a running
        # process, so it goes through the same squash as the capture name.
        return self._store.save(capture.to_dict(), capture.name, capture.game_name)

    def load_capture(self, path: Path) -> BenchmarkCapture | None:
        """Load a benchmark capture from disk.

        Args:
            path: Path to capture JSON file.

        Returns:
            BenchmarkCapture or None if loading fails.
        """
        return self._store.load(path, self._capture_from_dict)

    @staticmethod
    def _capture_from_dict(data: dict[str, Any]) -> BenchmarkCapture:
        """Rebuild a capture from its saved form, readings and all."""
        stats_data = data.get("stats", {})
        stats = FrameTimeStats(
            frame_count=stats_data.get("frame_count", 0),
            duration_seconds=stats_data.get("duration_seconds", 0),
            fps_avg=stats_data.get("fps_avg", 0),
            fps_min=stats_data.get("fps_min", 0),
            fps_max=stats_data.get("fps_max", 0),
            fps_1_percent_low=stats_data.get("fps_1_percent_low", 0),
            fps_0_1_percent_low=stats_data.get("fps_0_1_percent_low", 0),
            frametime_avg=stats_data.get("frametime_avg", 0),
            frametime_min=stats_data.get("frametime_min", 0),
            frametime_max=stats_data.get("frametime_max", 0),
            frametime_stdev=stats_data.get("frametime_stdev", 0),
            frametime_99th=stats_data.get("frametime_99th", 0),
            stutter_count=stats_data.get("stutter_count", 0),
            stutter_percent=stats_data.get("stutter_percent", 0),
            cpu_busy_ms=stats_data.get("cpu_busy_ms", 0.0),
            gpu_time_ms=stats_data.get("gpu_time_ms", 0.0),
            gpu_wait_ms=stats_data.get("gpu_wait_ms", 0.0),
            input_latency_ms=stats_data.get("input_latency_ms", 0.0),
            present_mode=stats_data.get("present_mode", ""),
        )

        return BenchmarkCapture(
            name=data.get("name", "unknown"),
            timestamp=data.get("timestamp", ""),
            game_name=data.get("game_name", "Unknown"),
            stats=stats,
            system_info=data.get("system_info", {}),
            notes=data.get("notes", ""),
        )

    def list_captures(self) -> list[Path]:
        """List all saved captures, newest first.

        Two directories, not one: the saved summaries live beside the results of
        every other bench, and PresentMon's own raw CSV traces live under
        ``captures/``. Both are listed because either can be loaded back.
        """
        captures = self._store.list_files()
        captures.extend(self._captures_dir.glob("*.csv"))
        captures.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return captures
