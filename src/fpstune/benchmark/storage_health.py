"""What the drive says about its own wear, read from the drive.

Two claims in the registry are about a disk lasting longer — `ssd_writes` and
`ssd_longevity` — and `sources.py` refused both for the same reason: *"needs
write volume accumulated over weeks"*, *"measured in years of endurance, which no
run observes"*. That reasoning was right about the round and wrong about the
machine. The drive has been counting for years already: every NVMe and every SATA
SSD keeps a wear figure, a power-on hour count and an error tally, and
`Get-StorageReliabilityCounter` reads them without a vendor tool.

What it closes, and what it does not:

*`ssd_longevity` is answered as life remaining, not as wear used.* The counter
reports the share of the drive's rated endurance already spent; the claim is
about how much is left, and a claim that goes up must be measured by a number
that goes up, or a verdict reads backwards. `100 - wear` is the same measurement
stated the way the claim states it.

*`ssd_writes` is not answered here, and stays on the record as a gap.* This
cmdlet reports wear and errors, not host writes — CrystalDiskInfo's "Total Host
Writes" comes from a SMART attribute this path does not expose. Wear is a
consequence of writes and not a count of them, and mapping one to the other
would be exactly the loose mapping `sources.py` exists to refuse.

*The reading is the worst drive, not an average.* A machine with a five-year-old
boot drive and a new games drive has one drive close to its end, and averaging
the two would hide it. Every drive's own figures are in `detail`, keyed by
`UniqueId` (C5) rather than by the order Windows happened to enumerate them.

**This needs administrator.** Measured unelevated on the machine this was written
on, the cmdlet answers `PermissionDenied` for every drive — so the bench says
`needs administrator` before running rather than reporting a machine with no
drives.
"""

from __future__ import annotations

import time
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.utils.admin import is_admin
from fpstune.utils.logger import get_logger

logger = get_logger()

NEEDS_ADMIN = "needs administrator: only an elevated process may read a drive's own counters"
NO_COUNTERS = (
    "no drive here reports reliability counters — a USB bridge or a RAID "
    "controller can hide them from Windows entirely"
)

_QUERY_SECONDS = 10.0
"""What one pass costs on a machine with several drives, per repeat."""

FULL_LIFE_PERCENT = 100.0
"""What a drive with nothing spent would report as life remaining."""

# One invocation, every drive. `Get-StorageReliabilityCounter` is asked per disk
# because that is the only shape it takes; the loop stays inside PowerShell so
# the cost is one process rather than one per drive.
SCRIPT = (
    "Get-PhysicalDisk | ForEach-Object { "
    "$disk=$_; "
    "$c=$disk | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
    "if($c){ [pscustomobject]@{"
    "unique_id=$disk.UniqueId;"
    "media_type=[string]$disk.MediaType;"
    "bus_type=[string]$disk.BusType;"
    "size_bytes=$disk.Size;"
    "wear=$c.Wear;"
    "power_on_hours=$c.PowerOnHours;"
    "temperature=$c.Temperature;"
    "read_errors=$c.ReadErrorsTotal;"
    "write_errors=$c.WriteErrorsTotal;"
    "start_stop_cycles=$c.StartStopCycleCount"
    "} } }"
)


def _number(value: Any) -> float | None:
    """A counter's value, or None when the drive does not report it.

    None and zero are different answers and the difference matters: a drive that
    reports no wear figure has not told us it is unworn.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class StorageHealthBench:
    """Wear, temperature and error counts, read off every drive that reports them."""

    key = "storage_health"
    label = "Drive health"
    requires = "administrator rights, so Windows will read the drive's own counters"

    def timeout_seconds(self, repeats: int) -> float:
        return deadline_for(_QUERY_SECONDS, repeats)

    def is_available(self) -> tuple[bool, str]:
        if not is_admin():
            return False, NEEDS_ADMIN
        return True, ""

    def sample(self) -> tuple[list[dict[str, Any]], str]:
        """Every drive's counters, or an empty list and the reason."""
        rows, reason = query_rows(SCRIPT, timeout=45, component="benchmark.storage_health")
        if reason:
            return [], reason
        if not rows:
            return [], NO_COUNTERS
        return rows, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        # Asked again here rather than trusted from `is_available`. The cmdlet's
        # refusal is indistinguishable from a machine whose drives hide their
        # counters, so a caller that ran this directly would be told the drives
        # report nothing when the truth is that this process may not ask.
        available, why = self.is_available()
        if not available:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=why,
                duration_seconds=time.perf_counter() - started,
            )

        life: list[float] = []
        hottest: list[float] = []
        errors: list[float] = []
        drives: list[dict[str, Any]] = []

        for _ in range(repeats):
            rows, reason = self.sample()
            if not rows:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=reason,
                    duration_seconds=time.perf_counter() - started,
                )
            drives = rows

            wears = [w for w in (_number(row.get("wear")) for row in rows) if w is not None]
            if wears:
                # The worst drive, because that is the one that will fail first.
                life.append(FULL_LIFE_PERCENT - max(wears))

            temps = [t for t in (_number(row.get("temperature")) for row in rows) if t is not None]
            if temps:
                hottest.append(max(temps))

            faults = [
                value
                for row in rows
                for value in (_number(row.get("read_errors")), _number(row.get("write_errors")))
                if value is not None
            ]
            if faults:
                # A sum across drives and across directions: these are counts of
                # the same kind of event, and one machine-wide fault count is
                # what a user is asking about.
                errors.append(sum(faults))

        readings: dict[str, BenchReading] = {}
        if life:
            readings["ssd_longevity"] = BenchReading("ssd_longevity", life, "% remaining")
        if hottest:
            readings["storage_temp_c"] = BenchReading(
                "storage_temp_c", hottest, "C", higher_is_better=False
            )
        if errors:
            readings["storage_error_count"] = BenchReading(
                "storage_error_count", errors, "errors", higher_is_better=False
            )

        if not readings:
            # Drives answered, and none of them reported a figure worth reading.
            # That is a reading of nothing, which is `ran=False` with a reason.
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=(
                    "the drives here report no wear, temperature or error counters, "
                    "so there is nothing to compare"
                ),
                detail={"drives": _describe(drives)},
                duration_seconds=time.perf_counter() - started,
            )

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail={"drives": _describe(drives)},
            duration_seconds=time.perf_counter() - started,
        )


def _describe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-drive facts, kept out of the comparable readings.

    Power-on hours belong here rather than beside `ssd_longevity`: a drive gets
    older whatever fpstune does, so an hour count that rises between two runs is
    not a regression and must never be offered to a comparison as one.
    """
    described = []
    for row in rows:
        described.append(
            {
                # `UniqueId` rather than a friendly name or an enumeration order:
                # C5's rule, and the only key that survives a drive being moved
                # to another port.
                "unique_id": str(row.get("unique_id") or ""),
                "media_type": str(row.get("media_type") or ""),
                "bus_type": str(row.get("bus_type") or ""),
                "size_bytes": _number(row.get("size_bytes")),
                "wear_percent": _number(row.get("wear")),
                "power_on_hours": _number(row.get("power_on_hours")),
                "temperature_c": _number(row.get("temperature")),
                "read_errors": _number(row.get("read_errors")),
                "write_errors": _number(row.get("write_errors")),
                "start_stop_cycles": _number(row.get("start_stop_cycles")),
            }
        )
    return described
