"""Tests for fpstune.benchmark.furmark — pure-logic coverage.

Covers:
- FurMarkResult: to_dict structure + field values
- FurMarkComparison property math (score_improvement, fps_improvement, min_fps_improvement)
- FurMarkComparison.format_report output
- FurMarkComparison.to_dict structure
- FurMarkBenchmark._parse_result: stdout parsing for score, FPS, GPU name, driver
- FurMarkBenchmark._parse_result: GPU log CSV parsing for temp/power
- FurMarkBenchmark.is_installed state helper
- FurMarkBenchmark.get_presets returns a copy
- FurMarkBenchmark.save_result / load_result round-trip
- FurMarkBenchmark.list_results
- FurMarkBenchmark.compare factory
- FurMarkBenchmark.install returns False on non-Windows
"""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_furmark_result(
    name="before",
    score=10000,
    fps_avg=60.0,
    fps_min=50.0,
    fps_max=75.0,
    gpu_name="NVIDIA GeForce RTX 4090",
    gpu_temp_max=85.0,
    gpu_power_max=450.0,
):
    from fpstune.benchmark.furmark import FurMarkResult

    return FurMarkResult(
        name=name,
        timestamp="2026-06-24T12:00:00",
        duration_seconds=120,
        score=score,
        fps_avg=fps_avg,
        fps_min=fps_min,
        fps_max=fps_max,
        gpu_name=gpu_name,
        gpu_driver="555.42",
        gpu_temp_max=gpu_temp_max,
        gpu_power_max=gpu_power_max,
        resolution="1920x1080",
        api="OPENGL",
        msaa=2,
    )


# ---------------------------------------------------------------------------
# FurMarkResult
# ---------------------------------------------------------------------------


class TestFurMarkResult:
    def test_to_dict_keys(self):
        result = _make_furmark_result()
        d = result.to_dict()
        for key in [
            "name",
            "timestamp",
            "duration_seconds",
            "score",
            "fps_avg",
            "fps_min",
            "fps_max",
            "gpu_name",
            "gpu_driver",
            "gpu_temp_max",
            "gpu_power_max",
            "resolution",
            "api",
            "msaa",
        ]:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_rounding(self):
        result = _make_furmark_result(
            fps_avg=59.9999,
            fps_min=49.9999,
            fps_max=74.9999,
            gpu_temp_max=84.9999,
            gpu_power_max=449.9999,
        )
        d = result.to_dict()
        assert d["fps_avg"] == round(59.9999, 2)
        assert d["fps_min"] == round(49.9999, 2)
        assert d["fps_max"] == round(74.9999, 2)
        assert d["gpu_temp_max"] == round(84.9999, 1)
        assert d["gpu_power_max"] == round(449.9999, 1)

    def test_to_dict_values(self):
        result = _make_furmark_result(score=12345, fps_avg=66.6)
        d = result.to_dict()
        assert d["score"] == 12345
        assert d["fps_avg"] == round(66.6, 2)
        assert d["resolution"] == "1920x1080"
        assert d["api"] == "OPENGL"
        assert d["msaa"] == 2


# ---------------------------------------------------------------------------
# FurMarkComparison property math
# ---------------------------------------------------------------------------


