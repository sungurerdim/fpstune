"""Per-scan batched PowerShell query cache.

Replaces N identical subprocess calls (Get-Service, Get-NetAdapterAdvancedProperty)
with a single batch query per scan.

The cache lives in a ContextVar and is created fresh by every scan, so a run can
never read another run's stale snapshot. Reaching worker threads is the caller's
job: ThreadPoolExecutor does *not* propagate contextvars on its own, so
DetectionEngine submits each task through ``copy_context().run`` — without that,
every worker sees an empty cache and re-runs the query this module exists to
avoid. Workers only read; writes happen before threads are spawned.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, Token
from typing import Any, cast

from fpstune.settings.applicability import NOT_SUPPORTED
from fpstune.utils.powershell import run_powershell

logger = logging.getLogger(__name__)

_ScanCache = dict[str, Any]

# ContextVar holding the per-scan cache dict. None means "no active scan context"
# (single-setting detect outside a full scan). Python 3.12 copies context to worker
# threads at submit() time so all workers share the same dict reference.
_ps_scan_cache: ContextVar[dict[str, Any] | None] = ContextVar("ps_scan_cache", default=None)


def init_scan_cache() -> tuple[dict[str, Any], Token[_ScanCache | None]]:
    """Create and activate a fresh scan cache. Call once before spawning detect threads.

    Returns (cache_dict, token). Pass token to reset_scan_cache() after scan completes.
    """
    cache: dict[str, Any] = {}
    token = _ps_scan_cache.set(cache)
    return cache, token


def reset_scan_cache(token: Token[_ScanCache | None]) -> None:
    """Restore previous scan cache state after scan completes."""
    _ps_scan_cache.reset(token)


def _get_cache() -> dict[str, Any] | None:
    """Return active cache dict or None if outside a scan context."""
    return _ps_scan_cache.get()


_locks_guard = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}


def cache_once[T](cache: dict[str, Any], key: str, compute: Callable[[], T]) -> T:
    """Return ``cache[key]``, computing it at most once across threads.

    A plain check-then-compute lets every worker that misses run the same
    multi-second query: measured, ten threads each ran the Get-Service snapshot
    the batch exists to avoid. The lock is per key, so a slow snapshot does not
    hold up an unrelated one, and it is module-level while the cache is
    per-scan — two overlapping scans serialise on a key but still fill their
    own cache.
    """
    if key in cache:
        return cast("T", cache[key])
    with _locks_guard:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        if key in cache:
            return cast("T", cache[key])
        value = compute()
        cache[key] = value
        return value


def _fetch_services_snapshot() -> dict[str, dict[str, Any]]:
    """Run Get-Service once and return {lowercase_name: {start_type}} map."""
    snapshot: dict[str, dict[str, Any]] = {}
    if sys.platform != "win32":
        return snapshot

    cmd = "Get-Service | Select-Object -Property Name,StartType | ConvertTo-Json -Compress -Depth 1"
    success, output = run_powershell(cmd, timeout=15)
    if success and output and output.strip():
        try:
            data = json.loads(output.strip())
            items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
            for item in items:
                name = str(item.get("Name", ""))
                if name:
                    snapshot[name.lower()] = {"start_type": item.get("StartType")}
        except (json.JSONDecodeError, AttributeError, TypeError) as exc:
            logger.debug("prefetch_services JSON parse failed: %s", exc)

    logger.debug("[scan] services_snapshot fetched: %d services", len(snapshot))
    return snapshot


def prefetch_services() -> dict[str, dict[str, Any]]:
    """Run Get-Service once and store snapshot in the active scan cache.

    Idempotent — subsequent calls within the same scan return the cached dict.
    Safe to call outside a scan context (result is not cached, just computed).
    """
    cache = _get_cache()
    if cache is not None:
        return cache_once(cache, "services_snapshot", _fetch_services_snapshot)

    # Outside scan context — compute without caching
    return _fetch_services_snapshot()


def _fetch_adapter_properties_snapshot() -> dict[str, Any]:
    """Run Get-NetAdapterAdvancedProperty once for every adapter and keyword.

    Returns {"<ifindex>|<lowercase keyword>": raw_value}. Each per-adapter
    setting otherwise spawns its own PowerShell that reloads the NetAdapter
    module — 20 such settings dominated scan wall-clock.
    """
    snapshot: dict[str, Any] = {}
    if sys.platform != "win32":
        return snapshot

    # Get-NetAdapterAdvancedProperty does NOT expose InterfaceIndex; selecting it
    # yields null on every row, and the null check below then dropped every entry,
    # leaving the snapshot permanently empty. An empty snapshot makes
    # get_adapter_property answer "not_supported" for every keyword, so all
    # per-adapter network settings silently reported as unsupported and never
    # appeared as applicable in the UI. Resolve the index from the adapter Name.
    cmd = (
        "$map = @{}; "
        "Get-NetAdapter -ErrorAction SilentlyContinue | "
        "ForEach-Object { $map[$_.Name] = $_.InterfaceIndex }; "
        "Get-NetAdapterAdvancedProperty -AllProperties -ErrorAction SilentlyContinue | "
        "Select-Object -Property @{Name='InterfaceIndex';Expression={$map[$_.Name]}},"
        "RegistryKeyword,RegistryValue | "
        "ConvertTo-Json -Compress -Depth 3"
    )
    success, output = run_powershell(cmd, timeout=30)
    if not (success and output and output.strip()):
        logger.debug("prefetch_adapter_properties returned no data")
        return snapshot

    try:
        data = json.loads(output.strip())
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("prefetch_adapter_properties JSON parse failed: %s", exc)
        return snapshot

    items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("InterfaceIndex")
        keyword = str(item.get("RegistryKeyword", "")).strip().lower()
        if index is None or not keyword:
            continue
        raw = item.get("RegistryValue")
        # RegistryValue comes back as a single-element array.
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        snapshot[f"{index}|{keyword}"] = raw

    logger.debug("[scan] adapter_properties fetched: %d entries", len(snapshot))
    return snapshot


# Sentinel for "this scan resolved no PnP power state for that adapter".
ADAPTER_POWER_MISSING = "Enabled"

_ADAPTER_POWER_KEY = "adapter_pnp_power"


def _fetch_adapter_power_snapshot() -> dict[str, str]:
    """Read the PnP power-management state of every adapter in one call.

    ``network:<n>:power_management`` resolves an adapter to its PnP device and
    reads ``PnPCapabilities``. The lookup is per-adapter, but the expensive part
    is ``Get-PnpDevice``, which enumerates every device on the machine — so a
    two-NIC machine paid for that enumeration twice, measured at 2.86 s and
    2.62 s of a 21 s scan. Enumerating once and indexing by InterfaceIndex costs
    the same as doing it for one adapter.

    PnPCapabilities: 24 = "allow the computer to turn this device off" cleared,
    anything else (including absent) = still allowed.
    """
    if sys.platform != "win32":
        return {}

    cmd = (
        "$pnp = @{}; "
        "Get-PnpDevice -Class Net -EA SilentlyContinue | ForEach-Object { "
        "$pnp[$_.FriendlyName] = $_.InstanceId }; "
        "$out = @{}; "
        "Get-NetAdapter -EA SilentlyContinue | ForEach-Object { "
        "$id = $pnp[$_.InterfaceDescription]; "
        "$state = 'Enabled'; "
        "if ($id) { "
        '$p = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$id\\Device Parameters"; '
        "$v = (Get-ItemProperty -Path $p -Name 'PnPCapabilities' -EA SilentlyContinue).PnPCapabilities; "
        "if ($v -eq 24) { $state = 'Disabled' } }; "
        "$out[[string]$_.InterfaceIndex] = $state }; "
        "$out | ConvertTo-Json -Compress"
    )
    success, output = run_powershell(cmd, timeout=30, component="ps_batch")
    if not (success and output and output.strip()):
        return {}

    try:
        data = json.loads(output.strip())
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def prefetch_adapter_power() -> dict[str, str]:
    """Populate the scan cache with every adapter's PnP power state."""
    cache = _get_cache()
    if cache is not None:
        return cache_once(cache, _ADAPTER_POWER_KEY, _fetch_adapter_power_snapshot)
    return _fetch_adapter_power_snapshot()


