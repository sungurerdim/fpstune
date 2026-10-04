"""The pinned-download path every benchmark tool goes through.

Each test names the file that would otherwise end up on disk: a truncated
executable `exists()` calls installed, a tampered one run elevated, or a
download that hangs while holding the operation lock.
"""

from __future__ import annotations

import hashlib
import io
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from fpstune.benchmark import download
from fpstune.benchmark.download import DownloadError, fetch_verified, part_path

PAYLOAD = b"MZ" + bytes(range(256)) * 64
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
URL = "https://github.com/GameTechDev/PresentMon/releases/download/v2.5.1/PresentMon-2.5.1-x64.exe"


class _Response(io.BytesIO):
    def __init__(self, body: bytes, *, fail_after: int | None = None) -> None:
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}
        self._fail_after = fail_after

    def read(self, size: int | None = -1) -> bytes:  # type: ignore[override]
        if self._fail_after is not None and self.tell() >= self._fail_after:
            raise TimeoutError("The read operation timed out")
        if self._fail_after is not None and size is not None and size > 0:
            size = min(size, self._fail_after - self.tell())
        return super().read(size)

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"body": PAYLOAD, "fail_after": None, "timeouts": []}

    def fake_urlopen(_request: object, timeout: float | None = None) -> _Response:
        state["timeouts"].append(timeout)
        return _Response(state["body"], fail_after=state["fail_after"])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return state


@pytest.mark.usefixtures("served")
def test_a_verified_download_lands_whole_and_leaves_no_part(tmp_path: Path) -> None:
    target = tmp_path / "tools" / "PresentMon.exe"
    progress: list[int] = []

    fetch_verified(URL, target, sha256=PAYLOAD_SHA, size=len(PAYLOAD), progress=progress.append)

    assert target.read_bytes() == PAYLOAD
    assert not part_path(target).exists()
    assert progress[-1] == 100


def test_every_socket_operation_is_bounded(served, tmp_path: Path) -> None:
    """`urlretrieve` takes no timeout: a stalled server held the bench, and the
    operation lock with it, until the process was killed."""
    fetch_verified(URL, tmp_path / "x.exe", sha256=PAYLOAD_SHA)

    assert served["timeouts"] == [download.SOCKET_TIMEOUT_SECONDS]


def test_a_tampered_file_is_discarded_unrun(served, tmp_path: Path) -> None:
    served["body"] = PAYLOAD[:-1] + b"\x00"
    target = tmp_path / "PresentMon.exe"

    with pytest.raises(DownloadError, match="pinned checksum"):
        fetch_verified(URL, target, sha256=PAYLOAD_SHA)

    assert not target.exists()
    assert not part_path(target).exists()


def test_an_interrupted_download_never_replaces_a_good_copy(served, tmp_path: Path) -> None:
    """Writing straight to the destination left a truncated executable that
    `is_installed()` answered yes to."""
    target = tmp_path / "PresentMon.exe"
    target.write_bytes(b"the copy that was already here")
    served["fail_after"] = 1000

    with pytest.raises(DownloadError, match="did not finish"):
        fetch_verified(URL, target, sha256=PAYLOAD_SHA, size=len(PAYLOAD))

    assert target.read_bytes() == b"the copy that was already here"
    assert not part_path(target).exists()


def test_a_short_download_is_refused_by_size(served, tmp_path: Path) -> None:
    served["body"] = PAYLOAD[:100]
    with pytest.raises(DownloadError, match="bytes"):
        fetch_verified(URL, tmp_path / "x.exe", sha256=PAYLOAD_SHA, size=len(PAYLOAD))


def test_a_download_larger_than_pinned_stops_early(served, tmp_path: Path) -> None:
    served["body"] = PAYLOAD * 4
    with pytest.raises(DownloadError, match="grew past"):
        fetch_verified(URL, tmp_path / "x.exe", sha256=PAYLOAD_SHA, size=len(PAYLOAD))


@pytest.mark.usefixtures("served")
def test_a_stale_part_from_a_crash_is_replaced(tmp_path: Path) -> None:
    target = tmp_path / "PresentMon.exe"
    part_path(target).write_bytes(b"half of an earlier attempt")

    fetch_verified(URL, target, sha256=PAYLOAD_SHA)

    assert target.read_bytes() == PAYLOAD
    assert not part_path(target).exists()


def test_plain_http_is_refused(served, tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="https"):
        fetch_verified("http://example.com/x.exe", tmp_path / "x.exe", sha256=PAYLOAD_SHA)
    assert served["timeouts"] == []
