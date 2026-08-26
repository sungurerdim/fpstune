"""Display/Monitor settings API routes."""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel

from fpstune.api.schemas import MonitorInfo
from fpstune.utils.hardware_manager import hardware_manager

router = APIRouter(prefix="/display", tags=["display"])
logger = logging.getLogger(__name__)

# A display mode write is guarded twice, because a wrong mode on a machine the
# developer is not sitting at is a black screen nobody can debug:
#   1. CDS_TEST first — the driver validates the mode without touching anything,
#      and a mode that fails the test is never written.
#   2. A revert timer — the write goes through, and unless the user confirms
#      within _REVERT_TIMEOUT_S the prior mode is written back: Windows' own
#      "keep these display settings?" pattern. A change whose prior mode could
#      not be read is refused outright — a write that cannot be undone is a
#      one-way door (the Wi-Fi radio lesson).
_REVERT_TIMEOUT_S = 15.0
_pending_lock = threading.Lock()
_pending_reverts: dict[str, dict[str, Any]] = {}

_MODE_CHANGE_SCRIPT = """
Add-Type @'
using System;
using System.Runtime.InteropServices;

public class DisplaySettings {{
    [DllImport("user32.dll")]
    public static extern int ChangeDisplaySettingsEx(
        string lpszDeviceName,
        ref DEVMODE lpDevMode,
        IntPtr hwnd,
        int dwflags,
        IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumDisplaySettings(
        string lpszDeviceName,
        int iModeNum,
        ref DEVMODE lpDevMode);

    public const int CDS_UPDATEREGISTRY = 0x01;
    public const int CDS_TEST = 0x02;
    public const int CDS_GLOBAL = 0x08;
    public const int DISP_CHANGE_SUCCESSFUL = 0;
    public const int ENUM_CURRENT_SETTINGS = -1;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DEVMODE {{
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }}
}}
'@

$device = "{device_name}"

# The mode the machine holds right now, read back before anything changes —
# this is what the revert timer restores. A machine whose current mode cannot
# be read gets no write at all.
$dm = New-Object DisplaySettings+DEVMODE
$dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm)
$null = [DisplaySettings]::EnumDisplaySettings($device, [DisplaySettings]::ENUM_CURRENT_SETTINGS, [ref]$dm)
if ($dm.dmPelsWidth -le 0 -or $dm.dmPelsHeight -le 0 -or $dm.dmDisplayFrequency -le 0) {{
    "NOPRIOR"
}} else {{
    "PRIOR=$($dm.dmPelsWidth)x$($dm.dmPelsHeight)@$($dm.dmDisplayFrequency)"

    # Set new values
    $dm.dmPelsWidth = {target_width}
    $dm.dmPelsHeight = {target_height}
    $dm.dmDisplayFrequency = {target_refresh}
    $dm.dmFields = {fields}  # only the fields that were actually suboptimal

    # CDS_TEST: the driver validates without touching anything. A mode that
    # fails here is never written.
    $test = [DisplaySettings]::ChangeDisplaySettingsEx(
        $device, [ref]$dm, [IntPtr]::Zero, [DisplaySettings]::CDS_TEST, [IntPtr]::Zero)
    if ($test -ne [DisplaySettings]::DISP_CHANGE_SUCCESSFUL) {{
        "TESTFAIL:$test"
    }} else {{
        $result = [DisplaySettings]::ChangeDisplaySettingsEx(
            $device, [ref]$dm, [IntPtr]::Zero, [DisplaySettings]::CDS_UPDATEREGISTRY, [IntPtr]::Zero)
        if ($result -eq [DisplaySettings]::DISP_CHANGE_SUCCESSFUL) {{
            "SUCCESS"
        }} else {{
            "ERROR:$result"
        }}
    }}
}}
"""


def _run_mode_change(
    device_name: str, width: int, height: int, refresh: int, fields: int
) -> tuple[str, tuple[int, int, int] | None]:
    """Run the mode-change script; return (status line, prior mode or None)."""
    script = _MODE_CHANGE_SCRIPT.format(
        device_name=device_name,
        target_width=width,
        target_height=height,
        target_refresh=refresh,
        fields=fields,
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, script built from detected values
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        encoding="utf-8",
        errors="replace",
    )
    prior: tuple[int, int, int] | None = None
    status_line = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("PRIOR="):
            match = re.match(r"PRIOR=(\d+)x(\d+)@(\d+)", line)
            if match:
                prior = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        elif line:
            status_line = line
    return status_line, prior


