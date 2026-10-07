"""A part near the limit its own maker published is a finding; one with no limit is a gap.

The rule is the same for a graphics card, an NVMe drive and an ACPI zone, so it is
tested once, here, with the readings each reader produces:

* a reading well under its limit is **no finding** — a healthy machine is an empty list;
* within the margin is a **warning**, at or over the limit is **critical**;
* a device that says it is already throttling for heat is a warning even below the limit;
* a temperature with **no limit the device itself gave** is never judged and never
  guessed at — it comes back as a gap that says so (C11 rule 3);
* CPU temperature is not read, and that gap is always on the record.
"""

from __future__ import annotations

import pytest

from fpstune.health.model import Finding, Gap, Quantity
from fpstune.health.thermal import (
    CPU_TEMPERATURE_GAP,
    NEAR_LIMIT_FLOOR_C,
    ThermalReading,
    ThermalSnapshot,
    assess,
    judge,
    margin_c,
    run_readers,
    unjudged,
)


def _gpu(temperature: float, **overrides: object) -> ThermalReading:
    fields: dict[str, object] = {
        "component": "gpu",
        "device_id": "PCI\\VEN_10DE&DEV_249D",
        "name": "NVIDIA GeForce RTX 3070 Laptop GPU",
        "temperature_c": temperature,
        "limit_c": 98.0,
        "critical_c": 101.0,
        "source": "nvidia_smi",
    }
    fields.update(overrides)
    return ThermalReading(**fields)  # type: ignore[arg-type]


class TestTheMargin:
    def test_the_span_between_the_devices_own_thresholds_is_the_margin_when_wide(self) -> None:
        wide = _gpu(60, limit_c=80.0, critical_c=95.0)

        assert margin_c(wide) == 15.0

    def test_a_narrow_span_never_shrinks_the_margin_below_the_floor(self) -> None:
        """The GPU's own slowdown and shutdown are three degrees apart: too tight to act on."""
        assert margin_c(_gpu(60)) == NEAR_LIMIT_FLOOR_C

    def test_a_device_with_one_threshold_uses_the_floor(self) -> None:
        assert margin_c(_gpu(60, critical_c=None)) == NEAR_LIMIT_FLOOR_C


class TestJudge:
    def test_a_card_well_under_its_slowdown_point_is_not_a_finding(self) -> None:
        assert judge(_gpu(65)) is None

    def test_one_degree_outside_the_margin_is_still_not_a_finding(self) -> None:
        assert judge(_gpu(98.0 - NEAR_LIMIT_FLOOR_C - 1)) is None

    def test_the_first_degree_inside_the_margin_is_a_warning(self) -> None:
        finding = judge(_gpu(98.0 - NEAR_LIMIT_FLOOR_C))

        assert finding is not None
        assert finding.severity == "warning"
        assert finding.title_key == "health.gpu.temperature"

    def test_at_the_limit_is_critical(self) -> None:
        assert judge(_gpu(98.0)) == Finding(
            component="gpu",
            device_id="PCI\\VEN_10DE&DEV_249D",
            severity="critical",
            title_key="health.gpu.temperature",
            reading=Quantity(98.0, "C"),
            limit=Quantity(98.0, "C"),
            source="nvidia_smi",
        )

    def test_over_the_limit_is_critical(self) -> None:
        finding = judge(_gpu(104))

        assert finding is not None
        assert finding.severity == "critical"

    def test_a_card_slowing_itself_down_for_heat_is_a_warning_even_well_under_the_limit(
        self,
    ) -> None:
        finding = judge(_gpu(70, throttle_reasons=("hw_thermal_slowdown",)))

        assert finding is not None
        assert (finding.severity, finding.title_key) == ("warning", "health.gpu.thermal_throttle")
        assert finding.limit == Quantity(98.0, "C")

    def test_throttling_at_the_limit_is_critical(self) -> None:
        finding = judge(_gpu(98, throttle_reasons=("sw_thermal_slowdown",)))

        assert finding is not None
        assert finding.severity == "critical"

    def test_throttling_with_no_published_limit_is_still_a_warning_without_a_limit(self) -> None:
        finding = judge(
            _gpu(70, limit_c=None, critical_c=None, throttle_reasons=("hw_thermal_slowdown",))
        )

        assert finding is not None
        assert finding.limit is None
        assert finding.severity == "warning"

    def test_a_drive_near_its_own_warning_temperature_is_a_storage_finding(self) -> None:
        drive = ThermalReading(
            component="storage",
            device_id="eui.0025385A11B2C3D4",
            name="NVMe drive",
            temperature_c=78.0,
            limit_c=81.0,
            critical_c=85.0,
            source="nvme",
        )

        finding = judge(drive)

        assert finding is not None
        assert (finding.component, finding.severity, finding.title_key) == (
            "storage",
            "warning",
            "health.storage.temperature",
        )

    def test_an_acpi_zone_is_filed_under_the_cpu(self) -> None:
        zone = ThermalReading(
            component="cpu",
            device_id="ACPI\\ThermalZone\\TZ00_0",
            name="zone",
            temperature_c=96.0,
            limit_c=95.0,
            source="acpi_thermal_zone",
        )

        finding = judge(zone)

        assert finding is not None
        assert (finding.component, finding.severity, finding.title_key) == (
            "cpu",
            "critical",
            "health.cpu.thermal_zone",
        )


