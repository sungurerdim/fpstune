"""BcdEdit executor for boot configuration detection and application.

Detection reads the BCD store through CIM (``Invoke-CimMethod`` on the WMI
``BcdStore`` provider), which answers with typed values no Windows language
changes. Apply goes through ``bcdedit /set {current}``, which accepts English
keywords on every language. The two address the same entry by construction.
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

_BOOLEAN_ELEMENTS = ("useplatformclock", "useplatformtick", "disabledynamictick")

# The well-known identifier of the entry Windows booted from. It is the entry
# `bcdedit /set {current}` writes, so detect and apply cannot disagree about which
# one they mean. The boot manager's *default* entry is deliberately not consulted:
# on a dual-boot machine it can be another OS entirely.
_CURRENT_ENTRY = "{fa926493-6f1c-4193-a414-58f0b2456d1e}"


def _bcd_store_script() -> str:
    """The PowerShell that reads the four elements from the BCD store, via CIM.

    Why CIM and not ``Get-WmiObject``: ``Get-WmiObject -Class BcdStore`` enumerates
    *instances* of the class, and BcdStore has none, so the old form threw on
    every machine and detection quietly fell back to ``bcdedit /enum`` text —
    whose value words are localized ("Yes" is "Evet" here). ``Invoke-CimMethod``
    calls the static ``OpenStore`` and then the instance methods on the objects
    it returns, and the results are typed (booleans, integers), not text.

    Every element type comes from ``BCD_ELEMENT_TYPES`` so there is one table.
    Output is one ``name=value`` line per element, ``notset`` when the entry has
    no such element, or one ``ERROR:`` line when the store could not be opened.
    """
    boolean_reads = "\n".join(
        f"    Write-Output ('{name}=' + (Read-BcdBoolean 0x{BCD_ELEMENT_TYPES[name]:08X}))"
        for name in _BOOLEAN_ELEMENTS
    )
    tsc_read = (
        "    Write-Output ('tscsyncpolicy=' + "
        f"(Read-BcdInteger 0x{BCD_ELEMENT_TYPES['tscsyncpolicy']:08X}))"
    )
    return f"""
$ErrorActionPreference = 'Stop'
try {{
    $opened = Invoke-CimMethod -Namespace root\\WMI -ClassName BcdStore -MethodName OpenStore -Arguments @{{ File = '' }}
    if (-not $opened.ReturnValue -or $null -eq $opened.Store) {{
        Write-Output 'ERROR:Cannot open the BCD store'
        exit 1
    }}
    $loaderResult = Invoke-CimMethod -InputObject $opened.Store -MethodName OpenObject -Arguments @{{ Id = '{_CURRENT_ENTRY}' }}
    if (-not $loaderResult.ReturnValue -or $null -eq $loaderResult.Object) {{
        Write-Output 'ERROR:Cannot open boot entry'
        exit 1
    }}
    $loader = $loaderResult.Object

    function Read-BcdElement([uint32]$type) {{
        # An element the entry never had is a method that answers false — or, on
        # some builds, a CIM error. Both mean "not set"; neither is a failure.
        try {{
            $elem = Invoke-CimMethod -InputObject $loader -MethodName GetElement -Arguments @{{ Type = $type }} -ErrorAction Stop
            if ($elem.ReturnValue -and $null -ne $elem.Element) {{ return $elem.Element }}
        }} catch {{ }}
        return $null
    }}
    function Read-BcdBoolean([uint32]$type) {{
        $elem = Read-BcdElement $type
        if ($null -eq $elem) {{ return 'notset' }}
        if ([bool]$elem.Boolean) {{ return 'true' }} else {{ return 'false' }}
    }}
    function Read-BcdInteger([uint32]$type) {{
        $elem = Read-BcdElement $type
        if ($null -eq $elem) {{ return 'notset' }}
        return [string][uint64]$elem.Integer
    }}

{boolean_reads}
{tsc_read}
}} catch {{
    Write-Output "ERROR:$($_.Exception.Message)"
    exit 1
}}
"""


def parse_store_lines(lines: list[str]) -> dict[str, str | None] | None:
    """Turn the script's ``name=value`` lines into the executor's vocabulary.

    Returns None on an ``ERROR:`` line — the store could not be read, and a
    partial answer would be a wrong one. Booleans become ``yes``/``no`` (the words
    bcdedit accepts), ``notset`` becomes None, and the TSC policy's integer is
    named through ``TSC_SYNC_VALUES``.
    """
    values: dict[str, str | None] = {}
    for raw in lines:
        line = raw.strip()
        if line.startswith("ERROR:"):
            return None
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
        elif name == "tscsyncpolicy" and val.isdigit():
            values[name] = TSC_SYNC_VALUES.get(int(val), "default")
        else:
            values[name] = val
    return values


_BCD_STORE_SCRIPT = _bcd_store_script()

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

    Detection is done through the BcdStore provider via CIM, which returns
    typed values rather than the localized "Yes/No/Evet/Ja" of bcdedit's text;
    that text is only the fallback for an unelevated process. Apply uses
    bcdedit commands, which accept English keywords on every language.
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
        """Read every BCD value fpstune manages from the store, via CIM.

        Typed values, not localized text. When the store cannot be read — most
        often because the process is not elevated — the answer comes from
        ``bcdedit /enum {current}`` instead, and the debug log says why.
        """
        if sys.platform != "win32":
            return {}

        from fpstune.utils.debug import debug_log

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    _BCD_STORE_SCRIPT,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            debug_log("bcdedit", f"BCD store read exception: {e}, falling back to bcdedit")
            return self._get_all_values_bcdedit()

        values = parse_store_lines(result.stdout.splitlines())
        if values is None or (not values and result.returncode != 0):
            debug_log(
                "bcdedit",
                f"BCD store read failed (returncode={result.returncode}): "
                f"{result.stdout.strip()[:200]} {result.stderr.strip()[:200]}",
            )
            return self._get_all_values_bcdedit()

        for name in (*_BOOLEAN_ELEMENTS, "tscsyncpolicy"):
            values.setdefault(name, None)
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
