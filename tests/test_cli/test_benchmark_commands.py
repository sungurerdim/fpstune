"""The CLI benchmark tree: every refusal says why, and no failure is a green tick.

These commands wrap the instruments (FurMark, PresentMon, the DPC and network
benches) in click. The instruments themselves are tested in tests/test_benchmark;
what is untested until now is the command layer — the part that decides whether
a failure reaches the user as words or as a traceback, and whether a benchmark
that did not run can still print like one that did (C11 rule 3: what could not
be measured says so).

Each test names the concrete failure it guards against.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# The package __init__ re-exports a click Command named `benchmark`, which
# shadows the submodule as a package attribute — import_module reaches the
# module itself.
bench_cmds = import_module("fpstune.commands.benchmark")


@pytest.fixture
def runner():
    return CliRunner()


def _furmark(**overrides) -> MagicMock:
    fm = MagicMock()
    fm.is_installed.return_value = True
    fm.get_presets.return_value = {
        "quick": {"duration": 30, "resolution": "1280x720", "msaa": 0},
        "standard": {"duration": 60, "resolution": "1920x1080", "msaa": 4},
        "extreme": {"duration": 60, "resolution": "2560x1440", "msaa": 8},
    }
    for key, value in overrides.items():
        setattr(fm, key, value)
    return fm


class TestFpsCaptureLifecycle:
    """Start/stop are stateful; the states must be told apart in words."""

    def test_start_refuses_while_a_capture_is_running(self, runner) -> None:
        """Two overlapping PresentMon sessions would fight over the ETW trace;
        the second start must refuse and say how to stop the first."""
        pm = MagicMock()
        pm.is_installed.return_value = True
        pm.is_capturing.return_value = True

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["start"])

        assert result.exit_code == 0
        assert "already in progress" in result.output
        assert "fps stop" in result.output
        pm.start_capture.assert_not_called()

    def test_stop_without_a_capture_says_so(self, runner) -> None:
        """Stopping nothing must not invent a result to analyze."""
        pm = MagicMock()
        pm.is_capturing.return_value = False

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["stop"])

        assert result.exit_code == 0
        assert "No capture in progress" in result.output
        pm.stop_capture.assert_not_called()

    def test_stop_with_empty_capture_reports_no_data(self, runner) -> None:
        """A capture that produced no file (game exited instantly, ETW denied)
        must end in words, not in create_capture crashing on None."""
        pm = MagicMock()
        pm.is_capturing.return_value = True
        pm.stop_capture.return_value = None

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["stop"])

        assert result.exit_code == 0
        assert "No capture data found" in result.output
        pm.create_capture.assert_not_called()

    def test_failed_install_stops_the_start(self, runner) -> None:
        """Without the binary there is nothing to start; the command must not
        pretend a capture began."""
        pm = MagicMock()
        pm.is_installed.return_value = False
        pm.install.return_value = False

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["start"])

        assert result.exit_code == 0
        assert "Failed to install" in result.output
        pm.start_capture.assert_not_called()


class TestFpsAnalyzeAndCompare:
    def test_analyze_rejects_a_nonexistent_file_before_touching_it(self, runner) -> None:
        """click's Path(exists=True) is the guard; if it ever loosens, a typo'd
        path reaches the CSV parser and dies as a traceback."""
        result = runner.invoke(bench_cmds.fps, ["analyze", "no-such-capture.csv"])

        assert result.exit_code == 2
        assert "does not exist" in result.output

    def test_compare_names_the_side_that_could_not_load(self, runner) -> None:
        """'Could not load benchmark' without saying which of the two is
        useless — the user typed two names."""
        pm = MagicMock()
        with (
            patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm),
            patch.object(bench_cmds, "load_fps_capture", side_effect=[None, MagicMock()]),
        ):
            result = runner.invoke(bench_cmds.fps, ["compare", "-b", "missing", "-a", "there"])

        assert result.exit_code == 0
        assert "'before'" in result.output
        assert "missing" in result.output
        pm.compare.assert_not_called()

    def test_list_with_no_captures_gives_the_next_step(self, runner) -> None:
        pm = MagicMock()
        pm.list_captures.return_value = []

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["list"])

        assert result.exit_code == 0
        assert "No saved benchmarks" in result.output
        assert "fps start" in result.output


class TestGpuBench:
    def test_run_reports_failure_and_saves_nothing(self, runner) -> None:
        """A FurMark pass that returned nothing must not leave a saved result a
        later compare would treat as a measurement (C11)."""
        fm = _furmark()
        fm.run_benchmark.return_value = None

        with patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm):
            result = runner.invoke(bench_cmds.gpu_bench, ["run"])

        assert result.exit_code == 0
        assert "Benchmark failed" in result.output
        fm.save_result.assert_not_called()

    def test_run_stops_when_the_install_fails(self, runner) -> None:
        fm = _furmark()
        fm.is_installed.return_value = False
        fm.install.return_value = False

        with patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm):
            result = runner.invoke(bench_cmds.gpu_bench, ["run"])

        assert result.exit_code == 0
        assert "Failed to install" in result.output
        fm.run_benchmark.assert_not_called()

    def test_run_passes_the_overrides_through(self, runner) -> None:
        """--duration and --resolution silently ignored would benchmark a
        different load than the one the user asked for and label it the same."""
        fm = _furmark()
        fm.run_benchmark.return_value = None  # stop before display

        with patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm):
            runner.invoke(
                bench_cmds.gpu_bench,
                ["run", "-p", "quick", "-a", "vulkan", "-d", "15", "-r", "1024x768"],
            )

        fm.run_benchmark.assert_called_once_with(
            name="benchmark",
            preset="quick",
            api="vulkan",
            custom_duration=15,
            custom_resolution="1024x768",
        )

    def test_run_rejects_an_unknown_preset(self, runner) -> None:
        """The preset list is the contract with FurMark's config; a free-text
        preset would KeyError inside get_presets()."""
        result = runner.invoke(bench_cmds.gpu_bench, ["run", "-p", "ultra"])

        assert result.exit_code == 2
        assert "ultra" in result.output

    def test_compare_names_the_missing_side(self, runner) -> None:
        fm = _furmark()
        with (
            patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm),
            patch.object(bench_cmds, "load_furmark_result", side_effect=[MagicMock(), None]),
        ):
            result = runner.invoke(bench_cmds.gpu_bench, ["compare", "-b", "there", "-a", "gone"])

        assert result.exit_code == 0
        assert "'after'" in result.output
        assert "gone" in result.output
        fm.compare.assert_not_called()

    def test_presets_are_read_from_the_instrument(self, runner) -> None:
        """The table renders whatever get_presets() says — a hardcoded copy of
        the durations would drift the moment the instrument's presets change."""
        fm = _furmark()
        fm.get_presets.return_value = {
            "quick": {"duration": 7, "resolution": "640x480", "msaa": 0},
            "standard": {"duration": 77, "resolution": "1920x1080", "msaa": 4},
            "extreme": {"duration": 777, "resolution": "2560x1440", "msaa": 8},
        }

        with patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm):
            result = runner.invoke(bench_cmds.gpu_bench, ["presets"])

        assert result.exit_code == 0
        assert "7s" in result.output
        assert "77s" in result.output
        assert "777s" in result.output


