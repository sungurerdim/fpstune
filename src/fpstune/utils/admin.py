"""Administrator privilege detection and enforcement."""

from __future__ import annotations

import ctypes
import functools
import os
import subprocess
import sys
from collections.abc import Callable


def relaunch_command() -> tuple[str, str]:
    """Program and parameters that start this same fpstune command again.

    A frozen build re-runs its own exe. From source, ``sys.argv[0]`` is the
    ``fpstune.exe`` console-script shim, which Python cannot run as a script,
    so the module is started instead.
    """
    args = sys.argv[1:]
    if getattr(sys, "frozen", False):
        return sys.executable, subprocess.list2cmdline(args)
    return sys.executable, subprocess.list2cmdline(["-m", "fpstune.cli", *args])


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
        program, params = relaunch_command()

        # ShellExecuteW with "runas" verb triggers UAC prompt. lpDirectory is the
        # current directory: an elevated process otherwise starts in System32.
        # Windows-only: ctypes.windll only exists on Windows platform
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            program,
            params,
            os.getcwd(),
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
