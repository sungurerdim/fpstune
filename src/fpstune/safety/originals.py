"""What the machine held before fpstune ever changed it.

`reset` writes a setting's `default_value` — the curated Windows stock value.
That is a useful thing to do and it is not the same thing as undoing fpstune,
which is what "reset" reads like. A machine that deliberately ran a non-stock
value before fpstune arrived gets that value overwritten by a reset, and until
this module existed there was nothing anywhere in the codebase that remembered
it: `safety/` held System Restore points, which are whole-machine and
coarse-grained, and nothing else.

**Where the value comes from.** The first scan that sees a setting records what
it read, and later scans never overwrite it. That timing is the definition, not
an implementation detail: "before fpstune changed it" is exactly "as fpstune
first found it". It also costs nothing — the scan already ran, and reading the
value again immediately before each write would add a subprocess per setting to
a path a previous phase deliberately removed one from.

The honest limit, and the UI must not overstate it: if someone applied tweaks
with an earlier fpstune release and only then ran this one, what gets recorded
is the already-tweaked value. This records what it saw, not what was true before
anything ever ran.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from fpstune.utils.config import get_config_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class OriginalValues:
    """First-seen value per setting, persisted across runs.

    First write wins. A store that let a later scan overwrite an entry would
    record the value fpstune itself had just applied, and "undo" would then put
    the tweak back — a guarantee that silently means nothing is worse than no
    guarantee, which is the failure mode this whole codebase keeps paying for.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_config_dir() / "originals.json")
        self._lock = threading.Lock()
        self._values: dict[str, dict[str, Any]] | None = None
        self._damaged: str | None = None

    # --- persistence ---------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._values is not None:
            return self._values

        self._values = {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            # Nothing recorded yet — or no place to keep it, in which case the
            # store lives in memory for this run (see _persist).
            return self._values
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            # A corrupt store must not take the app down, and must not read as
            # "nothing was ever recorded" either: the next scan would then
            # record post-apply values over every original. The file is left
            # exactly as it is and nothing is recorded until it is dealt with.
            self._damaged = f"the undo record at {self._path} could not be read ({exc})"
            logger.warning("originals store unreadable, undo is unavailable: %s", exc)
            return self._values

        if not isinstance(raw, dict) or raw.get("version") != SCHEMA_VERSION:
            self._damaged = (
                f"the undo record at {self._path} has a layout this version does not know"
            )
            logger.warning("originals store has an unrecognised layout; leaving it untouched")
            return self._values

        entries = raw.get("values")
        if isinstance(entries, dict):
            self._values = {
                str(k): v for k, v in entries.items() if isinstance(v, dict) and "value" in v
            }
        return self._values

    def _persist(self) -> None:
        payload = {"version": SCHEMA_VERSION, "values": self._values or {}}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside the target and replace, so an interrupted write
            # cannot leave a half-written store that reads as "nothing recorded".
            temp = self._path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            temp.replace(self._path)
        except OSError as exc:
            logger.warning("could not persist the originals store: %s", exc)

    # --- api -----------------------------------------------------------

    def record_first_seen(
        self, readings: dict[str, Any], raw: dict[str, dict[str, Any]] | None = None
    ) -> int:
        """Record any setting not seen before. Returns how many were added.

        Pass ``{setting_id: value}`` for settings that were actually read, and
        optionally ``raw`` — the stored state behind each (safety/raw_state.py),
        which lets undo restore it exactly. A setting whose value is None was
        not read, and recording None would promise an undo that writes nothing.
        Nothing is recorded while the store on disk is damaged.
        """
        added = 0
        with self._lock:
            values = self._load()
            if self._damaged:
                return 0
            for setting_id, value in readings.items():
                if value is None or setting_id in values:
                    continue
                entry: dict[str, Any] = {"value": value, "first_seen": time.time()}
                if raw and raw.get(setting_id) is not None:
                    entry["raw"] = raw[setting_id]
                values[setting_id] = entry
                added += 1
            if added:
                self._persist()
        return added

    def damaged(self) -> str | None:
        """Why the store cannot be trusted, or None when it is sound."""
        with self._lock:
            self._load()
            return self._damaged

    def get_raw(self, setting_id: str) -> dict[str, Any] | None:
        """The stored state recorded with the first reading, if one was."""
        with self._lock:
            entry = self._load().get(setting_id)
        raw = entry.get("raw") if entry else None
        return raw if isinstance(raw, dict) else None

    def get(self, setting_id: str) -> Any | None:
        """The value this setting held when fpstune first saw it, if it did."""
        with self._lock:
            entry = self._load().get(setting_id)
        return entry.get("value") if entry else None

    def forget(self, setting_id: str) -> bool:
        """Drop one entry. Returns whether there was one.

        Called after an undo lands: the machine is back where it started, so the
        next scan is free to record a fresh original — otherwise the store would
        pin a value from an arbitrarily old session forever.
        """
        with self._lock:
            values = self._load()
            if self._damaged or setting_id not in values:
                return False
            del values[setting_id]
            self._persist()
        return True

    def count(self) -> int:
        with self._lock:
            return len(self._load())


_store: OriginalValues | None = None
_store_lock = threading.Lock()


def get_original_values() -> OriginalValues:
    """The process-wide store. One instance, so its in-memory view is the truth."""
    global _store
    with _store_lock:
        if _store is None:
            _store = OriginalValues()
        return _store
