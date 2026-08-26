"""Administrator privilege detection and enforcement."""

from __future__ import annotations

import ctypes
import functools
import sys
from collections.abc import Callable


def is_admin() -> bool:
    """Check if the current process has administrator privileges.

    Returns:
        True if running as administrator, False otherwise.
    """
    if sys.platform != "win32":
        # On non-Windows, check for root
        import os

        return os.geteuid() == 0  # Unix-only: geteuid not available on Windows

    try:
        # Windows-only: ctypes.windll only exists on Windows platform
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def require_admin[R](func: Callable[..., R]) -> Callable[..., R]:
    """Decorator that ensures the function runs with admin privileges.

    Raises:
        PermissionError: If not running as administrator.
    """

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> R:
        if not is_admin():
            raise PermissionError(
                "Administrator privileges required. "
                "Please run as Administrator (Windows) or with sudo (Linux/macOS)."
            )
        return func(*args, **kwargs)

    return wrapper


def elevate_if_needed() -> bool:
    """Attempt to restart the process with elevated privileges.

    Shows Windows UAC prompt if not running as admin.

    Returns:
        True if elevation was successfully requested (process should restart),
        False if already elevated or elevation failed/denied.
    """
    if is_admin():
        return False

    if sys.platform != "win32":
        # On non-Windows, tell user to use sudo
        return False

    try:
        # Build command line for re-launching with admin
        # Use the full Python executable path and script
        script = sys.argv[0]
        params = " ".join(f'"{arg}"' if " " in arg else arg for arg in sys.argv[1:])

        # ShellExecuteW with "runas" verb triggers UAC prompt
        # Parameters:
        #   hwnd: None (no parent window)
        #   lpOperation: "runas" (request elevation)
        #   lpFile: Python executable
        #   lpParameters: script and arguments
        #   lpDirectory: None (use current)
        #   nShowCmd: 1 (SW_SHOWNORMAL)
        # Windows-only: ctypes.windll only exists on Windows platform
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}" {params}',
            None,
            1,  # SW_SHOWNORMAL
        )

        # ShellExecuteW return values:
        # > 32: Success
        # 0: Out of memory
        # 2: File not found
        # 3: Path not found
        # 5: Access denied (user clicked No on UAC)
        # 31: No application associated
        if result > 32:
            # Successfully launched elevated process
            sys.exit(0)

        # Elevation failed or was denied
        return False
    except (OSError, AttributeError):
        return False


def get_elevation_error_message() -> str:
    """Get a user-friendly error message for elevation failure.

    Returns:
        Error message with instructions.
    """
    if sys.platform == "win32":
        return (
            "To run fpstune manually as Administrator:\n"
            "  1. Right-click on Command Prompt or PowerShell\n"
            "  2. Select 'Run as administrator'\n"
            "  3. Run: fpstune serve"
        )
    else:
        return "To run fpstune with root privileges:\n  sudo fpstune serve"
