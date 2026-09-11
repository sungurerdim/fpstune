"""What the line does when it is busy, which is when a game is playing.

`network.py` measures a quiet connection: ping, jitter, loss and TCP connect
time with nothing else running. Those are real numbers and they are the easy
half. The half that decides whether a match feels bad is what happens when
something else on the line is downloading — because a queue that has filled up
with somebody else's traffic adds delay to every packet behind it, and the
player's packets are behind it.

That is bufferbloat, and it is not visible in an idle ping by construction. A
connection can show 12 ms at rest and 300 ms under its own upload, and the
second number is the one a game plays through. `NO_INSTRUMENT` listed
`throughput`, `download_throughput` and `bandwidth` as "no throughput test in
this build"; this closes all three and the bufferbloat question at the same
time, because they are the same measurement seen from two ends.

**How one pass works.** Probe the round trip a few times with the line quiet.
Start a bounded download. Probe again, at the same rate, while it runs. Then do
the whole thing again pushing bytes the other way. Report both throughputs, both
loaded latencies, and the rise the download caused.

**Why the upload leg is not optional.** The queue that a game's packets sit
behind is almost always the *upstream* one: a consumer line has ten times more
download than upload, so it is the upload that saturates first, and it is the
upload a voice chat, a cloud backup or a game's own telemetry fills. A
bufferbloat figure taken only under download describes the direction least
likely to be the problem.

**Three things this costs the user, all of them bounded and all of them said
out loud in `requires`:**

*Bandwidth.* A throughput test has to move real bytes. The download is capped in
both directions — by size and by seconds, whichever comes first — so a slow line
stops at the clock rather than at the byte count and nobody waits ten minutes to
find out their connection is slow.

*A third party.* Measuring throughput needs a server willing to send. The
endpoint is a parameter with a default rather than something buried, and a run
that cannot reach it declines with that reason rather than reporting a zero.

*A metered connection.* Windows knows, and now so does this: `INetworkCostManager`
— classic COM out of `netlistmgr.dll`, reachable through `ctypes` with no WinRT
and no PowerShell `Add-Type` — reports the cost flags on whichever connection the
internet is on. `Get-NetConnectionProfile` was checked first and carries no cost
field on this build (verified live 2026-09-11), and the registry's
`DefaultMediaCost` is the machine's default per media type rather than this
connection's actual state. Unrestricted means the automatic run may spend the
bytes; fixed, variable, roaming or over-limit means it may not; and a cost
nothing could read counts as "may not" — the honest direction, because the cost
of being wrong is the user's data allowance. A user who asks for the bench by
name still gets it.

**What the numbers are not.** Throughput measured over one connection to one
host is not the line's rating: a single TCP stream is limited by the path, the
window and the far end's willingness, and a modern line beats one stream easily.
It is a *repeatable* number on the same path, which is what a before/after
comparison needs and all it needs. The plan's own rule holds here — the
instrument is fixed and the load varies.
"""

from __future__ import annotations

import contextlib
import ctypes
import http.client
import os
import socket
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from ctypes import POINTER, byref, wintypes

from fpstune.benchmark.suite import BenchReading, BenchResult, deadline_for
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_ENDPOINT = "https://speed.cloudflare.com/__down?bytes={bytes}"
"""Where the bytes come from.

A purpose-built endpoint that exists to be downloaded from, rather than a large
file on somebody's server that was never offered for the job. Parameterised
because a user on a restricted network will have their own, and because pinning
a third party into the source is a dependency worth being able to replace.
"""

DEFAULT_UPLOAD_ENDPOINT = "https://speed.cloudflare.com/__up"
"""Where the bytes go.

The same service as the download leg and its documented counterpart: `__down`
takes a byte count in the query string because the server decides how much to
send, `__up` takes the bytes in the body because the client does. Verified live
2026-09-11 — a 2 MB POST answered 200 in 1.02 s. Parameterised for the same
reason the download endpoint is.
"""

DEFAULT_PROBE = ("1.1.1.1", 53)
"""What the round trip is measured against.

TCP rather than ICMP: `network.py` parses `ping.exe` output, which arrives in
the system language, and this has to run dozens of times inside a download
window. A SYN/SYN-ACK is one round trip and needs no parsing at all.
"""

