"""Setting-based API routes.

Uses the new SettingExecutor architecture with parallel detection.
Each setting is self-contained with its own detection and apply logic.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from fastapi import APIRouter, HTTPException

import fpstune.settings.registry_cache as registry_cache
from fpstune.api.schemas import (
    ApplyRequest,
    ApplyResponse,
    BulkApplyRequest,
    BulkApplyResponse,
    CategoryMetadataResponse,
    DetectionResultResponse,
    DetectRequest,
    DetectResponse,
    ModuleMetadataResponse,
    SettingDefinitionResponse,
    VerifyRequest,
    VerifyResponse,
)
from fpstune.safety import restore
from fpstune.safety.originals import get_original_values
from fpstune.settings import (
    CommandExecutor,
    DetectionEngine,
    SettingsRegistry,
)
from fpstune.settings.applicability import (
    ApplicabilityChecker,
    HardwareContext,
    is_absent_reading,
    values_equal,
)
from fpstune.settings.base import (
    CATEGORY_METADATA,
    MODULE_METADATA,
    DetectType,
    SettingExecutor,
    SettingValueType,
    get_all_categories_metadata,
    get_all_modules_metadata,
)
from fpstune.settings.hardware_context import build_hardware_context
from fpstune.settings.impact_categories import derive_impact_categories
from fpstune.utils.logger import log_activity, tweak_label

logger = logging.getLogger(__name__)


def _create_restore_point_async() -> None:
    """Fire-and-forget restore point before a write (safety.restore owns it).

    A one-line delegate rather than a from-import: the mechanics — the enabled
    probe, the checkpoint subprocess, the daemon thread — moved to
    `fpstune.safety.restore`, next to RestorePointManager. The name stays here
    because it is the seam the API tests patch.
    """
    restore.create_restore_point_async()


def _get_hardware_context() -> HardwareContext:
    """This machine, in the terms the applicability rules are written in.

    A thin alias over `settings.hardware_context.build_hardware_context`. The
    builder used to live here, which made a route module the only place anything
    could ask what the hardware was — the CLI would have had to reach through an
    HTTP layer to find out. It moved next to `HardwareContext` and the rules that
    consume it; the name stays because it is what the tests patch.
    """
    return build_hardware_context()


router = APIRouter()


def _get_registry() -> SettingsRegistry:
    """The process-wide registry (settings.registry_cache owns the singleton).

    A one-line delegate rather than a from-import: the cache, its lock and the
    warm-up moved to `fpstune.settings.registry_cache`, next to the registry
    they cache — a route module was the only place anything could ask for the
    registry, and the benchmark and debug routes were reaching into a sibling
    route's privates to get it. The name stays because it is the seam the API
    tests patch.
    """
    return registry_cache.get_registry()


async def _get_registry_async() -> SettingsRegistry:
    """The registry, fetched off the event loop.

    A request that lands while the startup warm-up is still discovering hardware
    blocks on ``_registry_lock`` for the whole discovery (~1.8 s measured). From
    an async route that wait must happen on a worker thread, not on the loop.
    """
    return await asyncio.to_thread(_get_registry)


async def _get_hardware_context_async() -> HardwareContext:
    """The hardware context, built off the event loop.

    Cached after the first build, so most calls are free — but the first one is
    not, and cold start is exactly when a request is most likely to arrive: it
    enumerates adapters and reads driver metadata through subprocesses. Cheap
    on the warm path is not the same as safe on the loop.
    """
    return await asyncio.to_thread(_get_hardware_context)


async def _context_and_applicability(
    setting: SettingExecutor,
) -> tuple[HardwareContext, bool, str | None]:
    """Build the context and answer "does this setting apply here", off the loop.

    One hop rather than two: the check is pure over the context it is handed, so
    splitting them would pay a second thread switch for nothing.
    """

    def _check() -> tuple[HardwareContext, bool, str | None]:
        context = _get_hardware_context()
        is_applicable, reason = ApplicabilityChecker(context).is_applicable(setting)
        return context, is_applicable, reason

    return await asyncio.to_thread(_check)


# =============================================================================
# Definition Endpoints (instant, no detection)
# =============================================================================


def _setting_to_response(s: SettingExecutor) -> SettingDefinitionResponse:
    """Convert SettingExecutor to response model."""
    from fpstune.settings.base import MaintenanceExecutor
    from fpstune.settings.groups import group_for

    # Check if this is a MaintenanceExecutor for additional fields
    is_maintenance = isinstance(s, MaintenanceExecutor)
    group = group_for(s.id)

    return SettingDefinitionResponse(
        id=s.id,
        category=s.category.value,
        display_name=s.display_name,
        description=s.description,
        value_type=s.value_type.value,
        choices=list(s.choices),
        default_value=s.default_value,
        recommended_value=s.recommended_value,
        requires_reboot=s.requires_reboot,
        is_action=s.is_action,
        current_impact=s.current_impact,
        recommended_impact=s.recommended_impact,
        scope=s.scope.value,
        short_name=s.short_name,
        icon=s.icon,
        color=s.color,
        category_order=s.category_order,
        min_value=s.min_value,
        max_value=s.max_value,
        applicable_conditions=s.applicable_conditions,
        evidence_level=s.evidence_level,
        sources=s.sources,
        effect=s.effect,
        impact_scores=s.impact_scores,
        impact_categories=derive_impact_categories(s.impact_scores),
        risk_level=s.risk_level,
        risk_warning=s.risk_warning,
        perceptible_cost=s.perceptible_cost,
        is_drift_guard=(
            not s.is_action
            and not s.is_readonly
            and s.recommended_value is not None
            and s.default_value is not None
            and values_equal(s.recommended_value, s.default_value)
        ),
        # MaintenanceExecutor fields (use getattr for type safety)
        duration_estimate=getattr(s, "duration_estimate", "") if is_maintenance else "",
        supports_streaming=getattr(s, "supports_streaming", False) if is_maintenance else False,
        progress_pattern=getattr(s, "progress_pattern", None) if is_maintenance else None,
        is_readonly=s.is_readonly,
        value_hints=s._derive_value_hints(),
        group_id=group.id if group else None,
        group_label=group.label if group else None,
        group_order=group.order if group else None,
    )


@router.get("/definitions", response_model=list[SettingDefinitionResponse])
async def get_definitions() -> list[SettingDefinitionResponse]:
    """Get all setting definitions (static, instant).

    Used by frontend for initial store population.
    No detection is performed - returns immediately.
    """
    registry = await _get_registry_async()
    return [_setting_to_response(s) for s in registry.get_all()]


@router.get("/cleanup-sizes")
async def get_cleanup_sizes() -> dict[str, Any]:
    """Return cached cleanup sizes for all background-detected cleanup settings.

    Each entry: {"bytes": int, "status": "ready" | "calculating"}.
    Frontend polls this endpoint (refetchInterval: 3s) while any item is calculating.
    """
    from fpstune.settings.cleanup_cache import cleanup_size_cache

    return {
        k: {"bytes": v["bytes"], "status": v["status"]}
        for k, v in cleanup_size_cache.all_entries().items()
    }


# =============================================================================
# Detection Endpoints (parallel)
# =============================================================================


@router.post("/detect", response_model=DetectResponse)
async def detect_settings(request: DetectRequest) -> DetectResponse:
    """Detect specified settings in parallel.

    Each setting is detected independently with its own timeout.
    Failed detections don't affect other settings.
    Applicability is checked using hardware context (GPU vendor, Windows version).
    """
    import time

    registry = await _get_registry_async()
    hardware_context = _get_hardware_context()
    engine = DetectionEngine(hardware_context=hardware_context, max_workers=16)

    start = time.perf_counter()

    # Determine which settings to detect
    settings: list[SettingExecutor]
    if request.setting_ids:
        settings = [s for sid in request.setting_ids if (s := registry.get(sid)) is not None]
    elif request.category:
        settings = registry.get_by_category(request.category)
    else:
        settings = registry.get_all()

    # Run parallel detection (offloaded to thread to avoid blocking event loop).
    # Hard cap at 120 s: individual settings already have 5 s timeouts, so this
    # only fires if the ThreadPoolExecutor itself blocks (e.g. zombie processes).
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(functools.partial(engine.detect_all, settings)),
            timeout=120.0,
        )
    except TimeoutError:
        logger.error("detect_settings: timed out after 120 s (%d settings)", len(settings))
        raise HTTPException(status_code=504, detail="Detection timed out after 120 s") from None

    total_time_ms = int((time.perf_counter() - start) * 1000)

    # Remember what the machine held the first time fpstune saw each setting, so
    # "undo fpstune's change" has something to write. This is the scan that
    # already ran, so it costs nothing; reading each value again just before its
    # write would add a subprocess per setting to a path an earlier phase
    # deliberately removed one from. Only settings that were actually read are
    # recorded, and only once — see safety/originals.py.
    _record_originals(results)

    # Convert to response
    response_results: dict[str, DetectionResultResponse] = {}
    success_count = error_count = 0
    settings_map = {s.id: s for s in settings}

    originals = get_original_values()
    for setting_id, result in results.items():
        setting_obj = settings_map.get(setting_id)
        response_results[setting_id] = DetectionResultResponse(
            setting_id=result.setting_id,
            value=result.value,
            error=result.error,
            time_ms=result.time_ms,
            success=result.success,
            is_optimized=result.is_optimized,
            is_applicable=result.is_applicable,
            applicable_reason=result.applicable_reason,
            recommended_value=setting_obj.recommended_value if setting_obj else None,
            original_value=originals.get(setting_id),
            finding=result.finding,
        )
        if result.success:
            success_count += 1
        else:
            error_count += 1

    return DetectResponse(
        results=response_results,
        total_time_ms=total_time_ms,
        success_count=success_count,
        error_count=error_count,
    )


def _record_originals(results: dict[str, Any]) -> None:
    """Store the first reading of each setting, for "undo fpstune's change".

    A setting that was not applicable or could not be read is skipped: recording
    None would promise an undo that writes nothing. Failure here is logged and
    swallowed, because a scan the user asked for must not fail over a
    convenience store.
    """
    try:
        readings = {
            setting_id: result.value
            for setting_id, result in results.items()
            if result.is_applicable and result.value is not None and result.error is None
        }
        added = get_original_values().record_first_seen(readings)
        if added:
            logger.debug("recorded %d setting(s) as first seen", added)
    except Exception as exc:  # pragma: no cover - a store failure is not a scan failure
        logger.warning("could not record original values: %s", exc)


@dataclass(frozen=True)
class _SlowResetTolerance:
    """A setting whose reset lands later than the read-back that checks it."""

    # The requested value that means "put this back to stock".
    reset_value: str
    # Readings that prove the tweak is still in force. Anything else is the
    # reset having landed, whatever the transitional value happens to be.
    still_applied_values: tuple[str, ...]
    why: str
    remedy: str


# Settings whose reset is asynchronous in the OS, keyed by id.
#
# This lives in a table rather than as an `if setting.id == ...` inside the
# generic verifier: the rule is one setting's property, so spelling its id in
# the middle of code that runs for all 395 makes a rename fail silently — the
# branch simply stops matching and the setting starts reporting a false
# verification failure. The cross-check that the key still names a registered
# setting is in tests/test_api/test_verify_contract.py rather than at import
# time, because this module is imported while the registry is being built.
_SLOW_RESET_TOLERANCES: dict[str, _SlowResetTolerance] = {
    "network:dns_security": _SlowResetTolerance(
        reset_value="default",
        still_applied_values=("cloudflare", "cloudflare_security", "cloudflare_family"),
        why="DHCP propagation has not finished, so any non-Cloudflare answer is the reset",
        remedy="may need adapter restart",
    ),
}


# =============================================================================
# Bulk Apply/Reset/Optimize Endpoints (must be before parameterized routes)
# =============================================================================


def _verify_setting_applied(
    setting: SettingExecutor, requested_value: Any, detected_value: Any
) -> tuple[bool, str | None, bool | None]:
    """Verify that a setting was actually applied.

    Returns (success, error_message, verified) where ``verified`` is:
      True  — the value was read back and matched
      False — the value was read back and did not match (success is False)
      None  — no check was possible, so success carries no verification claim

    A skipped check must never be reported as a passed one, which is why the
    outcome is separate from ``success``.
    """
    from fpstune.utils.debug import debug_log

    debug_log("settings", f"_verify_setting_applied: {setting.id}")
    debug_log("settings", f"  requested_value={requested_value}, detected_value={detected_value}")

    # Skip verification for actions — they have no persistent value to read back
    if setting.is_action:
        debug_log("settings", "  Skipping verification (action)")
        return True, None, None

    # Skip verification for advisory/detect-only settings. The test is
    # is_readonly, NOT an empty apply_command: the registry, powercfg and
    # nvprofile executors carry their target in apply_args and leave
    # apply_command empty, so an empty command is no evidence that a setting
    # is advisory. Testing the command here silently exempted 108 settings.
    if setting.is_readonly:
        debug_log("settings", "  Skipping verification (advisory: is_readonly)")
        return True, None, None

    # NVIDIA settings are only verifiable when NVAPI can read the driver back.
    # Without it, detection returns fpstune's own JSON cache — the value apply
    # just wrote — so a match would be a tautology proving nothing. In that case
    # report the apply as unverified rather than claiming a check that did not
    # happen; with NVAPI available the comparison below is a real observation.
    # The test is per setting, not just "is NVAPI loadable": a setting absent
    # from the driver profile also falls back to the cache, and that fallback is
    # exactly the tautology being avoided.
    if setting.detect_type == DetectType.NVPROFILE:
        from fpstune.settings.executors.nvprofile import read_setting_from_driver

        if read_setting_from_driver(str(setting.detect_args.get("setting", ""))) is None:
            debug_log("settings", "  Unverifiable (no driver read-back; value came from cache)")
            return True, None, None

    # If detection returned None, we can't verify - report as failure
    if detected_value is None:
        debug_log("settings", "  PROBLEM: detected_value is None")
        return False, "Verification failed: could not detect current value after apply", False

    # Normalize string sentinels for special-case checks
    actual_str = str(detected_value).lower().strip()

    debug_log(
        "settings", f"  Comparing: requested={requested_value!r} vs detected={detected_value!r}"
    )

    # Skip verification when detection answered with an absence sentinel — the
    # game, service or feature the setting configures is not on this machine.
    # The one sentinel set from applicability.py, never a local respelling: a
    # local two-string tuple here once let "not_supported" and "not_found"
    # fall through and fail verification (CC-02).
    if is_absent_reading(detected_value):
        debug_log(
            "settings",
            f"  Skipping verification: '{actual_str}' sentinel (absent on this system)",
        )
        return True, None, None

    tolerance = _SLOW_RESET_TOLERANCES.get(setting.id)
    if tolerance is not None and str(requested_value).lower().strip() == tolerance.reset_value:
        if actual_str not in tolerance.still_applied_values:
            debug_log(
                "settings",
                f"  {setting.id} reset: accepting '{actual_str}' ({tolerance.why})",
            )
            return True, None, True
        debug_log(
            "settings",
            f"  {setting.id} reset: still showing '{actual_str}', {tolerance.remedy}",
        )
        return (
            False,
            f"{setting.display_name} still showing '{actual_str}' after reset - {tolerance.remedy}",
            False,
        )

    # Use values_equal for type-aware comparison (handles "0" == 0, float tolerance, etc.)
    if not values_equal(requested_value, detected_value):
        debug_log("settings", f"  VERIFICATION FAILED: {requested_value!r} != {detected_value!r}")
        logger.info(
            "[VERIFY FAIL] %s: expected=%r, detected=%r",
            tweak_label(setting.id),
            requested_value,
            detected_value,
        )
        return (
            False,
            f"Verification failed: expected '{requested_value}', got '{detected_value}'",
            False,
        )

    debug_log("settings", "  Verification PASSED")
    logger.info("[VERIFIED]    %s: detected=%r", tweak_label(setting.id), detected_value)
    return True, None, True


def _finalize_apply_response(
    setting: SettingExecutor,
    requested_value: Any,
    engine: DetectionEngine,
    cmd_success: bool,
    cmd_error: str | None,
    activity_label: str,
) -> ApplyResponse:
    """Post-apply: detect new value, verify, log, and return ApplyResponse.

    Single source of truth for all apply/reset/optimize paths.
    """
    new_value = None
    success = cmd_success
    error = cmd_error
    verify_outcome: bool | None = None

    if success:
        # Cleanup settings: invalidate cached size so post-apply detect triggers fresh calculation.
        if setting.detect_command.strip() == "cleanup_status":
            from fpstune.settings.cleanup_cache import cleanup_size_cache

            cleanup_size_cache.invalidate(setting.id)
            # docker_prune and docker_prune_all share the same docker df reclaimable:
            # running one changes the other's estimate, so invalidate the sibling too
            # (the frontend re-detects both after a docker run → fresh recompute).
            _docker_siblings = {
                "cleanup:docker_prune": "cleanup:docker_prune_all",
                "cleanup:docker_prune_all": "cleanup:docker_prune",
            }
            sibling = _docker_siblings.get(setting.id)
            if sibling:
                cleanup_size_cache.invalidate(sibling)
        result = engine.detect_one(setting)
        new_value = result.value
        verified, verify_error, verify_outcome = _verify_setting_applied(
            setting, requested_value, new_value
        )
        if not verified:
            success = False
            error = verify_error
            log_activity(
                f"VERIFY FAILED {setting.display_name}: expected={requested_value!r}, detected={new_value!r}",
                "error",
            )
        else:
            log_activity(
                f"{activity_label} {setting.display_name}: {requested_value!r} → detected={new_value!r}",
                "success",
            )
    else:
        log_activity(f"Failed to {activity_label.lower()} {setting.display_name}: {error}", "error")

    return ApplyResponse(
        setting_id=setting.id,
        success=success,
        error=error,
        new_value=new_value,
        requires_reboot=setting.requires_reboot,
        verified=verify_outcome,
    )


# Free-form STRING settings declare no choices to enumerate, so the guard is
# the value's own shape. Every shipped free-form STRING value is a resolution
# ("2560x1440"), a bare rate ("300.000") or a prefixed one ("Auto:300.000");
# this covers all of those and excludes everything that could break out of an
# unescaped %value% command slot (quotes, whitespace, $, ;, |, backticks).
_SAFE_STRING_PATTERN = r"[A-Za-z0-9._:-]{1,64}"


def _in_apply_value_map(setting: SettingExecutor, value: Any) -> bool:
    """Dict membership that treats an unhashable value as absent, not a 500."""
    try:
        return value in setting.apply_value_map
    except TypeError:
        return False


def _validate_apply_value(setting: SettingExecutor, value: Any) -> str | None:
    """Reject a value the setting's own declaration does not allow (SEC-16).

    The one validation every apply path shares: the single-apply route raises it
    as a 400, ``_apply_one`` returns it as a per-setting failure — so a bulk
    request can no longer hand an arbitrary body straight to an elevated
    command slot that the single-setting route would have refused.

    Three shapes, each derived from the setting itself, never a global list:
      choices     — an enumerated setting takes one of its declared values
      INT/FLOAT   — the declared numeric type, inside any configured range
      free STRING — the setting's own ``validate_pattern``, or a conservative
                    token allowlist when it declares none (SEC-12)
    """
    if setting.choices and value not in setting.choices and not _in_apply_value_map(setting, value):
        return f"Value {value!r} is not valid for {setting.id}. Allowed: {list(setting.choices)}"

    if setting.value_type in (SettingValueType.INT, SettingValueType.FLOAT):
        try:
            numeric = int(value) if setting.value_type == SettingValueType.INT else float(value)
        except (ValueError, TypeError):
            return f"Value {value!r} is not a valid {setting.value_type.value} for {setting.id}."
        if setting.min_value is not None and numeric < setting.min_value:
            return f"Value {numeric} is below the minimum {setting.min_value} for {setting.id}."
        if setting.max_value is not None and numeric > setting.max_value:
            return f"Value {numeric} is above the maximum {setting.max_value} for {setting.id}."

    if setting.value_type == SettingValueType.STRING and not setting.choices:
        pattern = setting.validate_pattern or _SAFE_STRING_PATTERN
        if not isinstance(value, (str, int, float)) or re.fullmatch(pattern, str(value)) is None:
            return f"Value {value!r} does not match the allowed format for {setting.id}."

    return None


def _apply_one(
    setting: SettingExecutor,
    value: Any,
    hardware_context: HardwareContext | None,
    activity_label: str,
    *,
    skip_when_inapplicable: bool,
) -> tuple[str, ApplyResponse]:
    """Apply one setting's value and verify. Shared core for the bulk helpers.

    When the setting is not applicable to the current hardware, bulk apply treats
    it as a benign skip (success), while reset/optimize report it as a failure.
    """
    if hardware_context:
        is_applicable, reason = ApplicabilityChecker(hardware_context).is_applicable(setting)
        if not is_applicable:
            if skip_when_inapplicable:
                return setting.id, ApplyResponse(
                    setting_id=setting.id,
                    success=True,
                    error=None,
                    new_value=None,
                    requires_reboot=False,
                    skipped=True,
                )
            return setting.id, ApplyResponse(
                setting_id=setting.id,
                success=False,
                error=reason or "Setting not applicable to this system",
                new_value=None,
                requires_reboot=False,
            )

    invalid = _validate_apply_value(setting, value)
    if invalid is not None:
        return setting.id, ApplyResponse(
            setting_id=setting.id,
            success=False,
            error=invalid,
            new_value=None,
            requires_reboot=False,
        )

    engine = DetectionEngine(hardware_context=hardware_context)
    success, error = CommandExecutor.apply(setting, value)
    return setting.id, _finalize_apply_response(
        setting, value, engine, success, error, activity_label
    )


def _apply_single_setting(
    setting: SettingExecutor,
    value: Any,
    hardware_context: HardwareContext | None = None,
) -> tuple[str, ApplyResponse]:
    """Apply a single setting and verify. Returns (setting_id, ApplyResponse)."""
    return _apply_one(setting, value, hardware_context, "Applied", skip_when_inapplicable=True)


def _reset_single_setting(
    setting: SettingExecutor,
    hardware_context: HardwareContext | None = None,
) -> tuple[str, ApplyResponse]:
    """Reset a single setting to its default value. Returns (setting_id, ApplyResponse)."""
    return _apply_one(
        setting, setting.default_value, hardware_context, "Reset", skip_when_inapplicable=False
    )


@router.post("/bulk/apply", response_model=BulkApplyResponse)
async def bulk_apply_settings(request: BulkApplyRequest) -> BulkApplyResponse:
    """Apply multiple settings at once with verification (parallel execution).

    The fan-out below is synchronous — a ThreadPoolExecutor drained with
    ``as_completed`` — so the whole run goes to a worker thread. Draining it
    inline blocked the event loop for up to the bulk timeout (PERF-13).
    """
    return await asyncio.to_thread(_run_bulk_apply, request)


def _run_bulk_apply(request: BulkApplyRequest) -> BulkApplyResponse:
    """Synchronous core of ``/bulk/apply``; runs on a worker thread."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    registry = _get_registry()
    hardware_context = _get_hardware_context()
    results: dict[str, ApplyResponse] = {}
    success_count = 0
    error_count = 0
    any_requires_reboot = False

    # Prepare valid settings and check for actions (long-running operations)
    valid_settings: list[tuple[SettingExecutor, Any]] = []
    has_actions = False
    for setting_id, value in request.settings.items():
        setting = registry.get(setting_id)
        if not setting:
            results[setting_id] = ApplyResponse(
                setting_id=setting_id,
                success=False,
                error=f"Unknown setting: {setting_id}",
                new_value=None,
                requires_reboot=False,
            )
            error_count += 1
            log_activity(f"Unknown setting: {setting_id}", "error")
        else:
            valid_settings.append((setting, value))
            if setting.is_action:
                has_actions = True

    # Use longer timeout for maintenance actions (DISM, SFC, etc.)
    bulk_timeout = 300 if has_actions else 60

    # Create a system restore point before applying tweaks (best-effort)
    if valid_settings and sys.platform == "win32":
        _create_restore_point_async()

    # Apply all settings in parallel
    if valid_settings:
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {
                executor.submit(_apply_single_setting, setting, value, hardware_context): setting.id
                for setting, value in valid_settings
            }

            try:
                for future in as_completed(futures, timeout=bulk_timeout):
                    try:
                        setting_id, response = future.result(timeout=bulk_timeout)
                        results[setting_id] = response

                        if response.success:
                            success_count += 1
                            if response.requires_reboot:
                                any_requires_reboot = True
                        else:
                            error_count += 1
                            if response.error:
                                log_activity(
                                    f"APPLY FAILED {setting_id}: {response.error}",
                                    "error",
                                )
                    except Exception as e:
                        setting_id = futures[future]
                        results[setting_id] = ApplyResponse(
                            setting_id=setting_id,
                            success=False,
                            error=str(e),
                            new_value=None,
                            requires_reboot=False,
                        )
                        error_count += 1
                        log_activity(f"APPLY ERROR {setting_id}: {e}", "error")
            except TimeoutError:
                # Handle futures that didn't complete in time
                for future, setting_id in futures.items():
                    if setting_id not in results:
                        future.cancel()
                        results[setting_id] = ApplyResponse(
                            setting_id=setting_id,
                            success=False,
                            error=f"Operation timed out ({bulk_timeout}s)",
                            new_value=None,
                            requires_reboot=False,
                        )
                        error_count += 1
                        log_activity(f"APPLY TIMEOUT {setting_id}", "error")

    # Log summary
    if success_count > 0:
        log_activity(f"Applied {success_count} setting(s) OK", "success")
    if error_count > 0:
        log_activity(f"Failed to apply {error_count} setting(s)", "error")

    return BulkApplyResponse(
        results=results,
        success_count=success_count,
        error_count=error_count,
        requires_reboot=any_requires_reboot,
    )


