"""One ``<Setting>`` in the NVIDIA App backend's own ``config.xml``.

The App keeps its backend switches in ``NvBackend/config.xml`` as
``<Setting name='...' value='N' />`` elements — ``EnableAutomaticApplyOPS`` is
the one that decides whether the App applies its optimization profile to a game
without being asked. Turning it off is how fpstune stops the App replacing the
game settings it recommends.

The file belongs to NVIDIA (read on this machine 2026-10-22: five settings, an
``ApplicationScanPaths`` element and a version stamp), so it is edited the way
Battle.net.config is: one attribute changes, every other byte stays as NVIDIA
wrote it, and the replacement is atomic. An ``ElementTree`` round trip is
exactly what is *not* used here — it would re-quote every attribute and drop
the file's own layout, which is a diff in a vendor's file for no reason.

A file without the element is an absence, not "off": the App's behaviour for a
switch it never wrote is unknown, and guessing it would put a state on a row
that nobody measured.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from pathlib import Path

from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.utils import user_paths
from fpstune.utils.logger import get_logger

logger = get_logger()

#: The backend's configuration file, relative to the console user's local AppData.
_RELATIVE = Path("NVIDIA Corporation") / "NVIDIA App" / "NvBackend" / "config.xml"

#: The switch that keeps the App from applying its profile on its own.
AUTO_APPLY_SETTING = "EnableAutomaticApplyOPS"

#: Bulk apply runs rows in parallel; every write here shares this file.
_lock = threading.Lock()


def config_path() -> Path | None:
    """The App backend's config.xml, or None on a machine without one."""
    local = user_paths.local_appdata()
    return local / _RELATIVE if local is not None else None


def _element(name: str) -> re.Pattern[str]:
    """The one ``<Setting name='NAME' ... value='N' ... />`` element, whatever its attribute order."""
    return re.compile(
        r"<Setting\b(?=[^>]*\bname=(['\"])" + re.escape(name) + r"\1)[^>]*>",
    )


def _value_of(element: str) -> str | None:
    match = re.search(r"\bvalue=(['\"])([^'\"]*)\1", element)
    return match.group(2) if match else None


def read_setting(name: str, path: Path | None = None) -> str | None:
    """The element's raw ``value``, or None when the file or the element is absent."""
    target = path if path is not None else config_path()
    if target is None or not target.is_file():
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("NVIDIA App config.xml unreadable at %s: %s", target, exc)
        return None
    match = _element(name).search(text)
    if match is None:
        return None
    return _value_of(match.group(0))


def write_setting(name: str, value: str, path: Path | None = None) -> tuple[bool, str | None]:
    """Set one element's ``value`` in place, atomically, leaving every other byte alone."""
    if not value.isdigit():
        return False, f"'{value}' is not a number the NVIDIA App writes"
    target = path if path is not None else config_path()
    if target is None or not target.is_file():
        return False, "The NVIDIA App's backend configuration was not found, so nothing was changed"
    with _lock:
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return False, f"The NVIDIA App's backend configuration could not be read: {exc}"
        pattern = _element(name)
        match = pattern.search(text)
        if match is None:
            return False, (
                f"The NVIDIA App's configuration carries no {name} switch, so it was left untouched"
            )
        element = match.group(0)
        replaced, count = re.subn(r"\bvalue=(['\"])[^'\"]*\1", f"value='{value}'", element, count=1)
        if count != 1:
            return False, f"The {name} switch has no value attribute, so it was left untouched"
        updated = text[: match.start()] + replaced + text[match.end() :]
        try:
            handle, temporary = tempfile.mkstemp(prefix=".fpstune-", dir=target.parent)
            try:
                with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
                    stream.write(updated)
                os.replace(temporary, target)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
        except OSError as exc:
            return False, f"The NVIDIA App's backend configuration could not be written: {exc}"
    written = read_setting(name, target)
    if written != value:
        return False, (
            "The NVIDIA App rewrote its configuration before the change held; "
            "try again with the App closed"
        )
    return True, None


def auto_apply_state() -> str:
    """``enabled`` / ``disabled`` for the App's own game optimization, or ``not_available``."""
    if sys.platform != "win32":
        return NOT_AVAILABLE
    raw = read_setting(AUTO_APPLY_SETTING)
    if raw is None:
        return NOT_AVAILABLE
    return "enabled" if raw.strip() == "1" else "disabled"


def nvapp_auto_apply_read(_args: dict[str, object]) -> str:
    """``PYTHON_DETECTORS`` entry: whether the App applies its optimization profile on its own."""
    return auto_apply_state()


def nvapp_auto_apply_write(args: dict[str, object]) -> tuple[bool, str | None]:
    """``PYTHON_ACTIONS`` entry: write the display value into the App's own switch."""
    value = str(args.get("value", ""))
    if value not in ("enabled", "disabled"):
        return False, f"'{value}' is a reading, not a value fpstune can write"
    ok, error = write_setting(AUTO_APPLY_SETTING, "1" if value == "enabled" else "0")
    if not ok:
        return False, error
    return True, (
        "The NVIDIA App no longer applies its optimization profile on its own"
        if value == "disabled"
        else "The NVIDIA App applies its optimization profile on its own again"
    )
