"""Is there a newer fpstune, asked without saying anything about this machine.

The check is a plain GET of the public releases endpoint. It sends no
identifier, no version, no hardware, no query string — the URL is a constant, so
there is nothing in the request that distinguishes one user's check from
another's beyond the fact that someone asked. That is the whole design: fpstune
has no telemetry, and a "check for updates" that quietly became one would be the
most obvious place to hide it.

It is also **off unless asked for**. A tool that reaches the network on startup
without being told to is doing something the user did not choose, and on this
one that would contradict the promise in SECURITY.md. `fpstune update` and the
UI's update button ask; nothing else does.

Installing is just as deliberate. The release's own ``fpstune.exe.sha256`` is
fetched beside the executable and the download is refused unless they agree;
then the running executable is renamed aside (Windows allows renaming a running
image, not overwriting it) and the new one takes its name. The next start
removes the old copy. Nothing is executed during the update.

Failure is not an error. No network, GitHub down, rate limited, behind a proxy
that blocks it — none of those are worth interrupting anyone over, so they all
answer "could not check" and the caller says so plainly rather than pretending
to know the answer is "up to date".
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from fpstune import __version__

logger = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/sungurerdim/fpstune/releases/latest"
RELEASES_PAGE = "https://github.com/sungurerdim/fpstune/releases"

_TIMEOUT_SECONDS = 8
_DOWNLOAD_TIMEOUT_SECONDS = 60
_MAX_EXE_BYTES = 200 * 1024 * 1024
_EXE_ASSET = "fpstune.exe"
_SHA_ASSET = "fpstune.exe.sha256"


@dataclass(frozen=True)
class UpdateCheck:
    """What the check found, including "nothing, and here is why"."""

    current: str
    latest: str | None = None
    url: str = RELEASES_PAGE
    error: str | None = None
    exe_url: str | None = None
    sha256_url: str | None = None

    @property
    def reachable(self) -> bool:
        return self.latest is not None

    @property
    def update_available(self) -> bool:
        if self.latest is None:
            return False
        return _as_tuple(self.latest) > _as_tuple(self.current)


def _as_tuple(version: str) -> tuple[int, ...]:
    """Compare versions by their numbers, not as text.

    `"0.10.0" > "0.9.0"` is false as a string comparison and true as a version,
    and that is exactly the release where a naive check would start telling
    everyone they were up to date.
    """
    return tuple(int(part) for part in re.findall(r"\d+", version)) or (0,)


def check_for_update(timeout: float = _TIMEOUT_SECONDS) -> UpdateCheck:
    """Ask GitHub for the latest tag. Never raises."""
    request = urllib.request.Request(  # noqa: S310 - constant https URL
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            # Identifies the software, not the user or the machine. GitHub asks
            # for a User-Agent and rejects requests without one.
            "User-Agent": "fpstune",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return UpdateCheck(current=__version__, error=f"could not reach GitHub ({exc})")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return UpdateCheck(current=__version__, error=f"unreadable response ({exc})")

    tag = str(payload.get("tag_name") or "").lstrip("v").strip()
    if not tag:
        # A repository with no published release answers 404, which lands above.
        # This is the odder case of a release with no tag name.
        return UpdateCheck(current=__version__, error="the latest release has no version")

    assets = {
        str(a.get("name")): str(a.get("browser_download_url"))
        for a in payload.get("assets") or []
        if isinstance(a, dict) and a.get("browser_download_url")
    }
    return UpdateCheck(
        current=__version__,
        latest=tag,
        url=str(payload.get("html_url") or RELEASES_PAGE),
        exe_url=assets.get(_EXE_ASSET),
        sha256_url=assets.get(_SHA_ASSET),
    )


def _fetch(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "fpstune"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
        data: bytes = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{url} is larger than {limit} bytes")
    return data


def install_update(check: UpdateCheck, executable: Path | None = None) -> tuple[bool, str]:
    """Replace the running executable with the release ``check`` found.

    Only a packaged build updates itself; a source checkout updates with git.
    Returns (installed, message), the message being what to tell the user.
    """
    target = executable or Path(sys.executable)
    if executable is None and not getattr(sys, "frozen", False):
        return False, "A source checkout updates with git, not by replacing an executable."
    if not check.update_available:
        return False, "No newer release to install."
    if not check.exe_url or not check.sha256_url:
        return False, f"Release {check.latest} has no {_EXE_ASSET} with a checksum beside it."

    try:
        expected = _fetch(check.sha256_url, 4096).decode("ascii", "replace").split()[0].lower()
        binary = _fetch(check.exe_url, _MAX_EXE_BYTES)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, IndexError) as exc:
        return False, f"Download failed: {exc}"

    actual = hashlib.sha256(binary).hexdigest()
    if actual != expected:
        return False, "The download does not match its published checksum; nothing was changed."

    staged = target.with_name(target.name + ".new")
    previous = target.with_name(target.name + ".old")
    try:
        staged.write_bytes(binary)
        with contextlib.suppress(FileNotFoundError):
            previous.unlink()
        os.replace(target, previous)
        try:
            os.replace(staged, target)
        except OSError:
            os.replace(previous, target)
            raise
    except OSError as exc:
        with contextlib.suppress(OSError):
            staged.unlink()
        return False, f"Could not replace {target.name}: {exc}"
    return True, f"fpstune {check.latest} is installed. Close and reopen fpstune to use it."


def remove_replaced_executable(executable: Path | None = None) -> None:
    """Delete the copy an update renamed aside, once it is no longer running."""
    target = executable or Path(sys.executable)
    with contextlib.suppress(OSError):
        target.with_name(target.name + ".old").unlink()
