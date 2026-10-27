"""Windows performance counters by their English names, so a Turkish machine reads them too.

A performance counter's path is translated on a localised Windows: this machine
(Turkish) names `\\Processor Information(_Total)\\% Processor Performance` in Turkish, and
a query written with that path in English fails on it. The documented answer is
`PdhAddEnglishCounterW`, which takes the English path on every language and returns the
same counter; `PdhAddCounterW` is never called here, and a test fails if it is.

Measured on the development machine (Turkish locale), every counter below was added by
its English path and returned a value:

| Counter | Meaning (the counter's own help text) |
|---|---|
| `\\Processor Information(_Total)\\% Processor Performance` | the average performance of the processor while it executes instructions, as a percentage of its nominal performance; it can exceed 100 % when the CPU boosts |
| `\\Processor Information(_Total)\\% Performance Limit` | the performance the processor guarantees as a percentage of nominal; Windows power policy or the platform can limit it for a power budget, excessive heat or other hardware problems |
| `\\Processor Information(_Total)\\% Processor Time` | the share of time the processors were busy |
| `\\Thermal Zone Information(*)\\% Passive Limit` | the limit a thermal zone currently imposes on the devices it controls: 100 % is unrestricted, 0 % fully restricted |
| `\\Thermal Zone Information(*)\\Throttle Reasons` | why a thermal zone limits those devices (a bit mask; non-zero means it is) |

**Rates need two collections.** A counter that is a rate over time has no value until
it has been collected twice, so the query collects once when it opens and the first
`read()` is the second: a value is the average since the previous collection.

**A counter that does not exist here is reported as missing, not as zero.** A machine
with no thermal zone has no `Thermal Zone Information` object, and the add fails; that
counter is simply absent from the result and named in `missing`.
"""

from __future__ import annotations

import ctypes
from collections.abc import Mapping
from ctypes import wintypes
from types import TracebackType
from typing import Protocol

from fpstune.utils.logger import get_logger

logger = get_logger()

CPU_PERFORMANCE = r"\Processor Information(_Total)\% Processor Performance"
CPU_PERFORMANCE_LIMIT = r"\Processor Information(_Total)\% Performance Limit"
CPU_BUSY = r"\Processor Information(_Total)\% Processor Time"
ZONE_PASSIVE_LIMIT = r"\Thermal Zone Information(*)\% Passive Limit"
ZONE_THROTTLE_REASONS = r"\Thermal Zone Information(*)\Throttle Reasons"

PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
"""Without this a percentage is clamped to 100, and `% Processor Performance` is a boost above it."""
PDH_MORE_DATA = 0x800007D2
_VALID_STATUSES = frozenset({0, 1})
"""PDH_CSTATUS_VALID_DATA and PDH_CSTATUS_NEW_DATA."""


class Pdh(Protocol):
    """The five calls the reader makes, so a test can stand in for them."""

    def open_query(self) -> int: ...

    def add_english_counter(self, query: int, path: str) -> int | None:
        """The counter handle, or None when the machine has no such counter."""
        ...

    def collect(self, query: int) -> bool: ...

    def values(self, counter: int) -> list[float]:
        """Every instance's value for one counter; empty when none is valid yet."""
        ...

    def close(self, query: int) -> None: ...


class _FmtValue(ctypes.Structure):
    """`PDH_FMT_COUNTERVALUE`: a status, then a union of which only the double is used."""

    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _FmtItem(ctypes.Structure):
    """`PDH_FMT_COUNTERVALUE_ITEM_W`: the instance name, then its value."""

    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _FmtValue)]


class WindowsPdh:
    """The real `pdh.dll`."""

    def __init__(self) -> None:
        dll = ctypes.WinDLL("pdh")
        dll.PdhOpenQueryW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.PdhAddEnglishCounterW.argtypes = [
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
        dll.PdhGetFormattedCounterArrayW.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        dll.PdhCloseQuery.argtypes = [ctypes.c_void_p]
        for call in (
            dll.PdhOpenQueryW,
            dll.PdhAddEnglishCounterW,
            dll.PdhCollectQueryData,
            dll.PdhGetFormattedCounterArrayW,
            dll.PdhCloseQuery,
        ):
            call.restype = wintypes.DWORD
        self._dll = dll

    def open_query(self) -> int:
        query = ctypes.c_void_p()
        status = self._dll.PdhOpenQueryW(None, 0, ctypes.byref(query))
        if status != 0 or not query.value:
            raise OSError(f"PdhOpenQueryW failed ({status:#x})")
        return int(query.value)

    def add_english_counter(self, query: int, path: str) -> int | None:
        counter = ctypes.c_void_p()
        status = self._dll.PdhAddEnglishCounterW(
            ctypes.c_void_p(query), path, 0, ctypes.byref(counter)
        )
        return int(counter.value) if status == 0 and counter.value else None

    def collect(self, query: int) -> bool:
        return bool(self._dll.PdhCollectQueryData(ctypes.c_void_p(query)) == 0)

    def values(self, counter: int) -> list[float]:
        flags = PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        status = self._dll.PdhGetFormattedCounterArrayW(
            ctypes.c_void_p(counter), flags, ctypes.byref(size), ctypes.byref(count), None
        )
        if status != PDH_MORE_DATA or size.value == 0:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        status = self._dll.PdhGetFormattedCounterArrayW(
            ctypes.c_void_p(counter), flags, ctypes.byref(size), ctypes.byref(count), buffer
        )
        if status != 0:
            return []
        items = ctypes.cast(buffer, ctypes.POINTER(_FmtItem))
        return [
            items[i].FmtValue.doubleValue
            for i in range(count.value)
            if items[i].FmtValue.CStatus in _VALID_STATUSES
        ]

    def close(self, query: int) -> None:
        self._dll.PdhCloseQuery(ctypes.c_void_p(query))


class CounterSet:
    """A set of English-named counters read together, once per `read()`."""

    def __init__(self, paths: Mapping[str, str], api: Pdh | None = None) -> None:
        self._api: Pdh = api if api is not None else WindowsPdh()
        self._query = self._api.open_query()
        self._counters: dict[str, int] = {}
        self.missing: list[str] = []
        for name, path in paths.items():
            counter = self._api.add_english_counter(self._query, path)
            if counter is None:
                self.missing.append(name)
            else:
                self._counters[name] = counter
        # The first collection only sets the baseline a rate is measured from.
        self._api.collect(self._query)

    def read(self) -> dict[str, list[float]]:
        """Each counter's instance values since the previous collection; absent if none."""
        if not self._api.collect(self._query):
            return {}
        readings = {}
        for name, counter in self._counters.items():
            values = self._api.values(counter)
            if values:
                readings[name] = values
        return readings

    def close(self) -> None:
        self._api.close(self._query)

    def __enter__(self) -> CounterSet:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        # Closing is unconditional: a failed collection still owns a query
        # handle, and `__exit__` returning None re-raises whatever the body hit.
        self.close()
