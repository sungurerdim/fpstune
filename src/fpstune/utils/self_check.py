"""Every detector cross-checked against an independent source (A12).

The monitor correlation shipped dead and nobody noticed, because the fallback
produced a plausible map and "plausible" is what a wrong detection looks like.
The countermeasure is structural: each area is checked against a source that
does not share the pipeline's failure mode — the monitor report against raw
WMI and raw EnumDisplayDevices enumerations, the GPU's nvidia-smi figure
against the driver's own registry QWORD, the CPU's WMI counts against the OS
scheduler's. A disagreement is a named finding a user can read, never a log
line that dies in debug output.

Runs on demand (the API route) and once before the first apply on a machine
fpstune has not checked — a wrong detection is worth finding *before* the
first write derives from it. The report persists next to the originals store,
so "was this machine ever checked" survives restarts.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from fpstune.utils.config import get_config_dir

if TYPE_CHECKING:
    from fpstune.utils.detect import CpuDetailedInfo, GpuInfo, MonitorInfo

logger = logging.getLogger(__name__)

_REPORT_FILENAME = "selfcheck.json"


@dataclass(frozen=True)
class Finding:
    """One cross-check: which sources were compared and whether they agree."""

    area: str  # "monitors" | "gpu" | "cpu"
    name: str  # stable check identifier
    agrees: bool
    detail: str  # what each source said, readable by a user


@dataclass
class SelfCheckReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def disagreements(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.agrees]

    @property
    def ok(self) -> bool:
        return not self.disagreements

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [asdict(finding) for finding in self.findings],
        }


def check_monitor_sources(
    monitors: list[MonitorInfo],
    wmi_hw_ids: list[str],
    adapter_records: list[str],
) -> list[Finding]:
    """The monitor report against the two raw enumerations it was built from.

    These four checks catch the exact defect that shipped: an order-based map
    hands a panel its neighbour's identity, which shows up here as a WMI panel
    nothing accounts for, or a reported identity WMI never saw.
    """
    findings: list[Finding] = []

    attached_heads: list[str] = []
    for record in adapter_records:
        parts = record.split("|", 2)
        if len(parts) < 3:
            continue
        try:
            flags = int(parts[1])
        except ValueError:
            continue
        if flags & 0x8:  # mirroring pseudo-device
            continue
        if flags & 0x1:
            attached_heads.append(parts[0])

    active_names = {monitor.name for monitor in monitors if monitor.is_active}
    missing = sorted(name for name in attached_heads if name not in active_names)
    findings.append(
        Finding(
            "monitors",
            "every_attached_screen_reported",
            agrees=not missing,
            detail=(
                f"EnumDisplayDevices reports attached heads the monitor report lacks: {missing}"
                if missing
                else f"all {len(attached_heads)} attached head(s) present in the report"
            ),
        )
    )

    uncorrelated = sorted(m.name for m in monitors if m.is_active and not m.hardware_id)
    findings.append(
        Finding(
            "monitors",
            "every_active_screen_has_an_identity",
            agrees=not uncorrelated,
            detail=(
                f"active screens the UID join could not place: {uncorrelated}"
                if uncorrelated
                else "every active screen correlated to a WMI identity"
            ),
        )
    )

    reported_ids = {m.hardware_id for m in monitors if m.hardware_id}
    unaccounted = sorted(set(wmi_hw_ids) - reported_ids)
    findings.append(
        Finding(
            "monitors",
            "every_wmi_panel_accounted_for",
            agrees=not unaccounted,
            detail=(
                f"WMI names panels the report dropped: {unaccounted}"
                if unaccounted
                else f"all {len(set(wmi_hw_ids))} WMI panel identity(ies) accounted for"
            ),
        )
    )

    phantom = sorted(reported_ids - set(wmi_hw_ids))
    findings.append(
        Finding(
            "monitors",
            "no_reported_identity_wmi_never_saw",
            agrees=not phantom,
            detail=(
                f"the report claims identities WMI never enumerated: {phantom}"
                if phantom
                else "every reported identity exists in the WMI enumeration"
            ),
        )
    )

    return findings


def check_cpu_sources(cpu: CpuDetailedInfo | None, os_logical: int) -> list[Finding]:
    """WMI's counts against the OS scheduler's, and the topology against itself."""
    if cpu is None:
        return [
            Finding("cpu", "cpu_readable", agrees=False, detail="CPU detection returned nothing")
        ]

    findings = [
        Finding(
            "cpu",
            "logical_cores_agree_with_the_scheduler",
            agrees=bool(cpu.logical_cores == os_logical or not cpu.logical_cores or not os_logical),
            detail=f"WMI sums {cpu.logical_cores} logical cores, the OS schedules {os_logical}",
        )
    ]
    if cpu.is_hybrid is None:
        findings.append(
            Finding(
                "cpu",
                "pe_topology",
                agrees=True,
                detail="topology could not be read and is reported as unknown, not guessed",
            )
        )
    else:
        findings.append(
            Finding(
                "cpu",
                "pe_topology_sums_to_the_core_count",
                agrees=bool(
                    not cpu.physical_cores or cpu.p_cores + cpu.e_cores == cpu.physical_cores
                ),
                detail=(
                    f"kernel topology counts {cpu.p_cores}P+{cpu.e_cores}E, "
                    f"WMI counts {cpu.physical_cores} physical cores"
                ),
            )
        )
    return findings


def check_gpu_sources(gpu: GpuInfo | None, registry_vram_mb: int | None) -> list[Finding]:
    """The primary GPU read against the driver's own registry QWORD."""
    if gpu is None:
        return [
            Finding("gpu", "gpu_readable", agrees=False, detail="GPU detection returned nothing")
        ]

    if registry_vram_mb and gpu.vram_mb:
        # nvidia-smi and the registry round differently; a whole tier apart is
        # a disagreement, a rounding step is not.
        agree = abs(gpu.vram_mb - registry_vram_mb) <= 256
        return [
            Finding(
                "gpu",
                "vram_agrees_across_sources",
                agrees=agree,
                detail=(
                    f"primary source says {gpu.vram_mb} MB, the driver registry "
                    f"QWORD says {registry_vram_mb} MB"
                ),
            )
        ]
    return [
        Finding(
            "gpu",
            "vram_single_source",
            agrees=True,
            detail=(
                "only one VRAM source answered on this machine — no cross-check "
                "possible, recorded rather than assumed"
            ),
        )
    ]


