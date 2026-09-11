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

import threading
import time
from typing import TYPE_CHECKING, Any

from fpstune.benchmark.operation_lock import is_free
from fpstune.settings import CommandExecutor
from fpstune.settings.cleanup_measure import (
    NOTHING_MEASURED,
    cleanup_type_of,
    freed_after_cleanup,
    measure_cleanup_size,
)
from fpstune.settings.executors import action_will_not_run

if TYPE_CHECKING:
    from collections.abc import Callable

    from fpstune.api.schemas import ApplyResponse
    from fpstune.settings.base import SettingExecutor
    from fpstune.settings.detection import DetectionEngine


#: How many applies `/bulk/apply` runs at once (`routes/settings.py`).
_BULK_WORKERS = 16

#: How long an apply waits for a background measurement to give the machine back.
#: A bench holds `operation_lock.OPERATION_MUTEX` for its run; an apply landing
#: on a machine mid-measurement would change what the second half of the pair is
#: measuring, so it waits — and not for long, because a user pressed a button.
_BENCH_WAIT_SECONDS = 30.0
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


def _wait_for_bench() -> bool:
    """True once no bench holds the machine; False if one still does after the wait."""
    deadline = time.monotonic() + _BENCH_WAIT_SECONDS
    while not is_free():
        if time.monotonic() >= deadline:
            return False
        time.sleep(_BENCH_POLL_SECONDS)
    return True


def apply_budget_seconds(setting: SettingExecutor) -> int:
    """The longest one apply of `setting` can legitimately take, measurement included.

    A cleanup is not only its command: the same size instrument runs immediately
    before it and immediately after it, and for the readings still taken through
    PowerShell that is the expensive part. DISM's component store analysis
    measured 43.0 s before a cleanup and 34.7 s after it on this machine, either
    side of a run the user timed at about 108 s — so a flat cap that ignored the
    readings would abandon a cleanup that was working.
    """
    from fpstune.settings.executors.powershell import apply_timeout_seconds
    from fpstune.settings.executors.ps_batch import cleanup_batch_timeout

    budget = apply_timeout_seconds(setting, setting.apply_command.strip())
    cleanup_type = cleanup_type_of(setting)
    if cleanup_type:
        from fpstune.settings.cleanup_targets import CLEANUP_TARGETS

        if cleanup_type not in CLEANUP_TARGETS:
            # A folder is walked in this process in well under a second; only the
            # readings left in PowerShell are worth budgeting for.
            budget += 2 * cleanup_batch_timeout((cleanup_type,))
    return budget


def bulk_apply_timeout(settings: list[SettingExecutor]) -> int:
    """How long `/bulk/apply` may wait for this particular set of settings.

    Derived rather than fixed. The flat 300 s it replaces was shorter than a
    single DISM cleanup on this machine — 43 s of analysis, the cleanup itself,
    then 35 s more — so the one setting most likely to need the whole budget was
    the one guaranteed not to get it.
    """
    if not settings:
        return 60
    budgets = [apply_budget_seconds(setting) for setting in settings]
    waves = -(-len(budgets) // _BULK_WORKERS)  # ceiling division
    return max(60, max(budgets), (sum(budgets) + waves - 1) // _BULK_WORKERS)


def apply_and_finalize(
    setting: SettingExecutor,
    value: Any,
    engine: DetectionEngine,
    activity_label: str,
    on_line: Callable[[str, bool], None] | None = None,
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
    """
    global _in_flight
    success: bool
    error: str | None
    if not _wait_for_bench():
        success = False
        error = "A background measurement is using the machine; try again in a moment"
        freed = NOTHING_MEASURED
    else:
        with _in_flight_guard:
            _in_flight += 1
        try:
            will_run = not action_will_not_run(setting, value)
            before = measure_cleanup_size(setting) if will_run else None
            success, error = CommandExecutor.apply(setting, value, on_line)
            freed = (
                freed_after_cleanup(setting, before) if success and will_run else NOTHING_MEASURED
            )
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
