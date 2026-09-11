"""PowerShell executor for advanced Windows operations."""

from __future__ import annotations

import json
import logging
import sys
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fpstune.settings.base import Reading
from fpstune.settings.cleanup_measure import store_cleanup_reading
from fpstune.settings.executors import BaseExecutor, map_raw_to_display
from fpstune.settings.executors.powershell_actions import (
    ACTION_COMMANDS,
    constant_status_reading,
    detect_script,
)
from fpstune.settings.executors.ps_batch import get_batched_detect
from fpstune.utils.powershell import (
    run_powershell,
    run_powershell_stream,
    substitute_placeholders,
)

_logger = logging.getLogger(__name__)

# What a streamed apply hands back per line: the text, and whether it redraws the
# line before it (a progress bar) rather than following it.
type LineCallback = Callable[[str, bool], None]

# Cap concurrent background cleanup-size scans. Each size-bearing cleanup spawns
# its own daemon → its own powershell.exe; with ~20 cleanups that is a 20-process
# disk/CPU burst on app load. A small bound keeps several scans running in
# parallel (fast) without thrashing the machine (the cache returns "calculating"
# immediately, so queued scans just resolve a beat later via polling).
_CLEANUP_SCAN_LIMIT = 4
_cleanup_scan_semaphore = threading.BoundedSemaphore(_CLEANUP_SCAN_LIMIT)

# What one per-setting scan may take, and by when its claim on the cache has
# demonstrably failed: its own PowerShell timeout, plus one full wave of waiting
# behind the semaphore, plus process-start slack. Handed to `mark_calculating` so
# an entry cannot outlive the worker that claimed it.
#
# The timeout is the one `cleanup_batch_timeout` derives for that single type, so
# the fallback and the batch agree about what a reading costs. They did not: the
# flat 90 s here would have killed a DISM component store analysis measured at
# 43.0 s before a cleanup and 34.7 s after it, on a machine where the two run
# back to back, and reported "unavailable" for a reading that was on its way.


def _cleanup_scan_timeout(cleanup_type: str | None) -> tuple[int, int]:
    """(timeout, cache deadline) for one per-setting cleanup size scan."""
    from fpstune.settings.executors.ps_batch import cleanup_batch_timeout

    timeout = cleanup_batch_timeout((cleanup_type,) if cleanup_type else ())
    return timeout, timeout * 2 + 30


if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


_cleanup_batch_lock = threading.Lock()
_cleanup_batch_running = False