DEFAULT_CAP_BYTES = 25 * 1024 * 1024
DEFAULT_UPLOAD_CAP_BYTES = 8 * 1024 * 1024
"""Smaller than the download cap, because the line is.

A consumer connection carries several times more download than upload, so asking
for 25 MB in both directions would spend most of the run's clock on the slower
half and still stop at the time cap. Eight megabytes is enough for the stream to
leave its slow start behind on any line worth measuring.
"""

DEFAULT_CAP_SECONDS = 12.0
"""Whichever comes first. The byte cap keeps a fast line from being asked for
more than it needs to prove itself; the time cap keeps a slow one from being
asked for more than the user's patience."""

DEFAULT_PROBES = 8
DEFAULT_PROBE_INTERVAL = 0.25
DEFAULT_PROBE_TIMEOUT = 2.0

_UNSPACED_PROBE_CEILING = 10_000
"""Bound on loaded probes when they are taken back to back.

Only reachable with `probe_interval=0`, which is a test setting; the bound is
there so the loop is finite whatever it is handed rather than because anything
is expected to hit it."""

_LOST = -1.0
"""A probe that never answered. Kept as a marker rather than dropped, because
loss under load is one of the things being measured."""

_USER_AGENT = "fpstune-benchmark"
"""Sent on every request, and not optional.

Measured 2026-08-24: the default `Python-urllib/3.x` gets a flat 403 from the
throughput endpoint, and the bench read that as "the line is down". Identifying
the caller is the polite thing anyway when the request is being made of somebody
else's server.
"""

_UPLOAD_BLOCK_BYTES = 64 * 1024
"""How much is handed to the socket at a time.

Random rather than a repeated pattern, and generated per block: the body travels
under TLS so nothing on the path could compress it anyway, but a bench that sent
a megabyte of zeroes would be one middlebox away from measuring a compression
ratio instead of a line.
"""

_NO_UPLOAD = "the upload moved no bytes, so there is no upload throughput to report"

_UNREACHABLE_PROBE = "the latency probe host did not answer, so there is no round trip to measure"
_UNREACHABLE_ENDPOINT = "the throughput endpoint could not be reached, so there is nothing to pull"
_NO_IDLE_BASELINE = "every idle probe was lost, so there is no baseline to compare a loaded one to"
_NO_BYTES = "the download returned no data, so there is no throughput to report"
_NO_LOADED_PROBE = (
    "the download finished before the line could be probed under it, so nothing "
    "was measured while it was busy"
)
"""A pass with no loaded probe is not a pass with no bufferbloat.

On a fast line a 25 MB download can be over in under a second, and if no probe
lands inside that window the arithmetic below happily reports a rise of zero —
"we measured no queueing" and "we never looked" wearing one number. This is the
second of the two; it declines.
"""


def _tcp_rtt_ms(host: str, port: int, timeout: float) -> float:
    """One round trip in milliseconds, or `_LOST`.

    The connection is closed immediately: what is being timed is the handshake,
    and holding the socket open would add the far end's teardown to the next
    probe.
    """
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return _LOST
    return (time.perf_counter() - started) * 1000.0


def _download(url: str, cap_bytes: int, cap_seconds: float) -> tuple[int, float]:
    """Pull up to the cap and return (bytes read, seconds spent).

    Read in chunks and checked against both caps every chunk, so a line that
    turns out to be far slower than expected stops on the clock instead of
    running to the byte count.
    """
    read = 0
    started = time.perf_counter()
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Cache-Control": "no-cache"}
    )
    try:
        with urllib.request.urlopen(request, timeout=cap_seconds) as response:  # noqa: S310
            while read < cap_bytes and (time.perf_counter() - started) < cap_seconds:
                chunk = response.read(65536)
                if not chunk:
                    break
                read += len(chunk)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.debug("Throughput download stopped early: %s", exc)
    return read, time.perf_counter() - started


