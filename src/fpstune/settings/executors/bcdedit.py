"""BcdEdit executor for boot configuration detection and application.

Uses WMI BcdStore for localization-independent detection.
Falls back to bcdedit commands for apply operations (which are locale-safe).
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Any

from fpstune.settings.executors import BaseExecutor, map_raw_to_display

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


# BCD Element Type IDs (locale-independent)
# Reference: https://learn.microsoft.com/en-us/previous-versions/windows/desktop/bcd/bcd-reference
BCD_ELEMENT_TYPES: dict[str, int] = {
    # Boolean elements (BcdLibraryBoolean_*)
    "useplatformclock": 0x26000081,  # BcdOSLoaderBoolean_UsePlatformClock
    "useplatformtick": 0x26000082,  # BcdOSLoaderBoolean_UsePlatformTick
    "disabledynamictick": 0x26000083,  # BcdOSLoaderBoolean_DisableDynamicTick
    # Integer elements
    "tscsyncpolicy": 0x25000084,  # BcdOSLoaderInteger_TscSyncPolicy
}

# TSC Sync Policy values
TSC_SYNC_VALUES: dict[int, str] = {
    0: "default",
    1: "legacy",
    2: "enhanced",
}

# The command line is later tokenized with args.split() in _run, so a value or
# value name containing whitespace would append extra bcdedit arguments (e.g.
# "testsigning on"). BCD names and the values bcdedit accepts for them are all
# single alphanumeric tokens (yes/no/legacy/enhanced/default, integers), so
# anything wider is rejected — the same coerce-before-f-string pattern powercfg
# uses for its numeric indexes.
_BCD_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


class BcdEditExecutor(BaseExecutor):
    """Execute bcdedit commands for boot configuration.

    Handles HPET, dynamic tick, platform tick, etc.

    IMPORTANT: Uses WMI BcdStore for LOCALIZATION-INDEPENDENT detection.
    The old approach of parsing "Yes/No/Evet/Ja" from bcdedit text output
    was locale-dependent and unreliable on non-English Windows.

    Detection is done via WMI BcdStore (returns binary values, not localized text).
    Apply operations still use bcdedit commands (which accept English keywords).
    """

    _cache: dict[str, str | None] | None = None
    _lock: threading.Lock = threading.Lock()

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect a BCD setting value using bcdedit {current}.

        Uses bcdedit /enum {current} to ensure we read from the same boot entry
        that apply writes to. This avoids WMI vs bcdedit inconsistencies.

        The detect_command should be the BCD value name (e.g., "useplatformclock").
        """
        # Use class-level cache for proper sharing across instances
        with BcdEditExecutor._lock:
            if BcdEditExecutor._cache is None:
                try:
                    # Try WMI first (locale-independent, works without admin in some cases)
                    BcdEditExecutor._cache = self._get_all_values_wmi()
                    if not BcdEditExecutor._cache:
                        # WMI returned empty, try bcdedit as fallback
                        BcdEditExecutor._cache = self._get_all_values_bcdedit()
                except RuntimeError as e:
                    # Both WMI and bcdedit failed (not admin)
                    # Return clear error - never assume default values
                    return None, f"Admin required for BCD detection: {e}"

        value_name = setting.detect_command
        raw_value = BcdEditExecutor._cache.get(value_name)

        # Map raw value to display value
        # For BCD, None means "not set" (Windows default)
        if raw_value is not None and setting.value_map:
            mapped = map_raw_to_display(setting.value_map, raw_value)
            if mapped is not raw_value:
                return mapped, None
        if raw_value in setting.value_map:
            return setting.value_map[raw_value], None
        elif None in setting.value_map:
            # Use None mapping for "not set"
            return setting.value_map[None], None
        else:
            return raw_value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Apply a BCD setting value using bcdedit.

        The apply_command should be the BCD value name.
        If apply_value_map returns None for the value, the setting is deleted.

        Note: bcdedit /set and /deletevalue accept English keywords (yes/no/legacy/enhanced)
        regardless of Windows locale, so this is safe.
        """
        from fpstune.utils.debug import debug_log

        value_name = setting.apply_command
        raw_value = setting.apply_value_map.get(value, value)

        debug_log(
            "bcdedit",
            f"APPLY {setting.id}: value_name={value_name}, raw_value={raw_value}",
        )

        if not _BCD_TOKEN.match(value_name):
            return False, f"bcdedit value name must be a single token, got {value_name!r}"
        if raw_value is not None and not _BCD_TOKEN.match(str(raw_value).strip()):
            return False, f"bcdedit requires a single-token value, got {raw_value!r}"

        if raw_value is None:
            # Delete the value (revert to Windows default)
            # Must specify {current} boot entry explicitly
            cmd = f"/deletevalue {{current}} {value_name}"
            debug_log("bcdedit", f"Running: bcdedit {cmd}")
            success, output = self._run(cmd)
            debug_log("bcdedit", f"Result: success={success}, output={output}")
            # deletevalue may fail if value doesn't exist, which is OK
            if (
                not success
                and "not found" not in output.lower()
                and "element" not in output.lower()
            ):
                return False, output
        else:
            # Set the value - must specify {current} boot entry explicitly
            cmd = f"/set {{current}} {value_name} {str(raw_value).strip()}"
            debug_log("bcdedit", f"Running: bcdedit {cmd}")
            success, output = self._run(cmd)
            debug_log("bcdedit", f"Result: success={success}, output={output}")
            if not success:
                return False, output

        # Invalidate cache after changes (use class method for class-level variable)
        with BcdEditExecutor._lock:
            BcdEditExecutor._cache = None
        return True, None

    def _get_all_values_wmi(self) -> dict[str, str | None]:
        """Get all BCD values using WMI BcdStore (locale-independent).

        This method uses PowerShell with WMI to query the BCD store directly.
        Returns binary/numeric values that are NOT affected by Windows locale.

        The WMI namespace is root\\WMI with BcdStore class.
        """
        values: dict[str, str | None] = {}

        if sys.platform != "win32":
            return values

        # PowerShell script to query BCD via WMI
        # This returns numeric values (True/False for booleans, integers for others)
        # which are locale-independent
        ps_script = r"""
