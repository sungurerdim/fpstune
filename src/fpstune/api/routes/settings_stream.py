"""Server-Sent Events (SSE) streaming endpoints for bulk apply/reset.

Split out of routes/settings.py: this module owns the sequential SSE bulk
operations (``/bulk/stream-apply`` and ``/bulk/stream-reset``). It reuses the
single-setting apply/reset helpers from routes/settings.py — the dependency is
one-way (settings_stream imports settings, never the reverse) so there is no
import cycle. Registered under the same ``/api/settings`` prefix.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fpstune.api.routes.settings import (
    _apply_single_setting,
    _create_restore_point_async,
    _finalize_apply_response,
    _get_hardware_context,
    _get_registry,
    _reset_single_setting,
)
from fpstune.api.schemas import BulkStreamRequest
from fpstune.settings import SettingsRegistry
from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
from fpstune.settings.base import SettingExecutor
from fpstune.settings.detection import DetectionEngine

router = APIRouter()


def _sse(event: dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


async def _stream_grouped(
    ids: list[str],
    action: str,  # "apply" or "reset"
    registry: SettingsRegistry,
    hardware_context: HardwareContext | None,
) -> AsyncIterator[str]:
    """Yield SSE events grouping NVPROFILE settings into one NPI call.

    NVPROFILE group: single nvidiaProfileInspector invocation for all GPU settings.
    Other groups: asyncio.Semaphore(4) bounded parallelism.
    """
    from fpstune.settings.executors.nvprofile import NvProfileExecutor

    succeeded = 0
    failed = 0

    nv_settings: list[SettingExecutor] = []
    other_settings: list[SettingExecutor] = []

    for setting_id in ids:
        setting = registry.get(setting_id)
        if not setting:
            failed += 1
            yield _sse(
                {"event": "failed", "id": setting_id, "error": f"Unknown setting: {setting_id}"}
            )
            continue
        if setting.apply_type.value == "nvprofile":
            nv_settings.append(setting)
        else:
            other_settings.append(setting)

    # --- NVIDIA batch: single NPI write ---
    if nv_settings:
        for s in nv_settings:
            yield _sse({"event": "started", "id": s.id})

        # Applicability mirrors _apply_one: checked before any write, with the
        # same asymmetry — apply skips an inapplicable setting benignly, reset
        # reports it as a failure with the reason.
        applicable: list[SettingExecutor] = []
        checker = ApplicabilityChecker(hardware_context) if hardware_context else None
        for s in nv_settings:
            if checker is not None:
                is_applicable, reason = await asyncio.to_thread(checker.is_applicable, s)
                if not is_applicable:
                    if action == "apply":
                        succeeded += 1
                        yield _sse({"event": "skipped", "id": s.id})
                    else:
                        failed += 1
                        yield _sse(
                            {
                                "event": "failed",
                                "id": s.id,
                                "error": reason or "Setting not applicable to this system",
                            }
                        )
                    continue
            applicable.append(s)

        if applicable:
            updates: dict[str, Any] = {
                s.apply_args["setting"]: (
                    s.recommended_value if action == "apply" else s.default_value
                )
                for s in applicable
                if s.apply_args.get("setting")
            }

            nv_success, nv_error = await asyncio.to_thread(NvProfileExecutor.apply_bulk, updates)

            # The batch write is one NPI call, but everything after it is per
            # setting and goes through _finalize_apply_response — the single
            # post-apply path. Detect, verify, log_activity and the cleanup-cache
            # invalidation all live there; re-implementing them here is how
            # NVIDIA tweaks vanished from the Activity drawer.
            engine = DetectionEngine(hardware_context=hardware_context)
            activity_label = "Applied" if action == "apply" else "Reset"

            for s in applicable:
                target = s.recommended_value if action == "apply" else s.default_value
                response = await asyncio.to_thread(
                    _finalize_apply_response,
                    s,
                    target,
                    engine,
                    nv_success,
                    None if nv_success else (nv_error or "NVIDIA apply failed"),
                    activity_label,
                )

                if not response.success:
                    failed += 1
                    yield _sse(
                        {
                            "event": "failed",
                            "id": s.id,
                            "error": response.error or "NVIDIA apply failed",
                        }
                    )
                    continue

                succeeded += 1
                yield _sse(
                    {
                        "event": "applied",
                        "id": s.id,
                        "success": True,
                        "current_value": response.new_value,
                        "requires_reboot": response.requires_reboot,
                    }
                )
                yield _sse(
                    {
                        "event": "verified",
                        "id": s.id,
                        "matches": response.verified,
                        "current_value": response.new_value,
                    }
                )

    # --- Other settings: bounded parallel (max 4 concurrent) ---
    if other_settings:
        event_queue: asyncio.Queue[str | None] = asyncio.Queue()
        result_counts: dict[str, bool] = {}
        sem = asyncio.Semaphore(4)

        async def _process_one(setting: SettingExecutor) -> None:
            async with sem:
                try:
                    event_queue.put_nowait(_sse({"event": "started", "id": setting.id}))
                    if action == "apply":
                        _, response = await asyncio.to_thread(
                            _apply_single_setting,
                            setting,
                            setting.recommended_value,
                            hardware_context,
                        )
                    else:
                        _, response = await asyncio.to_thread(
                            _reset_single_setting, setting, hardware_context
                        )

                    if response.skipped:
                        event_queue.put_nowait(_sse({"event": "skipped", "id": setting.id}))
                        result_counts[setting.id] = True
                    elif response.success:
                        result_counts[setting.id] = True
                        event_queue.put_nowait(
                            _sse(
                                {
                                    "event": "applied",
                                    "id": setting.id,
                                    "success": True,
                                    "current_value": response.new_value,
                                    "requires_reboot": response.requires_reboot,
                                }
                            )
                        )
                        # Verification already happened inside
                        # _finalize_apply_response — re-comparing here with a
                        # raw values_equal would apply a *different* rule than
                        # the one that produced response.success (it misses the
                        # DNS-propagation and service-absent tolerances) and
                        # could emit success=True alongside matches=False.
                        event_queue.put_nowait(
                            _sse(
                                {
                                    "event": "verified",
                                    "id": setting.id,
                                    "matches": response.verified,
                                    "current_value": response.new_value,
                                }
                            )
                        )
                    else:
                        result_counts[setting.id] = False
                        event_queue.put_nowait(
                            _sse(
                                {
                                    "event": "failed",
                                    "id": setting.id,
                                    "error": response.error or "Unknown error",
                                }
                            )
                        )
                except Exception as exc:
                    result_counts[setting.id] = False
                    event_queue.put_nowait(
                        _sse({"event": "failed", "id": setting.id, "error": str(exc)})
                    )
                finally:
                    event_queue.put_nowait(None)  # per-task sentinel

        tasks = [asyncio.create_task(_process_one(s)) for s in other_settings]
        remaining = len(other_settings)

        while remaining > 0:
            item = await event_queue.get()
            if item is None:
                remaining -= 1
            else:
                yield item

        await asyncio.gather(*tasks, return_exceptions=True)

        for ok in result_counts.values():
            if ok:
                succeeded += 1
            else:
                failed += 1

    yield _sse({"event": "done", "total": len(ids), "succeeded": succeeded, "failed": failed})


@router.post("/bulk/stream-apply")
async def bulk_stream_apply(request: BulkStreamRequest) -> StreamingResponse:
    """Sequential SSE bulk apply — uses recommended_value for each setting.

    Streams per-setting events: started → applied → verified → (failed | done).
    Failures do not abort the stream; all IDs are processed.
    """
    # Both are cached, and both build their cache with subprocess work on first
    # call — which is the call a bulk apply is most likely to be.
    registry = await asyncio.to_thread(_get_registry)
    hardware_context = await asyncio.to_thread(_get_hardware_context)

    if request.ids and sys.platform == "win32":
        _create_restore_point_async()

    return StreamingResponse(
        _stream_grouped(request.ids, "apply", registry, hardware_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/bulk/stream-reset")
async def bulk_stream_reset(request: BulkStreamRequest) -> StreamingResponse:
    """SSE bulk reset — resets each setting to its default_value.

    Streams per-setting events: started → applied → verified → (failed | done).
    NVPROFILE settings are batched into one NPI call. Others run 4-at-a-time.
    Failures do not abort the stream; all IDs are processed.
    """
    registry = await asyncio.to_thread(_get_registry)
    hardware_context = await asyncio.to_thread(_get_hardware_context)

    # Bulk reset mutates state just like bulk apply — same rollback safety net.
    if request.ids and sys.platform == "win32":
        _create_restore_point_async()

    return StreamingResponse(
        _stream_grouped(request.ids, "reset", registry, hardware_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
