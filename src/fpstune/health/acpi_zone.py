"""ACPI thermal zones: the firmware's own temperature, against the firmware's own trip points.

`MSAcpi_ThermalZoneTemperature` (WMI, `root/wmi`) is the one place Windows publishes
what the platform firmware says about its thermal zones, and it publishes the zone's
limits with the reading: `PassiveTripPoint` is the temperature at which Windows starts
throttling the zone's processors (passive cooling), `CriticalTripPoint` the one at
which it shuts the machine down. All three are in tenths of a kelvin.

**A zone is not a core.** It is the firmware's sensor for part of the chassis, often
the area around the processor and sometimes not; it is no substitute for the package or
core temperature a kernel driver could read, and it is reported as what it is, a
thermal zone, under the CPU heading because the processors are what its passive trip
point throttles. A zone that publishes neither trip point is not judged.

**Administrator only.** Measured unelevated on the development machine, the class is
refused, which is why `sensors.py` reads the vendor-neutral performance-counter class
instead. This reader names that as a gap rather than trying and reporting a failure.
"""

from __future__ import annotations

from fpstune.benchmark.sensors import celsius_from_decikelvin
from fpstune.benchmark.win_query import query_rows
from fpstune.health.model import Gap
from fpstune.health.thermal import ThermalReading, ThermalSnapshot
from fpstune.utils.admin import is_admin

SOURCE = "acpi_thermal_zone"
NEEDS_ADMIN = (
    "needs administrator: Windows only lets an elevated process read the ACPI thermal "
    "zones' trip points, so the platform's own thermal limits are not read"
)
NO_ZONES = "this machine's firmware publishes no ACPI thermal zone"

SCRIPT = (
    "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
    "-ErrorAction Stop | ForEach-Object { [pscustomobject]@{"
    "instance=[string]$_.InstanceName;"
    "current=$_.CurrentTemperature;"
    "passive=$_.PassiveTripPoint;"
    "critical=$_.CriticalTripPoint"
    "} }"
)


def _celsius(decikelvin: object) -> float | None:
    """Tenths of a kelvin as degrees to the 0.05 the unit can express, or None."""
    celsius = celsius_from_decikelvin(decikelvin)
    return None if celsius is None else round(celsius, 2)


def reading_from(row: dict[str, object]) -> ThermalReading | None:
    """A zone's reading against its own trip points, or None when it reported no temperature."""
    current = _celsius(row.get("current"))
    if current is None:
        return None
    passive = _celsius(row.get("passive"))
    critical = _celsius(row.get("critical"))
    # The passive trip point is where the OS starts throttling; a zone with only a
    # critical one has no earlier limit than that to be judged against.
    limit = passive if passive is not None else critical
    return ThermalReading(
        component="cpu",
        device_id=str(row.get("instance") or "") or None,
        name=str(row.get("instance") or "ACPI thermal zone"),
        temperature_c=current,
        limit_c=limit,
        critical_c=critical if passive is not None else None,
        limit_source="ACPI passive trip point"
        if passive is not None
        else "ACPI critical trip point",
        source=SOURCE,
    )


def read(*, admin: bool | None = None) -> ThermalSnapshot:
    """Every ACPI thermal zone against its own trip points."""
    if not (is_admin() if admin is None else admin):
        return ThermalSnapshot(gaps=(Gap(SOURCE, NEEDS_ADMIN),))
    rows, reason = query_rows(SCRIPT, component="health.acpi_zone")
    if reason:
        return ThermalSnapshot(gaps=(Gap(SOURCE, reason),))
    readings = [r for r in (reading_from(row) for row in rows) if r is not None]
    if not readings:
        return ThermalSnapshot(gaps=(Gap(SOURCE, NO_ZONES),))
    return ThermalSnapshot(readings=tuple(readings))
