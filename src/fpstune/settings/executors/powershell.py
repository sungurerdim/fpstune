"""PowerShell executor for advanced Windows operations."""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING, Any

from fpstune.settings.executors import BaseExecutor, map_raw_to_display
from fpstune.settings.executors.powershell_actions import (
    ACTION_COMMANDS,
    CONSTANT_STATUS_ACTIONS,
)
from fpstune.settings.executors.ps_batch import get_batched_detect
from fpstune.utils.powershell import run_powershell, substitute_placeholders

_logger = logging.getLogger(__name__)

# Cap concurrent background cleanup-size scans. Each size-bearing cleanup spawns
# its own daemon → its own powershell.exe; with ~20 cleanups that is a 20-process
# disk/CPU burst on app load. A small bound keeps several scans running in
# parallel (fast) without thrashing the machine (the cache returns "calculating"
# immediately, so queued scans just resolve a beat later via polling).
_CLEANUP_SCAN_LIMIT = 4
_cleanup_scan_semaphore = threading.BoundedSemaphore(_CLEANUP_SCAN_LIMIT)

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


def _store_cleanup_reading(setting_id: str, reading: str) -> bool:
    """Turn one ``ready|<size>`` line into a cache entry. False if unparseable.

    Shared by the per-setting fallback and the batch, so the two cannot disagree
    about what "unavailable" or "not_installed" means for the same output.
    """
    from fpstune.settings.cleanup_cache import cleanup_size_cache

    for line in reversed(reading.splitlines()):
        s = line.strip()
        if not s.startswith("ready|"):
            continue
        size_part = s[6:].strip()
        # Service/daemon not running (e.g. Docker engine down): surface as
        # unavailable so the UI shows that, not "0 MB".
        if size_part.lower() == "unavailable":
            cleanup_size_cache.set_unavailable(setting_id)
            return True
        # Target software/dirs absent → not applicable (hidden, uncounted).
        if size_part.lower() == "not_installed":
            cleanup_size_cache.set_not_installed(setting_id)
            return True
        if size_part and "?" not in size_part and "MB" in size_part:
            try:
                mb = int(size_part.split()[0])
                cleanup_size_cache.set_result(setting_id, mb * 1024 * 1024)
                return True
            except (ValueError, IndexError):
                pass
    return False


_cleanup_batch_lock = threading.Lock()
_cleanup_batch_running = False


def start_cleanup_size_batch(settings: list[SettingExecutor]) -> None:
    """Size every pending cleanup target in one PowerShell, in the background.

    Each cleanup setting used to get its own daemon thread running the whole
    ~18 KB ``cleanup_status`` script to answer one question. Measured cold on the
    dev machine: 26 PowerShell processes, more than half of everything the scan
    spawned, each re-parsing the same helpers before touching a folder.

    Deliberately still asynchronous, and deliberately not awaited. Folder sizing
    is genuinely slow — ``dism /AnalyzeComponentStore`` alone runs 30-60 s — so
    putting it on the scan's critical path would trade 25 processes for a scan
    nobody waits through. The UI keeps its "calculating" state and fills in.

    Returns immediately. Settings already in the cache are left alone.
    """
    global _cleanup_batch_running
    from fpstune.settings.cleanup_cache import cleanup_size_cache

    pending: dict[str, list[str]] = {}
    for setting in settings:
        if setting.detect_command.strip() != "cleanup_status":
            continue
        if cleanup_size_cache.get(setting.id) is not None:
            continue
        cleanup_type = str(setting.detect_args.get("type", "")).strip()
        if cleanup_type:
            pending.setdefault(cleanup_type, []).append(setting.id)

    if not pending:
        return

    with _cleanup_batch_lock:
        if _cleanup_batch_running:
            return
        _cleanup_batch_running = True

    # Claim them before the thread starts, so a detect racing this one reads
    # "calculating" and does not start a second computation of the same folder.
    for ids in pending.values():
        for setting_id in ids:
            cleanup_size_cache.mark_calculating(setting_id)

    def _run() -> None:
        global _cleanup_batch_running
        from fpstune.settings.executors.ps_batch import _fetch_cleanup_sizes

        try:
            sizes = _fetch_cleanup_sizes(tuple(pending))
        except Exception as exc:  # pragma: no cover - environment dependent
            _logger.debug("cleanup size batch failed: %s", exc)
            sizes = {}
        finally:
            with _cleanup_batch_lock:
                _cleanup_batch_running = False

        for cleanup_type, setting_ids in pending.items():
            reading = sizes.get(cleanup_type, "")
            for setting_id in setting_ids:
                # Every id claimed above must end up with an outcome. A
                # "calculating" entry has no TTL, so one left behind would show
                # a spinner that never resolves for the life of the process.
                if not (reading and _store_cleanup_reading(setting_id, reading)):
                    cleanup_size_cache.set_unavailable(setting_id)

    try:
        threading.Thread(target=_run, daemon=True, name="cleanup-sizes-batch").start()
    except Exception:
        # The flag is set above, so a thread that never starts would block every
        # later batch for the life of the process while the settings it claimed
        # sit on "calculating" forever. Hand them back instead.
        with _cleanup_batch_lock:
            _cleanup_batch_running = False
        for ids in pending.values():
            for setting_id in ids:
                cleanup_size_cache.set_unavailable(setting_id)
        raise


