"""Network latency benchmark for fpstune.

Measures network latency before/after applying network optimizations.
Uses ping and TCP connection tests to measure real-world latency.
"""

from __future__ import annotations

import logging
import socket
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fpstune.benchmark.result_store import ResultStore
from fpstune.utils.config import get_config_dir


@dataclass
class LatencyStats:
    """Network latency statistics."""

    ping_count: int = 0
    ping_avg: float = 0.0
    ping_min: float = 0.0
    ping_max: float = 0.0
    ping_stdev: float = 0.0
    ping_loss_percent: float = 0.0

    # TCP connection latency (more accurate for gaming)
    tcp_count: int = 0
    tcp_avg: float = 0.0
    tcp_min: float = 0.0
    tcp_max: float = 0.0
    tcp_stdev: float = 0.0

    # Jitter (variation in latency)
    jitter_avg: float = 0.0
    jitter_max: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ping_count": self.ping_count,
            "ping_avg": self.ping_avg,
            "ping_min": self.ping_min,
            "ping_max": self.ping_max,
            "ping_stdev": self.ping_stdev,
            "ping_loss_percent": self.ping_loss_percent,
            "tcp_count": self.tcp_count,
            "tcp_avg": self.tcp_avg,
            "tcp_min": self.tcp_min,
            "tcp_max": self.tcp_max,
            "tcp_stdev": self.tcp_stdev,
            "jitter_avg": self.jitter_avg,
            "jitter_max": self.jitter_max,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LatencyStats:
        """Create from dictionary."""
        return cls(
            ping_count=data.get("ping_count", 0),
            ping_avg=data.get("ping_avg", 0.0),
            ping_min=data.get("ping_min", 0.0),
            ping_max=data.get("ping_max", 0.0),
            ping_stdev=data.get("ping_stdev", 0.0),
            ping_loss_percent=data.get("ping_loss_percent", 0.0),
            tcp_count=data.get("tcp_count", 0),
            tcp_avg=data.get("tcp_avg", 0.0),
            tcp_min=data.get("tcp_min", 0.0),
            tcp_max=data.get("tcp_max", 0.0),
            tcp_stdev=data.get("tcp_stdev", 0.0),
            jitter_avg=data.get("jitter_avg", 0.0),
            jitter_max=data.get("jitter_max", 0.0),
        )


@dataclass
class NetworkBenchmarkResult:
    """Network benchmark result."""

    name: str
    timestamp: str
    target: str
    stats: LatencyStats
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "target": self.target,
            "stats": self.stats.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NetworkBenchmarkResult:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            timestamp=data["timestamp"],
            target=data["target"],
            stats=LatencyStats.from_dict(data["stats"]),
            notes=data.get("notes", ""),
        )