def start_cleanup_size_batch(settings: list[SettingExecutor]) -> None:
    """Size every pending cleanup target in the background: one pass, one process.

    Each cleanup setting used to get its own daemon thread running the whole
    ~18 KB ``cleanup_status`` script to answer one question. Measured cold on the
    dev machine: 26 PowerShell processes, more than half of everything the scan
    spawned, each re-parsing the same helpers before touching a folder.

    Now the folders are walked in this process, in one thread pool, and PowerShell
    is started only for the handful of readings no walk can take — the component
    store, docker's own accounting, the shadow storage allocation, the event log
    record counts. Measured on the same 17 registered types: 13 406-16 991 ms
    through PowerShell under game load against 209-525 ms here.

    Deliberately still asynchronous, and deliberately not awaited. What is left in
    PowerShell is the slow part — ``dism /AnalyzeComponentStore`` alone runs
    40 s — so putting it on the scan's critical path would trade processes for a
    scan nobody waits through. The UI keeps its "calculating" state and fills in.

    Returns immediately. Settings already in the cache are left alone.
    """
    global _cleanup_batch_running
    from fpstune.settings.cleanup_cache import cleanup_size_cache
    from fpstune.settings.cleanup_targets import CLEANUP_TARGETS

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

    walked = tuple(t for t in pending if t in CLEANUP_TARGETS)
    scripted = tuple(t for t in pending if t not in CLEANUP_TARGETS)

    with _cleanup_batch_lock:
        if _cleanup_batch_running:
            return
        _cleanup_batch_running = True

    # Claim them before the thread starts, so a detect racing this one reads
    # "calculating" and does not start a second computation of the same folder.
    # Each claim expires just after this batch's own timeout, so an id cannot
    # outlive the run that claimed it however that run ends. The deadline is the
    # PowerShell half's, because that is the half that can take minutes.
    from fpstune.settings.executors.ps_batch import cleanup_batch_timeout

    deadline = cleanup_batch_timeout(scripted) + 30
    for ids in pending.values():
        for setting_id in ids:
            cleanup_size_cache.mark_calculating(setting_id, deadline)

    def _run() -> None:
        global _cleanup_batch_running
        from fpstune.settings.cleanup_measure import as_reading, store_measurement
        from fpstune.settings.cleanup_targets import size_types
        from fpstune.settings.executors.ps_batch import _fetch_cleanup_sizes

        settled: set[str] = set()
        try:
            for cleanup_type, measured in size_types(walked).items():
                for setting_id in pending[cleanup_type]:
                    store_measurement(setting_id, as_reading(measured))
                    settled.add(setting_id)
        except Exception as exc:  # pragma: no cover - environment dependent
            _logger.debug("cleanup size walk failed: %s", exc)

        try:
            sizes = _fetch_cleanup_sizes(scripted) if scripted else {}
        except Exception as exc:  # pragma: no cover - environment dependent
            _logger.debug("cleanup size batch failed: %s", exc)
            sizes = {}
        finally:
            with _cleanup_batch_lock:
                _cleanup_batch_running = False

        for cleanup_type, setting_ids in pending.items():
            reading = sizes.get(cleanup_type, "")
            for setting_id in setting_ids:
                # Every id claimed above must end up with an outcome. The claim's
                # deadline is only the backstop for a worker that dies before
                # reaching here; one left behind would spin until it expires.
                if setting_id in settled:
                    continue
                if not (reading and store_cleanup_reading(setting_id, reading)):
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


