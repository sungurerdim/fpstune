"""One concise, root-cause-tagged log for everything fpstune does to a machine.

Why this exists next to ``logging``:

* The API log is a stream of framework and command noise. A user asking "which
  tweak failed and why" cannot read it, and the debug log is opt-in, is cleared
  at start, and carries raw command text and identifiers.
* The activity journal is in memory and dies with the process. That is the right
  default for values (C6), not for the *outcome* of an apply.

So this module writes one line per operation, per session, under
``~/.fpstune/logs/operations.log``. A line names the setting, the phase, the
outcome, the duration and, for a failure, a classified root cause and a one-line
hint. It deliberately does **not** store a history of values: it stores what
fpstune did and how it ended. A verification failure is the one place the
expected and observed values are written, because that pair is the evidence the
user is asking for; they are the values the row already shows.

Format (one line, pipe-separated, no colour, no newlines inside a field)::

    2026-10-20T20:30:00+03:00 | APPLY | failed | 1.2s | network:7:eee |
    verification_mismatch | expected=Enabled observed=Disabled |
    hint=apply wrote, but detect read a different value; check the target

The file rotates at session start: the previous ``operations.log`` becomes
``operations-YYYYmmdd-HHMMSS.log`` and the last five are kept. The current run is
always ``operations.log`` so a user can attach it without hunting.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

_MAX_REASON = 600
_MAX_FIELD = 300
_MAX_BACKUPS = 5

# Root causes, in the order the classifier tests them. The names are the
# vocabulary the log and the UI share; do not rename one without a test.
PERMISSION = "permission"
GAME_RUNNING = "game_running"
ADAPTER_BUSY = "adapter_busy"
VERIFICATION_MISMATCH = "verification_mismatch"
PARTIAL = "partial"
PENDING_UPDATE = "pending_update"
TIMEOUT = "timeout"
UNAVAILABLE = "unavailable"
COMMAND_REJECTED = "command_rejected"
UNKNOWN = "unknown"

_HINTS: dict[str, str] = {
    PERMISSION: "run elevated; a protected key can refuse even an administrator",
    GAME_RUNNING: "close the game/launcher; it rewrites its config on exit",
    ADAPTER_BUSY: "adapter restart in progress; retry after it returns",
    VERIFICATION_MISMATCH: (
        "apply wrote but detect read a different value; check the target and OS deferral"
    ),
    PARTIAL: "the target state landed; a secondary plan or copy did not",
    PENDING_UPDATE: "finish the pending Windows update or restart, then retry",
    TIMEOUT: "the command hit the stall rule; check the tool and its process",
    UNAVAILABLE: "feature, game or service is absent here; not a failure",
    COMMAND_REJECTED: "the value or command was rejected before it reached the target",
    UNKNOWN: "no classified cause; attach the line and the command's own output",
}

# Turkish and English text, because Windows prints its own refusal in the system
# language. These are not parsed to make a decision — the decision is already a
# failure; this only labels it for the reader.
_PERMISSION = re.compile(
    # "izin verilmiyor" is ASCII and is the tail of Windows' Turkish refusal;
    # the surrounding words contain Turkish letters the C4 gate forbids in
    # shipped source, so the stable ASCII phrase is what is matched.
    r"access is denied|izin verilmiyor|requested registry access"
    r"|requires elevation|run as administrator|administrator privileges|0x5\b",
    re.IGNORECASE,
)
_GAME_RUNNING = re.compile(r"is running|keeps its settings in memory|close the game", re.IGNORECASE)
_ADAPTER = re.compile(
    r"not back within|restart(?:ing)? (?:the )?(?:network )?adapter|adapter .*restart",
    re.IGNORECASE,
)
_PENDING_UPDATE = re.compile(
    r"pending update|update is pending|update is installing|pending or installing"
    r"|restart to finish|0x800f0975",
    re.IGNORECASE,
)
_TIMEOUT = re.compile(r"timed out|timeout|\bstalled\b|stall rule|deadline", re.IGNORECASE)
_UNAVAILABLE = re.compile(
    r"not installed|not found|not available|not supported|not applicable|not_installed"
    r"|not_supported|not_available",
    re.IGNORECASE,
)
_REJECTED = re.compile(
    r"verification failed|not valid|rejected|requires a|cannot convert|does not match"
    r"|outside|invalid",
    re.IGNORECASE,
)


def classify_error(reason: str | None) -> str:
    """A stable cause for a failure message, or ``unknown``.

    The order is load-bearing: a permission denial often contains "cannot", and a
    verification failure often contains "not valid"; classification must choose
    the concrete cause, not the first generic word.
    """
    text = (reason or "").strip()
    if not text:
        return UNKNOWN
    if _PERMISSION.search(text):
        return PERMISSION
    if _GAME_RUNNING.search(text):
        return GAME_RUNNING
    if _ADAPTER.search(text):
        return ADAPTER_BUSY
    if "verification failed" in text.casefold():
        return VERIFICATION_MISMATCH
    if "applied, but" in text.casefold():
        return PARTIAL
    if _PENDING_UPDATE.search(text):
        return PENDING_UPDATE
    if _TIMEOUT.search(text):
        return TIMEOUT
    if _UNAVAILABLE.search(text):
        return UNAVAILABLE
    if _REJECTED.search(text):
        return COMMAND_REJECTED
    return UNKNOWN


def hint_for(kind: str) -> str:
    """The one-line next step for a cause."""
    return _HINTS.get(kind, _HINTS[UNKNOWN])


def _clean(value: object, limit: int = _MAX_FIELD) -> str:
    """One field: no line breaks, no pipes that break the format, bounded."""
    text = str(value).replace("\r", " ").replace("\n", " / ").replace("|", "/")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


@dataclass
class OperationLog:
    """Session-scoped, thread-safe, append-only operation log."""

    path: Path | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _started: bool = False
    _counts: Counter[str] = field(default_factory=Counter, repr=False)
    _last_error: str | None = None

    def start_session(self, path: Path | None = None, header: str | None = None) -> Path:
        """Open this run's file, rotate the previous one, write the header.

        ``path`` is for tests and for a caller that has already resolved the
        directory; the default is ``~/.fpstune/logs/operations.log``. Rotation is
        best-effort: a file locked by another process is kept as-is rather than
        failing the session.
        """
        with self._lock:
            if path is not None:
                self.path = path
            if self.path is None:
                from fpstune.utils import user_paths

                self.path = user_paths.fpstune_home() / "logs" / "operations.log"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                rotated = self.path.with_name(f"operations-{stamp}.log")
                with contextlib.suppress(OSError):
                    self.path.replace(rotated)
            self._prune()
            self._counts.clear()
            self._last_error = None
            self._started = True
            try:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(
                        f"# fpstune operations | {datetime.now().astimezone().isoformat(timespec='seconds')}"
                        f" | {_clean(header or os.environ.get('FPSTUNE_SESSION_LABEL', 'session'))}\n"
                    )
            except OSError:
                pass
            return self.path

    def _prune(self) -> None:
        """Keep the newest ``_MAX_BACKUPS`` rotated files."""
        if self.path is None:
            return
        try:
            # The name carries a microsecond timestamp, so it orders the files
            # without asking the filesystem. mtime is not stable enough: a touch
            # or a copy can make an older run look newer, and pruning then keeps
            # the wrong one.
            backups = sorted(self.path.parent.glob("operations-*.log"), key=lambda p: p.name)
        except OSError:
            return
        for old in backups[:-_MAX_BACKUPS]:
            with contextlib.suppress(OSError):
                old.unlink()

    def _ensure(self) -> None:
        if not self._started:
            self.start_session()

    def write(
        self,
        event: str,
        outcome: str,
        setting_id: str = "",
        *,
        duration_ms: int | None = None,
        error_kind: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        **fields: Any,
    ) -> None:
        """Append one line; never raise into the operation it is describing."""
        kind = error_kind or (classify_error(reason) if reason else None)
        parts = [
            datetime.now().astimezone().isoformat(timespec="seconds"),
            _clean(event, 20).upper(),
            _clean(outcome, 20).lower(),
        ]
        if duration_ms is not None:
            parts.append(f"{duration_ms / 1000:.1f}s")
        if setting_id:
            parts.append(_clean(setting_id, 120))
        if kind and outcome.lower() in ("failed", "partial", "blocked"):
            parts.append(kind)
        if reason:
            parts.append(_clean(reason, _MAX_REASON))
        if detail:
            parts.append(_clean(detail, _MAX_REASON))
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{_clean(key, 40)}={_clean(value, _MAX_FIELD)}")
        # A run/scan summary is a count, not a failure; a hint on it would read
        # as "the whole run has a cause" and would be repeated under the rows.
        if (
            kind
            and outcome.lower() in ("failed", "partial", "blocked")
            and event.lower() not in ("run", "scan")
        ):
            parts.append(f"hint={hint_for(kind)}")
        line = " | ".join(parts)
        with self._lock:
            self._counts[outcome.lower()] += 1
            if kind:
                self._last_error = kind
            if self.path is None:
                return
            try:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
            except OSError:
                # Logging must never turn a working apply into a failed one.
                pass

    def record_detect(
        self,
        *,
        total: int,
        errors: int,
        not_applicable: int,
        optimized: int,
        not_optimized: int,
        duration_ms: int,
    ) -> None:
        """One summary line for a scan; per-error lines are written beside it."""
        self.write(
            "detect",
            "ok" if errors == 0 else "partial",
            duration_ms=duration_ms,
            total=total,
            errors=errors,
            not_applicable=not_applicable,
            optimized=optimized,
            not_optimized=not_optimized,
        )

    def record_apply(
        self,
        setting: SettingExecutor,
        response: Any,
        duration_ms: int,
        *,
        ran: bool = True,
    ) -> None:
        """One line for the single apply path, with the verification verdict."""
        skipped = bool(getattr(response, "skipped", False)) or not ran
        success = bool(getattr(response, "success", False))
        error = getattr(response, "error", None)
        warnings = list(getattr(response, "warnings", None) or [])
        if skipped:
            outcome = "skipped"
        elif success and warnings:
            outcome = "partial"
        elif success:
            outcome = "ok"
        else:
            outcome = "failed"
        reason = None if outcome == "ok" else (error or ("; ".join(warnings) or None))
        self.write(
            "apply" if ran else "skip",
            outcome,
            setting.id,
            duration_ms=duration_ms,
            reason=reason,
            verified=getattr(response, "verified", None),
            requires_reboot=getattr(response, "requires_reboot", False),
            freed_bytes=getattr(response, "freed_bytes", None),
        )

    def summary(self) -> str:
        """The counts for this session, in one line."""
        with self._lock:
            counts = ", ".join(f"{k}={v}" for k, v in sorted(self._counts.items()))
        return counts or "no operations"

    @property
    def last_error(self) -> str | None:
        """The most recent classified cause, for a caller that wants to show it."""
        with self._lock:
            return self._last_error


# The process-wide log. It is lazy: importing this module never creates a file.
operation_log = OperationLog()
