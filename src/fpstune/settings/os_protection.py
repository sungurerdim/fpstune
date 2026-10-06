"""Registry keys Windows itself guards against other programs, and whether it is guarding now.

The User Choice Protection Driver (``ucpd.sys``, service ``UCPD``) filters writes to a
short list of keys from every process that is not a Microsoft one. The refusal is
absolute: an elevated token, an Administrators FullControl ACL and a clean ACL reset
all still end in "access denied" (measured 2026-10-06, #104: ``system:widgets`` on
Windows 11 build 26200 with the service Running). So a write to one of these keys is
not an operation that failed; it is an operation this machine does not offer, and
that is a capability fact — ``is_applicable=False`` (C10), decided in detection, never
a refusal reported after the apply. Turning the driver off to get past it would be
tampering with an OS protection, which stays a red line.

``ProtectedKey`` is the one list and ``blocked_write(setting, guard_up=...)`` is the one
question the ``ApplicabilityChecker`` asks (the state is read once into
``HardwareContext.ucpd_guard_up`` by ``build_hardware_context()``), so every path that detects or applies a setting
(detection, single apply, bulk apply) gets the same answer and a new definition that
writes a listed key is covered without being named anywhere.

Source of the list: https://kolbi.cz/blog/2025/07/15/ucpd-sys-userchoice-protection-driver-part-2/
(UCPD.sys 4.3: the ``UserChoice`` / ``UserChoiceLatest`` keys of http, https, .pdf,
.htm, .html, .doc, .docx, .xls, .xlsx, .ppt, .pptx; and ``SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Feeds``
and ``SOFTWARE\\Policies\\Microsoft\\Dsh``). The post notes the list varies by region and
edition, so a key that is listed here but unguarded on a machine costs nothing: the
service state below, not the list, decides whether the guard is up. ``TaskbarDa`` is
not in the post; it was measured refused on the same machine (#104).
"""

from __future__ import annotations

import ctypes
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

UCPD_SERVICE = "UCPD"
_UCPD_KEY = r"SYSTEM\CurrentControlSet\Services\UCPD"

# Service Start values: 0 boot, 1 system, 2 automatic (loaded this boot), 3 manual, 4 disabled.
# Service current states (winsvc.h).
_SERVICE_START_PENDING = 2
_SERVICE_RUNNING = 4

_SC_MANAGER_CONNECT = 0x0001
_SERVICE_QUERY_STATUS = 0x0004


@dataclass(frozen=True)
class ProtectedKey:
    """One guarded registry location.

    ``path`` is a lower-case regex over the key path (no hive); the key and everything
    under it is guarded. ``value_name`` narrows the guard to one value of that key when
    only that value is filtered (``TaskbarDa``); None guards the whole key.
    """

    hive: str
    path: str
    value_name: str | None = None
    label: str = ""  # the key as a reader would write it; the regex is not readable

    def covers(self, hive: str, path: str, name: str) -> bool:
        """Whether a structured registry write (hive, path, value) lands on this key."""
        if hive.strip().upper() != self.hive:
            return False
        if self.value_name is not None and name.strip().lower() != self.value_name.lower():
            return False
        return re.match(self.path + r"(?:\\|$)", _normalise_path(path)) is not None

    def named_in(self, text: str) -> bool:
        """Whether a script's text names this key (and value, when the guard is per value)."""
        lowered = _normalise_path(text)
        if re.search(self.path + r"(?![\w])", lowered) is None:
            return False
        return self.value_name is None or self.value_name.lower() in lowered


_FILE_EXTS = r"(?:pdf|htm|html|doc|docx|xls|xlsx|ppt|pptx)"
_USER_CHOICE = r"\\userchoice(?:latest)?"

PROTECTED_KEYS: tuple[ProtectedKey, ...] = (
    ProtectedKey(
        "HKLM",
        r"software\\policies\\microsoft\\dsh",
        label=r"HKLM\SOFTWARE\Policies\Microsoft\Dsh",
    ),
    ProtectedKey(
        "HKLM",
        r"software\\policies\\microsoft\\windows\\windows feeds",
        label=r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Feeds",
    ),
    ProtectedKey(
        "HKCU",
        r"software\\microsoft\\windows\\currentversion\\explorer\\advanced",
        value_name="TaskbarDa",
        label=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDa",
    ),
    ProtectedKey(
        "HKCU",
        r"software\\microsoft\\windows\\shell\\associations\\urlassociations\\https?"
        + _USER_CHOICE,
        label=r"HKCU\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\<http|https>\UserChoice",
    ),
    ProtectedKey(
        "HKCU",
        r"software\\microsoft\\windows\\currentversion\\explorer\\fileexts\\\."
        + _FILE_EXTS
        + _USER_CHOICE,
        label=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\<.pdf|.html|.docx|...>\UserChoice",
    ),
)


def _normalise_path(text: str) -> str:
    """Lower-case with single backslashes, so a doubled or forward slash still matches."""
    return re.sub(r"[\\/]+", r"\\", text.lower())


# === Is the guard up ==========================================================


