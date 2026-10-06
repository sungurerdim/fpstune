"""Who owns a TCP port, and what that process is — numbers and paths, never command text.

A previous fpstune that hangs can still hold the single-instance lock socket
while answering no HTTP at all, so the only honest way to find it is the
kernel's own table: ``GetExtendedTcpTable`` (``TCP_TABLE_OWNER_PID_ALL``,
``AF_INET``) lists every IPv4 socket with its owning PID, bound-but-not-listening
ones included. Locale does not touch any of it — the previous version read
``netstat``'s English "LISTENING" and was wrong on a Turkish or German Windows.

Identity comes from two calls on the PID:

- ``QueryFullProcessImageNameW`` — the executable's full path.
- ``NtQueryInformationProcess(ProcessCommandLineInformation = 60)`` — the command
  line, in one call that needs only ``PROCESS_QUERY_LIMITED_INFORMATION``. The
  other route is reading the PEB: ``ProcessBasicInformation``, then
  ``ReadProcessMemory`` through ``RTL_USER_PROCESS_PARAMETERS`` — which needs
  ``PROCESS_VM_READ``, differs between a 32-bit and a 64-bit target, and walks
  structure offsets Microsoft documents as subject to change. Class 60 has been
  stable since Windows 8.1 (every Windows 11 build, fpstune's only target) and is
  what Process Explorer-style tools use; the cost is that Microsoft's reference
  page does not list it, so a failure here reads as "unknown" and the caller
  refuses to touch the process rather than guessing.

Parent and child links come from ``CreateToolhelp32Snapshot``. Everything that
parses bytes (``parse_tcp_owner_table``, ``decode_unicode_string``) takes a plain
buffer so a test can hand it a fake one.
"""

from __future__ import annotations

import ctypes
import socket
import struct
from ctypes import wintypes
from dataclasses import dataclass

AF_INET = 2
TCP_TABLE_OWNER_PID_ALL = 5
_ERROR_INSUFFICIENT_BUFFER = 122
_ERROR_INVALID_PARAMETER = 87

_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_STILL_ACTIVE = 259

_PROCESS_COMMAND_LINE_INFORMATION = 60
_STATUS_SUCCESS = 0
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
_STATUS_BUFFER_OVERFLOW = 0x80000005
_STATUS_BUFFER_TOO_SMALL = 0xC0000023
_COMMAND_LINE_ATTEMPTS = 4

_TCP_ROW = struct.Struct("<6I")
"""MIB_TCPROW_OWNER_PID: state, local addr, local port, remote addr, remote port, pid."""

_TERMINATE_EXIT_CODE = 1
_TERMINATE_WAIT_MS = 5000


@dataclass(frozen=True)
class TcpRow:
    state: int
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    pid: int


@dataclass(frozen=True)
class ProcessEntry:
    pid: int
    parent_pid: int
    exe_name: str


def _port(raw: int) -> int:
    """A port as the table stores it: network byte order in the low 16 bits."""
    return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)


def _address(raw: int) -> str:
    return socket.inet_ntoa(struct.pack("<I", raw))


def parse_tcp_owner_table(buffer: bytes) -> list[TcpRow]:
    """The rows of a ``MIB_TCPTABLE_OWNER_PID`` buffer.

    Raises ``ValueError`` when the buffer is shorter than its own header claims:
    a half-read table must not read as "nobody owns that port".
    """
    if len(buffer) < 4:
        raise ValueError("TCP table buffer is shorter than its header")
    (count,) = struct.unpack_from("<I", buffer, 0)
    needed = 4 + count * _TCP_ROW.size
    if len(buffer) < needed:
        raise ValueError(f"TCP table claims {count} rows but holds {(len(buffer) - 4) // 24}")
    rows = []
    for index in range(count):
        state, laddr, lport, raddr, rport, pid = _TCP_ROW.unpack_from(
            buffer, 4 + index * _TCP_ROW.size
        )
        rows.append(
            TcpRow(state, _address(laddr), _port(lport), _address(raddr), _port(rport), pid)
        )
    return rows


