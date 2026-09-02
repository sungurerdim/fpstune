"""P-core / E-core split from the kernel's own topology.

``GetLogicalProcessorInformationEx(RelationProcessorCore)`` returns one record per
physical core, and each record carries an ``EfficiencyClass`` byte: the highest
class present is the performance tier, everything below it is efficiency. One
class means not hybrid; an empty answer means *unknown*, which the caller
reports as unknown rather than "not hybrid" — a model-name list would be the
same bug as a hardcoded constant (C10).

The buffer walk is a pure function over ``bytes`` so a test can hand it a
synthetic topology; only :func:`read_topology_buffer` touches the OS.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

RELATION_PROCESSOR_CORE = 0

# SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX: Relationship (DWORD) + Size (DWORD),
# then the union. For RelationProcessorCore the union is PROCESSOR_RELATIONSHIP,
# whose first two bytes are Flags and EfficiencyClass.
_HEADER_BYTES = 8
_EFFICIENCY_CLASS_OFFSET = 9


@dataclass(frozen=True)
class CoreSplit:
    """Physical cores by tier. ``is_hybrid`` is derived, never stored twice."""

    p_cores: int
    e_cores: int

    @property
    def is_hybrid(self) -> bool:
        return self.e_cores > 0


def split_from_buffer(buffer: bytes) -> CoreSplit | None:
    """Count cores per efficiency class in a topology buffer.

    Returns ``None`` when the buffer holds no core record at all — the unknown
    answer. A record whose declared size runs past the buffer ends the walk
    rather than reading garbage.
    """
    counts: dict[int, int] = {}
    total = len(buffer)
    offset = 0
    while offset + _HEADER_BYTES <= total:
        relationship = int.from_bytes(buffer[offset : offset + 4], "little")
        size = int.from_bytes(buffer[offset + 4 : offset + 8], "little")
        if size <= 0 or offset + size > total:
            break
        if relationship == RELATION_PROCESSOR_CORE and offset + _EFFICIENCY_CLASS_OFFSET < total:
            efficiency = buffer[offset + _EFFICIENCY_CLASS_OFFSET]
            counts[efficiency] = counts.get(efficiency, 0) + 1
        offset += size
    if not counts:
        return None
    top = max(counts)
    return CoreSplit(
        p_cores=counts[top],
        e_cores=sum(count for klass, count in counts.items() if klass != top),
    )


def read_topology_buffer() -> bytes | None:
    """The raw RelationProcessorCore buffer, or ``None`` off Windows or on failure."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel32.GetLogicalProcessorInformationEx
    query.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL

    length = wintypes.DWORD(0)
    # The sizing call fails by design (ERROR_INSUFFICIENT_BUFFER) and fills `length`.
    query(RELATION_PROCESSOR_CORE, None, ctypes.byref(length))
    if length.value == 0:
        return None
    buffer = ctypes.create_string_buffer(length.value)
    if not query(RELATION_PROCESSOR_CORE, buffer, ctypes.byref(length)):
        return None
    return buffer.raw[: length.value]


def core_split() -> CoreSplit | None:
    """The machine's P/E split, or ``None`` when the kernel would not say."""
    buffer = read_topology_buffer()
    return split_from_buffer(buffer) if buffer else None
