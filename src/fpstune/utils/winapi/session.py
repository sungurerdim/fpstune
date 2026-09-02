"""Whose registry hive ``HKCU`` should mean.

``HKEY_CURRENT_USER`` is the hive of the *process token's* user. fpstune runs
elevated, and when a standard user elevates with an administrator's credentials
the token belongs to the administrator: every per-user tweak (mouse
acceleration, Game DVR, visual effects, GPU preferences) would land in the wrong
account. A background process running as a service would write SYSTEM's hive.

So the interactive console session's user is resolved once and compared with the
process user; when they differ and that user's hive is loaded under
``HKEY_USERS``, the registry executor writes there instead. Everything is read
through documented APIs (``WTSQuerySessionInformation``, ``LookupAccountName``,
``GetTokenInformation``); nothing parses ``whoami`` text.

Every import carries its prototype. Without ``argtypes`` ctypes passes a Python
int as a 32-bit C ``int``, which truncates ``GetCurrentProcess()``'s pseudo handle
(``-1`` as a 64-bit pointer) and every SID pointer — ``OpenProcessToken`` then
fails on every 64-bit machine, silently.
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache

_WTS_CURRENT_SERVER_HANDLE = None
_WTS_USER_NAME = 5
_WTS_DOMAIN_NAME = 7
_TOKEN_QUERY = 0x0008
_TOKEN_INFORMATION_CLASS_USER = 1
_SID_MAX_BYTES = 68
_NO_SESSION = 0xFFFFFFFF


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


@dataclass(frozen=True)
class UserHive:
    """Where per-user keys go: the root name and the path prefix under it."""

    root: str  # "HKCU" or "HKU"
    prefix: str  # "" for HKCU, "<SID>\\" for HKU

    def path(self, subkey: str) -> str:
        return f"{self.prefix}{subkey}"


@dataclass(frozen=True)
class _Libraries:
    kernel32: ctypes.WinDLL
    advapi32: ctypes.WinDLL
    wtsapi32: ctypes.WinDLL


@lru_cache(maxsize=1)
def _libraries() -> _Libraries:
    """The three DLLs with every prototype declared, loaded once."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.WTSGetActiveConsoleSessionId.argtypes = []
    kernel32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD

    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.LookupAccountNameW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.LookupAccountNameW.restype = wintypes.BOOL

    wtsapi32.WTSQuerySessionInformationW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(wintypes.DWORD),
    ]
    wtsapi32.WTSQuerySessionInformationW.restype = wintypes.BOOL
    wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    wtsapi32.WTSFreeMemory.restype = None
    return _Libraries(kernel32=kernel32, advapi32=advapi32, wtsapi32=wtsapi32)


def _sid_to_string(sid: ctypes.c_void_p | int | None) -> str | None:
    libs = _libraries()
    out = wintypes.LPWSTR()
    if not libs.advapi32.ConvertSidToStringSidW(sid, ctypes.byref(out)):
        return None
    try:
        return out.value
    finally:
        libs.kernel32.LocalFree(out)


