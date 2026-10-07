"""What Windows' own power policy is doing to the processor, read without a subprocess.

A processor held below its nominal performance has three kinds of reasons that
Windows can tell apart from heat, and this reads the two that a counter cannot:

- **the machine is on battery** (`GetSystemPowerStatus`, `ACLineStatus`): a laptop off
  its charger is under a power budget the platform sets;
- **the active power plan caps the processor** (`PowerReadACValueIndex` /
  `PowerReadDCValueIndex` on `PROCTHROTTLEMAX`, "Maximum processor state"): a plan that
  says 50 % is a CPU that will never be asked for more than half its nominal speed,
  which is exactly "under half the machine's capacity" and has nothing to do with heat.

Both are the policy's own numbers: nothing is inferred, and a value that cannot be read
is None and never a default. The plan GUIDs are the ones `powercfg /q SCHEME_CURRENT
SUB_PROCESSOR PROCTHROTTLEMAX` printed on the development machine (alias `SUB_PROCESSOR`,
alias `PROCTHROTTLEMAX`, range 0-100 %, units %).

No `powercfg.exe`: its output is translated, and a process per read is a cost this is
called for while a game runs.
"""

from __future__ import annotations

import ctypes
import uuid
from dataclasses import dataclass
from typing import Protocol

from fpstune.utils.logger import get_logger

logger = get_logger()

SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"

_AC_OFFLINE = 0
_AC_ONLINE = 1
"""`SYSTEM_POWER_STATUS.ACLineStatus`: 0 offline, 1 online, 255 unknown."""


@dataclass(frozen=True)
class PowerState:
    """The two policy facts, each None when it could not be read."""

    on_battery: bool | None
    processor_cap_percent: int | None
    """Maximum processor state of the active plan on the power source in use (0-100)."""


class PowerApi(Protocol):
    def ac_line_status(self) -> int | None: ...

    def maximum_processor_state(self, on_battery: bool) -> int | None: ...


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> _Guid:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class WindowsPower:
    """`kernel32` and `powrprof`, bound the way their headers declare them."""

    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(_SystemPowerStatus)]
        self._kernel32.GetSystemPowerStatus.restype = ctypes.c_int
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p
        self._powrprof = ctypes.WinDLL("powrprof")
        dword_p = ctypes.POINTER(ctypes.c_uint32)
        guid_p = ctypes.POINTER(_Guid)
        self._powrprof.PowerGetActiveScheme.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(_Guid)),
        ]
        for name in ("PowerReadACValueIndex", "PowerReadDCValueIndex"):
            function = getattr(self._powrprof, name)
            function.argtypes = [ctypes.c_void_p, guid_p, guid_p, guid_p, dword_p]
            function.restype = ctypes.c_uint32
        self._powrprof.PowerGetActiveScheme.restype = ctypes.c_uint32

    def ac_line_status(self) -> int | None:
        status = _SystemPowerStatus()
        if not self._kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        return int(status.ACLineStatus)

    def maximum_processor_state(self, on_battery: bool) -> int | None:
        scheme = ctypes.POINTER(_Guid)()
        if self._powrprof.PowerGetActiveScheme(None, ctypes.byref(scheme)) != 0 or not scheme:
            return None
        try:
            value = ctypes.c_uint32()
            read = (
                self._powrprof.PowerReadDCValueIndex
                if on_battery
                else self._powrprof.PowerReadACValueIndex
            )
            status = read(
                None,
                scheme,
                ctypes.byref(_Guid.parse(SUB_PROCESSOR)),
                ctypes.byref(_Guid.parse(PROCTHROTTLEMAX)),
                ctypes.byref(value),
            )
            return int(value.value) if status == 0 else None
        finally:
            self._kernel32.LocalFree(scheme)


def read(api: PowerApi | None = None) -> PowerState:
    """Battery state and the active plan's processor cap for the source in use."""
    try:
        power = api if api is not None else WindowsPower()
        line = power.ac_line_status()
        on_battery = True if line == _AC_OFFLINE else False if line == _AC_ONLINE else None
        # With the source unknown, the AC value is read: a plan that caps the CPU
        # usually does so on both, and the answer is labelled by what was asked.
        cap = power.maximum_processor_state(bool(on_battery))
    except (OSError, AttributeError) as exc:
        logger.debug("Power policy could not be read: %s", exc)
        return PowerState(on_battery=None, processor_cap_percent=None)
    return PowerState(
        on_battery=on_battery,
        processor_cap_percent=cap if cap is not None and 0 <= cap <= 100 else None,
    )
