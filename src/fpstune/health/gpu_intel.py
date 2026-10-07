"""Intel: the graphics control library's own temperature sensors, through ctypes.

`ControlLib.dll` ships with Intel's graphics driver (`C:\\Windows\\System32` here) and
is the user-mode half of IGCL, Intel's public control API. Reading it needs no kernel
driver of ours: the call goes through the vendor's user-mode driver, the same path the
vendor's own control panel uses. Every structure and prototype below was read from
`igcl_api.h` in `intel/drivers.gpu.control-library` (`ctl_init_args_t`,
`ctl_device_adapter_properties_t`, `ctl_temp_properties_t`, `ctlInit`,
`ctlEnumerateDevices`, `ctlGetDeviceProperties`, `ctlEnumTemperatureSensors`,
`ctlTemperatureGetProperties`, `ctlTemperatureGetState`, `ctlClose`), and the struct
sizes are pinned by a test against what the header's layout works out to.

**The limit is the sensor's own maximum.** `ctl_temp_properties_t.maxTemperature` is
documented as the maximum temperature of the device in degrees Celsius; it is the
only limit IGCL publishes, and it is the one used. A sensor that reports none (zero)
is not judged.

**Not every Intel graphics part is supported, and that is an answer.** Measured on
the machine this was written on: `ctlInit` returns `CTL_RESULT_ERROR_PLATFORM_NOT_SUPPORTED`
(`0x40000020`) for an 11th-generation integrated GPU, so the reader names that and
reads nothing. It is not retried with other flags and it is not papered over with a
guess (C11 rule 3).

**A wrong call here must not take the server down.** Every prototype is typed, the
library is loaded by absolute System32 path (no DLL search), `ctlClose` always runs,
and an access violation from the driver surfaces as `OSError`, which ctypes raises on
Windows instead of crashing, and the reader turns into a gap.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from typing import Protocol

from fpstune.health.model import Gap
from fpstune.health.thermal import ThermalReading, ThermalSnapshot
from fpstune.utils.logger import get_logger

logger = get_logger()

SOURCE = "intel_igcl"
LIBRARY = "ControlLib.dll"

SUCCESS = 0x00000000
UNSUPPORTED_VERSION = 0x40000009
PLATFORM_NOT_SUPPORTED = 0x40000020

SENSOR_GLOBAL = 0
SENSOR_GPU = 1
"""`ctl_temp_sensors_t`: the maximum across all device sensors, and across the GPU's."""

# CTL_MAKE_VERSION(1, 0): the oldest interface that has the temperature calls. The
# driver answers with the version it implements; asking for less than it has works.
_APP_VERSION = (1 << 16) | 0

RESULT_REASONS = {
    PLATFORM_NOT_SUPPORTED: (
        "Intel's graphics control library reports this graphics part as not supported, "
        "so its temperature cannot be read"
    ),
    UNSUPPORTED_VERSION: (
        "Intel's graphics control library does not support the interface version fpstune asks for"
    ),
}
NO_LIBRARY = (
    "Intel's graphics control library (ControlLib.dll) is not installed, so the Intel "
    "adapter's temperature cannot be read"
)


class IgclError(Exception):
    """An IGCL call returned something other than success."""

    def __init__(self, code: int) -> None:
        super().__init__(f"IGCL result {code:#x}")
        self.code = code


@dataclass(frozen=True)
class IgclSensor:
    kind: int
    temperature_c: float
    maximum_c: float


@dataclass(frozen=True)
class IgclDevice:
    name: str
    vendor_id: int
    device_id: int
    sensors: tuple[IgclSensor, ...]
    sensor_error: int | None = None
    """The result code that stopped sensors being read for this device, if one did."""


class Igcl(Protocol):
    def devices(self) -> list[IgclDevice]: ...


class _AppId(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]


class _InitArgs(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_uint32),
        ("Version", ctypes.c_uint8),
        ("AppVersion", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("SupportedVersion", ctypes.c_uint32),
        ("ApplicationUID", _AppId),
    ]


