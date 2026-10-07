"""An NVMe drive's own temperature, thresholds and warning flags, from the bytes it sent.

The pages here are built to the NVMe base specification's byte offsets and then parsed
by the code under test, so a wrong offset in the parser shows as a wrong number rather
than as agreement with itself. The values are this development machine's own drive
(composite 319 K, `WCTEMP` 354 K, `CCTEMP` 358 K, spare 100 % against a threshold of
10 %), passed in as fixture input (C9).

What this file keeps true:

* the drive's own `WCTEMP` is the limit, and a drive that reports 0 has published none;
* the drive's own critical-warning flags are findings, each `critical`, because each is
  the drive reporting that it is failing;
* a reply too short for the page is a failure, never a reading of zeros;
* the request sent to Windows has the layout the NVMe pass-through documents.
"""

from __future__ import annotations

import ctypes
import struct
from typing import Any

import pytest

from fpstune.health import nvme
from fpstune.health.inventory import Disk
from fpstune.health.model import Gap
from fpstune.health.nvme import (
    ERROR_ACCESS_DENIED,
    HEALTH_LOG_BYTES,
    IDENTIFY_BYTES,
    IOCTL_STORAGE_QUERY_PROPERTY,
    NEEDS_ADMIN,
    NOT_EXPOSED,
    NvmeDrive,
    NvmeError,
    WindowsNvme,
    parse_drive,
    payload_of,
    read,
)
from fpstune.health.thermal import assess

_DISK = Disk(
    number=0,
    unique_id="eui.0025385A11B2C3D4",
    name="SAMSUNG MZVL21T0HCLR-00B00",
    bus_type="NVMe",
    media_type="SSD",
)


def _health(
    *,
    warning: int = 0,
    composite_k: int = 319,
    spare: int = 100,
    threshold: int = 10,
    used: int = 6,
    minutes_over_warning: int = 0,
    minutes_over_critical: int = 0,
) -> bytes:
    page = bytearray(HEALTH_LOG_BYTES)
    page[0] = warning
    struct.pack_into("<H", page, 1, composite_k)
    page[3], page[4], page[5] = spare, threshold, used
    struct.pack_into("<I", page, 192, minutes_over_warning)
    struct.pack_into("<I", page, 196, minutes_over_critical)
    return bytes(page)


def _identify(*, wctemp_k: int = 354, cctemp_k: int = 358) -> bytes:
    page = bytearray(IDENTIFY_BYTES)
    struct.pack_into("<HH", page, 266, wctemp_k, cctemp_k)
    return bytes(page)


class _Drive:
    """What `NvmeAccess.query` returns for each page of one fake drive."""

    def __init__(self, health: bytes, identify: bytes, error: NvmeError | None = None) -> None:
        self.pages = {"health": health, "identify": identify}
        self.error = error
        self.asked: list[tuple[int, str]] = []

    def query(self, disk_number: int, page: str) -> bytes:
        self.asked.append((disk_number, page))
        if self.error:
            raise self.error
        return self.pages[page]


class TestParse:
    def test_every_field_comes_from_the_offset_the_spec_gives(self) -> None:
        drive = parse_drive(
            _health(
                warning=0x05,
                composite_k=330,
                spare=87,
                threshold=10,
                used=42,
                minutes_over_warning=12,
                minutes_over_critical=3,
            ),
            _identify(wctemp_k=355, cctemp_k=360),
        )

        assert drive == NvmeDrive(
            critical_warning=0x05,
            composite_c=57.0,
            spare_percent=87,
            spare_threshold_percent=10,
            percentage_used=42,
            minutes_over_warning=12,
            minutes_over_critical=3,
            warning_c=82.0,
            critical_c=87.0,
        )

    def test_this_machines_drive_is_forty_six_degrees_with_limits_of_eighty_one_and_eighty_five(
        self,
    ) -> None:
        drive = parse_drive(_health(), _identify())

        assert (drive.composite_c, drive.warning_c, drive.critical_c) == (46.0, 81.0, 85.0)

    def test_a_threshold_of_zero_means_the_drive_published_none(self) -> None:
        drive = parse_drive(_health(), _identify(wctemp_k=0, cctemp_k=0))

        assert (drive.warning_c, drive.critical_c) == (None, None)

    @pytest.mark.parametrize("cut", [0, 100, HEALTH_LOG_BYTES - 1])
    def test_a_health_page_shorter_than_the_spec_is_an_error_not_zeros(self, cut: int) -> None:
        with pytest.raises(NvmeError):
            parse_drive(_health()[:cut], _identify())

    def test_an_identify_page_too_short_for_the_thresholds_is_an_error(self) -> None:
        with pytest.raises(NvmeError):
            parse_drive(_health(), _identify()[:200])


