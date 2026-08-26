"""Power profile and elevation API routes (split from routes/system.py)."""

from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, HTTPException

from fpstune.utils.logger import activity_log

router = APIRouter()


@router.get("/power-profile/status")
async def get_power_profile_status() -> dict[str, Any]:
    """Get FPS Balanced power profile status.

    Returns:
        Dict with power profile status including whether FPS Balanced
        profile exists and is active.
    """
    from fpstune.core.power_profile import get_power_profile_manager

    manager = get_power_profile_manager()
    status = manager.status()

    return {
        "active_plan": status.get("active_plan", "Unknown"),
        "active_guid": status.get("active_guid", ""),
        "fps_balanced_exists": status.get("fps_balanced_exists", False),
        "fps_balanced_active": status.get("fps_balanced_active", False),
        "optimizations": status.get("optimizations", []),
    }


@router.post("/power-profile/activate")
async def activate_power_profile() -> dict[str, Any]:
    """Activate FPS Balanced power profile.

    Creates the profile if it doesn't exist.

    Returns:
        Dict with success status and profile GUID.
    """
    from fpstune.core.power_profile import get_power_profile_manager

    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    manager = get_power_profile_manager()
    result = manager.activate()

    if result.success:
        activity_log.log("Activated FPS Balanced power profile", level="info")
        return {
            "success": True,
            "message": result.message,
            "profile_guid": result.profile_guid,
        }
    else:
        raise HTTPException(status_code=500, detail=result.message)


@router.post("/power-profile/revert")
async def revert_power_profile() -> dict[str, Any]:
    """Revert to Balanced power profile.

    Returns:
        Dict with success status.
    """
    from fpstune.core.power_profile import get_power_profile_manager

    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    manager = get_power_profile_manager()
    result = manager.revert()

    if result.success:
        activity_log.log("Reverted to Balanced power profile", level="info")
        return {
            "success": True,
            "message": result.message,
        }
    else:
        raise HTTPException(status_code=500, detail=result.message)
