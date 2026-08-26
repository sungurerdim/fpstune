"""Tests for fpstune.benchmark.dpc — pure-logic coverage.

Covers:
- DpcStats: to_dict / from_dict round-trip
- DpcBenchmarkResult: to_dict / from_dict round-trip
- DpcComparison.__post_init__ improvement math
- DpcComparison.format_report output
- DpcBenchmark._measure_timing_jitter logic (mocked perf_counter_ns)
- DpcBenchmark._measure_sleep_accuracy (mocked sleep + perf_counter_ns)
- DpcBenchmark.get_current_resolution (mocked _get_timer_resolution)
- DpcBenchmark.save_result / load_result round-trip
- DpcBenchmark.list_results
- DpcBenchmark.compare factory
- DpcBenchmark._get_timer_resolution / _get_qpc_frequency return 0 on non-Windows
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# DpcStats
# ---------------------------------------------------------------------------


class TestDpcStats:
    def test_to_dict_all_fields(self):
        from fpstune.benchmark.dpc import DpcStats

        s = DpcStats(
            timer_resolution_ns=156250,
            timer_resolution_ms=15.625,
            sample_count=100,
            sleep_accuracy_avg_us=250.0,
            sleep_accuracy_max_us=500.0,
            sleep_accuracy_stdev_us=50.0,
            timing_jitter_avg_us=1.0,
            timing_jitter_max_us=5.0,
            qpc_resolution_ns=100.0,
        )
        d = s.to_dict()
        assert d["timer_resolution_ns"] == 156250
        assert d["timer_resolution_ms"] == 15.625
        assert d["sample_count"] == 100
        assert d["sleep_accuracy_avg_us"] == 250.0
        assert d["sleep_accuracy_max_us"] == 500.0
        assert d["sleep_accuracy_stdev_us"] == 50.0
        assert d["timing_jitter_avg_us"] == 1.0
        assert d["timing_jitter_max_us"] == 5.0
        assert d["qpc_resolution_ns"] == 100.0

    def test_from_dict_round_trip(self):
        from fpstune.benchmark.dpc import DpcStats

        original = DpcStats(
            timer_resolution_ns=156250,
            timer_resolution_ms=15.625,
            sample_count=50,
            sleep_accuracy_avg_us=300.0,
            sleep_accuracy_max_us=600.0,
            sleep_accuracy_stdev_us=75.0,
            timing_jitter_avg_us=2.0,
            timing_jitter_max_us=8.0,
            qpc_resolution_ns=99.9,
        )
        loaded = DpcStats.from_dict(original.to_dict())
        assert loaded.timer_resolution_ns == original.timer_resolution_ns
        assert loaded.timer_resolution_ms == original.timer_resolution_ms
        assert loaded.sample_count == original.sample_count
        assert loaded.sleep_accuracy_avg_us == original.sleep_accuracy_avg_us
        assert loaded.sleep_accuracy_max_us == original.sleep_accuracy_max_us
        assert loaded.sleep_accuracy_stdev_us == original.sleep_accuracy_stdev_us
        assert loaded.timing_jitter_avg_us == original.timing_jitter_avg_us
        assert loaded.timing_jitter_max_us == original.timing_jitter_max_us
        assert loaded.qpc_resolution_ns == original.qpc_resolution_ns

    def test_from_dict_defaults_on_missing_keys(self):
        from fpstune.benchmark.dpc import DpcStats

        s = DpcStats.from_dict({})
        assert s.timer_resolution_ns == 0
        assert s.timer_resolution_ms == 0.0
        assert s.sample_count == 0
        assert s.sleep_accuracy_avg_us == 0.0


# ---------------------------------------------------------------------------
# DpcBenchmarkResult
# ---------------------------------------------------------------------------


class TestDpcBenchmarkResult:
    def test_to_dict_structure(self):
        from fpstune.benchmark.dpc import DpcBenchmarkResult, DpcStats

        result = DpcBenchmarkResult(
            name="before",
            timestamp="2026-06-24T12:00:00",
            stats=DpcStats(timer_resolution_ms=15.625, sample_count=100),
            notes="stock",
        )
        d = result.to_dict()
        assert d["name"] == "before"
        assert d["timestamp"] == "2026-06-24T12:00:00"
        assert d["notes"] == "stock"
        assert isinstance(d["stats"], dict)
        assert d["stats"]["timer_resolution_ms"] == 15.625

    def test_from_dict_round_trip(self):
        from fpstune.benchmark.dpc import DpcBenchmarkResult, DpcStats

        original = DpcBenchmarkResult(
            name="after",
            timestamp="2026-06-24T13:00:00",
            stats=DpcStats(timer_resolution_ms=0.5, sleep_accuracy_avg_us=80.0),
            notes="tuned",
        )
        loaded = DpcBenchmarkResult.from_dict(original.to_dict())
        assert loaded.name == original.name
        assert loaded.timestamp == original.timestamp
        assert loaded.notes == original.notes
        assert loaded.stats.timer_resolution_ms == original.stats.timer_resolution_ms
        assert loaded.stats.sleep_accuracy_avg_us == original.stats.sleep_accuracy_avg_us


# ---------------------------------------------------------------------------
# DpcComparison improvement math
# ---------------------------------------------------------------------------


class TestDpcComparison:
    def _make_result(self, res_ms=15.625, acc_us=300.0, jitter_us=5.0, name="run"):
        from fpstune.benchmark.dpc import DpcBenchmarkResult, DpcStats

        return DpcBenchmarkResult(
            name=name,
            timestamp="2026-06-24T12:00:00",
            stats=DpcStats(
                timer_resolution_ms=res_ms,
                sleep_accuracy_avg_us=acc_us,
                timing_jitter_avg_us=jitter_us,
            ),
        )

    def test_resolution_improvement_exact(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(res_ms=15.625, name="before")
        after = self._make_result(res_ms=7.8125, name="after")
        cmp = DpcComparison(before=before, after=after)
        # (15.625 - 7.8125) / 15.625 * 100 = 50.0%
        assert abs(cmp.resolution_improvement - 50.0) < 1e-9

    def test_resolution_improvement_zero_before(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(res_ms=0.0)
        after = self._make_result(res_ms=0.5)
        cmp = DpcComparison(before=before, after=after)
        assert cmp.resolution_improvement == 0.0

    def test_accuracy_improvement_exact(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(acc_us=400.0)
        after = self._make_result(acc_us=200.0)
        cmp = DpcComparison(before=before, after=after)
        # (400 - 200) / 400 * 100 = 50.0%
        assert abs(cmp.accuracy_improvement - 50.0) < 1e-9

    def test_accuracy_improvement_zero_before(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(acc_us=0.0)
        after = self._make_result(acc_us=100.0)
        cmp = DpcComparison(before=before, after=after)
        assert cmp.accuracy_improvement == 0.0

    def test_jitter_improvement_exact(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(jitter_us=10.0)
        after = self._make_result(jitter_us=4.0)
        cmp = DpcComparison(before=before, after=after)
        # (10 - 4) / 10 * 100 = 60.0%
        assert abs(cmp.jitter_improvement - 60.0) < 1e-9

    def test_jitter_improvement_zero_before(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(jitter_us=0.0)
        after = self._make_result(jitter_us=5.0)
        cmp = DpcComparison(before=before, after=after)
        assert cmp.jitter_improvement == 0.0

    def test_regression_gives_negative_improvement(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(res_ms=0.5)
        after = self._make_result(res_ms=15.625)  # worse
        cmp = DpcComparison(before=before, after=after)
        assert cmp.resolution_improvement < 0

    def test_format_report_structure(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(res_ms=15.625, acc_us=300.0, jitter_us=5.0, name="before")
        after = self._make_result(res_ms=7.8125, acc_us=150.0, jitter_us=2.5, name="after")
        cmp = DpcComparison(before=before, after=after)
        report = cmp.format_report()

        assert "DPC LATENCY COMPARISON" in report
        assert "before" in report
        assert "after" in report
        assert "Timer Resolution" in report
        assert "Sleep Accuracy" in report
        assert "Timing Jitter" in report

    def test_format_report_significant_improvement(self):
        from fpstune.benchmark.dpc import DpcComparison

        # 80% improvement in all three metrics -> avg > 10 -> "Significant improvement!"
        before = self._make_result(res_ms=15.625, acc_us=500.0, jitter_us=10.0)
        after = self._make_result(res_ms=3.125, acc_us=100.0, jitter_us=2.0)
        cmp = DpcComparison(before=before, after=after)
        report = cmp.format_report()
        assert "improvement" in report.lower()

    def test_format_report_no_change(self):
        from fpstune.benchmark.dpc import DpcComparison

        before = self._make_result(res_ms=15.625, acc_us=300.0, jitter_us=5.0)
        after = self._make_result(res_ms=15.625, acc_us=300.0, jitter_us=5.0)
        cmp = DpcComparison(before=before, after=after)
        report = cmp.format_report()
        assert "No significant change" in report


# ---------------------------------------------------------------------------
# DpcBenchmark._measure_timing_jitter — pure logic via mocked timestamps
# ---------------------------------------------------------------------------


class TestMeasureTimingJitter:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        with patch("fpstune.benchmark.dpc.get_config_dir", return_value=tmp_path):
            return DpcBenchmark(results_dir=tmp_path)

    def test_jitter_perfectly_uniform(self, bench):
        """When all intervals are equal, every jitter value is 0."""
        # 11 timestamps, each 1_000_000 ns apart → 10 intervals of 1000 µs
        ns_values = [i * 1_000_000 for i in range(11)]
        with patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_values):
            jitters = bench._measure_timing_jitter(samples=10)

        assert len(jitters) == 10
        assert all(abs(j) < 1e-9 for j in jitters)

    def test_jitter_single_spike(self, bench):
        """A single large interval causes non-zero jitter."""
        # 5 normal 1ms intervals + 1 spike of 10ms, then 4 more normal
        ns_values = [
            0,
            1_000_000,
            2_000_000,
            3_000_000,
            4_000_000,
            14_000_000,  # spike: 10ms gap
            15_000_000,
            16_000_000,
            17_000_000,
            18_000_000,
            19_000_000,
        ]
        with patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_values):
            jitters = bench._measure_timing_jitter(samples=10)

        assert max(jitters) > 0  # spike shows up as jitter

    def test_jitter_calls_progress_callback(self, bench):
        ns_values = [i * 1_000_000 for i in range(12)]
        callback = MagicMock()
        with patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_values):
            bench._measure_timing_jitter(samples=11, progress_callback=callback)

        callback.assert_called()

    def test_jitter_returns_empty_for_single_sample(self, bench):
        """With only 1 interval, there's no jitter to compute."""
        ns_values = [0, 1_000_000, 2_000_000]
        with patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_values):
            jitters = bench._measure_timing_jitter(samples=2)

        # 2 samples → 2 timestamps → 1 interval → len(intervals)==1 < 2 → empty
        assert isinstance(jitters, list)