def _raw_monitor_sources() -> tuple[list[str], list[str]]:
    """The two raw enumerations, read independently of the report pipeline."""
    from fpstune.utils.detect import _DISPLAY_DEVICES_CSHARP

    script = (
        _DISPLAY_DEVICES_CSHARP
        + r"""
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID 2>$null | ForEach-Object {
    $parts = $_.InstanceName -split '\\'
    if ($parts.Count -ge 2) { "WMI=$($parts[1])" }
}
foreach ($rec in [DisplayDevices]::EnumerateAdapters()) { "REC=$rec" }
"""
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, constant script
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        encoding="utf-8",
        errors="replace",
    )
    wmi_ids: list[str] = []
    records: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("WMI="):
            wmi_ids.append(line[4:])
        elif line.startswith("REC="):
            records.append(line[4:])
    return wmi_ids, records


def _registry_vram_mb() -> int | None:
    """The driver registry QWORD, independent of the nvidia-smi-first path."""
    from fpstune.utils.detect import _GPU_DETECT_PS

    result = subprocess.run(  # noqa: S603 - fixed argv, constant script
        ["powershell", "-NoProfile", "-Command", _GPU_DETECT_PS],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        encoding="utf-8",
        errors="replace",
    )
    for line in result.stdout.splitlines():
        if line.strip().startswith("VramBytes="):
            try:
                return int(line.split("=", 1)[1].strip()) // (1024 * 1024)
            except ValueError:
                return None
    return None


def run_self_check() -> SelfCheckReport:
    """Run every cross-check against the live machine and persist the report."""
    from fpstune.utils.detect import get_cpu_detailed_info, get_gpu_info, get_monitors

    report = SelfCheckReport()
    try:
        monitors = get_monitors()
        wmi_ids, records = _raw_monitor_sources()
        report.findings.extend(check_monitor_sources(monitors, wmi_ids, records))
    except Exception as exc:
        report.findings.append(
            Finding("monitors", "monitor_check_ran", agrees=False, detail=str(exc))
        )
    try:
        report.findings.extend(check_gpu_sources(get_gpu_info(), _registry_vram_mb()))
    except Exception as exc:
        report.findings.append(Finding("gpu", "gpu_check_ran", agrees=False, detail=str(exc)))
    try:
        report.findings.extend(check_cpu_sources(get_cpu_detailed_info(), os.cpu_count() or 0))
    except Exception as exc:
        report.findings.append(Finding("cpu", "cpu_check_ran", agrees=False, detail=str(exc)))

    for finding in report.disagreements:
        logger.warning(
            "FPSTUNE_WARN self-check disagreement [%s/%s]: %s",
            finding.area,
            finding.name,
            finding.detail,
        )

    try:
        _report_path().write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - disk-dependent
        logger.warning("Could not persist self-check report: %s", exc)
    return report


def _report_path() -> Any:
    path = get_config_dir() / _REPORT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_last_report() -> dict[str, Any] | None:
    """The persisted report, or None when this machine was never checked."""
    try:
        loaded = json.loads(_report_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def ensure_checked_before_first_apply() -> None:
    """Run the self-check once per machine, before the first write derives
    from a detection nobody has cross-checked. Idempotent and never raises —
    an apply must not fail because the check could not run, but a disagreement
    is already on the record (FPSTUNE_WARN + the persisted report) by the time
    the write happens.
    """
    try:
        if load_last_report() is not None:
            return
        logger.info("First apply on this machine — running the detection self-check")
        run_self_check()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Detection self-check could not run: %s", exc)
