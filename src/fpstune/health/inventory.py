"""Which drives and which display adapters this machine has, asked once.

The thermal readers need to know who is on the machine before they ask anyone:
the NVMe reader needs each disk's number to open `\\\\.\\PhysicalDriveN` and its
`UniqueId` to name it (C5); the GPU readers should only run for a vendor that has an
adapter here, because "no AMD library found" on an NVIDIA-only machine is not a gap
but a question that does not apply (C10: not-applicable is a first-class answer).

One PowerShell call returns both lists. It is session-stable data (C7), so it is
cached for `CACHE_SECONDS` and not asked on every health poll; five minutes is the
monitor cache's own lifetime and covers a drive being plugged in during a session.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from fpstune.benchmark.win_query import query_rows
from fpstune.health.model import stable_pci_id
from fpstune.utils.gpu_vendor_ids import vendor_id_of

CACHE_SECONDS = 300.0

# `DeviceId` of a physical disk is its disk number, which is also the N of
# `\\.\PhysicalDriveN`; `UniqueId` is the EUI-64 or serial C5 names. `BusType` and
# `MediaType` are enumeration names, which Windows does not translate.
SCRIPT = (
    "@(Get-PhysicalDisk | ForEach-Object { [pscustomobject]@{"
    "kind='disk';"
    "number=[string]$_.DeviceId;"
    "unique_id=[string]$_.UniqueId;"
    "name=[string]$_.FriendlyName;"
    "bus_type=[string]$_.BusType;"
    "media_type=[string]$_.MediaType"
    "} }) + "
    "@(Get-CimInstance Win32_VideoController | ForEach-Object { [pscustomobject]@{"
    "kind='adapter';"
    "name=[string]$_.Name;"
    "pnp=[string]$_.PNPDeviceID"
    "} })"
)


@dataclass(frozen=True)
class Disk:
    number: int
    unique_id: str
    name: str
    bus_type: str
    media_type: str


@dataclass(frozen=True)
class Adapter:
    name: str
    pnp_device_id: str

    @property
    def vendor_id(self) -> str | None:
        return vendor_id_of(self.pnp_device_id)

    @property
    def stable_id(self) -> str | None:
        return stable_pci_id(self.pnp_device_id)


@dataclass(frozen=True)
class Inventory:
    disks: tuple[Disk, ...] = ()
    adapters: tuple[Adapter, ...] = ()
    reason: str = ""
    """Why the lists are empty when Windows could not be asked. Empty when it could."""

    def vendors(self) -> set[str]:
        return {a.vendor_id for a in self.adapters if a.vendor_id}


def _disk(row: dict[str, object]) -> Disk | None:
    try:
        number = int(str(row.get("number", "")))
    except ValueError:
        return None
    return Disk(
        number=number,
        unique_id=str(row.get("unique_id") or ""),
        name=str(row.get("name") or ""),
        bus_type=str(row.get("bus_type") or ""),
        media_type=str(row.get("media_type") or ""),
    )


def parse(rows: list[dict[str, object]]) -> Inventory:
    """The two lists out of the one query's rows."""
    disks = [d for r in rows if r.get("kind") == "disk" and (d := _disk(r))]
    adapters = [
        Adapter(name=str(r.get("name") or ""), pnp_device_id=str(r.get("pnp") or ""))
        for r in rows
        if r.get("kind") == "adapter"
    ]
    return Inventory(disks=tuple(disks), adapters=tuple(adapters))


def read() -> Inventory:
    """Ask Windows now."""
    rows, reason = query_rows(SCRIPT, component="health.inventory")
    if reason:
        return Inventory(reason=reason)
    return parse(rows)


_lock = threading.Lock()
_cached: tuple[float, Inventory] | None = None


def reset_cache() -> None:
    global _cached
    with _lock:
        _cached = None


def inventory(
    *,
    ask: Callable[[], Inventory] = read,
    clock: Callable[[], float] = time.monotonic,
) -> Inventory:
    """The machine's drives and adapters, cached; a failed read is never cached."""
    global _cached
    with _lock:
        if _cached is not None and clock() - _cached[0] < CACHE_SECONDS:
            return _cached[1]
        answer = ask()
        if not answer.reason:
            _cached = (clock(), answer)
        return answer
