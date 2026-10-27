"""How many setting applies this process is running, for the bench scheduler.

The counter lives below both layers that use it. `api.routes.settings_apply`
counts an apply for its whole duration and `benchmark.scheduler` reads the count
before starting a bench; keeping it here is what lets the scheduler answer the
question without importing a FastAPI route module — and the whole API layer that
module drags in — into a daemon that does not need it.

The Windows mutex alone cannot answer it: a mutex is owned by the thread that
took it, and a bulk apply runs on sixteen pool threads while the scheduler asks
from its own. So the apply side keeps this counter, and the scheduler reads it
live rather than mirroring it — a second copy of the count would go stale
exactly when it mattered.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_in_flight = 0
_in_flight_guard = threading.Lock()


def applies_in_flight() -> int:
    """How many applies are running right now — the scheduler's other guard."""
    with _in_flight_guard:
        return _in_flight


@contextmanager
def apply_in_flight() -> Iterator[None]:
    """Count one apply for its whole duration, including the wait for the bench.

    The count is taken *before* that wait. Counting after left a window: the
    scheduler read zero applies, the apply side saw the lock free, and both went
    ahead — a bench measuring a machine halfway between two states.
    """
    global _in_flight
    with _in_flight_guard:
        _in_flight += 1
    try:
        yield
    finally:
        with _in_flight_guard:
            _in_flight -= 1