def guard_is_up(start: int | None, state: int | None) -> bool:
    """The driver's own state decides; the Start value only answers when the state is unreadable.

    A running driver filters regardless of what its Start value says (a user who
    disabled it and has not rebooted is still guarded), so the state wins. With no
    state, an auto/boot/system start means it is loaded this boot; no Start value at
    all means the driver is not installed.
    """
    if state is not None:
        return state in (_SERVICE_START_PENDING, _SERVICE_RUNNING)
    if start is None:
        return False
    return start in (0, 1, 2)


def _read_start() -> int | None:
    """The UCPD service's ``Start`` value, or None when the service key is absent/unreadable."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, _UCPD_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Start")
    except OSError:
        return None
    return value if isinstance(value, int) else None


class _ServiceStatus(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", ctypes.c_uint32),
        ("dwCurrentState", ctypes.c_uint32),
        ("dwControlsAccepted", ctypes.c_uint32),
        ("dwWin32ExitCode", ctypes.c_uint32),
        ("dwServiceSpecificExitCode", ctypes.c_uint32),
        ("dwCheckPoint", ctypes.c_uint32),
        ("dwWaitHint", ctypes.c_uint32),
    ]


def _read_state(name: str = UCPD_SERVICE) -> int | None:
    """``dwCurrentState`` of a service through the Service Control Manager, None if unreadable.

    Native API on purpose: no PowerShell, and no ``sc`` text to parse in whatever
    language Windows prints it.
    """
    if sys.platform != "win32":
        return None
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    handle_t = ctypes.c_void_p
    advapi32.OpenSCManagerW.restype = handle_t
    advapi32.OpenSCManagerW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    advapi32.OpenServiceW.restype = handle_t
    advapi32.OpenServiceW.argtypes = [handle_t, ctypes.c_wchar_p, ctypes.c_uint32]
    advapi32.QueryServiceStatus.restype = ctypes.c_int
    advapi32.QueryServiceStatus.argtypes = [handle_t, ctypes.POINTER(_ServiceStatus)]
    advapi32.CloseServiceHandle.restype = ctypes.c_int
    advapi32.CloseServiceHandle.argtypes = [handle_t]

    manager = advapi32.OpenSCManagerW(None, None, _SC_MANAGER_CONNECT)
    if not manager:
        return None
    try:
        service = advapi32.OpenServiceW(manager, name, _SERVICE_QUERY_STATUS)
        if not service:
            return None
        try:
            status = _ServiceStatus()
            if not advapi32.QueryServiceStatus(service, ctypes.byref(status)):
                return None
            return int(status.dwCurrentState)
        finally:
            advapi32.CloseServiceHandle(service)
    finally:
        advapi32.CloseServiceHandle(manager)


@lru_cache(maxsize=1)
def ucpd_active() -> bool:
    """Whether the User Choice Protection Driver is filtering registry writes right now.

    Session-stable (C7): the driver only changes state across a reboot, so one read per
    run is the answer. A machine that cannot be read is treated as unguarded, because
    claiming a protection we did not observe would hide a setting that works.
    """
    return guard_is_up(_read_start(), _read_state())


# === Which settings write a guarded key =======================================


@lru_cache(maxsize=512)
def _script_hits(apply_command: str) -> tuple[str, ...]:
    """Guarded keys named by the PowerShell script an ``apply_command`` key resolves to."""
    from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

    script = ACTION_COMMANDS.get(apply_command, "")
    return tuple(key.label for key in PROTECTED_KEYS if key.named_in(script))


def protected_write_targets(setting: SettingExecutor) -> tuple[str, ...]:
    """The guarded keys this setting's apply writes, as readable labels (empty: none).

    Structured for the registry executor (hive, path, value are fields); by script text
    for everything else, because a script's target is only in its text. Only the apply
    side counts: reading a guarded key is allowed.
    """
    from fpstune.settings.base import DetectType

    if setting.apply_type is DetectType.REGISTRY:
        args = setting.apply_args
        hive = str(args.get("hive", "HKLM"))
        path = str(args.get("path", ""))
        name = str(args.get("name", ""))
        return tuple(key.label for key in PROTECTED_KEYS if key.covers(hive, path, name))
    if setting.apply_type is DetectType.POWERSHELL:
        # The script (an ACTION_COMMANDS key) and the arguments it is handed: a
        # Python action receives its key path as an argument, not in a script.
        arg_text = " ".join(str(v) for v in setting.apply_args.values())
        from_args = tuple(key.label for key in PROTECTED_KEYS if key.named_in(arg_text))
        return tuple(dict.fromkeys((*_script_hits(setting.apply_command), *from_args)))
    return ()


def blocked_write(setting: SettingExecutor, *, guard_up: bool) -> str:
    """Why this setting cannot be written on this machine, or "" when it can.

    The one question the ``ApplicabilityChecker`` asks: the setting writes a key UCPD
    guards *and* UCPD is up. Whether it is up is a parameter — the checker hands in
    ``HardwareContext.ucpd_guard_up``, which ``build_hardware_context()`` filled from
    ``ucpd_active()`` — so this answer depends on its arguments and not on the machine
    the code happens to run on.
    """
    targets = protected_write_targets(setting)
    if not targets or not guard_up:
        return ""
    return (
        "Windows protects this setting against other programs (the User Choice "
        f"Protection Driver guards {targets[0]}), so it cannot be changed from here"
    )
