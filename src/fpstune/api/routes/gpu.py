"""GPU API routes.

Provides convenience endpoints for GPU settings that wrap the unified settings system.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fpstune.api.routes.settings import _apply_one, _get_hardware_context, _get_registry
from fpstune.api.schemas import GpuAmdApplyRequest, GpuDetectResponse, GpuNvidiaApplyRequest
from fpstune.settings import DetectionEngine
from fpstune.utils.detect import GpuVendor, get_gpu_info, get_gpu_vendor

router = APIRouter()


# === Response Models ===
#
# The request models and GpuDetectResponse live in api/schemas.py, which is the
# one place a payload shape is declared. This module used to declare its own
# copies; they drifted to `str` where the canonical ones are `Literal`, and the
# AMD copy never grew `anti_lag_2`, so the two disagreed about which fields
# exist for the same endpoint.


class GpuApplyResponse(BaseModel):
    """Response after applying GPU settings."""

    success: bool
    message: str
    applied: dict[str, Any] = {}
    errors: dict[str, str] = {}
    requires_reboot: bool = False


# === Endpoints ===


@router.get("/detect", response_model=GpuDetectResponse)
async def detect_gpu() -> GpuDetectResponse:
    """Detect installed GPU."""
    # A cold or in-flight cache waits on the background detection thread, so
    # this never runs on the event loop.
    gpu_info = await asyncio.to_thread(get_gpu_info)

    if gpu_info:
        return GpuDetectResponse(
            vendor=gpu_info.vendor.value,
            name=gpu_info.name,
            driver_version=gpu_info.driver_version,
            vram_mb=gpu_info.vram_mb,
        )
    else:
        return GpuDetectResponse(vendor=GpuVendor.UNKNOWN.value)


@router.get("/settings")
async def get_gpu_settings() -> dict[str, Any]:
    """Get current GPU settings from unified settings system."""
    vendor = await asyncio.to_thread(get_gpu_vendor)

    if vendor == GpuVendor.UNKNOWN:
        return {"vendor": "unknown", "settings": {}}

    # Determine category prefix based on vendor
    category_prefix = f"gpu-{vendor.value}:"

    def _collect() -> dict[str, Any]:
        # Reuse the cached registry singleton (ARCH-11/PERF-02) and run the
        # synchronous detection subprocess off the event loop (PERF-07).
        registry = _get_registry()
        engine = DetectionEngine()
        gpu_settings = [s for s in registry.get_all() if s.id.startswith(category_prefix)]
        if not gpu_settings:
            return {}
        detection_results = engine.detect_all(gpu_settings)
        return {
            setting_id.split(":")[-1]: result.value
            for setting_id, result in detection_results.items()
        }

    settings_dict = await asyncio.to_thread(_collect)

    return {
        "vendor": vendor.value,
        "settings": settings_dict,
    }


def _apply_gpu_settings(vendor_prefix: str, settings_map: dict[str, Any]) -> GpuApplyResponse:
    """Apply GPU settings using the unified settings system.

    Each setting goes through ``_apply_one`` — the same applicability check,
    apply, detect and verify chain the settings routes use. A write the driver
    silently rejected is therefore reported as a failure rather than assumed to
    have landed, and ``_finalize_apply_response`` logs each outcome, so no
    aggregate ``log_activity`` is added here (that would duplicate the single
    post-apply path).

    Args:
        vendor_prefix: GPU vendor prefix (e.g., "gpu-nvidia", "gpu-amd")
        settings_map: Map of setting names to values

    Returns:
        GpuApplyResponse with results
    """
    registry = _get_registry()
    hardware_context = _get_hardware_context()

    applied: dict[str, Any] = {}
    errors: dict[str, str] = {}
    any_reboot = False

    for setting_name, value in settings_map.items():
        setting_id = f"{vendor_prefix}:{setting_name}"
        setting = registry.get(setting_id)

        if not setting:
            errors[setting_name] = f"Unknown setting: {setting_id}"
            continue

        _, response = _apply_one(
            setting, value, hardware_context, "Applied", skip_when_inapplicable=False
        )

        if response.success:
            applied[setting_name] = value
            if response.requires_reboot:
                any_reboot = True
        else:
            errors[setting_name] = response.error or "Unknown error"

    total = len(settings_map)
    success_count = len(applied)

    if success_count == total:
        message = f"All {total} GPU settings applied and verified"
    elif success_count > 0:
        message = f"{success_count}/{total} GPU settings applied, {len(errors)} failed"
    else:
        message = f"Failed to apply GPU settings: {len(errors)} errors"

    return GpuApplyResponse(
        success=len(errors) == 0,
        message=message,
        applied=applied,
        errors=errors,
        requires_reboot=any_reboot,
    )


@router.post("/nvidia/apply", response_model=GpuApplyResponse)
async def apply_nvidia_settings(request: GpuNvidiaApplyRequest) -> GpuApplyResponse:
    """Apply NVIDIA GPU settings."""
    vendor = await asyncio.to_thread(get_gpu_vendor)
    if vendor != GpuVendor.NVIDIA:
        raise HTTPException(status_code=400, detail="NVIDIA GPU not detected")

    settings_map = {
        "low_latency": request.low_latency,
        "power_mode": request.power_mode,
        "threaded_opt": request.threaded_opt,
        "shader_cache": request.shader_cache,
        "vsync": request.vsync,
    }

    return await asyncio.to_thread(_apply_gpu_settings, "gpu-nvidia", settings_map)


@router.post("/amd/apply", response_model=GpuApplyResponse)
async def apply_amd_settings(request: GpuAmdApplyRequest) -> GpuApplyResponse:
    """Apply AMD GPU settings."""
    vendor = await asyncio.to_thread(get_gpu_vendor)
    if vendor != GpuVendor.AMD:
        raise HTTPException(status_code=400, detail="AMD GPU not detected")

    settings_map: dict[str, Any] = {
        "anti_lag": request.anti_lag,
        "shader_cache": request.shader_cache,
        "vsync": request.vsync,
    }
    # `anti_lag_2` is part of the canonical request but no `gpu-amd:anti_lag_2`
    # executor is registered yet (C10 symmetry gap). Forwarding it always would
    # make every AMD apply report an unknown-setting failure; forwarding it only
    # when the caller actually asked keeps the gap loud for that caller and
    # silent for the one who never mentioned it.
    if "anti_lag_2" in request.model_fields_set:
        settings_map["anti_lag_2"] = request.anti_lag_2

    return await asyncio.to_thread(_apply_gpu_settings, "gpu-amd", settings_map)


@router.post("/apply", response_model=GpuApplyResponse)
async def apply_gpu_settings(
    low_latency: Literal["off", "on", "ultra"] = "on",
    power_mode: Literal["optimal", "adaptive", "maximum"] = "optimal",
    vsync: Literal["off", "on"] = "off",
) -> GpuApplyResponse:
    """Apply GPU settings (auto-detect vendor).

    An omitted query parameter means "apply what fpstune advises", so each
    default is the setting's own ``recommended_value`` — the same reading
    ``GpuNvidiaApplyRequest`` and ``GpuAmdApplyRequest`` carry, and the reason
    all three endpoints answer an empty request identically. The two that used
    to differ were the two this product exists to argue against: ``"ultra"`` is
    the ``low_latency`` value ``ANTICHEAT_WARNINGS`` names as ban-risky, and
    ``"maximum"`` is "Prefer maximum performance", which buys no frames and
    holds the clocks up all session.

    ``vsync`` is the two values both vendors accept; NVIDIA's third option
    ("adaptive") is reachable through ``/nvidia/apply``, which is typed against
    the NVIDIA setting's own choices.

    An unsupported vendor answers 400, the same as ``/nvidia/apply`` and
    ``/amd/apply``: one condition, one shape. It used to answer 200 with a
    ``success=False`` body carrying a fabricated ``errors["vendor"]`` entry —
    a per-setting error key for something that is not a setting — so a client
    had to handle two shapes for the same condition.
    """
    vendor = await asyncio.to_thread(get_gpu_vendor)

    if vendor == GpuVendor.NVIDIA:
        nvidia_request = GpuNvidiaApplyRequest(
            low_latency=low_latency,
            power_mode=power_mode,
            vsync=vsync,
        )
        return await apply_nvidia_settings(nvidia_request)
    if vendor == GpuVendor.AMD:
        amd_request = GpuAmdApplyRequest(
            vsync=vsync,
        )
        return await apply_amd_settings(amd_request)
    raise HTTPException(status_code=400, detail="No supported GPU detected")
