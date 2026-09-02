"""Write a single MW4 (cod26) setting without disturbing anything else.

MW4's config is one setting per line, and the line carries more than the value:

    TextureQuality@0;61129;7764 = 1 // 0 to 3

The suffix after ``@0`` is an opaque hash the game emitted, and the trailing
comment is the file's own statement of the valid range. Both are copied through
untouched — this module only ever replaces the text between ``= `` and the
comment, on exactly one line.

Three properties of the file that a naive writer gets wrong, all measured:

* **Line endings are LF**, on Windows, in a file Windows wrote. ``write_text``
  would translate every one of them to CRLF and rewrite the whole file while
  reporting that one setting changed.
* **There is no BOM today**, but CS2's autoexec.cfg has one and MW4's release
  build may. The read strips it and the write puts back exactly what was there.
* **The file may be read-only.** An earlier fpstune release set that attribute
  on MW3's config and every in-game change silently reverted; the lock is
  cleared here and never set.
"""

from __future__ import annotations

import codecs
import contextlib
import ctypes
import os
import re
import stat
import sys
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from ctypes import wintypes
from pathlib import Path
from typing import Any

from fpstune.settings.executors.game_config_cache import (
    NOT_INSTALLED,
    get_mw4_metadata,
    mw4_config_paths,
)
from fpstune.utils.logger import get_logger

logger = get_logger()

_SOURCES = ("global", "profile")

# One mutex per config file, because one MW4 setting is one whole-file rewrite.
#
# Bulk apply runs settings in parallel — sixteen workers in
# `api/routes/settings.py`. Two of them writing the same file both read it
# before either writes, and the last one out replaces the file with a copy that
# never had the first one's change in it. Both then report success, because each
# verifies against the copy it wrote itself: apply green, verify green, setting
# absent. That is the same failure shape as the running-game overwrite this
# module already guards against, arriving from inside the product instead.
#
# Measured 2026-08-24: `voice_volume` and `effects_volume` applied in the same
# second and collided on the shared temp path — `[Errno 13] Permission denied`
# and `[WinError 5]`. The filesystem caught what the code did not, and only
# because both writers happened to pick the same temp name.
#
# A named system mutex rather than a `threading.Lock`, matching what the
# PowerShell writers already use for exactly this
# (`powershell_actions._MUTEX_GROUPS` — CS2's autoexec, MW3's cst, HotS's
# Variables.txt). It holds across processes too, so a CLI run and the API
# cannot race each other over the same file.
_MUTEX_NAMES = {
    "global": "Global\\fpstune-mw4-global-cst",
    "profile": "Global\\fpstune-mw4-profile-txt",
}

# Long enough that a slow disk finishes, short enough that a stuck holder does
# not hang bulk apply behind its own 60 s budget.
_LOCK_TIMEOUT_MS = 15_000

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080

# The fallback when there is no Windows mutex to take: same process only, which
# is the exposure bulk apply actually has. Never silently no-op — a lock that
# does nothing turns a loud collision into a silent lost update.
_fallback_locks: dict[str, threading.Lock] = {}
_fallback_guard = threading.Lock()


def _fallback_lock(name: str) -> threading.Lock:
    with _fallback_guard:
        return _fallback_locks.setdefault(name, threading.Lock())


