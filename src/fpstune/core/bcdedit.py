"""Boot Configuration Data (BCD) operations for fpstune."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass
class BcdValue:
    """BCD value container."""

    name: str
    value: str
    exists: bool

    def to_dict(self) -> dict[str, str | bool]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "exists": self.exists,
        }


class BcdEdit:
    """Windows Boot Configuration Data (BCD) operations wrapper.

    This class wraps bcdedit.exe for modifying boot configuration,
    particularly timer-related settings like:
    - useplatformclock: Forces use of platform timer (HPET/ACPI PM)
    - useplatformtick: Uses platform timer for tick generation
    - disabledynamictick: Disables dynamic tick (tickless kernel)

    All operations require Administrator privileges.
    """

    # Timer-related BCD settings
    SETTINGS = {
        "useplatformclock": {
            "description": "Use platform clock (HPET/ACPI PM) instead of TSC",
            "recommendation": "delete",  # Better to use TSC
        },
        "useplatformtick": {
            "description": "Use platform timer for tick generation",
            "recommendation": "yes",  # Use TSC for tick generation (lower DPC latency)
        },
        "disabledynamictick": {
            "description": "Disable dynamic tick (tickless kernel)",
            "recommendation": "yes",  # Consistent frame timing
        },
    }

    # Cached BCD enum output for batch queries
    _enum_cache: str | None = None
    _enum_cache_valid: bool = False

    def __init__(self) -> None:
        """Initialize BcdEdit wrapper."""
        self._available = sys.platform == "win32"

    def invalidate_cache(self) -> None:
        """Invalidate the BCD enum cache after modifications."""
        BcdEdit._enum_cache = None
        BcdEdit._enum_cache_valid = False

    def _get_enum_output(self, force_refresh: bool = False) -> str:
        """Get cached bcdedit /enum output.

        Args:
            force_refresh: Force re-running bcdedit even if cached.

        Returns:
            The bcdedit /enum output string.
        """
        if not force_refresh and BcdEdit._enum_cache_valid and BcdEdit._enum_cache:
            return BcdEdit._enum_cache

        success, output = self._run_bcdedit("/enum", "{current}")
        if success:
            BcdEdit._enum_cache = output
            BcdEdit._enum_cache_valid = True
            return output
        return ""

    def get_all_values(self, names: list[str] | None = None) -> dict[str, BcdValue]:
        """Get multiple BCD values in a single bcdedit call.

        Args:
            names: List of value names to get. If None, gets all SETTINGS.

        Returns:
            Dictionary of name -> BcdValue.
        """
        if not self._available:
            return {}

        if names is None:
            names = list(self.SETTINGS.keys())

        output = self._get_enum_output()
        if not output:
            return {name: BcdValue(name=name, value="", exists=False) for name in names}

        # Parse all values from single output
        result: dict[str, BcdValue] = {}
        output_lower = output.lower()

        for name in names:
            found = False
            for line in output_lower.splitlines():
                line = line.strip()
                if line.startswith(name.lower()):
                    parts = line.split()
                    if len(parts) >= 2:
                        result[name] = BcdValue(name=name, value=parts[-1], exists=True)
                        found = True
                        break
            if not found:
                result[name] = BcdValue(name=name, value="", exists=False)

        return result

    @property
    def is_available(self) -> bool:
        """Check if bcdedit operations are available."""
        return self._available

    def _run_bcdedit(self, *args: str) -> tuple[bool, str]:
        """Run bcdedit.exe command.

        Returns:
            Tuple of (success, output).
        """
        if not self._available:
            return False, "Not available on this platform"

        try:
            result = subprocess.run(
                ["bcdedit.exe", *args],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def get_value(self, name: str) -> BcdValue | None:
        """Get a BCD value (uses cached enum output).

        Args:
            name: Value name (e.g., 'useplatformclock').

        Returns:
            BcdValue or None if error.
        """
        if not self._available:
            return None

        # Use batch method with cache
        values = self.get_all_values([name])
        return values.get(name, BcdValue(name=name, value="", exists=False))

    def set_value(self, name: str, value: str) -> bool:
        """Set a BCD value.

        Args:
            name: Value name.
            value: Value to set (e.g., 'yes', 'no').

        Returns:
            True if set successfully.
        """
        if not self._available:
            return False

        success, _ = self._run_bcdedit("/set", "{current}", name, value)
        if success:
            self.invalidate_cache()
        return success

    def delete_value(self, name: str) -> bool:
        """Delete a BCD value (restore to default).

        Args:
            name: Value name.

        Returns:
            True if deleted (or didn't exist).
        """
        if not self._available:
            return False

        success, output = self._run_bcdedit("/deletevalue", "{current}", name)
        # Consider success if value didn't exist
        if not success and "element not found" in output.lower():
            self.invalidate_cache()
            return True
        if success:
            self.invalidate_cache()
        return success

    def disable_hpet(self) -> bool:
        """Disable HPET (High Precision Event Timer).

        This deletes useplatformclock to use TSC instead of HPET.
        TSC is faster and preferred for gaming.

        Returns:
            True if successful.
        """
        return self.delete_value("useplatformclock")

    def enable_hpet(self) -> bool:
        """Enable HPET (High Precision Event Timer).

        Sets useplatformclock to yes to force HPET usage.
        Generally not recommended for gaming.

        Returns:
            True if successful.
        """
        return self.set_value("useplatformclock", "yes")

    def disable_dynamic_tick(self) -> bool:
        """Disable dynamic tick (tickless kernel).

        This can improve latency consistency but increases power usage.
        Recommended for desktop gaming systems.

        Returns:
            True if successful.
        """
        return self.set_value("disabledynamictick", "yes")

    def enable_dynamic_tick(self) -> bool:
        """Enable dynamic tick (restore default).

        Returns:
            True if successful.
        """
        return self.delete_value("disabledynamictick")

    def enable_platform_tick(self) -> bool:
        """Enable useplatformtick for TSC-based tick generation.

        This uses TSC for tick generation which provides lower DPC latency
        compared to the default platform timer.

        Returns:
            True if successful.
        """
        return self.set_value("useplatformtick", "yes")

    def disable_platform_tick(self) -> bool:
        """Disable useplatformtick (restore default).

        Returns:
            True if successful.
        """
        return self.delete_value("useplatformtick")

    def get_timer_settings(self) -> dict[str, BcdValue]:
        """Get all timer-related BCD settings (batched).

        Returns:
            Dictionary of setting name to BcdValue.
        """
        return self.get_all_values(list(self.SETTINGS.keys()))

    def apply_gaming_settings(self) -> dict[str, bool]:
        """Apply recommended gaming settings.

        Returns:
            Dictionary of setting name to success status.
        """
        results = {}

        # Disable HPET (use TSC)
        results["useplatformclock"] = self.disable_hpet()

        # disabledynamictick is hardware-dependent, so we leave it optional
        # Users can enable it via config if needed

        return results

    def revert_to_defaults(self) -> dict[str, bool]:
        """Revert all timer settings to Windows defaults.

        Returns:
            Dictionary of setting name to success status.
        """
        results = {}

        for name in self.SETTINGS:
            results[name] = self.delete_value(name)

        return results

    def get_qpc_mode(self, bcd_values: dict[str, BcdValue] | None = None) -> str:
        """Get the current QPC (QueryPerformanceCounter) mode.

        QPC can use:
        - TSC (Time Stamp Counter) - fastest, preferred
        - HPET (High Precision Event Timer) - older, slower
        - ACPI PM Timer - slowest, legacy

        Args:
            bcd_values: Pre-fetched BCD values (optimization). If None, fetches fresh.

        Returns:
            Description of current mode.
        """
        if bcd_values is None:
            bcd_values = self.get_all_values(["useplatformclock"])

        useplatformclock = bcd_values.get("useplatformclock")

        if useplatformclock and useplatformclock.exists and useplatformclock.value == "yes":
            return "HPET/ACPI PM Timer (platform clock forced)"
        else:
            return "TSC (Time Stamp Counter) - optimal"
