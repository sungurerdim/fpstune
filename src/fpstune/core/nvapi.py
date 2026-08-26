"""Read NVIDIA driver settings directly through NVAPI.

Why this exists: fpstune applies GPU settings by importing a .nip file with
nvidiaProfileInspector, but NPI offers no way to read the result back — its
export path requires GUI interaction. Detection therefore fell back to
fpstune's own JSON cache, which apply had just written, so verifying a GPU
setting compared a value against itself and could never fail.

NVAPI's DRS (DRiver Settings) API is what NPI itself is built on, so reading
through it observes exactly what NPI wrote.

Everything here is read-only and best-effort: any failure returns None so the
caller falls back to the cache rather than reporting a wrong value.

Reference: NVIDIA "Driver Settings Programming Guide" (PG-12072-001).
"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import POINTER, Structure, byref, c_uint8, c_uint16, c_uint32, c_void_p
from typing import Any

from fpstune.utils.logger import get_logger

logger = get_logger()

# NVAPI status codes we care about; everything else is just "failed".
# Verified against the driver on this codebase: an oversized/undersized struct
# returns -9, while a setting absent from the profile returns -160 (confirmed by
# NvAPI_DRS_GetNumSettings reporting 0 settings on an untouched base profile).
NVAPI_OK = 0
NVAPI_INCOMPATIBLE_STRUCT_VERSION = -9
NVAPI_SETTING_NOT_FOUND = -160

# nvapi64.dll exposes a single exported symbol, nvapi_QueryInterface, which maps
# these well-known function IDs to real entry points.
_FN_INITIALIZE = 0x0150E828
_FN_UNLOAD = 0xD22BDD7E
_FN_DRS_CREATE_SESSION = 0x0694D52E
_FN_DRS_DESTROY_SESSION = 0xDAD9CFF8
_FN_DRS_LOAD_SETTINGS = 0x375DBD6B
_FN_DRS_GET_BASE_PROFILE = 0xDA8466A0
_FN_DRS_GET_SETTING = 0x73BF8338

# From nvapi.h.
_NVAPI_UNICODE_STRING_MAX = 2048
_NVAPI_BINARY_DATA_MAX = 4096


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


# NVDRS_SETTING_VER is version 1 of the struct.
NVDRS_SETTING_VER = _make_version(NvdrsSetting, 1)

# DRS setting types (NVDRS_SETTING_TYPE).
_NVDRS_DWORD_TYPE = 0
_NVDRS_BINARY_TYPE = 1
_NVDRS_STRING_TYPE = 2
_NVDRS_WSTRING_TYPE = 3


class NvapiUnavailable(Exception):
    """NVAPI could not be loaded or initialised on this system."""


class _Nvapi:
    """Lazily-loaded NVAPI entry points.

    Loading is attempted once; a failure is remembered so a machine without an
    NVIDIA driver does not pay for a retry on every detection.
    """

    _lock = threading.Lock()
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

        def resolve(fn_id: int, *argtypes: Any) -> Any:
            address = query(fn_id)
            if not address:
                raise NvapiUnavailable(f"NVAPI function {fn_id:#010x} not exported")
            proto = ctypes.CFUNCTYPE(ctypes.c_int, *argtypes)
            return proto(address)

        self._initialize = resolve(_FN_INITIALIZE)
        self._unload = resolve(_FN_UNLOAD)
        self._create_session = resolve(_FN_DRS_CREATE_SESSION, POINTER(c_void_p))
        self._destroy_session = resolve(_FN_DRS_DESTROY_SESSION, c_void_p)
        self._load_settings = resolve(_FN_DRS_LOAD_SETTINGS, c_void_p)
        self._get_base_profile = resolve(_FN_DRS_GET_BASE_PROFILE, c_void_p, POINTER(c_void_p))
        self._get_setting = resolve(
            _FN_DRS_GET_SETTING, c_void_p, c_void_p, c_uint32, POINTER(NvdrsSetting)
        )

        status = self._initialize()
        if status != NVAPI_OK:
            raise NvapiUnavailable(f"NvAPI_Initialize failed: {status}")

    @classmethod
    def get(cls) -> _Nvapi:
        """Return the shared instance, raising NvapiUnavailable if unusable."""
        with cls._lock:
            if cls._load_failed:
                raise NvapiUnavailable("NVAPI previously failed to load")
            if cls._instance is None:
                try:
                    cls._instance = cls()
                except NvapiUnavailable:
                    cls._load_failed = True
                    raise
            return cls._instance

    def read_settings(self, setting_ids: list[int]) -> dict[int, int]:
        """Read DWORD settings from the base profile in one session.

        The base profile is what fpstune writes, and it applies system-wide.
        NVIDIA's guide is explicit that DRS sessions do not merge, so the
        session is opened and destroyed around this single read.
        """
        session = c_void_p()
        status = self._create_session(byref(session))
        if status != NVAPI_OK:
            raise NvapiUnavailable(f"NvAPI_DRS_CreateSession failed: {status}")

        try:
            status = self._load_settings(session)
            if status != NVAPI_OK:
                raise NvapiUnavailable(f"NvAPI_DRS_LoadSettings failed: {status}")

            profile = c_void_p()
            status = self._get_base_profile(session, byref(profile))
            if status != NVAPI_OK:
                raise NvapiUnavailable(f"NvAPI_DRS_GetBaseProfile failed: {status}")

            values: dict[int, int] = {}
            for setting_id in setting_ids:
                setting = NvdrsSetting()
                setting.version = NVDRS_SETTING_VER
                status = self._get_setting(session, profile, c_uint32(setting_id), byref(setting))

                if status == NVAPI_SETTING_NOT_FOUND:
                    # Never written to this profile — the driver default applies.
                    continue
                if status == NVAPI_INCOMPATIBLE_STRUCT_VERSION:
                    # The struct layout no longer matches this driver; reading
                    # on would risk misinterpreting the union.
                    raise NvapiUnavailable(
                        f"NVDRS_SETTING layout rejected by driver (version {NVDRS_SETTING_VER})"
                    )
                if status != NVAPI_OK:
                    logger.debug("DRS_GetSetting(%#010x) failed: %s", setting_id, status)
                    continue
                if setting.settingType != _NVDRS_DWORD_TYPE:
                    # Every setting fpstune manages is a DWORD; anything else
                    # would need a different accessor, so skip rather than
                    # reinterpret the union.
                    logger.debug(
                        "DRS setting %#010x is type %s, not DWORD",
                        setting_id,
                        setting.settingType,
                    )
                    continue

                values[setting_id] = int(setting.currentValue.u32Value)

            return values
        finally:
            self._destroy_session(session)


def nvapi_available() -> bool:
    """Whether NVAPI can be used for a real read-back on this system.

    Cheap after the first call: the loader caches both success and failure.
    """
    try:
        _Nvapi.get()
    except NvapiUnavailable:
        return False
    except OSError:
        return False
    return True


def read_driver_settings(setting_ids: list[int]) -> dict[int, int] | None:
    """Read the given DRS setting IDs, or None if NVAPI is unusable.

    Returns only the IDs present in the base profile; a missing ID means the
    driver default is in effect. None (rather than an empty dict) signals that
    nothing could be read at all, so callers can fall back instead of treating
    the absence as "everything is at default".
    """
    if not setting_ids:
        return {}

    try:
        return _Nvapi.get().read_settings(setting_ids)
    except NvapiUnavailable as exc:
        logger.debug("NVAPI read unavailable: %s", exc)
        return None
    except OSError as exc:
        # A driver-level fault must degrade to the cache, not crash detection.
        logger.warning("NVAPI read failed: %s", exc)
        return None
