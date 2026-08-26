"""System Restore Point management for fpstune."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from fpstune.utils.powershell import escape_single_quoted

# Descriptions reach this module from an HTTP query parameter, so they are
# attacker-shaped: bound the length and drop control characters before any
# command string is built from them.
_MAX_DESCRIPTION_LENGTH = 128


def _sanitize_description(description: str) -> str:
    """Reduce a caller-supplied description to printable, bounded text."""
    cleaned = "".join(ch for ch in description if ch.isprintable())
    return cleaned[:_MAX_DESCRIPTION_LENGTH].strip() or "fpstune backup"


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
