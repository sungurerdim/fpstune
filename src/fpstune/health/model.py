"""The shapes every health source speaks: a finding, a gap, and what a source returns.

Kept apart from `findings.py` because the readers (`thermal`, `throttle`) build
findings and `findings.py` collects the readers: the types have to sit under both
or the two import each other.

A finding carries the reading, the limit it was read against, and the component it
belongs under:

| Field | Meaning |
|---|---|
| `component` | `cpu`, `gpu`, `storage` or `system` — which heading a UI files it under |
| `device_id` | a stable id (C5) of the device, or None when the evidence names a class of device and not one of them (a Windows event does not say which disk) |
| `severity` | `warning` (near its limit, or reported degraded) or `critical` (at or over it) |
| `title_key` | an i18n key — one of `TITLE_KEYS`, which the UI must hold a string for |
| `reading`, `limit` | what was measured and what it was measured against; both optional |
| `source` | which instrument said so |
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Component = Literal["cpu", "gpu", "storage", "system"]
Severity = Literal["warning", "critical"]

TITLE_KEYS = frozenset(
    {
        # A drive's own rated-endurance counter.
        "health.storage.endurance",
        # The graphics card negotiated fewer PCIe lanes than it has.
        "health.gpu.pcie_link_width",
        # Windows' own record of failures over the scan window.
        "health.system.crashes",
        "health.system.unexpected_shutdowns",
        "health.system.hardware_errors",
        "health.gpu.driver_resets",
        "health.storage.io_errors",
        # A temperature near or past the device's own published limit, and a
        # device reporting that it is slowing itself down because of heat.
        "health.gpu.temperature",
        "health.gpu.thermal_throttle",
        "health.storage.temperature",
        "health.cpu.thermal_zone",
        # An NVMe drive's own critical-warning flags (NVMe spec, SMART/Health log byte 0).
        "health.storage.spare_low",
        "health.storage.reliability_degraded",
        "health.storage.read_only",
        "health.storage.backup_failed",
    }
)
"""Every `title_key` a finding may carry.

A finding built with a key that is not here fails at construction, because the key
is a promise to the UI that a translated string exists: a misspelt one would reach
a screen as a raw identifier. The frontend adds the strings (`i18n/en.ts`,
`i18n/tr.ts`); a test there compares against this set.
"""

_PCI_STABLE_ID = re.compile(r"(PCI\\VEN_[0-9A-F]+&DEV_[0-9A-F]+)", re.IGNORECASE)


@dataclass(frozen=True)
class Quantity:
    """A number with the unit it is in."""

    value: float
    unit: str


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong, or about to be, on one component."""

    component: Component
    device_id: str | None
    severity: Severity
    title_key: str
    reading: Quantity | None
    limit: Quantity | None
    source: str

    def __post_init__(self) -> None:
        if self.title_key not in TITLE_KEYS:
            raise ValueError(
                f"{self.title_key!r} is not a known finding title — add it to TITLE_KEYS "
                "and give the UI a string for it"
            )


@dataclass(frozen=True)
class Gap:
    """A check that could not be made, and why."""

    source: str
    reason: str


@dataclass(frozen=True)
class SourceResult:
    """What one source contributed: findings, and gaps it could not close."""

    findings: tuple[Finding, ...] = ()
    gaps: tuple[Gap, ...] = ()


@dataclass(frozen=True)
class HealthReport:
    """Everything wrong, and everything that could not be checked."""

    findings: tuple[Finding, ...]
    unmeasured: tuple[Gap, ...]
    measured_at: float
    """Wall-clock epoch seconds when the sources were asked, so a UI can say how old this is."""


Source = Callable[[], SourceResult]


def stable_pci_id(pnp_device_id: str) -> str | None:
    """The `PCI\\VEN_xxxx&DEV_xxxx` part of a PNPDeviceID, upper-cased (C5), or None."""
    match = _PCI_STABLE_ID.match(pnp_device_id or "")
    return match.group(1).upper() if match else None
