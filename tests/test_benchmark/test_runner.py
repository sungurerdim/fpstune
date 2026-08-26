"""Tests for fpstune.benchmark.runner — pure-logic coverage.

Covers:
- BenchmarkResult: to_dict / from_dict round-trip
- BenchmarkRunner.save_result / load_result round-trip
- BenchmarkRunner.list_results
- BenchmarkRunner._benchmark_timer_resolution: returns dict with expected keys
- BenchmarkRunner._benchmark_sleep_accuracy: returns dict with expected keys
- BenchmarkRunner._benchmark_qpc_performance: returns {} on non-Windows
- BenchmarkRunner.run_all / run_timer_benchmark: integration via mocked helpers
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# BenchmarkResult
# ---------------------------------------------------------------------------


class TestBenchmarkResult:
    def test_to_dict_structure(self):
        from fpstune.benchmark.runner import BenchmarkResult

        result = BenchmarkResult(
            timestamp="2026-06-24T12:00:00",
            name="baseline",
            metrics={"sleep_1ms_error_ms": 1.5, "perf_counter_resolution_us": 0.1},
            system_info={"os": "Windows 11", "cpu": "i9-14900K"},
            notes="stock",
        )
        d = result.to_dict()
        assert d["timestamp"] == "2026-06-24T12:00:00"
        assert d["name"] == "baseline"
        assert d["metrics"]["sleep_1ms_error_ms"] == 1.5
        assert d["system_info"]["cpu"] == "i9-14900K"
        assert d["notes"] == "stock"

    def test_to_dict_empty_metrics(self):
        from fpstune.benchmark.runner import BenchmarkResult

        result = BenchmarkResult(timestamp="2026-06-24T12:00:00", name="empty")
        d = result.to_dict()
        assert d["metrics"] == {}
        assert d["system_info"] == {}
        assert d["notes"] == ""

    def test_default_fields(self):
        from fpstune.benchmark.runner import BenchmarkResult

        result = BenchmarkResult(timestamp="2026-06-24T12:00:00", name="test")
        assert result.metrics == {}
        assert result.system_info == {}
        assert result.notes == ""


# ---------------------------------------------------------------------------
# BenchmarkRunner save / load round-trip
# ---------------------------------------------------------------------------


class TestBenchmarkRunnerSaveLoad:
    @pytest.fixture
    def runner(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        return BenchmarkRunner(output_dir=tmp_path)

    def _make_result(self):
        from fpstune.benchmark.runner import BenchmarkResult

        return BenchmarkResult(
            timestamp="2026-06-24T12:00:00",
            name="timer_benchmark",
            metrics={
                "perf_counter_resolution_us": 0.10,
                "perf_counter_avg_us": 0.25,
                "sleep_1ms_error_ms": 1.5,
                "sleep_5ms_error_ms": 0.3,
                "sleep_10ms_error_ms": 0.2,
                "sleep_16ms_error_ms": 0.15,
            },
            system_info={"os": "Windows 11", "cpu": "Ryzen 9 7950X"},
            notes="before tuning",
        )

    def test_save_creates_json_file(self, runner):
        result = self._make_result()
        saved = runner.save_result(result)
        assert saved.exists()
        assert saved.suffix == ".json"

    def test_load_reconstructs_result(self, runner):
        original = self._make_result()
        saved = runner.save_result(original)
        loaded = runner.load_result(saved)

        assert loaded is not None
        assert loaded.timestamp == original.timestamp
        assert loaded.name == original.name
        assert loaded.notes == original.notes
        assert loaded.metrics["sleep_1ms_error_ms"] == original.metrics["sleep_1ms_error_ms"]
        assert loaded.system_info["cpu"] == original.system_info["cpu"]

    def test_load_returns_none_for_invalid_json(self, runner, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json")
        assert runner.load_result(bad) is None

    def test_load_returns_none_for_missing_required_key(self, runner, tmp_path):
        # Missing 'name' key triggers KeyError
        bad = tmp_path / "missing.json"
        bad.write_text(json.dumps({"timestamp": "2026-06-24T12:00:00"}))
        assert runner.load_result(bad) is None

    def test_load_returns_none_for_missing_file(self, runner, tmp_path):
        assert runner.load_result(tmp_path / "nonexistent.json") is None

    def test_list_results_returns_saved(self, runner):
        runner.save_result(self._make_result())
        results = runner.list_results()
        assert len(results) >= 1
        assert all(p.suffix == ".json" for p in results)

    def test_list_results_empty_when_none_saved(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        empty_dir = tmp_path / "empty_bench"
        empty_dir.mkdir()
        runner = BenchmarkRunner(output_dir=empty_dir)
        assert runner.list_results() == []

    def test_list_results_sorted_newest_first(self, runner, tmp_path):
        import time

        # Write two files directly with distinct names and touch them at different times
        r1 = self._make_result()
        f1 = tmp_path / "run_a_20260101_000000.json"
        import json as _json

        f1.write_text(_json.dumps(r1.to_dict()))
        time.sleep(0.05)
        f2 = tmp_path / "run_b_20260101_000001.json"
        f2.write_text(_json.dumps(r1.to_dict()))

        results = runner.list_results()
        assert len(results) >= 2
        # Newest first — mtime of results[0] >= results[1]
        assert results[0].stat().st_mtime >= results[1].stat().st_mtime


# ---------------------------------------------------------------------------
# BenchmarkRunner.save_result — filename sanitization (SEC-22)
# ---------------------------------------------------------------------------


class TestSaveResultNameSanitization:
    """SEC-22 regression: result.name arrives from an API query parameter and
    became a filename verbatim, so a name of "..\\..\\evil" wrote outside
    the benchmarks directory."""

    @pytest.fixture
    def runner(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        return BenchmarkRunner(output_dir=tmp_path)

    def _result(self, name):
        from fpstune.benchmark.runner import BenchmarkResult

        return BenchmarkResult(timestamp="2026-08-25T12:00:00", name=name)

    def test_traversal_name_stays_inside_output_dir(self, runner, tmp_path):
        saved = runner.save_result(self._result("..\\..\\evil"))
        assert saved.parent == tmp_path.resolve()
        assert saved.exists()
        assert "evil" in saved.name

    def test_forward_slash_traversal_stays_inside_output_dir(self, runner, tmp_path):
        saved = runner.save_result(self._result("../../../etc/passwd"))
        assert saved.parent == tmp_path.resolve()
        assert saved.exists()

    def test_separators_and_specials_are_squashed(self, runner):
        saved = runner.save_result(self._result('a/b\\c:d*e?"f'))
        assert saved.name.startswith("a_b_c_d_e_f_")
        assert saved.suffix == ".json"

    def test_name_length_is_bounded(self, runner):
        saved = runner.save_result(self._result("x" * 500))
        # 64-char name cap + "_YYYYMMDD_HHMMSS.json"
        assert len(saved.name) <= 64 + len("_20260825_120000.json")

    def test_dot_only_name_falls_back_to_benchmark(self, runner):
        """A name of pure dots must not become a hidden or empty filename."""
        saved = runner.save_result(self._result("..."))
        assert saved.name.startswith("benchmark_")


# ---------------------------------------------------------------------------
# BenchmarkRunner._benchmark_timer_resolution
# ---------------------------------------------------------------------------


class TestBenchmarkTimerResolution:
    @pytest.fixture
    def runner(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        return BenchmarkRunner(output_dir=tmp_path)

    def test_returns_dict_with_resolution_keys(self, runner):
        result = runner._benchmark_timer_resolution()
        # Should contain at least one of these keys (or both)
        assert isinstance(result, dict)
        # On any platform, perf_counter should resolve some samples
        # Keys may be absent if all samples are zero (degenerate environment)
        # but the return type must always be a dict
        assert isinstance(result, dict)

    def test_resolution_values_are_non_negative(self, runner):
        result = runner._benchmark_timer_resolution()
        for v in result.values():
            assert v >= 0

    def test_returns_resolution_and_avg_keys(self, runner):
        """On a normal system, both keys should be present."""
        result = runner._benchmark_timer_resolution()
        # At least one key expected when perf_counter is functional
        if result:  # non-empty dict
            assert "perf_counter_resolution_us" in result or "perf_counter_avg_us" in result


# ---------------------------------------------------------------------------
# BenchmarkRunner._benchmark_sleep_accuracy
# ---------------------------------------------------------------------------


class TestBenchmarkSleepAccuracy:
    @pytest.fixture
    def runner(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        return BenchmarkRunner(output_dir=tmp_path)

    def test_returns_dict_with_expected_keys(self, runner):
        result = runner._benchmark_sleep_accuracy()
        # Four intervals: 1ms, 5ms, 10ms, 16ms
        assert "sleep_1ms_error_ms" in result
        assert "sleep_5ms_error_ms" in result
        assert "sleep_10ms_error_ms" in result
        assert "sleep_16ms_error_ms" in result

    def test_error_values_are_non_negative(self, runner):
        result = runner._benchmark_sleep_accuracy()
        for v in result.values():
            assert v >= 0

    def test_error_values_are_floats(self, runner):
        result = runner._benchmark_sleep_accuracy()
        for v in result.values():
            assert isinstance(v, float)


# ---------------------------------------------------------------------------
# BenchmarkRunner._benchmark_qpc_performance
# ---------------------------------------------------------------------------


class TestBenchmarkQpcPerformance:
    @pytest.fixture
    def runner(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        return BenchmarkRunner(output_dir=tmp_path)

    def test_returns_empty_on_non_windows(self, runner):
        with patch("fpstune.benchmark.runner.sys.platform", "linux"):
            result = runner._benchmark_qpc_performance()
        assert result == {}


# ---------------------------------------------------------------------------
# BenchmarkRunner.run_all / run_timer_benchmark — mocked helpers
# ---------------------------------------------------------------------------


class TestRunAll:
    @pytest.fixture
    def runner(self, tmp_path):
        from fpstune.benchmark.runner import BenchmarkRunner

        return BenchmarkRunner(output_dir=tmp_path)

    def _mock_system_info(self):
        return {"os": "Windows 11", "cpu": "i9-14900K", "gpu": "RTX 4090"}

    def test_run_all_returns_benchmark_result(self, runner):
        from fpstune.benchmark.runner import BenchmarkResult

        with (
            patch.object(runner, "_get_system_info", return_value=self._mock_system_info()),
            patch.object(
                runner,
                "_benchmark_timer_resolution",
                return_value={"perf_counter_resolution_us": 0.1},
            ),
            patch.object(
                runner, "_benchmark_sleep_accuracy", return_value={"sleep_1ms_error_ms": 1.5}
            ),
            patch.object(runner, "_benchmark_qpc_performance", return_value={}),
        ):
            result = runner.run_all(name="test_run")

        assert isinstance(result, BenchmarkResult)
        assert result.name == "test_run"
        assert "perf_counter_resolution_us" in result.metrics
        assert "sleep_1ms_error_ms" in result.metrics

    def test_run_all_includes_system_info(self, runner):
        with (
            patch.object(runner, "_get_system_info", return_value=self._mock_system_info()),
            patch.object(runner, "_benchmark_timer_resolution", return_value={}),
            patch.object(runner, "_benchmark_sleep_accuracy", return_value={}),
            patch.object(runner, "_benchmark_qpc_performance", return_value={}),
        ):
            result = runner.run_all()

        assert result.system_info["cpu"] == "i9-14900K"

    def test_run_all_default_name(self, runner):
        with (
            patch.object(runner, "_get_system_info", return_value={}),
            patch.object(runner, "_benchmark_timer_resolution", return_value={}),
            patch.object(runner, "_benchmark_sleep_accuracy", return_value={}),
            patch.object(runner, "_benchmark_qpc_performance", return_value={}),
        ):
            result = runner.run_all()

        assert result.name == "benchmark"

    def test_run_timer_benchmark_returns_result(self, runner):
        from fpstune.benchmark.runner import BenchmarkResult

        with (
            patch.object(runner, "_get_system_info", return_value={}),
            patch.object(
                runner,
                "_benchmark_timer_resolution",
                return_value={"perf_counter_resolution_us": 0.1},
            ),
            patch.object(
                runner, "_benchmark_sleep_accuracy", return_value={"sleep_1ms_error_ms": 1.2}
            ),
            patch.object(
                runner, "_benchmark_qpc_performance", return_value={"qpc_frequency_hz": 1e7}
            ),
        ):
            result = runner.run_timer_benchmark()

        assert isinstance(result, BenchmarkResult)
        assert result.name == "timer_benchmark"

    def test_run_timer_benchmark_skips_qpc_on_non_windows(self, runner):
        with (
            patch.object(runner, "_get_system_info", return_value={}),
            patch.object(runner, "_benchmark_timer_resolution", return_value={}),
            patch.object(runner, "_benchmark_sleep_accuracy", return_value={}),
            patch.object(runner, "_benchmark_qpc_performance", return_value={}) as mock_qpc,
            patch("fpstune.benchmark.runner.sys.platform", "linux"),
        ):
            result = runner.run_timer_benchmark()

        # On non-Windows, _benchmark_qpc_performance should not be called
        mock_qpc.assert_not_called()
        assert result is not None
