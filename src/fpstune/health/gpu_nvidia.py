"""NVIDIA: temperature, the driver's own slowdown limit, and why the clocks are held.

`nvidia-smi -q -x` is one call (0.15 s measured here) that carries everything a heat
check needs, in tags that are the same on every Windows language:

| Tag | Meaning |
|---|---|
| `temperature/gpu_temp` | current temperature, `64 C` |
| `temperature/gpu_temp_tlimit` | live margin to the slowdown point, `N/A` on drivers and boards that do not report it (this machine's) |
| `temperature/gpu_temp_slow_threshold` | the temperature at which the driver slows the GPU down — the limit judged against |
| `temperature/gpu_temp_max_threshold` | the temperature at which the GPU shuts itself down |
| `clocks_event_reasons/clocks_event_reason_*` | why the clocks are below their ceiling right now |
| `pci/pci_device_id` | `249D10DE`: device id in the high half, vendor id in the low half |

The CSV query fields (`--query-gpu=temperature.gpu.tlimit,...`) carry the margin and the
reasons but not the slowdown or shutdown thresholds, which are not query fields; the
XML carries all of them in one process start, so the XML is what is read.

**The limit is the driver's, in this order.** The live margin to slowdown when the board
reports one (`limit = temperature + margin`); otherwise the slowdown threshold; with
neither the GPU is not judged and the reader says so. `N/A` is never read as zero.

**Only the thermal reasons count as heat.** `hw_thermal_slowdown` and
`sw_thermal_slowdown` mean the GPU is slowing itself down for temperature.
`sw_power_cap` is the power governor doing its job at full load on every card, and
`hw_slowdown` alone cannot be told apart from an external power brake; neither is
heat, so neither is a thermal finding. `health.throttle` reads all of them.
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET  # noqa: S405 - the text is our own nvidia-smi's output
from collections.abc import Callable
from dataclasses import dataclass

from fpstune.health.model import Gap
from fpstune.health.thermal import ThermalReading, ThermalSnapshot
from fpstune.utils import process_watch
from fpstune.utils.logger import get_logger
from fpstune.utils.system_tools import nvidia_smi

logger = get_logger()

SOURCE = "nvidia_smi"

RunSmi = Callable[[], tuple[str, str]]
"""What `run_smi` is: nothing in, `(xml, reason)` out. Tests pass their own."""

NO_SMI = (
    "this machine has an NVIDIA adapter but no nvidia-smi.exe, so its temperature and "
    "slowdown limit cannot be read"
)
SMI_FAILED = "nvidia-smi did not answer, so the NVIDIA GPU's temperature cannot be read"

THERMAL_REASONS = frozenset({"hw_thermal_slowdown", "sw_thermal_slowdown"})
"""The clock event reasons that mean the GPU is slowing itself down because of heat."""

_TEMPERATURE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*C\s*$")
_REASON_TAG = re.compile(r"^clocks_(?:event|throttle)_reason_(.+)$")
_PCI_DEVICE_ID = re.compile(r"^([0-9A-Fa-f]{4})([0-9A-Fa-f]{4})$")


@dataclass(frozen=True)
class NvidiaGpu:
    """One GPU as nvidia-smi reports it. Every field the board did not report is None."""

    name: str
    device_id: str | None
    temperature_c: float | None
    margin_c: float | None
    """`gpu_temp_tlimit`: degrees left before the slowdown point."""
    slowdown_c: float | None
    shutdown_c: float | None
    active_reasons: frozenset[str] | None
    """Every clock event reason that is active; None when the driver reported no reasons."""


def _celsius(text: str | None) -> float | None:
    """`64 C` as 64.0; `N/A`, empty and anything else as None."""
    match = _TEMPERATURE.match(text or "")
    return float(match.group(1).replace(",", ".")) if match else None


def _device_id(gpu: ET.Element) -> str | None:
    """`PCI\\VEN_10DE&DEV_249D` from the board's PCI id, or its UUID if it reported none (C5)."""
    match = _PCI_DEVICE_ID.match((gpu.findtext("pci/pci_device_id") or "").strip())
    if match:
        return f"PCI\\VEN_{match.group(2).upper()}&DEV_{match.group(1).upper()}"
    uuid = (gpu.findtext("uuid") or "").strip()
    return uuid or None


