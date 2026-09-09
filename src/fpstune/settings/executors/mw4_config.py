"""Write a single MW4 (cod26) setting without disturbing anything else.

Everything about *how* one line is rewritten — the LF line endings, the BOM
round-trip, the read-only clear, the atomic replace and its retry, the lock held
across the whole read-modify-write, the refusal of a value the line's own
``// range`` comment forbids — lives in ``game_config_writer`` and is shared
with MW3's gamerprofile. What is here is only what is true of MW4 and of no
other file: which two files it keeps, that one key can live in both of them, and
the mutex name that serializes each.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path

from fpstune.settings.executors.game_config_cache import (
    MW4_SOURCES,
    NOT_INSTALLED,
    get_mw4_metadata,
    mw4_config_paths,
    refresh_cached_config,
)
from fpstune.settings.executors.game_config_writer import (
    ConfigValueRejected,
    LineConfigTarget,
    file_lock,
    validate_config_value,
    write_config_line,
    write_config_lines,
)

# One mutex per config file, because one MW4 setting is one whole-file rewrite
# and bulk apply runs sixteen of them in parallel. The reasoning, and the
# collision measured before the lock existed, are in `game_config_writer`; the
# names are here because they name MW4's own two files.
_MUTEX_NAMES = {
    "global": "Global\\fpstune-mw4-global-cst",
    "profile": "Global\\fpstune-mw4-profile-txt",
}


class Mw4ValueRejected(ConfigValueRejected):
    """The requested value is outside what MW4's own file says the key accepts.

    Raised rather than written, because C1 forbids handing the game a value it
    will not accept — MW4 answers one by resetting the key, which loses whatever
    the user had.
    """


def _path_for(source: str) -> Path | None:
    """One file. ``both`` is handled by the caller and never reaches here."""
    global_path, profile_path = mw4_config_paths()
    return global_path if source == "global" else profile_path


def _target(source: str) -> LineConfigTarget:
    """Describe one of MW4's two config files to the shared writer."""
    if source not in MW4_SOURCES:
        raise ValueError(f"unknown MW4 config source {source!r}")
    snapshot_key = f"mw4_{source}"
    return LineConfigTarget(
        label=f"MW4 {source}",
        mutex_name=_MUTEX_NAMES[source],
        resolve_path=lambda: _path_for(source),
        metadata=lambda key: get_mw4_metadata(key, source),
        # Apply is followed immediately by a detect, and that detect reads the
        # per-scan snapshot. Without this the verify step compares the new value
        # against the pre-apply snapshot and reports a mismatch fpstune created.
        refresh=lambda text: refresh_cached_config(snapshot_key, text),
        rejection=Mw4ValueRejected,
    )


def _file_lock(source: str) -> AbstractContextManager[None]:
    """Hold the whole read-modify-write for one of MW4's two config files."""
    return file_lock(_MUTEX_NAMES[source])


def set_mw4_options(keys: Sequence[str], value: str, source: str = "global") -> str:
    """Write the same value to several keys that are one setting between them.

    MW4 keeps some controls under two scope indices — ``SSRQuality@0`` and
    ``SSRQuality@1`` hold the same value list and the same meaning. Writing only
    one leaves the concept half-applied, which is the shape C8 names a
    named-compound: several keys, one logical setting.

    Every key is validated against every file it will be written to before any
    of them is written, so a value the second key rejects cannot leave the first
    one changed.

    Returns the value written, or ``NOT_INSTALLED`` when no key was present.
    """
    if sys.platform != "win32":
        return NOT_INSTALLED

    names = [str(key) for key in keys]
    sources = MW4_SOURCES if source == "both" else (source,)

    for candidate in sources:
        for key in names:
            validate_config_value(_target(candidate), key, value)

    written = NOT_INSTALLED
    for candidate in sources:
        result = write_config_lines(_target(candidate), names, value)
        if result != NOT_INSTALLED:
            written = result
    return written


def set_mw4_option(key: str, value: str, source: str = "global") -> str:
    """Rewrite one ``Name@<scope>`` line in place and return the value written.

    ``source="both"`` writes the keys MW4 keeps in *both* files: every volume
    control appears in the global file and again in the profile, under the same
    scope index and a different hash. Measured 2026-08-23: changing the music
    volume in-game wrote the new value to both, so writing one would be
    half-applied and whichever copy the game prefers might not be the one
    fpstune touched.

    Returns ``NOT_INSTALLED`` when the game, the file, or the key is absent —
    the same sentinel detection uses, so an uninstalled game is reported rather
    than failed.
    """
    if sys.platform != "win32":
        return NOT_INSTALLED

    if source == "both":
        written = NOT_INSTALLED
        for candidate in MW4_SOURCES:
            result = write_config_line(_target(candidate), key, value)
            if result != NOT_INSTALLED:
                written = result
        return written

    return write_config_line(_target(source), key, value)
