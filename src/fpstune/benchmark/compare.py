"""Benchmark comparison for fpstune.

This module provides tools for comparing benchmark results
before and after applying optimizations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fpstune.benchmark.runner import BenchmarkResult


@dataclass
class ComparisonMetric:
    """A single metric comparison."""

    name: str
    before: float
    after: float
    unit: str = ""
    lower_is_better: bool = True

    @property
    def difference(self) -> float:
        """Absolute difference."""
        return self.after - self.before

    @property
    def percent_change(self) -> float:
        """Percent change."""
        if self.before == 0:
            return 0.0
        return ((self.after - self.before) / self.before) * 100

    @property
    def is_improved(self) -> bool:
        """Check if metric improved."""
        if self.lower_is_better:
            return self.after < self.before
        return self.after > self.before

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "difference": self.difference,
            "percent_change": round(self.percent_change, 2),
            "is_improved": self.is_improved,
            "unit": self.unit,
        }


@dataclass
class BenchmarkComparison:
    """Comparison of two benchmark results."""

    before: BenchmarkResult
    after: BenchmarkResult
    metrics: list[ComparisonMetric] = field(default_factory=list)
    summary: str = ""

    @classmethod
    def compare(
        cls,
        before: BenchmarkResult,
        after: BenchmarkResult,
    ) -> BenchmarkComparison:
        """Compare two benchmark results.

        Args:
            before: Baseline benchmark result.
            after: Post-optimization benchmark result.

        Returns:
            BenchmarkComparison with all metrics compared.
        """
        comparison = cls(before=before, after=after)

        # Define metric properties
        metric_info = {
            "perf_counter_resolution_us": ("Perf Counter Resolution", "µs", True),
            "perf_counter_avg_us": ("Perf Counter Avg", "µs", True),
            "sleep_1ms_error_ms": ("Sleep 1ms Error", "ms", True),
            "sleep_5ms_error_ms": ("Sleep 5ms Error", "ms", True),
            "sleep_10ms_error_ms": ("Sleep 10ms Error", "ms", True),
            "sleep_16ms_error_ms": ("Sleep 16ms Error", "ms", True),
            "qpc_call_overhead_ns": ("QPC Call Overhead", "ns", True),
            "qpc_call_min_ns": ("QPC Call Min", "ns", True),
            "qpc_frequency_hz": ("QPC Frequency", "Hz", False),
        }

        # Compare each metric
        all_metrics = set(before.metrics.keys()) | set(after.metrics.keys())

        for metric_name in sorted(all_metrics):
            before_value = before.metrics.get(metric_name, 0)
            after_value = after.metrics.get(metric_name, 0)

            info = metric_info.get(metric_name, (metric_name, "", True))
            display_name, unit, lower_is_better = info

            comparison.metrics.append(
                ComparisonMetric(
                    name=display_name,
                    before=before_value,
                    after=after_value,
                    unit=unit,
                    lower_is_better=lower_is_better,
                )
            )

        # Generate summary
        improved = sum(1 for m in comparison.metrics if m.is_improved)
        total = len(comparison.metrics)
        comparison.summary = f"{improved}/{total} metrics improved"

        return comparison

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "metrics": [m.to_dict() for m in self.metrics],
            "summary": self.summary,
        }

    def format_table(self) -> str:
        """Format comparison as ASCII table.

        Returns:
            Formatted table string.
        """
        lines = []
        lines.append("=" * 70)
        lines.append("BENCHMARK COMPARISON")
        lines.append("=" * 70)
        lines.append(f"Before: {self.before.name} ({self.before.timestamp})")
        lines.append(f"After:  {self.after.name} ({self.after.timestamp})")
        lines.append("-" * 70)
        lines.append(f"{'Metric':<30} {'Before':>12} {'After':>12} {'Change':>12}")
        lines.append("-" * 70)

        for metric in self.metrics:
            change_str = f"{metric.percent_change:+.1f}%"
            change_str = f"✓ {change_str}" if metric.is_improved else f"✗ {change_str}"

            before_str = f"{metric.before:.2f}{metric.unit}"
            after_str = f"{metric.after:.2f}{metric.unit}"

            lines.append(f"{metric.name:<30} {before_str:>12} {after_str:>12} {change_str:>12}")

        lines.append("-" * 70)
        lines.append(f"Summary: {self.summary}")
        lines.append("=" * 70)

        return "\n".join(lines)

    def get_improved_metrics(self) -> list[ComparisonMetric]:
        """Get list of improved metrics.

        Returns:
            List of ComparisonMetric that improved.
        """
        return [m for m in self.metrics if m.is_improved]

    def get_degraded_metrics(self) -> list[ComparisonMetric]:
        """Get list of degraded metrics.

        Returns:
            List of ComparisonMetric that got worse.
        """
        return [m for m in self.metrics if not m.is_improved and m.difference != 0]
