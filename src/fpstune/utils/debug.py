"""Debug utilities for fpstune.

Enable debug mode by setting FPSTUNE_DEBUG=1 environment variable.
This provides detailed logging for troubleshooting issues.

With the flag set, and only then, entries are kept in memory for the debug API
and written to four rotating files:
- debug.log - All debug entries (JSON format)
- hardware.log - Hardware detection logs
- settings.log - Settings detection/apply logs
- powershell.log - PowerShell command execution logs

They live under the repository's ``logs/`` when running from a checkout and
under ``%USERPROFILE%\\.fpstune\\logs`` when frozen, because a packaged build
has no repository and an elevated one has no trustworthy working directory.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TypeVar

# Check if debug mode is enabled (for console output)
DEBUG_ENABLED = os.environ.get("FPSTUNE_DEBUG", "").lower() in ("1", "true", "yes", "on")

MAX_DEBUG_ENTRIES = 500

# Debug log storage for the (debug-gated) API.
#
# A deque with a maxlen rather than a list that is re-sliced: the old form
# rebound a module global from whatever thread got there first, so two detection
# workers appending at once could drop each other's entry — and every append
# copied up to 500 dicts.
#
# Only populated when DEBUG_ENABLED, because only a debug-gated route can read
# it. The entries carry full command text, command output and the hardware
# identifiers that output contains; with the flag off nothing can ever fetch
# them, so keeping 500 of them resident in an elevated process buys nothing and
# leaves identifiers in memory for the life of the run.
_debug_entries: deque[dict[str, Any]] = deque(maxlen=MAX_DEBUG_ENTRIES)

# File logging configuration
_LOG_DIR: Path | None = None
_log_dir_lock = threading.Lock()
_file_lock = threading.Lock()
_log_writers: dict[str, logging.Logger] = {}

# Each component file rotates at the same size the API log does
# (`utils/logger.py`), because an elevated session can run for days and these
# files are only cleared at process start.
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3

# Log files to clear on startup
_LOG_FILES_TO_CLEAR = [
    "debug.log",
    "hardware.log",
    "settings.log",
    "powershell.log",
]

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class DebugContext:
    """Context for a debug operation."""

    operation: str
    component: str
    start_time: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_step(self, step: str, data: Any = None) -> None:
        """Add a step to the debug context."""
        self.steps.append(
            {
                "step": step,
                "data": _safe_serialize(data),
                "elapsed_ms": int((time.time() - self.start_time) * 1000),
            }
        )

    def add_error(self, error: str) -> None:
        """Add an error to the debug context."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning to the debug context."""
        self.warnings.append(warning)

    def set_detail(self, key: str, value: Any) -> None:
        """Set a detail value."""
        self.details[key] = _safe_serialize(value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation": self.operation,
            "component": self.component,
            "duration_ms": int((time.time() - self.start_time) * 1000),
            "details": self.details,
            "steps": self.steps,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": datetime.now().isoformat(),
        }


def _resolve_log_dir() -> Path:
    """Decide where this build's debug logs belong.

    A frozen build's ``__file__`` lives under the PyInstaller extraction
    directory, so climbing parents for ``pyproject.toml`` never matches and the
    old fallback was ``Path.cwd() / "logs"`` — which for an executable that
    requests elevation is whatever directory the shell handed it, commonly
    ``System32``. The README promises fpstune writes nothing outside
    ``%USERPROFILE%\\.fpstune``, so a packaged build keeps its logs there.

    A source checkout still logs beside its own tree, where a developer expects
    to find them; the user profile is the fallback there too, because the
    working directory is no better a guess from source than it is when frozen.
    """
    from fpstune.utils.config import get_config_dir
    from fpstune.utils.runtime import is_frozen

    if not is_frozen():
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / "pyproject.toml").exists():
                return parent / "logs"

    return get_config_dir() / "logs"


def _get_log_dir() -> Path:
    """Get or create the logs directory.

    On first call per session, clears existing log files for a fresh start. The
    whole resolve-create-clear sequence is under one lock: read and assignment
    of the module global were separate steps, so two threads logging at once
    could both run the clear — the second one deleting what the first had
    already started writing.
    """
    global _LOG_DIR

    if _LOG_DIR is not None:
        return _LOG_DIR

    with _log_dir_lock:
        if _LOG_DIR is not None:
            return _LOG_DIR

        log_dir = _resolve_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        for log_file in _LOG_FILES_TO_CLEAR:
            log_path = log_dir / log_file
            if log_path.exists():
                with contextlib.suppress(OSError):
                    log_path.unlink()

        _LOG_DIR = log_dir

    return _LOG_DIR