@dataclass
class NetworkComparison:
    """Comparison between two network benchmarks."""

    before: NetworkBenchmarkResult
    after: NetworkBenchmarkResult

    ping_improvement: float = 0.0
    tcp_improvement: float = 0.0
    jitter_improvement: float = 0.0

    def __post_init__(self) -> None:
        """Calculate improvements."""
        if self.before.stats.ping_avg > 0:
            self.ping_improvement = (
                (self.before.stats.ping_avg - self.after.stats.ping_avg)
                / self.before.stats.ping_avg
                * 100
            )

        if self.before.stats.tcp_avg > 0:
            self.tcp_improvement = (
                (self.before.stats.tcp_avg - self.after.stats.tcp_avg)
                / self.before.stats.tcp_avg
                * 100
            )

        if self.before.stats.jitter_avg > 0:
            self.jitter_improvement = (
                (self.before.stats.jitter_avg - self.after.stats.jitter_avg)
                / self.before.stats.jitter_avg
                * 100
            )

    def format_report(self) -> str:
        """Format comparison as a report."""
        lines = [
            "",
            "=" * 60,
            "NETWORK LATENCY COMPARISON",
            "=" * 60,
            "",
            f"Before: {self.before.name} ({self.before.timestamp[:19]})",
            f"After:  {self.after.name} ({self.after.timestamp[:19]})",
            f"Target: {self.before.target}",
            "",
            "-" * 60,
            f"{'Metric':<20} {'Before':>10} {'After':>10} {'Change':>10}",
            "-" * 60,
        ]

        # Ping latency
        ping_change = f"{self.ping_improvement:+.1f}%" if self.before.stats.ping_avg > 0 else "N/A"
        lines.append(
            f"{'Ping Avg (ms)':<20} {self.before.stats.ping_avg:>10.2f} "
            f"{self.after.stats.ping_avg:>10.2f} {ping_change:>10}"
        )
        lines.append(
            f"{'Ping Min (ms)':<20} {self.before.stats.ping_min:>10.2f} "
            f"{self.after.stats.ping_min:>10.2f}"
        )
        lines.append(
            f"{'Ping Max (ms)':<20} {self.before.stats.ping_max:>10.2f} "
            f"{self.after.stats.ping_max:>10.2f}"
        )

        # TCP latency
        if self.before.stats.tcp_count > 0:
            tcp_change = f"{self.tcp_improvement:+.1f}%"
            lines.append(
                f"{'TCP Avg (ms)':<20} {self.before.stats.tcp_avg:>10.2f} "
                f"{self.after.stats.tcp_avg:>10.2f} {tcp_change:>10}"
            )

        # Jitter
        jitter_change = (
            f"{self.jitter_improvement:+.1f}%" if self.before.stats.jitter_avg > 0 else "N/A"
        )
        lines.append(
            f"{'Jitter Avg (ms)':<20} {self.before.stats.jitter_avg:>10.2f} "
            f"{self.after.stats.jitter_avg:>10.2f} {jitter_change:>10}"
        )

        lines.append("-" * 60)

        # Summary
        best_improvement = max(self.ping_improvement, self.tcp_improvement)
        if best_improvement > 5:
            lines.append(f"\nLatency improved by up to {best_improvement:.1f}%")
        elif best_improvement > 0:
            lines.append(f"\nLatency improved by {best_improvement:.1f}%")
        elif best_improvement < -5:
            lines.append(f"\nWarning: Latency increased by {abs(best_improvement):.1f}%")
        else:
            lines.append("\nNo significant latency change detected")

        return "\n".join(lines)


