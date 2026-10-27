"""Parallel detection engine for settings."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import TYPE_CHECKING, Any

from fpstune.settings.applicability import (
    ApplicabilityChecker,
    HardwareContext,
    absent_reason,
    is_absent_reading,
    values_equal,
)
from fpstune.settings.base import DetectionResult, Reading
from fpstune.settings.executors import CommandExecutor
from fpstune.settings.executors.game_config_cache import prefetch_game_configs
from fpstune.settings.executors.ps_batch import (
    command_is_batchable,
    init_scan_cache,
    prefetch_adapter_properties,
    prefetch_powershell_detects,
    prefetch_services,
    reset_scan_cache,
)
from fpstune.utils.operation_log import classify_error, operation_log
from fpstune.utils.powershell import substitute_placeholders

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor


logger = logging.getLogger(__name__)

__all__ = ["DetectionEngine", "DetectionResult"]


def _prefetch_powershell_group(settings: list[SettingExecutor]) -> None:
    """Run the plain PowerShell detects for this scan in a few shared sessions.

    Starting a PowerShell process costs far more than any of these commands,
    so the remaining per-setting detects are grouped. Settings already served
    by a dedicated batch, action commands, and anything containing ``exit`` are
    left on the per-setting path.
    """
    from fpstune.settings.base import DetectType
    from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

    specs: list[tuple[str, str]] = []
    for setting in settings:
        if setting.detect_type != DetectType.POWERSHELL:
            continue
        if any(key.startswith("batch_") for key in setting.detect_args):
            continue
        command = setting.detect_command.strip()
        if command in ACTION_COMMANDS or not command_is_batchable(command):
            continue
        try:
            resolved = substitute_placeholders(command, **setting.detect_args)
        except ValueError as exc:
            # One setting the escaping layer refuses must not cost the whole
            # scan its batch. Left off the group, it falls through to the
            # per-setting path, which refuses the same command and reports it
            # against the setting that owns it.
            logger.debug("Batch prefetch skipped for %s: %s", setting.id, exc)
            continue
        specs.append((setting.id, resolved))

    if specs:
        prefetch_powershell_detects(specs)


def _log_scan(results: dict[str, DetectionResult], total: int, started: float) -> None:
    """One summary line for a scan, plus one line per error.

    A scan of 475 rows must not write 475 lines. The summary answers "how many
    need work, how many could not be read"; the per-error lines are the ones a
    user can act on, and there are usually a handful.
    """
    errors = [result for result in results.values() if result.error]
    operation_log.record_detect(
        total=total,
        errors=len(errors),
        not_applicable=sum(1 for result in results.values() if not result.is_applicable),
        optimized=sum(1 for result in results.values() if result.is_optimized),
        not_optimized=sum(
            1
            for result in results.values()
            if result.is_applicable and not result.is_optimized and not result.error
        ),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    for result in errors:
        operation_log.write(
            "detect",
            "failed",
            result.setting_id,
            error_kind=classify_error(result.error),
            reason=result.error,
        )


def _partition_applicable(
    settings: list[SettingExecutor],
    checker: ApplicabilityChecker | None,
) -> tuple[list[SettingExecutor], dict[str, DetectionResult]]:
    """Split settings into the ones detection should read and the absent ones.

    An absent setting is a result, not an error: it carries no value and the
    reason the UI shows under "not applicable". Keeping the split here keeps
    `detect_all` a scheduler rather than a second place that knows the rule.
    """
    applicable: list[SettingExecutor] = []
    results: dict[str, DetectionResult] = {}
    for setting in settings:
        if checker:
            is_applicable, reason = checker.is_applicable(setting)
            if not is_applicable:
                results[setting.id] = DetectionResult(
                    setting_id=setting.id,
                    value=None,
                    error=None,
                    time_ms=0,
                    is_optimized=False,
                    is_applicable=False,
                    applicable_reason=reason,
                )
                continue
        applicable.append(setting)
    return applicable, results


def _run_prefetchers(applicable_settings: list[SettingExecutor]) -> None:
    """Run the batch prefetches this scan needs, in parallel, before the pool.

    Return values are unused: every prefetcher writes into the scan cache. The
    cleanups and the plain PowerShell detects are always included; the batch
    queries are added only when a setting declares them.
    """
    prefetchers: list[Callable[[], object]] = []
    if any("batch_service" in s.detect_args for s in applicable_settings):
        prefetchers.append(prefetch_services)
    if any("batch_adapter_keyword" in s.detect_args for s in applicable_settings):
        prefetchers.append(prefetch_adapter_properties)
    if any("batch_config" in s.detect_args for s in applicable_settings):
        prefetchers.append(prefetch_game_configs)
    if any("batch_tcp" in s.detect_args for s in applicable_settings):
        from fpstune.settings.executors.netsh import prefetch_tcp_settings

        prefetchers.append(prefetch_tcp_settings)
    if any("batch_pnp_power" in s.detect_args for s in applicable_settings):
        from fpstune.settings.executors.ps_batch import prefetch_adapter_power

        prefetchers.append(prefetch_adapter_power)

    # Cleanup sizes: one PowerShell for every pending target instead of one per
    # setting. This returns immediately — the sizing itself runs in a background
    # thread, because folder walks are genuinely slow and putting them on the
    # scan's critical path would trade processes for wall-clock.
    from fpstune.settings.executors.powershell import start_cleanup_size_batch

    prefetchers.append(lambda: start_cleanup_size_batch(applicable_settings))
    prefetchers.append(lambda: _prefetch_powershell_group(applicable_settings))

    if len(prefetchers) == 1:
        prefetchers[0]()
        return
    with ThreadPoolExecutor(max_workers=len(prefetchers)) as pre_pool:
        # copy_context() must be evaluated HERE, in the submitting thread, so
        # each task copies the context holding the scan cache. Calling it inside
        # the worker callable copies the worker's own (empty) context instead,
        # and every prefetch then computed its snapshot outside the scan and
        # threw it away — the batches were silently dead in production while
        # every test passed.
        pre_futures = [pre_pool.submit(copy_context().run, fn) for fn in prefetchers]
        for pre_future in pre_futures:
            pre_future.result()


class DetectionEngine:
    """Parallel setting detection engine.

    Detects multiple settings concurrently using a thread pool.
    Each setting has its own timeout, isolating failures.
    """

    def __init__(
        self,
        max_workers: int = 16,
        hardware_context: HardwareContext | None = None,
    ):
        """Initialize detection engine.

        Args:
            max_workers: Maximum concurrent detection threads.
            hardware_context: Hardware context for applicability checks.
        """
        self.max_workers = max_workers
        self.context = hardware_context
        self.checker = ApplicabilityChecker(hardware_context) if hardware_context else None

    def detect_all(
        self,
        settings: list[SettingExecutor],
        hardware_context: HardwareContext | None = None,
    ) -> dict[str, DetectionResult]:
        """Detect all settings in parallel.

        Args:
            settings: List of settings to detect.
            hardware_context: Optional hardware context (overrides instance context).

        Returns:
            Dict mapping setting_id to DetectionResult.
        """
        if not settings:
            return {}

        started = time.perf_counter()

        # A bulk run restarts adapters; a read that starts in the settle window
        # sees an empty DNS/offload list and reports a transient as "not
        # optimized". Wait for the restarts, then a short settle, before the
        # scan reads any adapter.
        from fpstune.settings.executors.adapter_restart import wait_for_restarts

        wait_for_restarts()

        # Use provided context or fall back to instance context
        context = hardware_context or self.context
        checker = ApplicabilityChecker(context) if context else self.checker

        applicable_settings, results = _partition_applicable(settings, checker)
        if not applicable_settings:
            _log_scan(results, len(settings), started)
            return results

        # Initialize the per-scan cache. It is created fresh for every scan, so
        # a run can never read a previous run's snapshot, and it is carried into
        # worker threads by copy_context() at submit time (see below).
        _, token = init_scan_cache()
        _run_prefetchers(applicable_settings)

        try:
            # Use thread pool for parallel detection of applicable settings
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all detection tasks.
                # ThreadPoolExecutor does NOT propagate contextvars to worker
                # threads (that is asyncio.Task behaviour, not thread-pool
                # behaviour), so workers used to see an empty scan cache and
                # each re-ran the batch PowerShell query it was meant to avoid.
                # Copying the context per submit carries the cache dict through;
                # a fresh copy per task is required because a single Context
                # cannot be entered concurrently.
                futures = {
                    executor.submit(copy_context().run, self._detect_one, setting): setting
                    for setting in applicable_settings
                }

                # Collect every result. No deadline over the scan: the processes
                # a detection starts run under the stall rule
                # (utils.process_watch), so a reading that is working is waited
                # for and a stuck one ends itself with a reason. The deadlines
                # this replaced reported settings as timed out that were simply
                # queued behind slow ones.
                for future in as_completed(futures):
                    setting = futures[future]
                    try:
                        results[setting.id] = future.result()
                    except Exception as e:  # noqa: BLE001 - one setting's failure is its own DetectionResult; the rest must still be detected
                        results[setting.id] = DetectionResult(
                            setting_id=setting.id,
                            value=None,
                            error=str(e),
                            time_ms=0,
                            is_optimized=False,
                            is_applicable=True,
                        )
        finally:
            reset_scan_cache(token)

        _log_scan(results, len(settings), started)
        return results

    def detect_one(self, setting: SettingExecutor) -> DetectionResult:
        """Detect a single setting.

        Args:
            setting: The setting to detect.

        Returns:
            DetectionResult with value or error.
        """
        return self._detect_one(setting)

    def _detect_one(self, setting: SettingExecutor) -> DetectionResult:
        """Internal detection for a single setting."""
        from fpstune.utils.debug import debug_log

        start = time.perf_counter()

        try:
            value, error = CommandExecutor.detect(setting)
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # A detector with numbers behind its word hands both back in a
            # Reading; split them here, once, so nothing below ever compares a
            # Reading to a recommended value.
            finding: dict[str, Any] | None = None
            if isinstance(value, Reading):
                finding = value.finding
                value = value.value

            # Log raw detection result
            debug_log(
                "detect",
                f"DETECT {setting.id}: raw_value={repr(value)}, error={error}, time={elapsed_ms}ms",
            )

            # Check if this is a service setting and the service doesn't exist
            # Service settings have IDs like "services:SysMain" and return None when not found
            is_service_setting = setting.is_service
            is_applicable = True
            applicable_reason = ""

            if is_service_setting and value is None and error is None:
                # Service doesn't exist on this system
                is_applicable = False
                applicable_reason = "Service not installed on this system"
            elif (
                not is_service_setting
                and value is None
                and error is None
                and setting.applicable_conditions
            ):
                # None value with no error from registry executor (key not found)
                # If the setting has applicability conditions, check them
                # to determine if the setting is not applicable vs using default
                if self.checker:
                    cond_applicable, cond_reason = self.checker.is_applicable(setting)
                    if not cond_applicable:
                        is_applicable = False
                        applicable_reason = cond_reason

            # An absent reading means the feature/service/game is not on this
            # system. `ABSENT_READINGS` is the single spelling set (see
            # applicability.py); this used to be a hand-written tuple here that
            # omitted "not_installed", so every game setting on a machine without
            # the game surfaced the sentinel as its value. Marking it not
            # applicable:
            # 1. Hides it from the UI (filtered in getCategoriesWithSettings)
            # 2. Skips it in bulk apply/reset/optimize operations
            # 3. Excludes it from scope selections
            if is_absent_reading(value):
                is_applicable = False
                applicable_reason = absent_reason(setting, value)
                value = None  # Clear the value since it's not applicable

            # Compute is_optimized: current value matches recommended.
            # Exclude null (detection failed) and explicit "unknown" string
            # (value_map returned unknown) — these are "not detected" states,
            # not "not optimized" states.
            is_optimized = False
            if (
                is_applicable
                and error is None
                and value is not None
                and str(value).lower() != "unknown"
                and setting.recommended_value is not None
            ):
                is_optimized = values_equal(value, setting.recommended_value)

            return DetectionResult(
                setting_id=setting.id,
                value=value,
                error=error,
                time_ms=elapsed_ms,
                is_optimized=is_optimized,
                is_applicable=is_applicable,
                applicable_reason=applicable_reason,
                finding=finding,
            )
        except Exception as e:  # noqa: BLE001 - one setting's failure is its own DetectionResult; the rest must still be detected
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return DetectionResult(
                setting_id=setting.id,
                value=None,
                error=str(e),
                time_ms=elapsed_ms,
                is_optimized=False,
                is_applicable=True,
            )
