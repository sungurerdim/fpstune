"""Every change fpstune made to this machine, across runs.

`originals.py` remembers what the machine held *before* fpstune; nothing
remembered what fpstune did *after*. A user who applied a dozen tweaks last week
had no way to see them again, short of scanning every row for one that differs
from its default — and a guard that put a value back looks exactly like an
untouched setting.

So each successful apply, reset and undo is appended here, from the one place
every write ends (`routes.settings._finalize_apply_response`), so no path can
change the machine without leaving a line. A failed write is not a change and
is not recorded. Actions (cleanups, maintenance) are not either: they change
nothing that can be put back.

The file is a journal, oldest first, capped so it cannot grow without bound; the
latest line per setting is that setting's current story.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from fpstune.utils.config import get_config_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
#: Lines kept. A year of daily use is a few hundred; the cap only stops a runaway.
MAX_ENTRIES = 5000

Action = Literal["apply", "reset", "undo"]

#: `_finalize_apply_response`'s activity label → the journal's action.
ACTION_FOR_LABEL: dict[str, Action] = {"Applied": "apply", "Reset": "reset", "Undo": "undo"}


@dataclass(frozen=True)
class Change:
    """One write that landed and verified."""

    setting_id: str
    action: Action
    value: Any
    at: float


class ChangeJournal:
    """The append-only record of what fpstune changed."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_config_dir() / "history.json")
        self._lock = threading.Lock()
        self._entries: list[Change] | None = None

    def _load(self) -> list[Change]:
        if self._entries is not None:
            return self._entries
        self._entries = []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            return self._entries
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            # Unreadable history must not stop applies; it is set aside rather
            # than overwritten, so nothing that was recorded is lost to a bad read.
            logger.warning("change history unreadable, starting a new one: %s", exc)
            self._set_aside()
            return self._entries
        if not isinstance(raw, dict) or raw.get("version") != SCHEMA_VERSION:
            logger.warning("change history has an unknown layout, starting a new one")
            self._set_aside()
            return self._entries
        for item in raw.get("entries", []):
            if not isinstance(item, dict):
                continue
            action = item.get("action")
            if action in ("apply", "reset", "undo") and isinstance(item.get("setting_id"), str):
                self._entries.append(
                    Change(item["setting_id"], action, item.get("value"), float(item.get("at", 0)))
                )
        return self._entries

    def _set_aside(self) -> None:
        try:
            self._path.replace(self._path.with_suffix(f".unreadable-{int(time.time())}.json"))
        except OSError as exc:
            logger.warning("could not set the unreadable history aside: %s", exc)

    def _persist(self) -> None:
        payload = {
            "version": SCHEMA_VERSION,
            "entries": [asdict(entry) for entry in self._entries or []],
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
            temp.replace(self._path)
        except OSError as exc:
            logger.warning("could not persist the change history: %s", exc)

    def record(self, setting_id: str, action: Action, value: Any) -> None:
        """Append one landed change."""
        with self._lock:
            entries = self._load()
            entries.append(Change(setting_id, action, value, time.time()))
            del entries[:-MAX_ENTRIES]
            self._persist()

    def entries(self) -> list[Change]:
        """Every recorded change, newest first."""
        with self._lock:
            return list(reversed(self._load()))

    def latest(self) -> dict[str, Change]:
        """The most recent change per setting."""
        with self._lock:
            latest: dict[str, Change] = {}
            for entry in self._load():
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
