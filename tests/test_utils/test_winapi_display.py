"""user32 through ctypes: the structs are the documented size, and the machine answers.

The PowerShell versions of these calls compiled C# at run time (Add-Type), the
pattern Windows Defender flagged on 2026-09-02. A wrong struct size here is the
classic silent failure — the call returns FALSE with an empty name, which is
exactly what the [ref] binder did (A1) — so the sizes are pinned first.
"""

from __future__ import annotations

import ctypes
import sys

import pytest

from fpstune.utils.winapi import display
from fpstune.utils.winapi.display import DEVMODEW, DISPLAY_DEVICEW, AdapterRecord


class TestStructLayouts:
    def test_display_device_is_840_bytes(self) -> None:
        """cb=840 is the size the live probe recorded for DISPLAY_DEVICEW."""
        assert ctypes.sizeof(DISPLAY_DEVICEW) == 840

    def test_devmode_is_220_bytes(self) -> None:
        """DEVMODEW without the printer-only trailing fields, as user32 expects it."""
        assert ctypes.sizeof(DEVMODEW) == 220


class TestRecordShape:
    def test_flags_decode_the_three_bits_that_matter(self) -> None:
        record = AdapterRecord(
            r"\\.\DISPLAY5", 5, r"\\?\DISPLAY#CCC0003#4&1b2c3d4e&0&UID9003#{guid}"
        )
        assert record.attached is True
        assert record.primary is True
        assert record.mirroring is False
        assert AdapterRecord(r"\\.\DISPLAYV1", 9, "").mirroring is True

    def test_the_record_line_round_trips(self) -> None:
        """The self-check still speaks the name|flags|path line the C# class emitted."""
        record = AdapterRecord(r"\\.\DISPLAY1", 1, r"\\?\DISPLAY#BBB0002#UID5002#{g}")
        assert AdapterRecord.from_record(record.as_record()) == record
        assert AdapterRecord.from_record("garbage") is None
        assert AdapterRecord.from_record(r"\\.\DISPLAY1|notanumber|x") is None


@pytest.mark.skipif(sys.platform != "win32", reason="reads the running desktop")
class TestTheRealDesktop:
    def test_at_least_one_head_is_enumerated_with_a_display_name(self) -> None:
        records = display.enumerate_adapters()
        assert records, "user32 reported no adapter heads at all"
        assert all(r.device_name.startswith("\\\\.\\DISPLAY") for r in records)

    def test_an_attached_head_has_a_current_mode_with_real_dimensions(self) -> None:
        attached = [r for r in display.enumerate_adapters() if r.attached and not r.mirroring]
        if not attached:
            pytest.skip("no attached head on this session (service or headless run)")
        mode = display.current_mode(attached[0].device_name)
        assert mode is not None
        assert mode.width > 0 and mode.height > 0 and mode.refresh_hz > 0
        # The mode table contains the current mode, so the max at that
        # resolution is at least what the head runs now.
        assert (
            display.max_refresh_at(attached[0].device_name, mode.width, mode.height)
            >= mode.refresh_hz
        )

    def test_an_unknown_device_has_no_mode(self) -> None:
        assert display.current_mode(r"\\.\DISPLAY999") is None
        assert display.enumerate_modes(r"\\.\DISPLAY999") == []
