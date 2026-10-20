"""The CLI benchmark tree: every refusal says why, and no failure is a green tick.

These commands wrap the instruments (PresentMon, the DPC and network benches)
in click. The instruments themselves are tested in tests/test_benchmark;
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
        pm.install_error = "the download did not finish: timed out"

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["start"], input="y\n")

        assert result.exit_code == 0
        assert "Failed to install" in result.output
        assert "timed out" in result.output
        pm.start_capture.assert_not_called()

    def test_declining_the_download_installs_nothing(self, runner) -> None:
        """A capture used to download PresentMon unasked; the answer is the user's."""
        pm = MagicMock()
        pm.is_installed.return_value = False

        with patch.object(bench_cmds, "PresentMonBenchmark", return_value=pm):
            result = runner.invoke(bench_cmds.fps, ["start"], input="n\n")

        assert result.exit_code == 0
        pm.install.assert_not_called()
        pm.start_capture.assert_not_called()
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


