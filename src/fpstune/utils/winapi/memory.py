"""The standby list: how big it is, and purging it, through ``ntdll`` directly.

``memory:purge_standby`` used to run a PowerShell command that compiled a C#
class with ``Add-Type`` to reach ``NtSetSystemInformation``. Two things were
wrong with it. The pattern is the one Windows Defender flagged as trojan
behaviour on 2026-09-02, and the call itself passed the *value* 4 as the buffer
pointer (``New-Object IntPtr 4``) rather than a pointer to a buffer holding 4 —
so the kernel was handed address 0x4 to read a command from, and the script
printed "Standby list purged" whatever the return code said.

This module does it the documented way and measures the result: the standby
page counts are read through ``NtQuerySystemInformation`` before and after, so
the message a user sees carries megabytes that were observed on this machine
(C11), not a claim.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

SYSTEM_MEMORY_LIST_INFORMATION = 80
MEMORY_PURGE_STANDBY_LIST = 4
STATUS_SUCCESS = 0

_SE_PRIVILEGE_ENABLED = 0x00000002
_TOKEN_ADJUST_PRIVILEGES = 0x0020
_TOKEN_QUERY = 0x0008
_ERROR_NOT_ALL_ASSIGNED = 1300

# SYSTEM_MEMORY_LIST_INFORMATION, every field a ULONG_PTR: ZeroPageCount,
# FreePageCount, ModifiedPageCount, ModifiedNoWritePageCount, BadPageCount,
# PageCountByPriority[8], RepurposedPagesByPriority[8], ModifiedPageCountPageFile.
_PRIORITY_LEVELS = 8
_FIELDS_BEFORE_PRIORITIES = 5
_FIELD_COUNT = _FIELDS_BEFORE_PRIORITIES + 2 * _PRIORITY_LEVELS + 1

# Privileges NtSetSystemInformation(SystemMemoryListInformation) wants enabled
# on the calling token. An elevated token holds them disabled by default.
PURGE_PRIVILEGES = ("SeProfileSingleProcessPrivilege", "SeIncreaseQuotaPrivilege")


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", _LUID), ("Attributes", wintypes.DWORD)]


class _TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", _LUID_AND_ATTRIBUTES * 1)]


@dataclass(frozen=True)
class MemoryLists:
    """Page counts the kernel reports, in pages of ``page_size`` bytes."""

    free_pages: int
    zero_pages: int
    modified_pages: int
    standby_pages_by_priority: tuple[int, ...]
    page_size: int

    @property
    def standby_pages(self) -> int:
        return sum(self.standby_pages_by_priority)

    @property
    def standby_mb(self) -> int:
        return self.standby_pages * self.page_size // (1024 * 1024)


@dataclass(frozen=True)
class PurgeOutcome:
    status: int
    before: MemoryLists | None
    after: MemoryLists | None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SUCCESS

    @property
    def released_mb(self) -> int | None:
        if self.before is None or self.after is None:
            return None
        return max(0, self.before.standby_mb - self.after.standby_mb)


def memory_lists_from_buffer(
    buffer: bytes, page_size: int, pointer_size: int = 8
) -> MemoryLists | None:
    """Decode a SYSTEM_MEMORY_LIST_INFORMATION buffer. Short buffer → ``None``."""
    needed = _FIELD_COUNT * pointer_size
    if len(buffer) < needed or pointer_size not in (4, 8):
        return None
    fields = [
        int.from_bytes(buffer[i * pointer_size : (i + 1) * pointer_size], "little")
        for i in range(_FIELD_COUNT)
    ]
    priorities = fields[_FIELDS_BEFORE_PRIORITIES : _FIELDS_BEFORE_PRIORITIES + _PRIORITY_LEVELS]
    return MemoryLists(
        zero_pages=fields[0],
        free_pages=fields[1],
        modified_pages=fields[2],
        standby_pages_by_priority=tuple(priorities),
        page_size=page_size,
    )


def _page_size() -> int:
    class _SYSTEM_INFO(ctypes.Structure):
        _fields_ = [
            ("wProcessorArchitecture", wintypes.WORD),
            ("wReserved", wintypes.WORD),
            ("dwPageSize", wintypes.DWORD),
            ("lpMinimumApplicationAddress", ctypes.c_void_p),
            ("lpMaximumApplicationAddress", ctypes.c_void_p),
            ("dwActiveProcessorMask", ctypes.c_void_p),
            ("dwNumberOfProcessors", wintypes.DWORD),
            ("dwProcessorType", wintypes.DWORD),
            ("dwAllocationGranularity", wintypes.DWORD),
            ("wProcessorLevel", wintypes.WORD),
            ("wProcessorRevision", wintypes.WORD),
        ]

    info = _SYSTEM_INFO()
    ctypes.WinDLL("kernel32").GetSystemInfo(ctypes.byref(info))
    return int(info.dwPageSize) or 4096


def memory_lists() -> MemoryLists | None:
    """The kernel's page-list counts, or ``None`` off Windows or when refused."""
    if sys.platform != "win32":
        return None
    ntdll = ctypes.WinDLL("ntdll")
    query = ntdll.NtQuerySystemInformation
    query.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    query.restype = ctypes.c_long
    size = _FIELD_COUNT * ctypes.sizeof(ctypes.c_void_p)
    buffer = ctypes.create_string_buffer(size)
    returned = wintypes.ULONG(0)
    status = query(SYSTEM_MEMORY_LIST_INFORMATION, buffer, size, ctypes.byref(returned))
    if status != STATUS_SUCCESS:
        return None
    return memory_lists_from_buffer(buffer.raw, _page_size(), ctypes.sizeof(ctypes.c_void_p))


def enable_privilege(name: str) -> bool:
    """Enable one named privilege on the current process token.

    Returns False when the token does not hold it (an unelevated process), which
    the purge then reports as refused rather than pretending it ran.
    """
    if sys.platform != "win32":
        return False
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_ADJUST_PRIVILEGES | _TOKEN_QUERY, ctypes.byref(token)
    ):
        return False
    try:
        luid = _LUID()
        if not advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
            return False
        privileges = _TOKEN_PRIVILEGES()
        privileges.PrivilegeCount = 1
        privileges.Privileges[0].Luid = luid
        privileges.Privileges[0].Attributes = _SE_PRIVILEGE_ENABLED
        ctypes.set_last_error(0)
        if not advapi32.AdjustTokenPrivileges(
            token, False, ctypes.byref(privileges), ctypes.sizeof(privileges), None, None
        ):
            return False
        # AdjustTokenPrivileges returns TRUE even when nothing was assigned; the
        # last error is the only place the refusal shows.
        return ctypes.get_last_error() != _ERROR_NOT_ALL_ASSIGNED
    finally:
        kernel32.CloseHandle(token)


def purge_standby_list() -> PurgeOutcome:
    """Ask the kernel to drop the standby list, measuring it before and after."""
    if sys.platform != "win32":
        return PurgeOutcome(status=-1, before=None, after=None)
    for name in PURGE_PRIVILEGES:
        enable_privilege(name)
    before = memory_lists()
    ntdll = ctypes.WinDLL("ntdll")
    setter = ntdll.NtSetSystemInformation
    setter.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.ULONG]
    setter.restype = ctypes.c_long
    command = ctypes.c_int(MEMORY_PURGE_STANDBY_LIST)
    status = setter(SYSTEM_MEMORY_LIST_INFORMATION, ctypes.byref(command), ctypes.sizeof(command))
    after = memory_lists() if status == STATUS_SUCCESS else before
    return PurgeOutcome(status=status & 0xFFFFFFFF, before=before, after=after)