def _descriptor(payload: bytes, *, offset: int = 40, advertised: int | None = None) -> bytes:
    """A `STORAGE_PROTOCOL_DATA_DESCRIPTOR`: version, size, the specific data, the page."""
    specific = struct.pack(
        "<10I", 3, 2, 2, 0, offset, len(payload) if advertised is None else advertised, 0, 0, 0, 0
    )
    return struct.pack("<II", 1, 8 + 40) + specific + b"\x00" * (offset - 40) + payload


class TestPayloadOf:
    def test_the_page_is_found_where_the_driver_says_it_is(self) -> None:
        assert payload_of(_descriptor(b"\x01\x02\x03\x04")) == b"\x01\x02\x03\x04"

    def test_a_driver_that_pads_differently_is_still_read_right(self) -> None:
        assert payload_of(_descriptor(b"\xaa\xbb", offset=48)) == b"\xaa\xbb"

    def test_a_reply_that_ends_before_the_page_it_advertises_is_an_error(self) -> None:
        with pytest.raises(NvmeError):
            payload_of(_descriptor(b"\x01\x02", advertised=512))

    def test_a_reply_too_short_to_hold_the_header_is_an_error(self) -> None:
        with pytest.raises(NvmeError):
            payload_of(b"\x00" * 20)

    def test_a_page_of_zero_length_is_an_error(self) -> None:
        with pytest.raises(NvmeError):
            payload_of(_descriptor(b"", advertised=0))


class TestRead:
    def test_a_cool_drive_is_a_reading_against_its_own_warning_temperature(self) -> None:
        drive = _Drive(_health(), _identify())

        snapshot = read([_DISK], drive)

        (reading,) = snapshot.readings
        assert (reading.temperature_c, reading.limit_c, reading.critical_c) == (46.0, 81.0, 85.0)
        assert reading.device_id == "eui.0025385A11B2C3D4"
        assert reading.limit_source == "NVMe WCTEMP"
        assert assess([snapshot]).findings == ()

    def test_it_asks_the_drive_by_its_disk_number_for_both_pages(self) -> None:
        drive = _Drive(_health(), _identify())

        read([Disk(2, "eui.x", "second drive", "NVMe", "SSD")], drive)

        assert drive.asked == [(2, "health"), (2, "identify")]

    def test_a_drive_near_its_warning_temperature_is_a_warning(self) -> None:
        hot = _Drive(_health(composite_k=354 - 3), _identify())

        (finding,) = assess([read([_DISK], hot)]).findings

        assert (finding.severity, finding.title_key) == ("warning", "health.storage.temperature")
        assert finding.limit is not None and finding.limit.value == 81.0

    def test_a_drive_at_its_warning_temperature_is_critical(self) -> None:
        hot = _Drive(_health(composite_k=354), _identify())

        (finding,) = assess([read([_DISK], hot)]).findings

        assert finding.severity == "critical"

    def test_the_drives_own_temperature_flag_is_a_warning_even_when_the_numbers_look_fine(
        self,
    ) -> None:
        flagged = _Drive(_health(warning=0x02), _identify())

        (finding,) = assess([read([_DISK], flagged)]).findings

        assert (finding.severity, finding.title_key) == ("warning", "health.storage.temperature")

    def test_a_drive_that_published_no_warning_temperature_is_a_gap(self) -> None:
        silent = _Drive(_health(), _identify(wctemp_k=0, cctemp_k=0))

        result = assess([read([_DISK], silent)])

        assert result.findings == ()
        assert any(g.source == "nvme" and "publishes no limit" in g.reason for g in result.gaps)

    def test_only_nvme_drives_are_asked(self) -> None:
        sata = Disk(1, "5000C500DEADBEEF", "ST1000DM010", "SATA", "HDD")
        drive = _Drive(_health(), _identify())

        snapshot = read([sata], drive)

        assert drive.asked == []
        assert snapshot.readings == () and snapshot.gaps == ()


