"""Display/Monitor settings API routes."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel

from fpstune.api.schemas import MonitorInfo
from fpstune.settings import display_mode
from fpstune.settings.panel import primary_monitor, refresh_ceiling_hz
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


@router.get("/pending")
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


# =============================================================================
# VRR / G-Sync Optimization
# =============================================================================


class VrrOptimizationInfo(BaseModel):
    """VRR optimization information and recommendations."""

    # Monitor info
    monitor_name: str
    monitor_refresh_hz: int
    supports_vrr: bool | None

    # Recommended settings
    recommended_fps_limit: int
    recommended_vrr_mode: str
    recommended_vsync: str

    # Current settings (if applied)
    current_fps_limit: int
    current_vrr_mode: str
    current_vsync: str
    is_optimized: bool

    # Explanation for UI
    explanation: str
    warning: str | None = None


class VrrOptimizationApplyRequest(BaseModel):
    """Request to apply VRR optimization."""

    fps_limit: int
    vrr_mode: str
    vsync: str


class VrrOptimizationApplyResponse(BaseModel):
    """Response after applying VRR optimization."""

    success: bool
    message: str
    applied_fps_limit: int
    applied_vrr_mode: str
    applied_vsync: str


def _vrr_current() -> tuple[int, str, str]:
    """The driver's current frame cap, VRR scope and V-Sync, read from NVAPI.

    "unknown" names a state the driver could not report; it is never filled in
    with a guess, because a guess is what made the old panel claim settings
    were applied when they were not.
    """
    from fpstune.settings.executors.nvprofile import read_setting_from_driver

    fps = read_setting_from_driver("fps_limit")
    vrr = read_setting_from_driver("vrr_mode")
    vsync = read_setting_from_driver("vsync")
    return (
        int(fps) if isinstance(fps, int) else 0,
        str(vrr) if vrr is not None else "unknown",
        str(vsync) if vsync is not None else "unknown",
    )


@router.get("/vrr-optimization", response_model=VrrOptimizationInfo)
async def get_vrr_optimization_info(
    display_index: int | None = None,
) -> VrrOptimizationInfo:
    """VRR/G-Sync recommendation for one monitor, beside the driver's current state."""
    from fpstune.settings.executors.nvprofile import NvProfileExecutor

    # wait=True sleep-polls up to 15 s for an in-flight detection, so it runs off the loop.
    gpu, _ = await asyncio.to_thread(hardware_manager.get_gpu_info, wait=True)
    if not gpu or gpu.vendor.lower() != "nvidia":
        # The panel's own VRR answer is vendor-neutral (EDID), so it is still
        # reported. What is missing is fpstune's driver-side tuning for this
        # vendor — a product gap (C10, tracked), never a verdict about the
        # hardware: "not built yet" and "not supported" are different claims.
        monitors = await asyncio.to_thread(hardware_manager.detect_monitors)
        primary = primary_monitor(monitors)
        return VrrOptimizationInfo(
            monitor_name=(primary.friendly_name or primary.name) if primary else "N/A",
            monitor_refresh_hz=refresh_ceiling_hz(primary) if primary else 0,
            supports_vrr=primary.supports_vrr if primary else None,
            recommended_fps_limit=0,
            recommended_vrr_mode="off",
            recommended_vsync="off",
            current_fps_limit=0,
            current_vrr_mode="unknown",
            current_vsync="unknown",
            is_optimized=False,
            explanation=(
                "fpstune's driver-level VRR tuning is built for NVIDIA today; "
                "the AMD and Intel driver paths are not built yet. That is a "
                "gap in fpstune, not a fact about this panel — its own "
                "FreeSync/Adaptive-Sync support is reported above either way."
            ),
            warning=(
                "Driver-level VRR tuning for this GPU vendor is not built yet "
                "(a tracked product gap)."
            ),
        )

    monitors = await asyncio.to_thread(hardware_manager.detect_monitors)
    if not monitors:
        return VrrOptimizationInfo(
            monitor_name="No monitor",
            monitor_refresh_hz=0,
            supports_vrr=False,
            recommended_fps_limit=0,
            recommended_vrr_mode="off",
            recommended_vsync="off",
            current_fps_limit=0,
            current_vrr_mode="unknown",
            current_vsync="unknown",
            is_optimized=False,
            explanation="No monitor detected.",
            warning="Could not detect any connected monitors.",
        )

    if display_index is not None and 0 <= display_index < len(monitors):
        monitor = monitors[display_index]
    else:
        monitor = primary_monitor(monitors) or monitors[0]

    # panel.py's rule: an unknown rate stays 0 and never becomes 60.
    refresh_rate = refresh_ceiling_hz(monitor) or monitor.refresh_rate_hz or 0

    vrr_info = NvProfileExecutor().get_vrr_optimization_info_for_monitor(
        refresh_rate=refresh_rate,
        supports_vrr=monitor.supports_vrr,
    )
    current_fps, current_vrr, current_vsync = await asyncio.to_thread(_vrr_current)

    is_optimized = bool(
        vrr_info["supports_vrr"]
        and current_vrr == vrr_info["recommended_vrr_mode"]
        and current_vsync == vrr_info["recommended_vsync"]
        and current_fps == vrr_info["recommended_fps_limit"]
    )

    # Unknown and unsupported are different answers: the EDID failing to read
    # is a fact about detection, not about the panel.
    warning = None
    if vrr_info["supports_vrr"] is None:
        warning = (
            "This panel's G-Sync/FreeSync support could not be read from its "
            "EDID, so it is unknown — nothing is assumed either way."
        )
    elif not vrr_info["supports_vrr"]:
        warning = (
            "This monitor does not declare G-Sync or FreeSync support. "
            "VRR optimization won't provide benefits. FPS will remain uncapped."
        )

    return VrrOptimizationInfo(
        monitor_name=monitor.friendly_name or monitor.name,
        monitor_refresh_hz=vrr_info["monitor_refresh_hz"],
        supports_vrr=vrr_info["supports_vrr"],
        recommended_fps_limit=vrr_info["recommended_fps_limit"],
        recommended_vrr_mode=vrr_info["recommended_vrr_mode"],
        recommended_vsync=vrr_info["recommended_vsync"],
        current_fps_limit=current_fps,
        current_vrr_mode=current_vrr,
        current_vsync=current_vsync,
        is_optimized=is_optimized,
        explanation=vrr_info["explanation"],
        warning=warning,
    )


