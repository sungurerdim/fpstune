"""Read and write Battle.net.config without damaging it.

The file is JSON in the console user's roaming AppData. The PowerShell writer it
replaces round-tripped it through ``ConvertFrom-Json | ConvertTo-Json`` and
``Set-Content -Encoding UTF8``: Windows PowerShell re-escapes the whole document
and prepends a byte-order mark, so one toggle rewrote every value the client
owns. Here the document is parsed and dumped once, with no BOM, and replaced
atomically, so a failed write leaves the client's own file in place.

Keys are dotted paths into the document (``Client.Install.DownloadLimitNextPatchInBps``);
only paths the client is known to read are used by the definitions.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from fpstune.settings.applicability import NOT_INSTALLED
from fpstune.utils import user_paths
from fpstune.utils.logger import get_logger

logger = get_logger()

# What a detect returns for a key the file does not carry: the client's default.
ABSENT = "absent"

_RELATIVE = Path("Battle.net") / "Battle.net.config"

# Bulk apply runs settings in parallel; every Battle.net setting shares one
# file, so the read-modify-write holds this for its whole length.
_lock = threading.Lock()


def config_path() -> Path | None:
    """The console user's Battle.net.config, or None off Windows."""
    if sys.platform != "win32":
        return None
    from fpstune.settings.executors.game_config_cache import _console_user_folder

    roaming = _console_user_folder("AppData")
    if roaming is None:
        roaming = user_paths.roaming_appdata()
    return roaming / _RELATIVE if roaming is not None else None


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Battle.net.config is not a JSON object")
    return data


def read_value(key: str, path: Path | None = None) -> str:
    """The value at ``key`` as text, ``ABSENT``, or ``NOT_INSTALLED``."""
    path = path if path is not None else config_path()
    if path is None or not path.is_file():
        return NOT_INSTALLED
    try:
        node: Any = _load(path)
    except (OSError, ValueError) as exc:
        logger.debug("Battle.net.config unreadable: %s", exc)
        return NOT_INSTALLED
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return ABSENT
        node = node[part]
    if isinstance(node, bool):
        return "true" if node else "false"
    return str(node).strip().lower()


def write_value(key: str, value: str, path: Path | None = None) -> tuple[bool, str | None]:
    """Set ``key`` to the string ``value`` (the client stores its flags as strings)."""
    path = path if path is not None else config_path()
    if path is None or not path.is_file():
        return False, "Battle.net is not installed for this user"
    parts = key.split(".")
    with _lock:
        try:
            data = _load(path)
        except (OSError, ValueError) as exc:
            return False, f"Battle.net.config could not be read, so it was left untouched: {exc}"
        node = data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
        text = json.dumps(data, indent=4, ensure_ascii=False) + "\n"
        try:
            fd, tmp = tempfile.mkstemp(prefix=".fpstune-", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            return False, f"Battle.net.config could not be written: {exc}"
    return True, None


def bnet_config_read(args: dict[str, Any]) -> str:
    """``PYTHON_DETECTORS`` entry: the raw value at ``args['key']``."""
    return read_value(str(args["key"]))


def bnet_config_write(args: dict[str, Any]) -> tuple[bool, str | None]:
    """``PYTHON_ACTIONS`` entry: write ``args['value']``, refusing anything not allowed.

    ``allowed`` names the raw values a definition can write. A display value
    with no raw form (a guard's "changed" reading) arrives here unmapped and is
    refused rather than written into the client's config verbatim.
    """
    value = str(args.get("value", ""))
    allowed = str(args.get("allowed", "")).split(",")
    if value not in allowed:
        return False, f"'{value}' is a reading, not a value fpstune can write"
    return write_value(str(args["key"]), value)
