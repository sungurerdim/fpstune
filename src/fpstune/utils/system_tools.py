"""Absolute paths to Windows' own tools.

fpstune runs as Administrator, usually from a Downloads folder. A bare name such
as ``"powershell"`` is resolved through the search path, which starts with the
launching program's own folder — so a ``powershell.exe`` dropped beside
fpstune.exe would run elevated. Every Windows tool is therefore started from the
System32 directory Windows itself reports.
"""

from __future__ import annotations

import ctypes
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def system32() -> str:
    """The System32 directory, as GetSystemDirectoryW reports it."""
    windll = getattr(ctypes, "windll", None)
    if windll is not None:
        buffer = ctypes.create_unicode_buffer(260)
        length = windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
        if 0 < length < len(buffer):
            return buffer.value
    return os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32")


def system_tool(name: str) -> str:
    """Absolute path of a tool that ships in System32 (``"sc.exe"``, ...)."""
    return os.path.join(system32(), name)


def powershell_exe() -> str:
    """Windows PowerShell 5.1, which every Windows 11 edition ships."""
    return os.path.join(system32(), "WindowsPowerShell", "v1.0", "powershell.exe")


def nvidia_smi() -> str | None:
    """nvidia-smi.exe where an NVIDIA driver installs it, or None.

    DCH drivers place it in System32; older ones under NVSMI in Program Files.
    """
    candidates = [os.path.join(system32(), "nvidia-smi.exe")]
    program_files = os.environ.get("PROGRAMW6432") or os.environ.get("PROGRAMFILES")
    if program_files:
        candidates.append(
            os.path.join(program_files, "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
        )
    return next((path for path in candidates if os.path.isfile(path)), None)