def _write_vrr(fps_limit: int, vrr_mode: str, vsync: str) -> None:
    """The three keys in one driver session, so they land together or not at all."""
    from fpstune.core.nv_drs import KEYS, EnumKey, NumberKey
    from fpstune.core.nvapi import write_driver_settings

    fps_key, vrr_key, vsync_key = KEYS["fps_limit"], KEYS["vrr_mode"], KEYS["vsync"]
    assert isinstance(fps_key, NumberKey)
    assert isinstance(vrr_key, EnumKey) and isinstance(vsync_key, EnumKey)
    changes = {
        **fps_key.changes_for(fps_limit),
        **vrr_key.changes_for(vrr_mode),
        **vsync_key.changes_for(vsync),
    }
    write_driver_settings(changes)


async def _apply_vrr(fps_limit: int, vrr_mode: str, vsync: str) -> VrrOptimizationApplyResponse:
    from fpstune.core.nv_drs import KEYS, EnumKey, NumberKey
    from fpstune.core.nvapi import NvapiError, NvapiUnavailable

    gpu, _ = await asyncio.to_thread(hardware_manager.get_gpu_info, wait=True)
    if not gpu or gpu.vendor.lower() != "nvidia":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "fpstune's driver-level VRR tuning for this GPU vendor is not "
                "built yet — a tracked product gap, not a fact about the panel."
            ),
        )

    vrr_key, vsync_key, fps_key = KEYS["vrr_mode"], KEYS["vsync"], KEYS["fps_limit"]
    assert isinstance(vrr_key, EnumKey) and isinstance(vsync_key, EnumKey)
    assert isinstance(fps_key, NumberKey)
    if vrr_mode not in vrr_key.values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vrr_mode: {vrr_mode}. Must be one of {', '.join(vrr_key.values)}.",
        )
    if vsync not in vsync_key.values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vsync: {vsync}. Must be one of {', '.join(vsync_key.values)}.",
        )
    if not 0 <= fps_limit <= fps_key.maximum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid fps_limit: {fps_limit}. Must be 0-{fps_key.maximum}.",
        )

    try:
        await asyncio.to_thread(_write_vrr, fps_limit, vrr_mode, vsync)
    except NvapiUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The NVIDIA driver settings interface is not available: {exc}",
        ) from exc
    except NvapiError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The NVIDIA driver did not accept the change: {exc}",
        ) from exc

    return VrrOptimizationApplyResponse(
        success=True,
        message=f"G-Sync settings applied: VRR={vrr_mode}, VSync={vsync}, FPS limit={fps_limit}",
        applied_fps_limit=fps_limit,
        applied_vrr_mode=vrr_mode,
        applied_vsync=vsync,
    )


@router.post("/vrr-optimization/apply", response_model=VrrOptimizationApplyResponse)
async def apply_vrr_optimization(
    request: VrrOptimizationApplyRequest,
) -> VrrOptimizationApplyResponse:
    """Write VRR mode, V-Sync and the frame cap — those three keys and no others."""
    return await _apply_vrr(request.fps_limit, request.vrr_mode, request.vsync)


@router.post("/vrr-optimization/reset", response_model=VrrOptimizationApplyResponse)
async def reset_vrr_optimization() -> VrrOptimizationApplyResponse:
    """Return the three keys to the driver's own defaults."""
    from fpstune.core.nv_drs import KEYS

    return await _apply_vrr(
        int(KEYS["fps_limit"].stock),
        str(KEYS["vrr_mode"].stock),
        str(KEYS["vsync"].stock),
    )