@contextlib.contextmanager
def _file_lock(source: str) -> Iterator[None]:
    """Hold the whole read-modify-write for one config file.

    Falls back to a process-local lock when the system mutex cannot be created
    — off Windows, or on any API failure. That is weaker than the mutex but it
    still covers the parallel bulk apply, which is where the loss was measured.
    """
    name = _MUTEX_NAMES[source]

    if sys.platform != "win32":
        with _fallback_lock(name):
            yield
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = (wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        logger.debug("MW4 mutex unavailable (%s); serializing in-process only", name)
        with _fallback_lock(name):
            yield
        return

    try:
        waited = kernel32.WaitForSingleObject(handle, _LOCK_TIMEOUT_MS)
        # WAIT_ABANDONED means the previous holder died mid-write. The lock is
        # ours and the file may be half-written, which the atomic replace below
        # makes impossible to observe — so take it and say so.
        if waited == _WAIT_ABANDONED:
            logger.debug("MW4 %s lock was abandoned by a previous holder", source)
        elif waited != _WAIT_OBJECT_0:
            raise TimeoutError(
                f"another writer held the MW4 {source} config for over {_LOCK_TIMEOUT_MS // 1000}s"
            )
        try:
            yield
        finally:
            kernel32.ReleaseMutex(handle)
    finally:
        kernel32.CloseHandle(handle)


# Every character Python treats as a line terminator, because the rewrite below
# splices the value into one line of the file and MW4 reads one setting per line.
#
# This is the one rule that does not come from the file's own metadata, and it
# does not have to: a config line being a single line is a property of the
# format, not of any particular key. `Resolution@0` and `RefreshRate@0` ship
# without a `// range` comment, so absent authority means the value is written
# as given — and a value carrying a newline would have written arbitrary extra
# keys into the game's config. Inventing bounds for those keys would be the
# hardcoded-constant bug C9 names; refusing a value that is not one line is not.
_LINE_BREAK = re.compile("[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]")


class Mw4ValueRejected(ValueError):
    """The requested value is outside what the file says the key accepts.

    Raised rather than written, because C1 forbids handing the game a value it
    will not accept — MW4 answers one by resetting the key, which loses whatever
    the user had.
    """


def _path_for(source: str) -> Path | None:
    """One file. ``both`` is handled by the caller and never reaches here."""
    if source not in _SOURCES:
        raise ValueError(f"unknown MW4 config source {source!r}")
    global_path, profile_path = mw4_config_paths()
    return global_path if source == "global" else profile_path


def _line_pattern(key: str) -> re.Pattern[str] | None:
    """Match one ``Name@<scope>`` assignment, capturing what must survive.

    Group 1 is everything up to and including ``= ``; group 2 is the value;
    group 3 is the trailing comment with its leading whitespace. Only group 2
    is replaced.
    """
    name, sep, scope = key.rpartition("@")
    if not sep or not scope.isdigit():
        return None
    return re.compile(
        rf"(?m)^(?P<head>[ \t]*{re.escape(name)}@{scope}(?:;[^\s=]*)?[ \t]*=[ \t]*)"
        r"(?P<value>.*?)(?P<tail>[ \t]*\/\/.*)?$"
    )


def _validate(key: str, value: str, source: str) -> str:
    """Check the value against the range the file documents, and return what to write.

    The return value matters: a caller that spells a choice in a different case
    is accepted, but what lands in the file is the file's own spelling. Writing
    ``ultra`` where MW4 lists ``Ultra`` passes a string comparison here and then
    loses to whatever the game's parser does with it.

    Silent when the key carries no comment: absent metadata is absent authority,
    not permission to reject — with the one exception of a value that is not a
    single line, which no key can accept whatever its metadata says.
    """
    if _LINE_BREAK.search(value):
        raise Mw4ValueRejected(f"{key}: a config value must be one line, got {value!r}")

    meta: dict[str, Any] = get_mw4_metadata(key, source)
    if not meta:
        return value

    choices = meta.get("choices")
    if choices is not None:
        # Case-insensitive on the way in because the file mixes conventions
        # freely — `QUALITY_LOW` beside `Low Quality` beside `aniso 8x`.
        for choice in choices:
            if str(choice).casefold() == value.casefold():
                return str(choice)
        raise Mw4ValueRejected(f"{key}: {value!r} is not one of {choices}")

    low, high = meta.get("minimum"), meta.get("maximum")
    if low is None or high is None:
        return value
    try:
        numeric = float(value)
    except ValueError:
        raise Mw4ValueRejected(f"{key}: {value!r} is not numeric, range is {low}..{high}") from None
    if not (float(low) <= numeric <= float(high)):
        raise Mw4ValueRejected(f"{key}: {value!r} is outside {low}..{high}")
    return value


def _match_number_format(existing: str, value: str) -> str:
    """Write a number the way this file already writes it.

    MW4 stores volumes and scales with six decimal places — ``0.750000``. A UI
    slider sends ``0.5``, and writing that verbatim leaves the file carrying two
    formats for the same kind of value. The game parses both, but a config
    fpstune has half-reformatted is harder for a person to read afterwards, and
    a value that looks different from its neighbours reads as something fpstune
    got wrong.

    Only applies when the existing value is itself a decimal number. Anything
    else — ``Auto:300.000``, ``2560x1440``, ``aniso 16x`` — is left alone.
    """
    if "." not in existing:
        return value
    try:
        number = float(value)
        float(existing)
    except ValueError:
        return value

    decimals = len(existing.split(".", 1)[1])
    return f"{number:.{decimals}f}"


def _clear_readonly(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        if not mode & stat.S_IWRITE:
            path.chmod(mode | stat.S_IWRITE)
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("MW4 config read-only clear failed for %s: %s", path, exc)


# How many times a replace that Windows refuses is retried, and the pause that
# grows between attempts: 0.15, 0.30, ... about two seconds in all.
_REPLACE_ATTEMPTS = 6
_REPLACE_BACKOFF_S = 0.15


def _write_atomically(path: Path, payload: bytes) -> None:
    """Replace the file in one step, so an interrupted write cannot truncate it.

    The temp file is created beside the target because ``os.replace`` is only
    atomic within a filesystem.

    The name carries a random suffix so two writers can never pick the same one.
    That is belt to the lock's braces: with the lock held there is only ever one
    writer, and without a unique name a lock that failed open would turn a loud
    `Permission denied` into a silent half-written file.

    ``os.replace`` answers ``PermissionError`` (WinError 5) while another process
    holds the target open without FILE_SHARE_DELETE: an antivirus scanning the
    file the game just wrote, a sync client, the game itself between the
    running-game check and this write. Measured on 2026-09-02: one apply of
    ``game_config:mw4:dof_weapon`` failed exactly so, and the whole explanation
    the user got was the OS text in the system language. The retry covers the
    transient holder; the message names the persistent one.
    """
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.fpstune-tmp")
    try:
        temp.write_bytes(payload)
        for attempt in range(1, _REPLACE_ATTEMPTS + 1):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS:
                    raise
                time.sleep(_REPLACE_BACKOFF_S * attempt)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        raise PermissionError(
            f"{path.name} is held open by another program (the game, a sync client or an "
            "antivirus scan in progress), so it could not be replaced. Close it and apply again."
        ) from exc
    except OSError:
        temp.unlink(missing_ok=True)
        raise


def set_mw4_options(keys: Sequence[str], value: str, source: str = "global") -> str:
    """Write the same value to several keys that are one setting between them.

    MW4 keeps some controls under two scope indices — ``SSRQuality@0`` and
    ``SSRQuality@1`` hold the same value list and the same meaning. Writing only
    one leaves the concept half-applied, which is the shape C8 names a
    named-compound: several keys, one logical setting.

    Every key is validated before any is written, so a value the second key
    rejects cannot leave the first one changed.

    Returns the value written, or ``NOT_INSTALLED`` when no key was present.
    """
    if sys.platform != "win32":
        return NOT_INSTALLED

    for key in keys:
        _validate(key, value, source)

    written: str | Any = NOT_INSTALLED
    for key in keys:
        result = set_mw4_option(key, value, source)
        if result != NOT_INSTALLED:
            written = result
    return str(written)


def set_mw4_option(key: str, value: str, source: str = "global") -> str:
    """Rewrite one ``Name@<scope>`` line in place and return the value written.

    Returns ``NOT_INSTALLED`` when the game, the file, or the key is absent —
    the same sentinel detection uses, so an uninstalled game is reported rather
    than failed.
    """
    if sys.platform != "win32":
        return NOT_INSTALLED

    if source == "both":
        # Every volume control lives in both files under the same scope index
        # and a different hash. Measured: changing the music volume in-game
        # wrote the new value to both, so writing one would be half-applied and
        # whichever copy the game prefers might not be the one fpstune touched.
        written: str | Any = NOT_INSTALLED
        for candidate in _SOURCES:
            result = set_mw4_option(key, value, candidate)
            if result != NOT_INSTALLED:
                written = result
        return str(written)

    path = _path_for(source)
    if path is None or not path.is_file():
        return NOT_INSTALLED

    pattern = _line_pattern(key)
    if pattern is None:
        logger.debug("MW4 key %r has no @<scope> suffix; refusing to guess", key)
        return NOT_INSTALLED

    value = _validate(key, value, source)

    # Read, modify and write under one lock. Reading outside it is the whole
    # defect: two writers that both read the pre-change file each rewrite it
    # from their own stale copy, and the second one silently drops the first
    # one's setting. The cache refresh belongs inside too — it is what the
    # follow-up detect verifies against, so a refresh from stale text would
    # confirm a value that is not in the file.
    with _file_lock(source):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            logger.debug("MW4 config read failed for %s: %s", path, exc)
            return NOT_INSTALLED

        had_bom = raw.startswith(codecs.BOM_UTF8)
        text = raw.decode("utf-8-sig" if had_bom else "utf-8", errors="replace")

        match = pattern.search(text)
        if match is None:
            logger.debug("MW4 key %r not present in %s", key, path.name)
            return NOT_INSTALLED

        existing = match.group("value")
        value = _match_number_format(existing, value)

        if existing == value:
            # Already there. Returning early keeps the file's mtime untouched,
            # which matters because mtime is how the newest-config glob picks a
            # winner — and after the format match above, `0.5` counts as already
            # there when the file holds `0.500000`.
            return value

        replacement = f"{match.group('head')}{value}{match.group('tail') or ''}"
        updated = text[: match.start()] + replacement + text[match.end() :]

        _clear_readonly(path)
        payload = (codecs.BOM_UTF8 if had_bom else b"") + updated.encode("utf-8")
        _write_atomically(path, payload)

        _refresh_cached(source, updated)

    logger.debug("MW4 %s: %s = %s", source, key, value)
    return value


def _refresh_cached(source: str, content: str) -> None:
    """Keep the per-scan snapshot in step with what is now on disk.

    Apply is followed immediately by a detect, and that detect reads the cache.
    Without this the verify step compares the new value against the pre-apply
    snapshot and reports a mismatch fpstune itself created.
    """
    from fpstune.settings.executors.game_config_cache import _CACHE_KEY
    from fpstune.settings.executors.ps_batch import _get_cache

    cache = _get_cache()
    if cache is None:
        return
    snapshot = cache.get(_CACHE_KEY)
    if isinstance(snapshot, dict):
        snapshot[f"mw4_{source}"] = content
