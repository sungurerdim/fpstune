"""Safety API routes.

The manifest-based backup/revert system was removed: its state store was never
populated (``record_setting`` had no callers), so every "backup" it produced was
empty while telling the user one had been created. Windows System Restore is the
supported rollback path, and the apply/reset endpoints create a restore point
before mutating anything.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from fpstune.safety.restore import RestorePointManager
from fpstune.utils.logger import log_activity

router = APIRouter()


@router.post("/restore-point")
async def create_restore_point(description: str = "fpstune optimization") -> dict[str, Any]:
    """Create a Windows System Restore Point."""
    restore_mgr = RestorePointManager()

    if not restore_mgr.is_available:
        return {
            "success": False,
            "message": "System Restore not available on this platform",
        }

    # Checkpoint-Computer runs up to 120 s; inline it would block the event loop
    # for every other request that long.
    if await asyncio.to_thread(restore_mgr.create_restore_point, description):
        log_activity("System restore point created", "success")
        return {
            "success": True,
            "message": "System restore point created successfully",
        }
    else:
        log_activity("Failed to create system restore point", "warning")
        return {
            "success": False,
            "message": "Failed to create restore point. Check if System Restore is enabled.",
        }
