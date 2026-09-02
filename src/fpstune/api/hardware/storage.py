"""Physical disks, their free space, and whether TRIM is on.

A drive is identified by ``UniqueId`` — the EUI-64 or serial ``Get-PhysicalDisk``
reports (C5) — never by drive letter, which is a mount point and moves.
"""

from __future__ import annotations

import json
import logging
import sys

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


# The value `storage:trim_enabled` itself writes. Absent means Windows stock,
# which is 0: delete-notify on, TRIM enabled.
_FILESYSTEM_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"
_DELETE_NOTIFY_VALUE = "DisableDeleteNotify"


def _trim_is_enabled() -> bool | None:
    """Whether NTFS delete-notify is on — a machine-wide setting — or None if unreadable.

    Read from the registry value the setting writes, never from ``fsutil`` text:
    fsutil answers in the system language, and the old check matched the text
    for 'NTFS' and tested ``"0" in output``, which could read a localized label
    as a value. A key that cannot be opened is *unknown*, not
    "disabled" (A11): the card shows that it could not tell.
    """
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _FILESYSTEM_KEY,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, _DELETE_NOTIFY_VALUE)
            except FileNotFoundError:
                return True
    except OSError:
        logger.debug("TRIM state could not be read from the registry", exc_info=True)
        return None
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return None


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
                # TRIM is an SSD fact; on anything else it is not applicable, not off.
                trim_enabled=trim_enabled if media_type == "SSD" else None,
                bus_type=str(drive_data.get("BusType")) if drive_data.get("BusType") else None,
                unique_id=str(drive_data.get("UniqueId") or ""),
            )
        )

    logger.debug(f"Detected {len(drives)} storage drives with details")
    return drives
