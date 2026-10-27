"""Running one setting's command, and measuring what it freed while it runs.

Split out of routes/settings.py under the SoC ceiling that module carries: the
apply *pipeline* is where new surface has been landing, and this is the first
piece of it to move. It is the one place every apply path runs a command — the
bulk stream and the single-setting route alike; reset is an apply of the
default — which is what lets a cleanup be measured rather than estimated.

The dependency runs one way at import time: nothing here imports routes/settings
at module level, so this module can be imported from it. `_finalize_apply_response`
is looked up on that module when the run is over, which keeps it the single
post-apply path it is documented to be, and keeps it patchable by the tests that
already name it there.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from fpstune.api.schemas import ApplyResponse
from fpstune.benchmark.operation_lock import is_free
from fpstune.settings import CommandExecutor
from fpstune.settings.apply_state import (
    applies_in_flight as applies_in_flight,
)
from fpstune.settings.apply_state import (
    apply_in_flight,
)
from fpstune.settings.cleanup_measure import (
    NOTHING_MEASURED,
    freed_after_cleanup,
    measure_cleanup_size,
)
from fpstune.settings.detection import DetectionEngine
from fpstune.settings.executors import action_will_not_run
from fpstune.utils.operation_log import operation_log

if TYPE_CHECKING:
    from collections.abc import Callable

    from fpstune.settings.base import SettingExecutor


#: How often an apply looks again while a measurement holds the machine.
_BENCH_POLL_SECONDS = 0.5


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
    on_line: Callable[[str, bool], None] | None = None,
) -> ApplyResponse:
    """Run one setting's command and turn the outcome into the response.

    The single point every apply path reaches — the bulk stream and the
    single-setting route alike; reset is an apply of the default — which is what
    lets a cleanup be *measured* rather than estimated: the same size instrument runs immediately before the command
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
    started = time.perf_counter()
    success: bool
    error: str | None
    will_run = True
    # Counted before waiting for the lock (the context manager's own docstring
    # carries the window that counting later left open).
    with apply_in_flight():
        _wait_for_bench()
        will_run = not action_will_not_run(setting, value)
        before = measure_cleanup_size(setting) if will_run else None
        success, error = CommandExecutor.apply(setting, value, on_line)
        freed = freed_after_cleanup(setting, before) if success and will_run else NOTHING_MEASURED

    # Looked up now rather than imported above: routes/settings imports this
    # module, so the edge back to it cannot be a module-level one — and a late
    # lookup is what keeps the finalizer patchable where the tests name it.
    from fpstune.api.routes import settings as settings_routes

    response = settings_routes._finalize_apply_response(
        setting,
        value,
        engine,
        success,
        error,
        freed_bytes=freed.freed_bytes,
        size_after_bytes=freed.size_after_bytes,
    )
    # The one apply path logs its own outcome here, after the finalizer has the
    # verification verdict. A failed log write must never turn a working apply
    # into a failed one; `record_apply` swallows its own I/O errors.
    operation_log.record_apply(
        setting,
        response,
        int((time.perf_counter() - started) * 1000),
        ran=will_run,
    )
    return response
