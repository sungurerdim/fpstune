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
from fpstune.api.definitions_view import setting_to_response
from fpstune.api.routes.settings_apply import apply_and_finalize
from fpstune.api.schemas import (
    ApplyRequest,
    ApplyResponse,
    CategoryMetadataResponse,
    DetectRequest,
    DetectResponse,
    ModuleMetadataResponse,
    SettingDefinitionResponse,
    SettingState,
)
from fpstune.api.state_view import setting_state
from fpstune.safety import restore
from fpstune.settings import (
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
    SettingExecutor,
    SettingValueType,
    get_all_categories_metadata,
    get_all_modules_metadata,
)
from fpstune.settings.hardware_context import build_hardware_context
from fpstune.utils.logger import log_activity, tweak_label

logger = logging.getLogger(__name__)


def _ensure_restore_point() -> None:
    """Block until this session's restore point exists (safety.restore owns it).

    A one-line delegate rather than a from-import because it is the seam the API
    tests patch. Blocking, so call it off the event loop.
    """
    restore.ensure_session_restore_point()


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


@router.get("/definitions", response_model=list[SettingDefinitionResponse])
async def get_definitions() -> list[SettingDefinitionResponse]:
    """Get all setting definitions (static, instant).

    Used by frontend for initial store population.
    No detection is performed - returns immediately.
    """
    registry = await _get_registry_async()
    return [setting_to_response(s) for s in registry.get_all()]


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

    # Run parallel detection off the event loop. No outer deadline: every
    # process a detection starts runs under the stall rule (utils.process_watch).
    results = await asyncio.to_thread(functools.partial(engine.detect_all, settings))

    total_time_ms = int((time.perf_counter() - start) * 1000)
    settings_map = {s.id: s for s in settings}

    # Convert to response
    response_results: dict[str, SettingState] = {}
    success_count = error_count = 0

    for setting_id, result in results.items():
        response_results[setting_id] = setting_state(settings_map[setting_id], result)
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
# Verifying an apply, and the post-apply path every apply ends in
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
    # NVIDIA executors carry their target in apply_args and leave
    # apply_command empty, so an empty command is no evidence that a setting
    # is advisory. Testing the command here silently exempted 108 settings.
    if setting.is_readonly:
        debug_log("settings", "  Skipping verification (advisory: is_readonly)")
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
    *,
    freed_bytes: int | None = None,
    size_after_bytes: int | None = None,
) -> ApplyResponse:
    """Post-apply: re-detect, verify, log, and return ApplyResponse.

    Single source of truth for every apply path (reset is an apply of the
    default). The response carries the re-detected `SettingState` — the object
    `/detect` returns — so a write and a read report one shape.

    `freed_bytes` and `size_after_bytes` are what a cleanup's own size
    instrument read around the command, and they are only ever carried through
    here — this function runs *after* the command, so it could not take the
    before reading itself. `settings_apply.apply_and_finalize` measures the pair.
    """
    state: SettingState | None = None
    success = cmd_success
    error = cmd_error
    warnings: list[str] = []
    verify_outcome: bool | None = None

    if success:
        result = engine.detect_one(setting)
        state = setting_state(setting, result)
        verified, verify_error, verify_outcome = _verify_setting_applied(
            setting, requested_value, result.value
        )
        if not verified:
            success = False
            error = verify_error
            log_activity(
                f"VERIFY FAILED {setting.display_name}: expected={requested_value!r}, detected={result.value!r}",
                "error",
            )
        else:
            # A handler that succeeded may still return a sentence in the error
            # slot ("FPS Balanced profile activated"). It is a note, not a
            # failure: putting it in `error` made a clean apply read as partial.
            # "applied, but ..." is the one success-with-warning shape and keeps
            # the error so the warning reaches the caller and the operation log.
            if error and "applied, but" in error.casefold():
                warnings.append(error)
                log_activity(error, "warning")
                error = None
            elif error:
                log_activity(error, "info")
                error = None
            log_activity(
                f"Applied {setting.display_name}: {requested_value!r} → detected={result.value!r}",
                "success",
            )
    else:
        log_activity(f"Failed to apply {setting.display_name}: {error}", "error")

    return ApplyResponse(
        setting_id=setting.id,
        success=success,
        error=error,
        warnings=warnings,
        state=state,
        requires_reboot=setting.requires_reboot,
        verified=verify_outcome,
        freed_bytes=freed_bytes,
        size_after_bytes=size_after_bytes,
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
    as a 400, ``_apply_single_setting`` returns it as a per-setting failure — so a bulk
    request can no longer hand an arbitrary body straight to an elevated
    command slot that the single-setting route would have refused.

    A state setting takes a value, never ``None``: reset is an apply of the row's
    ``default_value``, and a row whose default could not be derived has none
    (C6: "a default that cannot be derived is not invented"), so a null write
    is refused here, where the write happens, whatever the client sent. An
    action takes ``None`` as "do not run" and is left alone.

    Three shapes, each derived from the setting itself, never a global list:
      choices     — an enumerated setting takes one of its declared values
      INT/FLOAT   — the declared numeric type, inside any configured range
      free STRING — the setting's own ``validate_pattern``, or a conservative
                    token allowlist when it declares none (SEC-12)
    """
    if value is None and not setting.is_action:
        return (
            f"{setting.display_name} needs a value to write; "
            "a row with no derivable default has no reset."
        )
    if setting.choices and value not in setting.choices and not _in_apply_value_map(setting, value):
        return f"Value {value!r} is not valid for {setting.id}. Allowed: {list(setting.choices)}"
    if setting.value_type == SettingValueType.CHOICE and not setting.can_write(value):
        return (
            f"Value {value!r} is a state {setting.id} detects but cannot set. "
            f"Settable: {[c for c in setting.choices if setting.can_write(c)]}"
        )

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


def _apply_single_setting(
    setting: SettingExecutor,
    value: Any,
    hardware_context: HardwareContext | None = None,
    on_line: Callable[[str, bool], None] | None = None,
) -> tuple[str, ApplyResponse]:
    """Apply one setting's value and verify. The core the bulk stream runs per id.

    A setting that does not apply to this hardware is a benign skip (success).
    Reset is not a separate path: it is this function called with the setting's
    `default_value`.

    `on_line` asks for the command's output while it runs, for the callers that
    can show it. Everything else about the run is identical — same applicability
    check, same validation, same `apply_and_finalize` afterwards — because a
    streamed apply that took a different path would be a second apply.
    """
    if hardware_context:
        is_applicable, _reason = ApplicabilityChecker(hardware_context).is_applicable(setting)
        if not is_applicable:
            return setting.id, ApplyResponse(
                setting_id=setting.id,
                success=True,
                error=None,
                requires_reboot=False,
                skipped=True,
            )

    invalid = _validate_apply_value(setting, value)
    if invalid is not None:
        return setting.id, ApplyResponse(
            setting_id=setting.id,
            success=False,
            error=invalid,
            requires_reboot=False,
        )

    engine = DetectionEngine(hardware_context=hardware_context)
    return setting.id, apply_and_finalize(setting, value, engine, on_line)


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
        color="text-gray-500",
        order=99,
    )


@router.get("/categories/metadata", response_model=list[CategoryMetadataResponse])
async def get_categories_metadata() -> list[CategoryMetadataResponse]:
    """Get full category metadata for UI rendering.

    Returns all categories with display names, colors, and order.
    This is the SSOT for category UI - frontend should not hardcode any of this.
    """
    registry = await _get_registry_async()
    active_categories = set(registry.get_categories())

    result = [
        CategoryMetadataResponse(
            id=meta.id,
            display_name=meta.display_name,
            description=meta.description,
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
# Individual Apply Endpoint
# (declared after the fixed-path routes to avoid path conflicts)
# =============================================================================


@router.post("/{setting_id}/apply", response_model=ApplyResponse)
async def apply_setting(setting_id: str, request: ApplyRequest) -> ApplyResponse:
    """Apply a specific setting value with verification."""
    registry = await _get_registry_async()
    setting = registry.get(setting_id)

    if not setting:
        raise HTTPException(404, f"Unknown setting: {setting_id}")

    # The one validation every apply path shares (SEC-16): here it surfaces as
    # an HTTP 400, in the bulk stream as a per-setting failure.
    invalid = _validate_apply_value(setting, request.value)
    if invalid is not None:
        raise HTTPException(400, invalid)

    hardware_context, is_applicable, reason = await _context_and_applicability(setting)
    if not is_applicable:
        return ApplyResponse(
            setting_id=setting_id,
            success=False,
            error=reason or "Setting not applicable to this system",
            requires_reboot=False,
        )

    # A machine fpstune has never cross-checked gets the detection self-check
    # before its first write — a wrong detection is worth finding before
    # anything derives from it (A12). Idempotent: one run per machine.
    from fpstune.utils.self_check import ensure_checked_before_first_apply

    await asyncio.to_thread(ensure_checked_before_first_apply)

    if sys.platform == "win32":
        await asyncio.to_thread(_ensure_restore_point)

    engine = DetectionEngine(hardware_context=hardware_context)

    def _apply() -> ApplyResponse:
        return apply_and_finalize(setting, request.value, engine)

    return await asyncio.to_thread(_apply)
