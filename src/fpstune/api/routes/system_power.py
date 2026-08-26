"""Power profile and elevation API routes (split from routes/system.py)."""

from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, HTTPException

from fpstune.utils.admin import elevate_if_needed, is_admin
from fpstune.utils.logger import activity_log

router = APIRouter()


@router.post("/elevate")
async def request_elevation() -> dict[str, bool | str]:
    """Request elevation to administrator privileges.

    On Windows, this will trigger a UAC prompt and restart the server
    with elevated privileges. The current process will exit.

    Returns:
        Dict with success status and message.
    """
    if is_admin():
        return {
            "success": True,
            "already_admin": True,
            "message": "Already running with administrator privileges",
        }

    # Attempt elevation (will restart process if successful)
    elevated = elevate_if_needed()

    if elevated:
        # Process will exit, this won't be returned
        return {
            "success": True,
            "already_admin": False,
            "message": "Elevation requested, server will restart",
        }
    else:
        raise HTTPException(
            status_code=403,
            detail="Failed to elevate. Please restart the application as Administrator.",
        )


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
