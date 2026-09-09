"""Rewrite one ``Name@<scope>`` line of a game config file and nothing else.

Two Call of Duty titles keep their settings one per line, and the line carries
more than the value::

    TextureQuality@0;61129;7764 = 1 // 0 to 3       MW4 (cod26)
    Sprint Assist Delay KBM@0 = 400 // 0 to 12750   MW3 (cod23) gamerprofile

The suffix after ``@0`` is an opaque hash the game emitted — MW4 writes one,
MW3's gamerprofile does not — and the trailing comment is the file's own
statement of the valid range. Both are copied through untouched: this module
only ever replaces the text between ``= `` and the comment, on exactly one line.

Three properties of these files that a naive writer gets wrong, all measured:

* **Line endings are LF**, on Windows, in a file Windows wrote. ``write_text``
  would translate every one of them to CRLF and rewrite the whole file while
  reporting that one setting changed.
* **There is no BOM today**, but CS2's autoexec.cfg has one and a release build
  may. The read strips it and the write puts back exactly what was there.
* **The file may be read-only.** An earlier fpstune release set that attribute
  on MW3's options file and every in-game change silently reverted; the lock is
  cleared here and never set.

What is deliberately *not* here is which file to open, which mutex serializes
it, where the range comes from and which per-scan snapshot entry to refresh.
Each game answers those and hands the answers over as a `LineConfigTarget`.
That split is the whole point: MW3's gamerprofile reached this proven path the
day it was wired up, instead of growing a second implementation of ``@scope``
handling to get wrong in its own way.
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
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpstune.settings.applicability import NOT_INSTALLED
from fpstune.utils.logger import get_logger

logger = get_logger()


class ConfigValueRejected(ValueError):
    """The requested value is outside what the file says the key accepts.

    Raised rather than written, because C1 forbids handing a game a value it
    will not accept — MW4 answers one by resetting the key, which loses whatever
    the user had.

    Each game subclasses this so its callers can name the game they are catching
    for; every caller that only wants "the file said no" catches this base.
    """


@dataclass(frozen=True)
class LineConfigTarget:
    """One config file, and everything about it this writer cannot derive.

    ``label`` names the file in the log and in nothing the user reads.
    ``resolve_path`` is called on every write rather than held, because the live
    file is chosen by discovery and a game update can move it mid-session.
    ``metadata`` answers with the range the file itself documents for a key, and
    ``refresh`` puts the rewritten text back into the per-scan snapshot the
    follow-up detect reads.
    """

    label: str
    mutex_name: str
    resolve_path: Callable[[], Path | None]
    metadata: Callable[[str], dict[str, Any]]
    refresh: Callable[[str], None]
    rejection: type[ConfigValueRejected]
    # Off by default, because making the scope digit optional is wrong for every
    # file except the one that needs it. See `key_prefix`.
    scope_optional: bool = False


# One mutex per config file, because one setting is one whole-file rewrite.
#
# Bulk apply runs settings in parallel — sixteen workers in
# `api/routes/settings.py`. Two of them writing the same file both read it
# before either writes, and the last one out replaces the file with a copy that
# never had the first one's change in it. Both then report success, because each
# verifies against the copy it wrote itself: apply green, verify green, setting
# absent. That is the same failure shape as the running-game overwrite
# `game_processes` guards against, arriving from inside the product instead.
#
# Measured 2026-08-24: `voice_volume` and `effects_volume` applied in the same
# second and collided on the shared temp path — `[Errno 13] Permission denied`
# and `[WinError 5]`. The filesystem caught what the code did not, and only
# because both writers happened to pick the same temp name.
#
# A named system mutex rather than a `threading.Lock`, matching what the
# PowerShell writers already use for exactly this
# (`powershell_actions._MUTEX_GROUPS` — CS2's autoexec, MW3's options.cst,
# HotS's Variables.txt). It holds across processes too, so a CLI run and the API
# cannot race each other over the same file — and a Python writer that shares a
# file with a PowerShell one shares its mutex name, or neither lock means
# anything.

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


def _take_system_mutex(name: str) -> tuple[Any, Any] | None:
    """Take the named system mutex, or answer None when there is none to take.

    None is not a failure to report: off Windows there is no such primitive, and
    on Windows the create call can still be refused. Both answers send the
    caller to the process-local fallback.

    Returning the API object alongside the handle keeps the release on the same
    ``kernel32`` the wait was made on, and keeps the whole Win32 surface of this
    module in one function — which is also what lets the caller be read on any
    platform instead of disappearing behind a ``sys.platform`` guard.
    """
    if sys.platform != "win32":
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = (wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        logger.debug("config mutex unavailable (%s); serializing in-process only", name)
        return None

    waited = kernel32.WaitForSingleObject(handle, _LOCK_TIMEOUT_MS)
    # WAIT_ABANDONED means the previous holder died mid-write. The lock is ours
    # and the file may be half-written, which the atomic replace below makes
    # impossible to observe — so take it and say so.
    if waited == _WAIT_ABANDONED:
        logger.debug("config lock %s was abandoned by a previous holder", name)
    elif waited != _WAIT_OBJECT_0:
        kernel32.CloseHandle(handle)
        raise TimeoutError(f"another writer held {name} for over {_LOCK_TIMEOUT_MS // 1000}s")
    return kernel32, handle


@contextlib.contextmanager
def file_lock(name: str) -> Generator[None, None, None]:
    """Hold the whole read-modify-write for one config file.

    Falls back to a process-local lock when the system mutex cannot be created
    — off Windows, or on any API failure. That is weaker than the mutex but it
    still covers the parallel bulk apply, which is where the loss was measured.
    """
    held = _take_system_mutex(name)
    if held is None:
        with _fallback_lock(name):
            yield
        return

    kernel32, handle = held
    try:
        yield
    finally:
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


# Every character Python treats as a line terminator, because the rewrite below
# splices the value into one line of the file and these games read one setting
# per line.
#
# This is the one rule that does not come from the file's own metadata, and it
# does not have to: a config line being a single line is a property of the
# format, not of any particular key. `Resolution@0` and `RefreshRate@0` ship
# without a `// range` comment, so absent authority means the value is written
# as given — and a value carrying a newline would have written arbitrary extra
# keys into the game's config. Inventing bounds for those keys would be the
# hardcoded-constant bug C9 names; refusing a value that is not one line is not.
_LINE_BREAK = re.compile("[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]")


def key_prefix(key: str, *, scope_optional: bool = False) -> str | None:
    """Regex source for ``Name@<scope>`` up to and including the separator.

    One builder for both halves of the round trip: the reader in
    ``game_config_cache`` and the writer below match the same prefix and differ
    only in what they capture after it. Two spellings of this would be two
    chances to accept a line one half cannot write back.

    The ``;hash`` suffix is optional because MW4 writes one and MW3's
    gamerprofile does not; where it exists it is matched loosely and never
    rebuilt.

    ``scope_optional`` is **MW3's gamerprofile and nothing else**, and it is not
    a tolerance — it is a second schema that is live today. One account
    directory holds ``Sprint Assist Delay KBM@0 = 400 // 0 to 12750`` and
    another, on the same machine, holds the older ``Sprint Assist Delay
    KBM@ 400 // 0 to 12750``: no scope digit, and a single space where the
    newer file writes ``=``. Discovery picks the newest by modification time,
    so either can be the live file on any given day.

    It stays off for MW4 because there the scope index is part of the key's
    identity: ``DxrMode@0`` is the Off/On master switch and ``DxrMode@1`` is
    the Off..Ultra quality level. Optional there, one setting would match the
    other's line and write it a value MW4 answers by resetting the key. It is
    safe for MW3 because neither of that game's profile schemas declares a key
    name twice, which
    ``tests/test_executors/test_mw3_profile.py::TestTheOlderSchemaIsReadAndWrittenToo::test_neither_schema_repeats_a_key_name``
    holds. A digit that *is* present must still agree either way.
    """
    name, sep, scope = key.rpartition("@")
    if not sep or not scope.isdigit():
        return None
    scope_source = f"(?:{scope})?" if scope_optional else scope
    separator = r"(?:[ \t]*=[ \t]*|[ \t]+)" if scope_optional else r"[ \t]*=[ \t]*"
    return rf"[ \t]*{re.escape(name)}@{scope_source}(?:;[^\s=]*)?{separator}"


def line_pattern(key: str, *, scope_optional: bool = False) -> re.Pattern[str] | None:
    """Match one ``Name@<scope>`` assignment, capturing what must survive.

    Group ``head`` is everything up to and including the separator; ``value``
    is the value; ``tail`` is the trailing comment with its leading whitespace.
    Only ``value`` is replaced, so a line written in the older scope-less shape
    comes back out in it.
    """
    prefix = key_prefix(key, scope_optional=scope_optional)
    if prefix is None:
        return None
    return re.compile(rf"(?m)^(?P<head>{prefix})(?P<value>.*?)(?P<tail>[ \t]*\/\/.*)?$")


def validate_config_value(target: LineConfigTarget, key: str, value: str) -> str:
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
        raise target.rejection(f"{key}: a config value must be one line, got {value!r}")

    meta: dict[str, Any] = target.metadata(key)
    if not meta:
        return value

    choices = meta.get("choices")
    if choices is not None:
        # Case-insensitive on the way in because the file mixes conventions
        # freely — `QUALITY_LOW` beside `Low Quality` beside `aniso 8x`.
        for choice in choices:
            if str(choice).casefold() == value.casefold():
                return str(choice)
        raise target.rejection(f"{key}: {value!r} is not one of {choices}")

    low, high = meta.get("minimum"), meta.get("maximum")
    if low is None or high is None:
        return value
    try:
        numeric = float(value)
    except ValueError:
        raise target.rejection(f"{key}: {value!r} is not numeric, range is {low}..{high}") from None
    if not (float(low) <= numeric <= float(high)):
        raise target.rejection(f"{key}: {value!r} is outside {low}..{high}")
    return value


def _match_number_format(existing: str, value: str) -> str:
    """Write a number the way this file already writes it.

    Both games store volumes, sensitivities and scales with six decimal places —
    ``0.750000``, ``0.850000``. A UI slider sends ``0.5``, and writing that
    verbatim leaves the file carrying two formats for the same kind of value.
    The game parses both, but a config fpstune has half-reformatted is harder
    for a person to read afterwards, and a value that looks different from its
    neighbours reads as something fpstune got wrong.

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
        logger.debug("config read-only clear failed for %s: %s", path, exc)


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