def process_user_sid() -> str | None:
    """The SID of the account this process runs as."""
    if sys.platform != "win32":
        return None
    libs = _libraries()
    token = wintypes.HANDLE()
    if not libs.advapi32.OpenProcessToken(
        libs.kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        return None
    try:
        needed = wintypes.DWORD(0)
        libs.advapi32.GetTokenInformation(
            token, _TOKEN_INFORMATION_CLASS_USER, None, 0, ctypes.byref(needed)
        )
        if needed.value == 0:
            return None
        buffer = ctypes.create_string_buffer(needed.value)
        if not libs.advapi32.GetTokenInformation(
            token, _TOKEN_INFORMATION_CLASS_USER, buffer, needed.value, ctypes.byref(needed)
        ):
            return None
        user = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents
        return _sid_to_string(user.User.Sid)
    finally:
        libs.kernel32.CloseHandle(token)


def _session_string(session_id: int, info_class: int) -> str | None:
    libs = _libraries()
    buffer = wintypes.LPWSTR()
    returned = wintypes.DWORD(0)
    if not libs.wtsapi32.WTSQuerySessionInformationW(
        _WTS_CURRENT_SERVER_HANDLE,
        session_id,
        info_class,
        ctypes.byref(buffer),
        ctypes.byref(returned),
    ):
        return None
    try:
        return buffer.value
    finally:
        libs.wtsapi32.WTSFreeMemory(buffer)


def interactive_user_sid() -> str | None:
    """The SID of the user on the active console session, or None when there is none."""
    if sys.platform != "win32":
        return None
    libs = _libraries()
    session_id = libs.kernel32.WTSGetActiveConsoleSessionId()
    if session_id == _NO_SESSION:
        return None
    user = _session_string(session_id, _WTS_USER_NAME)
    domain = _session_string(session_id, _WTS_DOMAIN_NAME)
    if not user:
        return None
    account = f"{domain}\\{user}" if domain else user

    sid = ctypes.create_string_buffer(_SID_MAX_BYTES)
    sid_size = wintypes.DWORD(_SID_MAX_BYTES)
    referenced = ctypes.create_unicode_buffer(256)
    referenced_size = wintypes.DWORD(256)
    use = wintypes.DWORD(0)
    if not libs.advapi32.LookupAccountNameW(
        None,
        account,
        sid,
        ctypes.byref(sid_size),
        referenced,
        ctypes.byref(referenced_size),
        ctypes.byref(use),
    ):
        return None
    return _sid_to_string(ctypes.cast(sid, ctypes.c_void_p))


def _hive_is_loaded(sid: str) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_USERS, sid, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            return True
    except OSError:
        return False


def resolve_user_hive(
    process_sid: str | None, interactive_sid: str | None, hive_loaded: bool
) -> UserHive:
    """Pure decision: HKU\\<SID> only when the console user is someone else and present."""
    if interactive_sid and process_sid and interactive_sid != process_sid and hive_loaded:
        return UserHive(root="HKU", prefix=f"{interactive_sid}\\")
    return UserHive(root="HKCU", prefix="")


@lru_cache(maxsize=1)
def user_hive() -> UserHive:
    """Where ``HKCU`` settings go for the person at the keyboard, resolved once per process."""
    if sys.platform != "win32":
        return UserHive(root="HKCU", prefix="")
    interactive = interactive_user_sid()
    process = process_user_sid()
    loaded = bool(interactive) and _hive_is_loaded(interactive or "")
    return resolve_user_hive(process, interactive, loaded)


def registry_root(hive: str, path: str) -> tuple[int, str]:
    """The winreg root and full subkey for a setting's hive.

    ``HKLM`` is what it says. ``HKCU`` is the person at the keyboard: when the
    console user is someone other than the token's owner and their hive is
    loaded, per-user keys live under ``HKEY_USERS\\<SID>``. Every winreg reader
    of a per-user key goes through here — the executor, the Documents-folder
    lookup, the Docker and WSL probes — so none of them can disagree.
    """
    import winreg

    if hive == "HKLM":
        return winreg.HKEY_LOCAL_MACHINE, path
    target = user_hive()
    if target.root == "HKU":
        return winreg.HKEY_USERS, target.path(path)
    return winreg.HKEY_CURRENT_USER, path


# The drive, however cased, wherever it starts a path: `HKCU:\Software\...` and
# `'HKCU:\...'` alike. `HKCU` without the colon is not a PowerShell path.
_HKCU_DRIVE = re.compile(r"\bHKCU:", re.IGNORECASE)


def redirect_hkcu(script: str) -> str:
    """Point a PowerShell script's ``HKCU:`` drive at the console user's hive.

    ``HKCU:`` is bound to the *process token's* user by the Registry provider,
    so a script that writes there under an administrator's elevation writes the
    administrator's hive. The Registry provider accepts a provider-qualified
    path to any loaded hive — ``Registry::HKEY_USERS\\<SID>\\Software\\...`` — and
    that is what the drive is rewritten to when the console user is someone
    else. Same user, or no console session: the script is returned untouched.
    """
    if "HKCU:" not in script.upper():
        return script
    target = user_hive()
    if target.root != "HKU":
        return script
    replacement = "Registry::HKEY_USERS\\" + target.prefix.rstrip("\\")
    return _HKCU_DRIVE.sub(lambda _m: replacement, script)
