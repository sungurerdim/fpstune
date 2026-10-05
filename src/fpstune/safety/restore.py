"""System Restore Point management for fpstune."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time

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


# Checkpoint-Computer takes a volume shadow copy, which routinely runs past a
# minute on a busy disk. The old 30 s ceiling killed it mid-snapshot and logged
# "skipped" on exactly the machines that needed the most time.
_SESSION_POINT_TIMEOUT_S = 600

# The newest point's sequence number before and after the checkpoint is the only
# locale-independent proof one was made. Windows refuses a second point inside
# SystemRestorePointCreationFrequency (24 h by default) with nothing but a
# *warning* and exit code 0, so success-by-exit-code reported points that were
# never created.
_SESSION_POINT_SCRIPT = (
    "$last = { @(Get-ComputerRestorePoint -EA SilentlyContinue | "
    "Sort-Object SequenceNumber | Select-Object -Last 1) }; "
    "$b = & $last; $before = if ($b.Count) { [int64]$b[0].SequenceNumber } else { -1 }; "
    "try { Checkpoint-Computer -Description 'fpstune pre-apply' "
    "-RestorePointType MODIFY_SETTINGS -WarningAction SilentlyContinue -EA Stop } "
    "catch { 'error|' + $_.Exception.Message; exit }; "
    "$a = & $last; "
    "if ($a.Count -and [int64]$a[0].SequenceNumber -gt $before) { 'created|' + $a[0].SequenceNumber } "
    "elseif ($a.Count) { 'recent|' + $a[0].ConvertToDateTime($a[0].CreationTime).ToString('yyyy-MM-dd HH:mm') } "
    "else { 'error|no restore point exists after the checkpoint' }"
)

_session_lock = threading.Lock()
_session_outcome: str | None = None


def ensure_session_restore_point() -> str:
    """Make sure a restore point precedes this session's first change; block until it does.

    It used to be fire-and-forget: a daemon thread started the checkpoint and the
    apply ran alongside it, so the snapshot could land *after* fpstune's writes and
    roll back to nothing. Now the first mutating request waits for the outcome,
    and every later one returns it at once — one point per session, not one per
    click, and concurrent requests queue on the lock rather than racing a second.

    Returns one of ``created``, ``recent`` (Windows already holds one from within
    its creation window), ``off`` (System Protection disabled), ``timeout``,
    ``error`` or ``unavailable``. The apply proceeds in every case; the outcome is
    logged so the terminal says what protection the change actually has.
    """
    global _session_outcome
    with _session_lock:
        if _session_outcome is not None:
            return _session_outcome
        _session_outcome = _create_session_point()
        return _session_outcome


def _create_session_point() -> str:
    from fpstune.utils.logger import log_activity

    if sys.platform != "win32":
        return "unavailable"
    if not system_restore_enabled():
        log_activity(
            "Restore point skipped: System Protection is turned off on this machine",
            "warning",
        )
        return "off"

    log_activity("Creating a restore point before the first change (this can take minutes)")
    started = time.monotonic()
    try:
        result = subprocess.run(
            [
                powershell_exe(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _SESSION_POINT_SCRIPT,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_SESSION_POINT_TIMEOUT_S,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        log_activity(
            f"Restore point not confirmed: Windows did not finish within "
            f"{_SESSION_POINT_TIMEOUT_S // 60} minutes",
            "warning",
        )
        return "timeout"
    except OSError as exc:
        log_activity(f"Restore point not created: {exc}", "warning")
        return "error"

    elapsed = time.monotonic() - started
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    kind, _, detail = (lines[-1] if lines else "").partition("|")
    if kind == "created":
        log_activity(f"Restore point created ({elapsed:.0f}s)", "success")
        return "created"
    if kind == "recent":
        log_activity(
            f"Restore point not needed: Windows already holds one from {detail}, "
            "inside its once-a-day limit",
            "success",
        )
        return "recent"
    stderr = (result.stderr or "").strip().splitlines()
    reason = detail or (stderr[0] if stderr else "unknown error")
    log_activity(f"Restore point not created: {reason}", "warning")
    return "error"


class RestorePointManager:
    """Windows System Restore Point management.

    Every point this manager creates is a MODIFY_SETTINGS one, and that is not
    a default: fpstune installs nothing and uninstalls nothing, so the other
    Checkpoint-Computer types describe an event that never happens here. The
    type is therefore fixed at the two call sites rather than passed in.
    """

    def __init__(self) -> None:
        """Initialize RestorePointManager."""
        self._available = sys.platform == "win32"

    @property
    def is_available(self) -> bool:
        """Check if restore point operations are available."""
        return self._available

    def create_restore_point(self, description: str = "fpstune optimization backup") -> bool:
        """Create a system restore point.

        Args:
            description: Description for the restore point.

        Returns:
            True if restore point was created successfully.
        """
        if not self._available:
            return False

        try:
            # Use PowerShell to create restore point (requires admin privileges).
            # The description goes into a SINGLE-quoted literal: a double-quoted
            # one evaluates $(...) without needing a quote break, which turned a
            # bare query parameter into elevated code execution.
            safe_description = escape_single_quoted(_sanitize_description(description))
            ps_script = f"""
            [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
            Checkpoint-Computer -Description '{safe_description}' -RestorePointType 'MODIFY_SETTINGS'
            """

            result = subprocess.run(
                [powershell_exe(), "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=120,  # Restore points can take a while
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )

            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
