"""Tests for fpstune.utils.admin — privilege detection and elevation."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from fpstune.utils.admin import (
    elevate_if_needed,
    get_elevation_error_message,
    is_admin,
    require_admin,
)


class TestIsAdmin:
    """Behavior of is_admin() across platforms and failure modes."""

    def test_returns_true_on_windows_when_shell32_reports_admin(self):
        """is_admin should return True when Windows IsUserAnAdmin returns non-zero."""
        with patch("sys.platform", "win32"):
            mock_shell32 = MagicMock()
            mock_shell32.IsUserAnAdmin.return_value = 1
            mock_windll = MagicMock(shell32=mock_shell32)
            with patch("fpstune.utils.admin.ctypes") as mock_ctypes:
                mock_ctypes.windll = mock_windll
                assert is_admin() is True

    def test_returns_false_on_windows_when_shell32_reports_non_admin(self):
        """is_admin should return False when Windows IsUserAnAdmin returns 0."""
        with patch("sys.platform", "win32"):
            mock_shell32 = MagicMock()
            mock_shell32.IsUserAnAdmin.return_value = 0
            mock_windll = MagicMock(shell32=mock_shell32)
            with patch("fpstune.utils.admin.ctypes") as mock_ctypes:
                mock_ctypes.windll = mock_windll
                assert is_admin() is False

    def test_returns_false_on_windows_when_ctypes_unavailable(self):
        """is_admin should swallow AttributeError/OSError from ctypes and return False."""
        with (
            patch("sys.platform", "win32"),
            patch("fpstune.utils.admin.ctypes") as mock_ctypes,
        ):
            mock_ctypes.windll.shell32.IsUserAnAdmin.side_effect = OSError("no syscall")
            assert is_admin() is False

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path")
    def test_returns_true_on_unix_when_uid_zero(self):
        """is_admin should check geteuid() == 0 on non-Windows."""
        with (
            patch("sys.platform", "linux"),
            patch("os.geteuid", return_value=0, create=True),
        ):
            assert is_admin() is True

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path")
    def test_returns_false_on_unix_when_uid_nonzero(self):
        """is_admin should return False on non-Windows when uid != 0."""
        with (
            patch("sys.platform", "linux"),
            patch("os.geteuid", return_value=1000, create=True),
        ):
            assert is_admin() is False


class TestRequireAdmin:
    """require_admin decorator must raise PermissionError on non-admin."""

    def test_raises_when_not_admin(self):
        """Calling decorated function without admin must raise PermissionError."""

        @require_admin
        def protected() -> str:
            return "ok"

        with (
            patch("fpstune.utils.admin.is_admin", return_value=False),
            pytest.raises(PermissionError, match="Administrator privileges"),
        ):
            protected()

    def test_executes_when_admin(self):
        """Calling decorated function as admin must run and return value."""

        @require_admin
        def protected(x: int, y: int) -> int:
            return x + y

        with patch("fpstune.utils.admin.is_admin", return_value=True):
            assert protected(2, 3) == 5

    def test_preserves_function_metadata(self):
        """@functools.wraps should preserve __name__ and __doc__."""

        @require_admin
        def documented_function() -> None:
            """My docstring."""

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "My docstring."


class TestElevateIfNeeded:
    """elevate_if_needed must not re-elevate when already admin and must return False on POSIX."""

    def test_returns_false_when_already_admin(self):
        """When already admin, elevate_if_needed must short-circuit to False."""
        with patch("fpstune.utils.admin.is_admin", return_value=True):
            assert elevate_if_needed() is False

    def test_returns_false_on_non_windows(self):
        """On non-Windows platforms, elevate_if_needed must return False without ShellExecute."""
        with (
            patch("fpstune.utils.admin.is_admin", return_value=False),
            patch("sys.platform", "linux"),
        ):
            assert elevate_if_needed() is False

    def test_returns_false_when_uac_denied(self):
        """When ShellExecuteW returns <=32 (denied/error), elevate_if_needed must return False."""
        with (
            patch("fpstune.utils.admin.is_admin", return_value=False),
            patch("sys.platform", "win32"),
            patch("fpstune.utils.admin.ctypes") as mock_ctypes,
        ):
            mock_ctypes.windll.shell32.ShellExecuteW.return_value = 5  # access denied
            assert elevate_if_needed() is False

    def test_handles_shellexecute_failure(self):
        """If ShellExecuteW raises OSError, elevate_if_needed must return False."""
        with (
            patch("fpstune.utils.admin.is_admin", return_value=False),
            patch("sys.platform", "win32"),
            patch("fpstune.utils.admin.ctypes") as mock_ctypes,
        ):
            mock_ctypes.windll.shell32.ShellExecuteW.side_effect = OSError("no shell")
            assert elevate_if_needed() is False


class TestElevationErrorMessage:
    """Platform-specific elevation hint messages."""

    def test_windows_message_mentions_run_as_administrator(self):
        """Windows error message must reference 'Administrator'."""
        with patch("sys.platform", "win32"):
            msg = get_elevation_error_message()
            assert "Administrator" in msg

    def test_non_windows_message_mentions_sudo(self):
        """Non-Windows error message must reference 'sudo'."""
        with patch("sys.platform", "linux"):
            msg = get_elevation_error_message()
            assert "sudo" in msg
