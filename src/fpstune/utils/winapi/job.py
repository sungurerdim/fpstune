"""A Job Object around a child process: what its whole tree is doing, and stopping it.

A process handle answers for one process. The commands fpstune runs are trees:
PowerShell starts ``Dism.exe``, ``sfc.exe`` or ``vssadmin.exe`` and waits on it,
so the parent can sit idle for half an hour while the real work happens a level
down. A Job Object counts CPU time and I/O for every process in it, children
included, and ``TerminateJobObject`` stops all of them at once — which a kill of
the parent never did (the orphaned ``Dism.exe`` in ``utils/powershell.py``).

Windows 8 and later allow nested jobs, so assigning a child that a terminal or a
launcher already put in a job of its own still works.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

_JOB_OBJECT_BASIC_AND_IO_ACCOUNTING_INFORMATION = 8


class _BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _BASIC_AND_IO_ACCOUNTING(ctypes.Structure):
    _fields_ = [("BasicInfo", _BASIC_ACCOUNTING), ("IoInfo", _IO_COUNTERS)]


@dataclass(frozen=True)
class TreeActivity:
    """Cumulative counters for every process the job has held."""

    cpu_seconds: float
    io_bytes: int
    active_processes: int


class ProcessTreeJob:
    """One job holding one child and everything it starts."""

    def __init__(self, handle: int) -> None:
        self._handle = handle

    @classmethod
    def around(cls, process_handle: int) -> ProcessTreeJob | None:
        """A job holding ``process_handle``, or None where Windows refused one."""
        if sys.platform != "win32":
            return None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process_handle)):
            kernel32.CloseHandle(job)
            return None
        return cls(int(job))

    def activity(self) -> TreeActivity | None:
        """The tree's counters so far, or None when the query failed."""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        info = _BASIC_AND_IO_ACCOUNTING()
        ok = kernel32.QueryInformationJobObject(
            wintypes.HANDLE(self._handle),
            _JOB_OBJECT_BASIC_AND_IO_ACCOUNTING_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        )
        if not ok:
            return None
        basic, io = info.BasicInfo, info.IoInfo
        # Job times are in 100 ns units.
        cpu = (basic.TotalUserTime + basic.TotalKernelTime) / 10_000_000
        moved = io.ReadTransferCount + io.WriteTransferCount + io.OtherTransferCount
        return TreeActivity(cpu, int(moved), int(basic.ActiveProcesses))

    def terminate(self) -> None:
        """Stop every process in the tree."""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject(wintypes.HANDLE(self._handle), 1)

    def close(self) -> None:
        """Release the handle. Processes keep running: no kill-on-close is set."""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(wintypes.HANDLE(self._handle))