# =============================================================================
# Info Endpoints
# =============================================================================


def categories_missing_metadata(active_categories: set[str]) -> list[str]:
    """Active categories that ``CATEGORY_METADATA`` never declared."""
    return sorted(active_categories - set(CATEGORY_METADATA))


def _fallback_category_metadata(category_id: str) -> CategoryMetadataResponse:
    """The generated stand-in for a category with no declared metadata."""
    return CategoryMetadataResponse(
        id=category_id,
        display_name=category_id.replace("_", " ").replace("-", " ").title(),
        description="",
        icon="Settings",
        color="text-gray-500",
        order=99,
    )


@router.get("/categories/metadata", response_model=list[CategoryMetadataResponse])
async def get_categories_metadata() -> list[CategoryMetadataResponse]:
    """Get full category metadata for UI rendering.

    Returns all categories with display names, icons, colors, and order.
    This is the SSOT for category UI - frontend should not hardcode any of this.
    """
    registry = await _get_registry_async()
    active_categories = set(registry.get_categories())

    result = [
        CategoryMetadataResponse(
            id=meta.id,
            display_name=meta.display_name,
            description=meta.description,
            icon=meta.icon,
            color=meta.color,
            order=meta.order,
            is_action_only=meta.is_action_only,
        )
        for meta in get_all_categories_metadata()
        if meta.id in active_categories
    ]
    missing = categories_missing_metadata(active_categories)
    if missing:
        logger.warning(
            "categories shipping settings with no CATEGORY_METADATA entry, "
            "rendering under a generated title: %s",
            ", ".join(missing),
        )
    result.extend(_fallback_category_metadata(cat_id) for cat_id in missing)
    return result


