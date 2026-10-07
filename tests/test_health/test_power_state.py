"""What the power policy is doing to the CPU: battery, and the plan's own cap.

Two numbers Windows holds that explain a CPU running slow with no heat involved: the
machine is off its charger, and the active power plan's "Maximum processor state" is
below 100 %. A plan that says 50 is a CPU that is never asked for more than half its
speed — "under half the machine's capacity" with nothing wrong in the hardware.

What this file keeps true: the right GUIDs reach the right Windows call (checked
against the bytes the call receives), AC and DC are read for the source in use, a value
that cannot be read is None and never a default, and a plan allocated by Windows is
freed.
"""

from __future__ import annotations

import ctypes
import sys
import uuid
from typing import Any

import pytest

from fpstune.health import power_state
from fpstune.health.power_state import (
    PROCTHROTTLEMAX,
    SUB_PROCESSOR,
    PowerState,
    WindowsPower,
    read,
)


class _FakeApi:
    def __init__(
        self, line: int | None, cap: int | None = 100, error: Exception | None = None
    ) -> None:
        self.line, self.cap, self.error = line, cap, error
        self.asked_battery: list[bool] = []

    def ac_line_status(self) -> int | None:
        if self.error:
            raise self.error
        return self.line

    def maximum_processor_state(self, on_battery: bool) -> int | None:
        self.asked_battery.append(on_battery)
        return self.cap


class TestRead:
    def test_a_machine_on_its_charger_reads_the_ac_value(self) -> None:
        api = _FakeApi(line=1, cap=100)

        assert read(api) == PowerState(on_battery=False, processor_cap_percent=100)
        assert api.asked_battery == [False]

    def test_a_laptop_off_its_charger_reads_the_dc_value(self) -> None:
        api = _FakeApi(line=0, cap=50)

        assert read(api) == PowerState(on_battery=True, processor_cap_percent=50)
        assert api.asked_battery == [True]

    def test_an_unknown_power_source_is_not_called_a_battery(self) -> None:
        assert read(_FakeApi(line=255)).on_battery is None

    @pytest.mark.parametrize("cap", [-1, 101, 4_000_000_000])
    def test_a_cap_outside_zero_to_one_hundred_is_not_a_percentage(self, cap: int) -> None:
        assert read(_FakeApi(line=1, cap=cap)).processor_cap_percent is None

    def test_a_cap_that_could_not_be_read_is_none_not_a_hundred(self) -> None:
        assert read(_FakeApi(line=1, cap=None)).processor_cap_percent is None

    def test_a_failure_reading_either_is_none_for_both(self) -> None:
        state = read(_FakeApi(line=1, error=OSError("powrprof.dll is not available")))

        assert state == PowerState(on_battery=None, processor_cap_percent=None)


class _Fn:
    def __init__(self, impl: Any) -> None:
        self.impl = impl
        self.argtypes: Any = None
        self.restype: Any = None

    def __call__(self, *args: Any) -> Any:
        return self.impl(*args)


def _guid_bytes(reference: Any) -> bytes:
    return bytes(reference._obj)


class _FakeLibraries:
    """kernel32 and powrprof, recording what the binding sends."""

    def __init__(self, *, ac_line: int = 1, cap: int = 100, scheme_status: int = 0) -> None:
        self.ac_line = ac_line
        self.cap = cap
        self.scheme_status = scheme_status
        self.reads: list[tuple[str, bytes, bytes]] = []
        self.freed: list[Any] = []
        self._scheme = power_state._Guid.parse("f0b769e8-7b04-4cb9-ae25-9c2a28918d23")
        self.GetSystemPowerStatus = _Fn(self._status)
        self.LocalFree = _Fn(self._free)
        self.PowerGetActiveScheme = _Fn(self._active)
        self.PowerReadACValueIndex = _Fn(lambda *a: self._read("ac", *a))
        self.PowerReadDCValueIndex = _Fn(lambda *a: self._read("dc", *a))

    def _status(self, status: Any) -> int:
        status._obj.ACLineStatus = self.ac_line
        return 1

    def _free(self, pointer: Any) -> None:
        self.freed.append(pointer)

    def _active(self, _root: Any, scheme: Any) -> int:
        if self.scheme_status == 0:
            scheme._obj.contents = self._scheme
        return self.scheme_status

    def _read(
        self, source: str, _root: Any, _scheme: Any, subgroup: Any, setting: Any, value: Any
    ) -> int:
        self.reads.append((source, _guid_bytes(subgroup), _guid_bytes(setting)))
        value._obj.value = self.cap
        return 0


def _windows_power(libraries: _FakeLibraries) -> WindowsPower:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ctypes, "WinDLL", lambda *_a, **_k: libraries, raising=False)
        return WindowsPower()


class TestTheBindingSendsTheRightGuids:
    def test_the_two_guids_are_the_ones_powercfg_prints_for_the_processor_cap(self) -> None:
        """Alias SUB_PROCESSOR and PROCTHROTTLEMAX, as `powercfg /q` listed them here."""
        assert SUB_PROCESSOR == "54533251-82be-4824-96c1-47b60b740d00"
        assert PROCTHROTTLEMAX == "bc5038f7-23e0-4960-96da-33abaf5935ec"

    def test_a_guid_has_the_memory_layout_windows_expects(self) -> None:
        # GUID is 16 bytes: u32, u16, u16, u8[8]; `bytes_le` is that layout.
        assert ctypes.sizeof(power_state._Guid) == 16
        assert bytes(power_state._Guid.parse(SUB_PROCESSOR)) == uuid.UUID(SUB_PROCESSOR).bytes_le

    def test_the_ac_read_is_asked_for_the_processor_subgroup_and_the_cap_setting(self) -> None:
        libraries = _FakeLibraries(cap=70)

        cap = _windows_power(libraries).maximum_processor_state(on_battery=False)

        assert cap == 70
        assert libraries.reads == [
            ("ac", uuid.UUID(SUB_PROCESSOR).bytes_le, uuid.UUID(PROCTHROTTLEMAX).bytes_le)
        ]

    def test_the_dc_read_is_used_on_battery(self) -> None:
        libraries = _FakeLibraries(cap=50)

        _windows_power(libraries).maximum_processor_state(on_battery=True)

        assert [source for source, _s, _g in libraries.reads] == ["dc"]

    def test_the_active_plan_that_windows_allocated_is_freed(self) -> None:
        libraries = _FakeLibraries()

        _windows_power(libraries).maximum_processor_state(on_battery=False)

        assert len(libraries.freed) == 1

    def test_no_active_plan_is_none_and_nothing_is_freed(self) -> None:
        libraries = _FakeLibraries(scheme_status=2)

        assert _windows_power(libraries).maximum_processor_state(on_battery=False) is None
        assert libraries.freed == []

    def test_the_line_status_is_passed_through(self) -> None:
        assert _windows_power(_FakeLibraries(ac_line=0)).ac_line_status() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="the power API is Windows-only")
def test_on_this_machine_the_cap_is_a_percentage_and_the_source_is_known() -> None:
    state = read()

    assert state.on_battery in (True, False)
    assert state.processor_cap_percent is not None and 0 <= state.processor_cap_percent <= 100