def tcp_table_bytes() -> bytes:
    """The raw IPv4 TCP table with owning PIDs, retrying while the table grows."""
    function = ctypes.WinDLL("iphlpapi", use_last_error=True).GetExtendedTcpTable
    function.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    )
    function.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    code = function(None, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    for _ in range(8):
        if code not in (0, _ERROR_INSUFFICIENT_BUFFER):
            break
        size.value += _TCP_ROW.size * 16  # sockets can appear between the two calls
        buffer = ctypes.create_string_buffer(size.value)
        code = function(buffer, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
        if code == 0:
            return buffer.raw[: size.value]
    raise ctypes.WinError(code)


def socket_owner_pids(
    port: int, addresses: tuple[str, ...] = ("127.0.0.1", "0.0.0.0")
) -> list[int]:  # noqa: S104 - a table filter, not a bind
    """The PIDs that own an unconnected IPv4 socket on ``port``, in table order.

    Unconnected means remote ``0.0.0.0:0``: a bound or listening socket, which is
    what blocks a second ``bind``. A client whose ephemeral port happens to equal
    ``port`` is a connection, not a holder, and PID 0 (TIME_WAIT leftovers) owns
    nothing.
    """
    owners: list[int] = []
    for row in parse_tcp_owner_table(tcp_table_bytes()):
        if (
            row.local_port == port
            and row.local_address in addresses
            and row.remote_port == 0
            and row.pid
            and row.pid not in owners
        ):
            owners.append(row.pid)
    return owners


def _kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel32


def image_path(pid: int) -> str | None:
    """The full executable path of ``pid``, or None when it cannot be read."""
    kernel32 = _kernel32()
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def creation_time(pid: int) -> int | None:
    """When ``pid`` started, as a FILETIME tick count, or None when unreadable."""
    kernel32 = _kernel32()
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        *([ctypes.POINTER(wintypes.FILETIME)] * 4),
    )
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        ok = kernel32.GetProcessTimes(
            handle, *(ctypes.byref(t) for t in (created, exited, kernel, user))
        )
        if not ok:
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel32.CloseHandle(handle)


def has_exited(pid: int) -> bool:
    """Whether ``pid`` is a process that already ended but is still listed.

    A process someone still holds a handle to stays in the process list after it
    exits, and its image can no longer be read; ``GetExitCodeProcess`` tells that
    apart from a live process that merely refuses to be opened.
    """
    kernel32 = _kernel32()
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD(0)
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value != _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def decode_unicode_string(buffer: bytes, header_size: int) -> str:
    """The text of a ``UNICODE_STRING`` followed by its characters in one buffer.

    ``ProcessCommandLineInformation`` fills ``Length`` (bytes) first, then a
    pointer, then the characters directly after the ``header_size``-byte header.
    """
    if len(buffer) < header_size:
        raise ValueError("buffer is shorter than a UNICODE_STRING header")
    (length,) = struct.unpack_from("<H", buffer, 0)
    data = buffer[header_size : header_size + length]
    if len(data) < length:
        raise ValueError("UNICODE_STRING claims more characters than the buffer holds")
    return data.decode("utf-16-le")


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = (
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_void_p),
    )


def command_line(pid: int) -> str | None:
    """The command line ``pid`` was started with, or None when it cannot be read."""
    ntdll = ctypes.WinDLL("ntdll")
    function = ntdll.NtQueryInformationProcess
    function.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    )
    function.restype = ctypes.c_long
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        needed = wintypes.ULONG(0)
        size = ctypes.sizeof(_UNICODE_STRING) + 4096
        for _ in range(_COMMAND_LINE_ATTEMPTS):
            buffer = ctypes.create_string_buffer(size)
            status = (
                function(
                    handle,
                    _PROCESS_COMMAND_LINE_INFORMATION,
                    buffer,
                    size,
                    ctypes.byref(needed),
                )
                & 0xFFFFFFFF
            )
            if status == _STATUS_SUCCESS:
                try:
                    return decode_unicode_string(buffer.raw, ctypes.sizeof(_UNICODE_STRING))
                except ValueError:
                    return None
            if status in (
                _STATUS_INFO_LENGTH_MISMATCH,
                _STATUS_BUFFER_OVERFLOW,
                _STATUS_BUFFER_TOO_SMALL,
            ):
                size = max(size * 2, needed.value)
                continue
            return None
        return None
    finally:
        kernel32.CloseHandle(handle)


def split_command_line(text: str) -> list[str]:
    """``text`` split the way Windows itself splits a command line (``CommandLineToArgvW``)."""
    if not text.strip():
        return []
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")
    shell32.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    count = ctypes.c_int(0)
    argv = shell32.CommandLineToArgvW(text, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [str(argv[index]) for index in range(count.value)]
    finally:
        kernel32.LocalFree(argv)


def list_processes() -> list[ProcessEntry]:
    """Every running process with its parent's PID (``CreateToolhelp32Snapshot``)."""
    from fpstune.settings.executors.game_processes import (
        _PROCESSENTRY32W,
        INVALID_HANDLE_VALUE,
        TH32CS_SNAPPROCESS,
    )

    kernel32 = _kernel32()
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    found: list[ProcessEntry] = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            found.append(
                ProcessEntry(
                    int(entry.th32ProcessID), int(entry.th32ParentProcessID), entry.szExeFile
                )
            )
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def terminate(pid: int) -> str:
    """End ``pid`` and wait for it to be gone: ``ended``, ``already_gone`` or ``failed``."""
    kernel32 = _kernel32()
    kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    handle = kernel32.OpenProcess(_PROCESS_TERMINATE | _SYNCHRONIZE, False, pid)
    if not handle:
        code = ctypes.get_last_error()
        if code == _ERROR_INVALID_PARAMETER or has_exited(pid):
            return "already_gone"
        return "failed"
    try:
        if not kernel32.TerminateProcess(handle, _TERMINATE_EXIT_CODE):
            return "already_gone" if has_exited(pid) else "failed"
        if kernel32.WaitForSingleObject(handle, _TERMINATE_WAIT_MS) == _WAIT_OBJECT_0:
            return "ended"
        return "failed"
    finally:
        kernel32.CloseHandle(handle)