def target_lock(target: LineConfigTarget) -> AbstractContextManager[None]:
    """The lock that serializes every writer of this target's file."""
    return file_lock(target.mutex_name)


def write_config_line(target: LineConfigTarget, key: str, value: str) -> str:
    """Rewrite one ``Name@<scope>`` line in place and return the value written.

    Returns ``NOT_INSTALLED`` when the game, the file, or the key is absent —
    the same sentinel detection uses, so an uninstalled game is reported rather
    than failed.
    """
    path = target.resolve_path()
    if path is None or not path.is_file():
        return NOT_INSTALLED

    pattern = line_pattern(key, scope_optional=target.scope_optional)
    if pattern is None:
        logger.debug("%s key %r has no @<scope> suffix; refusing to guess", target.label, key)
        return NOT_INSTALLED

    value = validate_config_value(target, key, value)

    # Read, modify and write under one lock. Reading outside it is the whole
    # defect: two writers that both read the pre-change file each rewrite it
    # from their own stale copy, and the second one silently drops the first
    # one's setting. The cache refresh belongs inside too — it is what the
    # follow-up detect verifies against, so a refresh from stale text would
    # confirm a value that is not in the file.
    with target_lock(target):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            logger.debug("%s config read failed for %s: %s", target.label, path, exc)
            return NOT_INSTALLED

        had_bom = raw.startswith(codecs.BOM_UTF8)
        text = raw.decode("utf-8-sig" if had_bom else "utf-8", errors="replace")

        match = pattern.search(text)
        if match is None:
            logger.debug("%s key %r not present in %s", target.label, key, path.name)
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

        target.refresh(updated)

    logger.debug("%s: %s = %s", target.label, key, value)
    return value


def write_config_lines(target: LineConfigTarget, keys: list[str], value: str) -> str:
    """Write the same value to several keys that are one setting between them.

    A game keeps some controls under two scope indices — MW4's ``SSRQuality@0``
    and ``SSRQuality@1`` hold the same value list and the same meaning — and
    some under several names that move together, like MW3's six per-zoom
    sensitivity multipliers. Writing only one leaves the concept half-applied,
    which is the shape C8 names a named-compound: several keys, one logical
    setting.

    Every key is validated before any is written, so a value the second key
    rejects cannot leave the first one changed.

    Returns the value written, or ``NOT_INSTALLED`` when no key was present.
    """
    for key in keys:
        validate_config_value(target, key, value)

    written: str = NOT_INSTALLED
    for key in keys:
        result = write_config_line(target, key, value)
        if result != NOT_INSTALLED:
            written = result
    return written
