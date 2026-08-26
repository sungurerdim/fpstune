"""Tests for fpstune.core.dism — Windows DISM cleanup wrapper."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from fpstune.core.dism import CleanupResult, Dism


class TestDismAvailability:
    """Dism must report availability based on platform."""

    def test_unavailable_on_non_windows(self):
        """is_available must be False on non-Windows."""
        with patch("sys.platform", "linux"):
            dism = Dism()
            assert dism.is_available is False

    def test_available_on_windows(self):
        """is_available must be True on Windows."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            assert dism.is_available is True


class TestRunDism:
    """_run_dism must short-circuit on non-Windows and surface subprocess failures."""

    def test_returns_failure_when_unavailable(self):
        """_run_dism must return (False, error) without spawning a process."""
        with patch("sys.platform", "linux"):
            dism = Dism()
            with patch("subprocess.run") as mock_run:
                success, output = dism._run_dism("/Cleanup-Image", "/StartComponentCleanup")  # noqa: SLF001
                assert success is False
                assert "Not available" in output
                mock_run.assert_not_called()

    def test_success_path_returns_combined_output(self):
        """_run_dism on success must return concatenated stdout+stderr."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="component cleanup succeeded\n",
                    stderr="",
                )
                success, output = dism._run_dism("/Cleanup-Image", "/StartComponentCleanup")  # noqa: SLF001
                assert success is True
                assert "succeeded" in output

    def test_returns_failure_on_nonzero_return_code(self):
        """_run_dism must report failure when DISM exits non-zero."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="DISM error 0x800f0954",
                )
                success, output = dism._run_dism("/Cleanup-Image")  # noqa: SLF001
                assert success is False
                assert "0x800f0954" in output

    def test_timeout_returns_friendly_message(self):
        """TimeoutExpired must be converted to (False, 'Operation timed out')."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="dism", timeout=600)
                success, output = dism._run_dism("/Cleanup-Image")  # noqa: SLF001
                assert success is False
                assert "timed out" in output.lower()

    def test_unexpected_exception_returns_string_form(self):
        """Generic exceptions must be caught and surfaced as string."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = RuntimeError("dism.exe missing")
                success, output = dism._run_dism("/Cleanup-Image")  # noqa: SLF001
                assert success is False
                assert "dism.exe missing" in output


class TestComponentCleanup:
    """component_cleanup orchestrates _run_dism and folder-size measurement."""

    def test_unavailable_returns_cleanup_result_with_zero_freed(self):
        """component_cleanup on non-Windows must return failure CleanupResult."""
        with patch("sys.platform", "linux"):
            dism = Dism()
            result = dism.component_cleanup()
            assert isinstance(result, CleanupResult)
            assert result.success is False
            assert result.space_freed_mb == 0
            assert "Not available" in result.message

    def test_success_path_reports_space_freed(self):
        """When DISM succeeds and WinSxS shrinks, space_freed_mb must be the delta."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            # Initial size = 8000, final size = 6500 -> 1500 MB freed
            with (
                patch("os.environ.get", return_value="C:\\Windows"),
                patch("pathlib.Path.is_dir", return_value=True),
                patch.object(dism, "_get_folder_size", side_effect=[8000, 6500]),
                patch.object(dism, "_run_dism", return_value=(True, "OK")),
            ):
                result = dism.component_cleanup()
                assert result.success is True
                assert result.space_freed_mb == 1500

    def test_invalid_systemroot_returns_failure(self):
        """If SYSTEMROOT path doesn't exist, must return failure without running DISM."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            with (
                patch("os.environ.get", return_value="C:\\NoSuchPath"),
                patch("pathlib.Path.is_dir", return_value=False),
                patch.object(dism, "_run_dism") as mock_run,
            ):
                result = dism.component_cleanup()
                assert result.success is False
                assert "Invalid SystemRoot" in result.message
                mock_run.assert_not_called()

    def test_negative_delta_clamped_to_zero(self):
        """If WinSxS appears to grow during cleanup, space_freed must clamp to 0."""
        with patch("sys.platform", "win32"):
            dism = Dism()
            with (
                patch("os.environ.get", return_value="C:\\Windows"),
                patch("pathlib.Path.is_dir", return_value=True),
                patch.object(dism, "_get_folder_size", side_effect=[5000, 5500]),
                patch.object(dism, "_run_dism", return_value=(True, "")),
            ):
                result = dism.component_cleanup()
                assert result.space_freed_mb == 0