def _schedule_revert(device_name: str, prior: tuple[int, int, int], fields: int) -> None:
    """Write the prior mode back after the timeout unless the change is kept."""

    def _revert() -> None:
        with _pending_lock:
            _pending_reverts.pop(device_name, None)
        width, height, refresh = prior
        try:
            revert_status, _ = _run_mode_change(device_name, width, height, refresh, fields)
            logger.info(
                "Display %s not confirmed — reverted to %dx%d@%d: %s",
                device_name,
                width,
                height,
                refresh,
                revert_status,
            )
            hardware_manager.invalidate_cache("monitors")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Display revert failed for %s: %s", device_name, exc)

    with _pending_lock:
        stale = _pending_reverts.pop(device_name, None)
        if stale is not None:
            stale["timer"].cancel()
        timer = threading.Timer(_REVERT_TIMEOUT_S, _revert)
        timer.daemon = True
        _pending_reverts[device_name] = {"timer": timer, "prior": prior}
        timer.start()


def _cancel_revert(device_name: str) -> bool:
    """Keep the applied mode: cancel its pending revert. False when none exists."""
    with _pending_lock:
        pending = _pending_reverts.pop(device_name, None)
    if pending is None:
        return False
    pending["timer"].cancel()
    return True


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

    # Write only what is actually wrong. Setting both unconditionally meant that
    # fixing a refresh rate also raised a resolution the user may have lowered on
    # purpose — this project's stated priority is performance first, and dropping
    # resolution for frame rate is a legitimate choice, not a defect to correct.
    DM_PELSWIDTH = 0x00080000
    DM_PELSHEIGHT = 0x00100000
    DM_DISPLAYFREQUENCY = 0x00400000

    fields = 0
    changed: list[str] = []
    if not monitor.is_resolution_optimal:
        fields |= DM_PELSWIDTH | DM_PELSHEIGHT
        changed.append(f"{target_width}x{target_height}")
    if not monitor.is_refresh_optimal:
        fields |= DM_DISPLAYFREQUENCY
        changed.append(f"{target_refresh}Hz")

    # PowerShell script to change display settings using ChangeDisplaySettingsEx
    # Use the actual device name from detection (handles non-contiguous numbering).
    #
    # Detection already returns the full device path, so prefixing unconditionally
    # built a name with the prefix twice over. Windows cannot resolve it, so
    # ChangeDisplaySettingsEx answered DISP_CHANGE_BADPARAM (-5) and this endpoint
    # 500'd for every display on every machine, for as long as it existed. Verified
    # on real hardware after the fix: 200 Hz -> 300 Hz, read back from the mode.
    device_name = monitor.name if monitor.name.startswith("\\\\.\\") else f"\\\\.\\{monitor.name}"

    try:
        status_line, prior = await asyncio.to_thread(
            _run_mode_change, device_name, target_width, target_height, target_refresh, fields
        )

        if status_line == "NOPRIOR":
            # No mode to revert to means no write happened: a change that
            # cannot be undone is a one-way door.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "The display's current mode could not be read, so the change "
                    "was refused — a mode this endpoint could not revert would be "
                    "a one-way door."
                ),
            )
        if status_line.startswith("TESTFAIL:"):
            code = status_line.split(":", 1)[1]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"The driver rejected this mode before anything was written "
                    f"(CDS_TEST returned {code}). Nothing was changed."
                ),
            )
        if status_line != "SUCCESS" or prior is None:
            error_code = (
                status_line.replace("ERROR:", "")
                if status_line.startswith("ERROR:")
                else status_line or "no output"
            )
            logger.error(f"Failed to change display settings: {error_code}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to change display settings (code: {error_code})",
            )

        # The write went through; unless the user keeps it, the prior mode
        # comes back — Windows' own "keep these display settings?" pattern.
        _schedule_revert(device_name, prior, fields)
        hardware_manager.invalidate_cache("monitors")

        return DisplayAutoResponse(
            success=True,
            display_index=display_index,
            resolution=f"{target_width}x{target_height}",
            refresh_rate=target_refresh,
            message=(
                f"Display set to {' and '.join(changed)} — reverts in "
                f"{int(_REVERT_TIMEOUT_S)}s unless kept"
            ),
            requires_confirmation=True,
            revert_timeout_s=_REVERT_TIMEOUT_S,
        )

    except subprocess.TimeoutExpired as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Display settings change timed out",
        ) from e
    except HTTPException:
        # The branches above already raised specific errors carrying the
        # DISP_CHANGE code. Letting the catch-all below swallow them turned
        # "code: -5" into an opaque "Internal server error", which is why the
        # real cause stayed hidden for as long as this endpoint existed.
        raise
    except Exception as e:
        logger.exception("Error changing display settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


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
    if not _cancel_revert(device_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No display change is awaiting confirmation — it may already have reverted.",
        )
    return DisplayConfirmResponse(success=True, message="Display mode kept.")


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
        monitors=[MonitorInfo.from_detected(m) for m in monitors],
    )