class TestAReadingWithNoLimitIsAGapNotAGuess:
    def test_a_temperature_with_no_published_limit_is_not_judged(self) -> None:
        hot_but_unlimited = _gpu(104, limit_c=None, critical_c=None)

        assert judge(hot_but_unlimited) is None

    def test_and_the_gap_names_the_device_and_says_nothing_was_guessed(self) -> None:
        gap = unjudged(_gpu(104, limit_c=None, critical_c=None))

        assert gap is not None
        assert gap.source == "nvidia_smi"
        assert "NVIDIA GeForce RTX 3070 Laptop GPU" in gap.reason
        assert "never guessed" in gap.reason

    def test_a_device_with_a_limit_has_no_gap(self) -> None:
        assert unjudged(_gpu(65)) is None

    def test_a_throttling_device_with_no_limit_is_judged_so_it_has_no_gap(self) -> None:
        reading = _gpu(70, limit_c=None, critical_c=None, throttle_reasons=("hw_thermal_slowdown",))

        assert unjudged(reading) is None


class TestAssess:
    def test_the_cpu_gap_is_always_on_the_record_even_on_a_cool_machine(self) -> None:
        result = assess([ThermalSnapshot(readings=(_gpu(65),))])

        assert result.findings == ()
        assert result.gaps == (Gap("cpu_temperature", CPU_TEMPERATURE_GAP),)

    def test_the_gap_says_why_and_that_throttling_is_measured_instead(self) -> None:
        assert "kernel driver" in CPU_TEMPERATURE_GAP
        assert "measured directly" in CPU_TEMPERATURE_GAP

    def test_findings_gaps_and_reader_findings_are_all_carried(self) -> None:
        own = Finding(
            "storage", "eui.1", "critical", "health.storage.read_only", None, None, "nvme"
        )
        result = assess(
            [
                ThermalSnapshot(readings=(_gpu(99),)),
                ThermalSnapshot(gaps=(Gap("amd_adlx", "no limit"),), findings=(own,)),
            ]
        )

        assert sorted(f.title_key for f in result.findings) == [
            "health.gpu.temperature",
            "health.storage.read_only",
        ]
        assert [g.source for g in result.gaps] == ["cpu_temperature", "amd_adlx"]


class TestRunReaders:
    def test_a_reader_that_raises_is_a_named_gap_and_the_others_still_answer(self) -> None:
        def broken() -> ThermalSnapshot:
            raise OSError("the driver call failed")

        snapshots = run_readers(
            {"broken": broken, "fine": lambda: ThermalSnapshot(readings=(_gpu(65),))}
        )

        assert [s.gaps for s in snapshots] == [
            (Gap("broken", "the reading failed (OSError)"),),
            (),
        ]
        assert len(snapshots[1].readings) == 1

    def test_no_readers_is_no_snapshots(self) -> None:
        assert run_readers({}) == []


@pytest.mark.parametrize("temperature", [0.0, -5.0])
def test_a_reading_below_zero_is_just_cold_and_judged_like_any_other(temperature: float) -> None:
    assert judge(_gpu(temperature)) is None
