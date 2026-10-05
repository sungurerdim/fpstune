"""System Restore Point management for fpstune."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from fpstune.utils import process_watch
from fpstune.utils.powershell import escape_single_quoted
from fpstune.utils.system_tools import powershell_exe

logger = logging.getLogger(__name__)

# Descriptions reach this module from an HTTP query parameter, so they are
# attacker-shaped: bound the length and drop control characters before any
# command string is built from them.
_MAX_DESCRIPTION_LENGTH = 128


def _sanitize_description(description: str) -> str:
    """Reduce a caller-supplied description to printable, bounded text."""
    cleaned = "".join(ch for ch in description if ch.isprintable())
    return cleaned[:_MAX_DESCRIPTION_LENGTH].strip() or "fpstune backup"


def system_restore_enabled() -> bool:
    """Return False when System Restore / System Protection is off.

    The registry read, not the PowerShell probe: this runs on the pre-apply hot
    path, where a subprocess would cost more than the answer is worth. Windows
    11 ships with System Protection OFF by default, in which case
    Checkpoint-Computer fails ("ServiceDisabled"). RPSessionInterval == 0 is the
    reliable "protection off" signal; the legacy srservice Start==4 check is
    kept as a fallback for older systems where srservice still exists.
    """
    if sys.platform != "win32":
        return False

    import winreg

    # System Protection state: RPSessionInterval == 0 → disabled.
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore",
        ) as k:
            interval, _ = winreg.QueryValueEx(k, "RPSessionInterval")
            if int(interval) == 0:
                return False
    except OSError:
        pass  # value/key absent → fall through to the service check

    # Legacy service check: Start == 4 means the service is Disabled.
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\srservice",
        ) as k:
            start_type, _ = winreg.QueryValueEx(k, "Start")
            return int(start_type) != 4
    except OSError:
        return True  # key absent (modern Windows) → assume available


# The newest point's sequence number before and after the checkpoint is the only
# locale-independent proof one was made. Windows refuses a second point inside
# SystemRestorePointCreationFrequency (24 h by default) with nothing but a
# *warning* and exit code 0, so success-by-exit-code reported points that were
# never created. Checkpoint-Computer takes a volume shadow copy, which routinely
# runs past a minute on a busy disk — the old 30 s and 120 s ceilings killed it
# mid-snapshot — so it runs under the stall rule instead (utils.process_watch).
_CHECKPOINT_SCRIPT = (
    "$last = { @(Get-ComputerRestorePoint -EA SilentlyContinue | "
    "Sort-Object SequenceNumber | Select-Object -Last 1) }; "
    "$b = & $last; $before = if ($b.Count) { [int64]$b[0].SequenceNumber } else { -1 }; "
    "try { Checkpoint-Computer -Description '__DESCRIPTION__' "
    "-RestorePointType 'MODIFY_SETTINGS' -WarningAction SilentlyContinue -EA Stop } "
    "catch { 'error|' + $_.Exception.Message; exit }; "
    "$a = & $last; "
    "if ($a.Count -and [int64]$a[0].SequenceNumber -gt $before) { 'created|' + $a[0].SequenceNumber } "
    "elseif ($a.Count) { 'recent|' + $a[0].ConvertToDateTime($a[0].CreationTime).ToString('yyyy-MM-dd HH:mm') } "
    "else { 'error|no restore point exists after the checkpoint' }"
)


@dataclass(frozen=True)
class RestoreOutcome:
    """What a checkpoint actually achieved, in words a user can read.

    ``kind`` is ``created``, ``recent`` (Windows already holds one from inside
    its once-a-day window), ``off`` (System Protection disabled), ``stalled``,
    ``error`` or ``unavailable``.
    """

    kind: str
    message: str

    @property
    def protected(self) -> bool:
        """True when a restore point from before the change exists."""
        return self.kind in ("created", "recent")


def checkpoint(description: str) -> RestoreOutcome:
    """Create a MODIFY_SETTINGS restore point and report what really happened."""
    from fpstune.utils.logger import log_activity

    if sys.platform != "win32":
        return RestoreOutcome("unavailable", "System Restore is only available on Windows")
    if not system_restore_enabled():
        outcome = RestoreOutcome(
            "off", "Restore point skipped: System Protection is turned off on this machine"
        )
        log_activity(outcome.message, "warning")
        return outcome

    safe = escape_single_quoted(_sanitize_description(description))
    script = _CHECKPOINT_SCRIPT.replace("__DESCRIPTION__", safe)
    log_activity("Creating a restore point (Windows can take minutes)")
    started = time.monotonic()
    try:
        result = process_watch.run(
            [powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            process_watch.CHANGE,
        )
    except subprocess.TimeoutExpired as exc:
        outcome = RestoreOutcome("stalled", f"Restore point not confirmed: {exc}")
        log_activity(outcome.message, "warning")
        return outcome
    except OSError as exc:
        outcome = RestoreOutcome("error", f"Restore point not created: {exc}")
        log_activity(outcome.message, "warning")
        return outcome

    elapsed = time.monotonic() - started
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    kind, _, detail = (lines[-1] if lines else "").partition("|")
    if kind == "created":
        outcome = RestoreOutcome("created", f"Restore point created ({elapsed:.0f}s)")
        log_activity(outcome.message, "success")
        return outcome
    if kind == "recent":
        outcome = RestoreOutcome(
            "recent",
            f"No new restore point: Windows already holds one from {detail} and allows one a day",
        )
        log_activity(outcome.message, "success")
        return outcome
    stderr = (result.stderr or "").strip().splitlines()
    reason = detail or (stderr[0] if stderr else "unknown error")
    outcome = RestoreOutcome("error", f"Restore point not created: {reason}")
    log_activity(outcome.message, "warning")
    return outcome


_session_lock = threading.Lock()
_session_outcome: RestoreOutcome | None = None


def ensure_session_restore_point() -> RestoreOutcome:
    """Make sure a restore point precedes this session's first change; block until it does.

    It used to be fire-and-forget: a daemon thread started the checkpoint and the
    apply ran alongside it, so the snapshot could land *after* fpstune's writes and
    roll back to nothing. Now the first mutating request waits for the outcome,
    and every later one returns it at once — one point per session, not one per
    click, and concurrent requests queue on the lock rather than racing a second.
    The apply proceeds whatever the outcome; it is logged so the terminal says
    what protection the change actually has.
    """
    global _session_outcome
    with _session_lock:
        if _session_outcome is None:
            _session_outcome = checkpoint("fpstune pre-apply")
        return _session_outcome


class RestorePointManager:
    """Windows System Restore Point management.

    Every point this manager creates is a MODIFY_SETTINGS one, and that is not
    a default: fpstune installs nothing and uninstalls nothing, so the other
    Checkpoint-Computer types describe an event that never happens here.
    """

    def __init__(self) -> None:
        """Initialize RestorePointManager."""
        self._available = sys.platform == "win32"

    @property
    def is_available(self) -> bool:
        """Check if restore point operations are available."""
        return self._available

    def create_restore_point(
        self, description: str = "fpstune optimization backup"
    ) -> RestoreOutcome:
        """Create a system restore point now, the same way the session one is made."""
        return checkpoint(description)