@router.get("/monitors")
async def get_all_monitors() -> list[MonitorInfo]:
    """Get all connected monitors with current and native settings.

    Returns:
        List of monitor information payloads.
    """
    monitors = await asyncio.to_thread(hardware_manager.detect_monitors)
    return [MonitorInfo.from_detected(m) for m in monitors]


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


@router.get("/vrr-optimization", response_model=VrrOptimizationInfo)
async def get_vrr_optimization_info(
    display_index: int | None = None,
) -> VrrOptimizationInfo:
    """Get VRR/G-Sync optimization info for a specific monitor.

    Args:
        display_index: 0-based monitor index. If None, uses primary monitor.

    Returns recommended settings based on monitor capabilities.
    User can then choose to apply these settings manually.
    """
    from fpstune.settings.executors.nvprofile import NvProfileExecutor

    # Check if NVIDIA GPU (use centralized hardware_manager). wait=True
    # sleep-polls up to 15 s for an in-flight detection, so it runs off the loop.
    gpu, _ = await asyncio.to_thread(hardware_manager.get_gpu_info, wait=True)
    if not gpu or gpu.vendor.lower() != "nvidia":
        return VrrOptimizationInfo(
            monitor_name="N/A",
            monitor_refresh_hz=0,
            supports_vrr=False,
            recommended_fps_limit=0,
            recommended_vrr_mode="off",
            recommended_vsync="off",
            current_fps_limit=0,
            current_vrr_mode="off",
            current_vsync="off",
            is_optimized=False,
            explanation="VRR optimization is only available for NVIDIA GPUs.",
            warning="Non-NVIDIA GPU detected. G-Sync features not available.",
        )

    # Get monitors
    monitors = await asyncio.to_thread(hardware_manager.detect_monitors)
    if not monitors:
        return VrrOptimizationInfo(
            monitor_name="No monitor",
            monitor_refresh_hz=60,
            supports_vrr=False,
            recommended_fps_limit=0,
            recommended_vrr_mode="off",
            recommended_vsync="off",
            current_fps_limit=0,
            current_vrr_mode="off",
            current_vsync="off",
            is_optimized=False,
            explanation="No monitor detected.",
            warning="Could not detect any connected monitors.",
        )

    # Get target monitor by index or primary
    if display_index is not None and 0 <= display_index < len(monitors):
        monitor = monitors[display_index]
    else:
        monitor = next((m for m in monitors if m.is_primary), monitors[0])

    # The panel's ceiling: mode-list max first, EDID preferred rate only as a
    # fallback (a high-refresh panel's EDID often prefers 60 Hz). The trailing
    # 60 is the forbidden constant panel.py names; deleting it is B5's work.
    refresh_rate = (
        monitor.max_refresh_rate_hz
        or monitor.native_refresh_rate_hz
        or monitor.refresh_rate_hz
        or 60
    )

    # Get VRR optimization info for this specific monitor
    executor = NvProfileExecutor()
    vrr_info = executor.get_vrr_optimization_info_for_monitor(
        refresh_rate=refresh_rate,
        supports_vrr=monitor.supports_vrr,
    )

    # Get current settings from cache
    cache = executor._load_cache()
    current_fps = cache.get("fps_limit", 0)
    current_vrr = cache.get("vrr_mode", "off")
    current_vsync = cache.get("vsync", "off")

    # Check if already optimized for this monitor
    is_optimized = bool(
        vrr_info["supports_vrr"]
        and current_vrr == vrr_info["recommended_vrr_mode"]
        and current_vsync == vrr_info["recommended_vsync"]
        and current_fps == vrr_info["recommended_fps_limit"]
    )

    # Unknown and unsupported are different answers: the EDID failing to read
    # is a fact about detection, not about the panel, and asserting
    # "doesn't support" on it told FreeSync owners their panel had nothing.
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


