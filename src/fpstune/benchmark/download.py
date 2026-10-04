"""The one way a benchmark tool reaches this machine: pinned, hashed, whole.

Every tool a bench downloads is a program fpstune is about to run elevated, so
three rules hold for all of them and live here once rather than in each module:

* **Pinned, never "latest".** The URL names one release and the SHA-256 beside
  it names one file. A release API answer is a promise about tomorrow; a hash is
  a fact about these bytes.
* **Bounded.** Every socket read has a timeout, so a stalled connection fails
  with a sentence instead of holding the operation lock forever.
* **Whole or absent.** Bytes land in ``<name>.part`` and are renamed into place
  only after the hash matched. An interrupted download leaves a ``.part`` the
  next attempt deletes, never a truncated executable that ``exists()`` reports
  as installed.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

#: Seconds any single connect or read may stall before the download is abandoned.
SOCKET_TIMEOUT_SECONDS = 30.0

_CHUNK = 1024 * 1024


class DownloadError(Exception):
    """A download that did not produce the pinned file. The message is user-facing."""


def part_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".part")


def fetch_verified(
    url: str,
    destination: Path,
    *,
    sha256: str,
    size: int | None = None,
    progress: Callable[[int], None] | None = None,
    timeout: float = SOCKET_TIMEOUT_SECONDS,
) -> None:
    """Download ``url`` to ``destination`` if and only if it hashes to ``sha256``.

    Raises `DownloadError` with a readable reason on any failure; ``destination``
    is then untouched and no ``.part`` is left behind.
    """
    if not url.startswith("https://"):
        raise DownloadError(f"refusing a download that is not https: {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = part_path(destination)
    partial.unlink(missing_ok=True)
    digest = hashlib.sha256()
    received = 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "fpstune"})
        with (
            urllib.request.urlopen(request, timeout=timeout) as response,  # noqa: S310 - https checked above
            open(partial, "wb") as handle,
        ):
            total = size or int(response.headers.get("Content-Length") or 0)
            while True:
                block = response.read(_CHUNK)
                if not block:
                    break
                handle.write(block)
                digest.update(block)
                received += len(block)
                if size is not None and received > size:
                    raise DownloadError(
                        f"the download grew past the pinned {size} bytes, so it was discarded"
                    )
                if progress is not None and total > 0:
                    progress(min(100, received * 100 // total))
    except DownloadError:
        partial.unlink(missing_ok=True)
        raise
    except (OSError, ValueError) as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"the download did not finish: {exc}") from exc

    if size is not None and received != size:
        partial.unlink(missing_ok=True)
        raise DownloadError(
            f"the download is {received} bytes and the pinned file is {size}, so it was discarded"
        )
    actual = digest.hexdigest()
    if actual != sha256.lower():
        partial.unlink(missing_ok=True)
        raise DownloadError(
            "the download does not match its pinned checksum "
            f"(expected {sha256.lower()}, got {actual}), so it was discarded unrun"
        )
    try:
        os.replace(partial, destination)
    except OSError as exc:
        with contextlib.suppress(OSError):
            partial.unlink()
        raise DownloadError(f"the verified download could not be put in place: {exc}") from exc
