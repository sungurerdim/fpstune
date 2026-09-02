"""The standby list is measured before it is purged, and purged the documented way.

The PowerShell version passed the value 4 as the buffer *pointer*, so the kernel
was handed address 0x4 and the script printed success regardless. These tests
pin the buffer decoding against a synthetic SYSTEM_MEMORY_LIST_INFORMATION, the
struct layouts the privilege call depends on, and — on Windows — that the kernel
answers the query at all. The purge itself mutates the machine and runs only
when FPSTUNE_LIVE_PURGE=1 is set by someone who wants it.
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys

import pytest

from fpstune.utils.winapi import memory
from fpstune.utils.winapi.memory import (
    MEMORY_PURGE_STANDBY_LIST,
    SYSTEM_MEMORY_LIST_INFORMATION,
    MemoryLists,
    memory_lists_from_buffer,
)


def _buffer(*fields: int, pointer_size: int = 8) -> bytes:
    fmt = "<Q" if pointer_size == 8 else "<I"
    return b"".join(struct.pack(fmt, f) for f in fields)


class TestDecoding:
    def test_standby_is_the_sum_over_the_eight_priorities(self) -> None:
        priorities = [10, 20, 30, 40, 50, 60, 70, 80]
        repurposed = [0] * 8
        buffer = _buffer(1, 2, 3, 4, 5, *priorities, *repurposed, 6)
        lists = memory_lists_from_buffer(buffer, page_size=4096)
        assert lists == MemoryLists(
            zero_pages=1,
            free_pages=2,
            modified_pages=3,
            standby_pages_by_priority=tuple(priorities),
            page_size=4096,
        )
        assert lists.standby_pages == 360
        assert lists.standby_mb == 360 * 4096 // (1024 * 1024)

    def test_a_short_buffer_is_no_answer(self) -> None:
        """Half a struct is not a smaller struct; it is nothing to report."""
        assert memory_lists_from_buffer(b"\0" * 40, page_size=4096) is None

    def test_a_32_bit_layout_is_decoded_with_4_byte_fields(self) -> None:
        priorities = [1] * 8
        buffer = _buffer(0, 0, 0, 0, 0, *priorities, *([0] * 8), 0, pointer_size=4)
        lists = memory_lists_from_buffer(buffer, page_size=4096, pointer_size=4)
        assert lists is not None and lists.standby_pages == 8

    def test_the_constants_are_the_documented_ones(self) -> None:
        """SystemMemoryListInformation is class 80; MemoryPurgeStandbyList is 4.
        The command travels as a 4-byte int behind a pointer, never as the pointer."""
        assert SYSTEM_MEMORY_LIST_INFORMATION == 80
        assert MEMORY_PURGE_STANDBY_LIST == 4
        assert ctypes.sizeof(ctypes.c_int(MEMORY_PURGE_STANDBY_LIST)) == 4


class TestPrivilegeStructs:
    def test_token_privileges_layout_matches_win32(self) -> None:
        """DWORD count + one LUID_AND_ATTRIBUTES (8 + 4) = 16 bytes."""
        assert ctypes.sizeof(memory._LUID) == 8
        assert ctypes.sizeof(memory._LUID_AND_ATTRIBUTES) == 12
        assert ctypes.sizeof(memory._TOKEN_PRIVILEGES) == 16


@pytest.mark.skipif(sys.platform != "win32", reason="reads the running kernel")
class TestTheRealKernel:
    def test_the_query_answers_with_plausible_counts(self) -> None:
        lists = memory.memory_lists()
        assert lists is not None
        assert lists.page_size in (4096, 8192, 16384)
        assert lists.standby_pages >= 0

    @pytest.mark.skipif(os.environ.get("FPSTUNE_LIVE_PURGE") != "1", reason="mutates the machine")
    def test_a_live_purge_reports_what_it_released(self) -> None:
        outcome = memory.purge_standby_list()
        assert outcome.ok, f"NTSTATUS {outcome.status:#010x}"
        assert outcome.released_mb is not None and outcome.released_mb >= 0