def _start_bg_cleanup_detection(setting_id: str, cmd: str) -> None:
    """Run cleanup_status PS in a daemon thread; store result in cleanup_size_cache.

    The per-setting fallback, for a cleanup the batch did not cover.
    """
    from fpstune.settings.cleanup_cache import cleanup_size_cache

    def _compute() -> None:
        with _cleanup_scan_semaphore:
            _compute_inner()

    def _compute_inner() -> None:
        try:
            ok, out = run_powershell(cmd, timeout=90)
            if ok and out and _store_cleanup_reading(setting_id, out):
                return
        except Exception:
            pass
        # No parseable "ready|<size>" line and no explicit "unavailable" marker.
        # Don't write a fake 0 (reads in the UI as "nothing to clean" and flashes
        # "0 MB"); surface unavailable so the short-TTL cache recomputes instead.
        cleanup_size_cache.set_unavailable(setting_id)

    threading.Thread(target=_compute, daemon=True, name=f"cleanup-{setting_id}").start()


class PowerShellExecutor(BaseExecutor):
    """Execute PowerShell commands for network adapter and other settings.

    Handles network adapter properties, advanced system queries, etc.
    Also handles special action commands for maintenance operations.

    detect_command/apply_command use %placeholder% syntax for substitution.
    This avoids conflicts with PowerShell {} braces and regex quantifiers.
    """

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        """Detect a value using PowerShell."""
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return None, "Not available on this platform"

        # Fast path: service settings use the pre-fetched batch snapshot.
        batch_service = setting.detect_args.get("batch_service")
        if batch_service:
            from fpstune.settings.executors.ps_batch import get_service_start_type

            raw = get_service_start_type(str(batch_service))
            debug_log(
                "powershell", f"DETECT BATCH_SERVICE {setting.id}: {batch_service!r} → {raw!r}"
            )
            mapped = map_raw_to_display(setting.value_map, raw)
            return mapped, None

        # Fast path: per-adapter advanced properties come from one batch query
        # instead of one PowerShell process per keyword.
        batch_keyword = setting.detect_args.get("batch_adapter_keyword")
        if batch_keyword:
            from fpstune.settings.executors.ps_batch import (
                ADAPTER_PROPERTY_MISSING,
                get_adapter_property,
            )

            # A list is accepted, not just one name, because vendors spell the same
            # feature differently (Intel `*EEE`, Realtek `EEE`, Broadcom `EEEControl`)
            # and several settings therefore probe a handful of candidates. Those
            # settings were doing it with one live PowerShell call per spelling —
            # measured at 2.5-3.8 s each — while the snapshot already holds every
            # keyword the adapter publishes and can answer all of them for free.
            # First hit wins, matching the order the live command tried.
            candidates = (
                [str(k) for k in batch_keyword]
                if isinstance(batch_keyword, (list, tuple))
                else [str(batch_keyword)]
            )
            ifindex = setting.detect_args.get("ifindex")
            batched: Any = ADAPTER_PROPERTY_MISSING
            for candidate in candidates:
                batched = get_adapter_property(ifindex, candidate)
                if batched != ADAPTER_PROPERTY_MISSING:
                    break
            debug_log(
                "powershell",
                f"DETECT BATCH_ADAPTER {setting.id}: {candidates!r} → {batched!r}",
            )
            if batched == ADAPTER_PROPERTY_MISSING:
                return ADAPTER_PROPERTY_MISSING, None
            return map_raw_to_display(setting.value_map, batched), None

        # Fast path: the PnP power state of every adapter comes from one
        # enumeration instead of one Get-PnpDevice sweep per NIC.
        if setting.detect_args.get("batch_pnp_power"):
            from fpstune.settings.executors.ps_batch import get_adapter_power_state

            raw = get_adapter_power_state(setting.detect_args.get("ifindex"))
            debug_log("powershell", f"DETECT BATCH_PNP_POWER {setting.id}: → {raw!r}")
            return map_raw_to_display(setting.value_map, raw), None

        # Fast path: every Get-NetTCPSetting property comes off one object, so a
        # POWERSHELL-type setting can share the snapshot the netsh path builds
        # instead of running the same cmdlet again.
        batch_tcp = setting.detect_args.get("batch_tcp")
        if batch_tcp:
            from fpstune.settings.executors.netsh import get_tcp_property

            raw = get_tcp_property(str(batch_tcp))
            debug_log("powershell", f"DETECT BATCH_TCP {setting.id}: {batch_tcp!r} → {raw!r}")
            return map_raw_to_display(setting.value_map, raw), None

        # Fast path: game config files are read once per scan in Python.
        # 47 MW3 settings share one options file and 24 CS2 settings share one
        # autoexec.cfg; each used to spawn its own PowerShell.
        batch_config = setting.detect_args.get("batch_config")
        if batch_config:
            from fpstune.settings.executors.game_config_cache import (
                get_cs2_marker,
                get_hots_variable,
                get_mw3_option,
                get_mw3_options_any_true,
                get_mw4_option,
                get_mw4_options_agreed,
            )

            if batch_config == "mw3":
                mw3_key = setting.detect_args["batch_key"]
                # A list means a named-compound: several cst keys that each switch
                # the same behaviour on, so the concept is off only when all are.
                if isinstance(mw3_key, (list, tuple)):
                    raw = get_mw3_options_any_true([str(k) for k in mw3_key])
                else:
                    raw = get_mw3_option(str(mw3_key))
            elif batch_config == "mw4":
                # MW4 keeps two files and a key can appear in both, so the
                # setting names which one it reads. Defaulting to the global
                # file matches where all but a handful of keys live.
                mw4_key = setting.detect_args["batch_key"]
                mw4_source = str(setting.detect_args.get("batch_source", "global"))
                if isinstance(mw4_key, (list, tuple)):
                    # A named-compound: scopes that hold the same value list and
                    # mean the same thing, so the concept is only at a value
                    # when every one of them is.
                    raw = get_mw4_options_agreed([str(k) for k in mw4_key], mw4_source)
                else:
                    raw = get_mw4_option(str(mw4_key), mw4_source)
            elif batch_config == "hots":
                raw = get_hots_variable(str(setting.detect_args["batch_key"]))
            elif batch_config == "nvidia_app":
                # Not a game config, but the same shape: one file read in Python
                # instead of a PowerShell process per setting that wants it.
                from fpstune.settings.executors.nvidia_app import battery_boost_exposure

                raw = battery_boost_exposure()
            elif batch_config == "cs2":
                raw = get_cs2_marker(
                    str(setting.detect_args["batch_marker"]),
                    str(setting.detect_args["batch_present"]),
                    str(setting.detect_args["batch_absent"]),
                )
            else:
                # Named explicitly rather than falling through to CS2. The branch
                # used to be `else: cs2`, so a new game whose args did not match
                # would have been read as a CS2 marker lookup and reported against
                # the wrong file.
                raise KeyError(f"unknown batch_config {batch_config!r} on {setting.id}")
            debug_log("powershell", f"DETECT BATCH_CONFIG {setting.id}: → {raw!r}")
            return map_raw_to_display(setting.value_map, raw), None

        # Check for special action commands
        cmd_key = setting.detect_command.strip()

        # Some action commands have no state to read: the operation is simply
        # always available. Their detect script is the literal `Write-Output
        # $true`, so running it started a PowerShell process to learn a constant
        # — measured, three of the twenty-five a cold scan spawned. The answer
        # still goes through `value_map`, so it is the same value by the same
        # route, just without the process.
        constant = CONSTANT_STATUS_ACTIONS.get(cmd_key)
        if constant is not None:
            debug_log("powershell", f"DETECT CONSTANT {setting.id}: {cmd_key} → {constant!r}")
            return map_raw_to_display(setting.value_map, constant), None

        # Cleanup status: serve from background cache; kick off PS in a daemon thread on miss.
        if cmd_key == "cleanup_status":
            from fpstune.settings.cleanup_cache import cleanup_size_cache

            entry = cleanup_size_cache.get(setting.id)
            if entry is not None:
                if entry["status"] == "calculating":
                    return "ready|calculating", None
                if entry["status"] == "unavailable":
                    return "ready|unavailable", None
                if entry["status"] == "not_installed":
                    # Maps to is_applicable=False in the detection engine → hidden.
                    return "not_available", None
                mb = entry["bytes"] // (1024 * 1024)
                return f"ready|{mb} MB", None
            # Cache miss: start background calculation and return immediately.
            cleanup_size_cache.mark_calculating(setting.id)
            try:
                bg_cmd = substitute_placeholders(ACTION_COMMANDS[cmd_key], **setting.detect_args)
            except ValueError as exc:
                cleanup_size_cache.set_unavailable(setting.id)
                return None, f"PowerShell command rejected: {exc}"
            _start_bg_cleanup_detection(setting.id, bg_cmd)
            return "ready|calculating", None

        # A value the escaping layer cannot place safely is a refused command,
        # not a failed detector: reported in this executor's own failure shape so
        # the route answers with a rejection rather than a server error.
        try:
            if cmd_key in ACTION_COMMANDS:
                cmd = substitute_placeholders(ACTION_COMMANDS[cmd_key], **setting.detect_args)
            else:
                cmd = substitute_placeholders(setting.detect_command, **setting.detect_args)
        except ValueError as exc:
            return None, f"PowerShell command rejected: {exc}"

        debug_log("powershell", f"DETECT CMD for {setting.id}: {cmd[:200]}...")

        # Use longer timeout for known slow detection commands.
        # cleanup_status with type=dism runs AnalyzeComponentStore which can take 30-60s.
        _slow_detect_commands = {
            "memory_status",
            "cleanup_status",
            "maintenance_status",
        }
        # Resolution order: per-setting override -> known-slow heuristic -> default 30s.
        if setting.detect_timeout is not None:
            timeout = setting.detect_timeout
        elif cmd_key in _slow_detect_commands:
            timeout = 90
        else:
            timeout = 30

        # A scan runs these commands in shared sessions, because starting a
        # PowerShell costs far more than any of them. Anything the batch did
        # not resolve — a failed group, an excluded command, or a detect
        # outside a scan — runs live here, so this stays a pure optimisation.
        batched = get_batched_detect(setting.id)
        if batched is not None:
            debug_log("powershell", f"DETECT BATCHED {setting.id}: {batched[:200]!r}")
            success, output = True, batched
        else:
            success, output = self._run(cmd, timeout=timeout)

        debug_log(
            "powershell",
            f"DETECT OUTPUT {setting.id}: success={success}, output={repr(output[:500]) if output else 'None'}",
        )

        if not success:
            return None, f"PowerShell failed: {output}"

        # Extract FPSTUNE_WARN: diagnostic lines from output and log them,
        # then use only the remaining lines as the actual value.
        # Detection scripts write "FPSTUNE_WARN: msg" to inform users of missing
        # tools or system features without failing the detection entirely.
        value_lines: list[str] = []
        if output:
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.startswith("FPSTUNE_WARN:"):
                    msg = stripped[len("FPSTUNE_WARN:") :].strip()
                    _logger.info("[%s] %s", setting.id, msg)
                elif stripped:
                    value_lines.append(stripped)

        raw_value = value_lines[-1] if value_lines else None

        debug_log("powershell", f"DETECT PARSE {setting.id}: raw_value={repr(raw_value)}")

        # Handle empty output
        if not raw_value:
            if None in setting.value_map:
                mapped = setting.value_map[None]
                debug_log("powershell", f"DETECT MAP {setting.id}: None -> {repr(mapped)}")
                return mapped, None
            return None, None

        # Map raw value to display value if mapping exists
        if setting.value_map:
            mapped = map_raw_to_display(setting.value_map, raw_value)
            debug_log("powershell", f"DETECT MAP {setting.id}: {repr(raw_value)} -> {repr(mapped)}")
            return mapped, None

        return raw_value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        """Apply a value using PowerShell."""
        from fpstune.utils.debug import debug_log

        if sys.platform != "win32":
            return False, "Not available on this platform"

        # A game holds its config in memory and flushes it on exit, so writing
        # into a running session is undone minutes later — after apply and verify
        # have both reported success. Refusing here is the only place that can
        # catch it, because every downstream check reads the file fpstune wrote.
        from fpstune.settings.executors.game_processes import refuse_if_game_is_running

        refusal = refuse_if_game_is_running(setting.id)
        if refusal:
            debug_log("powershell", f"APPLY BLOCKED {setting.id}: {refusal}")
            return False, refusal

        # Convert display value to raw value
        raw_value = setting.apply_value_map.get(value, value)
        debug_log(
            "powershell", f"APPLY {setting.id}: display={repr(value)} -> raw={repr(raw_value)}"
        )

        # Fast path: MW4 rewrites one line of a text file, which Python does
        # directly. Routing it through PowerShell would cost a process per
        # setting and duplicate the suffix-preserving rewrite that mw4_config
        # already owns — and a second implementation is a second thing to get
        # wrong about `@scope`.
        if setting.apply_args.get("batch_config") == "mw4":
            from fpstune.settings.applicability import NOT_INSTALLED
            from fpstune.settings.executors.mw4_config import (
                Mw4ValueRejected,
                set_mw4_option,
                set_mw4_options,
            )

            mw4_key = setting.apply_args["batch_key"]
            mw4_source = str(setting.apply_args.get("batch_source", "global"))
            try:
                if isinstance(mw4_key, (list, tuple)):
                    written = set_mw4_options([str(k) for k in mw4_key], str(raw_value), mw4_source)
                else:
                    written = set_mw4_option(str(mw4_key), str(raw_value), mw4_source)
            except Mw4ValueRejected as exc:
                # The file's own range said no. Reported rather than written,
                # because MW4 answers a value it dislikes by resetting the key.
                debug_log("powershell", f"APPLY REJECTED {setting.id}: {exc}")
                return False, str(exc)
            if written == NOT_INSTALLED:
                return False, "Modern Warfare IV config file not found"
            debug_log("powershell", f"APPLY MW4 {setting.id}: wrote {written!r}")
            return True, None

        # Check for special action commands
        cmd_key = setting.apply_command.strip()
        args = {**setting.apply_args, "value": raw_value}
        template = ACTION_COMMANDS.get(cmd_key, setting.apply_command)
        # A value the escaping layer cannot place safely is refused, not written.
        # Returning the executor's own failure shape keeps that a rejection the
        # route reports rather than a 500 out of the substitution layer.
        try:
            cmd = substitute_placeholders(template, **args)
        except ValueError as exc:
            debug_log("powershell", f"APPLY REJECTED {setting.id}: {exc}")
            return False, f"PowerShell command rejected: {exc}"

        debug_log("powershell", f"APPLY CMD {setting.id}: {cmd[:300]}...")

        # Increase timeout for long-running actions and service operations
        _slow_apply = {
            "dism_cleanup",
            "sfc_scan",
            "dism_health",
            # Docker prune + wsl shutdown + vhdx compact can take several minutes.
            "docker_prune",
            "docker_prune_all",
            "wsl_compact",
            # Dev tool caches can contain 100k+ files; deletion takes minutes
            "gradle_cache_cleanup",
            "maven_cache_cleanup",
            "npm_cache_cleanup",
            "nuget_cache_cleanup",
            "cargo_cache_cleanup",
            "pnpm_cache_cleanup",
            "yarn_cache_cleanup",
            "pip_cache_cleanup",
        }
        _medium_apply = {
            "service_toggle",
            "hyper_v_only_toggle",
            "vm_platform_toggle",
            "windows_update_cache_cleanup",
            "delivery_optimization_cleanup",
        }
        # Resolution order: per-setting override -> known-slow heuristic -> default 30s.
        if setting.apply_timeout is not None:
            timeout = setting.apply_timeout
        elif cmd_key in _slow_apply:
            timeout = 300
        elif cmd_key in _medium_apply:
            timeout = 60
        else:
            timeout = 30
        success, output = self._run(cmd, timeout=timeout)

        debug_log(
            "powershell",
            f"APPLY RESULT {setting.id}: success={success}, output={repr(output[:300]) if output else 'None'}",
        )

        if not success:
            return False, f"PowerShell failed: {output}"

        return True, None

    def _run(self, command: str, timeout: int = 30) -> tuple[bool, str]:
        """Run PowerShell command and return (success, output).

        Delegates to the shared utility function for consistent behavior.
        """
        return run_powershell(command, timeout=timeout)
