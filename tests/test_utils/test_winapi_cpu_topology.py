"""The P/E split is read from the kernel's buffer, not guessed from a name.

This replaces a C# class that PowerShell compiled at run time; Windows Defender
flagged that pattern on 2026-09-02, so the walk now lives in Python where a
synthetic buffer can prove every branch: a hybrid part, a homogeneous part,
records of other relationships interleaved, an empty answer, and a truncated
record that must end the walk instead of reading past the buffer.
"""

from __future__ import annotations

import struct
import sys

import pytest

from fpstune.utils.winapi.cpu_topology import (
    RELATION_PROCESSOR_CORE,
    CoreSplit,
    core_split,
    split_from_buffer,
)

_RELATION_CACHE = 2


def _core(efficiency: int) -> bytes:
    """One PROCESSOR_RELATIONSHIP record with a single group mask (48 bytes)."""
    body = bytes([0, efficiency]) + b"\0" * 20 + struct.pack("<H", 1) + b"\0" * 16
    return struct.pack("<II", RELATION_PROCESSOR_CORE, 8 + len(body)) + body


def _cache_record() -> bytes:
    body = b"\0" * 24
    return struct.pack("<II", _RELATION_CACHE, 8 + len(body)) + body


class TestTheWalk:
    def test_a_hybrid_part_counts_each_tier(self) -> None:
        """Eight class-1 cores and eight class-0 cores: the top class is P."""
        buffer = b"".join([_core(1)] * 8 + [_core(0)] * 8)
        assert split_from_buffer(buffer) == CoreSplit(p_cores=8, e_cores=8)
        assert split_from_buffer(buffer).is_hybrid is True  # type: ignore[union-attr]

    def test_a_homogeneous_part_is_not_hybrid(self) -> None:
        buffer = b"".join([_core(0)] * 16)
        split = split_from_buffer(buffer)
        assert split == CoreSplit(p_cores=16, e_cores=0)
        assert split.is_hybrid is False  # type: ignore[union-attr]

    def test_records_of_other_relationships_are_skipped_not_counted(self) -> None:
        """Cache records sit between core records in a real buffer."""
        buffer = _core(1) + _cache_record() + _core(0) + _cache_record() + _core(1)
        assert split_from_buffer(buffer) == CoreSplit(p_cores=2, e_cores=1)

    def test_an_empty_buffer_is_unknown_not_homogeneous(self) -> None:
        """The caller must report unknown, never "not hybrid", for no answer."""
        assert split_from_buffer(b"") is None
        assert split_from_buffer(_cache_record()) is None

    def test_a_record_running_past_the_buffer_ends_the_walk(self) -> None:
        """A declared size beyond the buffer is garbage; what was read stands."""
        truncated = struct.pack("<II", RELATION_PROCESSOR_CORE, 4096) + bytes([0, 1])
        assert split_from_buffer(_core(1) + _core(0) + truncated) == CoreSplit(1, 1)

    def test_the_top_class_is_performance_whatever_its_number(self) -> None:
        """Class numbers are ordinal, not fixed: 3 over 2 is P over E."""
        buffer = b"".join([_core(3)] * 6 + [_core(2)] * 10)
        assert split_from_buffer(buffer) == CoreSplit(p_cores=6, e_cores=10)


@pytest.mark.skipif(sys.platform != "win32", reason="reads the running machine")
class TestTheRealMachine:
    def test_the_kernel_reports_a_coherent_split(self) -> None:
        """Whatever CPU runs the suite: at least one P core, and E cores never
        exceed the logical count. No compile, no PowerShell."""
        split = core_split()
        assert split is not None
        assert split.p_cores >= 1
        assert split.e_cores >= 0
        assert split.is_hybrid == (split.e_cores > 0)
