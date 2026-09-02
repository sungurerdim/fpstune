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
Start a bounded download. Probe again, at the same rate, while it runs. Report
both, and the difference between them.

**Three things this costs the user, all of them bounded and all of them said
out loud in `requires`:**

*Bandwidth.* A throughput test has to move real bytes. The download is capped in
both directions — by size and by seconds, whichever comes first — so a slow line
stops at the clock rather than at the byte count and nobody waits ten minutes to
find out their connection is slow.

*A third party.* Measuring throughput needs a server willing to send. The
endpoint is a parameter with a default rather than something buried, and a run
that cannot reach it declines with that reason rather than reporting a zero.

*A metered connection.* Nothing here knows whether the line is metered, so this
bench never runs itself — the suite asks, and `requires` says what it will do
before it does it.

**What the numbers are not.** Throughput measured over one connection to one
host is not the line's rating: a single TCP stream is limited by the path, the
window and the far end's willingness, and a modern line beats one stream easily.
It is a *repeatable* number on the same path, which is what a before/after
comparison needs and all it needs. The plan's own rule holds here — the
instrument is fixed and the load varies.
"""

from __future__ import annotations

import socket
import statistics
import threading
import time
import urllib.error
import urllib.request

from fpstune.benchmark.suite import BenchReading, BenchResult
from fpstune.utils.logger import get_logger

logger = get_logger()

DEFAULT_ENDPOINT = "https://speed.cloudflare.com/__down?bytes={bytes}"
"""Where the bytes come from.

A purpose-built endpoint that exists to be downloaded from, rather than a large
file on somebody's server that was never offered for the job. Parameterised
because a user on a restricted network will have their own, and because pinning
a third party into the source is a dependency worth being able to replace.
"""

DEFAULT_PROBE = ("1.1.1.1", 53)
"""What the round trip is measured against.

TCP rather than ICMP: `network.py` parses `ping.exe` output, which arrives in
the system language, and this has to run dozens of times inside a download
window. A SYN/SYN-ACK is one round trip and needs no parsing at all.
"""

DEFAULT_CAP_BYTES = 25 * 1024 * 1024
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


class NetworkLoadBench:
    """Throughput, and what the round trip does while the line is busy."""

    key = "network_load"
    label = "Throughput and latency under load"
    requires = "an internet connection this may download about 25 MB over"

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        probe: tuple[str, int] = DEFAULT_PROBE,
        cap_bytes: int = DEFAULT_CAP_BYTES,
        cap_seconds: float = DEFAULT_CAP_SECONDS,
        probes: int = DEFAULT_PROBES,
        probe_interval: float = DEFAULT_PROBE_INTERVAL,
    ) -> None:
        if cap_bytes <= 0:
            raise ValueError("cap_bytes has to be positive to download anything")
        if probes < 2:
            raise ValueError("probes below 2 cannot produce a loss percentage worth reading")
        self.endpoint = endpoint
        self.probe = probe
        self.cap_bytes = cap_bytes
        self.cap_seconds = cap_seconds
        self.probes = probes
        self.probe_interval = probe_interval

    @property
    def url(self) -> str:
        return self.endpoint.format(bytes=self.cap_bytes)

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

    def _one_pass(self) -> tuple[dict[str, float] | None, str]:
        """One measurement, or None and the reason there is not one."""
        idle = self._probe_series(self.probes)
        idle_answered = [value for value in idle if value != _LOST]
        if not idle_answered:
            return None, _NO_IDLE_BASELINE

        loaded: list[float] = []
        stop = threading.Event()
        pulled: list[tuple[int, float]] = []

        def pull() -> None:
            try:
                pulled.append(_download(self.url, self.cap_bytes, self.cap_seconds))
            finally:
                # Always, including when the download raised: the probe loop
                # below waits on this, and a download that died silently would
                # otherwise keep it spinning to the cap.
                stop.set()

        # Probing runs only for as long as the download does, so no sample
        # labelled "loaded" is ever taken on a line that has gone quiet again.
        ceiling = (
            max(1, int(self.cap_seconds / self.probe_interval))
            if self.probe_interval > 0
            else _UNSPACED_PROBE_CEILING
        )

        puller = threading.Thread(target=pull, daemon=True)
        puller.start()
        try:
            # The first loaded probe is taken unconditionally. The download has
            # just started, so the sample is under load however quickly the pull
            # ends — and if the pull ended without bytes, the checks below refuse
            # the pass before this sample is ever read. Waiting on `stop` first
            # made the measurement depend on thread scheduling: on a busy machine
            # a fast download set the event before this thread took one sample,
            # and a pass that had downloaded fine was declined as "no loaded
            # probe". Seen in the test suite under pre-commit load, 2026-09-02.
            host, port = self.probe
            loaded.append(_tcp_rtt_ms(host, port, DEFAULT_PROBE_TIMEOUT))
            time.sleep(self.probe_interval)
            while not stop.is_set() and len(loaded) < ceiling:
                loaded.extend(self._probe_series(1, stop))
        finally:
            puller.join(timeout=self.cap_seconds + 5.0)

        if not pulled:
            return None, _NO_BYTES
        downloaded, seconds = pulled[0]
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

        return {
            "throughput_mbps": (downloaded * 8) / seconds / 1_000_000,
            "idle_ms": idle_median,
            "loaded_ms": loaded_median,
            "bufferbloat_ms": loaded_median - idle_median,
            "loss_percent": loss_percent,
            "bytes": float(downloaded),
        }, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        throughput: list[float] = []
        bufferbloat: list[float] = []
        loaded: list[float] = []
        loss: list[float] = []
        total_bytes = 0.0

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

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
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
            },
            detail={
                "endpoint": self.endpoint,
                "probe_host": f"{self.probe[0]}:{self.probe[1]}",
                "cap_bytes": self.cap_bytes,
                "cap_seconds": self.cap_seconds,
                "megabytes_downloaded": round(total_bytes / (1024 * 1024), 1),
                "note": "one TCP stream to one host — repeatable, not the line's rating",
            },
            duration_seconds=time.perf_counter() - started,
        )
