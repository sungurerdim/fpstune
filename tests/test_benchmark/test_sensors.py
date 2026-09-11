"""Tenths of a kelvin, a vendor gap, and the peak that averaging hides.

Three things this file exists to keep true.

*The ACPI zone is not degrees.* Windows reports `HighPrecisionTemperature` in
tenths of a kelvin, so 3532 is 80.05 °C. Read as Celsius it is a temperature no
machine has ever survived; read as kelvin without the tenths it is 3259 °C. Both
mistakes produce a number that looks like a reading.

*A window's peak is the reading, not its mean.* Heat is about the worst the part
reached — that is what throttles — and averaging the fan ramp with the quiet
seconds before it reports a card that never got hot.

*A machine without an NVIDIA driver still gets an answer.* GPU temperature comes
from `nvidia-smi` here, which is one vendor (C10). The ACPI zone reading is
vendor-neutral and unelevated, so the bench reports what it has and names what it
does not, rather than reporting nothing on two thirds of the machines out there.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.sensors import (
    NO_GPU_SENSOR,
    NO_SENSOR,
    NOTHING_SAMPLED,
    SensorBench,
    build_script,
    celsius_from_decikelvin,
)
from fpstune.benchmark.suite import Bench

# One second of sampling, in the shape the script returns. The values are this
# machine's own readings, passed in as fixture input (C9).
_SECOND: dict[str, Any] = {
    "gpu_temp": 56.0,
    "gpu_power": 22.12,
    "zone_dk": 3532,
    "throttled": 0,
    "nvidia": True,
}


def _second(**overrides: Any) -> dict[str, Any]:
    row = dict(_SECOND)
    row.update(overrides)
    return row


def _run(rows: list[dict[str, Any]], repeats: int = 2):
    with patch("fpstune.benchmark.sensors.query_rows", return_value=(rows, "")):
        return SensorBench(window_samples=len(rows)).run(repeats)


class TestTheAcpiZoneIsInTenthsOfAKelvin:
    def test_thirty_five_thirty_two_is_eighty_degrees(self) -> None:
        assert celsius_from_decikelvin(3532) == pytest.approx(80.05, abs=0.01)

    def test_a_zone_that_reported_nothing_is_not_absolute_zero(self) -> None:
        """Zero decikelvin is a missing reading, not a very cold machine."""
        assert celsius_from_decikelvin(0) is None
        assert celsius_from_decikelvin(None) is None

    def test_the_reading_reaches_the_bench_in_celsius(self) -> None:
        result = _run([_second(zone_dk=3532)])

        assert result.readings["thermal_zone_c"].median == pytest.approx(80.05, abs=0.01)
        assert result.readings["thermal_zone_c"].unit == "C"


class TestThePeakIsTheReading:
    def test_a_fan_ramp_is_not_averaged_away(self) -> None:
        """72, 74, 89 is a card that reached 89, not one that sat at 78."""
        result = _run(
            [_second(gpu_temp=72.0), _second(gpu_temp=74.0), _second(gpu_temp=89.0)],
            repeats=2,
        )

        assert result.readings["gpu_temp_c"].median == pytest.approx(89.0)

    def test_hotter_is_the_regression(self) -> None:
        assert _run([_second()]).readings["gpu_temp_c"].improves_upward is False

    def test_more_power_is_the_regression_too(self) -> None:
        assert _run([_second()]).readings["power_watts"].improves_upward is False

    def test_every_second_of_the_window_stays_on_the_record(self) -> None:
        result = _run([_second(gpu_temp=72.0), _second(gpu_temp=89.0)])

        assert result.detail["samples"][0]["gpu_temp_c"] == [72.0, 89.0]


class TestAMachineWithoutTheVendorToolStillAnswers:
    def test_the_acpi_zone_carries_a_machine_with_no_nvidia_driver(self) -> None:
        """C10: two thirds of machines are not NVIDIA."""
        result = _run([_second(gpu_temp=None, gpu_power=None, nvidia=False)])

        assert result.ran
        assert "gpu_temp_c" not in result.readings
        assert result.readings["thermal_zone_c"].median == pytest.approx(80.05, abs=0.01)
        assert result.detail["gpu_unmeasured"] == NO_GPU_SENSOR

    def test_a_machine_with_no_sensor_at_all_says_so(self) -> None:
        result = _run([_second(gpu_temp=None, gpu_power=None, zone_dk=None, nvidia=False)])

        assert not result.ran
        assert result.reason == NO_SENSOR

    def test_a_throttle_during_the_window_is_recorded(self) -> None:
        """Every other reading in that run was taken below the ceiling."""
        result = _run([_second(throttled=0), _second(throttled=2)])

        assert result.detail["thermal_throttled"] is True

    def test_an_unthrottled_window_says_so_too(self) -> None:
        assert _run([_second(throttled=0)]).detail["thermal_throttled"] is False


class TestWhatItCannotSample:
    def test_a_failed_query_carries_its_own_reason(self) -> None:
        with patch(
            "fpstune.benchmark.sensors.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = SensorBench(window_samples=2).run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"

    def test_an_empty_window_is_a_failure_not_a_cold_machine(self) -> None:
        with patch("fpstune.benchmark.sensors.query_rows", return_value=([], "")):
            result = SensorBench(window_samples=2).run(2)

        assert not result.ran
        assert result.reason == NOTHING_SAMPLED

    def test_a_window_needs_at_least_one_sample(self) -> None:
        with pytest.raises(ValueError):
            SensorBench(window_samples=0)


class TestTheScriptReadsWhatThisMachineExposes:
    def test_it_asks_nvidia_smi_without_units(self) -> None:
        """A stripped " W" suffix is how a number changes meaning silently."""
        script = build_script(3)

        assert "--query-gpu=temperature.gpu,power.draw" in script
        assert "nounits" in script

    def test_it_reads_the_acpi_zone_that_needs_no_administrator(self) -> None:
        """`MSAcpi_ThermalZoneTemperature` was refused unelevated on this machine."""
        script = build_script(3)

        assert "Win32_PerfFormattedData_Counters_ThermalZoneInformation" in script
        assert "MSAcpi_ThermalZoneTemperature" not in script

    def test_the_vendor_tool_is_resolved_once_for_the_whole_window(self) -> None:
        """A sampler that starts a process a second measures a load it made."""
        script = build_script(5)

        assert script.count("Get-Command nvidia-smi") == 1
        assert "1..5 |" in script

    def test_it_satisfies_the_bench_protocol(self) -> None:
        assert isinstance(SensorBench(), Bench)

    def test_the_deadline_covers_the_sleeps_it_asked_for(self) -> None:
        bench = SensorBench(window_samples=10)

        assert bench.timeout_seconds(3) > 10 * 3
