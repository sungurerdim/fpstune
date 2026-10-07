"""The thermal source: who is on the machine, a reader for each, one verdict per device.

The one place the readers are wired to the machine. It asks the inventory (cached,
`health.inventory`) which display adapters and which drives exist, runs only the
readers that apply — an AMD reader on an NVIDIA machine is a question that does not
apply, not a gap (C10) — concurrently, and hands the snapshots to `thermal.assess`.

If Windows cannot list the machine's hardware, no vendor reader is guessed at: the
source reports that one gap and nothing else, because "the NVIDIA tool was missing"
and "we did not know there was an NVIDIA card" are different claims.
"""

from __future__ import annotations

from collections.abc import Callable

from fpstune.health import acpi_zone, gpu_amd, gpu_intel, gpu_nvidia, nvme, smartctl
from fpstune.health.inventory import Inventory, inventory
from fpstune.health.model import Gap, SourceResult
from fpstune.health.thermal import Reader, assess, run_readers
from fpstune.utils.gpu_vendor_ids import AMD_VENDOR_ID, INTEL_VENDOR_ID, NVIDIA_VENDOR_ID

SOURCE = "thermal"

NO_INVENTORY = (
    "Windows could not list this machine's drives and graphics adapters, so their "
    "temperatures were not read"
)
READABLE_BUSES = frozenset({nvme.BUS_TYPE}) | smartctl.ATA_BUSES


def _unreadable_drives(inv: Inventory) -> Gap | None:
    """One gap for drives on a bus that exposes no temperature to Windows."""
    names = [d.name or d.unique_id for d in inv.disks if d.bus_type not in READABLE_BUSES]
    if not names:
        return None
    return Gap(
        "storage_temperature",
        "no temperature can be read from "
        + ", ".join(names)
        + ": a USB, RAID or virtual bus does not pass the drive's own sensor through to Windows",
    )


def thermal_source(
    ask_inventory: Callable[[], Inventory] = inventory,
    readers: dict[str, Reader] | None = None,
) -> SourceResult:
    """Findings and gaps from every thermal reader this machine needs.

    `readers` replaces the machine-derived set (tests); the inventory is still asked
    for the drives the storage readers are handed.
    """
    inv = ask_inventory()
    if inv.reason:
        return SourceResult(gaps=(Gap(SOURCE, NO_INVENTORY),))

    if readers is None:
        vendors = inv.vendors()
        chosen: dict[str, Reader] = {}
        if NVIDIA_VENDOR_ID in vendors:
            chosen["nvidia_smi"] = gpu_nvidia.read
        if INTEL_VENDOR_ID in vendors:
            chosen["intel_igcl"] = gpu_intel.read
        if AMD_VENDOR_ID in vendors:
            chosen["amd_adlx"] = gpu_amd.read
        chosen["nvme"] = lambda: nvme.read(inv.disks)
        chosen["smartctl"] = lambda: smartctl.read(inv.disks)
        chosen["acpi_thermal_zone"] = acpi_zone.read
        readers = chosen

    result = assess(run_readers(readers))
    unreadable = _unreadable_drives(inv)
    if unreadable is None:
        return result
    return SourceResult(findings=result.findings, gaps=(*result.gaps, unreadable))
