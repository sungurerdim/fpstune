"""The firmware's own thermal zones, against the firmware's own trip points.

`MSAcpi_ThermalZoneTemperature` reports in tenths of a kelvin, needs administrator, and
on some machines publishes a zone with no trip points at all. What this file keeps true:

* tenths of a kelvin are converted once, by the same function `sensors.py` uses, and
  never read as degrees;
* the passive trip point is the limit (that is where Windows starts throttling), the
  critical one only the margin's upper edge — and a zone with only a critical point is
  judged against that;
* a zone with neither is a gap, not a zone judged against a guess;
* a PowerShell refusal in Turkish is a gap in English: the text of a localised error
  is never shown to the user (C4).
"""

from __future__ import annotations

from unittest.mock import patch

from fpstune.health import acpi_zone
from fpstune.health.acpi_zone import NEEDS_ADMIN, NO_ZONES, read, reading_from
from fpstune.health.model import Gap
from fpstune.health.thermal import assess

# 3532 decikelvin is 353.2 K, which is 80.05 C (the conversion `sensors.py` documents).
_ZONE = {
    "instance": "ACPI\\ThermalZone\\TZ00_0",
    "current": 3532,
    "passive": 3682,
    "critical": 3732,
}
_TURKISH_REFUSAL = (
    "Get-CimInstance : Erişim engellendi \r\nSatırda:1 karakter:1\r\n"
    "+ CategoryInfo : PermissionDenied: (root/wmi:MSAcpi_ThermalZoneTemperature:String)"
)


class TestReadingFrom:
    def test_a_zone_is_read_against_its_passive_trip_point_with_the_critical_as_the_ceiling(
        self,
    ) -> None:
        reading = reading_from(_ZONE)

        assert reading is not None
        assert reading.temperature_c == 80.05
        assert (reading.limit_c, reading.critical_c) == (95.05, 100.05)
        assert reading.component == "cpu"
        assert reading.device_id == "ACPI\\ThermalZone\\TZ00_0"

    def test_a_zone_with_only_a_critical_trip_point_is_judged_against_that(self) -> None:
        reading = reading_from(dict(_ZONE, passive=0))

        assert reading is not None
        assert (reading.limit_c, reading.critical_c) == (100.05, None)

    def test_a_zone_with_no_trip_points_has_no_limit(self) -> None:
        reading = reading_from(dict(_ZONE, passive=0, critical=0))

        assert reading is not None and reading.limit_c is None

    def test_a_zone_that_reports_no_temperature_is_not_a_reading(self) -> None:
        assert reading_from(dict(_ZONE, current=0)) is None
        assert reading_from(dict(_ZONE, current=None)) is None


class TestRead:
    def test_a_cool_zone_is_no_finding(self) -> None:
        with patch.object(acpi_zone, "query_rows", return_value=([_ZONE], "")):
            snapshot = read(admin=True)

        assert assess([snapshot]).findings == ()

    def test_a_zone_past_its_passive_trip_point_is_critical_under_the_cpu(self) -> None:
        hot = dict(_ZONE, current=3700)
        with patch.object(acpi_zone, "query_rows", return_value=([hot], "")):
            snapshot = read(admin=True)

        (finding,) = assess([snapshot]).findings

        assert (finding.component, finding.severity, finding.title_key) == (
            "cpu",
            "critical",
            "health.cpu.thermal_zone",
        )

    def test_without_administrator_it_says_so_and_never_starts_powershell(self) -> None:
        with patch.object(acpi_zone, "query_rows", side_effect=AssertionError("asked")):
            snapshot = read(admin=False)

        assert snapshot.gaps == (Gap("acpi_thermal_zone", NEEDS_ADMIN),)

    def test_a_machine_whose_firmware_publishes_no_zone_is_a_gap(self) -> None:
        with patch.object(acpi_zone, "query_rows", return_value=([], "")):
            snapshot = read(admin=True)

        assert snapshot.gaps == (Gap("acpi_thermal_zone", NO_ZONES),)

    def test_a_turkish_refusal_from_powershell_is_an_english_gap(self) -> None:
        """Through the real `query_rows`: the localised text must not reach the reason."""
        with patch(
            "fpstune.benchmark.win_query.run_powershell", return_value=(False, _TURKISH_REFUSAL)
        ):
            (gap,) = read(admin=True).gaps

        assert gap.source == "acpi_thermal_zone"
        assert "Erişim" not in gap.reason
        assert gap.reason.isascii()
