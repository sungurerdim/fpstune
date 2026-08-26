"""Tests for fpstune.benchmark.compare — pure-logic coverage.

Covers:
- ComparisonMetric: difference, percent_change, is_improved, to_dict
- BenchmarkComparison.compare() factory: metric building, summary generation
- BenchmarkComparison.format_table()
- BenchmarkComparison.get_improved_metrics() / get_degraded_metrics()
- BenchmarkComparison.to_dict()
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(name: str = "baseline", **metrics):
    from fpstune.benchmark.runner import BenchmarkResult

    return BenchmarkResult(
        timestamp="2026-06-24T12:00:00",
        name=name,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# ComparisonMetric
# ---------------------------------------------------------------------------


class TestComparisonMetric:
    def test_difference_positive(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="latency", before=10.0, after=12.0)
        assert m.difference == pytest.approx(2.0)

    def test_difference_negative(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="latency", before=12.0, after=10.0)
        assert m.difference == pytest.approx(-2.0)

    def test_percent_change_increase(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="x", before=100.0, after=120.0)
        # (120 - 100) / 100 * 100 = +20%
        assert m.percent_change == pytest.approx(20.0)

    def test_percent_change_decrease(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="x", before=100.0, after=80.0)
        # (80 - 100) / 100 * 100 = -20%
        assert m.percent_change == pytest.approx(-20.0)

    def test_percent_change_zero_before(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="x", before=0.0, after=50.0)
        assert m.percent_change == 0.0

    def test_percent_change_no_change(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="x", before=50.0, after=50.0)
        assert m.percent_change == pytest.approx(0.0)

    def test_is_improved_lower_is_better_decreased(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="latency", before=10.0, after=8.0, lower_is_better=True)
        assert m.is_improved is True

    def test_is_improved_lower_is_better_increased(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="latency", before=8.0, after=10.0, lower_is_better=True)
        assert m.is_improved is False

    def test_is_improved_higher_is_better_increased(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="fps", before=60.0, after=80.0, lower_is_better=False)
        assert m.is_improved is True

    def test_is_improved_higher_is_better_decreased(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="fps", before=80.0, after=60.0, lower_is_better=False)
        assert m.is_improved is False

    def test_to_dict_keys(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="Sleep 1ms Error", before=1.5, after=0.9, unit="ms")
        d = m.to_dict()
        assert d["name"] == "Sleep 1ms Error"
        assert d["before"] == 1.5
        assert d["after"] == 0.9
        assert d["unit"] == "ms"
        assert "difference" in d
        assert "percent_change" in d
        assert "is_improved" in d

    def test_to_dict_percent_change_rounded(self):
        from fpstune.benchmark.compare import ComparisonMetric

        m = ComparisonMetric(name="x", before=3.0, after=4.0)
        d = m.to_dict()
        # percent_change = 33.3333... -> rounded to 2 dp
        assert d["percent_change"] == round((4.0 - 3.0) / 3.0 * 100, 2)


# ---------------------------------------------------------------------------
# BenchmarkComparison.compare() factory
# ---------------------------------------------------------------------------


class TestBenchmarkComparisonFactory:
    def test_compare_builds_metrics_for_known_keys(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result(
            "before",
            perf_counter_resolution_us=0.10,
            sleep_1ms_error_ms=1.5,
            qpc_frequency_hz=10_000_000.0,
        )
        after = _make_result(
            "after",
            perf_counter_resolution_us=0.10,
            sleep_1ms_error_ms=0.8,
            qpc_frequency_hz=10_000_000.0,
        )
        cmp = BenchmarkComparison.compare(before, after)

        names = {m.name for m in cmp.metrics}
        assert "Sleep 1ms Error" in names
        assert "Perf Counter Resolution" in names
        assert "QPC Frequency" in names

    def test_compare_unknown_metric_uses_key_as_name(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", custom_metric=5.0)
        after = _make_result("a", custom_metric=3.0)
        cmp = BenchmarkComparison.compare(before, after)

        names = {m.name for m in cmp.metrics}
        assert "custom_metric" in names

    def test_compare_summary_format(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=2.0, sleep_5ms_error_ms=2.0)
        after = _make_result("a", sleep_1ms_error_ms=1.0, sleep_5ms_error_ms=1.0)
        cmp = BenchmarkComparison.compare(before, after)

        # "2/2 metrics improved"
        assert "2/2" in cmp.summary
        assert "improved" in cmp.summary

    def test_compare_zero_improved_metrics(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=1.0)
        after = _make_result("a", sleep_1ms_error_ms=2.0)  # worse
        cmp = BenchmarkComparison.compare(before, after)

        assert cmp.get_improved_metrics() == []

    def test_compare_handles_missing_metric_in_one_result(self):
        """A metric only in 'after' should default before to 0."""
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b")
        after = _make_result("a", sleep_1ms_error_ms=1.0)
        cmp = BenchmarkComparison.compare(before, after)

        names = {m.name for m in cmp.metrics}
        assert "Sleep 1ms Error" in names
        metric = next(m for m in cmp.metrics if m.name == "Sleep 1ms Error")
        assert metric.before == 0.0
        assert metric.after == 1.0

    def test_compare_lower_is_better_flag_for_latency(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=2.0)
        after = _make_result("a", sleep_1ms_error_ms=1.0)
        cmp = BenchmarkComparison.compare(before, after)

        metric = next(m for m in cmp.metrics if m.name == "Sleep 1ms Error")
        assert metric.lower_is_better is True
        assert metric.is_improved is True  # decreased = improved

    def test_compare_higher_is_better_flag_for_frequency(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", qpc_frequency_hz=10_000_000.0)
        after = _make_result("a", qpc_frequency_hz=10_000_000.0)
        cmp = BenchmarkComparison.compare(before, after)

        metric = next(m for m in cmp.metrics if m.name == "QPC Frequency")
        assert metric.lower_is_better is False

    def test_compare_to_dict_structure(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_5ms_error_ms=2.0)
        after = _make_result("a", sleep_5ms_error_ms=1.5)
        cmp = BenchmarkComparison.compare(before, after)
        d = cmp.to_dict()

        assert "before" in d
        assert "after" in d
        assert "metrics" in d
        assert "summary" in d
        assert isinstance(d["metrics"], list)


# ---------------------------------------------------------------------------
# get_improved_metrics / get_degraded_metrics
# ---------------------------------------------------------------------------


class TestMetricFilters:
    def test_get_improved_metrics(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=2.0, sleep_5ms_error_ms=1.0)
        after = _make_result(
            "a",
            sleep_1ms_error_ms=1.0,
            sleep_5ms_error_ms=2.0,  # 5ms got worse
        )
        cmp = BenchmarkComparison.compare(before, after)

        improved = cmp.get_improved_metrics()
        improved_names = {m.name for m in improved}
        assert "Sleep 1ms Error" in improved_names
        assert "Sleep 5ms Error" not in improved_names

    def test_get_degraded_metrics(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=1.0)
        after = _make_result("a", sleep_1ms_error_ms=2.0)
        cmp = BenchmarkComparison.compare(before, after)

        degraded = cmp.get_degraded_metrics()
        assert len(degraded) == 1
        assert degraded[0].name == "Sleep 1ms Error"

    def test_unchanged_metric_not_in_degraded(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=1.0)
        after = _make_result("a", sleep_1ms_error_ms=1.0)
        cmp = BenchmarkComparison.compare(before, after)

        assert cmp.get_degraded_metrics() == []


# ---------------------------------------------------------------------------
# format_table()
# ---------------------------------------------------------------------------


class TestFormatTable:
    def test_format_table_contains_headers(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("before_run", sleep_1ms_error_ms=1.5)
        after = _make_result("after_run", sleep_1ms_error_ms=0.9)
        cmp = BenchmarkComparison.compare(before, after)

        table = cmp.format_table()
        assert "BENCHMARK COMPARISON" in table
        assert "before_run" in table
        assert "after_run" in table
        assert "Summary" in table or "summary" in table.lower()

    def test_format_table_contains_metric_name(self):
        from fpstune.benchmark.compare import BenchmarkComparison

        before = _make_result("b", sleep_1ms_error_ms=2.0)
        after = _make_result("a", sleep_1ms_error_ms=1.0)
        cmp = BenchmarkComparison.compare(before, after)

        table = cmp.format_table()
        assert "Sleep 1ms Error" in table
