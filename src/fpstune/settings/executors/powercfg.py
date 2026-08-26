"""PowerCfg executor for power setting detection and application.

LOCALIZATION-SAFE: Uses GUIDs (not names) and parses hex values (not text).
Power setting GUIDs and numeric values are never localized.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Any

from fpstune.settings.applicability import values_equal
from fpstune.settings.executors import BaseExecutor, map_raw_to_display

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

_POWER_SCHEMES_KEY = "SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes"

# Every powercfg setting is stored per plan:
#     ...\Power\User\PowerSchemes\<scheme>\<subgroup>\<setting>\ACSettingIndex
# so writing only the active plan leaves the tweak behind the moment anything
# switches plans. That is not hypothetical. On the machine this was measured on,
# Process Lasso switches to "Bitsum Highest Performance" while a game runs and back
# to "FPS Balanced" afterwards — two readings taken minutes apart in the same
# session disagreed for exactly that reason, and only one of the two plans carried
# the core-parking override.
#
# So fpstune writes every plan, and reports a setting as applied only when every
# plan it writes carries it. Same rule the DNS setting had to learn (#56): an
# observation narrower than the action lets verification pass over a state that was
# never reached.
#
# Which plans, decided by the user: the ones the machine actually uses — the active
# plan, plus every plan that is not one of Windows' own. Stock Balanced, High
# performance, Power saver and Ultimate Performance are left as they ship, so
# switching to Balanced for quiet or battery still gets Balanced. Writing those too
# would guarantee the tweak under any plan, at the price of redefining a plan the
# user picked precisely because of what it does — C3 in the other direction.
#
# "Windows' own" is read structurally rather than by name. A built-in plan stores
# its FriendlyName as an MUI indirect string:
#     381b4222-...  @C:\WINDOWS\system32\powrprof.dll,-15,Balanced
#     a1841308-...  @C:\WINDOWS\system32\powrprof.dll,-11,Power saver
# while a plan created by a person or a tool stores plain text:
#     f0b769e8-...  FPS Balanced
#     b76bc4cb-...  Bitsum Highest Performance
# The leading '@' is the indirect-string marker, not a word, so this holds in every
# locale — unlike matching "Balanced", which would not survive a Turkish install
# where the same plan reads "Dengeli".
_MUI_INDIRECT_PREFIX = "@"


class PowerCfgExecutor(BaseExecutor):
    """Execute powercfg commands for power settings.

    Handles USB selective suspend, PCIe link state, WLAN power saving, etc.
    Uses /query for detection (shows AC/DC values) and /setacvalueindex for apply.

    LOCALIZATION-SAFE APPROACH:
    - All settings use GUIDs (never localized names)
    - Values are parsed as hex (0x00000001) - never as text
    - "AC" and "DC" are universal abbreviations, not localized
    - Possible Setting Index values are numeric (000, 001, etc.)
    """

    _active_scheme: str | None = None
    _lock: threading.Lock = threading.Lock()

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect a power setting value using powercfg /query.

        Uses /query SCHEME_CURRENT to get current AC power setting value.
        Parses hex value from output using multiple detection strategies:
        1. Primary: Look for line with "AC" and hex value
        2. Fallback: Parse registry directly via PowerShell
        """
        # Build query command: /query SCHEME_CURRENT <subgroup> <setting>
        subgroup = setting.detect_args.get("subgroup", "")
        setting_guid = setting.detect_args.get("setting", "")

        if not subgroup or not setting_guid:
            return None, "Missing 'subgroup' or 'setting' in detect_args"

        # The registry holds the same AC index powercfg /query prints, and reading
        # it costs microseconds against ~370 ms for the subprocess. Verified on
        # the dev machine: all 12 shipped power settings produce identical values
        # through both paths, absent subgroups included. Anything the registry
        # cannot answer falls through to powercfg below, so this stays a pure
        # optimisation rather than a second source of truth.
        registry_value = self._detect_via_registry_key(setting)
        if registry_value is not None:
            return registry_value, None

        cmd = f"/query SCHEME_CURRENT {subgroup} {setting_guid}"

        success, output = self._run(cmd)
        if not success:
            # Fallback to registry detection
            return self._detect_via_registry(subgroup, setting_guid, setting.value_map)

        raw_value = self._parse_query_output(output)
        if raw_value is None:
            # Fallback to registry detection
            return self._detect_via_registry(subgroup, setting_guid, setting.value_map)

        # Map raw value to display value
        display_value = map_raw_to_display(setting.value_map, raw_value)
        return display_value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Write the setting to every power plan, not just the active one.

        A per-plan store plus a tool that switches plans means a single-plan write
        is a tweak that quietly stops applying — see the note on _target_schemes.
        The active plan is written first, so if a later plan fails the machine the
        user is actually on is already correct.
        """
        schemes = self._target_schemes()
        if not schemes:
            return False, "Could not enumerate power schemes"

        # Convert display value to raw value
        raw_value = setting.apply_value_map.get(value, value)

        # powercfg /set*valueindex requires a numeric setting index. Coerce here so a
        # free-form INT value (empty apply_value_map) cannot inject extra powercfg
        # arguments via the later args.split() in _run.
        try:
            raw_index = int(str(raw_value).strip())
        except (ValueError, TypeError):
            return False, f"powercfg requires a numeric value index, got {raw_value!r}"

        # Get subgroup and setting GUIDs
        subgroup = setting.apply_args.get("subgroup", "")
        setting_guid = setting.apply_args.get("setting", "")

        if not subgroup or not setting_guid:
            return False, "Missing 'subgroup' or 'setting' in apply_args"

        # Apply to both AC (plugged in) and DC (battery), on every plan.
        failures: list[str] = []
        for scheme in schemes:
            for flag in ("/setacvalueindex", "/setdcvalueindex"):
                cmd = f"{flag} {scheme} {subgroup} {setting_guid} {raw_index}"
                success, output = self._run(cmd)
                if not success:
                    failures.append(f"{scheme} {flag}: {output.strip()}")

        # The active plan is first in the list, so its failure is the one that
        # means the user's machine did not change. A plan they are not on failing
        # is reported but does not sink the apply.
        if any(entry.startswith(schemes[0]) for entry in failures):
            return False, f"powercfg failed on the active plan: {failures[0]}"

        # Re-activate so the change takes effect now rather than at the next switch.
        self._run("/setactive SCHEME_CURRENT")
        if failures:
            return True, f"applied, but {len(failures)} write(s) failed: {'; '.join(failures)}"
        return True, None

    def _active_scheme_from_registry(self) -> str | None:
        """Read the active scheme GUID from the registry.

        Preferred over the cached ``_get_active_scheme()`` on the detect path:
        that one caches for the process lifetime, so a user switching power plan
        while fpstune runs would be read against the plan they left.
        """
        if sys.platform != "win32":
            return None
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _POWER_SCHEMES_KEY) as key:
                guid, _ = winreg.QueryValueEx(key, "ActivePowerScheme")
        except OSError:
            return None
        return str(guid).strip().lower() or None

    def _target_schemes(self) -> list[str]:
        """The plans fpstune reads and writes: the active one, plus every custom one.

        Read from the registry rather than ``powercfg /list``, and that matters: on
        the measured machine ``/list`` shows two plans while the registry holds
        nine, and the plan Process Lasso switches to while gaming — "Bitsum Highest
        Performance" — is one of the seven ``/list`` does not print. Writing only
        what ``/list`` shows would miss the plan the user games on.

        The active plan is always included even when it is one of Windows' own: a
        machine running stock Balanced still deserves the tweak on the plan it is
        actually using.
        """
        if sys.platform != "win32":
            return []
        import winreg

        active = self._active_scheme_from_registry()
        custom: list[str] = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _POWER_SCHEMES_KEY) as key:
                index = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    guid = name.strip().lower()
                    if not guid or guid == active:
                        continue
                    if not self._is_windows_scheme(guid):
                        custom.append(guid)
        except OSError:
            return [active] if active else []

        # Active plan first, so a non-uniform reading reports the plan the user is
        # on rather than whichever one the registry happened to enumerate first,
        # and so an apply corrects that plan before any other.
        return ([active] if active else []) + custom

    def _is_windows_scheme(self, scheme: str) -> bool:
        """True for a plan Windows ships, false for one a person or tool created.

        Unreadable name -> treated as Windows'. Declining to write a plan we cannot
        identify is the safe direction: the cost is a tweak missing from one plan,
        against silently rewriting a stock plan.
        """
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, f"{_POWER_SCHEMES_KEY}\\{scheme}"
            ) as key:
                name, _ = winreg.QueryValueEx(key, "FriendlyName")
        except OSError:
            return True
        return str(name).startswith(_MUI_INDIRECT_PREFIX)

    def _scheme_index(self, scheme: str, subgroup: str, setting: str) -> int | None:
        """One plan's AC index for one setting, or None when it holds no override."""
        import winreg

        path = f"{_POWER_SCHEMES_KEY}\\{scheme}\\{subgroup}\\{setting}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                raw, _ = winreg.QueryValueEx(key, "ACSettingIndex")
        except OSError:
            return None
        return raw if isinstance(raw, int) else None

    def _detect_via_registry_key(self, setting: SettingExecutor) -> Any | None:
        """Read one power setting across every plan fpstune writes.

        Returns None — meaning "ask powercfg" — when the plan list cannot be read
        at all. A sentinel on every failure would be indistinguishable from a
        working read, which is the defect class this codebase has already paid for.

        A plan holding no override inherits Windows' default for that setting,
        which is what ``default_value`` is curated to be, so it is read as the
        default rather than as an absence. That is the difference between "this
        machine is not set up" and "there is nothing here to tune", and the old
        code answered the second for both — which is why four settings read
        `not_available` on every machine and never appeared in the UI at all.
        """
        if sys.platform != "win32":
            return None

        subgroup = setting.detect_args.get("subgroup", "")
        setting_guid = setting.detect_args.get("setting", "")
        schemes = self._target_schemes()
        if not schemes:
            return None

        readings: list[Any] = []
        for scheme in schemes:
            raw = self._scheme_index(scheme, subgroup, setting_guid)
            if raw is None:
                readings.append(setting.default_value)
            else:
                readings.append(map_raw_to_display(setting.value_map, raw))

        # `values_equal`, not `==`: these readings do not all come from the same
        # place. A plan holding an override yields whatever `value_map`
        # translates its integer index to, while a plan holding none yields the
        # curated `default_value` — so one side can be 100 and the other "100"
        # for a setting whose map is empty. Compared with `==` that reads as
        # "the plans disagree", and the UI would report a machine as half-tuned
        # when every plan already holds the same value.
        if all(values_equal(r, readings[0]) for r in readings):
            return readings[0]

        # The plans disagree, so the setting is not applied everywhere. Report a
        # plan that differs from the recommendation — never the recommendation
        # itself — or the UI would call this done while a plan the user games on
        # still holds the old value.
        for reading in readings:
            if not values_equal(reading, setting.recommended_value):
                return reading
        return readings[0]

    def _get_active_scheme(self) -> str | None:
        """Get the currently active power scheme GUID."""
        with PowerCfgExecutor._lock:
            if self._active_scheme:
                return self._active_scheme

            success, output = self._run("/getactivescheme")
            if not success:
                return None

            # Parse GUID using regex (locale-independent)
            # GUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            guid_pattern = (
                r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
            )
            match = re.search(guid_pattern, output)
            if match:
                self._active_scheme = match.group(1).lower()
                return self._active_scheme

            return None

    def _parse_query_output(self, output: str) -> int | None:
        """Parse powercfg /query output to extract AC power setting value.

        LOCALIZATION-SAFE: Uses multiple detection strategies:
        1. Look for line with "AC" (universal abbreviation) + hex value
        2. Look for hex values in format 0x followed by digits
        3. Look for numeric index pattern ": 0x"

        The hex values (0x00000001) are NEVER localized.

        Example output (any locale):
            Power Setting GUID: 48e6b7a6-50f5-4782-a5d4-53bb8f07e226
              Possible Setting Index: 000
              Possible Setting Friendly Name: Disabled
              Possible Setting Index: 001
              Possible Setting Friendly Name: Enabled
              Current AC Power Setting Index: 0x00000001
              Current DC Power Setting Index: 0x00000001
        """
        lines = output.splitlines()
        ac_value = None

        for line in lines:
            # Strategy 1: Look for "AC" keyword with hex value
            # "AC" is a universal abbreviation (Alternating Current)
            if " AC " in line.upper():
                hex_match = re.search(r"0x([0-9a-fA-F]+)", line)
                if hex_match:
                    with contextlib.suppress(ValueError):
                        ac_value = int(hex_match.group(1), 16)

        # Return AC value if found
        if ac_value is not None:
            return ac_value

        # Strategy 2: Look for pattern ": 0x" followed by hex digits
        # This catches "Current ... Index: 0x00000001" regardless of language
        for line in lines:
            if ": 0x" in line or ":0x" in line:
                hex_match = re.search(r":\s*0x([0-9a-fA-F]+)", line)
                if hex_match:
                    try:
                        return int(hex_match.group(1), 16)
                    except ValueError:
                        continue

        # Strategy 3: Find the last hex value (often the current setting)
        # Scan from end since "Current" values come after "Possible" values
        all_hex = re.findall(r"0x([0-9a-fA-F]+)", output)
        if all_hex:
            try:
                return int(all_hex[-1], 16)
            except ValueError:
                pass

        return None

    def _detect_via_registry(
        self, subgroup: str, setting: str, value_map: dict[Any, Any]
    ) -> tuple[Any | None, str | None]:
        """Fallback: Detect power setting via registry (locale-independent).

        Power settings are stored in registry under:
        HKLM\\SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes\\
        <scheme_guid>\\<subgroup_guid>\\<setting_guid>

        Values are stored as ACSettingIndex and DCSettingIndex (REG_DWORD).
        """
        if sys.platform != "win32":
            return None, "Not available on this platform"

        scheme = self._get_active_scheme()
        if not scheme:
            return None, "Could not get active power scheme"

        # PowerShell script to read from registry (completely locale-independent)
        ps_script = f"""
$path = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes\\{scheme}\\{subgroup}\\{setting}'
if (Test-Path -LiteralPath $path) {{
    $val = Get-ItemProperty -LiteralPath $path -Name 'ACSettingIndex' -ErrorAction SilentlyContinue
    if ($val) {{
        Write-Output $val.ACSettingIndex
    }} else {{
        Write-Output 'NOTFOUND'
    }}
}} else {{
    Write-Output 'NOTFOUND'
}}
"""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout.strip()
            if output == "NOTFOUND":
                # The subgroup or setting simply is not present in the active
                # scheme. Custom plans (Bitsum Highest Performance) and Modern
                # Standby plans routinely omit whole subgroups, and a plan that
                # never carried the knob is not a detection failure. Reporting an
                # error here made four settings — one of them ESSENTIAL — look
                # broken on any machine using such a plan, and an error is also
                # louder than the truth: there is nothing here to tune.
                # "not_available" is the engine's sentinel for exactly this; it
                # sets is_applicable=False and hides the setting.
                from fpstune.utils.debug import debug_log

                debug_log(
                    "powercfg",
                    f"Power setting {subgroup}\\{setting} absent from scheme {scheme}",
                )
                return "not_available", None
            if output:
                try:
                    raw_value = int(output)
                    display_value = map_raw_to_display(value_map, raw_value)
                    return display_value, None
                except ValueError as e:
                    from fpstune.utils.debug import debug_log

                    debug_log("powercfg", f"Failed to parse power setting value '{output}': {e}")
        except Exception as e:
            from fpstune.utils.debug import debug_log

            debug_log("powercfg", f"PowerShell power setting query failed: {e}")

        # Reached only on a real failure: an exception, an unparseable value, or
        # no output at all. A missing subgroup returns above and never lands here.
        return None, "Could not detect power setting"

    def get_available_values(self, subgroup: str, setting_guid: str) -> list[int]:
        """Get available values for a power setting.

        Returns list of possible setting index values (e.g., [0, 1] for on/off).
        These are extracted from "Possible Setting Index: 000" lines.
        """
        cmd = f"/query SCHEME_CURRENT {subgroup} {setting_guid}"
        success, output = self._run(cmd)
        if not success:
            return []

        values: list[int] = []
        for line in output.splitlines():
            # Look for numeric index pattern (locale-independent)
            # "Possible Setting Index: 000" or similar
            match = re.search(r":\s*(\d{3})\s*$", line.strip())
            if match:
                with contextlib.suppress(ValueError):
                    values.append(int(match.group(1)))

        return sorted(set(values))

    def _run(self, args: str) -> tuple[bool, str]:
        """Run powercfg command and return (success, output)."""
        if sys.platform != "win32":
            return False, "Not available on this platform"

        try:
            result = subprocess.run(
                ["powercfg"] + args.split(),
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
        """Invalidate cached active scheme."""
        with cls._lock:
            cls._active_scheme = None
