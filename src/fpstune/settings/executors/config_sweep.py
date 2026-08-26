"""Remove the blocks fpstune wrote for settings it no longer ships.

Deleting a setting deletes the only thing that knew its marker. Whatever that
setting already wrote into a game config stays there — orphaned, invisible to
detection because nothing looks for it any more, and impossible to undo through
the product because the code that could have removed it is gone.

This is not hypothetical and not a one-off. A CS2 autoexec.cfg audited on
2026-08-23 held 23 fpstune marker blocks and 12 of them were orphaned: eleven
from the dead-cvar removal, plus ``snd_mixahead``, dropped on 2026-08-11 and
still sitting in the file three months later. They accumulate silently with
every release that removes a setting, and the machine goes on being told it is
optimised by a line the game does not parse.

So the sweep is a product feature rather than a hand edit, and it is the same
shape as consequence 2's drift guard: reaching the ceiling means removing our
own leftovers as readily as someone else's.

Two traps found while doing this by hand, both worth the care they get here:

*The BOM eats the first block.* autoexec.cfg is written through
``[System.Text.Encoding]::UTF8`` from PowerShell, which emits a byte-order mark.
The first block therefore begins BOM + ``//``, and a ``^[ \\t]*//`` anchor misses
it — silently, and only ever for block one. The first hand-run sweep reported
23 of 24 blocks and left ``cl_forcepreload 1`` in the file while claiming
success.

*Own the markers from the registry, never from a list.* ``live_markers()`` reads
the shipped settings, so "orphaned" means "nothing ships this any more" by
construction. A hand-written list of dead markers would go stale on the next
removal, which is the defect itself.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import re
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKUP_SUFFIX = ".fpstune-backup"

# The same mutex every CS2 setting writer holds — the `_MUTEX_GROUPS` key in
# powershell_actions that wraps the cs2_*_toggle scripts. The sweep is one more
# whole-file rewrite of autoexec.cfg, and bulk apply runs 16 settings in
# parallel: a sweep that reads while a toggle writes rebuilds the file from a
# stale copy and silently drops the toggle's block while both report success.
# One name, so the two writers serialize against each other, not just
# themselves; a test pins the spelling to powershell_actions' copy.
CS2_AUTOEXEC_MUTEX = "Global\\fpstune-cs2-autoexec-cfg"

_LOCK_TIMEOUT_MS = 15_000

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080

# Same-process fallback when there is no Windows mutex to take — never a silent
# no-op, because a lock that does nothing turns a loud collision into a silent
# lost update. Same shape as mw4_config._file_lock, for the same reason.
_fallback_lock = threading.Lock()


@contextlib.contextmanager
def _autoexec_lock() -> Iterator[None]:
    """Hold the whole read-modify-write of CS2's autoexec.cfg.

    Falls back to a process-local lock when the system mutex cannot be created
    — off Windows, or on any API failure. Weaker than the mutex, but it still
    covers the parallel bulk apply, which is where updates get lost.
    """
    if sys.platform != "win32":
        with _fallback_lock:
            yield
        return

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = (wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    handle = kernel32.CreateMutexW(None, False, CS2_AUTOEXEC_MUTEX)
    if not handle:
        logger.debug("CS2 autoexec mutex unavailable; serializing in-process only")
        with _fallback_lock:
            yield
        return

    try:
        waited = kernel32.WaitForSingleObject(handle, _LOCK_TIMEOUT_MS)
        # WAIT_ABANDONED means the previous holder died mid-write; the lock is
        # ours and the sweep re-reads the file, so take it and say so.
        if waited == _WAIT_ABANDONED:
            logger.debug("CS2 autoexec lock was abandoned by a previous holder")
        elif waited != _WAIT_OBJECT_0:
            raise TimeoutError(
                f"another writer held CS2's autoexec.cfg for over {_LOCK_TIMEOUT_MS // 1000}s"
            )
        try:
            yield
        finally:
            kernel32.ReleaseMutex(handle)
    finally:
        kernel32.CloseHandle(handle)


# One fpstune block, start marker through end marker.
#
# ``\ufeff`` is in both leading character classes for the BOM trap above. The
# back-reference is what makes a block a block: without it, an orphaned start
# marker would pair with the *next* setting's end marker and take a live block
# out with it.
_BLOCK = re.compile(
    r"[\ufeff \t]*//[ \t]*===fpstune-(?P<marker>[^\s=]+)-start==="
    r".*?"
    r"^[\ufeff \t]*//[ \t]*===fpstune-(?P=marker)-end===[ \t]*\r?\n?",
    re.MULTILINE | re.DOTALL,
)


def live_markers(registry: Any = None) -> set[str]:
    """Every marker a shipped setting still owns.

    Read off the settings themselves rather than listed here, so that removing a
    setting is all it takes to make its leftovers sweepable. Both spellings are
    read because both are used: ``apply_args["marker"]`` is what the write path
    uses and ``detect_args["batch_marker"]`` is what the batched read path uses,
    and a setting that carried only one would otherwise look orphaned.
    """
    if registry is None:
        # Reuse the warm registry singleton when one exists: it is the
        # authoritative set (it includes dynamically discovered settings, so a
        # dynamic setting that ever gains a marker is counted live rather than
        # swept). Peeked rather than built — `get_registry()` would trigger the
        # full hardware discovery in contexts that have no warm registry, and
        # every marker-carrying setting today is static, so the cheap build
        # below is a correct fallback.
        import fpstune.settings.registry_cache as registry_cache

        registry = registry_cache._registry
    if registry is None:
        from fpstune.settings.registry import SettingsRegistry

        registry = SettingsRegistry(discover_dynamic=False)

    markers: set[str] = set()
    for setting in registry.get_all():
        for source in (getattr(setting, "apply_args", None), getattr(setting, "detect_args", None)):
            if not source:
                continue
            for key in ("marker", "batch_marker"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    markers.add(value)
    return markers


def found_markers(text: str) -> list[str]:
    """Every fpstune block in this file, in the order it appears."""
    return [match.group("marker") for match in _BLOCK.finditer(text)]


def sweep_text(text: str, live: set[str]) -> tuple[str, list[str]]:
    """Return the file without its orphaned blocks, and which ones went.

    A pure function on purpose: the decision about what is orphaned is the part
    worth testing, and it should not need a Steam install to exercise.
    """
    removed: list[str] = []

    def _drop(match: re.Match[str]) -> str:
        marker = match.group("marker")
        if marker in live:
            return match.group(0)
        removed.append(marker)
        return ""

    swept = _BLOCK.sub(_drop, text)
    if removed:
        # Collapse the runs of blank lines the removals leave behind, so a file
        # swept twice does not drift further apart each time.
        swept = re.sub(r"\n{3,}", "\n\n", swept).rstrip() + "\n"
    return swept, removed


def cs2_autoexec_path() -> Path | None:
    """The managed autoexec.cfg, found the way the product finds it."""
    from fpstune.settings.executors.game_config_cache import CS2_CFG_DIR, _steam_library_paths

    for library in _steam_library_paths():
        cfg_dir = library / CS2_CFG_DIR
        if cfg_dir.is_dir():
            return cfg_dir / "autoexec.cfg"
    return None


def sweep_cs2_autoexec(*, dry_run: bool = True, registry: Any = None) -> dict[str, Any]:
    """Remove orphaned fpstune blocks from CS2's autoexec.cfg.

    Defaults to a dry run. The caller has to ask for the write, because this
    edits a file the user may also have edited by hand, and "show me first" is
    the only honest default for that.
    """
    path = cs2_autoexec_path()
    if path is None or not path.is_file():
        return {
            "path": str(path) if path else None,
            "status": "not_installed",
            "blocks": 0,
            "orphaned": [],
            "removed": [],
            "backup": None,
        }

    live = live_markers(registry)

    # The entire read-modify-write under one lock, shared with the CS2 setting
    # writers. Reading outside it is the whole defect: a sweep and a toggle
    # that both read the pre-change file each rewrite it from their own stale
    # copy, and the second one out silently drops the first one's block while
    # both report success. The dry-run read holds it too, so it never reports
    # from a file another writer is halfway through.
    with _autoexec_lock():
        text = path.read_text(encoding="utf-8-sig")
        present = found_markers(text)
        swept, orphaned = sweep_text(text, live)

        result: dict[str, Any] = {
            "path": str(path),
            "status": "clean" if not orphaned else ("would_remove" if dry_run else "removed"),
            "blocks": len(present),
            "orphaned": orphaned,
            "removed": [],
            "backup": None,
        }
        if dry_run or not orphaned:
            return result

        # Back up what this machine held, once. First write wins, for the same
        # reason safety/originals.py does it that way: the valuable copy is the
        # one from before fpstune first touched the file, and overwriting it on
        # a second sweep would replace that with a copy fpstune had already
        # edited.
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        result["backup"] = str(backup)

        # Written without a BOM. PowerShell's UTF8 encoding adds one and that
        # is what made block one unreachable; nothing here needs it, and the
        # game reads either.
        path.write_text(swept, encoding="utf-8")
        result["removed"] = orphaned

    logger.info("swept %d orphaned fpstune blocks from %s", len(orphaned), path)
    return result