def modules_missing_metadata(active_modules: set[str]) -> list[str]:
    """Active modules that ``MODULE_METADATA`` never declared.

    Exported because it is the only way this gap is visible: the list endpoint
    has to keep answering for such a module (dropping it would hide a whole
    section of the UI), so the fallback below cannot simply be deleted. Naming
    the gap is what turns "papered over" into "reported" — ``game_cleanup``
    shipped twelve settings under a title-cased id and no test noticed.
    """
    return sorted(active_modules - set(MODULE_METADATA))


def _fallback_module_metadata(module_id: str) -> ModuleMetadataResponse:
    """The generated stand-in for a module with no declared metadata."""
    return ModuleMetadataResponse(
        id=module_id,
        display_name=module_id.replace("_", " ").replace("-", " ").title(),
        description="",
        order=99,
    )


@router.get("/modules/metadata", response_model=list[ModuleMetadataResponse])
async def get_modules_metadata() -> list[ModuleMetadataResponse]:
    """Get all module metadata for UI rendering.

    Returns all modules with display names, descriptions, and order.
    This is the SSOT for module UI - frontend should not hardcode any of this.
    Replaces hardcoded MODULE_DISPLAY_NAMES and MODULE_DESCRIPTIONS in frontend.
    """
    registry = await _get_registry_async()
    active_modules = {s.module for s in registry.get_all()}

    result = [
        ModuleMetadataResponse(
            id=meta.id,
            display_name=meta.display_name,
            description=meta.description,
            order=meta.order,
        )
        for meta in get_all_modules_metadata()
        if meta.id in active_modules
    ]
    missing = modules_missing_metadata(active_modules)
    if missing:
        logger.warning(
            "modules shipping settings with no MODULE_METADATA entry, "
            "rendering under a generated title: %s",
            ", ".join(missing),
        )
    result.extend(_fallback_module_metadata(module_id) for module_id in missing)
    return result


