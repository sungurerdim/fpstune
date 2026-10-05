"""Tests for fpstune.utils.admin — privilege detection and elevation."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from fpstune.utils.admin import (
    elevate_if_needed,
    is_admin,
    relaunch_command,
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

    def test_elevated_relaunch_runs_the_module_in_the_current_directory(
        self, tmp_path, monkeypatch
    ):
        """The uv console-script shim is an exe: handing it to python.exe as a script made the
        elevated window die at once (start.bat closed before the web UI opened), and with no
        directory the elevated process started in System32."""
        shim = r"C:\Program Files\fpstune checkout\.venv\Scripts\fpstune.exe"
        monkeypatch.chdir(tmp_path)
        with (
            patch("fpstune.utils.admin.is_admin", return_value=False),
            patch("sys.platform", "win32"),
            patch.object(sys, "argv", [shim, "serve", "--port", "8000"]),
            patch("fpstune.utils.admin.ctypes") as mock_ctypes,
            pytest.raises(SystemExit),
        ):
            mock_ctypes.windll.shell32.ShellExecuteW.return_value = 42
            elevate_if_needed()
        _, verb, program, params, directory, _ = (
            mock_ctypes.windll.shell32.ShellExecuteW.call_args.args
        )
        assert verb == "runas"
        assert program == sys.executable
        assert params == "-m fpstune.cli serve --port 8000"
        assert "fpstune.exe" not in params
        assert directory == str(tmp_path)


class TestRelaunchCommand:
    """A frozen build re-runs its own exe with only the user's arguments."""

    def test_frozen_build_reruns_itself(self, monkeypatch):
        exe = r"C:\Program Files\fpstune\fpstune.exe"
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", exe)
        monkeypatch.setattr(sys, "argv", [exe, "serve", "--host", "127.0.0.1"])
        assert relaunch_command() == (exe, "serve --host 127.0.0.1")

    def test_argument_with_spaces_is_quoted(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["fpstune", "serve", "--log", r"C:\My Logs\fpstune.log"])
        _, params = relaunch_command()
        assert params == r'-m fpstune.cli serve --log "C:\My Logs\fpstune.log"'
