"""Physical disks, their free space, and whether TRIM is on.

A drive is identified by ``UniqueId`` — the EUI-64 or serial ``Get-PhysicalDisk``
reports (C5) — never by drive letter, which is a mount point and moves.
"""

from __future__ import annotations

import json
import logging

from fpstune.api.schemas import StorageDriveInfo
from fpstune.utils.powershell import run_powershell

logger = logging.getLogger(__name__)

# Get physical disk info with bus type and partition info with free space
_STORAGE_SCRIPT = """
    Get-PhysicalDisk | ForEach-Object {
        $disk = $_
        $partitions = Get-Partition -DiskNumber $disk.DeviceId -ErrorAction SilentlyContinue
        foreach ($part in $partitions) {
            if ($part.DriveLetter) {
                $volume = Get-Volume -DriveLetter $part.DriveLetter -ErrorAction SilentlyContinue
                [PSCustomObject]@{
                    DriveLetter = $part.DriveLetter
                    Model = $disk.FriendlyName
                    MediaType = $disk.MediaType
                    BusType = $disk.BusType
                    UniqueId = $disk.UniqueId
                    SizeGB = [math]::Round($part.Size / 1GB)
                    FreeGB = if ($volume) { [math]::Round($volume.SizeRemaining / 1GB) } else { $null }
                }
            }
        }
    } | ConvertTo-Json -Depth 2
    """


def _trim_is_enabled() -> bool:
    """Whether NTFS delete-notify is on, which is a machine-wide setting."""
    try:
        success, output = run_powershell(
            "fsutil behavior query DisableDeleteNotify | Select-String 'NTFS'"
        )
    except Exception:
        logger.debug("TRIM status query failed", exc_info=True)
        return False
    if success and output:
        return "0" in output  # DisableDeleteNotify = 0 means TRIM enabled
    return False


def get_detailed_storage_drives() -> list[StorageDriveInfo]:
    """Get detailed storage drive information including free space and bus type."""
    drives: list[StorageDriveInfo] = []

    success, output = run_powershell(_STORAGE_SCRIPT)

    if not success or not output:
        logger.debug("Enhanced storage detection failed, returning empty list")
        return drives

    try:
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse storage JSON: {e}")
        return drives

    trim_enabled = _trim_is_enabled()

    for drive_data in data:
        if not drive_data:
            continue

        # Skip drives without essential data - don't create entries with fake values
        drive_letter = drive_data.get("DriveLetter")
        model = drive_data.get("Model")
        size_gb = drive_data.get("SizeGB")

        if not drive_letter:
            logger.debug("Skipping drive with missing drive letter")
            continue

        if size_gb is None or size_gb <= 0:
            logger.debug(f"Skipping drive {drive_letter}: with missing/invalid size")
            continue

        media_type = str(drive_data.get("MediaType") or "")
        # Normalize media type
        if "SSD" in media_type:
            media_type = "SSD"
        elif "HDD" in media_type:
            media_type = "HDD"
        else:
            media_type = "Unknown"

        drives.append(
            StorageDriveInfo(
                drive_letter=str(drive_letter),
                model=str(model) if model else "Unknown Model",
                media_type=media_type,
                size_gb=int(size_gb),
                free_gb=drive_data.get("FreeGB"),  # None is valid - means couldn't detect
                trim_enabled=trim_enabled if media_type == "SSD" else False,
                bus_type=str(drive_data.get("BusType")) if drive_data.get("BusType") else None,
                unique_id=str(drive_data.get("UniqueId") or ""),
            )
        )

    logger.debug(f"Detected {len(drives)} storage drives with details")
    return drives
