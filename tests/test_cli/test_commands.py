"""Tests for CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fpstune.cli import main


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestMainCommand:
    """Tests for main CLI group."""

    def test_help(self, runner):
        """Test help message."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "fpstune" in result.output.lower()
        assert "gaming" in result.output.lower() or "windows" in result.output.lower()

    def test_version(self, runner):
        """Test version output."""
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "fpstune" in result.output.lower()


class TestStatusCommand:
    """Tests for status command."""

    @patch("fpstune.commands.utils.elevate_if_needed")
    @patch("fpstune.commands.status.get_os_info")
    @patch("fpstune.commands.status.get_gpu_info")
    @patch("fpstune.commands.utils.is_admin")
    @patch("fpstune.commands.status.is_admin")
    def test_status_runs(
        self, mock_status_admin, mock_utils_admin, mock_gpu, mock_os, mock_elevate, runner
    ):
        """Test status command runs."""
        mock_status_admin.return_value = True
        mock_utils_admin.return_value = True  # Must return True to bypass admin check
        mock_elevate.return_value = False
        mock_os.return_value = MagicMock(
            edition="Windows 11",
            version="10.0.22621",
            build="22621",
            is_supported=True,
        )
        mock_gpu.return_value = None

        result = runner.invoke(main, ["status"])

        # Should run without error
        assert result.exit_code == 0


class TestNoCommandClaimsToHaveAppliedAnything:
    """`fpstune apply` applied nothing and said "Optimization complete!".

    It took `--module`, `--profile` and `--no-backup`, ignored all three, ran a
    FurMark pass, created a restore point, ran a second FurMark pass, printed a
    comparison of pure noise between two identical machine states, and finished
    with a green tick. A user who ran it had every reason to believe their
    machine had been tuned.

    `--profile` had also outlived the concept: scope replaced profiles across
    the whole product, so the flag named something that no longer existed.

    The before/after half was already `fpstune benchmark --after`. What is left
    is the browser, which is the one path that actually applies and verifies.
    """

    def test_it_is_gone_rather_than_quietly_doing_nothing(self, runner):
        result = runner.invoke(main, ["apply"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    @pytest.mark.parametrize(
        "option",
        ["--power", "--low-latency", "--vsync"],
    )
    @patch("fpstune.commands.utils.elevate_if_needed", return_value=False)
    @patch("fpstune.commands.utils.is_admin", return_value=True)
    def test_the_gpu_options_that_did_nothing_are_refused(self, _admin, _elevate, option, runner):
        """Same defect, smaller: accepted, ignored, and read as configuration.

        `--power maximum` is the sharpest case — it advertised the one GPU
        setting that costs heat all session and buys no frames, and it was the
        default. Refused now, so a script using it fails loudly instead of
        silently achieving nothing.
        """
        result = runner.invoke(main, ["gpu", option, "whatever"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()


class TestAReportIsNotInterleavedWithItsOwnLog:
    """Observed on a real run of `fpstune status`:

        Elevated  no - some settings cannot be read
        INFO | detect | GPU detection: Trying nvidia-smi...
        INFO | detect | GPU detected via nvidia-smi: ...
        Where this machine stands

    The detector narrating itself in the middle of a formatted report reads as
    part of the report. `serve` is different — it is a server and its log is
    the output — so the level depends on the subcommand rather than being one
    setting for the whole CLI.
    """

    @patch("fpstune.commands.utils.elevate_if_needed", return_value=False)
    @patch("fpstune.commands.utils.is_admin", return_value=True)
    @patch("fpstune.commands.gpu.get_gpu_info", return_value=None)
    def test_a_report_command_is_quiet_by_default(self, _gpu, _admin, _elevate, runner):
        import logging

        from fpstune.utils.logger import LOGGER_NAME

        runner.invoke(main, ["gpu"])

        assert logging.getLogger(LOGGER_NAME).level == logging.WARNING

    @patch("fpstune.commands.utils.elevate_if_needed", return_value=False)
    @patch("fpstune.commands.utils.is_admin", return_value=True)
    @patch("fpstune.commands.gpu.get_gpu_info", return_value=None)
    def test_verbose_still_turns_everything_back_on(self, _gpu, _admin, _elevate, runner):
        import logging

        from fpstune.utils.logger import LOGGER_NAME

        runner.invoke(main, ["-v", "gpu"])

        assert logging.getLogger(LOGGER_NAME).level == logging.DEBUG


class TestGpuCommand:
    @patch("fpstune.commands.utils.elevate_if_needed", return_value=False)
    @patch("fpstune.commands.utils.is_admin", return_value=True)
    @patch("fpstune.commands.gpu.get_gpu_info", return_value=None)
    def test_it_says_so_when_there_is_no_gpu(self, _gpu, _admin, _elevate, runner):
        """The failure path, which is the one a user with a broken driver hits."""
        result = runner.invoke(main, ["gpu"])

        assert result.exit_code == 0
        assert "no gpu detected" in result.output.lower()


class TestRemovedCommands:
    """backups/revert/state were removed with the manifest backup system."""

    @pytest.mark.parametrize("name", ["backups", "revert", "state"])
    def test_command_is_no_longer_registered(self, name, runner):
        result = runner.invoke(main, [name])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()