class TestTheDrivesOwnWarningFlags:
    def test_a_healthy_drive_raises_none(self) -> None:
        assert read([_DISK], _Drive(_health(), _identify())).findings == ()

    def test_spare_below_threshold_is_critical_with_both_numbers(self) -> None:
        drive = _Drive(_health(warning=0x01, spare=8, threshold=10), _identify())

        (finding,) = read([_DISK], drive).findings

        assert finding.title_key == "health.storage.spare_low"
        assert finding.severity == "critical"
        assert (finding.reading.value, finding.limit.value) == (8.0, 10.0)  # type: ignore[union-attr]
        assert finding.device_id == "eui.0025385A11B2C3D4"

    @pytest.mark.parametrize(
        ("flag", "title"),
        [
            (0x04, "health.storage.reliability_degraded"),
            (0x08, "health.storage.read_only"),
            (0x10, "health.storage.backup_failed"),
        ],
    )
    def test_each_failing_flag_is_its_own_critical_finding(self, flag: int, title: str) -> None:
        (finding,) = read([_DISK], _Drive(_health(warning=flag), _identify())).findings

        assert (finding.title_key, finding.severity) == (title, "critical")

    def test_every_flag_at_once_is_four_findings_and_the_temperature_bit_is_not_one_of_them(
        self,
    ) -> None:
        findings = read([_DISK], _Drive(_health(warning=0x1F), _identify())).findings

        assert sorted(f.title_key for f in findings) == [
            "health.storage.backup_failed",
            "health.storage.read_only",
            "health.storage.reliability_degraded",
            "health.storage.spare_low",
        ]


class TestWhenTheDriveCannotBeRead:
    @pytest.mark.parametrize(
        ("code", "reason"),
        [
            (ERROR_ACCESS_DENIED, NEEDS_ADMIN),
            (1, NOT_EXPOSED),
            (50, NOT_EXPOSED),
            (87, NOT_EXPOSED),
            (-1, NOT_EXPOSED),
        ],
    )
    def test_the_refusal_is_a_named_gap(self, code: int, reason: str) -> None:
        drive = _Drive(b"", b"", NvmeError(code))

        snapshot = read([_DISK], drive)

        assert snapshot.readings == ()
        assert snapshot.gaps == (Gap("nvme", f"SAMSUNG MZVL21T0HCLR-00B00: {reason}"),)

    def test_an_unknown_windows_error_is_shown_as_its_number(self) -> None:
        (gap,) = read([_DISK], _Drive(b"", b"", NvmeError(32))).gaps

        assert "error 32" in gap.reason

    def test_one_unreadable_drive_does_not_hide_the_other(self) -> None:
        class Mixed:
            def query(self, disk_number: int, page: str) -> bytes:
                if disk_number == 0:
                    raise NvmeError(ERROR_ACCESS_DENIED)
                return _health() if page == "health" else _identify()

        second = Disk(1, "eui.2", "second", "NVMe", "SSD")

        snapshot = read([_DISK, second], Mixed())

        assert [r.device_id for r in snapshot.readings] == ["eui.2"]
        assert len(snapshot.gaps) == 1


