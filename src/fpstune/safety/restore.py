"""System Restore Point management for fpstune."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from dataclasses import dataclass

from fpstune.utils.powershell import escape_single_quoted

logger = logging.getLogger(__name__)

# Descriptions reach this module from an HTTP query parameter, so they are
# attacker-shaped: bound the length and drop control characters before any
# command string is built from them.
_MAX_DESCRIPTION_LENGTH = 128


def _sanitize_description(description: str) -> str:
    """Reduce a caller-supplied description to printable, bounded text."""
    cleaned = "".join(ch for ch in description if ch.isprintable())
    return cleaned[:_MAX_DESCRIPTION_LENGTH].strip() or "fpstune backup"


def system_restore_enabled() -> bool:
    """Return False when System Restore / System Protection is off.

    The registry read, not the PowerShell probe: this runs on the pre-apply hot
    path, where a subprocess would cost more than the answer is worth. Windows
    11 ships with System Protection OFF by default, in which case
    Checkpoint-Computer fails ("ServiceDisabled"). RPSessionInterval == 0 is the
    reliable "protection off" signal; the legacy srservice Start==4 check is
    kept as a fallback for older systems where srservice still exists.
    """
    if sys.platform != "win32":
        return False

    import winreg

    # System Protection state: RPSessionInterval == 0 → disabled.
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore",
        ) as k:
            interval, _ = winreg.QueryValueEx(k, "RPSessionInterval")
            if int(interval) == 0:
                return False
    except OSError:
        pass  # value/key absent → fall through to the service check

    # Legacy service check: Start == 4 means the service is Disabled.
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\srservice",
        ) as k:
            start_type, _ = winreg.QueryValueEx(k, "Start")
            return int(start_type) != 4
    except OSError:
        return True  # key absent (modern Windows) → assume available


def create_restore_point_async() -> None:
    """Fire-and-forget restore point creation via PowerShell Checkpoint-Computer.

    Runs in a daemon thread so it never blocks the apply pipeline. Silently
    skipped when System Restore / System Protection is disabled.
    """
    if not system_restore_enabled():
        logger.debug("System Restore service is disabled — skipping restore point")
        return

    def _run() -> None:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "Checkpoint-Computer -Description 'fpstune pre-apply' -RestorePointType MODIFY_SETTINGS",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                if "servicedisabled" in err.lower() or "disabled" in err.lower():
                    # Expected when System Protection is off — fpstune's own
                    # per-setting backup still applies. Keep it quiet (one line).
                    logger.info(
                        "Restore point skipped: System Restore is turned off on this system."
                    )
                else:
                    logger.warning(
                        "Restore point creation failed: %s",
                        err.splitlines()[0] if err else "unknown error",
                    )
            else:
                logger.info("Restore point created before bulk apply")
        except Exception as exc:
            logger.warning("Restore point skipped: %s", exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@dataclass
class RestorePointInfo:
    """System restore point information."""

    sequence_number: int
    description: str
    creation_time: str
    restore_point_type: str


class RestorePointManager:
    """Windows System Restore Point management.

    Every point this manager creates is a MODIFY_SETTINGS one, and that is not
    a default: fpstune installs nothing and uninstalls nothing, so the other
    Checkpoint-Computer types describe an event that never happens here. The
    type is therefore fixed at the two call sites rather than passed in.
    """

    def __init__(self) -> None:
        """Initialize RestorePointManager."""
        self._available = sys.platform == "win32"

    @property
    def is_available(self) -> bool:
        """Check if restore point operations are available."""
        return self._available

    def create_restore_point(self, description: str = "fpstune optimization backup") -> bool:
        """Create a system restore point.

        Args:
            description: Description for the restore point.

        Returns:
            True if restore point was created successfully.
        """
        if not self._available:
            return False

        try:
            # Use PowerShell to create restore point (requires admin privileges).
            # The description goes into a SINGLE-quoted literal: a double-quoted
            # one evaluates $(...) without needing a quote break, which turned a
            # bare query parameter into elevated code execution.
            safe_description = escape_single_quoted(_sanitize_description(description))
            ps_script = f"""
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            Checkpoint-Computer -Description '{safe_description}' -RestorePointType 'MODIFY_SETTINGS'
            """

            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=120,  # Restore points can take a while
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )

            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def create_restore_point_wmi(self, description: str = "fpstune optimization backup") -> bool:
        """Create a system restore point using WMI.

        Alternative method that may work when PowerShell method fails.

        Args:
            description: Description for the restore point.

        Returns:
            True if restore point was created successfully.
        """
        if not self._available:
            return False

        try:
            # Use WMIC to create restore point. The description travels inside
            # wmic's own quoting, so embedded double quotes are stripped — they
            # are the only way out of that argument.
            safe_description = _sanitize_description(description).replace('"', "")
            result = subprocess.run(
                [
                    "wmic.exe",
                    "/Namespace:\\\\root\\default",
                    "Path",
                    "SystemRestore",
                    "Call",
                    "CreateRestorePoint",
                    f'"{safe_description}"',
                    "100",
                    "12",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )

            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def list_restore_points(self, limit: int = 10) -> list[RestorePointInfo]:
        """List available system restore points.

        Args:
            limit: Maximum number of restore points to return.

        Returns:
            List of RestorePointInfo objects.
        """
        if not self._available:
            return []

        try:
            ps_script = f"""
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            Get-ComputerRestorePoint | Select-Object -First {limit} | ForEach-Object {{
                "$($_.SequenceNumber)|$($_.Description)|$($_.CreationTime)|$($_.RestorePointType)"
            }}
            """

            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                return []

            restore_points = []
            for line in result.stdout.strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    try:
                        restore_points.append(
                            RestorePointInfo(
                                sequence_number=int(parts[0]),
                                description=parts[1],
                                creation_time=parts[2],
                                restore_point_type=parts[3],
                            )
                        )
                    except (ValueError, IndexError):
                        continue

            return restore_points
        except (subprocess.SubprocessError, OSError):
            return []

    def is_system_restore_enabled(self) -> bool:
        """Check if System Restore is enabled.

        Returns:
            True if System Restore is enabled on the system drive.
        """
        if not self._available:
            return False

        try:
            ps_script = """
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            $status = Get-ComputerRestorePoint -ErrorAction SilentlyContinue
            if ($status -ne $null) { "enabled" } else { "disabled" }
            """

            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )

            return "enabled" in result.stdout.lower()
        except (subprocess.SubprocessError, OSError):
            return False

    def get_restore_point_by_fpstune(self) -> RestorePointInfo | None:
        """Get the most recent restore point created by fpstune.

        Returns:
            RestorePointInfo or None if not found.
        """
        restore_points = self.list_restore_points(limit=50)

        for rp in restore_points:
            if "fpstune" in rp.description.lower():
                return rp

        return None

    def restore_to_point(self, sequence_number: int) -> bool:
        """Initiate system restore to a specific restore point.

        WARNING: This will restart the computer!

        Args:
            sequence_number: Restore point sequence number.

        Returns:
            True if restore was initiated (computer will restart).
        """
        if not self._available:
            return False

        try:
            # This requires elevation and will restart the computer
            result = subprocess.run(
                [
                    "rstrui.exe",
                    f"/RUNONCE:{sequence_number}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )

            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