def _reasons(gpu: ET.Element) -> frozenset[str] | None:
    section = gpu.find("clocks_event_reasons")
    if section is None:
        section = gpu.find("clocks_throttle_reasons")
    if section is None:
        return None
    active = set()
    for child in section:
        tag = _REASON_TAG.match(child.tag)
        if tag and (child.text or "").strip().lower() == "active":
            active.add(tag.group(1))
    return frozenset(active)


def parse(text: str) -> list[NvidiaGpu]:
    """Every GPU in an `nvidia-smi -q -x` document; an unparseable one is no GPUs."""
    try:
        root = ET.fromstring(text)  # noqa: S314 - the text is our own nvidia-smi's output
    except ET.ParseError:
        return []
    gpus = []
    for gpu in root.findall("gpu"):
        gpus.append(
            NvidiaGpu(
                name=(gpu.findtext("product_name") or "").strip(),
                device_id=_device_id(gpu),
                temperature_c=_celsius(gpu.findtext("temperature/gpu_temp")),
                margin_c=_celsius(gpu.findtext("temperature/gpu_temp_tlimit")),
                slowdown_c=_celsius(gpu.findtext("temperature/gpu_temp_slow_threshold")),
                shutdown_c=_celsius(gpu.findtext("temperature/gpu_temp_max_threshold")),
                active_reasons=_reasons(gpu),
            )
        )
    return gpus


def run_smi() -> tuple[str, str]:
    """`nvidia-smi -q -x`'s output, or an empty string and the reason."""
    smi = nvidia_smi()
    if smi is None:
        return "", NO_SMI
    try:
        result = process_watch.run([smi, "-q", "-x"], process_watch.QUERY)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("nvidia-smi failed: %s", exc)
        return "", SMI_FAILED
    if result.returncode != 0 or not result.stdout.strip():
        logger.debug("nvidia-smi exited %s: %s", result.returncode, result.stderr)
        return "", SMI_FAILED
    return result.stdout, ""


def gpus(run: RunSmi | None = None) -> tuple[list[NvidiaGpu], str]:
    """Every NVIDIA GPU, or an empty list and why."""
    text, reason = (run or run_smi)()
    if reason:
        return [], reason
    found = parse(text)
    if not found:
        return [], SMI_FAILED
    return found, ""


def read(run: RunSmi | None = None) -> ThermalSnapshot:
    """Each NVIDIA GPU's temperature against the limit its own driver reports."""
    found, reason = gpus(run)
    if reason:
        return ThermalSnapshot(gaps=(Gap(SOURCE, reason),))

    readings = []
    gaps = []
    for gpu in found:
        if gpu.temperature_c is None:
            gaps.append(
                Gap(SOURCE, f"nvidia-smi reports no temperature for {gpu.name or 'the GPU'}")
            )
            continue
        if gpu.margin_c is not None:
            limit, source = gpu.temperature_c + gpu.margin_c, "driver margin to slowdown"
        elif gpu.slowdown_c is not None:
            limit, source = gpu.slowdown_c, "driver slowdown temperature"
        else:
            limit, source = None, ""
        critical = gpu.shutdown_c if limit is not None and (gpu.shutdown_c or 0) > limit else None
        readings.append(
            ThermalReading(
                component="gpu",
                device_id=gpu.device_id,
                name=gpu.name,
                temperature_c=gpu.temperature_c,
                limit_c=limit,
                critical_c=critical,
                throttle_reasons=tuple(
                    sorted((gpu.active_reasons or frozenset()) & THERMAL_REASONS)
                ),
                limit_source=source,
                source=SOURCE,
            )
        )
    return ThermalSnapshot(readings=tuple(readings), gaps=tuple(gaps))