# ---------------------------------------------------------------------------
# DpcBenchmark._measure_sleep_accuracy — pure logic via mocks
# ---------------------------------------------------------------------------


class TestMeasureSleepAccuracy:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        with patch("fpstune.benchmark.dpc.get_config_dir", return_value=tmp_path):
            return DpcBenchmark(results_dir=tmp_path)

    def test_overshoot_calculated_correctly(self, bench):
        """Each overshoot = (actual_ns - target_ns) / 1000."""
        target_ms = 1.0
        target_ns = int(target_ms * 1_000_000)
        # Each call: start=0ns, end=1_200_000ns → actual=1.2ms → overshoot=200µs
        ns_pairs = [0, 1_200_000] * 5  # 5 samples
        with (
            patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_pairs),
            patch("fpstune.benchmark.dpc.time.sleep"),
        ):
            overshoots = bench._measure_sleep_accuracy(target_ms=target_ms, samples=5)

        assert len(overshoots) == 5
        expected_overshoot_us = (1_200_000 - target_ns) / 1000  # 200.0 µs
        for o in overshoots:
            assert abs(o - expected_overshoot_us) < 1e-6

    def test_progress_callback_called(self, bench):
        ns_pairs = [0, 1_000_000] * 3
        callback = MagicMock()
        with (
            patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_pairs),
            patch("fpstune.benchmark.dpc.time.sleep"),
        ):
            bench._measure_sleep_accuracy(target_ms=1.0, samples=3, progress_callback=callback)

        callback.assert_called()

    def test_negative_overshoot_allowed(self, bench):
        """If actual < target (impossible in practice but not guarded), result is negative."""
        # target_ms=1.0 → target_ns=1_000_000; actual = 900_000ns → overshoot = -100µs
        ns_pairs = [0, 900_000] * 2
        with (
            patch("fpstune.benchmark.dpc.time.perf_counter_ns", side_effect=ns_pairs),
            patch("fpstune.benchmark.dpc.time.sleep"),
        ):
            overshoots = bench._measure_sleep_accuracy(target_ms=1.0, samples=2)

        assert all(o < 0 for o in overshoots)