@router.post("/vrr-optimization/apply", response_model=VrrOptimizationApplyResponse)
async def apply_vrr_optimization(
    request: VrrOptimizationApplyRequest,
) -> VrrOptimizationApplyResponse:
    """Apply VRR/G-Sync optimization settings.

    This sets VRR mode, VSync, and FPS limit as specified by the user.
    """
    from fpstune.settings.executors.nvprofile import NvProfileExecutor

    # Check if NVIDIA GPU (use centralized hardware_manager). wait=True
    # sleep-polls up to 15 s for an in-flight detection, so it runs off the loop.
    gpu, _ = await asyncio.to_thread(hardware_manager.get_gpu_info, wait=True)
    if not gpu or gpu.vendor.lower() != "nvidia":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VRR optimization is only available for NVIDIA GPUs",
        )

    # Validate inputs
    if request.vrr_mode not in ("off", "on", "fullscreen"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vrr_mode: {request.vrr_mode}. Must be off, on, or fullscreen.",
        )

    if request.vsync not in ("off", "on", "adaptive"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vsync: {request.vsync}. Must be off, on, or adaptive.",
        )

    if request.fps_limit < 0 or request.fps_limit > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid fps_limit: {request.fps_limit}. Must be 0-500.",
        )

    try:
        executor = NvProfileExecutor()

        # Load cache and update VRR settings
        cache = executor._load_cache()
        cache["vrr_mode"] = request.vrr_mode
        cache["vsync"] = request.vsync
        cache["fps_limit"] = request.fps_limit

        # Apply settings via NPI
        from fpstune.core.nv_profile import NvidiaProfileInspector

        nv = NvidiaProfileInspector()
        # NPI is an external process; run it off the event loop.
        success, error = await asyncio.to_thread(
            nv.apply_gaming_profile,
            power_mode=cache.get("power_mode", "optimal"),
            low_latency=cache.get("low_latency", "ultra"),
            threaded_opt=cache.get("threaded_opt", "on"),
            vsync=request.vsync,
            shader_cache=cache.get("shader_cache", "on"),
            fps_limit=request.fps_limit,
            vrr_mode=request.vrr_mode,
            bg_app_fps=cache.get("bg_app_fps", 0),  # Off — see gpu-nvidia:bg_app_fps
            aniso_sample_opt=cache.get("aniso_sample_opt", "on"),
            texture_lod_bias=cache.get("texture_lod_bias", "clamp"),
            ogl_thread_opt=cache.get("ogl_thread_opt", "on"),
            cuda_force_p2=cache.get("cuda_force_p2", "off"),
        )

        if success:
            # Save to cache
            executor._save_cache(cache)

            return VrrOptimizationApplyResponse(
                success=True,
                message=f"G-Sync optimization applied: VRR={request.vrr_mode}, "
                f"VSync={request.vsync}, FPS limit={request.fps_limit}",
                applied_fps_limit=request.fps_limit,
                applied_vrr_mode=request.vrr_mode,
                applied_vsync=request.vsync,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to apply VRR settings: {error}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error applying VRR optimization")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post("/vrr-optimization/reset", response_model=VrrOptimizationApplyResponse)
async def reset_vrr_optimization() -> VrrOptimizationApplyResponse:
    """Reset VRR settings to defaults (VRR off, VSync off, FPS unlimited)."""
    return await apply_vrr_optimization(
        VrrOptimizationApplyRequest(
            fps_limit=0,
            vrr_mode="off",
            vsync="off",
        )
    )
