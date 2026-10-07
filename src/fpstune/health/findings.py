"""One list of what is wrong with this machine, built from the instruments.

Four instruments already knew something about the machine's health and none of
them said it as a problem: `storage_health` reads a drive's own wear counter,
`pcie_link` reads the lanes the graphics card negotiated, `event_scan` counts what
Windows recorded going wrong. Each answered through its own panel, in its own
shape, to someone who already knew to look. This module is the one place they are
turned into the same thing — a **finding** — so a screen that asks "is anything
wrong?" reads one list instead of three panels (#107, H1).

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

**Healthy is an empty list.** No instrument "reports OK": a source that finds
nothing wrong contributes nothing.

**A measurement that could not be taken is a gap, not a clean bill** (C11 rule 3).
`unmeasured` carries `(source, reason)` for every source that could not run — a
drive health counter that needs administrator, an integrated GPU that has no PCIe
link to read — and it travels beside the findings, never inside them, so a badge
that counts findings does not count a missing sensor as a problem and a panel that
shows gaps does not mistake them for failures.

**Severity is about the device's own limit.** Where a device publishes a limit
(`limit` is not None) `critical` means the reading is at or over it and `warning`
means close. Where the evidence is a record of something that already happened —
a crash, a driver reset — there is no limit to be at or over, so those are always
`warning`: fpstune does not invent a scale for a count of events.

**Cached for a short while.** The instruments start PowerShell and read event logs;
a screen polling this route must not pay that on every poll (C7). The cache is
`CACHE_SECONDS` long and holds the lock while it refills, so concurrent callers wait
for one refill rather than starting several.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from fpstune.benchmark.event_scan import EventScanBench
from fpstune.benchmark.pcie_link import PcieLinkBench
from fpstune.benchmark.storage_health import StorageHealthBench
from fpstune.benchmark.suite import Bench, BenchResult, run_bench_with_deadline
from fpstune.utils.logger import get_logger

logger = get_logger()

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
    }
)
"""Every `title_key` a finding may carry.

A finding built with a key that is not here fails at construction, because the key
is a promise to the UI that a translated string exists: a misspelt one would reach
a screen as a raw identifier. The frontend adds the strings (`i18n/en.ts`,
`i18n/tr.ts`); a test there compares against this set.
"""

CACHE_SECONDS = 30.0
"""How long a collected report is served without asking the instruments again.

Thirty seconds is longer than a screen polls and shorter than a person waits for a
fix to show: after a drive is replaced or a slot reseated, the answer is at most
this stale, and `refresh` asks again immediately.
"""

WEAR_WARNING_MARGIN_PERCENT = 10.0
"""How far from a drive's rated endurance a warning begins.

The one constant in this file that is a judgement rather than a device figure. A
drive reports the share of its rated endurance already spent in whole percent, and
`100` is the point its maker rated it to; the last tenth of that is when a
replacement should be planned rather than discovered, and a reading is whole
percent so a margin finer than a few points would be noise.
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


def _gap(result: BenchResult) -> SourceResult:
    return SourceResult(gaps=(Gap(source=result.bench, reason=result.reason),))


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def storage_findings(result: BenchResult) -> SourceResult:
    """A drive close to, or past, the endurance it was rated for.

    Only the wear counter becomes a finding here. The same cmdlet's read and write
    error totals are not used: on a SATA drive they are the vendor-encoded raw
    value of a SMART attribute, which on a healthy Seagate runs to millions, so
    "non-zero" would flag the healthy ones. What Windows itself recorded failing
    comes through `event_findings`, which counts events and not raw attributes.
    Temperature is judged against the drive's own limit in `health.thermal`.
    """
    if not result.ran:
        return _gap(result)

    findings = []
    for drive in result.detail.get("drives", []):
        wear = _number(drive.get("wear_percent"))
        if wear is None:
            continue
        if wear >= 100.0:
            severity: Severity = "critical"
        elif wear >= 100.0 - WEAR_WARNING_MARGIN_PERCENT:
            severity = "warning"
        else:
            continue
        findings.append(
            Finding(
                component="storage",
                device_id=str(drive.get("unique_id") or "") or None,
                severity=severity,
                title_key="health.storage.endurance",
                reading=Quantity(wear, "%"),
                limit=Quantity(100.0, "%"),
                source=result.bench,
            )
        )
    return SourceResult(findings=tuple(findings))


def pcie_findings(result: BenchResult) -> SourceResult:
    """A graphics card running on fewer lanes than it was built for.

    Only the width is a finding. The link *speed* is reported by Windows as
    negotiated *now*, and a card drops to the slowest generation when idle to save
    power: measured at an idle desktop, this machine's card reports generation 1 of
    a maximum 4 (`nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max`).
    Flagging it would put a warning on every idle desktop. Width does not do that.
    """
    if not result.ran:
        return _gap(result)

    findings = []
    for adapter in result.detail.get("adapters", []):
        current = _number(adapter.get("current_width"))
        maximum = _number(adapter.get("max_width"))
        if current is None or maximum is None or current >= maximum:
            continue
        findings.append(
            Finding(
                component="gpu",
                device_id=stable_pci_id(str(adapter.get("instance_id") or "")),
                severity="warning",
                title_key="health.gpu.pcie_link_width",
                reading=Quantity(current, "lanes"),
                limit=Quantity(maximum, "lanes"),
                source=result.bench,
            )
        )
    return SourceResult(findings=tuple(findings))


