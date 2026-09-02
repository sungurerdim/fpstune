"""Wi-Fi facts and connection control through ``wlanapi.dll``, via ctypes.

Two places used to touch wlanapi. The hardware panel compiled a C# class at run
time (``Add-Type``, six ``DllImport`` lines) to read the connected interface's
channel, centre frequency, PHY, signal, auth and SSID — the pattern Windows
Defender flagged on 2026-09-02. The Wi-Fi reconnect route never used the API at
all: it parsed ``netsh wlan show profiles`` for the English label
``All User Profile``, so on a Turkish or German Windows the reconnect after the
wired-radio tweak silently did nothing.

Everything here is numeric or a name the API hands back: enums, kHz, a profile
string. No text Windows localizes is ever matched (A9, C4).
"""

from __future__ import annotations

import ctypes
import sys
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass

ERROR_SUCCESS = 0
WLAN_API_VERSION = 2

# wlan_interface_state_connected; the other states are not connections.
WLAN_INTERFACE_STATE_CONNECTED = 1
# WLAN_INTF_OPCODE values used here.
WLAN_INTF_OPCODE_CURRENT_CONNECTION = 7
WLAN_INTF_OPCODE_CHANNEL_NUMBER = 8
# DOT11_BSS_TYPE / WLAN_CONNECTION_MODE values used here.
DOT11_BSS_TYPE_INFRASTRUCTURE = 1
WLAN_CONNECTION_MODE_PROFILE = 0

_SSID_MAX = 32
_RATES_MAX = 126


class DOT11_SSID(ctypes.Structure):
    _fields_ = [("uSSIDLength", wintypes.ULONG), ("ucSSID", ctypes.c_ubyte * _SSID_MAX)]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", ctypes.c_ubyte * 16),
        ("strInterfaceDescription", ctypes.c_wchar * 256),
        ("isState", wintypes.DWORD),
    ]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", wintypes.DWORD),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11PhyType", wintypes.DWORD),
        ("uDot11PhyIndex", wintypes.ULONG),
        ("wlanSignalQuality", wintypes.ULONG),
        ("ulRxRate", wintypes.ULONG),
        ("ulTxRate", wintypes.ULONG),
    ]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("bSecurityEnabled", wintypes.BOOL),
        ("bOneXEnabled", wintypes.BOOL),
        ("dot11AuthAlgorithm", wintypes.DWORD),
        ("dot11CipherAlgorithm", wintypes.DWORD),
    ]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("isState", wintypes.DWORD),
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfileName", ctypes.c_wchar * 256),
        ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
        ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES),
    ]


class WLAN_RATE_SET(ctypes.Structure):
    _fields_ = [("uRateSetLength", wintypes.ULONG), ("usRateSet", wintypes.USHORT * _RATES_MAX)]


class WLAN_BSS_ENTRY(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("uPhyId", wintypes.ULONG),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11BssType", wintypes.DWORD),
        ("dot11BssPhyType", wintypes.DWORD),
        ("lRssi", wintypes.LONG),
        ("uLinkQuality", wintypes.ULONG),
        ("bInRegDomain", ctypes.c_ubyte),
        ("usBeaconPeriod", wintypes.USHORT),
        ("ullTimestamp", ctypes.c_ulonglong),
        ("ullHostTimestamp", ctypes.c_ulonglong),
        ("usCapabilityInformation", wintypes.USHORT),
        ("ulChCenterFrequency", wintypes.ULONG),
        ("wlanRateSet", WLAN_RATE_SET),
        ("ulIeOffset", wintypes.ULONG),
        ("ulIeSize", wintypes.ULONG),
    ]


class WLAN_PROFILE_INFO(ctypes.Structure):
    _fields_ = [("strProfileName", ctypes.c_wchar * 256), ("dwFlags", wintypes.DWORD)]