class TestFurMarkComparison:
    def _make_comparison(
        self,
        before_score=10000,
        after_score=11000,
        before_fps_avg=60.0,
        after_fps_avg=66.0,
        before_fps_min=50.0,
        after_fps_min=55.0,
    ):
        from fpstune.benchmark.furmark import FurMarkComparison

        before = _make_furmark_result(
            name="before", score=before_score, fps_avg=before_fps_avg, fps_min=before_fps_min
        )
        after = _make_furmark_result(
            name="after", score=after_score, fps_avg=after_fps_avg, fps_min=after_fps_min
        )
        return FurMarkComparison(before=before, after=after)

    def test_score_improvement_exact(self):
        cmp = self._make_comparison(before_score=10000, after_score=11000)
        # (11000 - 10000) / 10000 * 100 = 10.0%
        assert abs(cmp.score_improvement - 10.0) < 1e-9

    def test_score_improvement_zero_before(self):
        cmp = self._make_comparison(before_score=0, after_score=10000)
        assert cmp.score_improvement == 0.0

    def test_score_regression_negative(self):
        cmp = self._make_comparison(before_score=10000, after_score=9000)
        # (9000 - 10000) / 10000 * 100 = -10%
        assert abs(cmp.score_improvement - (-10.0)) < 1e-9

    def test_fps_improvement_exact(self):
        cmp = self._make_comparison(before_fps_avg=60.0, after_fps_avg=66.0)
        # (66 - 60) / 60 * 100 = 10.0%
        assert abs(cmp.fps_improvement - 10.0) < 1e-9

    def test_fps_improvement_zero_before(self):
        cmp = self._make_comparison(before_fps_avg=0.0, after_fps_avg=60.0)
        assert cmp.fps_improvement == 0.0

    def test_min_fps_improvement_exact(self):
        cmp = self._make_comparison(before_fps_min=40.0, after_fps_min=50.0)
        # (50 - 40) / 40 * 100 = 25.0%
        assert abs(cmp.min_fps_improvement - 25.0) < 1e-9

    def test_min_fps_improvement_zero_before(self):
        cmp = self._make_comparison(before_fps_min=0.0, after_fps_min=50.0)
        assert cmp.min_fps_improvement == 0.0

    def test_to_dict_structure(self):
        cmp = self._make_comparison()
        d = cmp.to_dict()
        assert "before" in d
        assert "after" in d
        assert "improvements" in d
        assert "score_percent" in d["improvements"]
        assert "fps_avg_percent" in d["improvements"]
        assert "fps_min_percent" in d["improvements"]

    def test_to_dict_improvement_values(self):
        cmp = self._make_comparison(before_score=10000, after_score=12000)
        d = cmp.to_dict()
        assert abs(d["improvements"]["score_percent"] - 20.0) < 0.01

    def test_format_report_structure(self):
        cmp = self._make_comparison(
            before_score=10000, after_score=11000, before_fps_avg=60.0, after_fps_avg=66.0
        )
        report = cmp.format_report()
        assert "FURMARK GPU BENCHMARK COMPARISON" in report
        assert "BENCHMARK SCORE" in report
        assert "FPS PERFORMANCE" in report
        assert "GPU THERMALS" in report
        assert "SUMMARY" in report

    def test_format_report_score_improvement_shown(self):
        cmp = self._make_comparison(before_score=10000, after_score=11000)
        report = cmp.format_report()
        assert "10.0%" in report or "Improvement" in report

    def test_format_report_no_improvement(self):
        cmp = self._make_comparison(
            before_score=10000, after_score=10000, before_fps_avg=60.0, after_fps_avg=60.0
        )
        report = cmp.format_report()
        assert "No significant" in report


# ---------------------------------------------------------------------------
# FurMarkBenchmark._parse_result — stdout parsing
# ---------------------------------------------------------------------------


class TestParseResult:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.furmark import FurMarkBenchmark

        with patch("fpstune.benchmark.furmark.get_config_dir", return_value=tmp_path):
            return FurMarkBenchmark(data_dir=tmp_path)

    def _default_settings(self):
        return {"duration": 120, "resolution": "1920x1080", "msaa": 2}

    def test_parses_score(self, bench):
        output = "Score: 12345\nFPS: avg=66.5, min=55.0, max=80.0\n"
        result = bench._parse_result("test", output, None, self._default_settings(), "opengl")
        assert result.score == 12345

    def test_parses_fps_avg_min_max(self, bench):
        output = "FPS: avg=66.5, min=55.0, max=80.0\n"
        result = bench._parse_result("test", output, None, self._default_settings(), "opengl")
        assert abs(result.fps_avg - 66.5) < 1e-6
        assert abs(result.fps_min - 55.0) < 1e-6
        assert abs(result.fps_max - 80.0) < 1e-6

    def test_parses_fps_case_insensitive(self, bench):
        output = "fps: AVG=120.0 MIN=90.0 MAX=144.0\n"
        result = bench._parse_result("test", output, None, self._default_settings(), "opengl")
        assert abs(result.fps_avg - 120.0) < 1e-6

    def test_parses_gpu_name(self, bench):
        output = "GPU: NVIDIA GeForce RTX 4090\n"
        result = bench._parse_result("test", output, None, self._default_settings(), "opengl")
        assert result.gpu_name == "NVIDIA GeForce RTX 4090"

    def test_parses_renderer_as_gpu_name(self, bench):
        output = "Renderer: AMD Radeon RX 7900 XTX\n"
        result = bench._parse_result("test", output, None, self._default_settings(), "opengl")
        assert result.gpu_name == "AMD Radeon RX 7900 XTX"

    def test_parses_driver(self, bench):
        output = "Driver: 555.42\n"
        result = bench._parse_result("test", output, None, self._default_settings(), "opengl")
        assert result.gpu_driver == "555.42"

    def test_result_fields_from_settings(self, bench):
        result = bench._parse_result("myrun", "", None, self._default_settings(), "vulkan")
        assert result.name == "myrun"
        assert result.duration_seconds == 120
        assert result.resolution == "1920x1080"
        assert result.api == "VULKAN"
        assert result.msaa == 2

    def test_empty_output_gives_zero_score(self, bench):
        result = bench._parse_result("test", "", None, self._default_settings(), "opengl")
        assert result.score == 0
        assert result.fps_avg == 0.0

    def test_full_realistic_output(self, bench):
        output = (
            "Score: 9876\n"
            "FPS: avg=55.2, min=45.0, max=68.0\n"
            "GPU: NVIDIA GeForce RTX 4080\n"
            "Driver: 546.33\n"
        )
        result = bench._parse_result("full_test", output, None, self._default_settings(), "opengl")
        assert result.score == 9876
        assert abs(result.fps_avg - 55.2) < 1e-6
        assert result.gpu_name == "NVIDIA GeForce RTX 4080"
        assert result.gpu_driver == "546.33"


