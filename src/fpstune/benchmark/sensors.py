"""How hot the machine is while it is being measured, without a kernel driver.

Heat is a performance category here, not a comfort one: thermal throttling is how
a frame rate decays, and it arrives in minute forty rather than at the moment of
the tweak. Until now the only temperature fpstune could produce came from FurMark
— a power virus, which answers "how hot under a load nobody plays at" and stays
off the performance path for exactly that reason (C11 rule 6).

What this machine actually exposes, all probed live rather than assumed:

| Source | Needs | What it gives |
|---|---|---|
| `nvidia-smi` on PATH | an NVIDIA driver | GPU temperature and board power, unelevated |
| `Win32_PerfFormattedData_Counters_ThermalZoneInformation` | nothing | ACPI zone temperature and the throttle flags, unelevated, any vendor |
| `MSAcpi_ThermalZoneTemperature` | administrator | refused unelevated here, so it is not used |
| `Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine` | nothing | utilisation only — it carries no temperature at all |

**The vendor gap is stated, not papered over (C10).** GPU temperature and power
come from `nvidia-smi` and therefore only on NVIDIA. AMD and Intel have no
equivalent that runs without a vendor SDK or a ring-0 driver, and
LibreHardwareMonitor — the obvious candidate — documents administrator rights for
its sensors and ships a kernel driver for the ones fpstune would want, which is a
standing red line. On those machines the GPU readings are absent with a reason
and the ACPI zone reading still works, so the panel is never blank and never
guesses. The gap is recorded in `tasks.md`.

**The ACPI zone is in tenths of a kelvin.** `HighPrecisionTemperature` of 3532
is 353.2 K, which is 80.05 °C. Measured moving here across three seconds — 3452,
3512, 3392 — so it is a live reading rather than a fixed trip point, which is the
thing worth checking about any ACPI value.

**One process for the whole window.** The sampling loop runs inside PowerShell,
because a sampler that starts a process a second would be measuring a load it
created itself.
"""

from __future__ import annotations

import time
from typing import Any

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.benchmark.win_query import query_rows
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_WINDOW_SAMPLES = 5
"""Readings per repeat, one a second.

Five seconds is long enough to catch a fan ramp and short enough that the whole
bench is a fraction of a suite run.
"""

SAMPLE_INTERVAL_MS = 1000

_PER_SAMPLE_SECONDS = 2.0
"""What one sample costs on a slow machine: the sleep plus two short queries."""

DECIKELVIN_TO_KELVIN = 10.0
KELVIN_OFFSET = 273.15

NOTHING_SAMPLED = "the sensor window returned nothing to read"
NO_SENSOR = (
    "nothing on this machine reports a temperature without a kernel driver — "
    "an NVIDIA driver supplies one through nvidia-smi, and Windows supplies the "
    "ACPI zones, and neither answered here"
)
NO_GPU_SENSOR = (
    "GPU temperature and power come from nvidia-smi here, which needs an NVIDIA "
    "driver; AMD and Intel have no equivalent that runs without a vendor SDK or "
    "a kernel driver"
)


def build_script(samples: int) -> str:
    """The whole sampling window as one PowerShell expression.

    `nvidia-smi` is resolved once, before the loop, so a machine without it pays
    one lookup rather than one per second. `nounits` is passed because the CSV
    otherwise carries " W" and " C" suffixes that would have to be stripped, and
    stripping a unit is how a number silently changes meaning.
    """
    count = int(samples)
    return (
        "$smi=(Get-Command nvidia-smi -ErrorAction SilentlyContinue); "
        f"1..{count} | ForEach-Object {{ "
        "$t=$null; $p=$null; "
        "if($smi){ $line=@(& $smi.Source --query-gpu=temperature.gpu,power.draw "
        "--format=csv,noheader,nounits 2>$null)[0]; "
        "if($line){ $parts=$line -split ','; "
        "$t=[double]($parts[0].Trim()); $p=[double]($parts[1].Trim()) } }; "
        "$zones=@(Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation "
        "-ErrorAction SilentlyContinue); "
        "[pscustomobject]@{"
        "gpu_temp=$t;"
        "gpu_power=$p;"
        "zone_dk=(($zones | ForEach-Object { $_.HighPrecisionTemperature } "
        "| Measure-Object -Maximum).Maximum);"
        "throttled=(($zones | ForEach-Object { $_.ThrottleReasons } "
        "| Measure-Object -Maximum).Maximum);"
        "nvidia=[bool]$smi"
        "}; "
        f"if($_ -lt {count}){{ Start-Sleep -Milliseconds {SAMPLE_INTERVAL_MS} }} }}"
    )