class _FakeKernel32:
    """Captures the request `WindowsNvme` sends and answers with a canned descriptor."""

    def __init__(self, reply: bytes, *, open_error: int | None = None) -> None:
        self.reply = reply
        self.open_error = open_error
        self.request = b""
        self.opened: list[Any] = []
        self.closed = 0

    def CreateFileW(self, path: str, access: int, share: int, *_rest: Any) -> Any:  # noqa: N802
        self.opened.append((path, access, share))
        return None if self.open_error else 0x1234

    def DeviceIoControl(  # noqa: N802
        self,
        _handle: Any,
        code: int,
        sent: Any,
        sent_size: int,
        out: Any,
        out_size: int,
        returned: Any,
        _o: Any,
    ) -> bool:
        assert code == IOCTL_STORAGE_QUERY_PROPERTY
        self.request = bytes(sent.raw[:sent_size])
        data = self.reply[:out_size]
        ctypes.memmove(out, data, len(data))
        returned._obj.value = len(data)
        return True

    def CloseHandle(self, _handle: Any) -> bool:  # noqa: N802
        self.closed += 1
        return True


def _windows_nvme(kernel32: _FakeKernel32) -> WindowsNvme:
    from ctypes import wintypes

    access = WindowsNvme.__new__(WindowsNvme)
    access._wintypes = wintypes  # type: ignore[attr-defined]
    access._kernel32 = kernel32  # type: ignore[attr-defined]
    return access


class TestTheRequestWindowsReceives:
    def test_the_health_log_request_has_the_pass_through_layout(self) -> None:
        kernel32 = _FakeKernel32(_descriptor(_health()))

        page = _windows_nvme(kernel32).query(0, "health")

        header = struct.unpack_from("<II", kernel32.request, 0)
        specific = struct.unpack_from("<10I", kernel32.request, 8)
        # PropertyId = StorageDeviceProtocolSpecificProperty (50), standard query.
        assert header == (50, 0)
        # ProtocolTypeNvme, NVMeDataTypeLogPage, log page 2, sub value 0, data 40 bytes in,
        # 512 bytes long.
        assert specific[:6] == (3, 2, 2, 0, 40, HEALTH_LOG_BYTES)
        assert page == _health()

    def test_the_identify_request_asks_for_the_controller_structure(self) -> None:
        kernel32 = _FakeKernel32(_descriptor(_identify()))

        _windows_nvme(kernel32).query(0, "identify")

        header = struct.unpack_from("<II", kernel32.request, 0)
        specific = struct.unpack_from("<10I", kernel32.request, 8)
        # StorageAdapterProtocolSpecificProperty (49); NVMeDataTypeIdentify; CNS 1.
        assert header == (49, 0)
        assert specific[:6] == (3, 1, 1, 0, 40, IDENTIFY_BYTES)

    def test_the_drive_is_opened_with_no_access_rights_and_closed_again(self) -> None:
        kernel32 = _FakeKernel32(_descriptor(_health()))

        _windows_nvme(kernel32).query(3, "health")

        assert kernel32.opened == [("\\\\.\\PhysicalDrive3", 0, 3)]
        assert kernel32.closed == 1

    def test_a_drive_that_cannot_be_opened_raises_with_the_windows_error(self) -> None:
        kernel32 = _FakeKernel32(b"", open_error=2)

        with pytest.raises(NvmeError):
            _windows_nvme(kernel32).query(9, "health")


def test_the_pass_through_numbers_are_the_documented_ones() -> None:
    """IOCTL_STORAGE_QUERY_PROPERTY is CTL_CODE(IOCTL_STORAGE_BASE, 0x500, METHOD_BUFFERED, FILE_ANY_ACCESS)."""
    assert nvme.IOCTL_STORAGE_QUERY_PROPERTY == (0x2D << 16) | (0 << 14) | (0x500 << 2) | 0
