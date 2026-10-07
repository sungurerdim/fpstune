"""What is wrong with this machine: one list for every screen that asks.

`GET /api/health/findings` is the single read behind the Optimize tab's problem
count and behind the rows filed under a device (#107, H1/H2/H3). It answers from
`fpstune.health.findings`, which turns the drive, PCIe, event-log and thermal
instruments into the same shape and caches the answer for a short while, so a
screen polling this route does not start PowerShell on every poll (C7).

A healthy machine returns `findings: []`. What could not be checked is in
`unmeasured`, beside the list and never in it: a missing sensor is not a problem,
and not a clean bill either (C11 rule 3).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fpstune.health.findings import collect
from fpstune.health.model import (
    Component,
    Finding,
    Gap,
    HealthReport,
    Quantity,
    Severity,
)

router = APIRouter()


class QuantityResponse(BaseModel):
    """A number and the unit it is in (`C`, `%`, `lanes`, `events`)."""

    value: float
    unit: str


class HealthFindingResponse(BaseModel):
    """One thing wrong with one component."""

    component: Component
    device_id: str | None = Field(
        description=(
            "Stable id of the device (PCI VEN+DEV, drive UniqueId, vendor id). Null when the "
            "evidence names a class of hardware and not one device."
        )
    )
    severity: Severity
    title_key: str = Field(description="i18n key the UI holds a string for.")
    reading: QuantityResponse | None = Field(description="What was measured.")
    limit: QuantityResponse | None = Field(
        description="What it was measured against: the device's own limit. Null for event history."
    )
    source: str = Field(description="Which instrument said so.")


class HealthGapResponse(BaseModel):
    """A check that could not be made, and why."""

    source: str
    reason: str


class HealthFindingsResponse(BaseModel):
    """Findings, the gaps beside them, and when the sources were asked."""

    findings: list[HealthFindingResponse]
    unmeasured: list[HealthGapResponse]
    measured_at: float = Field(description="Unix epoch seconds at which the sources were asked.")


def _quantity(value: Quantity | None) -> QuantityResponse | None:
    return None if value is None else QuantityResponse(value=value.value, unit=value.unit)


def _finding(finding: Finding) -> HealthFindingResponse:
    return HealthFindingResponse(
        component=finding.component,
        device_id=finding.device_id,
        severity=finding.severity,
        title_key=finding.title_key,
        reading=_quantity(finding.reading),
        limit=_quantity(finding.limit),
        source=finding.source,
    )


def _gap(gap: Gap) -> HealthGapResponse:
    return HealthGapResponse(source=gap.source, reason=gap.reason)


def to_response(report: HealthReport) -> HealthFindingsResponse:
    """The wire shape of a report."""
    return HealthFindingsResponse(
        findings=[_finding(f) for f in report.findings],
        unmeasured=[_gap(g) for g in report.unmeasured],
        measured_at=report.measured_at,
    )


@router.get("/health/findings", response_model=HealthFindingsResponse)
async def get_health_findings(refresh: bool = False) -> HealthFindingsResponse:
    """Every finding, from every source, cached for a short while.

    `refresh=true` asks the instruments again now. The sources start PowerShell and
    read event logs, so the collection runs on a worker thread, never the event loop.
    """
    report = await asyncio.to_thread(collect, refresh=refresh)
    return to_response(report)