def _log_writer(log_dir: Path, filename: str) -> logging.Logger:
    """A rotating writer for one component file, created once per file.

    ``RotatingFileHandler`` rather than ``open(..., "a")``: the files are only
    cleared at process start, so a long elevated session grew them without
    bound. Same size and backup count as the API log in ``utils/logger.py``.
    """
    writer = _log_writers.get(filename)
    if writer is not None:
        return writer

    writer = logging.getLogger(f"fpstune.debugfile.{filename}")
    writer.setLevel(logging.DEBUG)
    writer.propagate = False
    for handler in list(writer.handlers):
        writer.removeHandler(handler)
    file_handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    writer.addHandler(file_handler)
    _log_writers[filename] = writer
    return writer


def _write_to_file(component: str, message: str, data: dict[str, Any] | None = None) -> None:
    """Write a log entry to a component-specific file and the main debug.log.

    Each file is written through a rotating handler, so the entry lands
    immediately (logging flushes per record) and the file cannot grow unbounded
    across a long session.

    File logging is gated on DEBUG_ENABLED: when FPSTUNE_DEBUG is unset, no
    PowerShell command text or hardware detection output (which can carry
    MAC/IP/GUID identifiers) is persisted to disk. In-memory entries for the
    (debug-gated) API still populate via the callers.
    """
    if not DEBUG_ENABLED:
        return

    try:
        log_dir = _get_log_dir()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Determine which files to write to
        # Map components to log files
        component_map = {
            "hardware": "hardware.log",
            "network": "hardware.log",
            "audio": "hardware.log",
            "detect": "settings.log",
            "settings": "settings.log",
            "executor": "settings.log",
            "powershell": "powershell.log",
            "registry": "settings.log",
            "nvprofile": "settings.log",
            "bcdedit": "settings.log",
        }
        log_file = component_map.get(component, "debug.log")

        with _file_lock:
            if data:
                line = f"[{timestamp}] [{component.upper()}] {message} | {json.dumps(data, ensure_ascii=False, default=str)}"
            else:
                line = f"[{timestamp}] [{component.upper()}] {message}"
            _log_writer(log_dir, log_file).debug(line)

            # Also write to main debug.log (JSON format for easy parsing)
            entry = {
                "timestamp": timestamp,
                "component": component,
                "message": message,
                "data": data,
            }
            _log_writer(log_dir, "debug.log").debug(
                json.dumps(entry, ensure_ascii=False, default=str)
            )

    except Exception:
        pass  # Never fail on logging


