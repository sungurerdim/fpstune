"""The one place a user-profile root is resolved.

C9 says every path fpstune touches is discovered at runtime, never carried in
the source. This module is that discovery's single source for the roots that
live under a user's profile: the home directory, ``%LOCALAPPDATA%``,
``%APPDATA%`` and fpstune's own ``~/.fpstune``.

Why one module: a discovery function that reads ``%LOCALAPPDATA%`` itself
cannot be redirected by a test that did not know it was there. On 2026-10-06 a
sweep over every setting rewrote the developer's real Call of Duty options file
and Battle.net.config that way (#104). With every root resolved here, the test
suite points them all at a temporary tree in one fixture, and
``tests/test_user_paths.py`` fails on any module that reads one directly.

Every function reads the environment at call time, never at import, so a test's
``monkeypatch.setenv`` and the redirect both take effect.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The variables that name a user-profile root. Machine-wide ones (ProgramData,
#: SystemRoot, ProgramFiles) are not a user's profile and are not read here.
PROFILE_VARIABLES = ("LOCALAPPDATA", "APPDATA", "USERPROFILE")

_STATE_DIRECTORY = ".fpstune"


def profile_env(name: str) -> str | None:
    """A profile variable's value, or None when it is unset or blank."""
    value = os.environ.get(name)
    if not value:
        return None
    return value.strip() or None


def home() -> Path:
    """The account's home directory.

    Windows reads ``USERPROFILE`` (what the shell and the game launchers read);
    elsewhere the platform's own home.
    """
    if os.name == "nt":
        return Path(profile_env("USERPROFILE") or "~").expanduser()
    return Path.home()


def local_appdata() -> Path | None:
    """``%LOCALAPPDATA%``, or None when the environment did not answer."""
    value = profile_env("LOCALAPPDATA")
    return Path(value) if value else None


def roaming_appdata() -> Path | None:
    """``%APPDATA%``, or None when the environment did not answer."""
    value = profile_env("APPDATA")
    return Path(value) if value else None


def fpstune_home_path() -> Path:
    """``~/.fpstune``, the per-user state directory, without creating it."""
    return home() / _STATE_DIRECTORY


def fpstune_home() -> Path:
    """``~/.fpstune``, created if it does not exist yet."""
    folder = fpstune_home_path()
    folder.mkdir(parents=True, exist_ok=True)
    return folder
