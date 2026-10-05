"""Whether Windows was updated since fpstune last ran.

A feature update — and now and then a cumulative one — puts settings back to
Windows' own values: a policy re-applied, a service start type reset, a power
scheme rewritten. fpstune's guards exist for exactly that drift, but a user who
applied everything a month ago has no reason to look again. So the first time
the UI asks after a start, the running build (``CurrentBuild.UBR``, e.g.
``26100.4061``) is compared with the one recorded last time, and the answer is
kept for the rest of the process: the startup scan that runs anyway is the
re-check, and the notice says why its results may have changed.

State is one small JSON file in ~/.fpstune. A missing or unreadable file is a
first run — nothing to compare, so no notice — and is rewritten in place.
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from fpstune.utils.logger import get_logger

logger = get_logger()

_STATE_FILE = "os_build.json"
_CURRENT_VERSION_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"


@dataclass(frozen=True)
class BuildChange:
    """The build recorded last time, the running one, and whether they differ."""

    previous: str | None
    current: str | None
    changed: bool


def current_build() -> str | None:
    """``CurrentBuild.UBR`` of the running Windows, or None where it cannot be read."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _CURRENT_VERSION_KEY,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            build = str(winreg.QueryValueEx(key, "CurrentBuild")[0]).strip()
            try:
                ubr = int(winreg.QueryValueEx(key, "UBR")[0])
            except (FileNotFoundError, ValueError, TypeError):
                return build or None
    except OSError as exc:
        logger.debug("Windows build could not be read: %s", exc)
        return None
    return f"{build}.{ubr}" if build else None


def _read_previous(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    build = data.get("build") if isinstance(data, dict) else None
    return build if isinstance(build, str) and build else None


def check_build_change(state_path: Path, current: str | None) -> BuildChange:
    """Compare ``current`` with the build recorded at ``state_path``, then record it.

    ``changed`` is true only when both are known and differ: a first run, or a
    build that could not be read, says nothing about drift. An unreadable
    current build leaves the record alone, so the next readable start still
    compares against the last real one.
    """
    previous = _read_previous(state_path)
    if current is None:
        return BuildChange(previous=previous, current=None, changed=False)
    if previous != current:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"build": current}), encoding="utf-8")
            tmp.replace(state_path)
        except OSError as exc:
            logger.warning("Could not record the Windows build: %s", exc)
    return BuildChange(
        previous=previous,
        current=current,
        changed=previous is not None and previous != current,
    )


_lock = threading.Lock()
_answer: BuildChange | None = None


def build_change_since_last_run() -> dict[str, object]:
    """This process's one answer, computed on first call and kept.

    Recording happens on that first call, so a page reload in the same session
    still sees the update; the next start compares against the new build.
    """
    global _answer
    with _lock:
        if _answer is None:
            from fpstune.utils.config import get_config_dir

            _answer = check_build_change(get_config_dir() / _STATE_FILE, current_build())
            if _answer.changed:
                logger.info("Windows was updated: %s -> %s", _answer.previous, _answer.current)
        return asdict(_answer)
