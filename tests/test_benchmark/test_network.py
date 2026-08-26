"""Tests for fpstune.benchmark.network — pure-logic coverage.

Covers:
- LatencyStats: to_dict / from_dict round-trip
- NetworkBenchmarkResult: to_dict / from_dict round-trip
- NetworkComparison.__post_init__ improvement math + format_report
- NetworkBenchmark._calculate_jitter pure math
- NetworkBenchmark.run_benchmark with mocked _ping_test / _tcp_test
- NetworkBenchmark.save_result / load_result round-trip
- NetworkBenchmark.list_results
- NetworkBenchmark.compare factory
- NetworkBenchmark.get_available_targets
- NetworkBenchmark._ping_test: non-Windows returns empty immediately
"""

from __future__ import annotations

import json
import statistics
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# LatencyStats
# ---------------------------------------------------------------------------


class TestLatencyStats:
    def test_to_dict_keys(self):
        from fpstune.benchmark.network import LatencyStats

        s = LatencyStats(
            ping_count=50,
            ping_avg=12.5,
            ping_min=10.0,
            ping_max=20.0,
            ping_stdev=2.0,
            ping_loss_percent=2.0,
            tcp_count=20,
            tcp_avg=11.0,
            tcp_min=9.5,
            tcp_max=15.0,
            tcp_stdev=1.5,
            jitter_avg=0.8,
            jitter_max=3.0,
        )
        d = s.to_dict()
        for key in [
            "ping_count",
            "ping_avg",
            "ping_min",
            "ping_max",
            "ping_stdev",
            "ping_loss_percent",
            "tcp_count",
            "tcp_avg",
            "tcp_min",
            "tcp_max",
            "tcp_stdev",
            "jitter_avg",
            "jitter_max",
        ]:
            assert key in d

    def test_from_dict_round_trip(self):
        from fpstune.benchmark.network import LatencyStats

        original = LatencyStats(
            ping_count=50,
            ping_avg=12.5,
            ping_min=10.0,
            ping_max=20.0,
            ping_stdev=2.0,
            ping_loss_percent=4.0,
            tcp_count=20,
            tcp_avg=11.0,
            tcp_min=9.5,
            tcp_max=15.0,
            tcp_stdev=1.5,
            jitter_avg=0.8,
            jitter_max=3.0,
        )
        loaded = LatencyStats.from_dict(original.to_dict())
        assert loaded.ping_count == original.ping_count
        assert loaded.ping_avg == original.ping_avg
        assert loaded.ping_min == original.ping_min
        assert loaded.ping_loss_percent == original.ping_loss_percent
        assert loaded.tcp_avg == original.tcp_avg
        assert loaded.jitter_avg == original.jitter_avg

    def test_from_dict_defaults_on_missing_keys(self):
        from fpstune.benchmark.network import LatencyStats

        s = LatencyStats.from_dict({})
        assert s.ping_count == 0
        assert s.ping_avg == 0.0
        assert s.jitter_avg == 0.0


# ---------------------------------------------------------------------------
# NetworkBenchmarkResult
# ---------------------------------------------------------------------------


class TestNetworkBenchmarkResult:
    def test_to_dict_structure(self):
        from fpstune.benchmark.network import LatencyStats, NetworkBenchmarkResult

        result = NetworkBenchmarkResult(
            name="before",
            timestamp="2026-06-24T12:00:00",
            target="8.8.8.8",
            stats=LatencyStats(ping_avg=12.5, tcp_avg=11.0),
            notes="stock",
        )
        d = result.to_dict()
        assert d["name"] == "before"
        assert d["target"] == "8.8.8.8"
        assert d["notes"] == "stock"
        assert isinstance(d["stats"], dict)

    def test_from_dict_round_trip(self):
        from fpstune.benchmark.network import LatencyStats, NetworkBenchmarkResult

        original = NetworkBenchmarkResult(
            name="after",
            timestamp="2026-06-24T13:00:00",
            target="1.1.1.1",
            stats=LatencyStats(ping_avg=8.0, jitter_avg=0.5),
            notes="tuned",
        )
        loaded = NetworkBenchmarkResult.from_dict(original.to_dict())
        assert loaded.name == original.name
        assert loaded.target == original.target
        assert loaded.stats.ping_avg == original.stats.ping_avg
        assert loaded.stats.jitter_avg == original.stats.jitter_avg


# ---------------------------------------------------------------------------
# NetworkComparison improvement math
# ---------------------------------------------------------------------------