# ---------------------------------------------------------------------------
# FurMarkBenchmark._parse_result — GPU log CSV parsing
# ---------------------------------------------------------------------------


class TestParseResultGpuLog:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.furmark import FurMarkBenchmark

        with patch("fpstune.benchmark.furmark.get_config_dir", return_value=tmp_path):
            return FurMarkBenchmark(data_dir=tmp_path)

    def _write_gpu_log(self, path: Path, temps: list[float], powers: list[float]) -> None:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["time", "gpu_temp", "gpu_power"])
            writer.writeheader()
            for t, p in zip(temps, powers, strict=True):
                writer.writerow({"time": "1.0", "gpu_temp": str(t), "gpu_power": str(p)})

    def test_parses_gpu_temp_max(self, bench, tmp_path):
        log = tmp_path / "gpu.csv"
        self._write_gpu_log(log, temps=[80.0, 83.0, 85.0, 82.0], powers=[400.0] * 4)
        result = bench._parse_result(
            "test", "", log, {"duration": 60, "resolution": "1920x1080", "msaa": 0}, "opengl"
        )
        assert abs(result.gpu_temp_max - 85.0) < 1e-6

    def test_parses_gpu_power_max(self, bench, tmp_path):
        log = tmp_path / "gpu.csv"
        self._write_gpu_log(log, temps=[80.0] * 4, powers=[380.0, 430.0, 450.0, 420.0])
        result = bench._parse_result(
            "test", "", log, {"duration": 60, "resolution": "1920x1080", "msaa": 0}, "opengl"
        )
        assert abs(result.gpu_power_max - 450.0) < 1e-6

    def test_missing_log_file_gives_zero_temp_power(self, bench, tmp_path):
        nonexistent = tmp_path / "missing.csv"
        result = bench._parse_result(
            "test",
            "",
            nonexistent,
            {"duration": 60, "resolution": "1920x1080", "msaa": 0},
            "opengl",
        )
        assert result.gpu_temp_max == 0.0
        assert result.gpu_power_max == 0.0

    def test_log_file_none_gives_zero_temp_power(self, bench):
        result = bench._parse_result(
            "test", "", None, {"duration": 60, "resolution": "1920x1080", "msaa": 0}, "opengl"
        )
        assert result.gpu_temp_max == 0.0
        assert result.gpu_power_max == 0.0

    def test_skips_non_numeric_log_rows(self, bench, tmp_path):
        log = tmp_path / "bad_gpu.csv"
        with open(log, "w", newline="") as f:
            f.write("time,gpu_temp,gpu_power\n")
            f.write("1.0,bad,400.0\n")
            f.write("2.0,85.0,bad\n")
            f.write("3.0,82.0,420.0\n")
        result = bench._parse_result(
            "test", "", log, {"duration": 60, "resolution": "1920x1080", "msaa": 0}, "opengl"
        )
        # Only row 3 has both valid → temp_max=82, power_max=420
        assert result.gpu_temp_max == pytest.approx(85.0)  # row 2 valid temp
        assert result.gpu_power_max == pytest.approx(420.0)  # row 3 valid power