def get_adapter_power_state(ifindex: Any) -> str:
    """Return one adapter's PnP power state from the per-scan snapshot."""
    snapshot = prefetch_adapter_power()
    return snapshot.get(str(ifindex), ADAPTER_POWER_MISSING)


def prefetch_adapter_properties() -> dict[str, Any]:
    """Populate the active scan cache with every adapter advanced property.

    Idempotent within a scan; computed without caching outside one.
    """
    cache = _get_cache()
    if cache is not None:
        return cache_once(cache, "adapter_properties", _fetch_adapter_properties_snapshot)

    return _fetch_adapter_properties_snapshot()


# Sentinel meaning "this adapter does not expose this keyword", matching what
# the per-setting PowerShell commands returned. The spelling comes from the
# applicability contract so detection recognises it as an absence.
ADAPTER_PROPERTY_MISSING = NOT_SUPPORTED


def get_adapter_property(interface_index: Any, keyword: str) -> Any:
    """Return one adapter advanced property from the batch snapshot.

    Falls back to ADAPTER_PROPERTY_MISSING when the adapter does not expose the
    keyword, which is the same sentinel the individual commands produced.
    """
    cache = _get_cache()
    if cache is not None:
        snapshot = cache.get("adapter_properties")
        if snapshot is None:
            snapshot = prefetch_adapter_properties()
    else:
        snapshot = _fetch_adapter_properties_snapshot()

    if not snapshot:
        return ADAPTER_PROPERTY_MISSING

    wanted = keyword.strip().lower()
    value = snapshot.get(f"{interface_index}|{wanted}")

    if value is None:
        # The '*' prefix marks a standardised NDIS keyword; vendor-specific ones
        # carry the bare name. Drivers disagree about which spelling they expose
        # for the same feature — Realtek publishes "AdvancedEEE" while the
        # definition asks for "*AdvancedEEE" — and a definition written for one
        # spelling was silently reported as unsupported on adapters using the
        # other. Try the counterpart before giving up.
        alt = wanted.removeprefix("*") if wanted.startswith("*") else f"*{wanted}"
        value = snapshot.get(f"{interface_index}|{alt}")

    return ADAPTER_PROPERTY_MISSING if value is None else value


