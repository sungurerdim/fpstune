"""Counters are added by their English path, so a Turkish machine reads them too.

A counter's path is translated on a localised Windows. This development machine is
Turkish, and a query that names `\\Processor Information(_Total)\\% Processor Performance`
through the *localised* API fails there, while `PdhAddEnglishCounterW` takes the English
path on any language and returns the same counter. What this file keeps true:

* the English API is the only one called — `PdhAddCounterW` raises in the stand-in, so
  a change back to it fails here and not on a user's Turkish machine;
* a counter the machine does not have is *missing*, never zero;
* a rate is read as the second collection, never the first;
* on this machine, whatever its language, the real counters answer (a live check).
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

import pytest

from fpstune.health import pdh
from fpstune.health.pdh import (
    CPU_BUSY,
    CPU_PERFORMANCE,
    CPU_PERFORMANCE_LIMIT,
    PDH_FMT_DOUBLE,
    PDH_FMT_NOCAP100,
    PDH_MORE_DATA,
    ZONE_PASSIVE_LIMIT,
    CounterSet,
    WindowsPdh,
)


class _FakePdh:
    """A Windows whose counters exist only under their English paths."""

    def __init__(self, answers: dict[str, list[float]]) -> None:
        self.answers = answers
        self.handles: dict[int, str] = {}
        self.collected = 0
        self.closed = False
        self.added: list[str] = []

    def open_query(self) -> int:
        return 7

    def add_english_counter(self, _query: int, path: str) -> int | None:
        self.added.append(path)
        if path not in self.answers:
            return None
        handle = 100 + len(self.handles)
        self.handles[handle] = path
        return handle

    def collect(self, _query: int) -> bool:
        self.collected += 1
        return True

    def values(self, counter: int) -> list[float]:
        # A rate has no value until it has been collected twice.
        return self.answers[self.handles[counter]] if self.collected >= 2 else []

    def close(self, _query: int) -> None:
        self.closed = True


_PATHS = {
    "performance": CPU_PERFORMANCE,
    "limit": CPU_PERFORMANCE_LIMIT,
    "busy": CPU_BUSY,
    "passive": ZONE_PASSIVE_LIMIT,
}


class TestCounterSet:
    def test_each_counter_is_read_under_the_name_it_was_asked_for(self) -> None:
        fake = _FakePdh(
            {
                CPU_PERFORMANCE: [148.0],
                CPU_PERFORMANCE_LIMIT: [100.0],
                CPU_BUSY: [32.4],
                ZONE_PASSIVE_LIMIT: [100.0, 100.0],
            }
        )

        with CounterSet(_PATHS, fake) as counters:
            readings = counters.read()

        assert readings == {
            "performance": [148.0],
            "limit": [100.0],
            "busy": [32.4],
            "passive": [100.0, 100.0],
        }
        assert fake.added == list(_PATHS.values())

    def test_the_first_collection_is_only_the_baseline_a_rate_is_measured_from(self) -> None:
        fake = _FakePdh({CPU_PERFORMANCE: [148.0]})

        counters = CounterSet({"performance": CPU_PERFORMANCE}, fake)

        assert fake.collected == 1  # the baseline, taken when the query opened
        assert counters.read() == {"performance": [148.0]}
        assert fake.collected == 2

    def test_a_counter_this_machine_does_not_have_is_missing_not_zero(self) -> None:
        """A machine with no thermal zone has no `Thermal Zone Information` object."""
        fake = _FakePdh({CPU_PERFORMANCE: [148.0]})

        with CounterSet(_PATHS, fake) as counters:
            readings = counters.read()

        assert counters.missing == ["limit", "busy", "passive"]
        assert readings == {"performance": [148.0]}

    def test_the_query_is_closed_even_when_the_caller_raises(self) -> None:
        fake = _FakePdh({CPU_PERFORMANCE: [148.0]})

        with pytest.raises(RuntimeError), CounterSet({"performance": CPU_PERFORMANCE}, fake):
            raise RuntimeError("the caller failed")

        assert fake.closed

    def test_a_failed_collection_is_an_empty_read_not_stale_values(self) -> None:
        fake = _FakePdh({CPU_PERFORMANCE: [148.0]})
        counters = CounterSet({"performance": CPU_PERFORMANCE}, fake)
        fake.collect = lambda _query: False  # type: ignore[method-assign]

        assert counters.read() == {}


class _Fn:
    def __init__(self, impl: Any) -> None:
        self.impl = impl
        self.argtypes: Any = None
        self.restype: Any = None

    def __call__(self, *args: Any) -> int:
        return self.impl(*args)


class _FakePdhDll:
    """`pdh.dll` with only the English entry point: asking for another name fails."""

    _ALLOWED = frozenset(
        {
            "PdhOpenQueryW",
            "PdhAddEnglishCounterW",
            "PdhCollectQueryData",
            "PdhGetFormattedCounterArrayW",
            "PdhCloseQuery",
        }
    )

    def __init__(self, items: list[float], *, add_status: int = 0) -> None:
        self.items = items
        self.add_status = add_status
        self.paths: list[str] = []
        self.formats: list[int] = []
        self.PdhOpenQueryW = _Fn(self._open)
        self.PdhAddEnglishCounterW = _Fn(self._add)
        self.PdhCollectQueryData = _Fn(lambda _query: 0)
        self.PdhGetFormattedCounterArrayW = _Fn(self._array)
        self.PdhCloseQuery = _Fn(lambda _query: 0)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(f"{name} is not one of the English-name entry points")

    def _open(self, _source: Any, _data: int, query: Any) -> int:
        query._obj.value = 0x10
        return 0

    def _add(self, _query: Any, path: str, _data: int, counter: Any) -> int:
        self.paths.append(path)
        if self.add_status == 0:
            counter._obj.value = 0x20
        return self.add_status

    def _array(self, _counter: Any, flags: int, size: Any, count: Any, buffer: Any) -> int:
        self.formats.append(flags)
        item_type = pdh._FmtItem
        needed = ctypes.sizeof(item_type) * len(self.items)
        if buffer is None:
            size._obj.value = needed
            return PDH_MORE_DATA
        array = (item_type * len(self.items))()
        for index, value in enumerate(self.items):
            array[index].FmtValue.CStatus = 0
            array[index].FmtValue.doubleValue = value
        ctypes.memmove(buffer, array, needed)
        count._obj.value = len(self.items)
        return 0


def _windows_pdh(dll: _FakePdhDll) -> WindowsPdh:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ctypes, "WinDLL", lambda _name: dll, raising=False)
        return WindowsPdh()


class TestTheRealBindingUsesTheEnglishApiOnly:
    def test_the_english_path_reaches_the_english_entry_point_unchanged(self) -> None:
        dll = _FakePdhDll([148.0])
        api = _windows_pdh(dll)

        handle = api.add_english_counter(api.open_query(), CPU_PERFORMANCE)

        assert handle == 0x20
        assert dll.paths == [CPU_PERFORMANCE]

    def test_a_counter_the_machine_lacks_is_none(self) -> None:
        dll = _FakePdhDll([], add_status=0xC0000BB8)  # PDH_CSTATUS_NO_OBJECT
        api = _windows_pdh(dll)

        assert api.add_english_counter(api.open_query(), ZONE_PASSIVE_LIMIT) is None

    def test_the_localised_entry_point_is_never_touched(self) -> None:
        dll = _FakePdhDll([100.0])
        api = _windows_pdh(dll)

        with CounterSet({"limit": CPU_PERFORMANCE_LIMIT}, api) as counters:
            counters.read()

        # `PdhAddCounterW` raises AttributeError in the stand-in; reaching here without
        # it means the localised API was never asked for.
        assert dll.paths == [CPU_PERFORMANCE_LIMIT]

    def test_every_instance_of_a_wildcard_counter_is_returned(self) -> None:
        dll = _FakePdhDll([100.0, 62.5])
        api = _windows_pdh(dll)
        handle = api.add_english_counter(api.open_query(), ZONE_PASSIVE_LIMIT)
        assert handle is not None

        assert api.values(handle) == [100.0, 62.5]

    def test_a_percentage_above_one_hundred_is_not_clamped(self) -> None:
        """`% Processor Performance` is 148 % while the CPU boosts; capping it at 100 hides that."""
        dll = _FakePdhDll([148.0])
        api = _windows_pdh(dll)
        handle = api.add_english_counter(api.open_query(), CPU_PERFORMANCE)
        assert handle is not None

        api.values(handle)

        assert all(flags & PDH_FMT_NOCAP100 and flags & PDH_FMT_DOUBLE for flags in dll.formats)


class TestTheStructuresMatchTheHeader:
    def test_a_formatted_value_is_sixteen_bytes_with_the_double_on_an_eight_byte_boundary(
        self,
    ) -> None:
        assert ctypes.sizeof(pdh._FmtValue) == 16
        assert pdh._FmtValue.doubleValue.offset == 8

    def test_an_array_item_is_twenty_four_bytes(self) -> None:
        # LPWSTR szName (8) followed by the 16-byte value.
        assert ctypes.sizeof(pdh._FmtItem) == 24


@pytest.mark.skipif(sys.platform != "win32", reason="performance counters are a Windows API")
class TestOnThisMachineWhateverItsLanguage:
    """The development machine is Turkish: its counter names are not the English ones."""

    def test_the_cpu_counters_answer_by_their_english_paths(self) -> None:
        import time

        with CounterSet(
            {"performance": CPU_PERFORMANCE, "limit": CPU_PERFORMANCE_LIMIT, "busy": CPU_BUSY}
        ) as counters:
            time.sleep(0.5)
            readings = counters.read()

        assert counters.missing == []
        assert readings["performance"][0] > 0
        assert 0 < readings["limit"][0] <= 100 + 1e-6
        assert 0 <= readings["busy"][0] <= 100
