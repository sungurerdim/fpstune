"""Intel's graphics control library, driven through a stand-in that checks what ctypes sends.

The structures and prototypes in `gpu_intel` were read from `igcl_api.h`. A binding that
is wrong by one field does not fail loudly: it hands the driver a structure of the wrong
size and reads garbage back. So these tests pin the layout (sizes the header's field
order works out to on x64), and drive the real `ControlLib` class against a fake DLL
that asserts what it was called with — the structure sizes, the handle plumbing, and
that `ctlClose` runs even when a later call fails.

Measured live on the development machine (11th-generation integrated GPU):
`ctlInit` returns `0x40000020`, platform not supported. That answer is a fixture here.
"""

from __future__ import annotations

import ctypes
from typing import Any
from unittest.mock import patch

import pytest

from fpstune.health import gpu_intel
from fpstune.health.gpu_intel import (
    NO_LIBRARY,
    PLATFORM_NOT_SUPPORTED,
    SENSOR_GLOBAL,
    SENSOR_GPU,
    SUCCESS,
    UNSUPPORTED_VERSION,
    ControlLib,
    IgclDevice,
    IgclError,
    IgclSensor,
    read,
)
from fpstune.health.model import Gap
from fpstune.health.thermal import assess


class TestTheLayoutMatchesTheHeader:
    """Sizes follow from `igcl_api.h`'s field order and natural alignment on x64."""

    def test_init_args_is_thirty_six_bytes(self) -> None:
        # u32 Size, u8 Version (+3), u32 AppVersion, u32 flags, u32 SupportedVersion,
        # then the 16-byte application id.
        assert ctypes.sizeof(gpu_intel._InitArgs) == 36

    def test_adapter_properties_is_three_hundred_twenty_bytes(self) -> None:
        # Pointer at 8, driver_version at 32, firmware at 40, name[100] at 88,
        # the xe-core count at 204, reserved[108] at 208: 316, rounded up to 8.
        assert ctypes.sizeof(gpu_intel._AdapterProperties) == 320

    def test_temperature_properties_is_twenty_four_bytes(self) -> None:
        # u32, u8 (+3), i32 type, f64 maximum (aligned to 8).
        assert ctypes.sizeof(gpu_intel._TempProperties) == 24
        assert gpu_intel._TempProperties.maxTemperature.offset == 16

    def test_the_name_and_the_xe_core_count_sit_where_the_header_puts_them(self) -> None:
        assert gpu_intel._AdapterProperties.name.offset == 88
        assert gpu_intel._AdapterProperties.num_xe_cores.offset == 204


class _Fn:
    """A stand-in for one DLL export: records the call, carries `argtypes` and `restype`."""

    def __init__(self, impl: Any) -> None:
        self.impl = impl
        self.argtypes: Any = None
        self.restype: Any = None

    def __call__(self, *args: Any) -> int:
        return self.impl(*args)


def _target(reference: Any) -> Any:
    """What a `ctypes.byref(...)` argument points at."""
    return reference._obj


