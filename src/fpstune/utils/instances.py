"""Finding the other fpstune APIs on this machine, and asking them to stop.

A new start closes the ones already running. The one rule that matters: an
instance is identified **only** by what its ``/health`` answers, never by
process name, window title or the text a system command prints (the previous
version matched netstat's English "LISTENING", which a Turkish or German Windows
never prints). A port that does not answer with fpstune's own health body is left
completely alone — it is somebody else's server. An instance that answers nothing
at all (hung, or its server gone) cannot be found this way; ``instance_reclaim``
handles that last, after this polite round.

Stopping is a request, not a kill: ``POST /api/system/shutdown`` makes the
instance run its own graceful shutdown (see ``api/shutdown.py``).

Everything here talks to ``127.0.0.1`` over plain HTTP with the system proxy
settings ignored, so a corporate proxy cannot turn a loopback probe into a
request to somebody else.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

LOOPBACK = "127.0.0.1"
HEALTH_PATH = "/health"
SHUTDOWN_PATH = "/api/system/shutdown"

SCAN_ATTEMPTS = 10
"""How many consecutive ports ``serve`` tries from its preferred one."""

PROBE_TIMEOUT_SECONDS = 1.5
STOP_TIMEOUT_SECONDS = 5.0

_HEALTH_BODY_LIMIT = 65536
_SUBSYSTEMS = frozenset({"registry", "powershell", "gpu_detection"})

# No proxies: the default opener honours the machine's proxy settings, and a
# loopback address is not guaranteed to be on a proxy bypass list.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass(frozen=True)
class StopAttempt:
    """What came back when one instance was asked to stop."""

    port: int
    status: int | None
    """The HTTP status, or None when nothing answered."""

    @property
    def accepted(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def describe(self) -> str:
        if self.accepted:
            return f"port {self.port}: asked to stop (HTTP {self.status})"
        if self.status is None:
            return f"port {self.port}: no answer to the stop request"
        return (
            f"port {self.port}: refused (HTTP {self.status}; an older fpstune has no stop request)"
        )


def is_fpstune_health(body: object) -> bool:
    """Whether a ``/health`` body is fpstune's own, field by field.

    A single key is a guess; the shape ``api/main.py`` returns is a signature:
    a status word, a version, a platform, an admin flag, and the subsystem
    probes by name.
    """
    if not isinstance(body, dict):
        return False
    subsystems = body.get("subsystems")
    return (
        body.get("status") in ("healthy", "degraded")
        and isinstance(body.get("version"), str)
        and isinstance(body.get("platform"), str)
        and isinstance(body.get("is_admin"), bool)
        and isinstance(subsystems, dict)
        and subsystems.keys() >= _SUBSYSTEMS
    )


def fetch_health(port: int, timeout: float = PROBE_TIMEOUT_SECONDS) -> object | None:
    """The parsed ``/health`` body of whatever listens on ``port``, or None."""
    try:
        with _opener.open(f"http://{LOOPBACK}:{port}{HEALTH_PATH}", timeout=timeout) as response:
            if response.status != 200:
                return None
            parsed: object = json.loads(response.read(_HEALTH_BODY_LIMIT).decode("utf-8"))
            return parsed
    except (OSError, ValueError, http.client.HTTPException):
        return None


def post_stop(port: int, timeout: float = STOP_TIMEOUT_SECONDS) -> int | None:
    """POST the stop request to ``port``; the HTTP status, or None when nothing answered."""
    request = urllib.request.Request(  # noqa: S310 - fixed http://127.0.0.1 URL
        f"http://{LOOPBACK}:{port}{SHUTDOWN_PATH}", data=b"", method="POST"
    )
    try:
        with _opener.open(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as refused:
        return refused.code
    except (OSError, http.client.HTTPException):
        return None


def candidate_ports(
    preferred: int, pid_file_port: int | None, attempts: int = SCAN_ATTEMPTS
) -> list[int]:
    """Every port an earlier fpstune could be serving on, most likely first.

    The PID file's port (written by the instance itself), then the range
    ``serve`` picks from: ``preferred`` and the next ``attempts - 1``.
    """
    ordered = [] if pid_file_port is None else [pid_file_port]
    ordered.extend(range(preferred, preferred + attempts))
    seen: set[int] = set()
    unique = []
    for port in ordered:
        if 0 < port < 65536 and port not in seen:
            seen.add(port)
            unique.append(port)
    return unique


def find_instances(ports: Iterable[int]) -> list[int]:
    """The ports among ``ports`` whose ``/health`` is fpstune's own, in the order given."""
    wanted = list(ports)
    if not wanted:
        return []
    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        bodies = list(pool.map(fetch_health, wanted))
    return [port for port, body in zip(wanted, bodies, strict=True) if is_fpstune_health(body)]


def stop_instances(ports: Iterable[int]) -> list[StopAttempt]:
    """Ask each instance to stop. Never raises: every outcome is in the result."""
    return [StopAttempt(port, post_stop(port)) for port in ports]
