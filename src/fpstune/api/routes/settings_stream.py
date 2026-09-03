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
import re
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
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
from fpstune.api.schemas import ApplyResponse, BulkStreamRequest
from fpstune.settings import SettingsRegistry
from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext
from fpstune.settings.base import SettingExecutor
from fpstune.settings.detection import DetectionEngine

router = APIRouter()


def _sse(event: dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def _percent(pattern: str | None, line: str) -> float | None:
    """The progress this line reports, if its own command reports any.

    Only settings that declare a `progress_pattern` are asked — a delete script
    that prints a path containing "100%" is not reporting progress, and a bar
    the UI drew from that would be a number nothing measured (C11).
    """
    if not pattern:
        return None
    try:
        match = re.search(pattern, line)
    except re.error:  # pragma: no cover - a definition would have to ship broken
        return None
    if not match:
        return None
    # The pattern carries the number on either side of the sign, so take
    # whichever group matched (see base.PERCENT_PROGRESS).
    found = next((g for g in match.groups() if g), None) or match.group(0)
    try:
        value = float(str(found).replace(",", "."))
    except ValueError:  # pragma: no cover - the pattern matched digits
        return None
    return max(0.0, min(100.0, value))


def apply_target(setting: SettingExecutor, action: str) -> Any:
    """The value this run writes.

    An action is *run*, and the only value that means run is True. Its
    `recommended_value` answers a different question — whether fpstune suggests
    running it unprompted — and for 24 of the 38 actions this ships, including
    both repairs and every developer cache, the answer is False. Deriving the
    target from it made `CommandExecutor.apply` take its own falsy-value branch,
    which skips the action and reports success: measured on the reporting machine
    as `[APPLY] maintenance:sfc_scan → False` followed immediately by
    `Applied System File Checker`, with nothing having run.

    The quiet bulk endpoint never had to know this, because its callers send
    explicit values (`{id: True}`). The stream derives them, so it must.

    A reset is unchanged: writing an action's `default_value` is False by design,
    a cleanup cannot be un-run, and the falsy branch skipping it is correct.
    """
    if action != "apply":
        return setting.default_value
    return True if setting.is_action else setting.recommended_value


def _started(setting: SettingExecutor, *, reports_progress: bool | None = None) -> str:
    """The event that opens a setting's row, before it has anything to report.

    It carries the name and the duration so the row can say "Windows Image
    Repair, 10-30 min" from the first frame rather than starting as an unlabelled
    wait — the whole complaint this stream answers.
    """
    return _sse(
        {
            "event": "started",
            "id": setting.id,
            "name": setting.display_name,
            "duration_estimate": setting.duration_estimate,
            "reports_progress": (
                bool(setting.progress_pattern) if reports_progress is None else reports_progress
            ),
        }
    )


def _output_pump(
    setting: SettingExecutor,
    queue: asyncio.Queue[str | None],
    loop: asyncio.AbstractEventLoop,
) -> Callable[[str, bool], None]:
    """A line callback that puts this setting's output onto the SSE queue.

    Called from the PowerShell reader thread, which is why every hand-off goes
    through `call_soon_threadsafe`: an asyncio queue touched from another thread
    loses events silently rather than loudly.

    `replaces` travels with the line because a progress bar redraws itself in
    place; a client that appends every one of them shows a wall of near-identical
    rows instead of a bar (see utils.powershell._LineSplitter).
    """

    def _on_line(text: str, replaces: bool) -> None:
        event: dict[str, Any] = {
            "event": "output",
            "id": setting.id,
            "text": text,
            "replaces": replaces,
        }
        percent = _percent(setting.progress_pattern, text)
        if percent is not None:
            event["percent"] = percent
        loop.call_soon_threadsafe(queue.put_nowait, _sse(event))

    return _on_line


@dataclass
class _Tally:
    """What the run has come to so far, carried across the two group streams."""

    succeeded: int = 0
    failed: int = 0


def _outcome_events(setting_id: str, response: ApplyResponse) -> list[str]:
    """The events one finished setting produces, whichever path ran it.

    Verification is not re-derived here: it happened inside
    `_finalize_apply_response`, and re-comparing with a raw `values_equal` would
    apply a *different* rule than the one that produced `response.success` (it
    misses the DNS-propagation and service-absent tolerances), so the stream
    could report success=True beside matches=False.
    """
    if response.skipped:
        return [_sse({"event": "skipped", "id": setting_id})]
    if not response.success:
        return [
            _sse(
                {
                    "event": "failed",
                    "id": setting_id,
                    "error": response.error or "Unknown error",
                }
            )
        ]
    return [
        _sse(
            {
                "event": "applied",
                "id": setting_id,
                "success": True,
                "current_value": response.new_value,
                "requires_reboot": response.requires_reboot,
            }
        ),
        _sse(
            {
                "event": "verified",
                "id": setting_id,
                "matches": response.verified,
                "current_value": response.new_value,
            }
        ),
    ]


async def _stream_nvidia(
    settings: list[SettingExecutor],
    action: str,
    hardware_context: HardwareContext | None,
    tally: _Tally,
) -> AsyncIterator[str]:
    """One nvidiaProfileInspector call for every NVIDIA setting in the run."""
    from fpstune.settings.executors.nvprofile import NvProfileExecutor

    for s in settings:
        # An NVIDIA write is one batched call with nothing to print.
        yield _started(s, reports_progress=False)

    # Applicability mirrors _apply_one: checked before any write, with the same
    # asymmetry — apply skips an inapplicable setting benignly, reset reports it
    # as a failure with the reason.
    applicable: list[SettingExecutor] = []
    checker = ApplicabilityChecker(hardware_context) if hardware_context else None
    for s in settings:
        if checker is not None:
            is_applicable, reason = await asyncio.to_thread(checker.is_applicable, s)
            if not is_applicable:
                if action == "apply":
                    tally.succeeded += 1
                    yield _sse({"event": "skipped", "id": s.id})
                else:
                    tally.failed += 1
                    yield _sse(
                        {
                            "event": "failed",
                            "id": s.id,
                            "error": reason or "Setting not applicable to this system",
                        }
                    )
                continue
        applicable.append(s)

    if not applicable:
        return

    updates: dict[str, Any] = {
        s.apply_args["setting"]: apply_target(s, action)
        for s in applicable
        if s.apply_args.get("setting")
    }
    nv_success, nv_error = await asyncio.to_thread(NvProfileExecutor.apply_bulk, updates)

    # The batch write is one NPI call, but everything after it is per setting and
    # goes through _finalize_apply_response — the single post-apply path. Detect,
    # verify, log_activity and the cleanup-cache invalidation all live there;
    # re-implementing them here is how NVIDIA tweaks vanished from the Activity
    # drawer.
    engine = DetectionEngine(hardware_context=hardware_context)
    activity_label = "Applied" if action == "apply" else "Reset"

    for s in applicable:
        target = apply_target(s, action)
        response = await asyncio.to_thread(
            _finalize_apply_response,
            s,
            target,
            engine,
            nv_success,
            None if nv_success else (nv_error or "NVIDIA apply failed"),
            activity_label,
        )
        if response.success:
            tally.succeeded += 1
        else:
            tally.failed += 1
            response.error = response.error or "NVIDIA apply failed"
        for event in _outcome_events(s.id, response):
            yield event


async def _stream_each(
    settings: list[SettingExecutor],
    action: str,
    hardware_context: HardwareContext | None,
    tally: _Tally,
) -> AsyncIterator[str]:
    """Every other setting, four at a time, each reporting as it goes.

    An apply is handed a line pump so a command that takes minutes can say what
    it is doing while it does it; a reset is not, because resets are registry and
    powercfg writes with nothing to print.
    """
    event_queue: asyncio.Queue[str | None] = asyncio.Queue()
    result_counts: dict[str, bool] = {}
    sem = asyncio.Semaphore(4)
    loop = asyncio.get_running_loop()

    async def _process_one(setting: SettingExecutor) -> None:
        async with sem:
            try:
                event_queue.put_nowait(_started(setting))
                if action == "apply":
                    _, response = await asyncio.to_thread(
                        _apply_single_setting,
                        setting,
                        apply_target(setting, action),
                        hardware_context,
                        _output_pump(setting, event_queue, loop),
                    )
                else:
                    _, response = await asyncio.to_thread(
                        _reset_single_setting, setting, hardware_context
                    )
                result_counts[setting.id] = response.skipped or response.success
                for event in _outcome_events(setting.id, response):
                    event_queue.put_nowait(event)
            except Exception as exc:
                result_counts[setting.id] = False
                event_queue.put_nowait(
                    _sse({"event": "failed", "id": setting.id, "error": str(exc)})
                )
            finally:
                event_queue.put_nowait(None)  # per-task sentinel

    tasks = [asyncio.create_task(_process_one(s)) for s in settings]
    remaining = len(settings)

    while remaining > 0:
        item = await event_queue.get()
        if item is None:
            remaining -= 1
        else:
            yield item

    await asyncio.gather(*tasks, return_exceptions=True)

    for ok in result_counts.values():
        if ok:
            tally.succeeded += 1
        else:
            tally.failed += 1


async def _stream_grouped(
    ids: list[str],
    action: str,  # "apply" or "reset"
    registry: SettingsRegistry,
    hardware_context: HardwareContext | None,
) -> AsyncIterator[str]:
    """Yield SSE events grouping NVPROFILE settings into one NPI call.

    NVPROFILE group: single nvidiaProfileInspector invocation for all GPU settings.
    Other groups: asyncio.Semaphore(4) bounded parallelism, each streaming its own
    command's output.
    """
    tally = _Tally()
    nv_settings: list[SettingExecutor] = []
    other_settings: list[SettingExecutor] = []

    for setting_id in ids:
        setting = registry.get(setting_id)
        if not setting:
            tally.failed += 1
            yield _sse(
                {"event": "failed", "id": setting_id, "error": f"Unknown setting: {setting_id}"}
            )
            continue
        if setting.apply_type.value == "nvprofile":
            nv_settings.append(setting)
        else:
            other_settings.append(setting)

    if nv_settings:
        async for event in _stream_nvidia(nv_settings, action, hardware_context, tally):
            yield event

    if other_settings:
        async for event in _stream_each(other_settings, action, hardware_context, tally):
            yield event

    yield _sse(
        {
            "event": "done",
            "total": len(ids),
            "succeeded": tally.succeeded,
            "failed": tally.failed,
        }
    )


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