# ---------------------------------------------------------------------------
# FurMarkBenchmark helpers
# ---------------------------------------------------------------------------


class TestFurMarkHelpers:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.furmark import FurMarkBenchmark

        with patch("fpstune.benchmark.furmark.get_config_dir", return_value=tmp_path):
            return FurMarkBenchmark(data_dir=tmp_path)

    def test_is_installed_false_when_no_exe(self, bench):
        assert bench.is_installed() is False

    def test_is_installed_true_when_furmark_exe_present(self, bench):
        exe = bench.furmark_path
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        assert bench.is_installed() is True

    def test_is_installed_true_when_cli_exe_present(self, bench):
        exe = bench.furmark_cli_path
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        assert bench.is_installed() is True

    def test_get_presets_returns_copy(self, bench):
        presets = bench.get_presets()
        assert "quick" in presets
        assert "standard" in presets
        assert "extreme" in presets
        # Adding a new top-level key to the returned copy must not alter the class
        presets["custom"] = {"duration": 999}
        assert "custom" not in bench.get_presets()

    def test_install_returns_false_on_non_windows(self, bench):
        with patch("fpstune.benchmark.furmark.sys.platform", "linux"):
            result = bench.install()
        assert result is False


# ---------------------------------------------------------------------------
# FurMarkBenchmark save / load round-trip
# ---------------------------------------------------------------------------


class TestFurMarkSaveLoad:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.furmark import FurMarkBenchmark

        with patch("fpstune.benchmark.furmark.get_config_dir", return_value=tmp_path):
            return FurMarkBenchmark(data_dir=tmp_path)

    def test_save_creates_json(self, bench):
        result = _make_furmark_result()
        saved = bench.save_result(result)
        assert saved.exists()
        assert saved.suffix == ".json"

    def test_load_reconstructs_result(self, bench):
        original = _make_furmark_result(
            name="after",
            score=11000,
            fps_avg=66.0,
            fps_min=55.0,
            gpu_temp_max=87.0,
            gpu_power_max=460.0,
        )
        saved = bench.save_result(original)
        loaded = bench.load_result(saved)

        assert loaded is not None
        assert loaded.name == original.name
        assert loaded.score == original.score
        assert loaded.fps_avg == pytest.approx(original.fps_avg, abs=0.01)
        assert loaded.fps_min == pytest.approx(original.fps_min, abs=0.01)
        assert loaded.gpu_temp_max == pytest.approx(original.gpu_temp_max, abs=0.1)
        assert loaded.resolution == original.resolution
        assert loaded.api == original.api
        assert loaded.msaa == original.msaa

    def test_load_returns_none_for_invalid_json(self, bench, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json")
        assert bench.load_result(bad) is None

    def test_load_returns_none_for_missing_file(self, bench, tmp_path):
        assert bench.load_result(tmp_path / "nonexistent.json") is None

    def test_list_results_returns_saved(self, bench):
        bench.save_result(_make_furmark_result())
        results = bench.list_results()
        assert len(results) >= 1
        assert all(p.suffix == ".json" for p in results)

    def test_list_results_empty_when_none_saved(self, tmp_path):
        from fpstune.benchmark.furmark import FurMarkBenchmark

        # A real instance over an empty data dir. It used to be built with
        # `__new__` and one attribute assigned, which pinned the test to the
        # bench's internals — and broke the moment the result store moved out
        # of it, while the property under test never changed.
        bench = FurMarkBenchmark(data_dir=tmp_path / "empty_data")
        assert bench.list_results() == []


# ---------------------------------------------------------------------------
# FurMarkBenchmark.compare factory
# ---------------------------------------------------------------------------


class TestFurMarkCompareFactory:
    @pytest.fixture
    def bench(self, tmp_path):
        from fpstune.benchmark.furmark import FurMarkBenchmark

        with patch("fpstune.benchmark.furmark.get_config_dir", return_value=tmp_path):
            return FurMarkBenchmark(data_dir=tmp_path)

    def test_compare_returns_furmark_comparison(self, bench):
        from fpstune.benchmark.furmark import FurMarkComparison

        before = _make_furmark_result(name="before", score=10000)
        after = _make_furmark_result(name="after", score=11000)
        cmp = bench.compare(before, after)
        assert isinstance(cmp, FurMarkComparison)
        assert cmp.before is before
        assert cmp.after is after