def celsius_from_decikelvin(value: Any) -> float | None:
    """An ACPI zone reading as degrees Celsius, or None if there was none.

    Windows reports these in tenths of a kelvin: 3532 is 353.2 K is 80.05 °C.
    Absolute zero is not a temperature any machine reports, so a value at or
    below it is a missing reading rather than a cold one.
    """
    if value is None:
        return None
    try:
        kelvin = float(value) / DECIKELVIN_TO_KELVIN
    except (TypeError, ValueError):
        return None
    if kelvin <= 0:
        return None
    return kelvin - KELVIN_OFFSET


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SensorBench:
    """GPU and system temperature over a short window, sampled once a second."""

    key = "sensors"
    label = "Temperature and power"
    requires = "nothing — it reads whatever this machine exposes without a driver"

    def __init__(self, *, window_samples: int = DEFAULT_WINDOW_SAMPLES) -> None:
        if window_samples < 1:
            raise ValueError("a sensor window needs at least one sample")
        self.window_samples = int(window_samples)

    def timeout_seconds(self, repeats: int) -> float:
        return deadline_for(_PER_SAMPLE_SECONDS * self.window_samples, repeats)

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def sample_window(self) -> tuple[list[dict[str, Any]], str]:
        """One window of per-second rows, or an empty list and the reason."""
        budget = int(self.window_samples * _PER_SAMPLE_SECONDS + 15)
        rows, reason = query_rows(
            build_script(self.window_samples), timeout=budget, component="benchmark.sensors"
        )
        if reason:
            return [], reason
        if not rows:
            return [], NOTHING_SAMPLED
        return rows, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        gpu_temp: list[float] = []
        gpu_power: list[float] = []
        zone: list[float] = []
        throttled = False
        nvidia = False
        series: list[dict[str, Any]] = []

        for _ in range(repeats):
            rows, reason = self.sample_window()
            if not rows:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=reason,
                    duration_seconds=time.perf_counter() - started,
                )

            nvidia = nvidia or any(bool(row.get("nvidia")) for row in rows)
            throttled = throttled or any((_number(row.get("throttled")) or 0) > 0 for row in rows)

            temps = [t for t in (_number(row.get("gpu_temp")) for row in rows) if t is not None]
            powers = [p for p in (_number(row.get("gpu_power")) for row in rows) if p is not None]
            zones = [
                z
                for z in (celsius_from_decikelvin(row.get("zone_dk")) for row in rows)
                if z is not None
            ]

            # The peak of each window, not its mean: heat is about the worst the
            # part reached, and averaging a fan ramp with the seconds before it
            # reports a card that never got hot.
            if temps:
                gpu_temp.append(max(temps))
            if powers:
                gpu_power.append(max(powers))
            if zones:
                zone.append(max(zones))
            series.append(
                {
                    "gpu_temp_c": [round(t, 2) for t in temps],
                    "gpu_power_w": [round(p, 2) for p in powers],
                    "thermal_zone_c": [round(z, 2) for z in zones],
                }
            )

        readings: dict[str, BenchReading] = {}
        if gpu_temp:
            readings["gpu_temp_c"] = BenchReading("gpu_temp_c", gpu_temp, "C")
        if gpu_power:
            readings["power_watts"] = BenchReading("power_watts", gpu_power, "W")
        if zone:
            # Vendor-neutral and unelevated, so this is the reading a machine
            # without an NVIDIA driver still gets.
            readings["thermal_zone_c"] = BenchReading(
                "thermal_zone_c", zone, "C", higher_is_better=False
            )

        if not readings:
            return BenchResult(
                bench=self.key,
                label=self.label,
                ran=False,
                reason=NO_SENSOR,
                duration_seconds=time.perf_counter() - started,
            )

        detail: dict[str, Any] = {
            "window_samples": self.window_samples,
            "nvidia_smi": nvidia,
            # Straight from the ACPI zones: a machine that reported a throttle
            # during the window was not measured at its ceiling, and every other
            # reading in the run inherits that.
            "thermal_throttled": throttled,
            "samples": series,
        }
        if not gpu_temp:
            detail["gpu_unmeasured"] = NO_GPU_SENSOR

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail=detail,
            duration_seconds=time.perf_counter() - started,
        )