class TestNetworkBench:
    def test_run_reports_failure_and_saves_nothing(self, runner) -> None:
        nb = MagicMock()
        nb.run_benchmark.return_value = None

        with patch("fpstune.benchmark.network.NetworkBenchmark", return_value=nb):
            result = runner.invoke(bench_cmds.network_bench, ["run"])

        assert result.exit_code == 0
        assert "Benchmark failed" in result.output
        nb.save_result.assert_not_called()

    def test_targets_render_what_the_instrument_offers(self, runner) -> None:
        """A target the instrument knows but the table drops is a target the
        user cannot choose; an unknown one must still list (blank description)."""
        nb = MagicMock()
        nb.get_available_targets.return_value = {
            "cloudflare": ("1.1.1.1", 443),
            "brand_new": ("192.0.2.1", 80),
        }

        with patch("fpstune.benchmark.network.NetworkBenchmark", return_value=nb):
            result = runner.invoke(bench_cmds.network_bench, ["targets"])

        assert result.exit_code == 0
        assert "1.1.1.1" in result.output
        assert "brand_new" in result.output

    def test_list_with_no_results_gives_the_next_step(self, runner) -> None:
        nb = MagicMock()
        nb.list_results.return_value = []

        with patch("fpstune.benchmark.network.NetworkBenchmark", return_value=nb):
            result = runner.invoke(bench_cmds.network_bench, ["list"])

        assert result.exit_code == 0
        assert "No saved benchmarks" in result.output
        assert "network-bench run" in result.output


