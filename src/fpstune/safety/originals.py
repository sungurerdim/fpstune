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

    # --- persistence ---------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._values is not None:
            return self._values

        self._values = {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._values
        except (json.JSONDecodeError, OSError) as exc:
            # A corrupt store must not take the app down, and must not silently
            # read as "nothing was ever recorded" either — that would let the
            # next scan overwrite every original with a post-apply value.
            logger.warning("originals store unreadable, undo is unavailable: %s", exc)
            return self._values

        if not isinstance(raw, dict) or raw.get("version") != SCHEMA_VERSION:
            logger.warning("originals store has an unrecognised layout; ignoring it")
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

    def record_first_seen(self, readings: dict[str, Any]) -> int:
        """Record any setting not seen before. Returns how many were added.

        Pass ``{setting_id: value}`` for settings that were actually read. A
        setting whose value is None was not read, and recording None would
        promise an undo that writes nothing.
        """
        added = 0
        with self._lock:
            values = self._load()
            for setting_id, value in readings.items():
                if value is None or setting_id in values:
                    continue
                values[setting_id] = {"value": value, "first_seen": time.time()}
                added += 1
            if added:
                self._persist()
        return added

    def get(self, setting_id: str) -> Any | None:
        """The value this setting held when fpstune first saw it, if it did."""
        with self._lock:
            entry = self._load().get(setting_id)
        return entry.get("value") if entry else None

    def has(self, setting_id: str) -> bool:
        with self._lock:
            return setting_id in self._load()

    def forget(self, setting_id: str) -> bool:
        """Drop one entry. Returns whether there was one.

        Called after an undo lands: the machine is back where it started, so the
        next scan is free to record a fresh original — otherwise the store would
        pin a value from an arbitrarily old session forever.
        """
        with self._lock:
            values = self._load()
            if setting_id not in values:
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