class _Bdf(ctypes.Structure):
    _fields_ = [
        ("bus", ctypes.c_uint8),
        ("device", ctypes.c_uint8),
        ("function", ctypes.c_uint8),
    ]


class _FirmwareVersion(ctypes.Structure):
    _fields_ = [
        ("major_version", ctypes.c_uint64),
        ("minor_version", ctypes.c_uint64),
        ("build_number", ctypes.c_uint64),
    ]


class _AdapterProperties(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_uint32),
        ("Version", ctypes.c_uint8),
        ("pDeviceID", ctypes.c_void_p),
        ("device_id_size", ctypes.c_uint32),
        ("device_type", ctypes.c_int32),
        ("supported_subfunction_flags", ctypes.c_uint32),
        ("driver_version", ctypes.c_uint64),
        ("firmware_version", _FirmwareVersion),
        ("pci_vendor_id", ctypes.c_uint32),
        ("pci_device_id", ctypes.c_uint32),
        ("rev_id", ctypes.c_uint32),
        ("num_eus_per_sub_slice", ctypes.c_uint32),
        ("num_sub_slices_per_slice", ctypes.c_uint32),
        ("num_slices", ctypes.c_uint32),
        ("name", ctypes.c_char * 100),
        ("graphics_adapter_properties", ctypes.c_uint32),
        ("Frequency", ctypes.c_uint32),
        ("pci_subsys_id", ctypes.c_uint16),
        ("pci_subsys_vendor_id", ctypes.c_uint16),
        ("adapter_bdf", _Bdf),
        ("num_xe_cores", ctypes.c_uint32),
        ("reserved", ctypes.c_char * 108),
    ]


class _TempProperties(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_uint32),
        ("Version", ctypes.c_uint8),
        ("type", ctypes.c_int32),
        ("maxTemperature", ctypes.c_double),
    ]


_LUID_BYTES = 8
"""`pDeviceID` is the adapter's LUID on Windows: the caller supplies the buffer."""


def _check(code: int) -> None:
    if code != SUCCESS:
        raise IgclError(code)


class ControlLib:
    """The real library, bound the way `igcl_api.h` declares it."""

    def __init__(self, path: str) -> None:
        dll = ctypes.WinDLL(path)
        void_p, u32_p = ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
        self._init = dll.ctlInit
        self._init.argtypes = [ctypes.POINTER(_InitArgs), ctypes.POINTER(void_p)]
        self._close = dll.ctlClose
        self._close.argtypes = [void_p]
        self._enumerate = dll.ctlEnumerateDevices
        self._enumerate.argtypes = [void_p, u32_p, ctypes.POINTER(void_p)]
        self._properties = dll.ctlGetDeviceProperties
        self._properties.argtypes = [void_p, ctypes.POINTER(_AdapterProperties)]
        self._sensors = dll.ctlEnumTemperatureSensors
        self._sensors.argtypes = [void_p, u32_p, ctypes.POINTER(void_p)]
        self._sensor_properties = dll.ctlTemperatureGetProperties
        self._sensor_properties.argtypes = [void_p, ctypes.POINTER(_TempProperties)]
        self._sensor_state = dll.ctlTemperatureGetState
        self._sensor_state.argtypes = [void_p, ctypes.POINTER(ctypes.c_double)]
        for call in (
            self._init,
            self._close,
            self._enumerate,
            self._properties,
            self._sensors,
            self._sensor_properties,
            self._sensor_state,
        ):
            call.restype = ctypes.c_uint32

    def devices(self) -> list[IgclDevice]:
        args = _InitArgs()
        args.Size = ctypes.sizeof(_InitArgs)
        args.Version = 0
        args.AppVersion = _APP_VERSION
        args.flags = 0  # no Level Zero: the temperature calls do not need it, and it loads more
        handle = ctypes.c_void_p()
        _check(self._init(ctypes.byref(args), ctypes.byref(handle)))
        try:
            count = ctypes.c_uint32(0)
            _check(self._enumerate(handle, ctypes.byref(count), None))
            if count.value == 0:
                return []
            adapters = (ctypes.c_void_p * count.value)()
            _check(self._enumerate(handle, ctypes.byref(count), adapters))
            return [self._device(adapters[i]) for i in range(count.value)]
        finally:
            self._close(handle)

    def _device(self, adapter: int | None) -> IgclDevice:
        luid = (ctypes.c_byte * _LUID_BYTES)()
        props = _AdapterProperties()
        props.Size = ctypes.sizeof(_AdapterProperties)
        props.Version = 0
        props.pDeviceID = ctypes.cast(luid, ctypes.c_void_p)
        props.device_id_size = _LUID_BYTES
        _check(self._properties(adapter, ctypes.byref(props)))
        name = props.name.decode("ascii", errors="replace")
        device = IgclDevice(name, props.pci_vendor_id, props.pci_device_id, ())

        count = ctypes.c_uint32(0)
        code = self._sensors(adapter, ctypes.byref(count), None)
        if code != SUCCESS or count.value == 0:
            return IgclDevice(
                name, device.vendor_id, device.device_id, (), None if code == SUCCESS else code
            )
        handles = (ctypes.c_void_p * count.value)()
        code = self._sensors(adapter, ctypes.byref(count), handles)
        if code != SUCCESS:
            return IgclDevice(name, device.vendor_id, device.device_id, (), code)
        sensors = []
        for i in range(count.value):
            sensor_props = _TempProperties()
            sensor_props.Size = ctypes.sizeof(_TempProperties)
            sensor_props.Version = 0
            temperature = ctypes.c_double()
            if (
                self._sensor_properties(handles[i], ctypes.byref(sensor_props)) != SUCCESS
                or self._sensor_state(handles[i], ctypes.byref(temperature)) != SUCCESS
            ):
                continue
            sensors.append(
                IgclSensor(sensor_props.type, temperature.value, sensor_props.maxTemperature)
            )
        return IgclDevice(name, device.vendor_id, device.device_id, tuple(sensors))


