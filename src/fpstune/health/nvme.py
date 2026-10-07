"""NVMe: a drive's own temperature, its own warning thresholds, and its own warning flags.

Windows ships the NVMe pass-through in `stornvme.sys`: `IOCTL_STORAGE_QUERY_PROPERTY`
with a protocol-specific query returns the drive's SMART/Health log page and its
Identify Controller data, as the bytes the drive sent. No tool, no kernel driver of
ours, no PowerShell: one `DeviceIoControl` on `\\\\.\\PhysicalDriveN` opened with no
access rights at all. Measured on this machine **without administrator** — the
`Get-StorageReliabilityCounter` route refuses unelevated, this one does not.

Two reads per drive, both fixed layouts from the NVMe specification:

| Page | Offset | Field |
|---|---|---|
| Health log (id 2) | 0 | Critical Warning bit field |
| | 1-2 | Composite Temperature, kelvin |
| | 3, 4 | Available Spare, and its threshold, percent |
| | 5 | Percentage Used |
| | 192-195 / 196-199 | minutes spent over WCTEMP / over CCTEMP |
| Identify Controller (CNS 1) | 266-267 | WCTEMP: warning composite temperature threshold, kelvin |
| | 268-269 | CCTEMP: critical composite temperature threshold, kelvin |

**The limit is WCTEMP.** It is the temperature at which the drive itself says it is too
hot and starts protecting itself; at or over it is `critical` here, in the same sense a
GPU's slowdown temperature is. CCTEMP, the drive's critical threshold, is the
`critical_c` that widens the warning margin (`thermal.margin_c`). A drive that reports
a threshold of 0 published none, and is not judged.

**The drive's own critical-warning flags are findings in their own right.** Bit 0 says
the spare capacity is below the drive's threshold, bit 2 that its reliability is
degraded, bit 3 that it has gone read-only, bit 4 that its volatile memory backup
failed. Each is the drive reporting that it is failing, so each is `critical`. Bit 1,
the temperature flag, is folded into the temperature reading as a throttle reason.

**Layout is read from what the driver returns, not assumed.** The payload offset and
length come from the returned `STORAGE_PROTOCOL_SPECIFIC_DATA`, so a driver that pads
differently is still read right, and a reply too short for the page is a failure
rather than a reading of zeros.
"""

from __future__ import annotations

import ctypes
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from fpstune.health.inventory import Disk
from fpstune.health.model import Finding, Gap, Quantity
from fpstune.health.thermal import ThermalReading, ThermalSnapshot
from fpstune.utils.logger import get_logger

logger = get_logger()

SOURCE = "nvme"
BUS_TYPE = "NVMe"

IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
_ADAPTER_PROTOCOL_SPECIFIC_PROPERTY = 49
_DEVICE_PROTOCOL_SPECIFIC_PROPERTY = 50
_STANDARD_QUERY = 0
_PROTOCOL_TYPE_NVME = 3
_DATA_TYPE_IDENTIFY = 1
_DATA_TYPE_LOG_PAGE = 2
_CNS_CONTROLLER = 1
_LOG_PAGE_HEALTH = 2

_QUERY_HEADER = 8
"""`STORAGE_PROPERTY_QUERY` up to its `AdditionalParameters`: PropertyId and QueryType."""
_SPECIFIC_DATA = 40
"""`STORAGE_PROTOCOL_SPECIFIC_DATA`: ten 32-bit fields."""
_DESCRIPTOR_HEADER = 8
"""`STORAGE_PROTOCOL_DATA_DESCRIPTOR` up to its `ProtocolSpecificData`: Version and Size."""

HEALTH_LOG_BYTES = 512
IDENTIFY_BYTES = 4096

KELVIN_OFFSET = 273.15

ERROR_ACCESS_DENIED = 5
_NOT_SUPPORTED_CODES = frozenset({1, 50, 87})
"""ERROR_INVALID_FUNCTION, ERROR_NOT_SUPPORTED, ERROR_INVALID_PARAMETER: no pass-through here."""

