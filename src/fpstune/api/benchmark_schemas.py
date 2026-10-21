"""Response models for the benchmark surface.

These shapes have one caller (the Measure tab) and are large enough that they
do not belong in `api/schemas.py` beside the settings contract. They mirror the
frontend's `SuiteCatalogue`, `BenchLedger`, `VerifyCoverage`, `MachineHeadroom`
and friends field for field; the TS contract test is the binding.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SuiteBenchResponse(BaseModel):
    key: str
    label: str
    requires: str
    costs: str
    available: bool
    reason: str
    in_default_run: bool


class SuiteCatalogueResponse(BaseModel):
    benches: list[SuiteBenchResponse]
    default_keys: list[str]
    min_repeats: int
    default_repeats: int
    max_repeats: int


class SuiteReadingResponse(BaseModel):
    metric: str
    samples: list[float]
    median: float
    noise: float | None
    unit: str
    improves_upward: bool | None


class SuiteResultResponse(BaseModel):
    bench: str
    label: str
    ran: bool
    reason: str
    readings: dict[str, SuiteReadingResponse]
    detail: dict[str, Any]
    duration_seconds: float


class SuiteRunResponse(BaseModel):
    label: str
    started_at: float
    summary: str
    results: list[SuiteResultResponse]


class SuiteMeasurementResponse(BaseModel):
    metric: str
    before: float
    after: float
    delta: float
    percent_change: float
    unit: str
    noise: float | None
    exceeds_noise: bool
    category: str | None = None


class SuiteUnpairedResponse(BaseModel):
    metric: str
    reason: str


class SuiteComparisonResponse(BaseModel):
    before_label: str
    after_label: str
    summary: str
    measurements: list[SuiteMeasurementResponse]
    unpaired: list[SuiteUnpairedResponse]


class LedgerJobResponse(BaseModel):
    id: str
    trigger: str
    label: str
    status: str
    plan: list[str]
    step_index: int
    current_bench: str | None
    remaining: list[str]
    attempts: dict[str, int]
    created_at: float
    updated_at: float


class LedgerRunSummaryResponse(BaseModel):
    label: str
    started_at: float
    summary: str
    bench_count: int
    ran_count: int
    metrics: list[str]


class LedgerAreaResponse(BaseModel):
    area: str
    label: str
    instrument: str
    metric: str | None
    measured: bool
    reason: str
    before: float | None
    after: float | None
    delta: float | None
    percent_change: float | None
    unit: str
    noise: float | None
    exceeds_noise: bool
    improves_upward: bool | None = None
    verdict: str | None = None
    samples_before: int | None = None
    samples_after: int | None = None


class BenchLedgerResponse(BaseModel):
    job: LedgerJobResponse | None
    baseline: LedgerRunSummaryResponse | None
    after: LedgerRunSummaryResponse | None
    areas: list[LedgerAreaResponse]
    bulk_apply_pending: bool
    poll_interval_seconds: float


class LedgerRunQueuedResponse(BaseModel):
    queued: bool
    job: LedgerJobResponse | None


class LedgerRunsResponse(BaseModel):
    baseline: SuiteRunResponse | None
    after: SuiteRunResponse | None


class MeasurableClaimResponse(BaseModel):
    setting_id: str
    metric: str
    claimed: str
    source: str
    requires: str


class UnmeasurableClaimResponse(BaseModel):
    setting_id: str
    metric: str
    claimed: str
    reason: str
    judgeable: bool


class VerifyCoverageResponse(BaseModel):
    summary: str
    total_claims: int
    measurable: list[MeasurableClaimResponse]
    unmeasurable: list[UnmeasurableClaimResponse]
    measurable_count: int
    gap_count: int
    not_judgeable_count: int
    required_conditions: list[str]


class VerifySourceResponse(BaseModel):
    name: str
    requires: str
    metrics: list[str]
    units: dict[str, str]
    runnable: bool


class VerifySourcesResponse(BaseModel):
    sources: list[VerifySourceResponse]
    no_instrument: dict[str, str]


class VerifySampleResponse(BaseModel):
    instrument: str
    requires: str
    metrics: dict[str, float]


class VerifyMeasurementResponse(BaseModel):
    before: float
    after: float
    delta: float
    percent_change: float
    unit: str
    noise: float


class VerifyVerdictResponse(BaseModel):
    setting_id: str
    metric: str
    claimed: str
    status: str
    reason: str
    measured: VerifyMeasurementResponse | None


class VerifyReportResponse(BaseModel):
    settings_changed: int
    summary: str
    verified: int
    contradicted: int
    unverified: int
    verdicts: list[VerifyVerdictResponse]
    notes: list[str]


class MachineHeadroomResponse(BaseModel):
    is_measured: bool
    measured_fps: float | None
    fps_1_percent_low: float | None
    target_fps: float | None
    achievement_percent: float | None
    tier: str
    bottleneck: str
    present_mode: str | None
    width: int | None
    height: int | None
    measured_at: float | None


class HeadroomResponse(BaseModel):
    headroom: MachineHeadroomResponse


class MeasureResultResponse(BaseModel):
    measured: bool
    outcome: str
    detail: str
    headroom: MachineHeadroomResponse | None


class GpuSceneStatusResponse(BaseModel):
    installed: bool
    download_size: str
    licence_note: str


class GpuSceneInstallResponse(BaseModel):
    installed: bool
    reason: str