class FakeDll:
    """An Arc card with a GPU sensor and a global sensor; every call is logged."""

    def __init__(self, *, init: int = SUCCESS, sensors_code: int = SUCCESS) -> None:
        self.calls: list[str] = []
        self.seen: dict[str, Any] = {}
        self._init_code = init
        self._sensors_code = sensors_code
        self.ctlInit = _Fn(self._ctl_init)
        self.ctlClose = _Fn(self._ctl_close)
        self.ctlEnumerateDevices = _Fn(self._enumerate)
        self.ctlGetDeviceProperties = _Fn(self._properties)
        self.ctlEnumTemperatureSensors = _Fn(self._sensors)
        self.ctlTemperatureGetProperties = _Fn(self._sensor_properties)
        self.ctlTemperatureGetState = _Fn(self._sensor_state)

    def _ctl_init(self, args: Any, handle: Any) -> int:
        self.calls.append("init")
        init = _target(args)
        self.seen["init_size"], self.seen["init_version"] = init.Size, init.Version
        self.seen["init_app_version"], self.seen["init_flags"] = init.AppVersion, init.flags
        _target(handle).value = 0x1000
        return self._init_code

    def _ctl_close(self, _handle: Any) -> int:
        self.calls.append("close")
        return SUCCESS

    def _enumerate(self, _handle: Any, count: Any, devices: Any) -> int:
        self.calls.append("enumerate" if devices is None else "enumerate-fill")
        _target(count).value = 1
        if devices is not None:
            devices[0] = 0x2000
        return SUCCESS

    def _properties(self, _device: Any, props: Any) -> int:
        self.calls.append("properties")
        value = _target(props)
        self.seen["props_size"], self.seen["luid_size"] = value.Size, value.device_id_size
        self.seen["luid_given"] = bool(value.pDeviceID)
        value.name = b"Intel(R) Arc(TM) A770 Graphics"
        value.pci_vendor_id, value.pci_device_id = 0x8086, 0x56A0
        return SUCCESS

    def _sensors(self, _device: Any, count: Any, handles: Any) -> int:
        self.calls.append("sensors" if handles is None else "sensors-fill")
        if self._sensors_code != SUCCESS:
            return self._sensors_code
        _target(count).value = 2
        if handles is not None:
            handles[0], handles[1] = 0x3001, 0x3002
        return SUCCESS

    def _sensor_properties(self, sensor: Any, props: Any) -> int:
        value = _target(props)
        self.seen["temp_props_size"] = value.Size
        value.type = SENSOR_GPU if sensor == 0x3001 else SENSOR_GLOBAL
        value.maxTemperature = 100.0 if sensor == 0x3001 else 110.0
        return SUCCESS

    def _sensor_state(self, sensor: Any, temperature: Any) -> int:
        _target(temperature).value = 58.5 if sensor == 0x3001 else 61.0
        return SUCCESS


def _library(dll: FakeDll) -> ControlLib:
    with patch.object(ctypes, "WinDLL", return_value=dll, create=True):
        return ControlLib("C:\\fake\\ControlLib.dll")


class TestTheRealBindingAgainstAFakeDll:
    def test_it_sends_structures_of_the_size_the_header_declares(self) -> None:
        dll = FakeDll()

        _library(dll).devices()

        assert dll.seen["init_size"] == 36
        assert dll.seen["init_version"] == 0
        assert dll.seen["init_flags"] == 0
        assert dll.seen["props_size"] == 320
        assert dll.seen["temp_props_size"] == 24

    def test_it_supplies_the_luid_buffer_the_properties_call_needs(self) -> None:
        dll = FakeDll()

        _library(dll).devices()

        assert dll.seen["luid_given"] is True
        assert dll.seen["luid_size"] == 8

    def test_it_asks_for_the_counts_before_the_handles_and_closes_last(self) -> None:
        dll = FakeDll()

        _library(dll).devices()

        assert dll.calls == [
            "init",
            "enumerate",
            "enumerate-fill",
            "properties",
            "sensors",
            "sensors-fill",
            "close",
        ]

    def test_it_returns_the_device_with_both_sensors_and_their_maximums(self) -> None:
        (device,) = _library(FakeDll()).devices()

        assert device == IgclDevice(
            name="Intel(R) Arc(TM) A770 Graphics",
            vendor_id=0x8086,
            device_id=0x56A0,
            sensors=(
                IgclSensor(SENSOR_GPU, 58.5, 100.0),
                IgclSensor(SENSOR_GLOBAL, 61.0, 110.0),
            ),
        )

    def test_a_failed_init_raises_with_the_code_and_never_closes_a_handle_it_does_not_have(
        self,
    ) -> None:
        dll = FakeDll(init=PLATFORM_NOT_SUPPORTED)

        with pytest.raises(IgclError) as raised:
            _library(dll).devices()

        assert raised.value.code == PLATFORM_NOT_SUPPORTED
        assert dll.calls == ["init"]

    def test_a_sensor_enumeration_that_fails_leaves_a_device_with_no_sensors_and_the_code(
        self,
    ) -> None:
        dll = FakeDll(sensors_code=0x40000014)

        (device,) = _library(dll).devices()

        assert (device.sensors, device.sensor_error) == ((), 0x40000014)
        assert dll.calls[-1] == "close"


