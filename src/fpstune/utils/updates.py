"""Is there a newer fpstune, asked without saying anything about this machine.

The check is a plain GET of the public releases endpoint. It sends no
identifier, no version, no hardware, no query string — the URL is a constant, so
there is nothing in the request that distinguishes one user's check from
another's beyond the fact that someone asked. That is the whole design: fpstune
has no telemetry, and a "check for updates" that quietly became one would be the
most obvious place to hide it.

It is also **off unless asked for**. A tool that reaches the network on startup
without being told to is doing something the user did not choose, and on this
one that would contradict the promise in SECURITY.md. `fpstune update` asks;
nothing else does.

Failure is not an error. No network, GitHub down, rate limited, behind a proxy
that blocks it — none of those are worth interrupting anyone over, so they all
answer "could not check" and the caller says so plainly rather than pretending
to know the answer is "up to date".
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from fpstune import __version__

logger = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/sungurerdim/fpstune/releases/latest"
RELEASES_PAGE = "https://github.com/sungurerdim/fpstune/releases"

_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class UpdateCheck:
    """What the check found, including "nothing, and here is why"."""

    current: str
    latest: str | None = None
    url: str = RELEASES_PAGE
    error: str | None = None

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

    return UpdateCheck(
        current=__version__,
        latest=tag,
        url=str(payload.get("html_url") or RELEASES_PAGE),
    )
