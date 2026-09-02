"""Display adapters, the monitors on them, and their modes — ``user32`` via ctypes.

Three PowerShell commands used to compile C# classes at run time for
``EnumDisplayDevices``, ``EnumDisplaySettings`` and ``ChangeDisplaySettingsEx``
(monitor detection, the refresh-rate action, the debug route and the A12
self-check). That is the ``Add-Type`` pattern the package docstring explains;
this module is the replacement.

The A1 lesson survives the port: the ``DISPLAY_DEVICE`` struct never crosses a
scripting binder. Here it never leaves Python at all, and each record carries
the same three facts the C# loop emitted — device name, ``StateFlags`` and the
monitor's device-interface path — because ``StateFlags`` bit 0 is the one
attachment answer WMI cannot give.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
DISPLAY_DEVICE_MIRRORING_DRIVER = 0x00000008
EDD_GET_DEVICE_INTERFACE_NAME = 0x00000001

# EnumDisplaySettings mode indices: (DWORD)-1 is the current mode, -2 the
# registry mode; 0.. walks the mode table.
ENUM_CURRENT_SETTINGS = 0xFFFFFFFF
ENUM_REGISTRY_SETTINGS = 0xFFFFFFFE
_MODE_TABLE_CEILING = 4096

CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
DISP_CHANGE_SUCCESSFUL = 0

DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", wintypes.LONG),
        ("dmPositionY", wintypes.LONG),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class AdapterRecord:
    """One adapter head as EnumDisplayDevices reports it."""

    device_name: str
    state_flags: int
    monitor_interface_path: str

    @property
    def attached(self) -> bool:
        return bool(self.state_flags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)

    @property
    def primary(self) -> bool:
        return bool(self.state_flags & DISPLAY_DEVICE_PRIMARY_DEVICE)

    @property
    def mirroring(self) -> bool:
        return bool(self.state_flags & DISPLAY_DEVICE_MIRRORING_DRIVER)

    def as_record(self) -> str:
        """The ``name|flags|path`` line the C# class used to emit — the self-check
        still speaks it, and it stays useful as a log line."""
        return f"{self.device_name}|{self.state_flags}|{self.monitor_interface_path}"

    @classmethod
    def from_record(cls, record: str) -> AdapterRecord | None:
        parts = record.split("|", 2)
        if len(parts) < 3:
            return None
        try:
            flags = int(parts[1])
        except ValueError:
            return None
        return cls(parts[0], flags, parts[2])


@dataclass(frozen=True)
class DisplayMode:
    width: int
    height: int
    refresh_hz: int


def _user32() -> ctypes.WinDLL:
    return ctypes.WinDLL("user32", use_last_error=True)


def enumerate_adapters() -> list[AdapterRecord]:
    """Every adapter head, with the interface path of the monitor on it ("" if none)."""
    if sys.platform != "win32":
        return []
    enum = _user32().EnumDisplayDevicesW
    enum.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(DISPLAY_DEVICEW),
        wintypes.DWORD,
    ]
    enum.restype = wintypes.BOOL

    records: list[AdapterRecord] = []
    index = 0
    while True:
        adapter = DISPLAY_DEVICEW()
        adapter.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not enum(None, index, ctypes.byref(adapter), 0):
            break
        monitor = DISPLAY_DEVICEW()
        monitor.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        path = ""
        if enum(adapter.DeviceName, 0, ctypes.byref(monitor), EDD_GET_DEVICE_INTERFACE_NAME):
            path = monitor.DeviceID
        records.append(
            AdapterRecord(adapter.DeviceName.rstrip("\0 "), int(adapter.StateFlags), path)
        )
        index += 1
    return records


def _fresh_devmode() -> DEVMODEW:
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    return mode


def _enum_settings(device_name: str, mode_index: int) -> DEVMODEW | None:
    if sys.platform != "win32":
        return None
    enum = _user32().EnumDisplaySettingsW
    enum.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW)]
    enum.restype = wintypes.BOOL
    mode = _fresh_devmode()
    if not enum(device_name, mode_index, ctypes.byref(mode)):
        return None
    return mode


def _to_mode(devmode: DEVMODEW) -> DisplayMode:
    return DisplayMode(
        width=int(devmode.dmPelsWidth),
        height=int(devmode.dmPelsHeight),
        refresh_hz=int(devmode.dmDisplayFrequency),
    )


def current_mode(device_name: str) -> DisplayMode | None:
    """The mode the head runs right now (physical pixels, not DPI-scaled)."""
    mode = _enum_settings(device_name, ENUM_CURRENT_SETTINGS)
    return _to_mode(mode) if mode is not None else None


def enumerate_modes(device_name: str) -> list[DisplayMode]:
    """The head's whole mode table, in the order the driver lists it."""
    modes: list[DisplayMode] = []
    for index in range(_MODE_TABLE_CEILING):
        mode = _enum_settings(device_name, index)
        if mode is None:
            break
        modes.append(_to_mode(mode))
    return modes


def max_refresh_at(device_name: str, width: int, height: int) -> int:
    """The highest refresh the mode table offers at exactly this resolution, or 0."""
    return max(
        (
            m.refresh_hz
            for m in enumerate_modes(device_name)
            if m.width == width and m.height == height
        ),
        default=0,
    )


def change_mode(
    device_name: str, width: int, height: int, refresh_hz: int, fields: int, *, test_only: bool
) -> int:
    """Test (``CDS_TEST``) or write (``CDS_UPDATEREGISTRY``) one mode; the DISP_CHANGE code.

    The DEVMODE starts from the current mode so every field the caller does not
    name keeps the driver's own value; ``fields`` says which of width, height and
    frequency the call is allowed to change.
    """
    if sys.platform != "win32":
        return -1
    mode = _enum_settings(device_name, ENUM_CURRENT_SETTINGS) or _fresh_devmode()
    mode.dmPelsWidth = width
    mode.dmPelsHeight = height
    mode.dmDisplayFrequency = refresh_hz
    mode.dmFields = fields
    change = _user32().ChangeDisplaySettingsExW
    change.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(DEVMODEW),
        wintypes.HWND,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    change.restype = ctypes.c_long
    flags = CDS_TEST if test_only else CDS_UPDATEREGISTRY
    return int(change(device_name, ctypes.byref(mode), None, flags, None))
