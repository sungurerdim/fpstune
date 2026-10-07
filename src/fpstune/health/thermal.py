"""Is anything on this machine near the temperature its own maker says it should not pass?

Heat is a performance category here (CLAUDE.md consequence 4), and a part close to
its limit is a finding whatever else is true of the machine. The rule is the same
for every component, and it never uses a constant limit:

- **The limit is the device's own.** An NVIDIA driver publishes a slowdown
  temperature (and, on newer ones, the live margin to it); an NVMe drive publishes
  the composite temperature at which it warns (`WCTEMP`) and the one at which it is
  critical (`CCTEMP`); Intel's control library publishes a sensor maximum; an ACPI
  thermal zone publishes its passive and critical trip points; a SATA or hard drive
  publishes its maximum operating temperature through SMART. A reading with no limit
  the device itself gave is **not judged**: it comes back as a gap that says so, and
  fpstune never fills one in from a model name or a table (C1, C11 rule 3).
- **At or over the limit is `critical`; within the margin is `warning`.** A device
  that reports it is already slowing itself down for heat is a `warning` at least,
  even below the limit: the device knows something the temperature alone does not.
- **The margin is derived where the device gives enough to derive it.** The span
  between a device's own two thresholds (an NVIDIA GPU's slowdown and shutdown, an
  NVMe's `WCTEMP` and `CCTEMP`) is how much room it considers the last stretch worth
  warning about; the margin is that span, but never below `NEAR_LIMIT_FLOOR_C`.

**CPU temperature is not read, and is not a gap that can be closed.** A core or
package temperature, and the `TjMax` it would be judged against, are machine-specific
registers that only a ring-0 driver can read, and a kernel driver is a standing red
line. What fpstune measures instead is the *effect*: whether the processor was held
below its own base performance while loaded (`health.throttle`). The one CPU-side
temperature fpstune can read without a driver is an ACPI thermal zone, which is the
firmware's own sensor for a zone of the chassis, judged against that zone's own trip
point — and it needs administrator.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fpstune.health.model import (
    Component,
    Finding,
    Gap,
    Quantity,
    Severity,
    SourceResult,
)
from fpstune.utils.logger import get_logger

logger = get_logger()

NEAR_LIMIT_FLOOR_C = 5.0
"""The least margin below a limit at which a reading becomes a warning.

A constant, because the devices that publish no second threshold give nothing to
derive one from. Five degrees is where three real effects stack: sensors report whole
degrees, so a reading of the limit minus one may be the limit; the sampling is one
reading a second, so the peak between two readings can be higher than either; and a
fan or a boost clock reacts over seconds, so a part five degrees under its limit and
rising is one load step from throttling.
"""

CPU_TEMPERATURE_GAP = (
    "a CPU core or package temperature, and the limit to judge it against, can only "
    "be read with a kernel driver, which fpstune never loads; what a hot CPU does to "
    "performance is measured directly instead"
)

# Which title a device's finding uses: (throttling reported, temperature near limit).
_TITLES: dict[Component, tuple[str | None, str]] = {
    "gpu": ("health.gpu.thermal_throttle", "health.gpu.temperature"),
    "storage": (None, "health.storage.temperature"),
    "cpu": (None, "health.cpu.thermal_zone"),
}


@dataclass(frozen=True)
class ThermalReading:
    """One device's temperature, and the limit its own driver or firmware gave for it."""

    component: Component
    device_id: str | None
    name: str
    temperature_c: float
    limit_c: float | None
    """The device's own throttle or warning point, or None when it published none."""
    critical_c: float | None = None
    """The device's own hard limit (shutdown, `CCTEMP`), when it published one."""
    throttle_reasons: tuple[str, ...] = ()
    """Thermal reasons the device reports as active right now."""
    limit_source: str = ""
    source: str = ""


@dataclass(frozen=True)
class ThermalSnapshot:
    """What one reader produced: readings it could take, and what it could not."""

    readings: tuple[ThermalReading, ...] = ()
    gaps: tuple[Gap, ...] = ()
    findings: tuple[Finding, ...] = ()
    """Findings a reader raises itself: a drive's own critical-warning flags are not a
    temperature against a limit, but they are the device reporting that it is failing."""


def margin_c(reading: ThermalReading) -> float:
    """How close below the limit a warning begins, for this device."""
    if reading.limit_c is not None and reading.critical_c is not None:
        return max(NEAR_LIMIT_FLOOR_C, reading.critical_c - reading.limit_c)
    return NEAR_LIMIT_FLOOR_C


def judge(reading: ThermalReading) -> Finding | None:
    """A finding for a device near, at or over its own limit, or None.

    A throttle reason alone is enough for a warning, with or without a limit: the
    device is saying it is already slowing down. Without a limit and without a
    reason there is nothing to judge — see `unjudged`.
    """
    throttled = bool(reading.throttle_reasons)
    over = reading.limit_c is not None and reading.temperature_c >= reading.limit_c
    near = reading.limit_c is not None and reading.temperature_c >= reading.limit_c - margin_c(
        reading
    )
    if not (throttled or near):
        return None

    throttle_key, temperature_key = _TITLES[reading.component]
    severity: Severity = "critical" if over else "warning"
    return Finding(
        component=reading.component,
        device_id=reading.device_id,
        severity=severity,
        title_key=throttle_key if throttled and throttle_key else temperature_key,
        reading=Quantity(reading.temperature_c, "C"),
        limit=None if reading.limit_c is None else Quantity(reading.limit_c, "C"),
        source=reading.source,
    )


def unjudged(reading: ThermalReading) -> Gap | None:
    """The gap for a device whose temperature is known and whose limit is not."""
    if reading.limit_c is not None or reading.throttle_reasons:
        return None
    label = reading.name or reading.device_id or reading.component
    return Gap(
        source=reading.source,
        reason=(
            f"{label} reports a temperature but publishes no limit to judge it against, "
            "so its heat is not assessed (a limit is never guessed)"
        ),
    )


Reader = Callable[[], ThermalSnapshot]


def assess(snapshots: list[ThermalSnapshot]) -> SourceResult:
    """Findings and gaps from every reader's snapshot, plus the CPU gap that never closes."""
    findings: list[Finding] = []
    gaps: list[Gap] = [Gap(source="cpu_temperature", reason=CPU_TEMPERATURE_GAP)]
    for snapshot in snapshots:
        gaps.extend(snapshot.gaps)
        findings.extend(snapshot.findings)
        for reading in snapshot.readings:
            finding = judge(reading)
            if finding is not None:
                findings.append(finding)
            gap = unjudged(reading)
            if gap is not None:
                gaps.append(gap)
    return SourceResult(findings=tuple(findings), gaps=tuple(gaps))


def run_readers(readers: dict[str, Reader]) -> list[ThermalSnapshot]:
    """Every reader, concurrently; one that raises becomes a gap, not a lost source.

    Each reader waits on a child process or a driver call, so the worker count is
    the reader count and not a core count.
    """

    def ask(name: str, reader: Reader) -> ThermalSnapshot:
        try:
            return reader()
        except Exception as exc:  # noqa: BLE001 - one broken reader must not hide the others
            logger.warning("Thermal reader %s failed: %s", name, exc, exc_info=True)
            return ThermalSnapshot(
                gaps=(Gap(source=name, reason=f"the reading failed ({type(exc).__name__})"),)
            )

    if not readers:
        return []
    with ThreadPoolExecutor(max_workers=len(readers)) as pool:
        futures = [pool.submit(ask, name, reader) for name, reader in readers.items()]
        return [future.result() for future in futures]