NEEDS_ADMIN = "needs administrator: Windows refused to let this process query the NVMe drive"
NOT_EXPOSED = (
    "the NVMe driver in use does not expose the drive's health log to Windows' own "
    "pass-through, so its temperature cannot be read"
)

# Critical Warning bits (NVMe base spec, SMART / Health Information log, byte 0).
_FLAG_SPARE_LOW = 0x01
_FLAG_TEMPERATURE = 0x02
_FLAG_RELIABILITY = 0x04
_FLAG_READ_ONLY = 0x08
_FLAG_BACKUP_FAILED = 0x10

_FLAG_TITLES = (
    (_FLAG_RELIABILITY, "health.storage.reliability_degraded"),
    (_FLAG_READ_ONLY, "health.storage.read_only"),
    (_FLAG_BACKUP_FAILED, "health.storage.backup_failed"),
)


class NvmeError(Exception):
    """A query the driver refused, with the Windows error code it gave."""

    def __init__(self, code: int) -> None:
        super().__init__(f"Windows error {code}")
        self.code = code


@dataclass(frozen=True)
class NvmeDrive:
    """What one NVMe drive reported about itself."""

    critical_warning: int
    composite_c: float
    spare_percent: int
    spare_threshold_percent: int
    percentage_used: int
    minutes_over_warning: int
    minutes_over_critical: int
    warning_c: float | None
    critical_c: float | None


class NvmeAccess(Protocol):
    def query(self, disk_number: int, page: str) -> bytes:
        """The page's bytes (`"health"` or `"identify"`), or raise `NvmeError`."""
        ...


def _celsius(kelvin: int) -> float | None:
    """Whole kelvin as whole degrees Celsius; 0 means the drive published none."""
    return float(round(kelvin - KELVIN_OFFSET)) if kelvin > 0 else None


def parse_drive(health: bytes, identify: bytes) -> NvmeDrive:
    """The fields above out of the two pages' bytes."""
    if len(health) < HEALTH_LOG_BYTES or len(identify) < 270:
        raise NvmeError(-1)
    composite = struct.unpack_from("<H", health, 1)[0]
    warning, critical = struct.unpack_from("<HH", identify, 266)
    return NvmeDrive(
        critical_warning=health[0],
        composite_c=float(round(composite - KELVIN_OFFSET)),
        spare_percent=health[3],
        spare_threshold_percent=health[4],
        percentage_used=health[5],
        minutes_over_warning=struct.unpack_from("<I", health, 192)[0],
        minutes_over_critical=struct.unpack_from("<I", health, 196)[0],
        warning_c=_celsius(warning),
        critical_c=_celsius(critical),
    )


class WindowsNvme:
    """`DeviceIoControl` against `\\\\.\\PhysicalDriveN`, opened with no access rights."""

    def __init__(self) -> None:
        from ctypes import wintypes

        self._wintypes = wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel32.DeviceIoControl.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32 = kernel32

    def query(self, disk_number: int, page: str) -> bytes:
        if page == "health":
            prop, data_type, value, length = (
                _DEVICE_PROTOCOL_SPECIFIC_PROPERTY,
                _DATA_TYPE_LOG_PAGE,
                _LOG_PAGE_HEALTH,
                HEALTH_LOG_BYTES,
            )
        else:
            prop, data_type, value, length = (
                _ADAPTER_PROTOCOL_SPECIFIC_PROPERTY,
                _DATA_TYPE_IDENTIFY,
                _CNS_CONTROLLER,
                IDENTIFY_BYTES,
            )
        request = struct.pack("<II", prop, _STANDARD_QUERY) + struct.pack(
            "<10I", _PROTOCOL_TYPE_NVME, data_type, value, 0, _SPECIFIC_DATA, length, 0, 0, 0, 0
        )
        request += b"\x00" * length
        reply_size = _DESCRIPTOR_HEADER + _SPECIFIC_DATA + length

        # No access rights, full sharing: a query needs neither, and asking for
        # none is what lets an unelevated process do it.
        handle = self._kernel32.CreateFileW(
            f"\\\\.\\PhysicalDrive{disk_number}", 0, 0x3, None, 0x3, 0, None
        )
        if handle in (None, self._wintypes.HANDLE(-1).value):
            raise NvmeError(ctypes.get_last_error())
        try:
            reply = ctypes.create_string_buffer(reply_size)
            sent = ctypes.create_string_buffer(request, len(request))
            returned = self._wintypes.DWORD(0)
            ok = self._kernel32.DeviceIoControl(
                handle,
                IOCTL_STORAGE_QUERY_PROPERTY,
                sent,
                len(request),
                reply,
                reply_size,
                ctypes.byref(returned),
                None,
            )
            if not ok:
                raise NvmeError(ctypes.get_last_error())
            return payload_of(bytes(reply.raw[: returned.value]))
        finally:
            self._kernel32.CloseHandle(handle)


