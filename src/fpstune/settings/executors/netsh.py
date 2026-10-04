"""Netsh executor for network configuration.

LOCALIZATION: a value is read only from the line whose label is the one the
setting names. netsh's TCP/IPv6/Teredo labels are English even on a localised
Windows 11 (verified on a Turkish install), and where Get-NetTCPSetting answers
the same question it is asked first. A label that is not there is an unanswered
question, never "the first known keyword anywhere in the output": that guess read
another row's ``enabled`` as this row's answer.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.settings.executors import BaseExecutor, map_raw_to_display
from fpstune.settings.executors.ps_batch import _get_cache, cache_once
from fpstune.utils.powershell import run_powershell, substitute_placeholders
from fpstune.utils.system_tools import system_tool

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


# Every TCP property fpstune reads comes off the same Get-NetTCPSetting object,
# so one query answers all of them. Each of these settings used to start its own
# PowerShell — measured at ~1.7 s each, the three slowest entries in a scan.
TCP_PARSE_KEY_TO_PROPERTY = {
    "receive window auto-tuning level": "AutoTuningLevelLocal",
    "receive-side scaling state": "ReceiveSideScaling",
    "receive segment coalescing state": "ReceiveSegmentCoalescing",
}

# Properties nothing in netsh's own output covers, read off the same object
# anyway. `network:tcp_timestamps` and `network:tcp_ecn` each ran their own
# `Get-NetTCPSetting -SettingName Internet` — measured at 1.10 s and 1.11 s in a
# scan whose total subprocess time was 21 s, for a query already being made.
EXTRA_TCP_PROPERTIES = ("EcnCapability", "Timestamps")

_TCP_CACHE_KEY = "tcp_settings"

# `_run` tokenizes the whole command with `args.split()`, so a value carrying a
# space would append netsh arguments to an elevated command line — the same
# defect bcdedit's `_BCD_TOKEN` closes for `/set {current} <name> <value>`.
# Checked here rather than left to the escaping layer: that layer only rejects a
# wide value when the placeholder sits *outside* quotes, and whether a netsh
# template happens to quote is not a property netsh's tokenizer cares about.
#
# Every value the shipped netsh settings apply is a single English keyword
# (enabled, disabled, normal, highlyrestricted, default) or an integer (MTU),
# and `store=persistent`-style literals are part of the template rather than the
# value — so a token rule refuses nothing legitimate.
_NETSH_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


# Why the remaining netsh queries are NOT folded into this snapshot.
#
# Five distinct netsh commands survive a scan — tcp show global, tcp show
# heuristics, ipv6 show global, ipv6 show privacy, teredo show state — and the
# obvious next step is to answer all five from cmdlets here and spawn nothing.
# Measured on the dev machine, that is four times slower:
#
#     five netsh commands, one process each   0.224 s total (0.045 s each)
#     one PowerShell covering all five        0.970 s
#
# netsh is a small native binary that starts in ~45 ms; a PowerShell session
# costs about a second before it runs anything. Batching pays when it removes
# PowerShell startups, and costs when it adds one. The per-command cache below
# already collapses the duplicates — four settings share `tcp show global` and
# it runs once — so what is left is five genuinely different questions.
#
# The locale argument does not rescue it either: netsh's TCP labels are English
# even on a localised install (verified on a Turkish Windows 11), so the parse
# keys are not the fragile part they look like.
def _fetch_tcp_snapshot() -> dict[str, str]:
    """Read every TCP property fpstune needs in one PowerShell call.

    Values are interpolated into strings inside PowerShell rather than left to
    ConvertTo-Json: these properties are enums, and JSON would serialise them as
    their numeric value, which no ``value_map`` here expects.
    """
    if sys.platform != "win32":
        return {}

    props = sorted(set(TCP_PARSE_KEY_TO_PROPERTY.values()) | set(EXTRA_TCP_PROPERTIES))
    fields = "; ".join(f'{name} = "$($s.{name})"' for name in props)
    cmd = (
        "$s = Get-NetTCPSetting -SettingName Internet -ErrorAction SilentlyContinue; "
        f"if ($s) {{ @{{ {fields} }} | ConvertTo-Json -Compress }}"
    )
    success, output = run_powershell(cmd, timeout=15, component="netsh")
    if not (success and output and output.strip()):
        return {}

    try:
        data = json.loads(output.strip())
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}

    snapshot: dict[str, str] = {}
    for name, value in data.items():
        text = str(value).strip().lower()
        # An absent property interpolates to the empty string, and the old
        # per-setting script answered 'unknown' for the same case. Both mean
        # "fall through to parsing netsh's own output", so neither is stored.
        if text and text != "unknown":
            snapshot[str(name)] = text
    return snapshot


def _tcp_snapshot() -> dict[str, str]:
    """Return the TCP property snapshot, computed once per scan."""
    cache = _get_cache()
    if cache is None:
        return _fetch_tcp_snapshot()
    return cache_once(cache, _TCP_CACHE_KEY, _fetch_tcp_snapshot)


# Sentinel distinguishing "the scan read the object and this property was absent"
# from "the property is off". Returning "not_available" for the first case is
# what the per-setting scripts did, and their value_maps still expect it. The
# spelling comes from the applicability contract so detection recognises it.
TCP_PROPERTY_MISSING = NOT_AVAILABLE


def get_tcp_property(name: str) -> str:
    """Read one ``Get-NetTCPSetting`` property from the per-scan snapshot.

    Lets a POWERSHELL-type setting share the query the netsh path already makes
    instead of spawning its own.
    """
    snapshot = _tcp_snapshot()
    # Snapshot keys keep the property's own casing (values are lowercased, keys
    # are not), so an exact hit first and a case-insensitive sweep as the
    # fallback rather than assuming either.
    if name in snapshot:
        return snapshot[name]
    lowered = name.lower()
    for key, value in snapshot.items():
        if key.lower() == lowered:
            return value
    return TCP_PROPERTY_MISSING


def prefetch_tcp_settings() -> dict[str, str]:
    """Populate the scan cache with the TCP snapshot."""
    return _tcp_snapshot()


class NetshExecutor(BaseExecutor):
    """Execute netsh commands for network configuration.

    Handles TCP settings, interface configuration, etc.

    LOCALIZATION-SAFE APPROACH:
    1. Values like "enabled", "disabled", "normal" are English keywords
       that work on all Windows locales (both for reading and setting)
    2. For detection, we try PowerShell first (Get-NetTCPSetting returns consistent values)
    3. Fall back to pattern matching for known values in netsh output
    """

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect a network setting using netsh or PowerShell fallback.

        Uses multiple strategies for localization-safe detection:
        1. Try PowerShell API for TCP settings (locale-independent)
        2. Fall back to netsh with smart pattern matching

        Commands use %key% placeholder syntax (consistent with PowerShell executor).
        """
        if sys.platform != "win32":
            return None, "Not available on this platform"

        # Use substitute_placeholders for %key% syntax (consistent with PowerShell executor)
        try:
            cmd = substitute_placeholders(setting.detect_command, **setting.detect_args)
        except ValueError as exc:
            # The escaping layer refused a value it could not place safely. That
            # is a rejected reading, not a crashed detector.
            return None, f"netsh command rejected: {exc}"

        # For TCP global settings, try PowerShell first (more reliable)
        if "tcp show global" in cmd.lower():
            ps_value = self._detect_tcp_via_powershell(setting.detect_args)
            if ps_value is not None:
                return map_raw_to_display(setting.value_map, ps_value), None

        success, output = self._query(cmd)
        if not success:
            return None, f"netsh failed: {output}"

        # Parse output based on command type
        raw_value = self._parse_output(output, setting.detect_args)

        # Map raw value to display value if mapping exists
        if setting.value_map and raw_value is not None:
            return map_raw_to_display(setting.value_map, raw_value), None
        elif None in setting.value_map and raw_value is None:
            return setting.value_map[None], None

        return raw_value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Apply a network setting using netsh.

        Note: netsh accepts English keywords (enabled/disabled/normal) on all locales.
        Commands use %key% placeholder syntax (consistent with PowerShell executor).
        """
        if sys.platform != "win32":
            return False, "Not available on this platform"

        # Convert display value to raw value
        raw_value = setting.apply_value_map.get(value, value)

        if not _NETSH_TOKEN.match(str(raw_value).strip()):
            return False, f"netsh requires a single-token value, got {raw_value!r}"

        # Use substitute_placeholders for %key% syntax (consistent with PowerShell executor)
        args = {**setting.apply_args, "value": str(raw_value).strip()}
        try:
            cmd = substitute_placeholders(setting.apply_command, **args)
        except ValueError as exc:
            return False, f"netsh command rejected: {exc}"

        success, output = self._run(cmd)
        if not success:
            return False, f"netsh failed: {output}"

        return True, None

    def _detect_tcp_via_powershell(self, args: dict[str, Any]) -> str | None:
        """Detect TCP setting via PowerShell Get-NetTCPSetting (locale-independent).

        PowerShell returns consistent property values regardless of locale.
        """
        parse_key = args.get("parse_key", "").lower()
        if not parse_key:
            return None

        property_name = TCP_PARSE_KEY_TO_PROPERTY.get(parse_key)
        if not property_name:
            return None

        return _tcp_snapshot().get(property_name)

    def _parse_output(self, output: str, args: dict[str, Any]) -> str | None:
        """The value on the line labelled ``parse_key``, or None when no line is.

        netsh prints ``Label : value`` rows. Only the row with this setting's own
        label answers; there is no fallback to a known keyword elsewhere in the
        output, because ``enabled`` on a neighbouring row is a different setting's
        state. With no ``parse_key`` the whole trimmed output is the answer.
        """
        target_key = args.get("parse_key", "").lower()
        if not target_key:
            return output.strip().lower() or None

        for line in output.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip().lower() == target_key:
                return value.strip().lower()
        return None

    def _query(self, args: str) -> tuple[bool, str]:
        """Run a read-only netsh command, once per scan.

        ``interface tcp show global`` backs four separate settings and prints
        the same block for all of them, so a scan ran it four times. Only
        detection goes through here — apply must always reach the system.
        """
        cache = _get_cache()
        if cache is None:
            return self._run(args)
        return cache_once(cache, f"netsh_query|{args}", lambda: self._run(args))

    def _run(self, args: str) -> tuple[bool, str]:
        """Run netsh command and return (success, output)."""
        if sys.platform != "win32":
            return False, "Not available on this platform"

        try:
            result = subprocess.run(
                [system_tool("netsh.exe")] + args.split(),
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only (platform checked above)
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)