class NetworkBenchmark:
    """Network latency benchmark runner."""

    # Default targets for testing
    DEFAULT_TARGETS = [
        ("8.8.8.8", 53),  # Google DNS
        ("1.1.1.1", 53),  # Cloudflare DNS
    ]

    # Game server regions (for more relevant testing)
    GAME_SERVERS = {
        "steam": ("store.steampowered.com", 443),
        "riot": ("status.riotgames.com", 443),
        "epic": ("www.epicgames.com", 443),
    }

    def __init__(self, results_dir: Path | None = None) -> None:
        """Initialize NetworkBenchmark.

        Args:
            results_dir: Directory to store results. Defaults to ~/.fpstune/network/
        """
        self._results_dir = results_dir or (get_config_dir() / "network")
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(__name__)
        self._store = ResultStore(self._results_dir, self._logger)

    def _ping_test(
        self,
        target: str,
        count: int = 50,
        progress_callback: Callable[[int], None] | None = None,
    ) -> tuple[list[float], int]:
        """Run ping test.

        Args:
            target: Target IP or hostname.
            count: Number of pings.
            progress_callback: Optional callback for progress updates.

        Returns:
            Tuple of (latencies in ms, lost packets count).
        """
        latencies: list[float] = []
        lost = 0

        if sys.platform != "win32":
            return latencies, count  # Not supported

        for i in range(count):
            try:
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "1000", target],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )

                if result.returncode == 0:
                    # Parse latency from output
                    # Windows: "Reply from x.x.x.x: bytes=32 time=5ms TTL=117"
                    for line in result.stdout.split("\n"):
                        if "time=" in line.lower() or "time<" in line.lower():
                            # Extract time value
                            if "time<" in line.lower():
                                # "time<1ms" means less than 1ms
                                latencies.append(0.5)
                            else:
                                parts = line.lower().split("time=")
                                if len(parts) >= 2:
                                    time_str = parts[1].split("ms")[0]
                                    try:
                                        latencies.append(float(time_str))
                                    except ValueError:
                                        lost += 1
                            break
                    else:
                        lost += 1
                else:
                    lost += 1
            except (subprocess.TimeoutExpired, OSError):
                lost += 1

            if progress_callback:
                progress_callback(int((i + 1) / count * 50))  # 0-50% for ping

        return latencies, lost

    def _tcp_test(
        self,
        target: str,
        port: int = 443,
        count: int = 20,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[float]:
        """Run TCP connection latency test.

        Measures time to establish TCP connection, which is more
        representative of game connection latency.

        Args:
            target: Target hostname or IP.
            port: Target port.
            count: Number of connections.
            progress_callback: Optional callback for progress updates.

        Returns:
            List of connection times in ms.
        """
        latencies: list[float] = []

        for i in range(count):
            try:
                start = time.perf_counter()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect((target, port))
                end = time.perf_counter()
                sock.close()

                latency_ms = (end - start) * 1000
                latencies.append(latency_ms)
            except OSError:
                pass  # Connection failed, skip

            if progress_callback:
                progress_callback(50 + int((i + 1) / count * 50))  # 50-100% for TCP

            # Small delay between tests
            time.sleep(0.05)

        return latencies

    def _calculate_jitter(self, latencies: list[float]) -> tuple[float, float]:
        """Calculate jitter (variation in latency).

        Args:
            latencies: List of latency measurements.

        Returns:
            Tuple of (average jitter, max jitter).
        """
        if len(latencies) < 2:
            return 0.0, 0.0

        # Jitter = difference between consecutive measurements
        jitters = [abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))]

        return statistics.mean(jitters), max(jitters)

    def run_benchmark(
        self,
        name: str = "benchmark",
        target: str = "8.8.8.8",
        tcp_target: tuple[str, int] | None = None,
        ping_count: int = 50,
        tcp_count: int = 20,
        progress_callback: Callable[[int], None] | None = None,
    ) -> NetworkBenchmarkResult | None:
        """Run network latency benchmark.

        Args:
            name: Name for this benchmark.
            target: Target for ping test.
            tcp_target: (host, port) for TCP test. Defaults to (target, 443).
            ping_count: Number of pings.
            tcp_count: Number of TCP connections.
            progress_callback: Optional callback for progress (0-100).

        Returns:
            NetworkBenchmarkResult or None if failed.
        """
        try:
            # Ping test
            ping_latencies, ping_lost = self._ping_test(target, ping_count, progress_callback)

            # TCP test
            tcp_host, tcp_port = tcp_target or (target, 443)
            tcp_latencies = self._tcp_test(tcp_host, tcp_port, tcp_count, progress_callback)

            # Calculate statistics
            stats = LatencyStats()

            if ping_latencies:
                stats.ping_count = len(ping_latencies)
                stats.ping_avg = statistics.mean(ping_latencies)
                stats.ping_min = min(ping_latencies)
                stats.ping_max = max(ping_latencies)
                stats.ping_stdev = (
                    statistics.stdev(ping_latencies) if len(ping_latencies) > 1 else 0.0
                )
                stats.ping_loss_percent = (ping_lost / ping_count) * 100

                stats.jitter_avg, stats.jitter_max = self._calculate_jitter(ping_latencies)

            if tcp_latencies:
                stats.tcp_count = len(tcp_latencies)
                stats.tcp_avg = statistics.mean(tcp_latencies)
                stats.tcp_min = min(tcp_latencies)
                stats.tcp_max = max(tcp_latencies)
                stats.tcp_stdev = statistics.stdev(tcp_latencies) if len(tcp_latencies) > 1 else 0.0

            return NetworkBenchmarkResult(
                name=name,
                timestamp=datetime.now().isoformat(),
                target=target,
                stats=stats,
            )
        except Exception as e:
            self._logger.error(f"Network benchmark failed: {e}")
            return None

    def save_result(self, result: NetworkBenchmarkResult) -> Path:
        """Save benchmark result.

        Args:
            result: Result to save.

        Returns:
            Path to saved file.
        """
        return self._store.save(result.to_dict(), result.name)

    def load_result(self, path: Path) -> NetworkBenchmarkResult | None:
        """Load benchmark result from file.

        Args:
            path: Path to result file.

        Returns:
            NetworkBenchmarkResult or None if failed.
        """
        return self._store.load(path, NetworkBenchmarkResult.from_dict)

    def list_results(self) -> list[Path]:
        """List saved benchmark results.

        Returns:
            List of result file paths, newest first.
        """
        return self._store.list_files()

    def compare(
        self,
        before: NetworkBenchmarkResult,
        after: NetworkBenchmarkResult,
    ) -> NetworkComparison:
        """Compare two benchmark results.

        Args:
            before: Before optimization result.
            after: After optimization result.

        Returns:
            NetworkComparison with analysis.
        """
        return NetworkComparison(before=before, after=after)

    def get_available_targets(self) -> dict[str, tuple[str, int]]:
        """Get available test targets.

        Returns:
            Dictionary of name -> (host, port).
        """
        targets = {"google_dns": ("8.8.8.8", 53), "cloudflare": ("1.1.1.1", 53)}
        targets.update(self.GAME_SERVERS)
        return targets