def _safe_serialize(value: Any) -> Any:
    """Safely serialize a value for JSON output."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value[:50]]  # Limit list size
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in list(value.items())[:50]}
    if hasattr(value, "__dict__"):
        return {k: _safe_serialize(v) for k, v in list(vars(value).items())[:20]}
    return str(value)[:500]  # Truncate long strings


def _record_entry(entry: dict[str, Any]) -> None:
    """Keep one entry for the debug API, and only when that API can be reached.

    The single door into ``_debug_entries``: gating it here rather than at each
    caller is what stops the next one from forgetting.
    """
    if not DEBUG_ENABLED:
        return
    _debug_entries.append(entry)


def _add_debug_entry(ctx: DebugContext) -> None:
    """Add a debug entry to the global storage."""
    _record_entry(ctx.to_dict())


def get_debug_entries(limit: int = 100, component: str | None = None) -> list[dict[str, Any]]:
    """Get debug entries, optionally filtered by component."""
    entries = list(_debug_entries)
    if component:
        entries = [e for e in entries if e.get("component") == component]
    return list(reversed(entries[-limit:]))


def clear_debug_entries() -> None:
    """Clear all debug entries."""
    _debug_entries.clear()


def get_logger(name: str) -> logging.Logger:
    """Get a debug logger with the given name."""
    logger = logging.getLogger(f"fpstune.debug.{name}")

    if DEBUG_ENABLED and not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "\033[36m[DEBUG]\033[0m \033[90m%(name)s\033[0m | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    return logger


@contextmanager
def debug_context(operation: str, component: str) -> Generator[DebugContext, None, None]:
    """Context manager for debug operations.

    Usage:
        with debug_context("detect_monitors", "hardware") as ctx:
            ctx.add_step("Starting WMI query")
            # ... do work ...
            ctx.set_detail("monitors_found", 2)
    """
    ctx = DebugContext(operation=operation, component=component)
    logger = get_logger(component)

    if DEBUG_ENABLED:
        logger.debug(f">>> {operation} started")

    try:
        yield ctx
    except Exception as e:
        ctx.add_error(f"{type(e).__name__}: {e}")
        if DEBUG_ENABLED:
            logger.error(f"!!! {operation} failed: {e}")
        raise
    finally:
        _add_debug_entry(ctx)
        if DEBUG_ENABLED:
            duration = int((time.time() - ctx.start_time) * 1000)
            logger.debug(f"<<< {operation} completed in {duration}ms")
            if ctx.errors:
                logger.error(f"    Errors: {ctx.errors}")
            if ctx.warnings:
                logger.warning(f"    Warnings: {ctx.warnings}")


def debug_powershell(
    command: str, output: str, success: bool, component: str = "powershell"
) -> None:
    """Log PowerShell command execution for debugging.

    Entries are kept in memory for the debug API, on disk, and on the console
    only when DEBUG_ENABLED=True — the command text and its output carry the
    machine's identifiers, and with debug off there is no reader for any of
    the three.
    """
    if not DEBUG_ENABLED:
        return

    _record_entry(
        {
            "operation": "powershell_execute",
            "component": component,
            "timestamp": datetime.now().isoformat(),
            "details": {
                "command": command[:2000],
                "output": output[:2000],
                "success": success,
            },
            "steps": [],
            "errors": [] if success else [output[:500]],
            "warnings": [],
            "duration_ms": 0,
        }
    )

    # Write to the log file (itself gated on DEBUG_ENABLED)
    status_str = "OK" if success else "FAIL"
    cmd_short = command.replace("\n", " ")[:300]
    out_short = output.replace("\n", " | ")[:500] if output else "(empty)"
    _write_to_file(
        "powershell",
        f"[{status_str}] {cmd_short}",
        {"output": out_short, "success": success, "component": component},
    )

    # Console output only when debug mode enabled
    if DEBUG_ENABLED:
        logger = get_logger(component)
        cmd_display = command[:500] + "..." if len(command) > 500 else command
        out_display = output[:1000] + "..." if len(output) > 1000 else output
        status = "\033[32mOK\033[0m" if success else "\033[31mFAIL\033[0m"
        logger.debug(f"PowerShell [{status}]")
        logger.debug(f"  Command: {cmd_display.replace(chr(10), ' ')[:200]}")
        logger.debug(f"  Output: {out_display.replace(chr(10), ' | ')[:300]}")


def debug_function(component: str) -> Callable[[F], F]:
    """Decorator to add debug logging to a function.

    Usage:
        @debug_function("hardware")
        def detect_monitors():
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not DEBUG_ENABLED:
                return func(*args, **kwargs)

            logger = get_logger(component)
            func_name = func.__name__

            # Log function call
            args_repr = ", ".join(
                [repr(a)[:50] for a in args[:5]]
                + [f"{k}={repr(v)[:50]}" for k, v in list(kwargs.items())[:5]]
            )
            logger.debug(f">>> {func_name}({args_repr})")

            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = int((time.time() - start) * 1000)
                result_repr = repr(result)[:200] if result is not None else "None"
                logger.debug(f"<<< {func_name} returned in {duration}ms: {result_repr}")
                return result
            except Exception as e:
                duration = int((time.time() - start) * 1000)
                logger.error(f"!!! {func_name} failed in {duration}ms: {e}")
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


def debug_log(component: str, message: str, data: Any = None) -> None:
    """Log a debug message with optional data.

    Nothing is kept, written or printed unless DEBUG_ENABLED: the message and
    its data are detection output, which carries adapter GUIDs, MAC addresses
    and paths, and no route can read them back with the flag off. Returning
    first also keeps ``_safe_serialize`` off the detection hot path.
    """
    if not DEBUG_ENABLED:
        return

    serialized_data = _safe_serialize(data) if data is not None else None
    _record_entry(
        {
            "operation": "debug_log",
            "component": component,
            "timestamp": datetime.now().isoformat(),
            "details": {
                "message": message,
                "data": serialized_data,
            },
            "steps": [],
            "errors": [],
            "warnings": [],
            "duration_ms": 0,
        }
    )

    # Write to the log file (itself gated on DEBUG_ENABLED)
    _write_to_file(component, message, {"data": serialized_data} if serialized_data else None)

    # Console output only when debug mode enabled
    if DEBUG_ENABLED:
        logger = get_logger(component)
        if data is not None:
            data_repr = repr(serialized_data)[:500]
            logger.debug(f"{message}: {data_repr}")
        else:
            logger.debug(message)


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return DEBUG_ENABLED


def get_debug_status() -> dict[str, Any]:
    """Get current debug status and statistics."""
    # One snapshot for the whole report: the deque is appended to from detection
    # threads, so counting it twice can describe two different buffers.
    entries = list(_debug_entries)
    return {
        "enabled": DEBUG_ENABLED,
        "env_var": os.environ.get("FPSTUNE_DEBUG", "(not set)"),
        "entry_count": len(entries),
        "max_entries": MAX_DEBUG_ENTRIES,
        "components": list({e.get("component", "") for e in entries}),
        "recent_errors": [
            {
                "operation": e.get("operation"),
                "component": e.get("component"),
                "errors": e.get("errors"),
                "timestamp": e.get("timestamp"),
            }
            for e in reversed(entries[-50:])
            if e.get("errors")
        ][:10],
    }
