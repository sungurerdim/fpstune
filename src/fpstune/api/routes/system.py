"""System information API routes."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter

from fpstune.api.hardware import (
    get_audio_devices,
    get_detailed_network_adapters,
    get_detailed_storage_drives,
)
from fpstune.api.schemas import (
    ActivityLogEntry,
    ActivityLogResponse,
    AudioDeviceInfo,
    CpuInfo,
    GpuDeviceInfo,
    GpuInfoResponse,
    HardwareContextResponse,
    HardwareInfo,
    ModuleSettingResponse,
    ModuleStatusResponse,
    MonitorInfo,
    NetworkAdapterInfo,
    OverallStatus,
    StorageDriveInfo,
    SystemInfo,
)
from fpstune.api.status_cache import (
    force_refresh,
    get_cached_status,
    start_background_update,
)
from fpstune.utils.admin import is_admin
from fpstune.utils.detect import (
    GpuVendor,
    get_cpu_info,
    get_gpu_info_cached,
    get_ram_info,
)
from fpstune.utils.hardware_manager import hardware_manager
from fpstune.utils.logger import activity_log

router = APIRouter()


logger = logging.getLogger(__name__)

_reported_unknown_cache_keys: set[str] = set()


def _module_setting_from_cache(raw: dict[str, Any]) -> ModuleSettingResponse:
    """Build the response model from a status-cache dict, loudly.

    ``status_cache`` hands over plain dicts, so nothing type-checks the handoff
    and ``ModuleSettingResponse(**raw)`` silently discarded every key the model
    did not declare. A key the model has no field for is logged once with its
    name, so the next divergence is discoverable from the log instead of from a
    missing value in the UI.
    """
    unknown = set(raw) - set(ModuleSettingResponse.model_fields)
    new = unknown - _reported_unknown_cache_keys
    if new:
        _reported_unknown_cache_keys.update(new)
        logger.warning(
            "status cache produced setting keys ModuleSettingResponse cannot carry: %s",
            ", ".join(sorted(new)),
        )
    return ModuleSettingResponse.model_validate(
        {k: v for k, v in raw.items() if k in ModuleSettingResponse.model_fields}
    )


@router.get("/system", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """Get system information.

    GPU info is returned from cache if available, otherwise detection
    starts in background. Check gpu_detecting field to know if detection
    is in progress, then poll /api/gpu for updates.
    """
    # Both are session-stable caches, but the first call of either runs
    # PowerShell, so they stay off the event loop.
    os_info, cpu_info = await asyncio.to_thread(
        lambda: (hardware_manager.detect_os(), get_cpu_info())
    )
    ram_info = get_ram_info()

    # Get cached GPU info (non-blocking, starts detection if needed)
    gpu_info, detecting = get_gpu_info_cached()

    return SystemInfo(
        os_platform=os_info.platform if os_info else "Unknown",
        os_version=os_info.version if os_info else "Unknown",
        os_build=os_info.build if os_info else "0",
        os_edition=os_info.edition if os_info else "Unknown",
        os_display_version=os_info.display_version if os_info else "Unknown",
        is_supported=os_info.is_supported if os_info else False,
        is_admin=is_admin(),
        cpu_name=cpu_info.get("cpu_name", "Unknown"),
        cpu_cores=int(cpu_info.get("core_count", 0)),
        ram_total_mb=ram_info.get("total_mb", 0),
        ram_available_mb=ram_info.get("available_mb", 0),
        gpu_vendor=gpu_info.vendor.value if gpu_info else GpuVendor.UNKNOWN.value,
        gpu_name=gpu_info.name if gpu_info else None,
        gpu_driver=gpu_info.driver_version if gpu_info else None,
        gpu_vram_mb=gpu_info.vram_mb if gpu_info else None,
        gpu_detecting=detecting,
    )


@router.get("/gpu", response_model=GpuInfoResponse)
async def get_gpu_info_endpoint() -> GpuInfoResponse:
    """Get GPU information.

    Returns cached GPU info if available, or detecting=True if detection
    is in progress. Poll this endpoint until detecting=False.
    """
    gpu_info, detecting = get_gpu_info_cached()

    return GpuInfoResponse(
        vendor=gpu_info.vendor.value if gpu_info else GpuVendor.UNKNOWN.value,
        name=gpu_info.name if gpu_info else None,
        driver=gpu_info.driver_version if gpu_info else None,
        vram_mb=gpu_info.vram_mb if gpu_info else None,
        detecting=detecting,
    )


@router.get("/status", response_model=OverallStatus)
async def get_overall_status(refresh: bool = False) -> OverallStatus:
    """Get overall optimization status.

    Returns cached status for fast response. Status is updated in background.
    Use refresh=true to trigger synchronous refresh and wait for completion.

    Args:
        refresh: If True, waits for cache refresh before returning.
    """
    # Start background update if not running
    start_background_update()

    if refresh:
        # Wait for refresh to complete before returning. The refresh is a full
        # detection run (up to 120 s), so it must not hold the event loop.
        await asyncio.to_thread(force_refresh, _wait=True)

    # Get cached status (non-blocking)
    cached, is_loading = get_cached_status()

    # Convert cache to response (modules is now a dict)
    modules = [
        ModuleStatusResponse(
            name=m.name,
            display_name=m.display_name,
            description=m.description,
            status=m.status,
            message=m.message,
            details=m.details,
            changes=m.changes,
            is_available=m.is_available,
            requires_reboot=m.requires_reboot,
            settings=[_module_setting_from_cache(s) for s in m.settings] if m.settings else [],
            loading=getattr(m, "loading", False),
        )
        for m in cached.modules.values()
    ]

    return OverallStatus(
        modules=modules,
        applied_count=cached.applied_count,
        total_count=cached.total_count,
        loading=is_loading,
        is_admin=is_admin(),
    )


@router.get("/activity", response_model=ActivityLogResponse)
async def get_activity_log(limit: int = 50) -> ActivityLogResponse:
    """Get recent activity log."""
    entries = activity_log.get_entries(limit=limit)

    return ActivityLogResponse(
        entries=[
            ActivityLogEntry(
                timestamp=e["timestamp"],
                message=e["message"],
                level=e["level"],
            )
            for e in entries
        ]
    )


@router.get("/hardware", response_model=HardwareInfo)
async def get_hardware_info() -> HardwareInfo:
    """Get all detected hardware information."""
    cpu_info: CpuInfo | None = None
    gpus: list[GpuDeviceInfo] = []
    monitors_list: list[MonitorInfo] = []
    network_adapters: list[NetworkAdapterInfo] = []
    storage_drives: list[StorageDriveInfo] = []
    detecting = False

    # Get GPU info
    gpu_info, gpu_detecting = get_gpu_info_cached()
    if gpu_detecting:
        detecting = True
    if gpu_info and gpu_info.name:
        gpus.append(
            GpuDeviceInfo(
                vendor=gpu_info.vendor.value,
                name=gpu_info.name,
                driver=gpu_info.driver_version,
                vram_mb=gpu_info.vram_mb,
            )
        )

    # Get CPU, monitors, network, storage, audio in parallel, off the event loop.
    # CPU and monitors go through hardware_manager so a cold detection runs its
    # PowerShell at most once per session.
    _cpu_res, _mon_res, _net_res, _stor_res, _audio_res = await asyncio.gather(
        asyncio.to_thread(hardware_manager.detect_cpu),
        asyncio.to_thread(hardware_manager.detect_monitors),
        asyncio.to_thread(get_detailed_network_adapters),
        asyncio.to_thread(get_detailed_storage_drives),
        asyncio.to_thread(get_audio_devices),
        return_exceptions=True,
    )
    if isinstance(_cpu_res, BaseException):
        logger.debug("Failed to get CPU info: %s", _cpu_res)
    elif _cpu_res:
        cpu_info = CpuInfo(
            name=_cpu_res.name,
            physical_cores=_cpu_res.physical_cores,
            logical_cores=_cpu_res.logical_cores,
            base_clock_mhz=_cpu_res.base_clock_mhz,
            architecture=_cpu_res.architecture,
            cache_l3_mb=_cpu_res.cache_l3_mb,
            sockets=_cpu_res.sockets,
            p_cores=_cpu_res.p_cores,
            e_cores=_cpu_res.e_cores,
            is_hybrid=_cpu_res.is_hybrid,
        )
    if isinstance(_mon_res, BaseException):
        logger.debug("Failed to get monitors: %s", _mon_res)
    else:
        monitors_list = [MonitorInfo.from_detected(mon) for mon in _mon_res]
    if isinstance(_net_res, BaseException):
        logger.warning("Failed to get network adapters: %s", _net_res)
    else:
        network_adapters = _net_res
    if isinstance(_stor_res, BaseException):
        logger.debug("Failed to get storage drives: %s", _stor_res)
    else:
        storage_drives = _stor_res
    audio_devices: list[AudioDeviceInfo] = []
    if isinstance(_audio_res, BaseException):
        logger.debug("Failed to get audio devices: %s", _audio_res)
    else:
        audio_devices = _audio_res

    return HardwareInfo(
        cpu=cpu_info,
        gpus=gpus,
        monitors=monitors_list,
        network_adapters=network_adapters,
        storage_drives=storage_drives,
        audio_devices=audio_devices,
        detecting=detecting,
    )


@router.get("/self-check")
async def get_self_check(refresh: bool = False) -> dict[str, Any]:
    """Every detector cross-checked against an independent source (A12).

    Returns the persisted report; ``refresh=true`` (or no report yet) runs the
    checks against the live machine first. A disagreement is a named finding —
    the exact sources compared and what each said.
    """
    from fpstune.utils.self_check import load_last_report, run_self_check

    if not refresh:
        persisted = await asyncio.to_thread(load_last_report)
        if persisted is not None:
            return persisted
    report = await asyncio.to_thread(run_self_check)
    return report.to_dict()


@router.get("/hardware/context", response_model=HardwareContextResponse)
async def get_hardware_context() -> HardwareContextResponse:
    """Get hardware context for setting applicability checks.

    This endpoint returns the hardware context that determines
    which settings are applicable to the current system.
    """
    os_info = hardware_manager.detect_os()
    gpu_info, _ = get_gpu_info_cached()

    # Determine GPU vendors
    gpu_vendor = None
    gpu_vendors: list[str] = []
    gpu_name = None
    if gpu_info:
        gpu_vendor = gpu_info.vendor.value
        gpu_vendors = [gpu_info.vendor.value]
        gpu_name = gpu_info.name

    # Parse Windows build number
    windows_build = 0
    if os_info:
        with contextlib.suppress(ValueError, TypeError):
            windows_build = int(os_info.build)

    # Determine if Windows 11 (build >= 22000)
    is_windows_11 = windows_build >= 22000

    return HardwareContextResponse(
        gpu_vendor=gpu_vendor,
        gpu_vendors=gpu_vendors,
        gpu_name=gpu_name,
        windows_build=windows_build,
        windows_version=os_info.display_version if os_info else "Unknown",
        is_windows_11=is_windows_11,
        is_admin=is_admin(),
    )


# =============================================================================
# Granular Refresh Endpoints (per-category hardware detection)
# =============================================================================


# =============================================================================
# Power Profile Endpoints
# =============================================================================