_CLEANUP_KEY = "cleanup_sizes"

# The tail that turns the shared cleanup script into a single-type query. The
# batch replaces it with a loop, and derives the preamble by cutting here rather
# than keeping its own copy — two copies of a 15 KB script would drift, and the
# drift would be invisible because both halves would still run.
_CLEANUP_CALL = "Get-CleanupStatus '%type%'"


def _fetch_cleanup_sizes(types: tuple[str, ...]) -> dict[str, str]:
    """Ask one PowerShell session for every cleanup type's reclaimable size.

    Each cleanup setting used to run the whole ~18 KB ``cleanup_status`` script
    in its own process to answer one question about one folder. Measured on the
    dev machine, a cold scan spawned 26 of them — over half of every subprocess
    the scan made — and each one re-parsed the same helpers before doing any
    work. The helpers are identical for all of them, so they are parsed once
    here and the types are asked in a loop.

    Sizing the folders still costs what it costs; this removes the process
    startups and the repeated parse around it.
    """
    if sys.platform != "win32" or not types:
        return {}

    from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

    script = ACTION_COMMANDS.get("cleanup_status", "")
    preamble, marker, _ = script.rpartition(_CLEANUP_CALL)
    if not marker:
        # The shared script no longer ends the way this batch assumes. Answer
        # nothing rather than something: every setting then falls back to its
        # own process, which is exactly today's behaviour rather than a wrong
        # size. Loud, because a silently dead batch is the defect this codebase
        # has shipped twice.
        logger.warning(
            "cleanup_status no longer ends with %r, so sizes cannot be batched "
            "and every cleanup setting will run its own PowerShell",
            _CLEANUP_CALL,
        )
        return {}

    quoted = ", ".join("'" + t.replace("'", "''") + "'" for t in types)
    script = (
        f"{preamble}\n"
        "$__fpstune_out = @{}\n"
        f"foreach ($__fpstune_t in @({quoted})) {{\n"
        "  try { $__fpstune_out[$__fpstune_t] = "
        "(Get-CleanupStatus $__fpstune_t | Out-String).Trim() }\n"
        "  catch { }\n"
        "}\n"
        f"Write-Output '{DETECT_JSON_MARKER}'\n"
        "$__fpstune_out | ConvertTo-Json -Compress -Depth 2"
    )

    # Folder sizing dominates: a large npm or shader cache takes real seconds,
    # and this now carries every type in one call.
    success, output = run_powershell(script, timeout=30 + 12 * len(types), component="ps_batch")
    if not (success and output and output.strip()):
        logger.debug("cleanup size batch produced nothing")
        return {}

    _, marker, tail = output.rpartition(DETECT_JSON_MARKER)
    try:
        data = json.loads((tail if marker else output).strip())
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("cleanup size batch JSON parse failed: %s", exc)
        return {}

    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}


