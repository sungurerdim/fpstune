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
from typing import TYPE_CHECKING, Any, Literal

from fpstune.settings.applicability import NOT_SUPPORTED, values_equal
from fpstune.settings.base import Reading
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

# Windows' own catalogue of power settings, one key per setting, and beside each
# one the value Windows ships for every scheme:
#     ...\Power\PowerSettings\<subgroup>\<setting>
#         \DefaultPowerSchemeValues\<scheme>\{AC,DC}SettingIndex
# The Balanced entry is what `reset` is contracted to write (C6: "the curated
# stock value (Windows stock)"), and it is populated per machine by the processor
# driver — on the measured host `cpu_epp` reads 33 where the shipped constant said
# 50, which was the Windows *Server* figure quoted in Microsoft's tuning document.
# A default taken from a document rather than from the device is the same defect
# class as a hardcoded buffer size.
_POWER_CATALOGUE_KEY = "SYSTEM\\CurrentControlSet\\Control\\Power\\PowerSettings"
BALANCED_SCHEME = "381b4222-f694-41f0-9685-ff5bb260df2e"


def windows_default_index(
    subgroup: str, setting: str, rail: Literal["AC", "DC"] = "AC"
) -> int | None:
    """Windows' own Balanced index for one power setting on one rail, or None.

    Mains (``AC``) is the value the product tunes and the one `reset` writes.
    Battery (``DC``) is the value fpstune writes *instead of* the tweak: the
    owner's decision of 2026-09-11 is calm on battery, so the rail nobody is
    gaming on keeps whatever Windows shipped for it.

    None means "this machine publishes no default for that setting" — a GUID it
    does not carry, or a catalogue that cannot be read — and every caller keeps
    what it has rather than inventing a value.
    """
    if sys.platform != "win32":
        return None
    import winreg

    path = (
        f"{_POWER_CATALOGUE_KEY}\\{subgroup}\\{setting}"
        f"\\DefaultPowerSchemeValues\\{BALANCED_SCHEME}"
    )
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            raw, _ = winreg.QueryValueEx(key, f"{rail}SettingIndex")
    except OSError:
        return None
    return raw if isinstance(raw, int) else None


# === When the processor, not Windows, picks the frequency =====================
#
# Microsoft's processor power management tuning document — the source the seven
# settings below already cite — says of Broadwell-and-later Intel parts under
# Windows' default configuration: "most of the processor power management
# decisions are made in the processor instead of OS level ... The legacy PPM
# parameters used by OS have minimal impact on the actual frequency decisions,
# except telling the processor if it should favor power or performance, or
# capping the minimal and maximum frequencies", and "OS is no longer required to
# monitor activity and select frequency at regular intervals".
#
# Its own tuning list splits on exactly that line: "For HWP enabled system" names
# Energy performance preference alone, while the increase/decrease threshold,
# time and policy parameters are listed "For Non-HWP system". The time-check
# interval is the period of that same monitoring loop, so it goes with them.
#
# Whether the loop runs on this machine is one read (PERFAUTONOMOUS), so per C10
# the honest answer is "not applicable here" rather than a control that does
# nothing while claiming fps and latency. EPP, minimum and maximum processor
# state keep acting and are deliberately absent from this set; so is core
# parking, which is a scheduling decision rather than a frequency one.
_PROCESSOR_SUBGROUP = "54533251-82be-4824-96c1-47b60b740d00"
_PERF_AUTONOMOUS_SETTING = "8baa4a8a-14c6-4451-8e8b-14bdbd197537"

