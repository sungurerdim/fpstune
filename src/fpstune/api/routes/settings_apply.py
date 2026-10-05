"""Running one setting's command, and measuring what it freed while it runs.

Split out of routes/settings.py under the SoC ceiling that module carries: the
apply *pipeline* is where new surface has been landing, and this is the first
piece of it to move. It is the one place every apply, reset and undo path runs a
command — bulk, streamed and single-setting alike — which is what lets a cleanup
be measured rather than estimated.

The dependency runs one way at import time: nothing here imports routes/settings
at module level, so this module can be imported from it. `_finalize_apply_response`
is looked up on that module when the run is over, which keeps it the single
post-apply path it is documented to be, and keeps it patchable by the tests that
already name it there.
"""

from __future__ import annotations

import functools
import threading
import time
from typing import TYPE_CHECKING, Any

from fpstune.api.schemas import ApplyResponse
from fpstune.benchmark.operation_lock import is_free
from fpstune.safety.originals import get_original_values
from fpstune.safety.raw_state import restore as restore_raw_state
from fpstune.settings import CommandExecutor
from fpstune.settings.applicability import ApplicabilityChecker
from fpstune.settings.cleanup_measure import (
    NOTHING_MEASURED,
    freed_after_cleanup,
    measure_cleanup_size,
)
from fpstune.settings.detection import DetectionEngine
from fpstune.settings.executors import action_will_not_run

if TYPE_CHECKING:
    from collections.abc import Callable

    from fpstune.settings.applicability import HardwareContext
    from fpstune.settings.base import SettingExecutor


#: How many applies `/bulk/apply` runs at once (`routes/settings.py`).
_BULK_WORKERS = 16

#: How often an apply looks again while a measurement holds the machine.
_BENCH_POLL_SECONDS = 0.5

# Applies in flight in this process. The scheduler reads it before starting a
# bench: the Windows mutex is per-thread and a bulk apply runs on many threads,
# so the apply side keeps a counter rather than taking the mutex itself.
_in_flight = 0
_in_flight_guard = threading.Lock()


def applies_in_flight() -> int:
    """How many applies are running right now — the scheduler's other guard."""
    with _in_flight_guard:
        return _in_flight


def _wait_for_bench() -> None:
    """Return once no bench holds the machine.

    No fixed deadline. A bench holds `operation_lock.OPERATION_MUTEX` for one
    step, and the scheduler and the suite both stand down before the next step
    while an apply is in flight (counted before this wait), so the wait is at
    most the step already running — itself bounded by its own deadline
    (`benchmark.suite.run_bench_with_deadline`). The old 30 s cap refused the
    user's apply while a healthy measurement was finishing.
    """
    if is_free():
        return
    from fpstune.utils.logger import log_activity

    log_activity("Waiting for a background measurement to finish before applying")
    while not is_free():
        time.sleep(_BENCH_POLL_SECONDS)


def apply_and_finalize(
    setting: SettingExecutor,
    value: Any,
    engine: DetectionEngine,
    activity_label: str,
    on_line: Callable[[str, bool], None] | None = None,
    write: Callable[[], tuple[bool, str | None]] | None = None,
) -> ApplyResponse:
    """Run one setting's command and turn the outcome into the response.

    The single point every apply, reset and undo path reaches — bulk, streamed
    and single-setting alike — which is what lets a cleanup be *measured* rather
    than estimated: the same size instrument runs immediately before the command
    and immediately after it, and the response carries the difference. A second
    copy of this pairing is how the quiet route and the streamed one would come
    to report different numbers for the same run.

    The measurement is never streamed through `on_line`: that channel is the
    command's own output, and PowerShell fpstune ran to size a folder is not
    something the command said. Nor is anything measured around an action that
    is not going to run — a cleanup reset carries `False`, which is permission
    withheld, and sizing a folder twice around a command that never happened
    would cost two scans to report that nothing was freed.

    ``write`` replaces the setting's own command — undo passes one that puts the
    recorded stored state back verbatim — and everything around it (the bench
    lock, detection, verification against ``value``) stays the same.
    """
    global _in_flight
    success: bool
    error: str | None
    # Counted *before* waiting for the lock. Counting after left a window: the
    # scheduler read zero applies, this side saw the lock free, and then both
    # went ahead — a bench measuring a machine mid-apply. Counted first, a bench
    # that takes the lock afterwards sees this apply and stands down
    # (`scheduler.poll_once`, `benchmark_suite`), and one that took it earlier
    # is waited out here.
    with _in_flight_guard:
        _in_flight += 1
    try:
        _wait_for_bench()
        will_run = not action_will_not_run(setting, value)
        before = measure_cleanup_size(setting) if will_run else None
        success, error = (
            write() if write is not None else CommandExecutor.apply(setting, value, on_line)
        )
        freed = freed_after_cleanup(setting, before) if success and will_run else NOTHING_MEASURED
    finally:
        with _in_flight_guard:
            _in_flight -= 1

    # Looked up now rather than imported above: routes/settings imports this
    # module, so the edge back to it cannot be a module-level one — and a late
    # lookup is what keeps the finalizer patchable where the tests name it.
    from fpstune.api.routes import settings as settings_routes

    return settings_routes._finalize_apply_response(
        setting,
        value,
        engine,
        success,
        error,
        activity_label,
        freed_bytes=freed.freed_bytes,
        size_after_bytes=freed.size_after_bytes,
    )


