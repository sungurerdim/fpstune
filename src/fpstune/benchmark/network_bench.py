"""The idle-line benchmark, wearing the suite's shape.

`network.py` has measured ping, jitter, loss and TCP connect time since long
before the suite existed, and measures them well. What it could not do was take
part in a before/after run: one reading per call, its own result type, no notion
of repeats and therefore no noise floor. So its numbers were shown and never
compared, and the only way to put two of them side by side was a separate
"Compare" screen that diffed two saved files by name.

This is an adapter, not a second implementation — the same relationship
`timing_bench.py` has with `dpc.py`. Every value still comes out of
`NetworkBenchmark.run_benchmark`; what is added is calling it `repeats` times and
handing the samples over in the shape `measure_pair` consumes.

It keeps the metric names `sources.py` already maps — `latency_ms`, `jitter_ms`,
`packet_loss` — so a setting claiming any of them is judged against the same
field it always was. The busy-line measurements live in `network_load.py` and
name themselves differently on purpose: an idle round trip and a round trip
under load are different quantities, and one name for both would let a claim
about one be confirmed by the other.
"""

from __future__ import annotations

import time

from fpstune.benchmark.network import NetworkBenchmark
from fpstune.benchmark.suite import BenchReading, BenchResult

DEFAULT_PING_COUNT = 20
"""Fewer than `network.py`'s own default of 50.

The suite runs this several times over, so the samples that matter are the
per-run medians rather than the pings inside one run — and fifty pings a repeat
turns a three-repeat suite into a two-minute wait for one of five benches.
"""

DEFAULT_TCP_COUNT = 10

_MEASUREMENT_FAILED = "the network benchmark returned nothing — the target did not answer"


class NetworkIdleBench:
    """Round trip, jitter and loss on a quiet line, made comparable."""

    key = "network"
    label = "Latency on an idle line"
    requires = "a reachable host to measure against"

    def __init__(
        self,
        *,
        target: str = "8.8.8.8",
        ping_count: int = DEFAULT_PING_COUNT,
        tcp_count: int = DEFAULT_TCP_COUNT,
        benchmark: NetworkBenchmark | None = None,
    ) -> None:
        self.target = target
        self.ping_count = ping_count
        self.tcp_count = tcp_count
        self._benchmark = benchmark or NetworkBenchmark()

    def is_available(self) -> tuple[bool, str]:
        """Answered by running rather than guessed at.

        A reachability check here would be a round trip to the same host the
        measurement is about to make twenty of, so it would cost what it saves.
        A target that does not answer surfaces as `ran=False` with the reason.
        """
        return True, ""

    def run(self, repeats: int) -> BenchResult:
        started = time.perf_counter()

        ping: list[float] = []
        jitter: list[float] = []
        loss: list[float] = []
        tcp: list[float] = []

        for _ in range(repeats):
            result = self._benchmark.run_benchmark(
                name="suite",
                target=self.target,
                ping_count=self.ping_count,
                tcp_count=self.tcp_count,
            )
            if result is None:
                # Not a partial result: a repeat that produced nothing has
                # nothing to be averaged with the ones that did, and a noise
                # floor computed from fewer samples than it claims is worse
                # than no noise floor.
                return BenchResult(
                    bench=self.key,
                    label=self.label,
                    ran=False,
                    reason=_MEASUREMENT_FAILED,
                    duration_seconds=time.perf_counter() - started,
                )

            stats = result.stats
            ping.append(stats.ping_avg)
            jitter.append(stats.jitter_avg)
            loss.append(stats.ping_loss_percent)
            tcp.append(stats.tcp_avg)

        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                "latency_ms": BenchReading("latency_ms", ping, "ms"),
                "jitter_ms": BenchReading("jitter_ms", jitter, "ms"),
                "packet_loss": BenchReading("packet_loss", loss, "%"),
                # TCP connect is a round trip through the same path that ICMP may
                # be deprioritised on, so it moves when ICMP does not. Named for
                # itself because no setting claims it.
                "tcp_connect_ms": BenchReading("tcp_connect_ms", tcp, "ms", higher_is_better=False),
            },
            detail={
                "target": self.target,
                "ping_count": self.ping_count,
                "tcp_count": self.tcp_count,
                "source": "fpstune.benchmark.network.NetworkBenchmark",
            },
            duration_seconds=time.perf_counter() - started,
        )