# (event count reading, component, title key). A crash is the larger of two counts
# of the same event, which the instrument already computes as `crash_rate`'s input;
# here it is rebuilt from the two raw counts the same way.
_EVENT_KINDS: tuple[tuple[str, Component, str], ...] = (
    ("unexpected_shutdown_count", "system", "health.system.unexpected_shutdowns"),
    ("whea_error_count", "system", "health.system.hardware_errors"),
    ("tdr_count", "gpu", "health.gpu.driver_resets"),
    ("disk_error_count", "storage", "health.storage.io_errors"),
)


def event_findings(result: BenchResult) -> SourceResult:
    """Failures Windows recorded in the scan window.

    These are history, not a reading against a limit, so every one is a `warning`
    with no `limit`. None of them carries a `device_id`: the events name a driver
    or a class of hardware, not which disk or which adapter, and a guessed device
    would put the finding under the wrong heading.
    """
    if not result.ran:
        return _gap(result)

    def count(name: str) -> float:
        reading = result.readings.get(name)
        return reading.median if reading is not None else 0.0

    findings = []
    crashes = max(count("bugcheck_count"), count("minidump_count"))
    if crashes > 0:
        findings.append(_event_finding("system", "health.system.crashes", crashes, result.bench))
    for name, component, title_key in _EVENT_KINDS:
        events = count(name)
        if events > 0:
            findings.append(_event_finding(component, title_key, events, result.bench))
    return SourceResult(findings=tuple(findings))


def _event_finding(component: Component, title_key: str, events: float, source: str) -> Finding:
    return Finding(
        component=component,
        device_id=None,
        severity="warning",
        title_key=title_key,
        reading=Quantity(events, "events"),
        limit=None,
        source=source,
    )


def _from_bench(
    make: Callable[[], Bench], convert: Callable[[BenchResult], SourceResult]
) -> Source:
    """A source that runs one instrument once, under its own deadline, and converts it."""

    def source() -> SourceResult:
        return convert(run_bench_with_deadline(make(), 1))

    return source


SOURCES: dict[str, Source] = {
    "storage_health": _from_bench(StorageHealthBench, storage_findings),
    "pcie_link": _from_bench(PcieLinkBench, pcie_findings),
    "event_scan": _from_bench(EventScanBench, event_findings),
}
"""Every source `collect` asks, by the name a gap is reported under."""

_SEVERITY_ORDER = {"critical": 0, "warning": 1}


def _ask(name: str, source: Source) -> SourceResult:
    """One source's answer, with a crash turned into a visible gap.

    A source that raises is a bug in that source, and it must not take the other
    checks down with it — or vanish: the gap names it, the log carries the trace.
    """
    try:
        return source()
    except Exception as exc:  # noqa: BLE001 - one broken check must not hide the rest
        logger.warning("Health source %s failed: %s", name, exc, exc_info=True)
        return SourceResult(
            gaps=(Gap(source=name, reason=f"the check failed ({type(exc).__name__})"),)
        )


def _gather(sources: Mapping[str, Source]) -> HealthReport:
    measured_at = time.time()
    # One thread per source and no more: each spends its time waiting on a child
    # process or an event-log read, so the count is the source count, not a core count.
    with ThreadPoolExecutor(max_workers=max(len(sources), 1)) as pool:
        futures = {name: pool.submit(_ask, name, source) for name, source in sources.items()}
        results = {name: future.result() for name, future in futures.items()}

    findings = sorted(
        (finding for result in results.values() for finding in result.findings),
        key=lambda f: (_SEVERITY_ORDER[f.severity], f.component, f.source, f.device_id or ""),
    )
    gaps = sorted(
        (gap for result in results.values() for gap in result.gaps),
        key=lambda g: g.source,
    )
    return HealthReport(findings=tuple(findings), unmeasured=tuple(gaps), measured_at=measured_at)


_cache_lock = threading.Lock()
_cached: tuple[float, HealthReport] | None = None


def reset_cache() -> None:
    """Forget the cached report (tests, and a caller that knows the machine changed)."""
    global _cached
    with _cache_lock:
        _cached = None


def collect(
    sources: Mapping[str, Source] | None = None,
    *,
    refresh: bool = False,
    clock: Callable[[], float] = time.monotonic,
) -> HealthReport:
    """Everything wrong with this machine, from every source, cached for `CACHE_SECONDS`.

    `sources` replaces the registry and bypasses the cache: a caller that names its
    own sources wants exactly those, asked now.
    """
    global _cached
    if sources is not None:
        return _gather(sources)
    with _cache_lock:
        if not refresh and _cached is not None and clock() - _cached[0] < CACHE_SECONDS:
            return _cached[1]
        report = _gather(SOURCES)
        _cached = (clock(), report)
        return report