def _upload(url: str, cap_bytes: int, cap_seconds: float) -> tuple[int, float]:
    """Push up to the cap and return (bytes written, seconds spent).

    `http.client` rather than `urllib.request`, because the caps have to hold
    mid-flight. `urlopen` wants the whole body up front and would either send
    all of it — a slow line uploading 8 MB is a run measured in minutes — or
    abandon the request with nothing to report. Writing block by block lets the
    clock stop the stream where it said it would, and the bytes already written
    are still a measurement.

    What `send` returns is what the kernel accepted, not what reached the far
    end, so the last socket buffer's worth is counted optimistically. At the
    sizes here that is well under a percent of the total, and the alternative —
    waiting for the response — cannot be had from a stream stopped on a clock.
    """
    parts = urllib.parse.urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    factory = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    connection = factory(parts.hostname or "", parts.port, timeout=cap_seconds)

    written = 0
    started = time.perf_counter()
    try:
        connection.putrequest("POST", path, skip_accept_encoding=True)
        connection.putheader("Content-Length", str(cap_bytes))
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("User-Agent", _USER_AGENT)
        connection.endheaders()

        # Timed from the first byte of the body rather than from the connect, so
        # the figure is throughput and not throughput-plus-a-TLS-handshake.
        started = time.perf_counter()
        while written < cap_bytes and (time.perf_counter() - started) < cap_seconds:
            block = os.urandom(min(_UPLOAD_BLOCK_BYTES, cap_bytes - written))
            connection.send(block)
            written += len(block)

        if written >= cap_bytes:
            # Only when the body was sent whole. A stream cut short by the clock
            # has left the far end waiting for bytes that are not coming, and
            # reading its response would wait out the timeout for nothing.
            with contextlib.suppress(OSError, http.client.HTTPException):
                connection.getresponse().read()
    except (OSError, http.client.HTTPException) as exc:
        logger.debug("Throughput upload stopped early: %s", exc)
    finally:
        connection.close()
    return written, time.perf_counter() - started


# --- Is this line metered? --------------------------------------------------

# NLM_CONNECTION_COST, from netlistmgr.h. Flags rather than an enum: a roaming
# connection that is also over its data limit reports both.
COST_UNKNOWN = 0x0
COST_UNRESTRICTED = 0x1
COST_FIXED = 0x2
COST_VARIABLE = 0x4
COST_OVER_DATA_LIMIT = 0x8
COST_CONGESTED = 0x10
COST_ROAMING = 0x20
COST_APPROACHING_DATA_LIMIT = 0x40

_COST_NAMES: tuple[tuple[int, str], ...] = (
    (COST_FIXED, "on a fixed data allowance"),
    (COST_VARIABLE, "charged by the byte"),
    (COST_OVER_DATA_LIMIT, "over its data limit"),
    (COST_APPROACHING_DATA_LIMIT, "close to its data limit"),
    (COST_ROAMING, "roaming"),
    (COST_CONGESTED, "congested"),
)

_CLSID_NETWORK_LIST_MANAGER = "{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"
_IID_NETWORK_COST_MANAGER = "{DCB00008-570F-4A9B-8D69-199FDBA5723B}"

_CLSCTX_ALL = 0x17
_COINIT_APARTMENTTHREADED = 0x2
_S_FALSE = 1
_RPC_E_CHANGED_MODE = -2147417850
"""The thread is already in a different apartment. Not a failure: the object can
still be created there, and the thread's initialisation is not ours to undo."""

_RELEASE_SLOT = 2
_GET_COST_SLOT = 3
"""`INetworkCostManager` derives straight from `IUnknown`, so its own methods
start at slot 3 and `GetCost` is the first of them."""

_COST_UNREADABLE = "cannot tell whether this connection is metered"


class _GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    )


