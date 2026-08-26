"""FurMark 2 integration for GPU benchmarking.

FurMark 2 is a free GPU stress test and benchmark tool.
https://geeks3d.com/furmark/

This module provides:
- Automatic FurMark 2 download/installation
- Standardized benchmark runs (consistent settings)
- Result parsing and analysis
- Before/after comparison
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from fpstune.benchmark.result_store import ResultStore
from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

# FurMark 2 download URL
FURMARK_DOWNLOAD_URL = "https://geeks3d.com/dl/get/806"  # FurMark 2 latest
FURMARK_VERSION = "2.10"
FURMARK_DOWNLOAD_SIZE_MB = 34  # Approximate ZIP download size


@dataclass
class FurMarkResult:
    """FurMark benchmark result."""

    # Basic info
    name: str
    timestamp: str
    duration_seconds: int

    # Performance metrics
    score: int = 0
    fps_avg: float = 0.0
    fps_min: float = 0.0
    fps_max: float = 0.0

    # GPU info
    gpu_name: str = ""
    gpu_driver: str = ""
    gpu_temp_max: float = 0.0
    gpu_power_max: float = 0.0

    # Settings
    resolution: str = ""
    api: str = ""  # OpenGL or Vulkan
    msaa: int = 0

    # Raw data file
    log_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "score": self.score,
            "fps_avg": round(self.fps_avg, 2),
            "fps_min": round(self.fps_min, 2),
            "fps_max": round(self.fps_max, 2),
            "gpu_name": self.gpu_name,
            "gpu_driver": self.gpu_driver,
            "gpu_temp_max": round(self.gpu_temp_max, 1),
            "gpu_power_max": round(self.gpu_power_max, 1),
            "resolution": self.resolution,
            "api": self.api,
            "msaa": self.msaa,
        }


@dataclass
class FurMarkComparison:
    """Comparison between before and after FurMark benchmarks."""

    before: FurMarkResult
    after: FurMarkResult

    @property
    def score_improvement(self) -> float:
        """Score improvement percentage."""
        if self.before.score == 0:
            return 0.0
        return ((self.after.score - self.before.score) / self.before.score) * 100

    @property
    def fps_improvement(self) -> float:
        """Average FPS improvement percentage."""
        if self.before.fps_avg == 0:
            return 0.0
        return ((self.after.fps_avg - self.before.fps_avg) / self.before.fps_avg) * 100

    @property
    def min_fps_improvement(self) -> float:
        """Minimum FPS improvement percentage."""
        if self.before.fps_min == 0:
            return 0.0
        return ((self.after.fps_min - self.before.fps_min) / self.before.fps_min) * 100

    def format_report(self) -> str:
        """Format a comparison report."""
        lines = []
        lines.append("=" * 70)
        lines.append("FURMARK GPU BENCHMARK COMPARISON")
        lines.append("=" * 70)
        lines.append(f"Before: {self.before.name} ({self.before.timestamp[:10]})")
        lines.append(f"After:  {self.after.name} ({self.after.timestamp[:10]})")
        lines.append(f"GPU: {self.before.gpu_name}")
        lines.append("-" * 70)
        lines.append("")

        # Score comparison
        lines.append("BENCHMARK SCORE:")
        lines.append(f"  Before: {self.before.score:,}")
        lines.append(f"  After:  {self.after.score:,}")
        if self.score_improvement > 0:
            lines.append(f"  [green]Improvement: +{self.score_improvement:.1f}%[/green]")
        elif self.score_improvement < 0:
            lines.append(f"  [red]Change: {self.score_improvement:.1f}%[/red]")
        lines.append("")

        # FPS comparison
        lines.append("FPS PERFORMANCE:")
        lines.append(f"  {'Metric':<20} {'Before':>12} {'After':>12} {'Change':>12}")
        lines.append("  " + "-" * 56)

        metrics = [
            ("Average FPS", self.before.fps_avg, self.after.fps_avg, self.fps_improvement),
            ("Minimum FPS", self.before.fps_min, self.after.fps_min, self.min_fps_improvement),
            ("Maximum FPS", self.before.fps_max, self.after.fps_max, None),
        ]

        for name, before, after, change in metrics:
            change_str = ""
            if change is not None:
                if change > 0:
                    change_str = f"[green]+{change:.1f}%[/green]"
                elif change < 0:
                    change_str = f"[red]{change:.1f}%[/red]"
            lines.append(f"  {name:<20} {before:>12.1f} {after:>12.1f} {change_str:>12}")

        lines.append("")
        lines.append("GPU THERMALS:")
        lines.append(
            f"  Max Temp: {self.before.gpu_temp_max:.0f}°C -> {self.after.gpu_temp_max:.0f}°C"
        )
        lines.append(
            f"  Max Power: {self.before.gpu_power_max:.0f}W -> {self.after.gpu_power_max:.0f}W"
        )

        lines.append("")
        lines.append("=" * 70)
        lines.append("SUMMARY:")

        if self.score_improvement > 0:
            lines.append(f"  [green]✓ Score improved by {self.score_improvement:.1f}%[/green]")
        if self.fps_improvement > 0:
            lines.append(f"  [green]✓ Average FPS improved by {self.fps_improvement:.1f}%[/green]")
        if self.min_fps_improvement > 0:
            lines.append(
                f"  [green]✓ Minimum FPS improved by {self.min_fps_improvement:.1f}%[/green]"
            )

        if self.score_improvement <= 0 and self.fps_improvement <= 0:
            lines.append("  [yellow]No significant performance improvement detected[/yellow]")

        lines.append("=" * 70)

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "improvements": {
                "score_percent": round(self.score_improvement, 2),
                "fps_avg_percent": round(self.fps_improvement, 2),
                "fps_min_percent": round(self.min_fps_improvement, 2),
            },
        }


class FurMarkBenchmark:
    """FurMark 2 GPU benchmarking."""

    # Preset configurations for consistent benchmarks
    PRESETS = {
        "quick": {
            "duration": 60,
            "resolution": "1280x720",
            "msaa": 0,
        },
        "standard": {
            "duration": 120,
            "resolution": "1920x1080",
            "msaa": 2,
        },
        "extreme": {
            "duration": 180,
            "resolution": "2560x1440",
            "msaa": 4,
        },
    }

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize FurMark benchmark.

        Args:
            data_dir: Directory to store benchmark data.
        """
        self._data_dir = data_dir or get_config_dir() / "furmark"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._furmark_dir = self._data_dir / "furmark2"
        self._results_dir = self._data_dir / "results"
        self._results_dir.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger()
        self._store = ResultStore(self._results_dir, self._logger)

    @property
    def furmark_path(self) -> Path:
        """Path to FurMark executable."""
        return self._furmark_dir / "FurMark.exe"

    @property
    def furmark_cli_path(self) -> Path:
        """Path to FurMark CLI executable."""
        # FurMark 2 uses furmark.exe for CLI
        return self._furmark_dir / "furmark.exe"

    def is_installed(self) -> bool:
        """Check if FurMark is installed."""
        return self.furmark_cli_path.exists() or self.furmark_path.exists()

    def install(self, progress_callback: Callable[[int], None] | None = None) -> bool:
        """Download and install FurMark 2.

        Args:
            progress_callback: Optional callback for download progress.

        Returns:
            True if installed successfully.
        """
        if sys.platform != "win32":
            self._logger.warning("FurMark only works on Windows")
            return False

        try:
            self._furmark_dir.mkdir(parents=True, exist_ok=True)
            zip_path = self._furmark_dir / "furmark2.zip"

            # Download
            self._logger.info("Downloading FurMark 2...")

            def reporthook(count: int, block_size: int, total_size: int) -> None:
                if progress_callback and total_size > 0:
                    progress = int(count * block_size * 100 / total_size)
                    progress_callback(min(progress, 100))

            urlretrieve(FURMARK_DOWNLOAD_URL, zip_path, reporthook)

            # Extract
            self._logger.info("Extracting FurMark 2...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self._furmark_dir)

            # Find the exe (might be in a subdirectory)
            for exe in self._furmark_dir.rglob("furmark.exe"):
                if exe.parent != self._furmark_dir:
                    # Move all files from subdirectory
                    for item in exe.parent.iterdir():
                        shutil.move(str(item), str(self._furmark_dir / item.name))
                break

            # Cleanup
            zip_path.unlink(missing_ok=True)

            # Remove empty subdirectories
            for subdir in self._furmark_dir.iterdir():
                if subdir.is_dir() and not list(subdir.iterdir()):
                    subdir.rmdir()

            self._logger.info("FurMark 2 installed successfully")
            return self.is_installed()

        except Exception as e:
            self._logger.error(f"Failed to install FurMark: {e}")
            return False

    def run_benchmark(
        self,
        name: str = "benchmark",
        preset: str = "standard",
        api: str = "opengl",
        custom_duration: int | None = None,
        custom_resolution: str | None = None,
    ) -> FurMarkResult | None:
        """Run a FurMark benchmark.

        Args:
            name: Name for this benchmark run.
            preset: Preset configuration (quick, standard, extreme).
            api: Graphics API (opengl or vulkan).
            custom_duration: Override preset duration (seconds).
            custom_resolution: Override preset resolution (e.g., "1920x1080").

        Returns:
            FurMarkResult or None if benchmark fails.
        """
        if not self.is_installed() and not self.install():
            return None

        # Get preset settings
        settings = self.PRESETS.get(preset, self.PRESETS["standard"]).copy()

        if custom_duration:
            settings["duration"] = custom_duration
        if custom_resolution:
            settings["resolution"] = custom_resolution

        # Parse resolution
        resolution = settings["resolution"]
        assert isinstance(resolution, str), f"resolution must be str, got {type(resolution)}"
        width, height = resolution.split("x")

        # Determine demo name
        demo = "furmark-gl" if api.lower() == "opengl" else "furmark-vk"

        # Output file for GPU data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self._results_dir / f"{name}_{timestamp}_gpu.csv"

        # Build command
        cmd = [
            str(self.furmark_cli_path),
            "--demo",
            demo,
            "--width",
            width,
            "--height",
            height,
            "--max-time",
            str(settings["duration"]),
            "--msaa",
            str(settings["msaa"]),
            "--log-gpu-data",
            "--export-dir",
            str(self._results_dir),
            "--no-score-box",
        ]

        self._logger.info(f"Running FurMark benchmark: {name}")
        self._logger.info(
            f"Settings: {settings['resolution']}, {settings['duration']}s, {api.upper()}"
        )

        try:
            # Run benchmark
            raw_duration = settings["duration"]
            # Cast to int safely - preset values are always int but dict returns object
            duration: int = int(str(raw_duration)) if raw_duration is not None else 120
            result = subprocess.run(
                cmd,
                cwd=str(self._furmark_dir),
                capture_output=True,
                text=True,
                timeout=duration + 60,  # Extra time for startup/shutdown
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                self._logger.error(f"FurMark failed: {result.stderr}")
                return None

            # Parse output
            return self._parse_result(
                name=name,
                output=result.stdout,
                log_file=log_file if log_file.exists() else None,
                settings=settings,
                api=api,
            )

        except subprocess.TimeoutExpired:
            self._logger.error("FurMark benchmark timed out")
            return None
        except Exception as e:
            self._logger.error(f"FurMark benchmark failed: {e}")
            return None

    def _parse_result(
        self,
        name: str,
        output: str,
        log_file: Path | None,
        settings: dict[str, Any],
        api: str,
    ) -> FurMarkResult:
        """Parse FurMark output and log file.

        Args:
            name: Benchmark name.
            output: FurMark stdout.
            log_file: Path to GPU log CSV.
            settings: Benchmark settings.
            api: Graphics API used.

        Returns:
            FurMarkResult with parsed data.
        """
        result = FurMarkResult(
            name=name,
            timestamp=datetime.now().isoformat(),
            duration_seconds=settings["duration"],
            resolution=settings["resolution"],
            api=api.upper(),
            msaa=settings["msaa"],
        )

        # Parse stdout for score and FPS
        # FurMark outputs lines like:
        # Score: 12345
        # FPS: avg=123.4, min=100.0, max=150.0

        for line in output.split("\n"):
            line = line.strip()

            # Score
            if line.startswith("Score:"):
                match = re.search(r"Score:\s*(\d+)", line)
                if match:
                    result.score = int(match.group(1))

            # FPS
            if "FPS:" in line or "fps:" in line:
                avg_match = re.search(r"avg[=:]\s*([\d.]+)", line, re.I)
                min_match = re.search(r"min[=:]\s*([\d.]+)", line, re.I)
                max_match = re.search(r"max[=:]\s*([\d.]+)", line, re.I)

                if avg_match:
                    result.fps_avg = float(avg_match.group(1))
                if min_match:
                    result.fps_min = float(min_match.group(1))
                if max_match:
                    result.fps_max = float(max_match.group(1))

            # GPU name
            if "GPU:" in line or "Renderer:" in line:
                match = re.search(r"(?:GPU|Renderer):\s*(.+)", line)
                if match:
                    result.gpu_name = match.group(1).strip()

            # Driver
            if "Driver:" in line:
                match = re.search(r"Driver:\s*(.+)", line)
                if match:
                    result.gpu_driver = match.group(1).strip()

        # Parse GPU log file for temperature and power
        if log_file and log_file.exists():
            result.log_file = str(log_file)
            temps = []
            powers = []

            try:
                with open(log_file) as f:
                    lines = f.readlines()
                    if len(lines) > 1:
                        # Find column indices
                        header = lines[0].strip().split(",")
                        temp_idx = None
                        power_idx = None

                        for i, col in enumerate(header):
                            col_lower = col.lower()
                            if "temp" in col_lower:
                                temp_idx = i
                            if "power" in col_lower:
                                power_idx = i

                        # Parse data rows
                        for line in lines[1:]:
                            cols = line.strip().split(",")
                            if temp_idx is not None and temp_idx < len(cols):
                                with contextlib.suppress(ValueError):
                                    temps.append(float(cols[temp_idx]))
                            if power_idx is not None and power_idx < len(cols):
                                with contextlib.suppress(ValueError):
                                    powers.append(float(cols[power_idx]))

                if temps:
                    result.gpu_temp_max = max(temps)
                if powers:
                    result.gpu_power_max = max(powers)

            except Exception as e:
                self._logger.warning(f"Failed to parse GPU log: {e}")

        return result

    def save_result(self, result: FurMarkResult) -> Path:
        """Save benchmark result to disk.

        Args:
            result: FurMarkResult to save.

        Returns:
            Path to saved file.
        """
        return self._store.save(result.to_dict(), result.name)

    def load_result(self, path: Path) -> FurMarkResult | None:
        """Load benchmark result from disk.

        Args:
            path: Path to result JSON file.

        Returns:
            FurMarkResult or None if loading fails.
        """
        return self._store.load(
            path,
            lambda data: FurMarkResult(
                name=data.get("name", "unknown"),
                timestamp=data.get("timestamp", ""),
                duration_seconds=data.get("duration_seconds", 0),
                score=data.get("score", 0),
                fps_avg=data.get("fps_avg", 0),
                fps_min=data.get("fps_min", 0),
                fps_max=data.get("fps_max", 0),
                gpu_name=data.get("gpu_name", ""),
                gpu_driver=data.get("gpu_driver", ""),
                gpu_temp_max=data.get("gpu_temp_max", 0),
                gpu_power_max=data.get("gpu_power_max", 0),
                resolution=data.get("resolution", ""),
                api=data.get("api", ""),
                msaa=data.get("msaa", 0),
            ),
        )

    def list_results(self) -> list[Path]:
        """List all saved benchmark results, newest first.

        Returns:
            List of result file paths.
        """
        return self._store.list_files()

    def compare(
        self,
        before: FurMarkResult,
        after: FurMarkResult,
    ) -> FurMarkComparison:
        """Compare two benchmark results.

        Args:
            before: Baseline benchmark.
            after: Post-optimization benchmark.

        Returns:
            FurMarkComparison with analysis.
        """
        return FurMarkComparison(before=before, after=after)

    def get_presets(self) -> dict[str, dict[str, Any]]:
        """Get available benchmark presets.

        Returns:
            Dictionary of preset configurations.
        """
        return self.PRESETS.copy()
