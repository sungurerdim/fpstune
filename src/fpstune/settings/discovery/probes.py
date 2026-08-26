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
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

DEFAULT_ADAPTER_DISCOVERY_TIMEOUT = 10.0


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

    def __init__(
        self, adapter_discovery_timeout: float = DEFAULT_ADAPTER_DISCOVERY_TIMEOUT
    ) -> None:
        self.adapter_discovery_timeout = adapter_discovery_timeout
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
            self.rss_queue_options,
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

    def active_adapters(self) -> list[tuple[int, str, str]]:
        """Memoised; the real query is _query_active_adapters."""
        return self.probe_once("adapters", self._query_active_adapters)

    def rss_queue_options(self) -> dict[int, tuple[tuple[str, ...], str]]:
        """Memoised; the real query is _query_rss_queue_options."""
        return self.probe_once("rss_queues", self._query_rss_queue_options)

    def default_route_interface_index(self) -> int | None:
        """Memoised; the real query is _query_default_route_interface_index."""
        return self.probe_once("default_route", self._query_default_route_interface_index)

    def _query_active_adapters(self) -> list[tuple[int, str, str]]:
        """Get list of network adapters via PowerShell.

        Queries Windows for all network adapters (including disabled), excluding virtual ones.
        Returns InterfaceIndex (for commands), Name (for display), and MediaType (for
        medium-aware gating of per-adapter settings).

        BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands to avoid
        issues with special characters and localization in adapter names.

        Returns:
            List of (interface_index, display_name, media_type) tuples. Empty if discovery fails.
        """
        try:
            # Return InterfaceIndex,Name pairs separated by |
            # InterfaceIndex is numeric, always safe for commands
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    # Get all physical adapters - exclude only true virtual adapters
                    # Use $_.Virtual property (boolean) instead of pattern matching
                    # This correctly identifies USB/Docking station ethernet as physical
                    "Get-NetAdapter | Where-Object {"
                    "-not $_.Virtual -and "
                    "$_.Name -notlike '*vEthernet*' -and "
                    "$_.InterfaceDescription -notlike '*Loopback*'"
                    '} | ForEach-Object { "$($_.InterfaceIndex)|$($_.Name)|$($_.MediaType)" }',
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.adapter_discovery_timeout,
            )

            if result.returncode != 0:
                logger.warning(
                    "PowerShell adapter discovery failed. Exit code: %d, Stderr: %s",
                    result.returncode,
                    result.stderr.strip() if result.stderr else "N/A",
                )
                return []

            adapters = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|", 2)
                if len(parts) >= 2:
                    try:
                        idx = int(parts[0])
                        name = parts[1].strip()
                        media_type = parts[2].strip() if len(parts) == 3 else ""
                        if name:
                            adapters.append((idx, name, media_type))
                    except ValueError:
                        logger.debug("Skipping adapter with invalid index: %r", line)
                        continue
            return adapters

        except subprocess.TimeoutExpired:
            logger.warning(
                "Adapter discovery timed out after %.1f seconds",
                self.adapter_discovery_timeout,
            )
            return []
        except Exception as e:
            logger.warning(
                "Failed to get active adapters. Error: %s",
                e,
            )
            return []

    def _query_rss_queue_options(self) -> dict[int, tuple[tuple[str, ...], str]]:
        """Read each adapter's own accepted ``*NumRssQueues`` values.

        Returns ``{interface_index: (queue_counts, driver_default)}``, holding
        only adapters whose driver exposes the keyword. An adapter that is
        absent from the result has no RSS queue control, which is exactly what
        the setting's detect command would have reported as ``not_supported``.

        Drivers describe the keyword in one of two ways and both are read here:
        an enum publishes ``ValidRegistryValues``, while a numeric keyword
        publishes a min/max range instead. RSS queue counts are powers of two,
        so a range is expanded as such rather than as every integer in it.

        One PowerShell for the whole machine, on the discovery path that already
        runs two — not one per adapter.
        """
        options: dict[int, tuple[tuple[str, ...], str]] = {}
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    # Get-NetAdapterAdvancedProperty does not expose
                    # InterfaceIndex (#31), so resolve it from the adapter name
                    # the same way the per-scan property snapshot does.
                    "$map = @{}; "
                    "Get-NetAdapter -ErrorAction SilentlyContinue | "
                    "ForEach-Object { $map[$_.Name] = $_.InterfaceIndex }; "
                    "$out = @{}; "
                    "Get-NetAdapterAdvancedProperty -AllProperties "
                    "-RegistryKeyword '*NumRssQueues' -ErrorAction SilentlyContinue | "
                    "ForEach-Object { "
                    "$idx = $map[$_.Name]; "
                    "if ($null -ne $idx) { $out[[string]$idx] = @{ "
                    "valid = @($_.ValidRegistryValues); "
                    "default = [string]$_.DefaultRegistryValue; "
                    "min = $_.NumericParameterMinValue; "
                    "max = $_.NumericParameterMaxValue } } }; "
                    "$out | ConvertTo-Json -Compress -Depth 4",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.adapter_discovery_timeout,
            )
            if result.returncode != 0 or not result.stdout.strip():
                logger.debug("RSS queue option discovery returned nothing")
                return options
            payload = json.loads(result.stdout.strip())
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError) as e:
            logger.debug("RSS queue option discovery failed: %s", e)
            return options

        if not isinstance(payload, dict):
            return options

        for raw_index, entry in payload.items():
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
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' "
                    "-ErrorAction SilentlyContinue | Sort-Object RouteMetric | "
                    "Select-Object -First 1; if ($r) { $r.InterfaceIndex }",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.adapter_discovery_timeout,
            )
            if result.returncode != 0:
                return None
            output = result.stdout.strip()
            return int(output) if output.isdigit() else None
        except (subprocess.TimeoutExpired, ValueError, OSError) as e:
            logger.debug("Default route lookup failed: %s", e)
            return None