class TestNetworkComparison:
    def _make_result(self, ping_avg=20.0, tcp_avg=18.0, jitter_avg=2.0, name="run"):
        from fpstune.benchmark.network import LatencyStats, NetworkBenchmarkResult

        return NetworkBenchmarkResult(
            name=name,
            timestamp="2026-06-24T12:00:00",
            target="8.8.8.8",
            stats=LatencyStats(ping_avg=ping_avg, tcp_avg=tcp_avg, jitter_avg=jitter_avg),
        )

    def test_ping_improvement_exact(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(ping_avg=20.0)
        after = self._make_result(ping_avg=16.0)
        cmp = NetworkComparison(before=before, after=after)
        # (20 - 16) / 20 * 100 = 20.0%
        assert abs(cmp.ping_improvement - 20.0) < 1e-9

    def test_ping_improvement_zero_before(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(ping_avg=0.0)
        after = self._make_result(ping_avg=15.0)
        cmp = NetworkComparison(before=before, after=after)
        assert cmp.ping_improvement == 0.0

    def test_tcp_improvement_exact(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(tcp_avg=40.0)
        after = self._make_result(tcp_avg=30.0)
        cmp = NetworkComparison(before=before, after=after)
        # (40 - 30) / 40 * 100 = 25.0%
        assert abs(cmp.tcp_improvement - 25.0) < 1e-9

    def test_tcp_improvement_zero_before(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(tcp_avg=0.0)
        after = self._make_result(tcp_avg=20.0)
        cmp = NetworkComparison(before=before, after=after)
        assert cmp.tcp_improvement == 0.0

    def test_jitter_improvement_exact(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(jitter_avg=5.0)
        after = self._make_result(jitter_avg=2.5)
        cmp = NetworkComparison(before=before, after=after)
        # (5 - 2.5) / 5 * 100 = 50.0%
        assert abs(cmp.jitter_improvement - 50.0) < 1e-9

    def test_jitter_improvement_zero_before(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(jitter_avg=0.0)
        after = self._make_result(jitter_avg=1.0)
        cmp = NetworkComparison(before=before, after=after)
        assert cmp.jitter_improvement == 0.0

    def test_regression_gives_negative_improvement(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(ping_avg=10.0)
        after = self._make_result(ping_avg=15.0)  # worse
        cmp = NetworkComparison(before=before, after=after)
        assert cmp.ping_improvement < 0

    def test_format_report_structure(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(ping_avg=20.0, tcp_avg=18.0, jitter_avg=2.0, name="before")
        after = self._make_result(ping_avg=16.0, tcp_avg=14.0, jitter_avg=1.0, name="after")
        cmp = NetworkComparison(before=before, after=after)
        report = cmp.format_report()

        assert "NETWORK LATENCY COMPARISON" in report
        assert "before" in report
        assert "after" in report
        assert "Ping Avg" in report
        assert "Jitter" in report

    def test_format_report_significant_improvement(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(ping_avg=100.0)
        after = self._make_result(ping_avg=90.0)  # 10% improvement → > 5%
        cmp = NetworkComparison(before=before, after=after)
        report = cmp.format_report()
        assert "improved" in report.lower() or "Latency improved" in report

    def test_format_report_no_change(self):
        from fpstune.benchmark.network import NetworkComparison

        before = self._make_result(ping_avg=20.0, tcp_avg=18.0, jitter_avg=2.0)
        after = self._make_result(ping_avg=20.0, tcp_avg=18.0, jitter_avg=2.0)
        cmp = NetworkComparison(before=before, after=after)
        report = cmp.format_report()
        assert "No significant" in report

    def test_format_report_shows_tcp_section_when_tcp_data(self):
        from fpstune.benchmark.network import (
            LatencyStats,
            NetworkBenchmarkResult,
            NetworkComparison,
        )

        before = NetworkBenchmarkResult(
            name="b",
            timestamp="2026-06-24T12:00:00",
            target="8.8.8.8",
            stats=LatencyStats(ping_avg=20.0, tcp_count=20, tcp_avg=18.0),
        )
        after = NetworkBenchmarkResult(
            name="a",
            timestamp="2026-06-24T13:00:00",
            target="8.8.8.8",
            stats=LatencyStats(ping_avg=16.0, tcp_count=20, tcp_avg=14.0),
        )
        cmp = NetworkComparison(before=before, after=after)
        report = cmp.format_report()
        assert "TCP" in report


# ---------------------------------------------------------------------------
# NetworkBenchmark._calculate_jitter — pure math
# ---------------------------------------------------------------------------


class TestCalculateJitter:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.network import NetworkBenchmark

        with patch("fpstune.benchmark.network.get_config_dir", return_value=tmp_path):
            return NetworkBenchmark(results_dir=tmp_path)

    def test_empty_input(self, bench):
        avg, mx = bench._calculate_jitter([])
        assert avg == 0.0
        assert mx == 0.0

    def test_single_sample(self, bench):
        avg, mx = bench._calculate_jitter([15.0])
        assert avg == 0.0
        assert mx == 0.0

    def test_uniform_latencies_zero_jitter(self, bench):
        # All same → consecutive differences are all 0
        latencies = [15.0] * 10
        avg, mx = bench._calculate_jitter(latencies)
        assert avg == pytest.approx(0.0)
        assert mx == pytest.approx(0.0)

    def test_alternating_latencies_exact_jitter(self, bench):
        # Alternating 10ms / 20ms → diff always |10-20|=10 or |20-10|=10
        latencies = [10.0, 20.0, 10.0, 20.0, 10.0]
        avg, mx = bench._calculate_jitter(latencies)
        # All 4 consecutive diffs = 10.0
        assert avg == pytest.approx(10.0)
        assert mx == pytest.approx(10.0)

    def test_spike_shows_in_max_jitter(self, bench):
        latencies = [10.0, 10.0, 10.0, 100.0, 10.0]  # spike at index 3
        avg, mx = bench._calculate_jitter(latencies)
        # |100 - 10| = 90 should dominate max
        assert mx == pytest.approx(90.0)

    def test_jitter_matches_manual_calculation(self, bench):
        latencies = [12.0, 15.0, 11.0, 18.0, 14.0]
        # diffs: |15-12|=3, |11-15|=4, |18-11|=7, |14-18|=4
        expected_jitters = [3.0, 4.0, 7.0, 4.0]
        expected_avg = statistics.mean(expected_jitters)
        expected_max = max(expected_jitters)

        avg, mx = bench._calculate_jitter(latencies)
        assert avg == pytest.approx(expected_avg)
        assert mx == pytest.approx(expected_max)


# ---------------------------------------------------------------------------
# NetworkBenchmark.run_benchmark — mocked _ping_test / _tcp_test
# ---------------------------------------------------------------------------


class TestRunBenchmark:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.network import NetworkBenchmark

        with patch("fpstune.benchmark.network.get_config_dir", return_value=tmp_path):
            return NetworkBenchmark(results_dir=tmp_path)

    def test_run_benchmark_populates_ping_stats(self, bench):
        ping_latencies = [12.0, 13.0, 11.5, 12.5, 14.0]
        with (
            patch.object(bench, "_ping_test", return_value=(ping_latencies, 0)),
            patch.object(bench, "_tcp_test", return_value=[]),
        ):
            result = bench.run_benchmark(name="test", target="8.8.8.8", ping_count=5)

        assert result is not None
        assert result.stats.ping_count == 5
        assert abs(result.stats.ping_avg - statistics.mean(ping_latencies)) < 1e-6
        assert result.stats.ping_min == min(ping_latencies)
        assert result.stats.ping_max == max(ping_latencies)
        assert result.stats.ping_loss_percent == 0.0

    def test_run_benchmark_ping_loss_calculated(self, bench):
        # 2 out of 10 lost
        ping_latencies = [12.0] * 8
        with (
            patch.object(bench, "_ping_test", return_value=(ping_latencies, 2)),
            patch.object(bench, "_tcp_test", return_value=[]),
        ):
            result = bench.run_benchmark(name="test", target="8.8.8.8", ping_count=10)

        assert result is not None
        assert result.stats.ping_loss_percent == pytest.approx(20.0)

    def test_run_benchmark_populates_tcp_stats(self, bench):
        tcp_latencies = [10.0, 11.0, 12.0]
        with (
            patch.object(bench, "_ping_test", return_value=([], 0)),
            patch.object(bench, "_tcp_test", return_value=tcp_latencies),
        ):
            result = bench.run_benchmark(name="test", target="8.8.8.8")

        assert result is not None
        assert result.stats.tcp_count == 3
        assert abs(result.stats.tcp_avg - statistics.mean(tcp_latencies)) < 1e-6

    def test_run_benchmark_computes_jitter(self, bench):
        # Alternating ping latencies → jitter should be non-zero
        ping_latencies = [10.0, 20.0, 10.0, 20.0]
        with (
            patch.object(bench, "_ping_test", return_value=(ping_latencies, 0)),
            patch.object(bench, "_tcp_test", return_value=[]),
        ):
            result = bench.run_benchmark(name="test", target="8.8.8.8")

        assert result is not None
        assert result.stats.jitter_avg > 0

    def test_run_benchmark_returns_result_with_name_and_target(self, bench):
        with (
            patch.object(bench, "_ping_test", return_value=([15.0, 16.0], 0)),
            patch.object(bench, "_tcp_test", return_value=[]),
        ):
            result = bench.run_benchmark(name="my_run", target="1.1.1.1")

        assert result is not None
        assert result.name == "my_run"
        assert result.target == "1.1.1.1"

    def test_run_benchmark_empty_ping_and_tcp(self, bench):
        """All-empty results should still return a valid result."""
        with (
            patch.object(bench, "_ping_test", return_value=([], 5)),
            patch.object(bench, "_tcp_test", return_value=[]),
        ):
            result = bench.run_benchmark(name="empty", target="8.8.8.8")

        assert result is not None
        assert result.stats.ping_count == 0
        assert result.stats.tcp_count == 0


# ---------------------------------------------------------------------------
# NetworkBenchmark._ping_test on non-Windows
# ---------------------------------------------------------------------------


class TestPingTestNonWindows:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.network import NetworkBenchmark

        with patch("fpstune.benchmark.network.get_config_dir", return_value=tmp_path):
            return NetworkBenchmark(results_dir=tmp_path)

    def test_ping_test_returns_empty_on_non_windows(self, bench):
        with patch("fpstune.benchmark.network.sys.platform", "linux"):
            latencies, lost = bench._ping_test("8.8.8.8", count=10)
        assert latencies == []
        assert lost == 10  # all count treated as lost


# ---------------------------------------------------------------------------
# NetworkBenchmark save / load round-trip
# ---------------------------------------------------------------------------


class TestNetworkSaveLoad:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.network import NetworkBenchmark

        with patch("fpstune.benchmark.network.get_config_dir", return_value=tmp_path):
            return NetworkBenchmark(results_dir=tmp_path)

    def _make_result(self):
        from fpstune.benchmark.network import LatencyStats, NetworkBenchmarkResult

        return NetworkBenchmarkResult(
            name="test_run",
            timestamp="2026-06-24T12:00:00",
            target="8.8.8.8",
            stats=LatencyStats(
                ping_count=50,
                ping_avg=12.5,
                ping_min=10.0,
                ping_max=20.0,
                ping_stdev=2.0,
                ping_loss_percent=2.0,
                tcp_count=20,
                tcp_avg=11.0,
                tcp_min=9.5,
                tcp_max=15.0,
                tcp_stdev=1.5,
                jitter_avg=0.8,
                jitter_max=3.0,
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
        assert loaded.target == original.target
        assert loaded.stats.ping_avg == original.stats.ping_avg
        assert loaded.stats.tcp_avg == original.stats.tcp_avg
        assert loaded.stats.jitter_avg == original.stats.jitter_avg

    def test_load_returns_none_for_invalid_json(self, bench, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json")
        assert bench.load_result(bad) is None

    def test_load_returns_none_for_missing_key(self, bench, tmp_path):
        bad = tmp_path / "missing.json"
        bad.write_text(json.dumps({"timestamp": "2026-06-24T12:00:00"}))
        assert bench.load_result(bad) is None

    def test_list_results_returns_saved(self, bench):
        bench.save_result(self._make_result())
        results = bench.list_results()
        assert len(results) >= 1
        assert all(p.suffix == ".json" for p in results)

    def test_list_results_empty_when_none_saved(self, tmp_path):
        from fpstune.benchmark.network import NetworkBenchmark

        empty_dir = tmp_path / "empty_net"
        empty_dir.mkdir()
        bench = NetworkBenchmark(results_dir=empty_dir)
        assert bench.list_results() == []


# ---------------------------------------------------------------------------
# NetworkBenchmark.compare factory + get_available_targets
# ---------------------------------------------------------------------------


class TestNetworkMisc:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.network import NetworkBenchmark

        with patch("fpstune.benchmark.network.get_config_dir", return_value=tmp_path):
            return NetworkBenchmark(results_dir=tmp_path)

    def test_compare_returns_network_comparison(self, bench):
        from fpstune.benchmark.network import (
            LatencyStats,
            NetworkBenchmarkResult,
            NetworkComparison,
        )

        before = NetworkBenchmarkResult(
            "b", "2026-06-24T12:00:00", "8.8.8.8", LatencyStats(ping_avg=20.0)
        )
        after = NetworkBenchmarkResult(
            "a", "2026-06-24T13:00:00", "8.8.8.8", LatencyStats(ping_avg=16.0)
        )
        cmp = bench.compare(before, after)
        assert isinstance(cmp, NetworkComparison)
        assert cmp.before is before
        assert cmp.after is after

    def test_get_available_targets_includes_defaults(self, bench):
        targets = bench.get_available_targets()
        assert "google_dns" in targets
        assert "cloudflare" in targets
        # Should also include game servers
        assert "steam" in targets or len(targets) >= 2
