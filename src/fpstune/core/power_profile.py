"""Power profile management for FPS Balanced mode.

Creates a custom power profile by duplicating Balanced, then writes every
`power:*` powercfg setting's recommended value from
`settings/definitions/power.py` through `PowerCfgExecutor.apply()` — the same
write path a single-setting `POST /settings/{id}/apply` uses. There is exactly
one table of what "FPS Balanced" tunes (C6, "one writer, one AC/DC promise"):
the settings registry, not a second list kept here. Mains (AC) gets the
registry's recommendation; battery (DC) gets Windows' own value for this
machine, because that is what `PowerCfgExecutor.apply()` itself always writes
to DC — nothing in this module chooses a battery value.

`PowerCfgExecutor.apply()` targets every power plan the machine actually uses
(the active plan plus every plan that is not one of Windows' own — see its own
docstring), so the newly duplicated-and-renamed plan is picked up automatically
once it exists; no scheme GUID is threaded through as a parameter.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from dataclasses import dataclass

from fpstune.settings.applicability import ApplicabilityChecker
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.definitions.power import POWER_SETTINGS
from fpstune.settings.executors.powercfg import PowerCfgExecutor
from fpstune.settings.hardware_context import build_hardware_context

logger = logging.getLogger(__name__)

# Well-known power plan GUIDs
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
POWER_SAVER_GUID = "a1841308-3541-4fab-bc81-f71556f20b4a"

# FPS Balanced profile name and identifier
FPS_BALANCED_NAME = "FPS Balanced"
FPS_BALANCED_DESCRIPTION = "Balanced + gaming optimizations (AC only)"


def _registry_powercfg_settings() -> list[SettingExecutor]:
    """The `power:*` settings this plan tunes: powercfg-executed and applicable here.

    Filtered the same way the single-setting apply route decides applicability
    (`ApplicabilityChecker` over `applicable_conditions`), so a setting gated to
    one CPU vendor is skipped here exactly as it would be skipped there. Registry
    settings that are not `PowerCfgExecutor`-driven (hibernation, power
    throttling, the Ryzen plan switch) are machine-wide rather than per-scheme
    and are out of scope for a plan's own values.
    """
    context = build_hardware_context()
    checker = ApplicabilityChecker(context)
    return [
        setting
        for setting in POWER_SETTINGS
        if setting.detect_type is DetectType.POWERCFG and checker.is_applicable(setting)[0]
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

        Duplicates Balanced, renames it, then writes every applicable
        `power:*` powercfg setting's recommended value onto it through
        `PowerCfgExecutor.apply()`. Mains (AC) gets the recommendation; battery
        (DC) gets Windows' own Balanced value for this machine, which is what
        the executor always writes to DC regardless of the AC value asked for.

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

            # Step 3: Apply the registry's recommended power:* values through the
            # same PowerCfgExecutor path every other apply uses (C6). The
            # executor decides the schemes it writes and the DC value it puts
            # back; this loop supplies no values of its own.
            executor = PowerCfgExecutor()
            for setting in _registry_powercfg_settings():
                success, error = executor.apply(setting, setting.recommended_value)
                if success:
                    details.append(f"[AC] {setting.effect}")
                else:
                    details.append(f"[AC] {setting.effect} (failed: {error})")

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
            optimizations_applied = [s.effect for s in _registry_powercfg_settings()]

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