def payload_of(reply: bytes) -> bytes:
    """The page's bytes out of a `STORAGE_PROTOCOL_DATA_DESCRIPTOR`.

    Offset and length are the ones the driver wrote into the returned
    `STORAGE_PROTOCOL_SPECIFIC_DATA` (its fifth and sixth fields), counted from the start
    of that structure.
    """
    if len(reply) < _DESCRIPTOR_HEADER + _SPECIFIC_DATA:
        raise NvmeError(-1)
    offset, length = struct.unpack_from("<II", reply, _DESCRIPTOR_HEADER + 16)
    start = _DESCRIPTOR_HEADER + offset
    page = reply[start : start + length]
    if len(page) < length or length == 0:
        raise NvmeError(-1)
    return page


def _gap(disk: Disk, reason: str) -> Gap:
    return Gap(SOURCE, f"{disk.name or 'An NVMe drive'}: {reason}")


def _drive_findings(disk: Disk, drive: NvmeDrive) -> list[Finding]:
    device_id = disk.unique_id or None
    findings = []
    if drive.critical_warning & _FLAG_SPARE_LOW:
        findings.append(
            Finding(
                "storage",
                device_id,
                "critical",
                "health.storage.spare_low",
                Quantity(float(drive.spare_percent), "%"),
                Quantity(float(drive.spare_threshold_percent), "%"),
                SOURCE,
            )
        )
    for flag, title in _FLAG_TITLES:
        if drive.critical_warning & flag:
            findings.append(Finding("storage", device_id, "critical", title, None, None, SOURCE))
    return findings


def read(disks: Iterable[Disk], api: NvmeAccess | None = None) -> ThermalSnapshot:
    """Every NVMe drive's temperature against its own WCTEMP, and its own warning flags."""
    nvme = [d for d in disks if d.bus_type == BUS_TYPE]
    if not nvme:
        return ThermalSnapshot()
    try:
        access = api if api is not None else WindowsNvme()
    except (OSError, AttributeError):  # no kernel32 off Windows
        return ThermalSnapshot(gaps=(Gap(SOURCE, NOT_EXPOSED),))

    readings: list[ThermalReading] = []
    findings: list[Finding] = []
    gaps: list[Gap] = []
    for disk in nvme:
        try:
            drive = parse_drive(
                access.query(disk.number, "health"), access.query(disk.number, "identify")
            )
        except NvmeError as exc:
            reason = (
                NEEDS_ADMIN
                if exc.code == ERROR_ACCESS_DENIED
                else NOT_EXPOSED
                if exc.code in _NOT_SUPPORTED_CODES or exc.code == -1
                else f"Windows refused the query (error {exc.code})"
            )
            gaps.append(_gap(disk, reason))
            continue
        readings.append(
            ThermalReading(
                component="storage",
                device_id=disk.unique_id or None,
                name=disk.name,
                temperature_c=drive.composite_c,
                limit_c=drive.warning_c,
                critical_c=drive.critical_c,
                throttle_reasons=("temperature_flag",)
                if drive.critical_warning & _FLAG_TEMPERATURE
                else (),
                limit_source="NVMe WCTEMP",
                source=SOURCE,
            )
        )
        findings.extend(_drive_findings(disk, drive))
    return ThermalSnapshot(readings=tuple(readings), gaps=tuple(gaps), findings=tuple(findings))