class WLAN_CONNECTION_PARAMETERS(ctypes.Structure):
    _fields_ = [
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfile", wintypes.LPCWSTR),
        ("pDot11Ssid", ctypes.c_void_p),
        ("pDesiredBssidList", ctypes.c_void_p),
        ("dot11BssType", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class WlanInterface:
    guid: str  # lowercase, no braces — the form the join with Get-NetAdapter uses
    description: str
    state: int

    @property
    def connected(self) -> bool:
        return self.state == WLAN_INTERFACE_STATE_CONNECTED


@dataclass(frozen=True)
class WlanRecord:
    """One connected radio, in the API's own numbers."""

    interface_guid: str
    channel: int
    center_khz: int  # 0 when no BSS entry matched the connected BSSID
    phy_type: int
    signal_percent: int
    auth_algorithm: int
    ssid: str
    profile_name: str
    bssid: str

    def as_record_line(self) -> str:
        """``guid|channel|freqKHz|phy|signal|auth|ssid`` — SSID last because an
        SSID may itself contain the separator."""
        return (
            f"{self.interface_guid}|{self.channel}|{self.center_khz}|{self.phy_type}|"
            f"{self.signal_percent}|{self.auth_algorithm}|{self.ssid}"
        )


# dot11_phy_type, by the API's own numeric enum; anything else is an empty name.
PHY_NAMES = {
    4: "802.11a",
    5: "802.11b",
    6: "802.11g",
    7: "802.11n",
    8: "802.11ac",
    9: "802.11ad",
    10: "802.11ax",
    11: "802.11be",
}


def phy_name(phy_type: int) -> str:
    """The radio standard's name, or empty when the enum is unknown."""
    return PHY_NAMES.get(phy_type, "")


def band_ghz(center_khz: int) -> float:
    """The band from the BSS entry's centre frequency; 0 when no entry answered."""
    if center_khz >= 5_925_000:
        return 6.0
    if center_khz >= 4_900_000:
        return 5.0
    if center_khz >= 2_400_000:
        return 2.4
    return 0.0


def _guid_str(raw: bytes) -> str:
    return str(uuid.UUID(bytes_le=bytes(raw)))


def _guid_bytes(guid: str) -> ctypes.Array[ctypes.c_ubyte]:
    raw = uuid.UUID(guid.strip("{}")).bytes_le
    return (ctypes.c_ubyte * 16)(*raw)


def _ssid_text(ssid: DOT11_SSID) -> str:
    length = int(ssid.uSSIDLength)
    if length <= 0 or length > _SSID_MAX:
        return ""
    return bytes(ssid.ucSSID[:length]).decode("utf-8", errors="replace")


def _mac(raw: ctypes.Array[ctypes.c_ubyte]) -> str:
    return ":".join(f"{b:02x}" for b in bytes(raw[:6]))


def _api() -> ctypes.WinDLL:
    api = ctypes.WinDLL("wlanapi", use_last_error=True)
    api.WlanOpenHandle.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.HANDLE),
    ]
    api.WlanOpenHandle.restype = wintypes.DWORD
    api.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    api.WlanCloseHandle.restype = wintypes.DWORD
    api.WlanEnumInterfaces.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.WlanEnumInterfaces.restype = wintypes.DWORD
    api.WlanQueryInterface.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_ubyte * 16),
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    api.WlanQueryInterface.restype = wintypes.DWORD
    api.WlanGetNetworkBssList.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_ubyte * 16),
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.BOOL,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.WlanGetNetworkBssList.restype = wintypes.DWORD
    api.WlanGetProfileList.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_ubyte * 16),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.WlanGetProfileList.restype = wintypes.DWORD
    api.WlanConnect.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_ubyte * 16),
        ctypes.POINTER(WLAN_CONNECTION_PARAMETERS),
        ctypes.c_void_p,
    ]
    api.WlanConnect.restype = wintypes.DWORD
    api.WlanDisconnect.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_ubyte * 16),
        ctypes.c_void_p,
    ]
    api.WlanDisconnect.restype = wintypes.DWORD
    api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    api.WlanFreeMemory.restype = None
    return api


@contextmanager
def _handle() -> Generator[tuple[ctypes.WinDLL, wintypes.HANDLE] | None, None, None]:
    """An open wlanapi client handle, or ``None`` when the service is not there."""
    if sys.platform != "win32":
        yield None
        return
    try:
        api = _api()
    except OSError:
        yield None
        return
    negotiated = wintypes.DWORD(0)
    handle = wintypes.HANDLE()
    if (
        api.WlanOpenHandle(WLAN_API_VERSION, None, ctypes.byref(negotiated), ctypes.byref(handle))
        != ERROR_SUCCESS
    ):
        yield None
        return
    try:
        yield api, handle
    finally:
        api.WlanCloseHandle(handle, None)


def _interfaces(api: ctypes.WinDLL, handle: wintypes.HANDLE) -> list[WlanInterface]:
    plist = ctypes.c_void_p()
    if api.WlanEnumInterfaces(handle, None, ctypes.byref(plist)) != ERROR_SUCCESS:
        return []
    address = plist.value
    if address is None:
        return []
    try:
        count = ctypes.cast(plist, ctypes.POINTER(wintypes.DWORD))[0]
        base = address + 8  # dwNumberOfItems, dwIndex
        size = ctypes.sizeof(WLAN_INTERFACE_INFO)
        result = []
        for index in range(count):
            info = WLAN_INTERFACE_INFO.from_address(base + index * size)
            result.append(
                WlanInterface(
                    _guid_str(info.InterfaceGuid), info.strInterfaceDescription, int(info.isState)
                )
            )
        return result
    finally:
        api.WlanFreeMemory(plist)


def interfaces() -> list[WlanInterface]:
    """Every WLAN interface the service knows, connected or not."""
    with _handle() as opened:
        if opened is None:
            return []
        api, handle = opened
        return _interfaces(api, handle)


def _query(
    api: ctypes.WinDLL, handle: wintypes.HANDLE, guid: str, opcode: int
) -> ctypes.c_void_p | None:
    size = wintypes.DWORD(0)
    data = ctypes.c_void_p()
    status = api.WlanQueryInterface(
        handle, _guid_bytes(guid), opcode, None, ctypes.byref(size), ctypes.byref(data), None
    )
    if status != ERROR_SUCCESS or not data:
        return None
    return data


