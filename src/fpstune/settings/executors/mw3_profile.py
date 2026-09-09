"""Write a single MW3 (cod23) gamerprofile setting without disturbing anything else.

MW3 keeps two config files. Graphics live in ``options.4.cod23.cst`` at the
players directory; audio, input, aim and field of view live one level down, in a
per-account ``gamerprofile*.cst`` whose line shape is MW4's::

    Sprint Assist Delay KBM@0 = 400 // 0 to 12750

— the same ``Name@<scope> = value // range`` as cod26 without the ``;hash``
suffix. So it is written by the same engine (``game_config_writer``) rather than
by a second implementation of ``@scope`` handling: the LF endings, the BOM
round-trip, the read-only clear, the atomic replace with its retry, the lock
held across the whole read-modify-write and the refusal of a value the line's
own comment forbids all come from there, already proven on MW4.

Two things are specific to this file and live here.

**It is shared with a PowerShell writer.** ``mw3_texture_toggle`` in
``powershell_actions`` rewrites this same gamerprofile for HTTPStreamLimit, and
serializes on ``Global\\fpstune-mw3-gamerprofile-cst``. Taking a different mutex
name here would leave the two writers unserialized against each other, which is
the lost update the lock exists to prevent — so the name below is that one, and
a test holds them equal.

**Discovery must agree with that writer too.** Both pick the newest
``gamerprofile*.cst`` under the players directory, and both refuse a copy under
a ``mw3fix_backup`` directory: writing to a backup changes nothing for the game
while reporting success. The rule itself is in ``game_config_cache``.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextlib import AbstractContextManager

from fpstune.settings.executors.game_config_cache import (
    NOT_INSTALLED,
    get_mw3_profile_metadata,
    mw3_profile_path,
    refresh_cached_config,
)
from fpstune.settings.executors.game_config_writer import (
    ConfigValueRejected,
    LineConfigTarget,
    file_lock,
    write_config_line,
    write_config_lines,
)

# The name `powershell_actions._MUTEX_GROUPS` already uses for this file. Held
# as a constant rather than imported from there because that module is the
# heavyweight script table and this one is on the apply path; the equality is a
# test instead.
_MUTEX_NAME = "Global\\fpstune-mw3-gamerprofile-cst"

_SNAPSHOT_KEY = "mw3_profile"


class Mw3ValueRejected(ConfigValueRejected):
    """The requested value is outside what MW3's gamerprofile says the key accepts.

    Refused rather than written. What MW3 does with a value outside a range it
    documents has not been measured here — MW4 resets the key, which loses
    whatever the user had — and C1 does not allow finding out on a user's
    machine.
    """


def _target() -> LineConfigTarget:
    """Describe MW3's gamerprofile to the shared writer."""
    return LineConfigTarget(
        label="MW3 profile",
        mutex_name=_MUTEX_NAME,
        resolve_path=mw3_profile_path,
        metadata=get_mw3_profile_metadata,
        # Apply is followed immediately by a detect, and that detect reads the
        # per-scan snapshot. Without this the verify step compares the new value
        # against the pre-apply snapshot and reports a mismatch fpstune created.
        refresh=lambda text: refresh_cached_config(_SNAPSHOT_KEY, text),
        rejection=Mw3ValueRejected,
        # This game ships two schemas of the same file and both are live: one
        # account directory holds `Name@0 = value // range` and another, on the
        # same machine, holds the older `Name@ value // range` with a BOM. The
        # writer's `key_prefix` carries the whole argument for why that is safe
        # here and wrong for MW4.
        scope_optional=True,
    )


def _file_lock() -> AbstractContextManager[None]:
    """Hold the whole read-modify-write of MW3's gamerprofile."""
    return file_lock(_MUTEX_NAME)


def set_mw3_profile_option(key: str, value: str) -> str:
    """Rewrite one ``Name@<scope>`` line in place and return the value written.

    Returns ``NOT_INSTALLED`` when the game, the profile, or the key is absent —
    the same sentinel detection uses, so an uninstalled game is reported rather
    than failed.
    """
    if sys.platform != "win32":
        return NOT_INSTALLED
    return write_config_line(_target(), key, value)


def set_mw3_profile_options(keys: Sequence[str], value: str) -> str:
    """Write the same value to several keys that are one setting between them.

    MW3 keeps one aim-sensitivity multiplier per optic — ``ADS2xZoomSensitivity``
    through ``ADSHighZoomSensitivity`` — which are one concept between them (C8).
    Every key is validated before any is written, so a value the second key
    rejects cannot leave the first one changed.
    """
    if sys.platform != "win32":
        return NOT_INSTALLED
    return write_config_lines(_target(), [str(key) for key in keys], value)