_AUTONOMOUS_BYPASSED_SETTINGS: frozenset[str] = frozenset(
    {
        "06cadf0e-64ed-448a-8927-ce7bf90eb35d",  # performance increase threshold
        "12a0ab44-fe28-4fa9-b3bd-4b64f44960a6",  # performance decrease threshold
        "465e1f50-b610-473a-ab58-00d1077dc418",  # performance increase policy
        "40fbefc7-2e9d-4d25-a185-0cfd8574bac6",  # performance decrease policy
        "4d2b0152-7d5c-498b-88e2-34345392a2c5",  # performance time check interval
        "984cf492-3bed-4488-a8f9-4286c97bf5aa",  # performance increase time
        "d8edeb9b-95cf-4f95-a73c-b061973693c8",  # performance decrease time
    }
)


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
    # Tri-state, because "could not tell" and "not autonomous" must not collapse:
    # `_autonomous_mode` is the answer, `_autonomous_read` says whether one was
    # obtained. Without the second flag a machine that cannot answer would pay a
    # ~370 ms subprocess for every setting in every scan.
    _autonomous_mode: bool | None = None
    _autonomous_read: bool = False
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

        # A frequency-selection parameter the silicon is bypassing is not a
        # setting this machine has — see _AUTONOMOUS_BYPASSED_SETTINGS. An
        # unreadable answer (None) leaves it visible: hiding seven tweaks
        # because a subprocess failed is the worse error.
        if setting_guid in _AUTONOMOUS_BYPASSED_SETTINGS and self._autonomous_mode_enabled():
            return NOT_SUPPORTED, None

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

        Two rails, two answers (owner's decision, 2026-09-11 — calm on battery).
        Mains gets the value asked for. Battery gets Windows' own default for
        this machine, whatever was asked: a laptop on battery is the clearest
        case of "performance is not wanted right now", and the tweaks that bite
        there — every thread unparked, fans active, the radio awake — spend heat
        and runtime for frames nobody asked for. That also makes every apply a
        consequence-6 guard on the rail it does not tune, which is what puts back
        the machines already carrying fpstune's old both-rails write.

        A battery default that cannot be read leaves the battery rail alone. The
        alternative is writing a remembered constant onto a rail we did not
        measure, which is the defect this pass just removed from `default_value`.
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

        # One read for the whole apply: the battery default cannot differ between
        # plans, because it is a property of the setting rather than of a plan.
        battery_index = windows_default_index(subgroup, setting_guid, "DC")
        writes: list[tuple[str, int]] = [("/setacvalueindex", raw_index)]
        if battery_index is None:
            from fpstune.utils.debug import debug_log

            debug_log(
                "powercfg",
                f"{setting.id}: no Balanced DC default published for "
                f"{subgroup}\\{setting_guid}; battery rail left untouched",
            )
        else:
            writes.append(("/setdcvalueindex", battery_index))

        failures: list[str] = []
        for scheme in schemes:
            for flag, index in writes:
                cmd = f"{flag} {scheme} {subgroup} {setting_guid} {index}"
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

    def _autonomous_mode_enabled(self) -> bool | None:
        """Whether the processor is choosing its own frequencies on this machine.

        Asked of powercfg rather than of the plan's registry key, because the
        question is the *effective* value. Measured 2026-09-11: the active plan
        holds no override for PERFAUTONOMOUS and the Balanced catalogue default
        is 0, yet ``powercfg /qh`` reports 0x00000001 — the platform answers over
        both. A registry-only read would have said "Windows is in control" on a
        machine where it is not.

        None means the question could not be answered; the caller treats that as
        "leave the setting visible". Cached for the process because it cannot
        change while a scan runs, and a scan asks it once per affected setting.
        """
        with PowerCfgExecutor._lock:
            if PowerCfgExecutor._autonomous_read:
                return PowerCfgExecutor._autonomous_mode

        # Outside the lock: `_run` spawns a subprocess, and the same lock guards
        # `_get_active_scheme`, which would then be blocked behind it.
        success, output = self._run(
            f"/qh SCHEME_CURRENT {_PROCESSOR_SUBGROUP} {_PERF_AUTONOMOUS_SETTING}"
        )
        raw = self._parse_query_output(output) if success else None
        answer = None if raw is None else raw == 1

        with PowerCfgExecutor._lock:
            PowerCfgExecutor._autonomous_mode = answer
            PowerCfgExecutor._autonomous_read = True
        return answer

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

    def _scheme_index(
        self, scheme: str, subgroup: str, setting: str
    ) -> tuple[int | None, int | None]:
        """One plan's (mains, battery) indices, each None when it holds no override.

        Both rails in one key open, because an observation narrower than the
        action is how a write goes unnoticed: fpstune writes DC as well as AC, so
        reading only AC left a drifted battery rail invisible to detect and to
        verify alike.
        """
        import winreg

        path = f"{_POWER_SCHEMES_KEY}\\{scheme}\\{subgroup}\\{setting}"
        indices: list[int | None] = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                for rail in ("AC", "DC"):
                    try:
                        raw, _ = winreg.QueryValueEx(key, f"{rail}SettingIndex")
                    except OSError:
                        indices.append(None)
                        continue
                    indices.append(raw if isinstance(raw, int) else None)
        except OSError:
            return None, None
        return indices[0], indices[1]

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

        # The battery rail is not tuned, so it is not compared against the
        # recommendation — it is compared against Windows' own value for it. A
        # plan holding no DC override already inherits that value, so only an
        # override can drift.
        windows_battery = windows_default_index(subgroup, setting_guid, "DC")

        readings: list[Any] = []
        battery_drift: dict[str, Any] | None = None
        for scheme in schemes:
            mains, battery = self._scheme_index(scheme, subgroup, setting_guid)
            if mains is None:
                readings.append(setting.default_value)
            else:
                readings.append(map_raw_to_display(setting.value_map, mains))

            if (
                battery_drift is None
                and battery is not None
                and windows_battery is not None
                and battery != windows_battery
            ):
                battery_drift = {
                    "kind": "power_dc_rail",
                    "dc_value": map_raw_to_display(setting.value_map, battery),
                    "windows_dc_default": map_raw_to_display(setting.value_map, windows_battery),
                }

        # `values_equal`, not `==`: these readings do not all come from the same
        # place. A plan holding an override yields whatever `value_map`
        # translates its integer index to, while a plan holding none yields the
        # curated `default_value` — so one side can be 100 and the other "100"
        # for a setting whose map is empty. Compared with `==` that reads as
        # "the plans disagree", and the UI would report a machine as half-tuned
        # when every plan already holds the same value.
        return self._with_battery_note(self._agreed_value(setting, readings), battery_drift)

    @staticmethod
    def _agreed_value(setting: SettingExecutor, readings: list[Any]) -> Any:
        """The one mains value the plans agree on, or the plan that is behind."""
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

    @staticmethod
    def _with_battery_note(value: Any, battery_drift: dict[str, Any] | None) -> Any:
        """The reading, carrying what the battery rail holds when it is not stock.

        The value itself stays the mains reading — that is the value the product
        tunes, talks about and verifies. The battery rail travels in ``finding``,
        the channel an advisory already uses for the numbers behind its word, so
        a rail nobody tunes is still a rail somebody can see.
        """
        if battery_drift is None:
            return value
        return Reading(value, battery_drift)

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

        Values are stored as ACSettingIndex and DCSettingIndex (REG_DWORD), and
        both are read here: fpstune writes both rails, so a fallback that saw
        only one would be the narrower-observation defect all over again. The
        mains index is the value; the battery index travels in the ``Reading``
        when it is not what Windows ships, exactly as on the fast path. A plan
        with no battery override prints ``NONE``, which is inheritance rather
        than drift.
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
    $val = Get-ItemProperty -LiteralPath $path -ErrorAction SilentlyContinue
    if ($val -and $null -ne $val.ACSettingIndex) {{
        $dc = if ($null -ne $val.DCSettingIndex) {{ $val.DCSettingIndex }} else {{ 'NONE' }}
        Write-Output ('{{0}} {{1}}' -f $val.ACSettingIndex, $dc)
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
                fields = output.split()
                try:
                    raw_value = int(fields[0])
                except ValueError as e:
                    from fpstune.utils.debug import debug_log

                    debug_log("powercfg", f"Failed to parse power setting value '{output}': {e}")
                else:
                    display_value = map_raw_to_display(value_map, raw_value)
                    return self._battery_note_from_fallback(
                        display_value, fields, subgroup, setting, value_map
                    ), None
        except Exception as e:
            from fpstune.utils.debug import debug_log

            debug_log("powercfg", f"PowerShell power setting query failed: {e}")

        # Reached only on a real failure: an exception, an unparseable value, or
        # no output at all. A missing subgroup returns above and never lands here.
        return None, "Could not detect power setting"

    def _battery_note_from_fallback(
        self,
        value: Any,
        fields: list[str],
        subgroup: str,
        setting: str,
        value_map: dict[Any, Any],
    ) -> Any:
        """Same battery note as the fast path, from the PowerShell fallback's line."""
        if len(fields) < 2 or fields[1] == "NONE":
            return value
        try:
            battery = int(fields[1])
        except ValueError:
            return value

        windows_battery = windows_default_index(subgroup, setting, "DC")
        if windows_battery is None or battery == windows_battery:
            return value
        return Reading(
            value,
            {
                "kind": "power_dc_rail",
                "dc_value": map_raw_to_display(value_map, battery),
                "windows_dc_default": map_raw_to_display(value_map, windows_battery),
            },
        )

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
        """Invalidate the cached active scheme and autonomous-mode reading."""
        with cls._lock:
            cls._active_scheme = None
            cls._autonomous_mode = None
            cls._autonomous_read = False