def _unwritable_original(setting: SettingExecutor) -> str | None:
    """Why the recorded original cannot be written back, or None when it can.

    Two shapes, both seen on a real machine. A label outside the setting's choices
    came from an earlier release's vocabulary; no map says what it meant, and the
    registry writer either failed to convert it or stored the label's own text. A
    state the setting declares unwritable (a guard's "changed", a Wi-Fi radio that
    is off) has no write at all. A recorded stored state is written back verbatim
    and so needs no label to be writable, but its label still has to be one this
    release can verify against.
    """
    originals = get_original_values()
    original = originals.get(setting.id)
    if original is None:
        return None
    reset_note = "Reset to the Windows default still works."
    if not setting.is_known_state(original):
        return (
            f"The state recorded for {setting.id}, {original!r}, comes from an earlier fpstune "
            f"release and is not one this release can restore. {reset_note}"
        )
    if originals.get_raw(setting.id) is None and not setting.can_write(original):
        return (
            f"fpstune cannot write back {original!r} for {setting.id}: that is a state it "
            f"detects but never sets. {reset_note}"
        )
    return None


def offered_original(setting: SettingExecutor) -> Any | None:
    """The recorded original the UI may offer to put back, or None.

    None both when nothing was recorded and when what was recorded cannot be
    written; the UI offers an undo exactly when this is not None.
    """
    if _unwritable_original(setting) is not None:
        return None
    return get_original_values().get(setting.id)


def undo_refusal(setting: SettingExecutor) -> str | None:
    """Why `setting` cannot be undone, or None when it can."""
    if setting.is_action or setting.is_readonly:
        return f"{setting.id} is an action or an advisory; there is no earlier state to put back."
    if setting.apply_command == "display_mode_native":
        return (
            "A display mode is undone by not keeping it: the new mode reverts on its own "
            "unless it is kept within 15 seconds. Pick another mode in Windows Settings."
        )
    originals = get_original_values()
    damaged = originals.damaged()
    if damaged:
        return f"Undo is unavailable because {damaged}. Reset to the Windows default still works."
    if originals.get(setting.id) is None:
        return (
            f"fpstune has no record of what {setting.id} held before it was changed. "
            "Originals are recorded by the first scan that reads a setting, so a "
            "setting applied before that scan has none."
        )
    return _unwritable_original(setting)


def undo_single_setting(
    setting: SettingExecutor, hardware_context: HardwareContext | None = None
) -> tuple[str, ApplyResponse]:
    """Write back what this machine held, verify, and forget the record once it landed.

    The one undo path, for the single endpoint and the streamed bulk undo alike;
    here rather than in the route module, which is at its size ceiling.
    Refusals come back as failed responses; the endpoint turns them into 409s
    before calling this.
    """
    refusal = undo_refusal(setting)
    if refusal is not None:
        return setting.id, ApplyResponse(
            setting_id=setting.id,
            success=False,
            error=refusal,
            new_value=None,
            requires_reboot=False,
        )
    if hardware_context:
        is_applicable, reason = ApplicabilityChecker(hardware_context).is_applicable(setting)
        if not is_applicable:
            return setting.id, ApplyResponse(
                setting_id=setting.id,
                success=False,
                error=reason or "Setting not applicable to this system",
                new_value=None,
                requires_reboot=False,
            )
    originals = get_original_values()
    original = originals.get(setting.id)
    # The stored state itself where it was captured, so nothing is lost to the
    # display value's many-to-one mapping (safety/raw_state.py).
    raw = originals.get_raw(setting.id)
    write = functools.partial(restore_raw_state, setting, raw) if raw is not None else None
    engine = DetectionEngine(hardware_context=hardware_context)
    response = apply_and_finalize(setting, original, engine, "Undo", write=write)
    # Drop the record only once the machine is actually back, so a failed undo
    # can be retried. Keeping it after a success would pin a value from an
    # arbitrarily old session and stop the next scan recording a fresh one.
    if response.success:
        originals.forget(setting.id)
    return setting.id, response
