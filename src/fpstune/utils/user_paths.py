"""The one place a user-profile root is resolved.

C9 says every path fpstune touches is discovered at runtime, never carried in
the source. This module is that discovery's single source for the roots that
live under a user's profile (the home directory, ``%LOCALAPPDATA%``,
``%APPDATA%``, fpstune's own ``~/.fpstune``, the shell folders such as Documents)
and for ``ProgramData``, the machine-wide root the cleanups delete under.

Why one module: a discovery function that reads ``%LOCALAPPDATA%`` itself
cannot be redirected by a test that did not know it was there. On 2026-10-06 a
sweep over every setting rewrote the developer's real Call of Duty options file
and Battle.net.config that way (#104). With every root resolved here, the test
suite points them all at a temporary tree in one fixture, and
``tests/test_user_paths.py`` fails on any module that reads one directly.

Every function reads the environment at call time, never at import, so a test's
``monkeypatch.setenv`` and the redirect both take effect. The two operating
system lookups that an environment variable cannot redirect, the shell folders
registry key and ``SHGetKnownFolderPath``, are the module's own seams
(``_shell_folders_value``, ``_known_folder``) and ``tests/conftest.py`` silences
both, so a test sees a shell that answers nothing and falls back to the
redirected environment.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

#: The variables that name a user-profile root. SystemRoot and ProgramFiles are
#: neither a user's profile nor written under, and are not read here.
PROFILE_VARIABLES = ("LOCALAPPDATA", "APPDATA", "USERPROFILE")

#: ``FOLDERID_Documents`` and ``FOLDERID_ProgramData``, the known-folder ids
#: ``SHGetKnownFolderPath`` is asked for.
_FOLDERID_DOCUMENTS = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
_FOLDERID_PROGRAM_DATA = "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97"
_SHELL_FOLDERS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"

_STATE_DIRECTORY = ".fpstune"


def profile_env(name: str) -> str | None:
    """A root variable's value (profile or ProgramData), or None when unset or blank."""
    value = os.environ.get(name)
    if not value:
        return None
    return value.strip() or None


def home() -> Path:
    """The account's home directory.

    Windows reads ``USERPROFILE`` (what the shell and the game launchers read);
    elsewhere the platform's own home.
    """
    if os.name == "nt":
        return Path(profile_env("USERPROFILE") or "~").expanduser()
    return Path.home()


def local_appdata() -> Path | None:
    """``%LOCALAPPDATA%``, or None when the environment did not answer."""
    value = profile_env("LOCALAPPDATA")
    return Path(value) if value else None


def roaming_appdata() -> Path | None:
    """``%APPDATA%``, or None when the environment did not answer."""
    value = profile_env("APPDATA")
    return Path(value) if value else None


def fpstune_home_path() -> Path:
    """``~/.fpstune``, the per-user state directory, without creating it."""
    return home() / _STATE_DIRECTORY


def fpstune_home() -> Path:
    """``~/.fpstune``, created if it does not exist yet."""
    folder = fpstune_home_path()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _shell_folders_value(value_name: str) -> str | None:
    """One value of the console user's ``Shell Folders`` key, as Explorer wrote it.

    Read from the console user's hive, not the elevated token's: under another
    administrator's credentials ``HKEY_CURRENT_USER``, ``%LOCALAPPDATA%`` and
    ``Path.home()`` are all that administrator's, whose folders hold no game
    config at all. ``Shell Folders`` also follows OneDrive redirection, which
    reading ``%USERPROFILE%\\Documents`` directly would miss.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        from fpstune.utils.winapi.session import registry_root

        root, key_path = registry_root("HKCU", _SHELL_FOLDERS_KEY)
        with winreg.OpenKey(root, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("%s folder lookup failed: %s", value_name, exc)
        return None
    return str(value) or None


def _known_folder(folder_id: str) -> Path | None:
    """What ``SHGetKnownFolderPath`` answers for a known-folder id, or None.

    Asked with no token, so for the *process* user: right for machine-wide
    folders, and for a per-user one only when the console user is the process
    user (:func:`documents` checks that before asking).
    """
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        shell32 = ctypes.WinDLL("shell32")
        ole32 = ctypes.WinDLL("ole32")
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.c_char_p,
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None
        # A GUID's in-memory layout is the little-endian form of its text.
        guid = uuid.UUID(folder_id).bytes_le
        answer = ctypes.c_void_p()
        status = shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(answer))
        try:
            if status < 0 or not answer.value:
                return None
            return Path(ctypes.wstring_at(answer.value))
        finally:
            ole32.CoTaskMemFree(answer)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("known folder %s lookup failed: %s", folder_id, exc)
        return None


def shell_folder(value_name: str) -> Path | None:
    """One of the console user's shell folders, when it exists on disk.

    ``value_name`` is a ``Shell Folders`` value: ``Personal``, ``Local AppData``,
    ``AppData``, or the GUID Windows lists Saved Games under.
    """
    value = _shell_folders_value(value_name)
    if value is None:
        return None
    folder = Path(value)
    return folder if folder.exists() else None


def documents() -> Path | None:
    """The console user's Documents folder, honouring OneDrive redirection.

    Order: the console user's ``Shell Folders``; then the shell's own known
    folder, only when the console user is the process user (the known-folder
    call has no way to ask for anyone else); then ``<home>\\Documents`` if it
    exists. None off Windows or when none of them answers.
    """
    if sys.platform != "win32":
        return None
    found = shell_folder("Personal")
    if found is not None:
        return found
    from fpstune.utils.winapi.session import user_hive

    if user_hive().root == "HKCU":
        known = _known_folder(_FOLDERID_DOCUMENTS)
        if known is not None and known.exists():
            return known
    fallback = home() / "Documents"
    return fallback if fallback.exists() else None


def program_data() -> Path | None:
    """``ProgramData``, the machine-wide root; None when nothing answers.

    The shell's known folder first, ``%PROGRAMDATA%`` when it does not answer.
    """
    known = _known_folder(_FOLDERID_PROGRAM_DATA)
    if known is not None:
        return known
    value = profile_env("PROGRAMDATA")
    return Path(value) if value else None