def _connection_cost_flags() -> tuple[int | None, str]:
    """Windows' own cost flags for the connection the internet is on.

    `INetworkCostManager::GetCost` with a null destination address, which is the
    documented way to ask about the machine's internet connection rather than
    about the route to one host. Verified live on this machine, unelevated,
    2026-09-11: it returned `0x1`, unrestricted.

    Classic COM through `ctypes` and nothing else. WinRT's
    `NetworkInformation.GetConnectionCost` answers the same question and is not
    reachable without a WinRT bridge; PowerShell `Add-Type` is banned outright
    after Defender classified it as a trojan; and `Get-NetConnectionProfile`
    carries no cost field at all on this build.

    None with a reason rather than a guess when it cannot be read: the caller
    treats an unreadable cost as "do not spend the bytes".
    """
    if sys.platform != "win32":
        return None, f"{_COST_UNREADABLE} — Windows is the only system that reports one"

    try:
        ole32 = ctypes.WinDLL("ole32")
        ole32.CLSIDFromString.argtypes = (wintypes.LPCWSTR, POINTER(_GUID))
        ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
        ole32.CoCreateInstance.argtypes = (
            POINTER(_GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            POINTER(_GUID),
            POINTER(ctypes.c_void_p),
        )

        clsid, iid = _GUID(), _GUID()
        if ole32.CLSIDFromString(_CLSID_NETWORK_LIST_MANAGER, byref(clsid)) != 0:
            return None, f"{_COST_UNREADABLE} — the network list manager has no class id here"
        if ole32.CLSIDFromString(_IID_NETWORK_COST_MANAGER, byref(iid)) != 0:
            return None, f"{_COST_UNREADABLE} — the cost interface has no id here"

        initialised = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        must_uninitialise = initialised in (0, _S_FALSE)
        if not must_uninitialise and initialised != _RPC_E_CHANGED_MODE:
            return None, f"{_COST_UNREADABLE} — COM could not be started on this thread"

        try:
            manager = ctypes.c_void_p()
            created = ole32.CoCreateInstance(
                byref(clsid), None, _CLSCTX_ALL, byref(iid), byref(manager)
            )
            if created != 0 or not manager:
                return None, f"{_COST_UNREADABLE} — the network list manager did not answer"

            table = ctypes.cast(manager, POINTER(POINTER(ctypes.c_void_p))).contents
            get_cost = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, POINTER(wintypes.DWORD), ctypes.c_void_p
            )(table[_GET_COST_SLOT])
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[_RELEASE_SLOT])

            cost = wintypes.DWORD(COST_UNKNOWN)
            try:
                get_cost(manager, byref(cost), None)
            finally:
                release(manager)
        finally:
            if must_uninitialise:
                ole32.CoUninitialize()
    except (OSError, AttributeError, ValueError) as exc:
        logger.debug("Could not read the connection cost: %s", exc)
        return None, f"{_COST_UNREADABLE} — {exc}"

    return int(cost.value), ""


def unmetered_connection() -> tuple[bool, str]:
    """Whether the automatic run may spend this line's bytes, and why not if not.

    True only for a connection Windows calls unrestricted. Metered, roaming,
    over its limit, unknown and unreadable all answer False — an allowance spent
    by a daemon nobody asked is a cost the user never agreed to, and the whole
    point of the guard is that being wrong is expensive in one direction only.
    """
    flags, reason = _connection_cost_flags()
    if flags is None:
        return False, reason
    if flags == COST_UNKNOWN:
        return False, f"{_COST_UNREADABLE} — Windows reports its cost as unknown"

    named = [words for flag, words in _COST_NAMES if flags & flag]
    if named:
        return False, f"this connection is {', '.join(named)}"
    if flags & COST_UNRESTRICTED:
        return True, ""
    return False, f"{_COST_UNREADABLE} — Windows reports cost flags {flags:#x}"


