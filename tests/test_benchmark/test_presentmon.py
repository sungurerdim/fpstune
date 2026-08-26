"""Tests for fpstune.benchmark.presentmon — pure-logic coverage.

Covers:
- FrameTimeStats dataclass + to_dict()
- BenchmarkCapture dataclass + to_dict()
- BenchmarkComparison property math (fps_improvement, fps_1_low_improvement,
  frametime_improvement, stutter_improvement, format_report, to_dict)
- PresentMonBenchmark._calculate_stats() — the core statistics engine
- PresentMonBenchmark.analyze_capture() — CSV parsing with realistic column names
- PresentMonBenchmark.is_installed / is_capturing state helpers
- PresentMonBenchmark.save_capture / load_capture round-trip
- PresentMonBenchmark.list_captures
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_benchmark(
    fps_avg=60.0, fps_1_low=45.0, fps_0_1_low=30.0, frametime_avg=16.6, stutter_count=0
):
    from fpstune.benchmark.presentmon import BenchmarkCapture, FrameTimeStats

    stats = FrameTimeStats(
        frame_count=600,
        fps_avg=fps_avg,
        fps_1_percent_low=fps_1_low,
        fps_0_1_percent_low=fps_0_1_low,
        frametime_avg=frametime_avg,
        stutter_count=stutter_count,
        stutter_percent=stutter_count / 600 * 100,
    )
    return BenchmarkCapture(
        name="test",
        timestamp="2026-06-24T12:00:00",
        game_name="TestGame",
        stats=stats,
    )


# ---------------------------------------------------------------------------
# FrameTimeStats
# ---------------------------------------------------------------------------


class TestFrameTimeStats:
    def test_defaults(self):
        from fpstune.benchmark.presentmon import FrameTimeStats

        s = FrameTimeStats()
        assert s.frame_count == 0
        assert s.fps_avg == 0.0
        assert s.frametimes == []
        assert s.timestamps == []

    def test_to_dict_keys(self):
        from fpstune.benchmark.presentmon import FrameTimeStats

        s = FrameTimeStats(
            frame_count=100,
            fps_avg=60.0,
            fps_1_percent_low=55.0,
            frametime_avg=16.666,
            stutter_count=2,
            stutter_percent=2.0,
        )
        d = s.to_dict()
        assert "frame_count" in d
        assert "fps_avg" in d
        assert "fps_1_percent_low" in d
        assert "stutter_count" in d
        # Raw lists must NOT appear (too large for API responses)
        assert "frametimes" not in d
        assert "timestamps" not in d

    def test_to_dict_rounding(self):
        from fpstune.benchmark.presentmon import FrameTimeStats

        s = FrameTimeStats(fps_avg=59.9876543, frametime_avg=16.6666666)
        d = s.to_dict()
        assert d["fps_avg"] == round(59.9876543, 2)
        assert d["frametime_avg"] == round(16.6666666, 3)


# ---------------------------------------------------------------------------
# BenchmarkCapture
# ---------------------------------------------------------------------------


class TestBenchmarkCapture:
    def test_to_dict_structure(self):
        from fpstune.benchmark.presentmon import BenchmarkCapture, FrameTimeStats

        cap = BenchmarkCapture(
            name="before",
            timestamp="2026-06-24T12:00:00",
            game_name="CS2",
            stats=FrameTimeStats(frame_count=1000, fps_avg=144.0),
            system_info={"cpu": "i9-14900K", "gpu": "RTX 4090"},
            notes="stock settings",
        )
        d = cap.to_dict()
        assert d["name"] == "before"
        assert d["game_name"] == "CS2"
        assert d["notes"] == "stock settings"
        assert isinstance(d["stats"], dict)
        assert d["system_info"]["cpu"] == "i9-14900K"


# ---------------------------------------------------------------------------
# BenchmarkComparison property math
# ---------------------------------------------------------------------------


class TestBenchmarkComparison:
    """Tests for the BenchmarkComparison class defined in presentmon.py."""

    def _make_comparison(
        self,
        before_fps=60.0,
        after_fps=66.0,
        before_1low=45.0,
        after_1low=50.0,
        before_ft_avg=16.6,
        after_ft_avg=15.1,
        before_stutter=10,
        after_stutter=5,
    ):
        from fpstune.benchmark.presentmon import BenchmarkComparison

        before = _make_benchmark(
            fps_avg=before_fps,
            fps_1_low=before_1low,
            frametime_avg=before_ft_avg,
            stutter_count=before_stutter,
        )
        after = _make_benchmark(
            fps_avg=after_fps,
            fps_1_low=after_1low,
            frametime_avg=after_ft_avg,
            stutter_count=after_stutter,
        )
        return BenchmarkComparison(before=before, after=after)

    def test_fps_improvement_exact(self):
        cmp = self._make_comparison(before_fps=60.0, after_fps=66.0)
        # (66 - 60) / 60 * 100 = 10.0 %
        assert abs(cmp.fps_improvement - 10.0) < 1e-9

    def test_fps_improvement_zero_before(self):
        cmp = self._make_comparison(before_fps=0.0, after_fps=60.0)
        assert cmp.fps_improvement == 0.0

    def test_fps_1_low_improvement_exact(self):
        cmp = self._make_comparison(before_1low=40.0, after_1low=50.0)
        # (50 - 40) / 40 * 100 = 25.0 %
        assert abs(cmp.fps_1_low_improvement - 25.0) < 1e-9

    def test_fps_1_low_improvement_zero_before(self):
        cmp = self._make_comparison(before_1low=0.0, after_1low=50.0)
        assert cmp.fps_1_low_improvement == 0.0

    def test_frametime_improvement_exact(self):
        cmp = self._make_comparison(before_ft_avg=20.0, after_ft_avg=16.0)
        # (20 - 16) / 20 * 100 = 20.0 %
        assert abs(cmp.frametime_improvement - 20.0) < 1e-9

    def test_frametime_improvement_regression(self):
        """Higher frametime after = negative improvement."""
        cmp = self._make_comparison(before_ft_avg=16.0, after_ft_avg=20.0)
        assert cmp.frametime_improvement < 0

    def test_frametime_improvement_zero_before(self):
        cmp = self._make_comparison(before_ft_avg=0.0, after_ft_avg=16.0)
        assert cmp.frametime_improvement == 0.0

    def test_stutter_improvement_exact(self):
        cmp = self._make_comparison(before_stutter=10, after_stutter=5)
        # (10 - 5) / 10 * 100 = 50.0 %
        assert abs(cmp.stutter_improvement - 50.0) < 1e-9

    def test_stutter_improvement_zero_before(self):
        cmp = self._make_comparison(before_stutter=0, after_stutter=0)
        assert cmp.stutter_improvement == 0.0

    def test_to_dict_improvements(self):
        cmp = self._make_comparison(before_fps=100.0, after_fps=110.0)
        d = cmp.to_dict()
        assert "before" in d
        assert "after" in d
        assert "improvements" in d
        # 10% improvement
        assert abs(d["improvements"]["fps_avg_percent"] - 10.0) < 0.01

    def test_format_report_contains_headers(self):
        cmp = self._make_comparison()
        report = cmp.format_report()
        assert "FPS BENCHMARK COMPARISON" in report
        assert "FRAME TIME" in report
        assert "STUTTER" in report
        assert "SUMMARY" in report


# ---------------------------------------------------------------------------
# PresentMonBenchmark._calculate_stats — the statistics engine
# ---------------------------------------------------------------------------


class TestCalculateStats:
    """Core statistics math — feed known arrays, assert exact computed values."""

    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        with patch("fpstune.benchmark.presentmon.get_config_dir", return_value=tmp_path):
            return PresentMonBenchmark(data_dir=tmp_path)

    def test_uniform_60fps_frametimes(self, bench):
        """60 fps = 16.6667 ms per frame. All equal frametimes."""
        ft = [16.6667] * 600  # 10 seconds of 60fps
        stats = bench._calculate_stats(ft, [])

        assert stats.frame_count == 600
        # avg frametime ≈ 16.6667
        assert abs(stats.frametime_avg - 16.6667) < 0.001
        assert stats.frametime_min == 16.6667
        assert stats.frametime_max == 16.6667
        # stdev is 0 for uniform series
        assert stats.frametime_stdev == 0
        # avg FPS = 1000/16.6667 ≈ 60.0
        assert abs(stats.fps_avg - 60.0) < 0.01
        # 1% low of uniform series = min = same fps
        assert abs(stats.fps_1_percent_low - 60.0) < 0.01
        # No stutter for uniform series
        assert stats.stutter_count == 0
        assert stats.stutter_percent == 0.0

    def test_uniform_120fps_frametimes(self, bench):
        """120 fps = 8.3333 ms per frame."""
        ft = [8.3333] * 1200
        stats = bench._calculate_stats(ft, [])

        assert abs(stats.fps_avg - 120.0) < 0.02
        assert stats.frame_count == 1200
        assert stats.stutter_count == 0

    def test_single_frame(self, bench):
        """Single frame — no stdev, percentile falls back to only element."""
        stats = bench._calculate_stats([16.6667], [])

        assert stats.frame_count == 1
        assert stats.frametime_stdev == 0
        assert abs(stats.fps_avg - 60.0) < 0.01
        assert stats.stutter_count == 0

    def test_empty_frametimes_returns_zeroed_stats(self, bench):
        """Empty input should return a stats object with zero counts."""
        stats = bench._calculate_stats([], [])
        assert stats.frame_count == 0
        assert stats.fps_avg == 0.0
        assert stats.stutter_count == 0

    def test_frametime_min_max(self, bench):
        ft = [8.333, 16.667, 33.333]  # 120fps, 60fps, 30fps frames
        stats = bench._calculate_stats(ft, [])
        assert stats.frametime_min == pytest.approx(8.333)
        assert stats.frametime_max == pytest.approx(33.333)

    def test_fps_min_max(self, bench):
        """fps_max comes from smallest frametime; fps_min from largest."""
        ft = [8.333, 16.667, 33.333]
        stats = bench._calculate_stats(ft, [])
        # fps for 8.333ms = 120.005; fps for 33.333ms = 30.0
        assert stats.fps_max > stats.fps_min
        assert stats.fps_min == pytest.approx(1000.0 / 33.333, rel=1e-3)
        assert stats.fps_max == pytest.approx(1000.0 / 8.333, rel=1e-3)

    def test_stutter_detection_exact(self, bench):
        """Frames > 2× avg frametime are counted as stutters."""
        # 9 normal 16.667ms frames + 1 stutter 50ms frame (50 > 2*16.667=33.33)
        ft = [16.667] * 9 + [50.0]
        stats = bench._calculate_stats(ft, [])
        avg = statistics.mean(ft)
        expected_stutters = sum(1 for f in ft if f > avg * 2)
        assert stats.stutter_count == expected_stutters
        assert abs(stats.stutter_percent - expected_stutters / 10 * 100) < 0.01

    def test_stutter_percent_zero_when_no_stutter(self, bench):
        ft = [16.667] * 100
        stats = bench._calculate_stats(ft, [])
        assert stats.stutter_percent == 0.0

    def test_duration_from_timestamps(self, bench):
        """Duration should be last_ts - first_ts when timestamps are provided."""
        ft = [16.667] * 60
        ts = [i * 0.01667 for i in range(60)]  # 0..~1 second
        stats = bench._calculate_stats(ft, ts)
        expected = ts[-1] - ts[0]
        assert abs(stats.duration_seconds - expected) < 0.001

    def test_duration_from_frametimes_when_no_ts(self, bench):
        """Duration = sum(ft) / 1000 when no timestamps provided."""
        ft = [16.667] * 60
        stats = bench._calculate_stats(ft, [])
        expected = sum(ft) / 1000.0
        assert abs(stats.duration_seconds - expected) < 0.001

    def test_1_percent_low_calculation(self, bench):
        """1% low = avg of the bottom 1% of fps values."""
        # 100 frames, 99 at 60fps, 1 at 30fps
        ft = [16.667] * 99 + [33.333]
        stats = bench._calculate_stats(ft, [])
        # Bottom 1% (1 frame) is the ~30fps frame
        fps_values = sorted([1000.0 / f for f in ft])
        idx_1 = int(len(fps_values) * 0.01)
        expected_1pct_low = statistics.mean(fps_values[: max(1, idx_1)])
        assert abs(stats.fps_1_percent_low - expected_1pct_low) < 0.01

    def test_99th_percentile_frametime(self, bench):
        """99th percentile frametime should be the 99th element of sorted frametimes."""
        # 100 frames where the 100th has a large spike
        ft = [16.667] * 99 + [50.0]
        stats = bench._calculate_stats(ft, [])
        sorted_ft = sorted(ft)
        idx = int(len(sorted_ft) * 0.99)
        expected = sorted_ft[idx] if idx < len(sorted_ft) else sorted_ft[-1]
        assert abs(stats.frametime_99th - expected) < 0.001

    def test_frametime_stdev_computed(self, bench):
        """Stdev should match stdlib statistics.stdev for the same data."""
        ft = [16.667, 8.333, 33.333, 16.667, 20.0]
        stats = bench._calculate_stats(ft, [])
        expected = statistics.stdev(ft)
        assert abs(stats.frametime_stdev - expected) < 1e-6


# ---------------------------------------------------------------------------
# PresentMonBenchmark.analyze_capture — CSV parsing
# ---------------------------------------------------------------------------


class TestAnalyzeCapture:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        with patch("fpstune.benchmark.presentmon.get_config_dir", return_value=tmp_path):
            return PresentMonBenchmark(data_dir=tmp_path)

    def _write_csv(
        self,
        path: Path,
        col: str,
        frametimes: list[float],
        ts_col: str | None = None,
        timestamps: list[float] | None = None,
    ) -> None:
        headers = [col]
        if ts_col and timestamps:
            headers.append(ts_col)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for i, ft in enumerate(frametimes):
                row = {col: str(ft)}
                if ts_col and timestamps:
                    row[ts_col] = str(timestamps[i])
                writer.writerow(row)

    def test_returns_none_for_missing_file(self, bench, tmp_path):
        result = bench.analyze_capture(tmp_path / "nonexistent.csv")
        assert result is None

    def test_parses_MsBetweenPresents_column(self, bench, tmp_path):
        csv_path = tmp_path / "capture.csv"
        ft = [16.667] * 100
        self._write_csv(csv_path, "MsBetweenPresents", ft)
        stats = bench.analyze_capture(csv_path)
        assert stats is not None
        assert stats.frame_count == 100
        assert abs(stats.fps_avg - 60.0) < 0.05

    def test_parses_msBetweenPresents_lowercase(self, bench, tmp_path):
        csv_path = tmp_path / "capture2.csv"
        ft = [8.333] * 200
        self._write_csv(csv_path, "msBetweenPresents", ft)
        stats = bench.analyze_capture(csv_path)
        assert stats is not None
        assert abs(stats.fps_avg - 120.0) < 0.1

    def test_parses_FrameTime_column(self, bench, tmp_path):
        csv_path = tmp_path / "capture3.csv"
        ft = [33.333] * 60
        self._write_csv(csv_path, "FrameTime", ft)
        stats = bench.analyze_capture(csv_path)
        assert stats is not None
        assert abs(stats.fps_avg - 30.0) < 0.1

    def test_parses_TimeInSeconds_column(self, bench, tmp_path):
        csv_path = tmp_path / "capture_ts.csv"
        ft = [16.667] * 60
        ts = [i * 0.01667 for i in range(60)]
        self._write_csv(csv_path, "MsBetweenPresents", ft, ts_col="TimeInSeconds", timestamps=ts)
        stats = bench.analyze_capture(csv_path)
        assert stats is not None
        # Duration should be derived from timestamps
        assert abs(stats.duration_seconds - (ts[-1] - ts[0])) < 0.001

    def test_returns_none_for_empty_csv(self, bench, tmp_path):
        csv_path = tmp_path / "empty.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["MsBetweenPresents"])
            writer.writeheader()
        result = bench.analyze_capture(csv_path)
        assert result is None

    def test_skips_zero_and_negative_frametimes(self, bench, tmp_path):
        """Zero and negative rows should be discarded."""
        csv_path = tmp_path / "zeros.csv"
        rows = [16.667, 0.0, -5.0, 16.667]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["MsBetweenPresents"])
            writer.writeheader()
            for v in rows:
                writer.writerow({"MsBetweenPresents": str(v)})
        stats = bench.analyze_capture(csv_path)
        # Only the two 16.667ms rows should count
        assert stats is not None
        assert stats.frame_count == 2

    def test_skips_non_numeric_rows(self, bench, tmp_path):
        """Non-numeric values should be silently skipped."""
        csv_path = tmp_path / "bad.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            f.write("MsBetweenPresents\n")
            f.write("16.667\n")
            f.write("bad_value\n")
            f.write("16.667\n")
        stats = bench.analyze_capture(csv_path)
        assert stats is not None
        assert stats.frame_count == 2


# ---------------------------------------------------------------------------
# PresentMonBenchmark helpers
# ---------------------------------------------------------------------------


class TestPresentMonHelpers:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        with patch("fpstune.benchmark.presentmon.get_config_dir", return_value=tmp_path):
            return PresentMonBenchmark(data_dir=tmp_path)

    def test_is_installed_false_when_no_exe(self, bench):
        assert bench.is_installed() is False

    def test_is_installed_true_when_exe_present(self, bench):
        exe_path = bench.presentmon_path
        exe_path.parent.mkdir(parents=True, exist_ok=True)
        exe_path.touch()
        assert bench.is_installed() is True

    def test_is_capturing_false_initially(self, bench):
        assert bench.is_capturing() is False

    def test_is_capturing_false_when_process_exited(self, bench):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # process exited
        bench._process = mock_proc
        assert bench.is_capturing() is False

    def test_is_capturing_true_when_running(self, bench):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        bench._process = mock_proc
        assert bench.is_capturing() is True

    def test_stop_capture_returns_none_when_not_running(self, bench):
        result = bench.stop_capture()
        assert result is None


# ---------------------------------------------------------------------------
# PresentMonBenchmark save/load round-trip
# ---------------------------------------------------------------------------


class TestSaveLoadCapture:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        with patch("fpstune.benchmark.presentmon.get_config_dir", return_value=tmp_path):
            return PresentMonBenchmark(data_dir=tmp_path)

    def test_save_creates_json_file(self, bench):
        cap = _make_benchmark(fps_avg=144.0)
        saved_path = bench.save_capture(cap)
        assert saved_path.exists()
        assert saved_path.suffix == ".json"

    def test_load_reconstructs_capture(self, bench):
        from fpstune.benchmark.presentmon import BenchmarkCapture, FrameTimeStats

        # Build a full capture with all numeric fields
        stats = FrameTimeStats(
            frame_count=600,
            duration_seconds=10.0,
            fps_avg=144.0,
            fps_min=120.0,
            fps_max=165.0,
            fps_1_percent_low=100.0,
            fps_0_1_percent_low=80.0,
            frametime_avg=6.944,
            frametime_min=6.06,
            frametime_max=8.33,
            frametime_stdev=0.3,
            frametime_99th=8.0,
            stutter_count=2,
            stutter_percent=0.33,
        )
        cap = BenchmarkCapture(
            name="after",
            timestamp="2026-06-24T12:00:00",
            game_name="CyberPunk 2077",
            stats=stats,
            system_info={"cpu": "Ryzen 9 7950X"},
            notes="tuned",
        )
        saved_path = bench.save_capture(cap)
        loaded = bench.load_capture(saved_path)

        assert loaded is not None
        assert loaded.name == "after"
        assert loaded.game_name == "CyberPunk 2077"
        assert loaded.notes == "tuned"
        assert abs(loaded.stats.fps_avg - 144.0) < 0.01
        assert abs(loaded.stats.fps_1_percent_low - 100.0) < 0.01
        assert loaded.stats.frame_count == 600

    def test_load_returns_none_for_invalid_json(self, bench, tmp_path):  # noqa: ARG002
        bad_file = bench._data_dir / "bad.json"
        bad_file.write_text("not json")
        result = bench.load_capture(bad_file)
        assert result is None

    def test_load_returns_none_for_missing_file(self, bench, tmp_path):  # noqa: ARG002
        result = bench.load_capture(tmp_path / "nonexistent.json")
        assert result is None

    def test_list_captures_includes_saved(self, bench):
        cap = _make_benchmark()
        bench.save_capture(cap)
        captures = bench.list_captures()
        assert len(captures) >= 1
        assert any(p.suffix == ".json" for p in captures)
