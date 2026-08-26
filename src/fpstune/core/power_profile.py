"""Power profile management for FPS Balanced mode.

Creates a custom power profile based on Balanced with gaming optimizations
applied ONLY when plugged in (AC). Battery (DC) uses Balanced defaults.

Safe optimizations applied:
- PCI Express ASPM = Off (eliminates GPU micro-stutter)
- USB Selective Suspend = Disabled (no peripheral wake delay)
- Hard Disk Timeout = 0 (no spin-up delay)

NOT changed (keeps Balanced behavior):
- CPU Min State = 5% (allows idle power saving)
- Processor Idle = Enabled (C-states active)
- Core Parking = Enabled (modern CPUs benefit)
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Well-known power plan GUIDs
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
POWER_SAVER_GUID = "a1841308-3541-4fab-bc81-f71556f20b4a"

# FPS Balanced profile name and identifier
FPS_BALANCED_NAME = "FPS Balanced"
FPS_BALANCED_DESCRIPTION = "Balanced + gaming optimizations (AC only)"

# Power setting GUIDs for optimizations
# Subgroup: USB settings
USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
USB_SELECTIVE_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"

# Subgroup: PCI Express
PCIE_SUBGROUP = "501a4d13-42af-4429-9fd1-a8218c268e20"
PCIE_LINK_STATE = "ee12f906-d277-404b-b6da-e5fa1a576df5"

# Subgroup: Hard Disk
DISK_SUBGROUP = "0012ee47-9041-4b5d-9b77-535fba8b1442"
DISK_TIMEOUT = "6738e2c4-e8a5-4a42-b16a-e040e769756e"

# Optimized values (AC only)
OPTIMIZATIONS = [
    # (subgroup, setting, ac_value, description)
    (PCIE_SUBGROUP, PCIE_LINK_STATE, 0, "PCI-E Link State → Off"),
    (USB_SUBGROUP, USB_SELECTIVE_SUSPEND, 0, "USB Selective Suspend → Disabled"),
    (DISK_SUBGROUP, DISK_TIMEOUT, 0, "Hard Disk Timeout → Never"),
]


@dataclass
class PowerPlan:
    """Power plan information."""

    guid: str
    name: str
    is_active: bool


@dataclass
class PowerProfileResult:
    """Result of a power profile operation."""

    success: bool
    message: str
    profile_guid: str | None = None
    details: list[str] | None = None


class PowerProfileManager:
    """Manages FPS Balanced power profile creation and activation."""

    def __init__(self) -> None:
        self._fps_balanced_guid: str | None = None

    def list_plans(self) -> list[PowerPlan]:
        """List all available power plans.

        Returns:
            List of PowerPlan objects.
        """
        if sys.platform != "win32":
            return []

        plans: list[PowerPlan] = []

        try:
            result = subprocess.run(
                ["powercfg", "/list"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            # Parse output - look for GUIDs and names
            # Format: Power Scheme GUID: xxxx-xxxx  (Name) *
            guid_pattern = (
                r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
            )

            for line in result.stdout.splitlines():
                guid_match = re.search(guid_pattern, line)
                if guid_match:
                    guid = guid_match.group(1).lower()

                    # Extract name (between parentheses or after GUID)
                    name_match = re.search(r"\(([^)]+)\)", line)
                    name = name_match.group(1) if name_match else "Unknown"

                    # Check if active (marked with *)
                    is_active = "*" in line

                    plans.append(PowerPlan(guid=guid, name=name, is_active=is_active))

        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("Failed to list power plans: %s", e)

        return plans

    def get_active_plan(self) -> PowerPlan | None:
        """Get the currently active power plan.

        Returns:
            Active PowerPlan or None.
        """
        plans = self.list_plans()
        for plan in plans:
            if plan.is_active:
                return plan
        return None

    def find_fps_balanced(self) -> str | None:
        """Find existing FPS Balanced profile GUID.

        Returns:
            GUID string if found, None otherwise.
        """
        if self._fps_balanced_guid:
            return self._fps_balanced_guid

        plans = self.list_plans()
        for plan in plans:
            if plan.name == FPS_BALANCED_NAME:
                self._fps_balanced_guid = plan.guid
                return plan.guid

        return None

    def is_fps_balanced_active(self) -> bool:
        """Check if FPS Balanced is the active power plan.

        Returns:
            True if FPS Balanced is active.
        """
        active = self.get_active_plan()
        return bool(active and active.name == FPS_BALANCED_NAME)

    def create(self) -> PowerProfileResult:
        """Create FPS Balanced power profile.

        Duplicates Balanced profile and applies gaming optimizations
        to AC (plugged in) settings only. DC (battery) keeps Balanced defaults.

        Returns:
            PowerProfileResult with success status.
        """
        if sys.platform != "win32":
            return PowerProfileResult(
                success=False,
                message="Power profiles are only available on Windows",
            )

        # Check if already exists
        existing = self.find_fps_balanced()
        if existing:
            return PowerProfileResult(
                success=True,
                message="FPS Balanced profile already exists",
                profile_guid=existing,
            )

        details: list[str] = []

        try:
            # Step 1: Duplicate Balanced profile
            result = subprocess.run(
                ["powercfg", "/duplicatescheme", BALANCED_GUID],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                return PowerProfileResult(
                    success=False,
                    message=f"Failed to duplicate Balanced profile: {result.stderr}",
                )

            # Extract new GUID from output
            guid_pattern = (
                r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
            )
            guid_match = re.search(guid_pattern, result.stdout)
            if not guid_match:
                return PowerProfileResult(
                    success=False,
                    message="Could not find new profile GUID in output",
                )

            new_guid = guid_match.group(1).lower()
            details.append(f"Created profile: {new_guid}")

            # Step 2: Rename the profile
            subprocess.run(
                ["powercfg", "/changename", new_guid, FPS_BALANCED_NAME, FPS_BALANCED_DESCRIPTION],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )
            details.append(f"Renamed to: {FPS_BALANCED_NAME}")

            # Step 3: Apply optimizations to AC only (DC keeps Balanced defaults)
            for subgroup, setting, value, description in OPTIMIZATIONS:
                # Only set AC value - leave DC at Balanced default
                ac_result = subprocess.run(
                    ["powercfg", "/setacvalueindex", new_guid, subgroup, setting, str(value)],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding="utf-8",
                    errors="replace",
                )

                if ac_result.returncode == 0:
                    details.append(f"[AC] {description}")
                else:
                    details.append(f"[AC] {description} (failed)")

            self._fps_balanced_guid = new_guid

            logger.info("Created FPS Balanced profile: %s", new_guid)
            return PowerProfileResult(
                success=True,
                message="FPS Balanced profile created successfully",
                profile_guid=new_guid,
                details=details,
            )

        except (subprocess.SubprocessError, OSError) as e:
            logger.error("Failed to create FPS Balanced profile: %s", e)
            return PowerProfileResult(
                success=False,
                message=f"Error creating profile: {e}",
            )

    def activate(self) -> PowerProfileResult:
        """Activate FPS Balanced power profile.

        Creates the profile if it doesn't exist.

        Returns:
            PowerProfileResult with success status.
        """
        if sys.platform != "win32":
            return PowerProfileResult(
                success=False,
                message="Power profiles are only available on Windows",
            )

        # Create if doesn't exist
        guid = self.find_fps_balanced()
        if not guid:
            create_result = self.create()
            if not create_result.success:
                return create_result
            guid = create_result.profile_guid

        if not guid:
            return PowerProfileResult(
                success=False,
                message="Could not find or create FPS Balanced profile",
            )

        # Activate the profile
        try:
            result = subprocess.run(
                ["powercfg", "/setactive", guid],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                logger.info("Activated FPS Balanced profile")
                return PowerProfileResult(
                    success=True,
                    message="FPS Balanced profile activated",
                    profile_guid=guid,
                )
            else:
                return PowerProfileResult(
                    success=False,
                    message=f"Failed to activate profile: {result.stderr}",
                )

        except (subprocess.SubprocessError, OSError) as e:
            return PowerProfileResult(
                success=False,
                message=f"Error activating profile: {e}",
            )

    def revert(self) -> PowerProfileResult:
        """Revert to Balanced power profile.

        Returns:
            PowerProfileResult with success status.
        """
        if sys.platform != "win32":
            return PowerProfileResult(
                success=False,
                message="Power profiles are only available on Windows",
            )

        try:
            result = subprocess.run(
                ["powercfg", "/setactive", BALANCED_GUID],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                logger.info("Reverted to Balanced profile")
                return PowerProfileResult(
                    success=True,
                    message="Reverted to Balanced power profile",
                    profile_guid=BALANCED_GUID,
                )
            else:
                return PowerProfileResult(
                    success=False,
                    message=f"Failed to revert: {result.stderr}",
                )

        except (subprocess.SubprocessError, OSError) as e:
            return PowerProfileResult(
                success=False,
                message=f"Error reverting profile: {e}",
            )

    def delete(self) -> PowerProfileResult:
        """Delete FPS Balanced power profile.

        Reverts to Balanced first if FPS Balanced is active.

        Returns:
            PowerProfileResult with success status.
        """
        if sys.platform != "win32":
            return PowerProfileResult(
                success=False,
                message="Power profiles are only available on Windows",
            )

        guid = self.find_fps_balanced()
        if not guid:
            return PowerProfileResult(
                success=True,
                message="FPS Balanced profile does not exist",
            )

        # Revert to Balanced if FPS Balanced is active
        if self.is_fps_balanced_active():
            self.revert()

        try:
            result = subprocess.run(
                ["powercfg", "/delete", guid],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                self._fps_balanced_guid = None
                logger.info("Deleted FPS Balanced profile")
                return PowerProfileResult(
                    success=True,
                    message="FPS Balanced profile deleted",
                )
            else:
                return PowerProfileResult(
                    success=False,
                    message=f"Failed to delete profile: {result.stderr}",
                )

        except (subprocess.SubprocessError, OSError) as e:
            return PowerProfileResult(
                success=False,
                message=f"Error deleting profile: {e}",
            )

    def status(self) -> dict[str, str | bool | list[str]]:
        """Get current power profile status.

        Returns:
            Dictionary with status information.
        """
        active = self.get_active_plan()
        fps_balanced_exists = self.find_fps_balanced() is not None

        optimizations_applied: list[str] = []
        if fps_balanced_exists and active and active.name == FPS_BALANCED_NAME:
            optimizations_applied = [desc for _, _, _, desc in OPTIMIZATIONS]

        return {
            "active_plan": active.name if active else "Unknown",
            "active_guid": active.guid if active else "",
            "fps_balanced_exists": fps_balanced_exists,
            "fps_balanced_active": self.is_fps_balanced_active(),
            "optimizations": optimizations_applied,
        }


# Singleton instance
_power_profile_manager: PowerProfileManager | None = None


def get_power_profile_manager() -> PowerProfileManager:
    """Get the singleton PowerProfileManager instance."""
    global _power_profile_manager
    if _power_profile_manager is None:
        _power_profile_manager = PowerProfileManager()
    return _power_profile_manager
