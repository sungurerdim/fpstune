"""Interface index to the device behind it, without asking PowerShell.

A network setting is bound to an ``InterfaceIndex`` at discovery; the device
behind that index is the adapter's PnP instance id. iphlpapi turns the index
into the interface LUID, whose two fields (``NetLuidIndex``, ``IfType``) the
network setup class stores next to the adapter's ``DeviceInstanceID`` in its
driver key — the same two numbers ``Get-NetAdapter`` joins on.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

# NET_LUID_LH.Info: Reserved:24, NetLuidIndex:24, IfType:16 (low to high bits).
_INDEX_SHIFT = 24
_INDEX_MASK = 0xFFFFFF
_IFTYPE_SHIFT = 48
_IFTYPE_MASK = 0xFFFF

# {4d36e972-e325-11ce-bfc1-08002be10318}: the network adapter setup class.
_NET_CLASS_KEY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"


def split_luid(luid: int) -> tuple[int, int]:
    """``(NetLuidIndex, IfType)`` of a 64-bit interface LUID."""
    return (luid >> _INDEX_SHIFT) & _INDEX_MASK, (luid >> _IFTYPE_SHIFT) & _IFTYPE_MASK


def interface_luid(interface_index: int) -> int | None:
    """The LUID of an interface index, or None when no such interface exists."""
    function = ctypes.WinDLL("iphlpapi", use_last_error=True).ConvertInterfaceIndexToLuid
    function.argtypes = (wintypes.ULONG, ctypes.POINTER(ctypes.c_uint64))
    function.restype = wintypes.DWORD
    luid = ctypes.c_uint64(0)
    if function(interface_index, ctypes.byref(luid)) != 0:
        return None
    return luid.value


def adapter_instance_id(interface_index: int) -> str | None:
    """The PnP instance id of the adapter that owns ``interface_index``, or None."""
    import winreg

    luid = interface_luid(interface_index)
    if luid is None:
        return None
    wanted = split_luid(luid)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _NET_CLASS_KEY) as klass:
        position = 0
        while True:
            try:
                name = winreg.EnumKey(klass, position)
            except OSError:
                return None
            position += 1
            try:
                with winreg.OpenKey(klass, name) as entry:
                    index = winreg.QueryValueEx(entry, "NetLuidIndex")[0]
                    if_type = winreg.QueryValueEx(entry, "*IfType")[0]
                    if (int(index), int(if_type)) == wanted:
                        return str(winreg.QueryValueEx(entry, "DeviceInstanceID")[0])
            except OSError:
                # "Configuration" and "Properties" sit beside the numbered
                # entries and are not adapters; an unreadable one cannot be ours.
                continue
