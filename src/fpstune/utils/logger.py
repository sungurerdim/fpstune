"""Logging utilities for fpstune."""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fpstune.utils.console import console

# Logger name
LOGGER_NAME = "fpstune"


# ANSI color codes (Windows 10+ and all Unix terminals support these)
class _Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Bright variants
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"


# Palette cycled per setting_id for consistent per-tweak coloring
_TWEAK_COLORS = [
    _Colors.CYAN,
    _Colors.GREEN,
    _Colors.MAGENTA,
    _Colors.YELLOW,
    _Colors.BLUE,
    _Colors.BRIGHT_CYAN,
    _Colors.BRIGHT_GREEN,
    _Colors.BRIGHT_YELLOW,
]


def tweak_label(setting_id: str) -> str:
    """Return a consistently colored setting_id label for terminal output.

    The color is determined by hashing setting_id so the same tweak always
    gets the same color across log lines, making logs easier to scan.
    Falls back to plain text when colors are disabled (CI, no TTY).
    """
    if not _should_use_colors():
        return setting_id
    color = _TWEAK_COLORS[hash(setting_id) % len(_TWEAK_COLORS)]
    return f"{color}{setting_id}{_Colors.RESET}"


class _ColorFormatter(logging.Formatter):
    """Custom formatter with colors and professional format.

    Format: LEVEL | service | dd.mm.yyyy HH:MM:SS | message
    """

    # Level colors
    LEVEL_COLORS = {
        logging.DEBUG: _Colors.GRAY,
        logging.INFO: _Colors.CYAN,
        logging.WARNING: _Colors.YELLOW,
        logging.ERROR: _Colors.RED,
        logging.CRITICAL: _Colors.BRIGHT_RED + _Colors.BOLD,
    }

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize formatter.

        Args:
            use_colors: Whether to use ANSI colors.
        """
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with professional layout."""
        # Timestamp in dd.mm.yyyy HH:MM:SS format
        timestamp = datetime.fromtimestamp(record.created).strftime("%d.%m.%Y %H:%M:%S")

        # Shorten logger name (fpstune.api.cache -> api.cache)
        name = record.name
        if name.startswith("fpstune."):
            name = name[8:]  # Remove "fpstune." prefix

        # Level name padded to 5 chars
        level = record.levelname[:5].ljust(5)

        # Format message
        message = record.getMessage()

        if self.use_colors:
            level_color = self.LEVEL_COLORS.get(record.levelno, _Colors.WHITE)
            return (
                f"{level_color}{level}{_Colors.RESET} "
                f"{_Colors.DIM}|{_Colors.RESET} "
                f"{_Colors.MAGENTA}{name:20}{_Colors.RESET} "
                f"{_Colors.DIM}|{_Colors.RESET} "
                f"{_Colors.GRAY}{timestamp}{_Colors.RESET} "
                f"{_Colors.DIM}|{_Colors.RESET} "
                f"{message}"
            )
        else:
            return f"{level} | {name:20} | {timestamp} | {message}"