class _FakeApi:
    def __init__(self, *devices: IgclDevice, error: Exception | None = None) -> None:
        self._devices = list(devices)
        self._error = error

    def devices(self) -> list[IgclDevice]:
        if self._error:
            raise self._error
        return self._devices


_ARC = IgclDevice(
    "Intel(R) Arc(TM) A770 Graphics",
    0x8086,
    0x56A0,
    (IgclSensor(SENSOR_GPU, 58.5, 100.0), IgclSensor(SENSOR_GLOBAL, 61.0, 110.0)),
)


class TestRead:
    def test_the_gpu_sensor_is_read_against_its_own_maximum(self) -> None:
        (reading,) = read(_FakeApi(_ARC)).readings

        assert (reading.temperature_c, reading.limit_c) == (58.5, 100.0)
        assert reading.device_id == "PCI\\VEN_8086&DEV_56A0"
        assert reading.component == "gpu"

    def test_with_no_gpu_sensor_the_global_one_is_used(self) -> None:
        device = IgclDevice("iGPU", 0x8086, 0x9A60, (IgclSensor(SENSOR_GLOBAL, 70.0, 105.0),))

        (reading,) = read(_FakeApi(device)).readings

        assert (reading.temperature_c, reading.limit_c) == (70.0, 105.0)

    def test_a_sensor_that_reports_no_maximum_is_not_judged(self) -> None:
        device = IgclDevice("iGPU", 0x8086, 0x9A60, (IgclSensor(SENSOR_GPU, 99.0, 0.0),))

        result = assess([read(_FakeApi(device))])

        assert result.findings == ()
        assert any(
            g.source == "intel_igcl" and "publishes no limit" in g.reason for g in result.gaps
        )

    def test_a_hot_arc_card_is_a_critical_finding(self) -> None:
        device = IgclDevice("Arc", 0x8086, 0x56A0, (IgclSensor(SENSOR_GPU, 101.0, 100.0),))

        (finding,) = assess([read(_FakeApi(device))]).findings

        assert (finding.severity, finding.title_key) == ("critical", "health.gpu.temperature")

    def test_a_device_with_no_sensor_is_a_gap_with_the_code(self) -> None:
        device = IgclDevice("Arc", 0x8086, 0x56A0, (), sensor_error=0x40000014)

        assert read(_FakeApi(device)).gaps == (
            Gap("intel_igcl", "Arc reports no temperature sensor (error 0x40000014)"),
        )

    def test_the_platform_not_supported_answer_this_machine_gives_is_named(self) -> None:
        snapshot = read(_FakeApi(error=IgclError(PLATFORM_NOT_SUPPORTED)))

        (gap,) = snapshot.gaps
        assert gap.source == "intel_igcl"
        assert "not supported" in gap.reason

    def test_an_unsupported_interface_version_is_named(self) -> None:
        (gap,) = read(_FakeApi(error=IgclError(UNSUPPORTED_VERSION))).gaps

        assert "interface version" in gap.reason

    def test_an_unknown_error_code_is_shown_as_the_code(self) -> None:
        (gap,) = read(_FakeApi(error=IgclError(0x40000099))).gaps

        assert "0x40000099" in gap.reason

    def test_an_access_violation_from_the_driver_is_a_gap_not_a_crash(self) -> None:
        (gap,) = read(_FakeApi(error=OSError("exception: access violation reading 0x0"))).gaps

        assert gap.source == "intel_igcl"
        assert "failed while being read" in gap.reason

    def test_no_library_installed_is_a_gap(self) -> None:
        with patch.object(gpu_intel, "load", return_value=None):
            snapshot = read()

        assert snapshot.gaps == (Gap("intel_igcl", NO_LIBRARY),)

    def test_load_returns_none_when_the_dll_is_not_in_system32(self, tmp_path: Any) -> None:
        with (
            patch("fpstune.utils.system_tools.system32", return_value=str(tmp_path)),
            patch.object(gpu_intel.sys, "platform", "win32"),
        ):
            assert gpu_intel.load() is None
