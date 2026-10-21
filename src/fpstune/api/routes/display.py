"""Display/Monitor settings API routes."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel

from fpstune.api.schemas import DisplayPendingResponse, MonitorInfo
from fpstune.settings import display_mode
from fpstune.utils.hardware_manager import hardware_manager

router = APIRouter(prefix="/display", tags=["display"])
logger = logging.getLogger(__name__)


class DisplayAutoResponse(BaseModel):
    """Response for setting display to auto."""

    success: bool
    display_index: int
    resolution: str
    refresh_rate: int
    message: str
    # A real mode write awaits confirmation: unless /display/{index}/confirm
    # arrives within revert_timeout_s, the prior mode is written back.
    requires_confirmation: bool = False
    revert_timeout_s: float | None = None


class DisplayConfirmResponse(BaseModel):
    """Response for confirming (keeping) an applied display mode."""

    success: bool
    message: str


class RefreshDisplaysResponse(BaseModel):
    """Response for refreshing display info."""

    success: bool
    # MonitorInfo.from_detected is the one monitor serializer — /api/hardware
    # uses it too, so the payloads cannot drift apart again.
    monitors: list[MonitorInfo]


@router.post("/{display_index}/auto", response_model=DisplayAutoResponse)
async def set_display_to_auto(display_index: int = Path(ge=0, le=10)) -> DisplayAutoResponse:
    """Set a display to its native resolution and maximum refresh rate.

    Args:
        display_index: 0-based index of the display to configure.

    Returns:
        DisplayAutoResponse with result details.
    """
    if sys.platform != "win32":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display settings are only available on Windows",
        )

    # Get current monitors (use cache - native values don't change). A cold
    # cache runs a multi-second PowerShell detection, so it stays off the loop.
    monitors = await asyncio.to_thread(hardware_manager.detect_monitors)
    if display_index >= len(monitors):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Display index {display_index} not found. Available displays: 0-{len(monitors) - 1}",
        )

    monitor = monitors[display_index]
    target_width = monitor.native_width
    target_height = monitor.native_height
    # The UI shows `native_refresh_rate_hz || max_refresh_rate_hz` as the target, so
    # applying `max` unconditionally could write a rate the arrow never promised —
    # they differ on panels whose maximum is an overclock above the EDID native
    # rate. One source of truth, and it is the one the user was shown.
    # Ceiling first: a high-refresh panel's EDID often prefers 60 Hz while its
    # mode list reaches 300 — targeting the preferred rate would set it there.
    target_refresh = monitor.max_refresh_rate_hz or monitor.native_refresh_rate_hz

    # Check if already optimal
    if monitor.is_resolution_optimal and monitor.is_refresh_optimal:
        return DisplayAutoResponse(
            success=True,
            display_index=display_index,
            resolution=f"{target_width}x{target_height}",
            refresh_rate=target_refresh,
            message="Display is already at optimal settings",
        )

    # Only what is wrong is written (a lowered resolution is a legitimate choice
    # when the refresh is what needs fixing), guarded by CDS_TEST and a revert
    # unless kept — the one write path, shared with the per-monitor setting.
    changed = [
        part
        for part, wrong in (
            (f"{target_width}x{target_height}", not monitor.is_resolution_optimal),
            (f"{target_refresh}Hz", not monitor.is_refresh_optimal),
        )
        if wrong
    ]
    try:
        outcome = await asyncio.to_thread(display_mode.write_native, monitor)
    except Exception as e:
        logger.exception("Error changing display settings")
        raise HTTPException(status_code=500, detail="Internal server error") from e
    if not outcome.ok:
        # The specific reason, never an opaque 500: "code: -5" hidden behind a
        # catch-all is how a broken device name stayed undiagnosed.
        code = status.HTTP_409_CONFLICT if outcome.kind == "testfail" else 500
        logger.error("Display mode not written: %s", outcome.message)
        raise HTTPException(status_code=code, detail=outcome.message)

    return DisplayAutoResponse(
        success=True,
        display_index=display_index,
        resolution=f"{target_width}x{target_height}",
        refresh_rate=target_refresh,
        message=(
            f"Display set to {' and '.join(changed)} — reverts in "
            f"{int(display_mode.REVERT_TIMEOUT_S)}s unless kept"
        ),
        requires_confirmation=True,
        revert_timeout_s=display_mode.REVERT_TIMEOUT_S,
    )


@router.post("/{display_index}/confirm", response_model=DisplayConfirmResponse)
async def confirm_display_change(display_index: int = Path(ge=0, le=10)) -> DisplayConfirmResponse:
    """Keep an applied display mode: cancel its pending revert.

    Returns 404 when nothing is awaiting confirmation for that display — the
    timer may already have fired and reverted the change.
    """
    monitors = await asyncio.to_thread(hardware_manager.detect_monitors)
    if display_index >= len(monitors):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Display index {display_index} not found",
        )
    monitor = monitors[display_index]
    device_name = monitor.name if monitor.name.startswith("\\\\.\\") else f"\\\\.\\{monitor.name}"
    if not display_mode.cancel_revert(device_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No display change is awaiting confirmation — it may already have reverted.",
        )
    return DisplayConfirmResponse(success=True, message="Display mode kept.")


@router.get("/pending", response_model=DisplayPendingResponse)
async def pending_display_changes() -> dict[str, Any]:
    """Displays whose new mode reverts unless kept, and how long the window is."""
    return {
        "devices": display_mode.pending_devices(),
        "seconds_left": round(display_mode.seconds_until_revert()),
    }


@router.post("/keep-all", response_model=DisplayConfirmResponse)
async def keep_all_display_changes() -> DisplayConfirmResponse:
    """Keep every display mode waiting for confirmation (the per-monitor settings
    and a bulk apply write several at once; one answer keeps them all)."""
    kept = display_mode.keep_all()
    if not kept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No display change is awaiting confirmation — it may already have reverted.",
        )
    return DisplayConfirmResponse(success=True, message=f"Kept {len(kept)} display mode(s).")


@router.post("/refresh", response_model=RefreshDisplaysResponse)
async def refresh_displays() -> RefreshDisplaysResponse:
    """Refresh display detection and return updated monitor info.

    Returns:
        RefreshDisplaysResponse with updated monitor list.
    """
    if sys.platform != "win32":
        return RefreshDisplaysResponse(success=True, monitors=[])

    # Invalidate cache to force fresh detection. The re-detect is therefore
    # always a cold multi-second PowerShell run — never inline on the loop.
    hardware_manager.invalidate_cache("monitors")
    monitors = await asyncio.to_thread(hardware_manager.detect_monitors)

    return RefreshDisplaysResponse(
        success=True,
        monitors=[MonitorInfo.from_detected(m, monitors) for m in monitors],
    )