try {
    # Open BCD store via WMI
    $bcdStore = Get-WmiObject -Namespace root\WMI -Class BcdStore -ErrorAction Stop
    $result = $bcdStore.OpenStore("")
    $store = [WMI]"$($result.Store)"

    # Get current boot entry GUID
    # {current} maps to the actual GUID of the current boot entry
    $currentGuid = "{fa926493-6f1c-4193-a414-58f0b2456d1e}"  # Default Windows Boot Manager

    # Try to get the actual current OS loader entry
    $bootMgrResult = $store.OpenObject("{9dea862c-5cdd-4e70-acc1-f32b344d4795}")
    if ($bootMgrResult.ReturnValue -eq 0) {
        $bootMgr = [WMI]"$($bootMgrResult.Object)"
        $defaultResult = $bootMgr.GetElement(0x23000003)  # BcdBootMgrObject_DefaultObject
        if ($defaultResult.ReturnValue -eq 0) {
            $currentGuid = $defaultResult.Element.Id
        }
    }

    # Open the current OS loader entry
    $loaderResult = $store.OpenObject($currentGuid)
    if ($loaderResult.ReturnValue -ne 0) {
        Write-Output "ERROR:Cannot open boot entry"
        exit 1
    }
    $loader = [WMI]"$($loaderResult.Object)"

    # Query each element we care about
    # Element types: 0x26000081=useplatformclock, 0x26000082=useplatformtick,
    #                0x26000083=disabledynamictick, 0x25000084=tscsyncpolicy

    # useplatformclock (boolean)
    $elem = $loader.GetElement(0x26000081)
    if ($elem.ReturnValue -eq 0 -and $elem.Element -ne $null) {
        $val = $elem.Element.Boolean
        Write-Output "useplatformclock=$($val.ToString().ToLower())"
    } else {
        Write-Output "useplatformclock=notset"
    }

    # useplatformtick (boolean)
    $elem = $loader.GetElement(0x26000082)
    if ($elem.ReturnValue -eq 0 -and $elem.Element -ne $null) {
        $val = $elem.Element.Boolean
        Write-Output "useplatformtick=$($val.ToString().ToLower())"
    } else {
        Write-Output "useplatformtick=notset"
    }

    # disabledynamictick (boolean)
    $elem = $loader.GetElement(0x26000083)
    if ($elem.ReturnValue -eq 0 -and $elem.Element -ne $null) {
        $val = $elem.Element.Boolean
        Write-Output "disabledynamictick=$($val.ToString().ToLower())"
    } else {
        Write-Output "disabledynamictick=notset"
    }

    # tscsyncpolicy (integer: 0=default, 1=legacy, 2=enhanced)
    $elem = $loader.GetElement(0x25000084)
    if ($elem.ReturnValue -eq 0 -and $elem.Element -ne $null) {
        $val = $elem.Element.Integer
        switch ($val) {
            1 { Write-Output "tscsyncpolicy=legacy" }
            2 { Write-Output "tscsyncpolicy=enhanced" }
            default { Write-Output "tscsyncpolicy=default" }
        }
    } else {
        Write-Output "tscsyncpolicy=notset"
    }

} catch {
    Write-Output "ERROR:$($_.Exception.Message)"
}
"""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )

            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("ERROR:"):
                    # WMI failed (likely not admin) - don't return partial results
                    from fpstune.utils.debug import debug_log

                    debug_log("bcdedit", f"WMI BcdStore error: {line}")
                    return self._get_all_values_bcdedit()
                if "=" not in line:
                    continue

                name, val = line.split("=", 1)
                name = name.lower().strip()
                val = val.lower().strip()

                if val == "notset":
                    values[name] = None
                elif val == "true":
                    values[name] = "yes"
                elif val == "false":
                    values[name] = "no"
                else:
                    # For tscsyncpolicy: legacy, enhanced, default
                    values[name] = val

            # If WMI failed, fall back to bcdedit
            if not values and result.returncode != 0:
                from fpstune.utils.debug import debug_log

                debug_log(
                    "bcdedit",
                    f"WMI failed (returncode={result.returncode}), falling back to bcdedit",
                )
                return self._get_all_values_bcdedit()

        except Exception as e:
            # Fall back to bcdedit if PowerShell fails - but log the error
            from fpstune.utils.debug import debug_log

            debug_log("bcdedit", f"WMI exception: {e}, falling back to bcdedit")
            return self._get_all_values_bcdedit()

        # Ensure all expected names are in dict (with None if not found)
        for name in ["useplatformclock", "useplatformtick", "disabledynamictick", "tscsyncpolicy"]:
            if name not in values:
                values[name] = None

        return values

    def _get_all_values_bcdedit(self) -> dict[str, str | None]:
        """Get BCD values using bcdedit /enum {current}.

        Uses bcdedit to query the SAME boot entry that apply writes to.
        This ensures detect and apply are always in sync.

        Property names (useplatformclock, etc.) are NOT localized, so we can
        safely parse them regardless of Windows language.

        For boolean settings, if the property appears in output, it's enabled.
        (bcdedit only shows boolean settings when they're set to true/yes)
        """
        from fpstune.utils.debug import debug_log

        values: dict[str, str | None] = {}

        debug_log("bcdedit", "Running: bcdedit /enum {current}")
        success, output = self._run("/enum {current}")
        debug_log("bcdedit", f"Enum result: success={success}, output_len={len(output)}")

        if not success:
            debug_log("bcdedit", f"Enum failed: {output}")
            raise RuntimeError(f"bcdedit /enum {{current}} failed: {output}")

        # BCD names we care about
        bcd_names = [
            "useplatformclock",
            "useplatformtick",
            "disabledynamictick",
            "tscsyncpolicy",
        ]

        for name in bcd_names:
            # Check if property name appears in output (property names are never localized)
            found = False
            for line in output.splitlines():
                line_lower = line.lower().strip()
                if line_lower.startswith(name):
                    found = True
                    parts = line_lower.split()
                    if len(parts) >= 2:
                        raw_val = parts[-1]
                        # For tscsyncpolicy, check for known values
                        if name == "tscsyncpolicy":
                            if "legacy" in raw_val:
                                values[name] = "legacy"
                            elif "enhanced" in raw_val:
                                values[name] = "enhanced"
                            else:
                                values[name] = None  # Unknown or default
                        else:
                            # For boolean settings, if the line exists, it's set to "yes"
                            # (bcdedit only shows boolean settings when they're true)
                            values[name] = "yes"
                    break

            if not found:
                values[name] = None

        debug_log("bcdedit", f"Detected BCD values: {values}")
        return values

    def _run(self, args: str) -> tuple[bool, str]:
        """Run bcdedit command and return (success, output)."""
        if sys.platform != "win32":
            return False, "Not available on this platform"

        try:
            result = subprocess.run(
                ["bcdedit"] + args.split(),
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    @classmethod
    def invalidate_cache(cls) -> None:
        """Invalidate cached BCD values."""
        with cls._lock:
            cls._cache = None