# =============================================================================
# Bulk Reset/Optimize Endpoints
# =============================================================================


def _run_bulk_op(
    setting_ids: list[str],
    op: Callable[[SettingExecutor, HardwareContext | None], tuple[str, ApplyResponse]],
    success_message: Callable[[int], str],
    error_message: Callable[[int], str],
) -> BulkApplyResponse:
    """Run a per-setting operation across many settings in parallel and aggregate.

    Shared core for bulk reset/optimize: unknown IDs become per-setting errors,
    valid settings run through ``op`` on a thread pool, and results are tallied.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    registry = _get_registry()
    hardware_context = _get_hardware_context()
    results: dict[str, ApplyResponse] = {}
    success_count = 0
    error_count = 0
    any_requires_reboot = False

    valid_settings: list[SettingExecutor] = []
    for setting_id in setting_ids:
        setting = registry.get(setting_id)
        if not setting:
            results[setting_id] = ApplyResponse(
                setting_id=setting_id,
                success=False,
                error=f"Unknown setting: {setting_id}",
                new_value=None,
                requires_reboot=False,
            )
            error_count += 1
        else:
            valid_settings.append(setting)

    if valid_settings:
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {
                executor.submit(op, setting, hardware_context): setting.id
                for setting in valid_settings
            }
            for future in as_completed(futures, timeout=60):
                try:
                    setting_id, response = future.result(timeout=60)
                    results[setting_id] = response
                    if response.success:
                        success_count += 1
                        if response.requires_reboot:
                            any_requires_reboot = True
                    else:
                        error_count += 1
                except Exception as e:
                    setting_id = futures[future]
                    results[setting_id] = ApplyResponse(
                        setting_id=setting_id,
                        success=False,
                        error=str(e),
                        new_value=None,
                        requires_reboot=False,
                    )
                    error_count += 1

    if success_count > 0:
        log_activity(success_message(success_count), "success")
    if error_count > 0:
        log_activity(error_message(error_count), "error")

    return BulkApplyResponse(
        results=results,
        success_count=success_count,
        error_count=error_count,
        requires_reboot=any_requires_reboot,
    )


# =============================================================================
# Individual Apply/Reset/Disable/Verify/Revert Endpoints
# (declared after bulk routes to avoid path conflicts)
# =============================================================================


@router.post("/{setting_id}/apply", response_model=ApplyResponse)
async def apply_setting(setting_id: str, request: ApplyRequest) -> ApplyResponse:
    """Apply a specific setting value with verification."""
    registry = await _get_registry_async()
    setting = registry.get(setting_id)

    if not setting:
        raise HTTPException(404, f"Unknown setting: {setting_id}")

    # The one validation every apply path shares (SEC-16): here it surfaces as
    # an HTTP 400, in the bulk helpers as a per-setting failure.
    invalid = _validate_apply_value(setting, request.value)
    if invalid is not None:
        raise HTTPException(400, invalid)

    hardware_context, is_applicable, reason = await _context_and_applicability(setting)
    if not is_applicable:
        return ApplyResponse(
            setting_id=setting_id,
            success=False,
            error=reason or "Setting not applicable to this system",
            new_value=None,
            requires_reboot=False,
        )

    # A machine fpstune has never cross-checked gets the detection self-check
    # before its first write — a wrong detection is worth finding before
    # anything derives from it (A12). Idempotent: one run per machine.
    from fpstune.utils.self_check import ensure_checked_before_first_apply

    await asyncio.to_thread(ensure_checked_before_first_apply)

    if sys.platform == "win32":
        _create_restore_point_async()

    engine = DetectionEngine(hardware_context=hardware_context)

    def _apply() -> ApplyResponse:
        success, error = CommandExecutor.apply(setting, request.value)
        return _finalize_apply_response(setting, request.value, engine, success, error, "Applied")

    return await asyncio.to_thread(_apply)


@router.post("/{setting_id}/reset", response_model=ApplyResponse)
async def reset_setting(setting_id: str) -> ApplyResponse:
    """Reset a specific setting to its default value with verification."""
    registry = await _get_registry_async()
    setting = registry.get(setting_id)

    if not setting:
        raise HTTPException(404, f"Unknown setting: {setting_id}")

    hardware_context, is_applicable, reason = await _context_and_applicability(setting)
    if not is_applicable:
        return ApplyResponse(
            setting_id=setting_id,
            success=False,
            error=reason or "Setting not applicable to this system",
            new_value=None,
            requires_reboot=False,
        )

    # Reset mutates system state exactly like apply does, so it gets the same
    # rollback safety net — previously only the apply paths created one.
    if sys.platform == "win32":
        _create_restore_point_async()

    engine = DetectionEngine(hardware_context=hardware_context)

    def _reset() -> ApplyResponse:
        success, error = CommandExecutor.apply(setting, setting.default_value)
        return _finalize_apply_response(
            setting, setting.default_value, engine, success, error, "Reset"
        )

    return await asyncio.to_thread(_reset)


@router.post("/{setting_id}/undo", response_model=ApplyResponse)
async def undo_setting(setting_id: str) -> ApplyResponse:
    """Put a setting back to what this machine held when fpstune first saw it.

    Distinct from ``/reset``, which writes the curated Windows stock value. The
    two agree on a machine that was stock to begin with and disagree on one that
    deliberately ran something else — and on that machine a reset silently
    discards the user's own configuration, which is what this exists to avoid.

    Answers 409 when nothing was recorded, rather than falling back to the
    default: quietly doing a reset under the name "undo" would be exactly the
    conflation this endpoint was added to end.
    """
    registry = await _get_registry_async()
    setting = registry.get(setting_id)

    if not setting:
        raise HTTPException(404, f"Unknown setting: {setting_id}")

    originals = get_original_values()
    original = originals.get(setting_id)
    if original is None:
        raise HTTPException(
            409,
            f"fpstune has no record of what {setting_id} held before it was changed. "
            "Originals are recorded by the first scan that reads a setting, so a "
            "setting applied before that scan has none.",
        )

    hardware_context, is_applicable, reason = await _context_and_applicability(setting)
    if not is_applicable:
        return ApplyResponse(
            setting_id=setting_id,
            success=False,
            error=reason or "Setting not applicable to this system",
            new_value=None,
            requires_reboot=False,
        )

    # Undo mutates system state exactly like apply and reset, so it gets the
    # same rollback safety net.
    if sys.platform == "win32":
        _create_restore_point_async()

    engine = DetectionEngine(hardware_context=hardware_context)

    def _undo() -> ApplyResponse:
        success, error = CommandExecutor.apply(setting, original)
        response = _finalize_apply_response(setting, original, engine, success, error, "Undo")
        # Drop the record only once the machine is actually back, so a failed
        # undo can be retried. Keeping it after a success would pin a value from
        # an arbitrarily old session and stop the next scan recording a fresh one.
        if response.success:
            originals.forget(setting_id)
        return response

    return await asyncio.to_thread(_undo)


@router.post("/{setting_id}/verify", response_model=VerifyResponse)
async def verify_setting(setting_id: str, request: VerifyRequest | None = None) -> VerifyResponse:
    """Read a setting and report whether it holds the value asked about.

    The question defaults to "is this at the recommended value" — a drift check
    — which is what this endpoint always answered and never said. That silence
    was a defect: after a ``/reset`` the setting correctly holds its
    ``default_value``, and verifying it reported ``matches=false`` as though the
    reset had failed. The apply and reset responses were never wrong about this;
    they verify against whatever they wrote. Only this endpoint had one fixed
    idea of what "correct" meant.

    ``target`` now names the question, and the answer echoes it back in
    ``target`` and ``expected_value`` so a caller cannot misread which
    comparison it got:

      ``recommended``  is it at the value fpstune advises (default)
      ``default``      is it at the Windows stock value, i.e. did a reset land
      ``original``     is it back to what fpstune first found, i.e. did an undo land

    Does not modify any system state.
    """
    registry = await _get_registry_async()
    setting = registry.get(setting_id)

    if not setting:
        raise HTTPException(404, f"Unknown setting: {setting_id}")

    target = (request.target if request else None) or "recommended"
    if target == "default":
        expected: Any = setting.default_value
    elif target == "original":
        expected = get_original_values().get(setting_id)
        if expected is None:
            raise HTTPException(
                409,
                f"fpstune has no record of what {setting_id} held before it was changed, "
                "so there is nothing to verify against.",
            )
    else:
        expected = setting.recommended_value

    hardware_context = await _get_hardware_context_async()
    engine = DetectionEngine(hardware_context=hardware_context)
    # detect_one runs a synchronous subprocess — keep it off the event loop (PERF-08).
    result = await asyncio.to_thread(engine.detect_one, setting)

    if not result.is_applicable:
        return VerifyResponse(
            setting_id=setting_id,
            matches=False,
            current_value=None,
            expected_value=expected,
            target=target,
            error=result.applicable_reason or "Setting not applicable to this system",
        )

    if result.error:
        return VerifyResponse(
            setting_id=setting_id,
            matches=False,
            current_value=None,
            expected_value=expected,
            target=target,
            error=result.error,
        )

    matches = values_equal(result.value, expected)
    return VerifyResponse(
        setting_id=setting_id,
        matches=matches,
        current_value=result.value,
        expected_value=expected,
        target=target,
    )
