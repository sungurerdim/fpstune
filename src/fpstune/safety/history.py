"""What fpstune changed on this machine since this process started.

Each successful apply and reset is appended here, from the one place every write
ends (`routes.settings._finalize_apply_response`), so no path can change the
machine without leaving a line. A failed write is not a change and is not
recorded. Actions (cleanups, maintenance) are not either: they change nothing
that can be put back.

The journal lives in memory only. fpstune keeps no history and no previous
values on disk (decided 2026-10-06, #103): a restart empties it, and the History
tab shows this session's actions. Earlier releases wrote `history.json` and
`originals.json` under the config directory; `remove_retired_files` deletes what
they left behind, once, at start-up.

The journal is oldest first, capped so it cannot grow without bound; the latest
line per setting is that setting's current story.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from fpstune.utils.config import get_config_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

#: Lines kept. A session is a few dozen; the cap only stops a runaway.
MAX_ENTRIES = 5000

Action = Literal["apply", "reset", "revert"]

#: `_finalize_apply_response`'s activity label → the journal's action.
ACTION_FOR_LABEL: dict[str, Action] = {"Applied": "apply", "Reset": "reset"}

#: What earlier releases left in the config directory. Globs, because a write
#: interrupted mid-replace leaves its `.tmp`, and an unreadable history was set
#: aside under a timestamped name rather than overwritten.
RETIRED_FILE_PATTERNS = (
    "originals.json",
    "originals.json.tmp",
    "history.json",
    "history.json.tmp",
    "history.unreadable-*.json",
)


@dataclass(frozen=True)
class Change:
    """One write that landed and verified."""

    setting_id: str
    action: Action
    value: Any
    at: float


class ChangeJournal:
    """The append-only, in-memory record of what fpstune changed this session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[Change] = []

    def record(self, setting_id: str, action: Action, value: Any) -> None:
        """Append one landed change."""
        with self._lock:
            self._entries.append(Change(setting_id, action, value, time.time()))
            del self._entries[:-MAX_ENTRIES]

    def entries(self) -> list[Change]:
        """Every recorded change, newest first."""
        with self._lock:
            return list(reversed(self._entries))

    def latest(self) -> dict[str, Change]:
        """The most recent change per setting."""
        with self._lock:
            latest: dict[str, Change] = {}
            for entry in self._entries:
                latest[entry.setting_id] = entry
            return latest


_journal: ChangeJournal | None = None
_journal_lock = threading.Lock()


def get_change_journal() -> ChangeJournal:
    """The process-wide journal. One instance, so its in-memory view is the truth."""
    global _journal
    with _journal_lock:
        if _journal is None:
            _journal = ChangeJournal()
        return _journal


def remove_retired_files(config_dir: Path | None = None) -> list[Path]:
    """Delete the stored previous values and history earlier releases wrote.

    Returns the files removed. A file that cannot be deleted is logged and left
    for the next start; it never stops the application from starting. The
    directory defaults to `get_config_dir()` and is never a literal path (C9).
    """
    directory = config_dir if config_dir is not None else get_config_dir()
    removed: list[Path] = []
    for pattern in RETIRED_FILE_PATTERNS:
        for path in directory.glob(pattern):
            if not path.is_file():
                continue
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("could not remove retired file %s: %s", path, exc)
                continue
            removed.append(path)
    if removed:
        logger.info("removed %d retired state file(s) from %s", len(removed), directory)
    return removed
