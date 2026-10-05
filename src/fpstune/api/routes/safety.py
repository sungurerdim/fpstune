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

    # Checkpoint-Computer can run for minutes; inline it would block the event
    # loop for every other request that long. It logs its own outcome.
    outcome = await asyncio.to_thread(restore_mgr.create_restore_point, description)
    return {"success": outcome.kind == "created", "message": outcome.message}


@router.get("/history")
async def change_history(limit: int = 500) -> dict[str, Any]:
    """What fpstune changed on this machine, across runs (safety/history.py).

    ``settings`` is one row per setting fpstune ever wrote, newest change first:
    its last action, the value written and when, and whether an undo is still
    possible (an original is on record). ``entries`` is the raw journal, newest
    first, for the full timeline.
    """
    from fpstune.api.routes.settings_apply import undo_refusal
    from fpstune.safety.history import get_change_journal
    from fpstune.safety.originals import get_original_values
    from fpstune.settings.registry_cache import get_registry

    journal = get_change_journal()
    originals = get_original_values()
    registry = await asyncio.to_thread(get_registry)

    def can_undo(setting_id: str) -> bool:
        setting = registry.get(setting_id)
        # A setting no longer registered (an adapter or monitor since removed)
        # has nothing to write to; one that is follows the one undo rule.
        return setting is not None and undo_refusal(setting) is None

    latest = sorted(journal.latest().values(), key=lambda c: c.at, reverse=True)
    return {
        "settings": [
            {
                "setting_id": change.setting_id,
                "last_action": change.action,
                "value": change.value,
                "at": change.at,
                "can_undo": can_undo(change.setting_id),
                "original_value": originals.get(change.setting_id),
            }
            for change in latest
        ],
        "entries": [
            {"setting_id": c.setting_id, "action": c.action, "value": c.value, "at": c.at}
            for c in journal.entries()[: max(0, limit)]
        ],
    }
