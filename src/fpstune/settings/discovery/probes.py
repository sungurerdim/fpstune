"""The questions discovery asks the machine, each asked once.

Discovery needs six independent readings — which adapters exist, what queue
counts their drivers publish, which adapter carries the default route, what the
GPU is, what the panels are, which Windows build this is — and none of them
waits on another. Measured before the warm-up existed: 3.85 s of subprocess
time inside a 3.86 s discovery, strictly back to back, almost all of it
PowerShell startup rather than work.

Two properties this module exists to hold together, because separating them
loses both. Every probe memoises, so a second ask is free; and the warm-up runs
them concurrently, which only pays off *because* the second ask is free.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, NamedTuple, TypeVar, cast

from fpstune.utils import process_watch
from fpstune.utils.system_tools import powershell_exe

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class NetworkAdapter(NamedTuple):
    """One physical adapter as discovery sees it.

    ``interface_index`` addresses commands for this session; ``instance_id`` (the PnP
    device id) is what names the adapter's settings, because an interface index
    is reassigned when a driver is reinstalled or a USB adapter is replugged (C5).
    """

    interface_index: int
    name: str
    media_type: str
    instance_id: str


def positive_ints(raw: Any) -> list[int]:
    """Parse a driver's enum of accepted values into sorted positive integers.

    A single-valued enum arrives as a scalar rather than a list, and values
    arrive as text or number depending on the driver, so neither shape is
    assumed. Anything non-numeric or non-positive is dropped rather than
    guessed at.
    """
    items = raw if isinstance(raw, list) else [raw]
    parsed = set()
    for item in items:
        try:
            value = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if value > 0:
            parsed.add(value)
    return sorted(parsed)


def powers_of_two_between(minimum: Any, maximum: Any) -> list[int]:
    """Expand a driver's numeric range into the queue counts it can actually take.

    RSS queue counts are powers of two — the indirection table that spreads
    flows across queues is sized by masking hash bits, so a count of 3 has no
    meaning. A driver that publishes ``1..16`` is offering 1, 2, 4, 8 and 16,
    not sixteen distinct settings.
    """
    try:
        low = max(1, int(str(minimum).strip()))
        high = int(str(maximum).strip())
    except (TypeError, ValueError):
        return []
    if high < low:
        return []

    counts = []
    count = 1
    while count <= high:
        if count >= low:
            counts.append(count)
        count *= 2
    return counts


class HardwareProbes:
    """One reading of this machine per registry, shared by every discoverer.

    Scoped to the registry that owns it rather than to the process: the registry
    is built once at startup and cached forever (C7), so a probe cache with the
    same lifetime answers every discoverer without ever going stale inside a
    single build.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._key_locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # guards _key_locks only

    def probe_once(self, key: str, compute: Callable[[], _T]) -> _T:
        """Return this machine's answer for ``key``, asking it once.

        The lock is **per key**, and that matters: a single lock held across the
        call would serialise the probes the warm-up exists to overlap, which is
        the whole cost being removed. Per key, two threads asking the same
        question serialise on it while different questions still run together —
        and a check-then-compute without any lock would let both spawn the
        PowerShell the cache exists to avoid.
        """
        with self._locks_lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
        with lock:
            if key not in self._cache:
                self._cache[key] = compute()
            return cast("_T", self._cache[key])

    def warm(self) -> None:
        """Run every independent probe at once instead of one after another.

        Every probe here memoises, so this only moves *when* they run. The
        registration pass that follows is unchanged and now reads warm caches.

        The pool is small on purpose: concurrent PowerShell startups inflate each
        other (measured elsewhere in this codebase at roughly 1.4x for four
        at once), so past a handful the extra starts cost more than the
        serialisation they remove. Failures are swallowed — each probe already
        degrades on its own, and a warm-up must never be the thing that breaks
        discovery.
        """
        from fpstune.utils.detect import get_gpu_info
        from fpstune.utils.hardware_manager import hardware_manager

        probes: list[Callable[[], object]] = [
            self.active_adapters,
            self.adapter_advanced,
            self.default_route_interface_index,
            get_gpu_info,
            hardware_manager.detect_monitors,
            hardware_manager.detect_os,
        ]

        with ThreadPoolExecutor(max_workers=len(probes)) as pool:
            for future in [pool.submit(probe) for probe in probes]:
                try:
                    future.result()
                except Exception as e:  # pragma: no cover - environment dependent
                    logger.debug("A hardware probe failed during warm-up: %s", e)

    def adapter_guids(self) -> dict[int, str]:
        """InterfaceIndex -> InterfaceGuid (lowercase, no braces), for every adapter.

        The WLAN API addresses a radio by GUID while every per-adapter setting is
        keyed by index; this is the join, read once. Both fields are the
        adapter's own identifiers (C5), and nothing here is text a language
        changes.
        """
        return self.probe_once("adapter_guids", self._read_adapter_guids)

    def _read_adapter_guids(self) -> dict[int, str]:
        if sys.platform != "win32":
            return {}
        try:
            result = process_watch.run(
                [
                    powershell_exe(),
                    "-NoProfile",
                    "-Command",
                    "Get-NetAdapter -IncludeHidden | ForEach-Object { "
                    '"$($_.InterfaceIndex)|$([string]$_.InterfaceGuid)" }',
                ],
                process_watch.QUERY,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.debug("adapter GUID probe failed: %s", exc)
            return {}
        guids: dict[int, str] = {}
        for line in result.stdout.splitlines():
            index_text, _, guid = line.strip().partition("|")
            if index_text.isdigit() and guid:
                guids[int(index_text)] = guid.lower().strip("{}")
        return guids

    def active_adapters(self) -> list[NetworkAdapter]:
        """Memoised; the real query is _query_active_adapters."""
        return self.probe_once("adapters", self._query_active_adapters)

    def adapter_advanced(self) -> dict[str, Any]:
        """Memoised; the real query is _query_adapter_advanced."""
        return self.probe_once("adapter_advanced", self._query_adapter_advanced)

    def rss_queue_options(self) -> dict[int, tuple[tuple[str, ...], str]]:
        """Each adapter's own ``*NumRssQueues`` values, from adapter_advanced."""
        return self.probe_once("rss_queues", self._parse_rss_queue_options)

    def adapter_property_defaults(self) -> dict[int, dict[str, str]]:
        """``{interface_index: {lowercase keyword: DefaultRegistryValue}}``.

        The driver's own default for every advanced property it publishes, which
        is what "reset" must write — a hardcoded stock value is the right answer
        only for the drivers it happened to be copied from (C1).
        """
        return self.probe_once("adapter_defaults", self._parse_adapter_property_defaults)

    def adapter_property_names(self) -> dict[int, dict[str, str]]:
        """``{interface_index: {lowercase keyword: DisplayName}}``.

        The name each property shows in the driver's control panel. Some detect
        commands find their property by it as well as by keyword, so the default
        that belongs to such a property is only reachable through this table.
        """
        return self.probe_once("adapter_names", self._parse_adapter_property_names)

    def default_route_interface_index(self) -> int | None:
        """Memoised; the real query is _query_default_route_interface_index."""
        return self.probe_once("default_route", self._query_default_route_interface_index)

    def _query_active_adapters(self) -> list[NetworkAdapter]:
        """Get list of network adapters via PowerShell.

        Queries Windows for all network adapters (including disabled), excluding virtual ones.
        Returns InterfaceIndex (for commands), Name (for display), and MediaType (for
        medium-aware gating of per-adapter settings).

        BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands to avoid
        issues with special characters and localization in adapter names.

        Returns:
            One NetworkAdapter per physical adapter. Empty if discovery fails.
        """
        try:
            # Return InterfaceIndex,Name pairs separated by |
            # InterfaceIndex is numeric, always safe for commands
            result = process_watch.run(
                [
                    powershell_exe(),
                    "-NoProfile",
                    "-Command",
                    # Get all physical adapters - exclude only true virtual adapters
                    # Use $_.Virtual property (boolean) instead of pattern matching
                    # This correctly identifies USB/Docking station ethernet as physical
                    "Get-NetAdapter | Where-Object {"
                    "-not $_.Virtual -and "
                    "$_.Name -notlike '*vEthernet*' -and "
                    "$_.InterfaceDescription -notlike '*Loopback*'"
                    # The name goes last: it is the one field Windows lets a
                    # user type, so it is the one that may contain the separator.
                    "} | ForEach-Object { "
                    '"$($_.InterfaceIndex)|$($_.PnPDeviceID)|$($_.MediaType)|$($_.Name)" }',
                ],
                process_watch.QUERY,
            )

            if result.returncode != 0:
                logger.warning(
                    "PowerShell adapter discovery failed. Exit code: %d, Stderr: %s",
                    result.returncode,
                    result.stderr.strip() if result.stderr else "N/A",
                )
                return []

            adapters: list[NetworkAdapter] = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|", 3)
                if len(parts) != 4:
                    continue
                index_text, instance_id, media_type, name = (part.strip() for part in parts)
                if not index_text.isdigit() or not name:
                    logger.debug("Skipping adapter line: %r", line)
                    continue
                adapters.append(NetworkAdapter(int(index_text), name, media_type, instance_id))
            return adapters

        except subprocess.TimeoutExpired as e:
            logger.warning("Adapter discovery %s", e)
            return []
        except Exception as e:
            logger.warning(
                "Failed to get active adapters. Error: %s",
                e,
            )
            return []

    def _query_adapter_advanced(self) -> dict[str, Any]:
        """Every adapter's advanced properties, in one PowerShell for the machine.

        Returns ``{"<interface_index>": {"defaults": {keyword: default}, "names":
        {keyword: display name}, "rss": {...}}}``; ``rss`` is present only where
        the driver publishes ``*NumRssQueues``. An empty dict when the query fails.
        """
        try:
            result = process_watch.run(
                [
                    powershell_exe(),
                    "-NoProfile",
                    "-Command",
                    # Get-NetAdapterAdvancedProperty does not expose
                    # InterfaceIndex (#31), so resolve it from the adapter name
                    # the same way the per-scan property snapshot does.
                    "$map = @{}; "
                    "Get-NetAdapter -ErrorAction SilentlyContinue | "
                    "ForEach-Object { $map[$_.Name] = $_.InterfaceIndex }; "
                    "$out = @{}; "
                    "Get-NetAdapterAdvancedProperty -AllProperties -ErrorAction SilentlyContinue | "
                    "ForEach-Object { "
                    "$idx = $map[$_.Name]; "
                    "if ($null -ne $idx -and $_.RegistryKeyword) { "
                    "$k = [string]$idx; "
                    "if (-not $out.ContainsKey($k)) { "
                    "$out[$k] = @{ defaults = @{}; names = @{} } }; "
                    "$out[$k].defaults[$_.RegistryKeyword] = [string]$_.DefaultRegistryValue; "
                    "$out[$k].names[$_.RegistryKeyword] = [string]$_.DisplayName; "
                    "if ($_.RegistryKeyword -eq '*NumRssQueues') { $out[$k].rss = @{ "
                    "valid = @($_.ValidRegistryValues); "
                    "default = [string]$_.DefaultRegistryValue; "
                    "min = $_.NumericParameterMinValue; "
                    "max = $_.NumericParameterMaxValue } } } }; "
                    "$out | ConvertTo-Json -Compress -Depth 5",
                ],
                process_watch.QUERY,
            )
            if result.returncode != 0 or not result.stdout.strip():
                logger.debug("Adapter advanced-property discovery returned nothing")
                return {}
            payload = json.loads(result.stdout.strip())
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError) as e:
            logger.debug("Adapter advanced-property discovery failed: %s", e)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _parse_adapter_property_defaults(self) -> dict[int, dict[str, str]]:
        defaults: dict[int, dict[str, str]] = {}
        for raw_index, entry in self.adapter_advanced().items():
            if not str(raw_index).isdigit() or not isinstance(entry, dict):
                continue
            table = entry.get("defaults")
            if not isinstance(table, dict):
                continue
            defaults[int(raw_index)] = {
                str(keyword).lower(): str(value).strip()
                for keyword, value in table.items()
                if str(value).strip()
            }
        return defaults

    def _parse_adapter_property_names(self) -> dict[int, dict[str, str]]:
        names: dict[int, dict[str, str]] = {}
        for raw_index, entry in self.adapter_advanced().items():
            if not str(raw_index).isdigit() or not isinstance(entry, dict):
                continue
            table = entry.get("names")
            if not isinstance(table, dict):
                continue
            names[int(raw_index)] = {
                str(keyword).lower(): str(value).strip()
                for keyword, value in table.items()
                if str(value).strip()
            }
        return names

    def _parse_rss_queue_options(self) -> dict[int, tuple[tuple[str, ...], str]]:
        """Read each adapter's own accepted ``*NumRssQueues`` values.

        Returns ``{interface_index: (queue_counts, driver_default)}``, holding
        only adapters whose driver exposes the keyword. An adapter that is
        absent from the result has no RSS queue control, which is exactly what
        the setting's detect command would have reported as ``not_supported``.

        Drivers describe the keyword in one of two ways and both are read here:
        an enum publishes ``ValidRegistryValues``, while a numeric keyword
        publishes a min/max range instead. RSS queue counts are powers of two,
        so a range is expanded as such rather than as every integer in it.
        """
        options: dict[int, tuple[tuple[str, ...], str]] = {}
        for raw_index, adapter in self.adapter_advanced().items():
            entry = adapter.get("rss") if isinstance(adapter, dict) else None
            if not isinstance(entry, dict):
                continue
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue

            counts = positive_ints(entry.get("valid"))
            if not counts:
                counts = powers_of_two_between(entry.get("min"), entry.get("max"))
            if not counts:
                logger.debug(
                    "Adapter %d publishes *NumRssQueues but names no accepted values", index
                )
                continue

            default = str(entry.get("default", "")).strip()
            # A driver that publishes the keyword but no default still has one:
            # whatever it is currently set to is not knowable here, so fall back
            # to the largest count it accepts, which is what "unrestricted" means.
            if default not in {str(count) for count in counts}:
                default = str(counts[-1])

            options[index] = (tuple(str(count) for count in counts), default)

        return options

    def _query_default_route_interface_index(self) -> int | None:
        """Return the InterfaceIndex carrying the default IPv4 route, if there is one."""
        try:
            result = process_watch.run(
                [
                    powershell_exe(),
                    "-NoProfile",
                    "-Command",
                    "$r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' "
                    "-ErrorAction SilentlyContinue | Sort-Object RouteMetric | "
                    "Select-Object -First 1; if ($r) { $r.InterfaceIndex }",
                ],
                process_watch.QUERY,
            )
            if result.returncode != 0:
                return None
            output = result.stdout.strip()
            return int(output) if output.isdigit() else None
        except (subprocess.TimeoutExpired, ValueError, OSError) as e:
            logger.debug("Default route lookup failed: %s", e)
            return None