class NetworkLoadBench:
    """Throughput, and what the round trip does while the line is busy."""

    key = "network_load"
    label = "Throughput and latency under load"
    requires = "an internet connection this may move about 25 MB down and 8 MB up over"

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        upload_endpoint: str = DEFAULT_UPLOAD_ENDPOINT,
        probe: tuple[str, int] = DEFAULT_PROBE,
        cap_bytes: int = DEFAULT_CAP_BYTES,
        upload_cap_bytes: int = DEFAULT_UPLOAD_CAP_BYTES,
        cap_seconds: float = DEFAULT_CAP_SECONDS,
        probes: int = DEFAULT_PROBES,
        probe_interval: float = DEFAULT_PROBE_INTERVAL,
    ) -> None:
        if cap_bytes <= 0:
            raise ValueError("cap_bytes has to be positive to download anything")
        if upload_cap_bytes <= 0:
            raise ValueError("upload_cap_bytes has to be positive to upload anything")
        if probes < 2:
            raise ValueError("probes below 2 cannot produce a loss percentage worth reading")
        self.endpoint = endpoint
        self.upload_endpoint = upload_endpoint
        self.probe = probe
        self.cap_bytes = cap_bytes
        self.upload_cap_bytes = upload_cap_bytes
        self.cap_seconds = cap_seconds
        self.probes = probes
        self.probe_interval = probe_interval

    def timeout_seconds(self, repeats: int) -> float:
        """Both transfer caps plus both probe schedules.

        `cap_seconds` is the ceiling each leg already imposes on itself, so this
        bench knows its cost exactly; the probes add their own interval, and
        there are two sets of them because there are two legs.
        """
        per_repeat = 2 * (self.cap_seconds + self.probes * self.probe_interval)
        return deadline_for(per_repeat, repeats)

    @property
    def url(self) -> str:
        return self.endpoint.format(bytes=self.cap_bytes)

    @property
    def upload_url(self) -> str:
        """Where the upload leg posts.

        No `{bytes}` to fill in, and that asymmetry is the protocol's rather
        than ours: the download endpoint is told how much to send because the
        server decides, and the upload endpoint is told nothing because the
        client decides — the size is the body. `format` is still applied so a
        user pointing this at their own endpoint may parameterise it the same
        way if theirs works differently.
        """
        return self.upload_endpoint.format(bytes=self.upload_cap_bytes)

    def is_available(self) -> tuple[bool, str]:
        """Both ends have to answer, and the answer names which one did not."""
        host, port = self.probe
        if _tcp_rtt_ms(host, port, DEFAULT_PROBE_TIMEOUT) == _LOST:
            return False, _UNREACHABLE_PROBE

        # A single chunk rather than the whole file: this runs before every
        # suite run and should not spend the user's bandwidth to find out the
        # endpoint is up.
        read, _ = _download(self.endpoint.format(bytes=1024), 1024, 5.0)
        if read <= 0:
            return False, _UNREACHABLE_ENDPOINT
        return True, ""

    def _probe_series(self, count: int, stop: threading.Event | None = None) -> list[float]:
        """`count` round trips, spaced, with lost ones marked rather than dropped."""
        samples: list[float] = []
        host, port = self.probe
        for _ in range(count):
            if stop is not None and stop.is_set():
                break
            samples.append(_tcp_rtt_ms(host, port, DEFAULT_PROBE_TIMEOUT))
            time.sleep(self.probe_interval)
        return samples

    def _probe_under(
        self, transfer: Callable[[], tuple[int, float]]
    ) -> tuple[tuple[int, float] | None, list[float]]:
        """Run one transfer and probe the line for exactly as long as it lasts.

        Shared by both directions, because the awkward part is the same in each:
        the probing has to stop when the transfer does, or a sample labelled
        "under load" is taken on a line that has gone quiet again.
        """
        moved: list[tuple[int, float]] = []
        loaded: list[float] = []
        stop = threading.Event()

        def work() -> None:
            try:
                moved.append(transfer())
            finally:
                # Always, including when the transfer raised: the probe loop
                # below waits on this, and a transfer that died silently would
                # otherwise keep it spinning to the cap.
                stop.set()

        ceiling = (
            max(1, int(self.cap_seconds / self.probe_interval))
            if self.probe_interval > 0
            else _UNSPACED_PROBE_CEILING
        )

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        try:
            # The first loaded probe is taken unconditionally. The transfer has
            # just started, so the sample is under load however quickly it ends
            # — and if it ended without bytes, the checks below refuse the pass
            # before this sample is ever read. Waiting on `stop` first made the
            # measurement depend on thread scheduling: on a busy machine a fast
            # download set the event before this thread took one sample, and a
            # pass that had downloaded fine was declined as "no loaded probe".
            # Seen in the test suite under pre-commit load, 2026-09-02.
            host, port = self.probe
            loaded.append(_tcp_rtt_ms(host, port, DEFAULT_PROBE_TIMEOUT))
            time.sleep(self.probe_interval)
            while not stop.is_set() and len(loaded) < ceiling:
                loaded.extend(self._probe_series(1, stop))
        finally:
            worker.join(timeout=self.cap_seconds + 5.0)

        return (moved[0] if moved else None), loaded

    def _one_pass(self) -> tuple[dict[str, float] | None, str]:
        """One measurement, or None and the reason there is not one."""
        idle = self._probe_series(self.probes)
        idle_answered = [value for value in idle if value != _LOST]
        if not idle_answered:
            return None, _NO_IDLE_BASELINE

        pulled, loaded = self._probe_under(
            lambda: _download(self.url, self.cap_bytes, self.cap_seconds)
        )

        if pulled is None:
            return None, _NO_BYTES
        downloaded, seconds = pulled
        if downloaded <= 0 or seconds <= 0:
            return None, _NO_BYTES
        if not loaded:
            return None, _NO_LOADED_PROBE

        loaded_answered = [value for value in loaded if value != _LOST]
        idle_median = statistics.median(idle_answered)
        loss_percent = (len(loaded) - len(loaded_answered)) / len(loaded) * 100.0

        # Every loaded probe lost is not a missing measurement — it is the worst
        # result this bench can report, and it is already in `loss_percent`.
        # What cannot be computed is the latency and the rise, so those carry
        # the idle figure and a zero rise while the loss carries the finding.
        loaded_median = statistics.median(loaded_answered) if loaded_answered else idle_median

        measured = {
            "throughput_mbps": (downloaded * 8) / seconds / 1_000_000,
            "idle_ms": idle_median,
            "loaded_ms": loaded_median,
            "bufferbloat_ms": loaded_median - idle_median,
            "loss_percent": loss_percent,
            "bytes": float(downloaded),
        }

        # The upload leg is measured second and is allowed to fail on its own.
        # A line whose download measured fine and whose upload did not has still
        # produced a download figure, and throwing the pass away over the half
        # that failed would report nothing about the half that worked. What it
        # does not do is go quiet: the reason reaches `detail` (C11 rule 3).
        pushed, under_upload = self._probe_under(
            lambda: _upload(self.upload_url, self.upload_cap_bytes, self.cap_seconds)
        )
        if pushed is not None and pushed[0] > 0 and pushed[1] > 0:
            uploaded, up_seconds = pushed
            answered_up = [value for value in under_upload if value != _LOST]
            measured["upload_mbps"] = (uploaded * 8) / up_seconds / 1_000_000
            measured["uploaded_bytes"] = float(uploaded)
            if answered_up:
                measured["under_upload_ms"] = statistics.median(answered_up)

        return measured, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        throughput: list[float] = []
        bufferbloat: list[float] = []
        loaded: list[float] = []
        loss: list[float] = []
        upload: list[float] = []
        under_upload: list[float] = []
        total_bytes = 0.0
        total_uploaded = 0.0

        for _ in range(repeats):
            pass_result, reason = self._one_pass()
            if pass_result is None:
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=reason,
                    duration_seconds=time.perf_counter() - started,
                )
            throughput.append(pass_result["throughput_mbps"])
            bufferbloat.append(pass_result["bufferbloat_ms"])
            loaded.append(pass_result["loaded_ms"])
            loss.append(pass_result["loss_percent"])
            total_bytes += pass_result["bytes"]
            if "upload_mbps" in pass_result:
                upload.append(pass_result["upload_mbps"])
                total_uploaded += pass_result["uploaded_bytes"]
            if "under_upload_ms" in pass_result:
                under_upload.append(pass_result["under_upload_ms"])

        readings = {
            "download_throughput": BenchReading(
                "download_throughput", throughput, "Mbps", higher_is_better=True
            ),
            # The number a player feels. Latency under load rather than at
            # rest, because at rest nothing is competing for the queue.
            "latency_under_load_ms": BenchReading(
                "latency_under_load_ms", loaded, "ms", higher_is_better=False
            ),
            "bufferbloat_ms": BenchReading(
                "bufferbloat_ms", bufferbloat, "ms", higher_is_better=False
            ),
            "packet_loss_under_load": BenchReading(
                "packet_loss_under_load", loss, "%", higher_is_better=False
            ),
        }

        detail: dict[str, object] = {
            "endpoint": self.endpoint,
            "upload_endpoint": self.upload_endpoint,
            "probe_host": f"{self.probe[0]}:{self.probe[1]}",
            "cap_bytes": self.cap_bytes,
            "upload_cap_bytes": self.upload_cap_bytes,
            "cap_seconds": self.cap_seconds,
            "megabytes_downloaded": round(total_bytes / (1024 * 1024), 1),
            "megabytes_uploaded": round(total_uploaded / (1024 * 1024), 1),
            "note": "one TCP stream to one host — repeatable, not the line's rating",
        }

        # One sample per repeat or none at all. A reading built from the two
        # passes out of three whose upload worked would carry a noise floor
        # drawn from a different number of observations than every other reading
        # in the same result, and `measure_pair` would compare it as though it
        # had not.
        if len(upload) == repeats:
            readings["upload_throughput"] = BenchReading(
                "upload_throughput", upload, "Mbps", higher_is_better=True
            )
        else:
            detail["upload_unmeasured"] = _NO_UPLOAD

        if len(under_upload) == repeats:
            # The upstream queue is the one a game's own packets sit behind, so
            # this is the direction most likely to be the problem — and it is a
            # different number from `latency_under_load_ms`, never a substitute.
            readings["latency_under_upload_ms"] = BenchReading(
                "latency_under_upload_ms", under_upload, "ms", higher_is_better=False
            )
        elif "upload_unmeasured" not in detail:
            detail["upload_latency_unmeasured"] = _NO_LOADED_PROBE

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings=readings,
            detail=detail,
            duration_seconds=time.perf_counter() - started,
        )
