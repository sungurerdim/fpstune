"""One adapter restart per burst of writes, not one per property.

``Set-NetAdapterAdvancedProperty`` and its siblings restart the adapter after
every call unless told ``-NoRestart``. A bulk apply touches a dozen properties
of the same adapter, so it dropped the link a dozen times, each for several
seconds, and a later write could land on an adapter that was still coming back.

Every per-adapter write now runs with ``-NoRestart`` (or writes a key the
driver only reads at start) and asks for a restart here instead. The request
is debounced per adapter: the restart runs once the adapter has had no write
for ``QUIET_SECONDS``, so a single apply restarts it once, and a bulk run that
writes ten of its properties also restarts it once.

The written value is in the registry the moment the cmdlet returns, so the
read-back verify that follows an apply is unaffected; the restart is what makes
the driver use it.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from fpstune.utils.logger import get_logger

logger = get_logger()

# Long enough to cover the gap between two sequential applies (each starts its
# own PowerShell), short enough that a single change is live within seconds.
QUIET_SECONDS = 4.0

_lock = threading.Lock()
_pending: dict[int, threading.Timer] = {}


def _restart_now(ifindex: int) -> None:
    from fpstune.utils.powershell import run_powershell
    from fpstune.utils.process_watch import CHANGE

    with _lock:
        _pending.pop(ifindex, None)
    ok, output = run_powershell(
        # Restart-NetAdapter takes no -InterfaceIndex; the bare Get-NetAdapter does.
        f"try {{ Get-NetAdapter -InterfaceIndex {ifindex} -ErrorAction Stop | "
        "Restart-NetAdapter -Confirm:$false -ErrorAction Stop; 'ok' } "
        "catch { 'error:' + $_.Exception.Message }",
        CHANGE,
        component="adapter_restart",
    )
    text = (output or "").strip()
    if not ok or text.startswith("error:"):
        logger.warning("Restarting network adapter %d failed: %s", ifindex, text)
    else:
        logger.info("Network adapter %d restarted to load new settings", ifindex)


def schedule_adapter_restart(
    ifindex: object,
    *,
    quiet_seconds: float = QUIET_SECONDS,
    restart: Callable[[int], None] = _restart_now,
) -> bool:
    """Restart adapter ``ifindex`` once it has been quiet for ``quiet_seconds``.

    A second request for the same adapter before the restart runs replaces the
    first, so a burst of writes ends in exactly one restart. Returns False when
    ``ifindex`` is not an interface index.
    """
    try:
        index = int(str(ifindex))
    except ValueError:
        return False
    if index <= 0:
        return False
    if sys.platform != "win32" and restart is _restart_now:
        return False

    timer = threading.Timer(quiet_seconds, restart, args=(index,))
    timer.daemon = True
    with _lock:
        previous = _pending.pop(index, None)
        if previous is not None:
            previous.cancel()
        _pending[index] = timer
    timer.start()
    return True


def flush_pending(restart: Callable[[int], None] = _restart_now) -> list[int]:
    """Run every restart still waiting out its quiet period, now.

    Called at shutdown: the timers are daemon threads, so a change made in the
    last few seconds before exit would otherwise sit in the registry unloaded
    until the next reboot. Returns the adapters restarted.
    """
    with _lock:
        waiting = list(_pending.items())
        _pending.clear()
    for _, timer in waiting:
        timer.cancel()
    for index, _ in waiting:
        restart(index)
    return [index for index, _ in waiting]
