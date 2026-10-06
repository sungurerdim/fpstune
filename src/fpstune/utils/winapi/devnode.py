"""Device-node facts through cfgmgr32: which devices exist, which driver package runs one.

What a device's driver INF *installs* — the stock value of a registry setting the
driver ships — can only be read from the INF the device is bound to, and the
binding is three locale-independent device properties: ``DriverInfPath`` (the
``oemNN.inf`` copy in ``%WINDIR%\\INF``), ``DriverInfSection`` and
``DriverInfSectionExt`` (the platform decoration, ``.NTamd64``). Reading them
through ``Get-PnpDeviceProperty`` would start a PowerShell per device; these
calls start nothing. Constants from devpkey.h and cfgmgr32.h.
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

CR_SUCCESS = 0x00
CR_BUFFER_SMALL = 0x1A

CM_LOCATE_DEVNODE_NORMAL = 0x00
CM_GETIDLIST_FILTER_PRESENT = 0x00000100
CM_GETIDLIST_FILTER_CLASS = 0x00000200

DEVPROP_TYPE_STRING = 0x00000012

# {4d36e968-e325-11ce-bfc1-08002be10318}: the display adapter setup class.
CLASS_DISPLAY = "{4d36e968-e325-11ce-bfc1-08002be10318}"

# devpkey.h: DEVPKEY_Device_DriverInfPath / DriverInfSection / DriverInfSectionExt.
_DRIVER_INF_FMTID = "a8b865dd-2e3d-4094-ad97-e593a70c75d6"
_PID_DRIVER_INF_PATH = 5
_PID_DRIVER_INF_SECTION = 6
_PID_DRIVER_INF_SECTION_EXT = 7


class _Guid(ctypes.Structure):
    _fields_ = (
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    )


class _DevPropKey(ctypes.Structure):
    _fields_ = (("fmtid", _Guid), ("pid", wintypes.DWORD))


def _property_key(fmtid: str, pid: int) -> _DevPropKey:
    parsed = uuid.UUID(fmtid)
    guid = _Guid(
        parsed.time_low,
        parsed.time_mid,
        parsed.time_hi_version,
        (ctypes.c_ubyte * 8)(*parsed.bytes[8:]),
    )
    return _DevPropKey(guid, pid)


@dataclass(frozen=True)
class DriverInf:
    """The INF a device is bound to, and the install section chosen from it."""

    path: str  # file name inside %WINDIR%\INF, e.g. "oem9.inf"
    section: str  # e.g. "Section057"
    section_ext: str  # platform decoration, e.g. ".NTamd64"; empty when undecorated


def decode_string_property(raw: bytes) -> str:
    """A DEVPROP_TYPE_STRING buffer: UTF-16LE, NUL-terminated."""
    return raw.decode("utf-16-le", errors="replace").split("\x00", 1)[0]


def split_multi_sz(text: str) -> list[str]:
    """A REG_MULTI_SZ-style buffer (``a\\0b\\0\\0``) as its non-empty strings."""
    return [item for item in text.split("\x00") if item]


def _cfgmgr() -> Any:
    lib = ctypes.WinDLL("cfgmgr32", use_last_error=True)
    lib.CM_Locate_DevNodeW.argtypes = (
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPCWSTR,
        wintypes.ULONG,
    )
    lib.CM_Locate_DevNodeW.restype = wintypes.DWORD
    lib.CM_Get_DevNode_PropertyW.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(_DevPropKey),
        ctypes.POINTER(wintypes.ULONG),
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.ULONG,
    )
    lib.CM_Get_DevNode_PropertyW.restype = wintypes.DWORD
    lib.CM_Get_Device_ID_List_SizeW.argtypes = (
        ctypes.POINTER(wintypes.ULONG),
        wintypes.LPCWSTR,
        wintypes.ULONG,
    )
    lib.CM_Get_Device_ID_List_SizeW.restype = wintypes.DWORD
    lib.CM_Get_Device_ID_ListW.argtypes = (
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
    )
    lib.CM_Get_Device_ID_ListW.restype = wintypes.DWORD
    return lib


def present_device_ids(class_guid: str) -> list[str]:
    """Instance ids of the devices of one setup class that are present now."""
    lib = _cfgmgr()
    flags = CM_GETIDLIST_FILTER_CLASS | CM_GETIDLIST_FILTER_PRESENT
    size = wintypes.ULONG(0)
    if lib.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), class_guid, flags) != CR_SUCCESS:
        return []
    buffer = ctypes.create_unicode_buffer(size.value)
    if lib.CM_Get_Device_ID_ListW(class_guid, buffer, size.value, flags) != CR_SUCCESS:
        return []
    return split_multi_sz(ctypes.wstring_at(buffer, size.value))


def _string_property(lib: Any, devinst: int, key: _DevPropKey) -> str | None:
    """One string property of a device node, or None when the node has none."""
    prop_type = wintypes.ULONG(0)
    size = wintypes.ULONG(0)
    status = lib.CM_Get_DevNode_PropertyW(
        devinst, ctypes.byref(key), ctypes.byref(prop_type), None, ctypes.byref(size), 0
    )
    if status != CR_BUFFER_SMALL or size.value == 0:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    status = lib.CM_Get_DevNode_PropertyW(
        devinst, ctypes.byref(key), ctypes.byref(prop_type), buffer, ctypes.byref(size), 0
    )
    if status != CR_SUCCESS or prop_type.value != DEVPROP_TYPE_STRING:
        return None
    return decode_string_property(buffer.raw[: size.value])


def driver_inf(instance_id: str) -> DriverInf | None:
    """The INF, section and decoration a device's installed driver came from.

    None when the device is not known to the system or carries no INF binding
    (a device with no driver installed): the caller then has no stock to read.
    """
    lib = _cfgmgr()
    devinst = wintypes.DWORD(0)
    if (
        lib.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, CM_LOCATE_DEVNODE_NORMAL)
        != CR_SUCCESS
    ):
        return None
    path = _string_property(
        lib, devinst.value, _property_key(_DRIVER_INF_FMTID, _PID_DRIVER_INF_PATH)
    )
    section = _string_property(
        lib, devinst.value, _property_key(_DRIVER_INF_FMTID, _PID_DRIVER_INF_SECTION)
    )
    if not path or not section:
        return None
    ext = _string_property(
        lib, devinst.value, _property_key(_DRIVER_INF_FMTID, _PID_DRIVER_INF_SECTION_EXT)
    )
    return DriverInf(path=path, section=section, section_ext=ext or "")