def prefetch_cleanup_sizes(types: tuple[str, ...]) -> dict[str, str]:
    """Populate the scan cache with every cleanup type's size. Idempotent."""
    cache = _get_cache()
    if cache is None:
        return _fetch_cleanup_sizes(types)
    return cache_once(cache, _CLEANUP_KEY, lambda: _fetch_cleanup_sizes(types))


_DETECTS_KEY = "powershell_detects"

# How many detect sessions may run at once. Concurrent PowerShell starts inflate
# each other, so this cannot simply be raised; the optimum was measured over a
# full 322-setting scan rather than reasoned about, and it is a genuine peak:
#     4 sessions  4.67 s      8 sessions  4.00 s
#     6 sessions  3.96 s     10 sessions  4.11 s
# Past six, the extra startups cost more than the commands they take on.
MAX_DETECT_SESSIONS = 6

# Upper bound on commands per session, so one slow command cannot hold up an
# unbounded number of settings and the generated script stays well under the
# command line limit.
DETECT_GROUP_SIZE = 20


def _partition(specs: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Split commands into at most MAX_DETECT_SESSIONS near-equal sessions.

    Fixed-size chunking produced one group too many for the concurrency cap —
    53 commands became five groups of 12 against four slots, so the fifth waited
    for a free session and doubled the phase. Balancing across the slots removes
    that tail: the cost of a session is dominated by its startup, not by whether
    it carries 12 commands or 14.
    """
    if not specs:
        return []
    size = min(DETECT_GROUP_SIZE, -(-len(specs) // MAX_DETECT_SESSIONS))
    size = max(1, size)
    return [specs[start : start + size] for start in range(0, len(specs), size)]


# Prefix marking a command that raised, so a failure is never mistaken for a value.
DETECT_ERROR_PREFIX = "__fpstune_err__"


# Marks the start of the group's JSON document. Anything a command wrote
# straight to the host lands ahead of it and is skipped rather than swallowing
# the whole group — see _run_detect_group.
DETECT_JSON_MARKER = "__fpstune_json__"


def command_is_batchable(command: str) -> bool:
    """Whether a detect command is safe to run alongside others in one session.

    ``exit`` is excluded: at the top level of a ``-Command`` script it ends the
    whole session, which would silently blank every remaining setting in the
    group rather than failing loudly. Measured: neither ``& { }`` nor
    ``[scriptblock]::Create(...).Invoke()`` contains it — both kill the process.

    ``Write-Host`` is excluded because it writes past the pipeline: the group
    captures each command with ``| Out-String``, which never sees host output,
    so the FPSTUNE_WARN lines those commands exist to emit would be lost from
    the value *and* land in the session's own stdout. Measured on the dev
    machine: two such commands cost their entire group of 12 settings, all of
    which then fell back to a live subprocess each.
    """
    stripped = command.strip()
    if not stripped:
        return False
    if re.search(r"(^|[;{(\s])exit\b", stripped):
        return False
    return "write-host" not in stripped.lower()


def _build_group_script(specs: list[tuple[str, str]]) -> str:
    """Wrap each command in its own scope with independent error handling."""
    lines = ["$out = @{}"]
    for setting_id, command in specs:
        key = setting_id.replace("'", "''")
        # try/catch as a statement (not an expression) so this stays valid on
        # Windows PowerShell 5.1, and & { } so one command's variables and
        # early returns cannot leak into the next.
        lines.append(
            f"try {{ $v = (& {{ {command} }} | Out-String).Trim() }} "
            f"catch {{ $v = '{DETECT_ERROR_PREFIX}' + $_.Exception.Message }}; "
            f"$out['{key}'] = $v"
        )
    lines.append(f"Write-Output '{DETECT_JSON_MARKER}'")
    lines.append("$out | ConvertTo-Json -Compress -Depth 2")
    return "; ".join(lines)


def _run_detect_group(specs: list[tuple[str, str]]) -> dict[str, str]:
    """Execute one group and return {setting_id: raw output}."""
    results: dict[str, str] = {}
    if not specs:
        return results

    script = _build_group_script(specs)
    # Budget scales with group size; a single command's own timeout no longer
    # applies because they share a process.
    success, output = run_powershell(script, timeout=15 + 8 * len(specs))
    if not (success and output and output.strip()):
        logger.debug("powershell detect group failed (%d commands)", len(specs))
        return results

    # Take only what follows the marker. Without this one command writing past
    # the pipeline — a warning, a progress line, a cmdlet that talks to the host
    # — makes the whole document unparseable and costs every setting in the
    # group, which is not a failure mode worth leaving to discipline alone.
    _, marker, tail = output.rpartition(DETECT_JSON_MARKER)
    payload = (tail if marker else output).strip()

    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("powershell detect group JSON parse failed: %s", exc)
        return results

    if not isinstance(data, dict):
        return results

    for setting_id, value in data.items():
        if isinstance(value, str) and not value.startswith(DETECT_ERROR_PREFIX):
            results[str(setting_id)] = value
    return results


def prefetch_powershell_detects(specs: list[tuple[str, str]]) -> dict[str, str]:
    """Run many detect commands in a few sessions instead of one each.

    Only results that succeeded are cached; anything missing falls back to the
    per-setting path, so a failed group degrades to today's behaviour instead
    of producing wrong values.
    """
    cache = _get_cache()
    if cache is None:
        return {}

    store: dict[str, str] = cache.setdefault(_DETECTS_KEY, {})
    pending = [(sid, cmd) for sid, cmd in specs if sid not in store]
    if not pending or sys.platform != "win32":
        return store

    groups = _partition(pending)

    # The groups run before the detection thread pool starts, so running them
    # sequentially would put their whole cost on the scan's critical path.
    # Sessions are independent, so they overlap; the cap keeps concurrent
    # PowerShell startups low enough that they don't slow each other down
    # (measured: 4 concurrent ≈ 1.4x a single start, 16 ≈ 3.2x).
    if len(groups) == 1:
        store.update(_run_detect_group(groups[0]))
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_DETECT_SESSIONS, len(groups))) as pool:
            for result in pool.map(_run_detect_group, groups):
                store.update(result)

    logger.debug("[scan] powershell detects batched: %d/%d resolved", len(store), len(specs))
    return store


def get_batched_detect(setting_id: str) -> str | None:
    """Return a batched detect result, or None to fall back to a live run."""
    cache = _get_cache()
    if cache is None:
        return None
    store = cache.get(_DETECTS_KEY)
    if not isinstance(store, dict):
        return None
    value = store.get(setting_id)
    return value if isinstance(value, str) else None


def get_service_start_type(service_name: str) -> str:
    """Return service StartType string from snapshot: '2', '3', '4', or 'not_found'.

    StartType values: 2=Automatic, 3=Manual, 4=Disabled.
    Reads from scan cache if available; otherwise fetches on-demand.
    """
    cache = _get_cache()
    if cache is not None:
        snapshot = cache.get("services_snapshot")
        if snapshot is None:
            # Cache exists but snapshot not yet loaded (shouldn't happen if prefetch called)
            snapshot = prefetch_services()
    else:
        # Single-setting detect outside a full scan — fetch on-demand
        snapshot = _fetch_services_snapshot()

    entry = snapshot.get(service_name.lower())
    if entry is None:
        return "not_found"

    st = entry.get("start_type")
    if st is None:
        return "not_found"
    try:
        return str(int(st))
    except (ValueError, TypeError):
        return str(st)