# Actions whose command routinely runs for minutes, and what they get instead of
# the 30 s default. A per-setting `apply_timeout` overrides both.
_SLOW_APPLY = {
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
_MEDIUM_APPLY = {
    "service_toggle",
    # Two recursive sizing passes over %TEMP% measured 2.8 s each on a folder
    # holding 12719 files, before any deleting — inside 30 s, but not by enough
    # to leave a bigger Temp or a slower disk any room.
    "temp_cleanup",
    "hyper_v_only_toggle",
    "vm_platform_toggle",
    "windows_update_cache_cleanup",
    "delivery_optimization_cleanup",
}


def _cleanup_status_reading(setting: SettingExecutor) -> tuple[Any, str | None]:
    """How much this cleanup has to clean, as the row will show it.

    Served from the background cache when the scan has already filled it. On a
    miss there are two answers rather than one: a folder target is walked right
    here, because that costs a directory read and not a process — the row arrives
    with its size instead of a spinner and a three-second poll — while a reading
    that needs the component store, a docker daemon or the event log service
    still starts PowerShell in the background and reports "calculating".
    """
    from fpstune.settings.cleanup_cache import cleanup_size_cache
    from fpstune.settings.cleanup_measure import cleanup_type_of, measure_cleanup_size
    from fpstune.settings.cleanup_targets import CLEANUP_TARGETS

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

    cleanup_type = cleanup_type_of(setting)
    if cleanup_type in CLEANUP_TARGETS:
        measured = measure_cleanup_size(setting, remember=True)
        if measured is None:
            return "ready|unavailable", None
        if measured.status == "not_installed":
            return "not_available", None
        return measured.reading, None

    # Cache miss: start background calculation and return immediately.
    scan_timeout, scan_deadline = _cleanup_scan_timeout(cleanup_type)
    cleanup_size_cache.mark_calculating(setting.id, scan_deadline)
    try:
        bg_cmd = substitute_placeholders(ACTION_COMMANDS["cleanup_status"], **setting.detect_args)
    except ValueError as exc:
        cleanup_size_cache.set_unavailable(setting.id)
        return None, f"PowerShell command rejected: {exc}"
    _start_bg_cleanup_detection(setting.id, bg_cmd, scan_timeout)
    return "ready|calculating", None


def _add_cleanup_paths(setting: SettingExecutor, args: dict[str, Any]) -> str | None:
    """Put this cleanup's own path list into `args`, or say why it could not.

    The list comes from `cleanup_targets`, which is what sized the target
    immediately before this command runs and will size it again immediately
    after. A script asking for `%paths%` with nothing to give it would run over
    the literal placeholder and report success having deleted nothing, so a
    missing target is a refusal rather than a silent no-op.
    """
    from fpstune.settings.cleanup_measure import cleanup_type_of
    from fpstune.settings.cleanup_targets import (
        CLEANUP_TARGETS,
        EXTERNAL,
        UnsafePath,
        delete_arguments,
    )

    cleanup_type = cleanup_type_of(setting)
    target = CLEANUP_TARGETS.get(cleanup_type or "")
    if target is None or target.delete_mode == EXTERNAL:
        return f"cleanup paths unavailable: no path target for {setting.id}"
    try:
        args.update(delete_arguments(target))
    except UnsafePath as exc:
        return f"cleanup paths rejected: {exc}"
    return None


def _apply_command(
    setting: SettingExecutor, cmd_key: str, args: dict[str, Any]
) -> tuple[str | None, str | None]:
    """The exact command this apply will run, or None and why it was refused.

    Two things can refuse it, and both are rejections rather than failures — the
    route reports them instead of raising. A value the escaping layer cannot
    place safely is one; a cleanup whose path list could not be produced is the
    other, because a delete script running over the literal `%paths%` would
    report success having removed nothing.

    The path list itself is the one `cleanup_targets` resolved, which is also
    what sizes the target either side of this command. Every mismatch in the
    audit was a second path list drifting from the first: a folder counted twice
    and deleted once, a cache deleted and never counted, a subdirectory counted
    and never deletable.
    """
    template = ACTION_COMMANDS.get(cmd_key, setting.apply_command)
    if "%paths%" in template:
        paths_error = _add_cleanup_paths(setting, args)
        if paths_error is not None:
            return None, paths_error
    try:
        return substitute_placeholders(template, **args), None
    except ValueError as exc:
        return None, f"PowerShell command rejected: {exc}"


def apply_timeout_seconds(setting: SettingExecutor, cmd_key: str) -> int:
    """How long this apply may take: per-setting override, then the known-slow
    table, then 30 s.

    One resolution for the quiet run and the streamed one — a second copy is how
    the two would come to disagree about when a repair has stopped responding.
    """
    if setting.apply_timeout is not None:
        return setting.apply_timeout
    if cmd_key in _SLOW_APPLY:
        return 300
    if cmd_key in _MEDIUM_APPLY:
        return 60
    return 30


def _start_bg_cleanup_detection(setting_id: str, cmd: str, timeout: int) -> None:
    """Run cleanup_status PS in a daemon thread; store result in cleanup_size_cache.

    The per-setting fallback, for a cleanup the batch did not cover.
    """
    from fpstune.settings.cleanup_cache import cleanup_size_cache

    def _compute() -> None:
        with _cleanup_scan_semaphore:
            _compute_inner()

    def _compute_inner() -> None:
        try:
            ok, out = run_powershell(cmd, timeout=timeout)
            if ok and out and store_cleanup_reading(setting_id, out):
                return
        except Exception:
            pass
        # No parseable "ready|<size>" line and no explicit "unavailable" marker.
        # Don't write a fake 0 (reads in the UI as "nothing to clean" and flashes
        # "0 MB"); surface unavailable so the short-TTL cache recomputes instead.
        cleanup_size_cache.set_unavailable(setting_id)

    try:
        threading.Thread(target=_compute, daemon=True, name=f"cleanup-{setting_id}").start()
    except Exception:
        # The caller has already claimed this id as "calculating"; a thread that
        # never starts would leave that claim with nobody to settle it.
        cleanup_size_cache.set_unavailable(setting_id)
        raise


def _scriptless_reading(setting: SettingExecutor, cmd_key: str) -> Any | None:
    """A detect answer that needs no PowerShell, or None when a script must run.

    Two answers arrive here. ``PYTHON_DETECTORS`` holds readings taken in Python
    through a native API (wlanapi for the Wi-Fi link) — the detect counterpart of
    ``PYTHON_ACTIONS``. ``constant_status_reading`` holds action commands with no
    state to read: their detect script is the literal ``Write-Output $true``, so
    running it started a PowerShell process to learn a constant (measured: three of
    the twenty-five a cold scan spawned). Both answers still go through
    ``value_map``, so it is the same value by the same route, without the process.

    The constant is resolved from ``setting.detect_args`` and not from the command
    name alone, because one command name can cover both kinds: ``maintenance_status``
    answers a literal for SFC and the DISM health check, and reads the machine for
    the SSD retrim check. Keying on the name would have answered ``True`` for the
    reading that has something to say.
    """
    from fpstune.settings.executors.python_actions import PYTHON_DETECTORS
    from fpstune.utils.debug import debug_log

    detector = PYTHON_DETECTORS.get(cmd_key)
    if detector is not None:
        raw = detector(setting.detect_args)
        debug_log("powershell", f"DETECT PYTHON {setting.id}: {cmd_key} → {raw!r}")
        if isinstance(raw, Reading):
            return Reading(map_raw_to_display(setting.value_map, raw.value), raw.finding)
        return map_raw_to_display(setting.value_map, raw)

    constant = constant_status_reading(cmd_key, setting.detect_args)
    if constant is not None:
        debug_log("powershell", f"DETECT CONSTANT {setting.id}: {cmd_key} → {constant!r}")
        return map_raw_to_display(setting.value_map, constant)
    return None


def _split_detect_output(
    setting_id: str, output: str | None
) -> tuple[list[str], dict[str, Any] | None]:
    """Separate a detect script's value lines from the two kinds that ride along.

    "FPSTUNE_WARN: msg" is a diagnostic for the log — a missing tool, an
    unreadable counter — that must not fail the detection. "FPSTUNE_FINDING:
    {json}" is the numbers behind an advisory's word, handed to the UI as the
    Reading's finding. Neither is ever the value; the value is the last line left.
    """
    value_lines: list[str] = []
    finding: dict[str, Any] | None = None
    for line in (output or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("FPSTUNE_WARN:"):
            _logger.info("[%s] %s", setting_id, stripped[len("FPSTUNE_WARN:") :].strip())
        elif stripped.startswith("FPSTUNE_FINDING:"):
            finding = _parse_finding(setting_id, stripped[len("FPSTUNE_FINDING:") :])
        elif stripped:
            value_lines.append(stripped)
    return value_lines, finding


def _parse_finding(setting_id: str, text: str) -> dict[str, Any] | None:
    """The JSON object a detect script wrote after ``FPSTUNE_FINDING:``, or None.

    Only an object with a string ``kind`` counts: the UI picks its sentence by
    that key, and a finding it has no sentence for is shown as nothing, not as
    raw JSON.
    """
    try:
        parsed = json.loads(text.strip())
    except ValueError:
        _logger.warning("[%s] unreadable FPSTUNE_FINDING line: %r", setting_id, text[:200])
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("kind"), str):
        _logger.warning("[%s] FPSTUNE_FINDING without a kind: %r", setting_id, text[:200])
        return None
    return parsed


def _batch_config_reading(batch_config: str, setting: SettingExecutor) -> Any:
    """Read one setting out of the per-scan game-config snapshot.

    Game config files are read once per scan in Python: 47 MW3 settings share
    one options file and 24 CS2 settings share one autoexec.cfg, and each used
    to spawn its own PowerShell process.

    Which file a setting reads is named by the setting, never guessed. A game
    with two config files gets a name per file — ``mw3`` is MW3's graphics
    ``options.4.cod23.cst`` and ``mw3_profile`` is its per-account gamerprofile
    — because a key name can appear in both and the two have different line
    shapes.
    """
    from fpstune.settings.executors.game_config_cache import (
        get_cs2_marker,
        get_hots_variable,
        get_mw3_option,
        get_mw3_options_any_true,
        get_mw3_profile_option,
        get_mw3_profile_options_agreed,
        get_mw4_option,
        get_mw4_options_agreed,
    )

    def declared_keys() -> tuple[list[str], bool]:
        """The keys this setting names, and whether it named more than one.

        A list is a named-compound: several keys that are one setting between
        them. Read strictly — a file-backed setting with no ``batch_key`` is a
        registry mistake to raise on, never a key literally named ``None`` to
        look up and report absent.
        """
        declared = setting.detect_args["batch_key"]
        if isinstance(declared, (list, tuple)):
            return [str(k) for k in declared], True
        return [str(declared)], False

    if batch_config == "mw3":
        keys, compound = declared_keys()
        # MW3's compound is the other shape: keys that each switch the same
        # behaviour on, so the concept is off only when all of them are.
        return get_mw3_options_any_true(keys) if compound else get_mw3_option(keys[0])
    if batch_config == "mw3_profile":
        keys, compound = declared_keys()
        return get_mw3_profile_options_agreed(keys) if compound else get_mw3_profile_option(keys[0])
    if batch_config == "mw4":
        # MW4 keeps two files and a key can appear in both, so the setting names
        # which one it reads. Defaulting to the global file matches where all
        # but a handful of keys live.
        keys, compound = declared_keys()
        source = str(setting.detect_args.get("batch_source", "global"))
        if compound:
            return get_mw4_options_agreed(keys, source)
        return get_mw4_option(keys[0], source)
    if batch_config == "hots":
        return get_hots_variable(declared_keys()[0][0])
    if batch_config == "nvidia_app":
        # Not a game config, but the same shape: one file read in Python instead
        # of a PowerShell process per setting that wants it.
        from fpstune.settings.executors.nvidia_app import battery_boost_exposure

        return battery_boost_exposure()
    if batch_config == "cs2":
        return get_cs2_marker(
            str(setting.detect_args["batch_marker"]),
            str(setting.detect_args["batch_present"]),
            str(setting.detect_args["batch_absent"]),
        )
    # Named explicitly rather than falling through to CS2. The branch used to be
    # `else: cs2`, so a new game whose args did not match would have been read as
    # a CS2 marker lookup and reported against the wrong file.
    raise KeyError(f"unknown batch_config {batch_config!r} on {setting.id}")


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
            raw = _batch_config_reading(str(batch_config), setting)
            debug_log("powershell", f"DETECT BATCH_CONFIG {setting.id}: → {raw!r}")
            return map_raw_to_display(setting.value_map, raw), None

        # Check for special action commands
        cmd_key = setting.detect_command.strip()

        scriptless = _scriptless_reading(setting, cmd_key)
        if scriptless is not None:
            return scriptless, None

        if cmd_key == "cleanup_status":
            return _cleanup_status_reading(setting)

        # A value the escaping layer cannot place safely is a refused command,
        # not a failed detector: reported in this executor's own failure shape so
        # the route answers with a rejection rather than a server error.
        template = detect_script(cmd_key, setting.detect_args) or setting.detect_command
        try:
            cmd = substitute_placeholders(template, **setting.detect_args)
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

        value_lines, finding = _split_detect_output(setting.id, output)
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
        value: Any = raw_value
        if setting.value_map:
            value = map_raw_to_display(setting.value_map, raw_value)
            debug_log("powershell", f"DETECT MAP {setting.id}: {repr(raw_value)} -> {repr(value)}")

        if finding is not None:
            return Reading(value, finding), None
        return value, None

    streams_output = True

    def apply(
        self,
        setting: SettingExecutor,
        value: Any,
        on_line: LineCallback | None = None,
    ) -> tuple[bool, str | None]:
        """Apply a value using PowerShell.

        `on_line` turns the same run into a streamed one: every line the command
        prints is handed over as it is printed, so a repair that takes half an
        hour can say what it is doing. It changes nothing about *what* runs —
        the command, the timeout and the refusals below are resolved once, here,
        for both callers, because a second copy of the timeout table is how the
        streamed run would come to disagree with the quiet one.
        """
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

        # Fast path: MW4's two files and MW3's gamerprofile are rewritten one
        # line at a time, which Python does directly. Routing them through
        # PowerShell would cost a process per setting and duplicate the
        # suffix-preserving rewrite that `game_config_writer` already owns — and
        # a second implementation is a second thing to get wrong about `@scope`.
        line_config = setting.apply_args.get("batch_config")
        if line_config in ("mw4", "mw3_profile"):
            from fpstune.settings.applicability import NOT_INSTALLED
            from fpstune.settings.executors.game_config_writer import ConfigValueRejected

            batch_key = setting.apply_args["batch_key"]
            # A list is a named-compound: several keys that are one setting, so
            # every one of them gets the value or none of them does.
            compound = isinstance(batch_key, (list, tuple))
            keys = [str(k) for k in batch_key] if compound else [str(batch_key)]
            try:
                if line_config == "mw4":
                    from fpstune.settings.executors.mw4_config import (
                        set_mw4_option,
                        set_mw4_options,
                    )

                    # MW4 keeps two files and a key can appear in both, so the
                    # setting names which one it writes. Defaulting to the global
                    # file matches where all but a handful of keys live.
                    source = str(setting.apply_args.get("batch_source", "global"))
                    written = (
                        set_mw4_options(keys, str(raw_value), source)
                        if compound
                        else set_mw4_option(keys[0], str(raw_value), source)
                    )
                    absent = "Modern Warfare IV config file not found"
                else:
                    from fpstune.settings.executors.mw3_profile import (
                        set_mw3_profile_option,
                        set_mw3_profile_options,
                    )

                    written = (
                        set_mw3_profile_options(keys, str(raw_value))
                        if compound
                        else set_mw3_profile_option(keys[0], str(raw_value))
                    )
                    absent = "Modern Warfare III profile config file not found"
            except ConfigValueRejected as exc:
                # The file's own range said no. Reported rather than written,
                # because MW4 answers a value it dislikes by resetting the key.
                debug_log("powershell", f"APPLY REJECTED {setting.id}: {exc}")
                return False, str(exc)
            if written == NOT_INSTALLED:
                return False, absent
            debug_log("powershell", f"APPLY {line_config} {setting.id}: wrote {written!r}")
            return True, None

        # Check for special action commands
        cmd_key = setting.apply_command.strip()
        args = {**setting.apply_args, "value": raw_value}

        # Some actions are Python functions, not scripts: the standby-list purge
        # needs ntdll, and reaching it from PowerShell means compiling a C# class
        # with Add-Type, the pattern Windows Defender flags. No process starts.
        from fpstune.settings.executors.python_actions import PYTHON_ACTIONS

        if cmd_key in PYTHON_ACTIONS:
            ok, message = PYTHON_ACTIONS[cmd_key](args)
            debug_log("powershell", f"APPLY PYTHON {setting.id}: {cmd_key} ok={ok}")
            return ok, message
        cmd, rejection = _apply_command(setting, cmd_key, args)
        if cmd is None:
            debug_log("powershell", f"APPLY REJECTED {setting.id}: {rejection}")
            return False, rejection

        debug_log("powershell", f"APPLY CMD {setting.id}: {cmd[:300]}...")

        timeout = apply_timeout_seconds(setting, cmd_key)

        if on_line is not None:
            # The command about to run, before it runs: this is what the UI shows
            # above the progress bar, and showing the real one is the point — a
            # paraphrase would be a claim about what fpstune did rather than a
            # record of it.
            on_line(cmd, False)

        success, output = self._run(cmd, timeout=timeout, on_line=on_line)

        debug_log(
            "powershell",
            f"APPLY RESULT {setting.id}: success={success}, output={repr(output[:300]) if output else 'None'}",
        )

        if not success:
            return False, f"PowerShell failed: {output}"

        return True, None

    def _run(
        self, command: str, timeout: int = 30, on_line: LineCallback | None = None
    ) -> tuple[bool, str]:
        """Run PowerShell command and return (success, output).

        Delegates to the shared utility function for consistent behavior.
        """
        if on_line is not None:
            return run_powershell_stream(command, on_line, timeout=timeout)
        return run_powershell(command, timeout=timeout)
