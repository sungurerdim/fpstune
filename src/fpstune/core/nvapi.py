"""NVIDIA driver settings (DRS) through NVAPI: read, write, restore stock.

NVIDIA Control Panel's "Global Settings" live in the driver's settings database
(DRS), not in the registry. NVAPI's DRS functions are the one supported way to
read and change them, and they are what NVIDIA Control Panel and every profile
tool are built on. Reaching them through ``nvapi64.dll`` — which ships with
every NVIDIA driver — means no helper program is downloaded, unpacked or run.

Three rules shape this module:

* **Global profile.** Writes and reads target the profile NVIDIA Control Panel
  edits as Global Settings: ``NvAPI_DRS_GetCurrentGlobalProfile``. Reads return
  the effective value even when it is inherited from the base profile or the
  driver's predefined default, so what is read is what a game gets unless its
  own application profile overrides it.
* **Stock means absent.** Restoring a setting deletes it from the global
  profile, so the driver's own default applies — whatever this driver version
  ships, with nothing hardcoded here to drift from it.
* **One session per operation, under one lock.** NVIDIA's guide is explicit
  that sessions do not merge: two sessions loaded, changed and saved in
  parallel would each save the database as it looked when they loaded it, and
  the later save would silently drop the earlier one's change.

Reference: NVIDIA ``nvapi.h``, ``nvapi_interface.h`` and ``nvapi_lite_common.h``
(github.com/NVIDIA/nvapi); every ID and status code below is copied from them.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from ctypes import POINTER, Structure, byref, c_uint8, c_uint16, c_uint32, c_void_p
from dataclasses import dataclass
from typing import Any

from fpstune.utils.logger import get_logger

logger = get_logger()

# Status codes (nvapi_lite_common.h, NvAPI_Status). Every non-OK constant here
# has its words in _STATUS_MESSAGES; tests/test_core/test_nvapi.py fails when a
# constant is added without them, so a status can never again surface as a
# generic "refused" (NVAPI_SETTING_NOT_FOUND did, on a driver that lacked a key).
NVAPI_OK = 0
NVAPI_ERROR = -1
NVAPI_LIBRARY_NOT_FOUND = -2
NVAPI_NO_IMPLEMENTATION = -3
NVAPI_API_NOT_INITIALIZED = -4
NVAPI_INVALID_ARGUMENT = -5
NVAPI_NVIDIA_DEVICE_NOT_FOUND = -6
NVAPI_END_ENUMERATION = -7
NVAPI_INVALID_HANDLE = -8
NVAPI_INCOMPATIBLE_STRUCT_VERSION = -9
NVAPI_INVALID_USER_PRIVILEGE = -137
NVAPI_SETTING_NOT_FOUND = -160
NVAPI_PROFILE_NOT_FOUND = -163
NVAPI_ACCESS_DENIED = -175

# nvapi64.dll exports one symbol, nvapi_QueryInterface, which maps these IDs
# (nvapi_interface.h) to the real entry points.
_FN_INITIALIZE = 0x0150E828
_FN_DRS_CREATE_SESSION = 0x0694D52E
_FN_DRS_DESTROY_SESSION = 0xDAD9CFF8
_FN_DRS_LOAD_SETTINGS = 0x375DBD6B
_FN_DRS_SAVE_SETTINGS = 0xFCBC7E14
_FN_DRS_GET_CURRENT_GLOBAL_PROFILE = 0x617BFF9F
_FN_DRS_GET_SETTING = 0x73BF8338
_FN_DRS_SET_SETTING = 0x577DD202
_FN_DRS_DELETE_PROFILE_SETTING = 0xE4A26362
_FN_DRS_ENUM_SETTINGS = 0xAE3039DA
_FN_DRS_FIND_PROFILE_BY_NAME = 0x7E4A9A0B
_FN_DRS_DELETE_PROFILE = 0x17093206
_FN_DRS_GET_SETTING_NAME_FROM_ID = 0xD61CBE6E

# From nvapi.h.
_NVAPI_UNICODE_STRING_MAX = 2048
_NVAPI_BINARY_DATA_MAX = 4096

# fpstune 0.1.0 imported its settings into a custom profile of this name, with
# no executables attached — a profile that applied to nothing. It is deleted the
# first time this release writes, so it cannot shadow or confuse anything.
# Remove this once 0.1.0 is no longer in the field.
_ORPHAN_PROFILE_NAME = "fpstune_gaming"


class _NvdrsBinarySetting(Structure):
    _fields_ = [
        ("valueLength", c_uint32),
        ("valueData", c_uint8 * _NVAPI_BINARY_DATA_MAX),
    ]


class _NvdrsSettingValue(ctypes.Union):
    _fields_ = [
        ("u32Value", c_uint32),
        ("wszValue", c_uint16 * _NVAPI_UNICODE_STRING_MAX),
        ("binaryValue", _NvdrsBinarySetting),
    ]


class NvdrsSetting(Structure):
    """NVDRS_SETTING. Field order and sizes must match nvapi.h exactly."""

    _fields_ = [
        ("version", c_uint32),
        ("settingName", c_uint16 * _NVAPI_UNICODE_STRING_MAX),
        ("settingId", c_uint32),
        ("settingType", c_uint32),
        ("settingLocation", c_uint32),
        ("isCurrentPredefined", c_uint32),
        ("isPredefinedValid", c_uint32),
        ("predefinedValue", _NvdrsSettingValue),
        ("currentValue", _NvdrsSettingValue),
    ]


def _make_version(struct_type: type[Structure], version: int) -> int:
    """MAKE_NVAPI_VERSION: struct size in the low bits, version in the high."""
    return ctypes.sizeof(struct_type) | (version << 16)


NVDRS_SETTING_VER = _make_version(NvdrsSetting, 1)

# NVDRS_SETTING_TYPE.
_NVDRS_DWORD_TYPE = 0

# NVDRS_SETTING_LOCATION, in nvapi.h order.
LOCATIONS = ("current", "global", "base", "default")


class NvapiUnavailable(Exception):
    """NVAPI could not be loaded or initialised on this system."""


class NvapiError(Exception):
    """A DRS call failed; the message says which one and why, in words."""

    def __init__(self, call: str, status: int) -> None:
        self.call = call
        self.status = status
        super().__init__(f"{call} failed: {_describe(status)} (NVAPI status {status})")


_STATUS_MESSAGES: dict[int, str] = {
    NVAPI_ERROR: "the NVIDIA driver reported an unspecified error",
    NVAPI_LIBRARY_NOT_FOUND: "the NVIDIA settings library could not be loaded",
    NVAPI_NO_IMPLEMENTATION: "this driver does not implement that call",
    NVAPI_API_NOT_INITIALIZED: "the NVIDIA settings interface is not initialised",
    NVAPI_INVALID_ARGUMENT: "the NVIDIA driver rejected an argument as invalid",
    NVAPI_NVIDIA_DEVICE_NOT_FOUND: "no NVIDIA display driver is active",
    NVAPI_END_ENUMERATION: "there are no more entries to list",
    NVAPI_INVALID_HANDLE: "the NVIDIA driver no longer recognises this session handle",
    NVAPI_INCOMPATIBLE_STRUCT_VERSION: "this driver rejected the settings structure layout",
    NVAPI_INVALID_USER_PRIVILEGE: (
        "administrator rights are required to change NVIDIA driver settings"
    ),
    NVAPI_SETTING_NOT_FOUND: "this driver does not have this setting",
    NVAPI_PROFILE_NOT_FOUND: "this driver has no such profile",
    NVAPI_ACCESS_DENIED: "the NVIDIA driver denied access to this caller",
}


def _describe(status: int) -> str:
    return _STATUS_MESSAGES.get(
        status, "the NVIDIA driver returned a status this version of fpstune does not name"
    )


@dataclass(frozen=True)
class DriverSetting:
    """One DWORD setting as the driver reports it, for diagnostics."""

    setting_id: int
    value: int
    location: str
    predefined: bool


class _Nvapi:
    """Lazily-loaded NVAPI entry points, loaded once per process.

    A failed load is remembered so a machine without an NVIDIA driver does not
    pay for a retry on every detection.
    """

    _load_lock = threading.Lock()
    _instance: _Nvapi | None = None
    _load_failed = False

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise NvapiUnavailable("NVAPI is Windows-only")

        try:
            dll = ctypes.WinDLL("nvapi64.dll")
        except OSError as exc:
            raise NvapiUnavailable(f"nvapi64.dll not loadable: {exc}") from exc

        query = dll.nvapi_QueryInterface
        query.restype = c_void_p
        query.argtypes = [c_uint32]

        def resolve(fn_id: int, *argtypes: Any) -> Callable[..., int]:
            address = query(fn_id)
            if not address:
                raise NvapiUnavailable(f"NVAPI function {fn_id:#010x} not exported")
            proto = ctypes.CFUNCTYPE(ctypes.c_int, *argtypes)
            return proto(address)

        self.initialize = resolve(_FN_INITIALIZE)
        self.create_session = resolve(_FN_DRS_CREATE_SESSION, POINTER(c_void_p))
        self.destroy_session = resolve(_FN_DRS_DESTROY_SESSION, c_void_p)
        self.load_settings = resolve(_FN_DRS_LOAD_SETTINGS, c_void_p)
        self.save_settings = resolve(_FN_DRS_SAVE_SETTINGS, c_void_p)
        self.get_current_global_profile = resolve(
            _FN_DRS_GET_CURRENT_GLOBAL_PROFILE, c_void_p, POINTER(c_void_p)
        )
        self.get_setting = resolve(
            _FN_DRS_GET_SETTING, c_void_p, c_void_p, c_uint32, POINTER(NvdrsSetting)
        )
        self.set_setting = resolve(_FN_DRS_SET_SETTING, c_void_p, c_void_p, POINTER(NvdrsSetting))
        self.delete_profile_setting = resolve(
            _FN_DRS_DELETE_PROFILE_SETTING, c_void_p, c_void_p, c_uint32
        )
        self.enum_settings = resolve(
            _FN_DRS_ENUM_SETTINGS,
            c_void_p,
            c_void_p,
            c_uint32,
            POINTER(c_uint32),
            POINTER(NvdrsSetting),
        )
        self.find_profile_by_name = resolve(
            _FN_DRS_FIND_PROFILE_BY_NAME,
            c_void_p,
            POINTER(c_uint16 * _NVAPI_UNICODE_STRING_MAX),
            POINTER(c_void_p),
        )
        self.delete_profile = resolve(_FN_DRS_DELETE_PROFILE, c_void_p, c_void_p)

        # The capability probe is optional: a driver that does not export it
        # leaves every key's presence unknown, never absent.
        probe_address = query(_FN_DRS_GET_SETTING_NAME_FROM_ID)
        self.get_setting_name_from_id: Callable[..., int] | None = (
            ctypes.CFUNCTYPE(ctypes.c_int, c_uint32, POINTER(c_uint16 * _NVAPI_UNICODE_STRING_MAX))(
                probe_address
            )
            if probe_address
            else None
        )

        status = self.initialize()
        if status != NVAPI_OK:
            raise NvapiUnavailable(f"NvAPI_Initialize failed: {_describe(status)} ({status})")

    @classmethod
    def get(cls) -> _Nvapi:
        """Return the shared instance, raising NvapiUnavailable if unusable."""
        with cls._load_lock:
            if cls._load_failed:
                raise NvapiUnavailable("NVAPI previously failed to load")
            if cls._instance is None:
                try:
                    cls._instance = cls()
                except NvapiUnavailable:
                    cls._load_failed = True
                    raise
            return cls._instance


# Every session — read or write — runs under this lock; see the module docstring.
_session_lock = threading.Lock()


class _Session:
    """One loaded DRS session bound to the current global profile."""

    def __init__(self, api: _Nvapi, handle: c_void_p, profile: c_void_p) -> None:
        self._api = api
        self._handle = handle
        self._profile = profile

    def _check(self, call: str, status: int) -> None:
        if status != NVAPI_OK:
            raise NvapiError(call, status)

    def read(self, setting_id: int) -> NvdrsSetting | None:
        setting = NvdrsSetting()
        setting.version = NVDRS_SETTING_VER
        status = self._api.get_setting(
            self._handle, self._profile, c_uint32(setting_id), byref(setting)
        )
        if status == NVAPI_SETTING_NOT_FOUND:
            return None
        self._check(f"NvAPI_DRS_GetSetting({setting_id:#010x})", status)
        return setting

    def write(self, setting_id: int, value: int) -> None:
        setting = NvdrsSetting()
        setting.version = NVDRS_SETTING_VER
        setting.settingId = setting_id
        setting.settingType = _NVDRS_DWORD_TYPE
        setting.currentValue.u32Value = value & 0xFFFFFFFF
        status = self._api.set_setting(self._handle, self._profile, byref(setting))
        self._check(f"NvAPI_DRS_SetSetting({setting_id:#010x})", status)

    def delete(self, setting_id: int) -> None:
        status = self._api.delete_profile_setting(self._handle, self._profile, c_uint32(setting_id))
        # Deleting what is not there already leaves the driver default in force.
        if status == NVAPI_SETTING_NOT_FOUND:
            return
        self._check(f"NvAPI_DRS_DeleteProfileSetting({setting_id:#010x})", status)

    def enumerate(self) -> list[NvdrsSetting]:
        found: list[NvdrsSetting] = []
        batch = 64
        start = 0
        while True:
            buffer = (NvdrsSetting * batch)()
            for item in buffer:
                item.version = NVDRS_SETTING_VER
            count = c_uint32(batch)
            status = self._api.enum_settings(
                self._handle, self._profile, c_uint32(start), byref(count), buffer
            )
            if status == NVAPI_END_ENUMERATION:
                return found
            self._check("NvAPI_DRS_EnumSettings", status)
            found.extend(buffer[: count.value])
            if count.value < batch:
                return found
            start += count.value

    def drop_orphan_profile(self) -> bool:
        name = (c_uint16 * _NVAPI_UNICODE_STRING_MAX)()
        for index, char in enumerate(_ORPHAN_PROFILE_NAME):
            name[index] = ord(char)
        profile = c_void_p()
        status = self._api.find_profile_by_name(self._handle, byref(name), byref(profile))
        if status == NVAPI_PROFILE_NOT_FOUND:
            return False
        self._check("NvAPI_DRS_FindProfileByName", status)
        self._check("NvAPI_DRS_DeleteProfile", self._api.delete_profile(self._handle, profile))
        return True

    def save(self) -> None:
        self._check("NvAPI_DRS_SaveSettings", self._api.save_settings(self._handle))


@contextmanager
def _session() -> Iterator[_Session]:
    api = _Nvapi.get()
    with _session_lock:
        handle = c_void_p()
        status = api.create_session(byref(handle))
        if status != NVAPI_OK:
            raise NvapiError("NvAPI_DRS_CreateSession", status)
        try:
            status = api.load_settings(handle)
            if status != NVAPI_OK:
                raise NvapiError("NvAPI_DRS_LoadSettings", status)
            profile = c_void_p()
            status = api.get_current_global_profile(handle, byref(profile))
            if status != NVAPI_OK:
                raise NvapiError("NvAPI_DRS_GetCurrentGlobalProfile", status)
            yield _Session(api, handle, profile)
        finally:
            api.destroy_session(handle)


def read_driver_settings(setting_ids: list[int]) -> dict[int, int] | None:
    """Effective DWORD values of the given settings on the global profile.

    An ID missing from the result is one the driver holds no value for at any
    level, so its built-in default applies. None means nothing could be read at
    all — NVAPI is missing or refused — which callers must not mistake for
    "everything is at default".
    """
    if not setting_ids:
        return {}
    try:
        with _session() as session:
            values: dict[int, int] = {}
            for setting_id in setting_ids:
                setting = session.read(setting_id)
                if setting is None:
                    continue
                if setting.settingType != _NVDRS_DWORD_TYPE:
                    logger.debug("DRS setting %#010x is not a DWORD; skipped", setting_id)
                    continue
                values[setting_id] = int(setting.currentValue.u32Value)
            return values
    except NvapiUnavailable as exc:
        logger.debug("NVAPI read unavailable: %s", exc)
        return None
    except (NvapiError, OSError) as exc:
        logger.warning("NVAPI read failed: %s", exc)
        return None


def known_setting_ids(setting_ids: Iterable[int]) -> frozenset[int] | None:
    """The given IDs this driver has a definition for.

    A key an older or newer driver does not define (nvidiaProfileInspector's
    "Ultra Low Latency - Enabled" on driver 617.14) is a fact about this machine,
    not a failure. Absence needs the driver's word twice: naming the ID
    (NvAPI_DRS_GetSettingNameFromId) answers NVAPI_SETTING_NOT_FOUND, *and* a
    write of it, in a session that is never saved, does too. The second check
    exists because the naming table is not the whole story — measured on 617.14,
    CUDA "Force P2 State" is unnamed yet the driver answers its write with
    NVAPI_INVALID_USER_PRIVILEGE, so it knows the key — and a key wrongly called
    absent would hide a setting that works.

    None means the driver could not be asked — NVAPI is missing, refused, or does
    not export the probe — which callers must not read as "all absent".
    """
    try:
        probe = _Nvapi.get().get_setting_name_from_id
        if probe is None:
            return None
        known: set[int] = set()
        unnamed: list[int] = []
        for setting_id in setting_ids:
            name = (c_uint16 * _NVAPI_UNICODE_STRING_MAX)()
            status = probe(c_uint32(setting_id), byref(name))
            if status == NVAPI_OK:
                known.add(setting_id)
            elif status == NVAPI_SETTING_NOT_FOUND:
                unnamed.append(setting_id)
            else:
                raise NvapiError(f"NvAPI_DRS_GetSettingNameFromId({setting_id:#010x})", status)
        if unnamed:
            with _session() as session:  # destroyed without a save: nothing persists
                for setting_id in unnamed:
                    try:
                        session.write(setting_id, 0)
                    except NvapiError as exc:
                        if exc.status != NVAPI_SETTING_NOT_FOUND:
                            known.add(setting_id)
        return frozenset(known)
    except NvapiUnavailable as exc:
        logger.debug("NVAPI capability probe unavailable: %s", exc)
        return None
    except (NvapiError, OSError) as exc:
        logger.warning("NVAPI capability probe failed: %s", exc)
        return None


def write_driver_settings(changes: Mapping[int, int | None]) -> None:
    """Write DWORD values to the global profile; None restores driver stock.

    All changes land in one session and one save, so a multi-key setting is
    never left half-written. Raises NvapiUnavailable or NvapiError with a
    readable reason; nothing is saved when any write fails.
    """
    if not changes:
        return
    with _session() as session:
        for setting_id, value in changes.items():
            if value is None:
                session.delete(setting_id)
            else:
                session.write(setting_id, value)
        try:
            if session.drop_orphan_profile():
                logger.info("Removed the unused '%s' NVIDIA profile", _ORPHAN_PROFILE_NAME)
        except NvapiError as exc:
            # Housekeeping only; the user's change must not fail because of it.
            logger.warning("Could not remove the unused NVIDIA profile: %s", exc)
        session.save()


def dump_driver_settings() -> list[DriverSetting]:
    """Every DWORD setting present on the global profile, for diagnostics."""
    with _session() as session:
        return [
            DriverSetting(
                setting_id=int(item.settingId),
                value=int(item.currentValue.u32Value),
                location=(
                    LOCATIONS[item.settingLocation]
                    if item.settingLocation < len(LOCATIONS)
                    else str(item.settingLocation)
                ),
                predefined=bool(item.isCurrentPredefined),
            )
            for item in session.enumerate()
            if item.settingType == _NVDRS_DWORD_TYPE
        ]