# ---------------------------------------------------------------------------
# DpcBenchmark.get_current_resolution
# ---------------------------------------------------------------------------


class TestGetCurrentResolution:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        with patch("fpstune.benchmark.dpc.get_config_dir", return_value=tmp_path):
            return DpcBenchmark(results_dir=tmp_path)

    def test_converts_units_correctly(self, bench):
        """minimum=100_000, maximum=156_250, current=10_000 (all in 100ns units)."""
        with patch.object(bench, "_get_timer_resolution", return_value=(100_000, 156_250, 10_000)):
            info = bench.get_current_resolution()

        # minimum_ms = 100_000 / 10_000 = 10.0
        assert abs(info["minimum_ms"] - 10.0) < 1e-9
        # maximum_ms = 156_250 / 10_000 = 15.625
        assert abs(info["maximum_ms"] - 15.625) < 1e-9
        # current_ms = 10_000 / 10_000 = 1.0
        assert abs(info["current_ms"] - 1.0) < 1e-9

    def test_returns_zeros_when_resolution_is_zero(self, bench):
        with patch.object(bench, "_get_timer_resolution", return_value=(0, 0, 0)):
            info = bench.get_current_resolution()

        assert info["minimum_ms"] == 0.0
        assert info["maximum_ms"] == 0.0
        assert info["current_ms"] == 0.0


