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
    _ensure_restore_point,
    _get_hardware_context,
    _get_registry,
    _reset_single_setting,
)
from fpstune.api.schemas import ApplyResponse, BulkStreamRequest
from fpstune.settings import SettingsRegistry
from fpstune.settings.applicability import HardwareContext
from fpstune.settings.base import SettingExecutor

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
                # What a cleanup reclaimed, measured around its own command by
                # `_apply_and_finalize`, and null for everything else — including
                # a cleanup whose size could not be read (C11 rule 3). The
                # streamed run reports exactly what `POST /apply` returns,
                # because both come off the same ApplyResponse.
                "freed_bytes": response.freed_bytes,
                "size_after_bytes": response.size_after_bytes,
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

    try:
        while remaining > 0:
            item = await event_queue.get()
            if item is None:
                remaining -= 1
            else:
                yield item
    finally:
        # A client that disconnected (the UI's Stop) closes this generator.
        # Settings still waiting for a slot are cancelled so nothing is written
        # after Stop; the at most four already writing finish their one write.
        for task in tasks:
            task.cancel()
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
    """Yield SSE events for every requested setting, each reporting as it goes."""
    tally = _Tally()
    known: list[SettingExecutor] = []

    for setting_id in ids:
        setting = registry.get(setting_id)
        if not setting:
            tally.failed += 1
            yield _sse(
                {"event": "failed", "id": setting_id, "error": f"Unknown setting: {setting_id}"}
            )
            continue
        known.append(setting)

    if known:
        async for event in _stream_each(known, action, hardware_context, tally):
            yield event

    if action == "apply" and tally.succeeded:
        # The one thing the apply path knows about benchmarking: a sentinel the
        # scheduler finds on its next tick, which is what turns "the machine
        # changed" into an after-measurement without anyone asking for one.
        from fpstune.benchmark.ledger import mark_bulk_apply_finished

        mark_bulk_apply_finished()

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
        await asyncio.to_thread(_ensure_restore_point)

    return StreamingResponse(
        _stream_grouped(request.ids, "apply", registry, hardware_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/bulk/stream-reset")
async def bulk_stream_reset(request: BulkStreamRequest) -> StreamingResponse:
    """SSE bulk reset — resets each setting to its default_value.

    Streams per-setting events: started → applied → verified → (failed | done).
    Settings run four at a time.
    Failures do not abort the stream; all IDs are processed.
    """
    registry = await asyncio.to_thread(_get_registry)
    hardware_context = await asyncio.to_thread(_get_hardware_context)

    # Bulk reset mutates state just like bulk apply — same rollback safety net.
    if request.ids and sys.platform == "win32":
        await asyncio.to_thread(_ensure_restore_point)

    return StreamingResponse(
        _stream_grouped(request.ids, "reset", registry, hardware_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