def _center_khz(api: ctypes.WinDLL, handle: wintypes.HANDLE, guid: str, bssid: bytes) -> int:
    """The connected BSS entry's own centre frequency; 0 when it is not listed."""
    plist = ctypes.c_void_p()
    status = api.WlanGetNetworkBssList(
        handle,
        _guid_bytes(guid),
        None,
        DOT11_BSS_TYPE_INFRASTRUCTURE,
        False,
        None,
        ctypes.byref(plist),
    )
    address = plist.value
    if status != ERROR_SUCCESS or address is None:
        return 0
    try:
        count = ctypes.cast(address + 4, ctypes.POINTER(wintypes.DWORD))[0]
        base = address + 8  # dwTotalSize, dwNumberOfItems
        size = ctypes.sizeof(WLAN_BSS_ENTRY)
        for index in range(count):
            entry = WLAN_BSS_ENTRY.from_address(base + index * size)
            if bytes(entry.dot11Bssid[:6]) == bssid:
                return int(entry.ulChCenterFrequency)
        return 0
    finally:
        api.WlanFreeMemory(plist)


def query_connected() -> list[WlanRecord]:
    """One record per connected radio; nothing for disconnected or absent ones."""
    with _handle() as opened:
        if opened is None:
            return []
        api, handle = opened
        records: list[WlanRecord] = []
        for iface in _interfaces(api, handle):
            if not iface.connected:
                continue
            data = _query(api, handle, iface.guid, WLAN_INTF_OPCODE_CURRENT_CONNECTION)
            if data is None or data.value is None:
                continue
            try:
                conn = WLAN_CONNECTION_ATTRIBUTES.from_address(data.value)
                assoc = conn.wlanAssociationAttributes
                ssid = _ssid_text(assoc.dot11Ssid)
                bssid_raw = bytes(assoc.dot11Bssid[:6])
                phy = int(assoc.dot11PhyType)
                signal = int(assoc.wlanSignalQuality)
                auth = int(conn.wlanSecurityAttributes.dot11AuthAlgorithm)
                profile = conn.strProfileName
            finally:
                api.WlanFreeMemory(data)

            channel = 0
            data = _query(api, handle, iface.guid, WLAN_INTF_OPCODE_CHANNEL_NUMBER)
            if data is not None:
                try:
                    channel = ctypes.cast(data, ctypes.POINTER(wintypes.ULONG))[0]
                finally:
                    api.WlanFreeMemory(data)

            records.append(
                WlanRecord(
                    interface_guid=iface.guid,
                    channel=int(channel),
                    center_khz=_center_khz(api, handle, iface.guid, bssid_raw),
                    phy_type=phy,
                    signal_percent=signal,
                    auth_algorithm=auth,
                    ssid=ssid,
                    profile_name=profile,
                    bssid=_mac(assoc.dot11Bssid),
                )
            )
        return records


def profile_names(interface_guid: str) -> list[str]:
    """Saved profiles for one interface, in the service's preference order.

    This is what ``netsh wlan show profiles`` prints under a localized heading;
    the API hands back the names themselves, so nothing is parsed.
    """
    with _handle() as opened:
        if opened is None:
            return []
        api, handle = opened
        plist = ctypes.c_void_p()
        if (
            api.WlanGetProfileList(handle, _guid_bytes(interface_guid), None, ctypes.byref(plist))
            != ERROR_SUCCESS
        ):
            return []
        address = plist.value
        if address is None:
            return []
        try:
            count = ctypes.cast(plist, ctypes.POINTER(wintypes.DWORD))[0]
            base = address + 8  # dwNumberOfItems, dwIndex
            size = ctypes.sizeof(WLAN_PROFILE_INFO)
            return [
                WLAN_PROFILE_INFO.from_address(base + index * size).strProfileName
                for index in range(count)
            ]
        finally:
            api.WlanFreeMemory(plist)


def connect(interface_guid: str, profile_name: str) -> int:
    """Ask the service to connect an interface to a saved profile; Win32 error code."""
    with _handle() as opened:
        if opened is None:
            return -1
        api, handle = opened
        params = WLAN_CONNECTION_PARAMETERS()
        params.wlanConnectionMode = WLAN_CONNECTION_MODE_PROFILE
        params.strProfile = profile_name
        params.pDot11Ssid = None
        params.pDesiredBssidList = None
        params.dot11BssType = DOT11_BSS_TYPE_INFRASTRUCTURE
        params.dwFlags = 0
        return int(api.WlanConnect(handle, _guid_bytes(interface_guid), ctypes.byref(params), None))


def disconnect(interface_guid: str) -> int:
    """Disconnect an interface without touching the adapter; Win32 error code."""
    with _handle() as opened:
        if opened is None:
            return -1
        api, handle = opened
        return int(api.WlanDisconnect(handle, _guid_bytes(interface_guid), None))