class TestDpcBench:
    def test_run_reports_failure_and_saves_nothing(self, runner) -> None:
        db = MagicMock()
        db.run_benchmark.return_value = None

        with patch("fpstune.benchmark.dpc.DpcBenchmark", return_value=db):
            result = runner.invoke(bench_cmds.dpc_bench, ["run"])

        assert result.exit_code == 0
        assert "Benchmark failed" in result.output
        db.save_result.assert_not_called()

    @pytest.mark.parametrize(
        ("current_ms", "verdict"),
        [
            (0.5, "Excellent"),
            (1.0, "Good"),
            (10.0, "Suboptimal"),
            (15.6, "Poor"),
        ],
    )
    def test_resolution_verdict_tiers(self, runner, current_ms: float, verdict: str) -> None:
        """The tiers are the user-facing reading of a measured number; a shifted
        boundary would call Windows' 15.6 ms default acceptable."""
        db = MagicMock()
        db.get_current_resolution.return_value = {
            "current_ms": current_ms,
            "maximum_ms": 0.5,
            "minimum_ms": 15.6,
        }

        with patch("fpstune.benchmark.dpc.DpcBenchmark", return_value=db):
            result = runner.invoke(bench_cmds.dpc_bench, ["resolution"])

        assert result.exit_code == 0
        assert verdict in result.output

    def test_compare_names_the_missing_side(self, runner) -> None:
        db = MagicMock()
        with (
            patch("fpstune.benchmark.dpc.DpcBenchmark", return_value=db),
            patch.object(bench_cmds, "load_dpc_result", side_effect=[None, None]),
        ):
            result = runner.invoke(bench_cmds.dpc_bench, ["compare", "-b", "x", "-a", "y"])

        assert result.exit_code == 0
        assert "'before'" in result.output
        db.compare.assert_not_called()


class TestStandaloneBenchmark:
    def test_compare_flag_never_installs_anything(self, runner) -> None:
        """`benchmark --compare` is a read; downloading 100 MB of FurMark to
        show two saved results is a write the user did not ask for."""
        fm = _furmark()
        fm.is_installed.return_value = False

        with (
            patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm),
            patch.object(bench_cmds, "show_benchmark_comparison") as shown,
            patch.object(bench_cmds, "print_banner"),
        ):
            result = runner.invoke(bench_cmds.benchmark, ["--compare"])

        assert result.exit_code == 0
        fm.install.assert_not_called()
        shown.assert_called_once_with(fm)

    def test_failed_run_is_reported_not_saved(self, runner) -> None:
        fm = _furmark()
        fm.run_benchmark.return_value = None

        with (
            patch.object(bench_cmds, "FurMarkBenchmark", return_value=fm),
            patch.object(bench_cmds, "print_banner"),
        ):
            result = runner.invoke(bench_cmds.benchmark, [])

        assert result.exit_code == 0
        assert "Benchmark failed" in result.output
        fm.save_result.assert_not_called()