class _ConsoleHandler(logging.Handler):
    """Emit through the shared Console so colour is decided and enabled once.

    The formatter still produces the ANSI escapes; this only routes them to the
    stream Rich has prepared. `markup=False` and `highlight=False` because the
    text is already styled and already escaped — letting Rich re-interpret it
    would turn a Windows path or a `[skipped]` in a message into markup.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            console.print(self.format(record), markup=False, highlight=False, soft_wrap=True)
        except Exception:  # pragma: no cover - logging must never raise
            self.handleError(record)


def _should_use_colors() -> bool:
    """Whether this console can render colour.

    Asks the shared Console rather than re-deriving it. Two components deciding
    this separately is what produced escapes the terminal was not yet able to
    interpret.
    """
    # Check for NO_COLOR environment variable (standard)
    if os.environ.get("NO_COLOR"):
        return False

    # Check for pytest (no colors during tests)
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return False

    return console.is_terminal


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    verbose: bool = False,
) -> logging.Logger:
    """Set up logging for fpstune.

    Args:
        level: Logging level (default: INFO).
        log_file: Optional path to log file.
        verbose: If True, show debug messages.

    Returns:
        Configured logger instance.
    """
    if verbose:
        level = logging.DEBUG

    # Create logger
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)

    # Prevent propagation to root logger (avoids duplicate logs)
    logger.propagate = False

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler, writing through the shared Console.
    #
    # It used to be a plain StreamHandler emitting raw ANSI after deciding for
    # itself that stdout was a terminal. On Windows that decision is only half
    # the story: a console interprets those escapes only once virtual-terminal
    # mode is on, and the thing that turns it on is Rich, when Rich first
    # prints. So every log line before Rich's first output arrived as literal
    # `←[36mINFO ←[0m` and every line after it arrived correctly — same process,
    # same handler, same run.
    #
    # Going through the shared Console means one component decides colour and
    # one component enables it, which is also why the escapes below are now
    # Rich markup rather than bytes this module writes itself.
    use_colors = _should_use_colors()
    console_handler = _ConsoleHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(_ColorFormatter(use_colors=use_colors))
    logger.addHandler(console_handler)

    # File handler (if specified) — rotates at 5 MB, keeps 3 backups
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(levelname)-5s | %(name)-20s | %(asctime)s | %(message)s",
                datefmt="%d.%m.%Y %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    """Get the fpstune logger.

    Returns:
        Logger instance (creates one with defaults if not set up).
    """
    logger = logging.getLogger(LOGGER_NAME)

    # Ensure no propagation to root logger (avoids duplicate logs)
    logger.propagate = False

    # Set up with defaults if no handlers
    if not logger.handlers:
        setup_logging()

    return logger


class ActivityLog:
    """Activity log for tracking operations.

    Written from the sixteen bulk-apply worker threads, so every mutation is
    guarded. The store is a bounded deque rather than a list that gets sliced:
    the old trim rebound ``self._entries`` to a fresh list, and an append that
    landed between the read and the rebind was silently dropped.
    """

    def __init__(self, max_entries: int = 100) -> None:
        """Initialize activity log.

        Args:
            max_entries: Maximum number of log entries to keep.
        """
        self._entries: deque[dict[str, str]] = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def add(self, message: str, level: str = "info") -> None:
        """Add an entry to the activity log.

        Args:
            message: Log message.
            level: Log level (info, success, warning, error).
        """
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "message": message,
            "level": level,
        }
        with self._lock:
            # deque(maxlen=...) evicts the oldest in the same operation, so
            # there is no separate trim to race with.
            self._entries.append(entry)

    def log(self, message: str, level: str = "info") -> None:
        """Alias for add() method."""
        self.add(message, level)

    def get_entries(self, limit: int = 50) -> list[dict[str, str]]:
        """Get recent log entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of log entries (newest first).
        """
        with self._lock:
            recent = list(self._entries)[-limit:]
        return list(reversed(recent))

    def clear(self) -> None:
        """Clear all log entries."""
        with self._lock:
            self._entries.clear()


# Global activity log instance
activity_log = ActivityLog()


def log_activity(message: str, level: str = "info") -> None:
    """Log an activity message.

    Args:
        message: Activity message.
        level: Level (info, success, warning, error).
    """
    activity_log.add(message, level)

    # Also log to standard logger with colored prefix
    logger = get_logger()

    # Map level to log method and add prefix (ASCII for Windows compatibility)
    if level == "success":
        logger.info(f"{_Colors.GREEN}[OK]{_Colors.RESET} {message}")
    elif level == "error":
        logger.error(f"{_Colors.RED}[FAIL]{_Colors.RESET} {message}")
    elif level == "warning":
        logger.warning(f"{_Colors.YELLOW}[WARN]{_Colors.RESET} {message}")
    else:
        logger.info(message)
