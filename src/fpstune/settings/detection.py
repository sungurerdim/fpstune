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


class DetectionEngine:
    """Parallel setting detection engine.

    Detects multiple settings concurrently using a thread pool.
    Each setting has its own timeout, isolating failures.
    """

    def __init__(
        self,
        max_workers: int = 16,
        timeout_per_setting: float = 5.0,
        hardware_context: HardwareContext | None = None,
    ):
        """Initialize detection engine.

        Args:
            max_workers: Maximum concurrent detection threads.
            timeout_per_setting: Timeout in seconds per setting detection.
            hardware_context: Hardware context for applicability checks.
        """
        self.max_workers = max_workers
        self.timeout = timeout_per_setting
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

        # Use provided context or fall back to instance context
        context = hardware_context or self.context
        checker = ApplicabilityChecker(context) if context else self.checker

        results: dict[str, DetectionResult] = {}

        # Separate applicable and non-applicable settings
        applicable_settings: list[SettingExecutor] = []
        for setting in settings:
            if checker:
                is_applicable, reason = checker.is_applicable(setting)
                if not is_applicable:
                    # Skip detection for non-applicable settings
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
            applicable_settings.append(setting)

        if not applicable_settings:
            return results

        # Initialize the per-scan cache. It is created fresh for every scan, so
        # a run can never read a previous run's snapshot, and it is carried into
        # worker threads by copy_context() at submit time (see below).
        _, token = init_scan_cache()

        # Pre-fetch the batch queries before spawning the detection pool, so
        # workers read from cache. These sit on the scan's critical path, and
        # they are independent of each other, so they overlap. Each is only
        # fetched when some setting actually needs it.
        # Return values differ per prefetcher and are unused here — each one
        # writes into the scan cache.
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

        # Cleanup sizes: one PowerShell for every pending target instead of one
        # per setting. This returns immediately — the sizing itself runs in a
        # background thread, because folder walks are genuinely slow and putting
        # them on the scan's critical path would trade processes for wall-clock.
        from fpstune.settings.executors.powershell import start_cleanup_size_batch

        prefetchers.append(lambda: start_cleanup_size_batch(applicable_settings))
        prefetchers.append(lambda: _prefetch_powershell_group(applicable_settings))

        if len(prefetchers) == 1:
            prefetchers[0]()
        else:
            with ThreadPoolExecutor(max_workers=len(prefetchers)) as pre_pool:
                # copy_context() must be evaluated HERE, in the submitting
                # thread, so each task copies the context holding the scan cache.
                # Calling it inside the worker callable copies the worker's own
                # (empty) context instead, and every prefetch then computed its
                # snapshot outside the scan and threw it away — the batches were
                # silently dead in production while every test passed.
                pre_futures = [pre_pool.submit(copy_context().run, fn) for fn in prefetchers]
                for pre_future in pre_futures:
                    pre_future.result()

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

                # Collect results as they complete
                # Action settings (cleanup/maintenance) get longer timeout for size scanning
                total_timeout = max(self.timeout * len(applicable_settings), 120)
                try:
                    for future in as_completed(futures, timeout=total_timeout):
                        setting = futures[future]
                        per_timeout = 60.0 if setting.is_action else self.timeout
                        try:
                            result = future.result(timeout=per_timeout)
                            results[setting.id] = result
                        except TimeoutError:
                            results[setting.id] = DetectionResult(
                                setting_id=setting.id,
                                value=None,
                                error="Detection timed out",
                                time_ms=int(self.timeout * 1000),
                                is_optimized=False,
                                is_applicable=True,
                            )
                        except Exception as e:
                            results[setting.id] = DetectionResult(
                                setting_id=setting.id,
                                value=None,
                                error=str(e),
                                time_ms=0,
                                is_optimized=False,
                                is_applicable=True,
                            )
                except TimeoutError:
                    # The whole-run deadline, not a per-setting one. Letting it
                    # escape left every unfinished setting with no result at all
                    # — a caller reading `results[id]` got a KeyError instead of
                    # a timed-out reading — and then the `with` block's
                    # shutdown(wait=True) blocked on the very work that had just
                    # been declared too slow.
                    for future, setting in futures.items():
                        if setting.id in results:
                            continue
                        future.cancel()
                        results[setting.id] = DetectionResult(
                            setting_id=setting.id,
                            value=None,
                            error=f"Detection timed out ({total_timeout:.0f}s)",
                            time_ms=int(total_timeout * 1000),
                            is_optimized=False,
                            is_applicable=True,
                        )
                    # Drops the queued tasks so the exit below only waits for
                    # the ones already running.
                    executor.shutdown(wait=False, cancel_futures=True)
        finally:
            reset_scan_cache(token)

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
                applicable_reason = absent_reason(setting)
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
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return DetectionResult(
                setting_id=setting.id,
                value=None,
                error=str(e),
                time_ms=elapsed_ms,
                is_optimized=False,
                is_applicable=True,
            )

    def detect_by_category(
        self,
        settings: list[SettingExecutor],
        category: str,
        hardware_context: HardwareContext | None = None,
    ) -> dict[str, DetectionResult]:
        """Detect settings filtered by category.

        Args:
            settings: All available settings.
            category: Category to filter by.
            hardware_context: Optional hardware context for applicability.

        Returns:
            Detection results for matching settings.
        """
        filtered = [s for s in settings if s.category.value == category]
        return self.detect_all(filtered, hardware_context=hardware_context)
