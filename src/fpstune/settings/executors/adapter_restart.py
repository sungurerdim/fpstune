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

A restart is not over when ``Restart-NetAdapter`` returns: the adapter is gone
from ``Get-NetAdapter`` or Disabled for a moment and a read in that window comes
back empty. So the one restart helper, ``_restart_now``, returns only once the
adapter is back (``wait_until_back``, bounded, with a readable reason when it is
not), and marks the adapter as restarting meanwhile so a read can wait for it
(``wait_for_restarts``) instead of reading mid-restart.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable

from fpstune.utils.logger import get_logger

logger = get_logger()

# Long enough to cover the gap between two sequential applies (each starts its
# own PowerShell), short enough that a single change is live within seconds.
QUIET_SECONDS = 4.0

# An adapter is "back" when Windows lists it and it is enabled: Up, or
# Disconnected (no link, e.g. Wi-Fi not yet associated or a cable unplugged —
# the driver is loaded and every property is readable). Disabled, Not Present
# and the transitional states are the mid-restart window a read must not enter.
READY_STATUSES: tuple[str, ...] = ("Up", "Disconnected")

# Upper bound on one adapter's restart, and how often its status is asked.
SETTLE_TIMEOUT_SECONDS = 30.0
SETTLE_POLL_SECONDS = 0.5

_lock = threading.Lock()
_pending: dict[int, threading.Timer] = {}
# Adapters whose restart is running right now; the event is set when it ends.
_restarting: dict[int, threading.Event] = {}


def adapter_status(ifindex: int) -> str | None:
    """The adapter's ``Get-NetAdapter`` status, or None when it could not be read."""
    from fpstune.utils.powershell import run_powershell

    ok, output = run_powershell(
        f"try {{ [string](Get-NetAdapter -InterfaceIndex {ifindex} -ErrorAction Stop).Status }} "
        "catch { 'error:' + $_.Exception.Message }",
        component="adapter_restart",
    )
    text = (output or "").strip()
    if not ok or not text or text.startswith("error:"):
        return None
    return text.splitlines()[-1].strip()


def wait_until_back(
    ifindex: int,
    *,
    timeout: float = SETTLE_TIMEOUT_SECONDS,
    poll: float = SETTLE_POLL_SECONDS,
    status: Callable[[int], str | None] = adapter_status,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[bool, str]:
    """Wait until adapter ``ifindex`` is back after a restart.

    Returns ``(True, "")`` once its status is in ``READY_STATUSES``, or
    ``(False, reason)`` after ``timeout`` seconds, the reason naming the adapter
    and the last status seen (or that it could not be read at all).
    """
    deadline = clock() + timeout
    last: str | None = None
    while True:
        last = status(ifindex)
        if last in READY_STATUSES:
            return True, ""
        if clock() >= deadline:
            seen = f"last status: {last}" if last else "its status could not be read"
            return False, f"network adapter {ifindex} was not back within {timeout:g} s ({seen})"
        sleep(poll)


def wait_for_restarts(timeout: float = SETTLE_TIMEOUT_SECONDS) -> bool:
    """Wait for every adapter restart running right now; False if one outlasted ``timeout``.

    A read of adapter state calls this first, so it never starts in the middle
    of a restart. A restart that begins after the read has started is not
    covered: the read then fails for that adapter and says so (unknown), it does
    not report a default.
    """
    with _lock:
        running = list(_restarting.values())
    deadline = time.monotonic() + timeout
    return all(event.wait(max(0.0, deadline - time.monotonic())) for event in running)


def _restart_now(ifindex: int) -> None:
    from fpstune.utils.powershell import run_powershell
    from fpstune.utils.process_watch import CHANGE

    done = threading.Event()
    with _lock:
        _pending.pop(ifindex, None)
        _restarting[ifindex] = done
    try:
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
            return
        back, reason = wait_until_back(ifindex)
        if back:
            logger.info("Network adapter %d restarted to load new settings", ifindex)
        else:
            logger.warning("Restarted network adapter %d, but %s", ifindex, reason)
    finally:
        with _lock:
            _restarting.pop(ifindex, None)
        done.set()


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