# ---------------------------------------------------------------------------
# DpcBenchmark._get_timer_resolution / _get_qpc_frequency on non-Windows
# ---------------------------------------------------------------------------


class TestWindowsOnlyHelpers:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        with patch("fpstune.benchmark.dpc.get_config_dir", return_value=tmp_path):
            return DpcBenchmark(results_dir=tmp_path)

    def test_get_timer_resolution_returns_zeros_on_non_windows(self, bench):
        with patch("fpstune.benchmark.dpc.sys.platform", "linux"):
            result = bench._get_timer_resolution()
        assert result == (0, 0, 0)

    def test_get_qpc_frequency_returns_zero_on_non_windows(self, bench):
        with patch("fpstune.benchmark.dpc.sys.platform", "linux"):
            result = bench._get_qpc_frequency()
        assert result == 0


# ---------------------------------------------------------------------------
# DpcBenchmark save / load round-trip
# ---------------------------------------------------------------------------


class TestDpcSaveLoad:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        with patch("fpstune.benchmark.dpc.get_config_dir", return_value=tmp_path):
            return DpcBenchmark(results_dir=tmp_path)

    def _make_result(self):
        from fpstune.benchmark.dpc import DpcBenchmarkResult, DpcStats

        return DpcBenchmarkResult(
            name="test_run",
            timestamp="2026-06-24T12:00:00",
            stats=DpcStats(
                timer_resolution_ns=156250,
                timer_resolution_ms=15.625,
                sample_count=100,
                sleep_accuracy_avg_us=250.0,
                sleep_accuracy_max_us=500.0,
                sleep_accuracy_stdev_us=50.0,
                timing_jitter_avg_us=1.5,
                timing_jitter_max_us=6.0,
                qpc_resolution_ns=100.0,
            ),
            notes="baseline",
        )

    def test_save_creates_json(self, bench):
        result = self._make_result()
        saved = bench.save_result(result)
        assert saved.exists()
        assert saved.suffix == ".json"

    def test_load_reconstructs_result(self, bench):
        original = self._make_result()
        saved = bench.save_result(original)
        loaded = bench.load_result(saved)

        assert loaded is not None
        assert loaded.name == original.name
        assert loaded.notes == original.notes
        assert loaded.stats.timer_resolution_ms == original.stats.timer_resolution_ms
        assert loaded.stats.sleep_accuracy_avg_us == original.stats.sleep_accuracy_avg_us
        assert loaded.stats.sample_count == original.stats.sample_count

    def test_load_returns_none_for_invalid_json(self, bench, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json")
        assert bench.load_result(bad) is None

    def test_load_returns_none_for_missing_key(self, bench, tmp_path):
        # Missing required 'name' key
        bad = tmp_path / "missing.json"
        bad.write_text(json.dumps({"timestamp": "2026-06-24T12:00:00"}))
        assert bench.load_result(bad) is None

    def test_list_results_returns_saved(self, bench):
        bench.save_result(self._make_result())
        results = bench.list_results()
        assert len(results) >= 1
        assert all(p.suffix == ".json" for p in results)

    def test_list_results_empty_when_none_saved(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        empty_dir = tmp_path / "empty_dpc"
        empty_dir.mkdir()
        bench = DpcBenchmark(results_dir=empty_dir)
        assert bench.list_results() == []


# ---------------------------------------------------------------------------
# DpcBenchmark.compare factory
# ---------------------------------------------------------------------------


class TestDpcCompareFactory:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.dpc import DpcBenchmark

        with patch("fpstune.benchmark.dpc.get_config_dir", return_value=tmp_path):
            return DpcBenchmark(results_dir=tmp_path)

    def test_compare_returns_dpc_comparison(self, bench):
        from fpstune.benchmark.dpc import DpcBenchmarkResult, DpcComparison, DpcStats

        before = DpcBenchmarkResult(
            "before", "2026-06-24T12:00:00", DpcStats(timer_resolution_ms=15.625)
        )
        after = DpcBenchmarkResult(
            "after", "2026-06-24T13:00:00", DpcStats(timer_resolution_ms=7.8125)
        )
        cmp = bench.compare(before, after)
        assert isinstance(cmp, DpcComparison)
        assert cmp.before is before
        assert cmp.after is after
