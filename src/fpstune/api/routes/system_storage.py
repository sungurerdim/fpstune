"""Per-drive storage actions (sibling of system_network/audio/power).

The first storage mutation the UI has ever had (D3): every other device class
had at least one action, storage had only a readout. `Optimize-Volume` is the
one Windows offers per volume — a retrim on an SSD, a defrag on an HDD — and
which of the two is correct is the drive's own `MediaType`, never a caller's
claim (C1: derive from the hardware).
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from typing import Any

from fastapi import APIRouter, HTTPException

from fpstune.api.hardware import get_detailed_storage_drives
from fpstune.utils.admin import is_admin
from fpstune.utils.logger import activity_log
from fpstune.utils.powershell import run_powershell

router = APIRouter()

logger = logging.getLogger(__name__)

# A drive letter is exactly one ASCII letter. Anything else never reaches the
# shell — the path parameter is interpolated into a PowerShell command, and
# this pattern is the boundary validation that keeps it a drive letter.
_DRIVE_LETTER = re.compile(r"^[A-Za-z]$")

# An HDD defrag legitimately runs for minutes; a retrim is seconds. One
# generous ceiling for both, so a slow spinning disk is not reported failed
# mid-pass.
_OPTIMIZE_TIMEOUT_S = 900


@router.post("/storage/{drive_letter}/optimize")
async def optimize_drive(drive_letter: str) -> dict[str, Any]:
    """Run the optimization this drive's own media type calls for.

    SSD → ``Optimize-Volume -ReTrim`` (tells the controller which blocks are
    free). HDD → ``Optimize-Volume -Defrag``. Unknown media → 409, because
    running the wrong pass on the wrong medium is not a fallback: a defrag
    schedules pointless wear on an SSD.
    """
    if not _DRIVE_LETTER.match(drive_letter):
        raise HTTPException(status_code=400, detail="Invalid drive letter")
    if not is_admin():
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    letter = drive_letter.upper()
    drives = await asyncio.to_thread(get_detailed_storage_drives)
    drive = next((d for d in drives if d.drive_letter.upper() == letter), None)
    if drive is None:
        raise HTTPException(status_code=404, detail=f"No drive {letter}: detected")

    if drive.media_type == "SSD":
        flag, verb = "-ReTrim", "retrim"
    elif drive.media_type == "HDD":
        flag, verb = "-Defrag", "defrag"
    else:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Drive {letter}: reports media type "
                f"'{drive.media_type}' — fpstune will not guess which "
                "optimization pass is safe for it."
            ),
        )

    success, output = await asyncio.to_thread(
        run_powershell,
        f"Optimize-Volume -DriveLetter {letter} {flag}",
        _OPTIMIZE_TIMEOUT_S,
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"Optimize-Volume failed: {output}")

    activity_log.log(f"Ran {verb} on drive {letter}:", level="info")
    return {
        "success": True,
        "drive_letter": letter,
        "media_type": drive.media_type,
        "action": verb,
        "message": f"{verb.capitalize()} completed on drive {letter}:",
    }
