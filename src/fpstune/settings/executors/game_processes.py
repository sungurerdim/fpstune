"""Refuse to write a game's config while that game is running.

This exists because of a failure mode that passes every check the product has.
Measured on 2026-08-23: MW4's two config files changed under a running test
suite — size 17811 → 17807 and 8081 → 8084 — while fpstune had written neither.
``cod26-cod`` had started at 21:53 and the files were rewritten at 21:59.

The games keep their settings in memory and flush them on exit. So a write
applied to a running game is **lost when the game closes**, and nothing notices:
apply succeeds, and verify succeeds too, because detection re-reads the file
fpstune just wrote. The overwrite happens minutes later.

It is not an MW4 problem. MW3, CS2 and Heroes of the Storm all keep config the
same way; MW4 only happened to expose it.

Process enumeration goes through ``CreateToolhelp32Snapshot`` rather than
``psutil`` (not a dependency of this project, deliberately — see ``cli.py``) and
rather than ``tasklist`` (a subprocess per call, and bulk apply would pay it once
per setting).
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from fpstune.utils.logger import get_logger

logger = get_logger()

# Which running process means "this game has the config file in memory".
#
# Only MW4's entry is measured. The rest are the names those games are commonly
# known to run under, and each is unverified here because the game was not
# running when this was written — the honest consequence is that a missing or
# wrong name means no warning, i.e. today's behaviour, never a false block.
#
# Deliberately excluded: `CODBrokerService` and `codCrashHandler`, which were
# both running alongside MW4. They outlive the game, so treating either as "the
# game is open" would block every apply on a machine that had launched it once.
GAME_PROCESSES: dict[str, tuple[str, ...]] = {
    # measured: seen running while MW4 held its config open
    "mw4": ("cod26-cod",),
    # unverified
    "mw3": ("cod", "ModernWarfareIII"),
    # unverified
    "cs2": ("cs2",),
    # unverified
    "hots": ("HeroesOfTheStorm_x64", "Heroes of the Storm"),
}

# Human-readable name for the message the user actually sees.
GAME_LABELS: dict[str, str] = {
    "mw4": "Modern Warfare IV",
    "mw3": "Modern Warfare III",
    "cs2": "Counter-Strike 2",
    "hots": "Heroes of the Storm",
}

# A bulk apply asks this once per setting. The snapshot is cheap but not free,
# and a game does not open or close inside two seconds of a sequential apply.
_CACHE_TTL_SECONDS = 2.0
_cache: tuple[float, frozenset[str]] | None = None

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    )


def _snapshot_process_names() -> frozenset[str]:
    """Every running process name, lowercased, without its ``.exe`` suffix.

    Returns an empty set on any failure. That is deliberate: this module's whole
    job is to add a warning, so a failure to enumerate must fall back to the
    behaviour that existed before it — write, and do not block the user.
    """
    if sys.platform != "win32":
        return frozenset()

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not handle or handle == INVALID_HANDLE_VALUE:
        logger.debug("process snapshot failed: %s", ctypes.get_last_error())
        return frozenset()

    names: set[str] = set()
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not kernel32.Process32FirstW(handle, ctypes.byref(entry)):
            return frozenset()
        while True:
            exe = entry.szExeFile
            if exe:
                names.add(exe.removesuffix(".exe").removesuffix(".EXE").casefold())
            if not kernel32.Process32NextW(handle, ctypes.byref(entry)):
                break
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("process enumeration failed: %s", exc)
        return frozenset()
    finally:
        kernel32.CloseHandle(handle)

    return frozenset(names)


def running_process_names(*, use_cache: bool = True) -> frozenset[str]:
    """Cached view of the running process names."""
    global _cache

    if use_cache and _cache is not None:
        stamped, names = _cache
        if time.monotonic() - stamped < _CACHE_TTL_SECONDS:
            return names

    names = _snapshot_process_names()
    _cache = (time.monotonic(), names)
    return names


def reset_process_cache() -> None:
    """Drop the cached snapshot. For tests, and after a user closes a game."""
    global _cache
    _cache = None


def game_is_running(game: str) -> bool:
    """Is the named game holding its config in memory right now?

    Unknown game key → False. A game fpstune has no process name for gets the
    behaviour it had before this module existed.
    """
    candidates = GAME_PROCESSES.get(game)
    if not candidates:
        return False

    running = running_process_names()
    if not running:
        return False
    return any(name.casefold() in running for name in candidates)


def game_of_setting(setting_id: str) -> str | None:
    """Which game a setting writes for, from its id. None if it is not a game config.

    ``game_config:mw4:texture_quality`` → ``mw4``. Cleanup actions
    (``game_cleanup:*``) are deliberately not covered: they delete caches rather
    than write settings the game holds in memory, so the failure this module
    guards against does not apply to them.
    """
    parts = setting_id.split(":")
    if len(parts) >= 3 and parts[0] == "game_config":
        return parts[1]
    return None


def refuse_if_game_is_running(setting_id: str) -> str | None:
    """Return the message to fail an apply with, or None to go ahead.

    Phrased for the person reading it: the reason a correct-looking apply would
    be undone is not obvious, so the message says what to do rather than what
    went wrong.
    """
    game = game_of_setting(setting_id)
    if game is None or not game_is_running(game):
        return None

    label = GAME_LABELS.get(game, game.upper())
    return (
        f"{label} is running. It keeps its settings in memory and writes them "
        f"back when it closes, so this change would be silently undone. Close "
        f"the game and apply again."
    )
