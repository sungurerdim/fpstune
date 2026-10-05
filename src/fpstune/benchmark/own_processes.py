"""Find and end the tool processes fpstune itself started, and nothing else.

`taskkill /IM PresentMon.exe` ends every PresentMon on the machine — including
the one the user is recording with, from their own install. The sweep's job is
narrower: a tool *fpstune* left running after a crash. fpstune runs its tools
only from under its own state directory, so that is the test: the process's
full image path lies under that directory. A same-named executable anywhere
else belongs to somebody else and is left alone.

Process enumeration goes through ``CreateToolhelp32Snapshot`` and
``QueryFullProcessImageNameW`` over ctypes — no subprocess per process and no
PowerShell, the same reason ``game_processes`` gives.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath

from fpstune.utils import process_watch
from fpstune.utils.logger import get_logger
from fpstune.utils.system_tools import system_tool

logger = get_logger()

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass(frozen=True)
class ProcessImage:
    pid: int
    path: str


def _norm(path: str) -> str:
    return str(PureWindowsPath(path)).rstrip("\\").casefold()


def select_owned(
    images: Iterable[ProcessImage], root: str, names: Iterable[str], own_pid: int
) -> list[int]:
    """The PIDs whose image is one of ``names`` *and* lies under ``root``."""
    base = _norm(root) + "\\"
    wanted = {name.casefold() for name in names}
    chosen: list[int] = []
    for image in images:
        if image.pid in (0, own_pid) or not image.path:
            continue
        path = _norm(image.path)
        if PureWindowsPath(path).name in wanted and path.startswith(base):
            chosen.append(image.pid)
    return chosen


def _image_path(kernel32: ctypes.WinDLL, pid: int) -> str:
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def running_images(names: Iterable[str]) -> list[ProcessImage]:
    """Running processes named one of ``names``, with their full image paths."""
    if sys.platform != "win32":
        return []
    from fpstune.settings.executors.game_processes import (
        _PROCESSENTRY32W,
        INVALID_HANDLE_VALUE,
        TH32CS_SNAPPROCESS,
    )

    wanted = {name.casefold() for name in names}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return []
    found: list[ProcessImage] = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.casefold() in wanted:
                pid = int(entry.th32ProcessID)
                found.append(ProcessImage(pid, _image_path(kernel32, pid)))
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("process enumeration failed: %s", exc)
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def kill_pid_tree(pid: int) -> bool:
    """End one process and its children, by PID. Returns whether taskkill said so."""
    if sys.platform != "win32":
        return False
    try:
        completed = process_watch.run(
            [system_tool("taskkill.exe"), "/PID", str(pid), "/T", "/F"], process_watch.QUERY
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Could not end process %s: %s", pid, exc)
        return False
    return completed.returncode == 0


def kill_own_tools(root: str, names: Iterable[str]) -> int:
    """End every ``names`` process started from under ``root``. Returns how many."""
    names = list(names)
    killed = 0
    for pid in select_owned(running_images(names), root, names, os.getpid()):
        if kill_pid_tree(pid):
            killed += 1
    return killed