def load() -> Igcl | None:
    """The library from System32, or None when no Intel driver installed it."""
    if sys.platform != "win32":
        return None
    from fpstune.utils.system_tools import system32

    path = os.path.join(system32(), LIBRARY)
    return ControlLib(path) if os.path.isfile(path) else None


def _reading(device: IgclDevice) -> ThermalReading | None:
    gpu = [s for s in device.sensors if s.kind == SENSOR_GPU]
    candidates = gpu or [s for s in device.sensors if s.kind == SENSOR_GLOBAL]
    if not candidates:
        return None
    sensor = max(candidates, key=lambda s: s.temperature_c)
    return ThermalReading(
        component="gpu",
        device_id=f"PCI\\VEN_{device.vendor_id:04X}&DEV_{device.device_id:04X}",
        name=device.name,
        temperature_c=sensor.temperature_c,
        limit_c=sensor.maximum_c if sensor.maximum_c > 0 else None,
        limit_source="IGCL sensor maximum",
        source=SOURCE,
    )


def read(api: Igcl | None = None) -> ThermalSnapshot:
    """Each Intel adapter's temperature against the maximum its own sensor reports."""
    try:
        library = api if api is not None else load()
        if library is None:
            return ThermalSnapshot(gaps=(Gap(SOURCE, NO_LIBRARY),))
        devices = library.devices()
    except IgclError as exc:
        reason = RESULT_REASONS.get(
            exc.code, f"Intel's graphics control library returned error {exc.code:#x}"
        )
        return ThermalSnapshot(gaps=(Gap(SOURCE, reason),))
    except OSError as exc:
        logger.warning("Intel graphics control library call failed: %s", exc, exc_info=True)
        return ThermalSnapshot(
            gaps=(Gap(SOURCE, "Intel's graphics control library failed while being read"),)
        )

    readings = []
    gaps = []
    for device in devices:
        reading = _reading(device)
        if reading is not None:
            readings.append(reading)
        else:
            code = f" (error {device.sensor_error:#x})" if device.sensor_error else ""
            gaps.append(
                Gap(
                    SOURCE,
                    f"{device.name or 'The Intel adapter'} reports no temperature sensor{code}",
                )
            )
    return ThermalSnapshot(readings=tuple(readings), gaps=tuple(gaps))
