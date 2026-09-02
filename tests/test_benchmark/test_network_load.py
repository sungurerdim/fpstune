"""Nothing here touches the network.

Both ends are module-level functions precisely so they can be replaced: a test
that reaches the internet fails for reasons that have nothing to do with the
code, and on CI it fails for reasons that have nothing to do with the machine
either. What is tested is the arithmetic and the refusals — whether a lost probe
is counted rather than dropped, whether a dead endpoint declines instead of
reporting a zero, and whether the download stops where it said it would.

The one thing these cannot check is that the numbers are right, so that was done
by hand: 81.7 Mbps down, 7 ms idle, 17.5 ms under load, +10.5 ms of bufferbloat
against a 4.7 ms noise floor.
"""

from __future__ import annotations

import time

import pytest

from fpstune.benchmark import network_load
from fpstune.benchmark.network_load import _LOST, NetworkLoadBench
from fpstune.benchmark.suite import Bench, run_suite


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """A default world: the probe answers in 10 ms, the endpoint sends 1 MB/s.

    Autouse so that a test which forgets to stub something still cannot open a
    socket — the failure would be a slow, confusing timeout rather than a clear
    one.

    The stub download takes a little real time so the loaded series usually
    holds more than one sample. It no longer *has* to: the bench takes its first
    loaded probe unconditionally, because waiting on the stop event first made
    the measurement depend on thread scheduling (see the regression test on an
    instant download below).
    """

    def _slow_download(_url: str, cap: int, _seconds: float) -> tuple[int, float]:
        time.sleep(0.05)
        return cap, cap / 1_000_000

    monkeypatch.setattr(network_load, "_tcp_rtt_ms", lambda *_a, **_k: 10.0)
    monkeypatch.setattr(network_load, "_download", _slow_download)


def _bench(**kwargs: object) -> NetworkLoadBench:
    defaults: dict = {"cap_bytes": 1_000_000, "cap_seconds": 1.0, "probes": 3, "probe_interval": 0}
    defaults.update(kwargs)
    return NetworkLoadBench(**defaults)  # type: ignore[arg-type]


class TestItSaysWhenItCannotRun:
    def test_a_silent_probe_host_declines_and_names_which_end(self, monkeypatch) -> None:
        monkeypatch.setattr(network_load, "_tcp_rtt_ms", lambda *_a, **_k: _LOST)

        available, why = _bench().is_available()

        assert available is False
        assert "probe host" in why

    def test_a_dead_endpoint_declines_rather_than_reporting_zero(self, monkeypatch) -> None:
        """Zero throughput and "we could not ask" are different answers, and
        only one of them is about the user's connection."""
        monkeypatch.setattr(network_load, "_download", lambda *_a: (0, 0.1))

        available, why = _bench().is_available()

        assert available is False
        assert "throughput endpoint" in why

    def test_the_availability_check_costs_a_kilobyte_not_a_download(self, monkeypatch) -> None:
        """It runs before every suite run. Spending 25 MB to find out the line
        is up would make checking more expensive than measuring."""
        asked: list[int] = []
        monkeypatch.setattr(
            network_load, "_download", lambda _url, cap, _s: (asked.append(cap), (cap, 0.1))[1]
        )

        _bench(cap_bytes=25_000_000).is_available()

        assert asked == [1024]

    def test_a_probe_count_that_cannot_express_loss_is_refused(self) -> None:
        with pytest.raises(ValueError, match="loss percentage"):
            NetworkLoadBench(probes=1)

    def test_a_download_of_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to download anything"):
            NetworkLoadBench(cap_bytes=0)

    def test_it_satisfies_the_suite_protocol(self) -> None:
        assert isinstance(_bench(), Bench)


class TestWhatItMeasures:
    def test_throughput_is_bytes_over_seconds_in_megabits(self) -> None:
        """8 megabits is one megabyte, and getting the factor wrong by eight is
        the kind of error that still looks like a plausible connection."""
        bench = _bench(cap_bytes=1_000_000)

        throughput = bench.run(1).readings["download_throughput"].median

        assert throughput == pytest.approx(8.0, rel=0.01)

    def test_bufferbloat_is_the_rise_and_not_the_loaded_figure(self, monkeypatch) -> None:
        """Reporting the loaded latency as bufferbloat would call a 7 ms line
        with no queueing a 7 ms bufferbloat problem."""
        answers = iter([5.0, 5.0, 5.0] + [25.0] * 50)
        monkeypatch.setattr(network_load, "_tcp_rtt_ms", lambda *_a, **_k: next(answers, 25.0))

        readings = _bench().run(1).readings

        assert readings["latency_under_load_ms"].median == pytest.approx(25.0)
        assert readings["bufferbloat_ms"].median == pytest.approx(20.0)

    def test_a_line_with_no_queueing_reports_no_bufferbloat(self, monkeypatch) -> None:
        monkeypatch.setattr(network_load, "_tcp_rtt_ms", lambda *_a, **_k: 10.0)

        assert _bench().run(1).readings["bufferbloat_ms"].median == pytest.approx(0.0)

    def test_a_lost_probe_under_load_is_counted_rather_than_dropped(self, monkeypatch) -> None:
        """Dropping it would report a clean 10 ms on a line that answered half
        the time — the loss is the finding."""
        answers = iter([10.0, 10.0, 10.0, _LOST, 20.0, _LOST, 20.0])
        monkeypatch.setattr(network_load, "_tcp_rtt_ms", lambda *_a, **_k: next(answers, 20.0))

        loss = _bench().run(1).readings["packet_loss_under_load"].median

        assert loss > 0

    def test_every_metric_knows_which_way_is_better(self) -> None:
        readings = _bench().run(1).readings

        assert readings["download_throughput"].improves_upward is True
        assert readings["latency_under_load_ms"].improves_upward is False
        assert readings["bufferbloat_ms"].improves_upward is False
        assert readings["packet_loss_under_load"].improves_upward is False

    def test_a_download_faster_than_the_first_probe_still_measures_under_load(
        self, monkeypatch
    ) -> None:
        """The pass used to be declined for a scheduling accident.

        An instant download set the stop event before the probe loop had taken
        one sample, so a pass that had downloaded fine reported "no loaded
        probe" — seen under pre-commit load on 2026-09-02, where the autouse
        stub's 50 ms head start was not enough. The first loaded probe is now
        taken unconditionally.
        """
        monkeypatch.setattr(network_load, "_download", lambda _url, cap, _s: (cap, cap / 1_000_000))

        result = _bench().run(1)

        assert result.ran is True, result.reason
        assert set(result.readings) == {
            "download_throughput",
            "latency_under_load_ms",
            "bufferbloat_ms",
            "packet_loss_under_load",
        }

    def test_one_sample_per_repeat(self) -> None:
        for reading in _bench().run(3).readings.values():
            assert len(reading.samples) == 3

    def test_it_says_how_much_it_downloaded(self) -> None:
        """The user paid for those bytes and is entitled to the figure."""
        detail = _bench(cap_bytes=2_000_000).run(2).detail

        assert detail["megabytes_downloaded"] == pytest.approx(3.8, abs=0.1)

    def test_it_says_the_number_is_one_stream_to_one_host(self) -> None:
        """A single TCP stream is not a line's rating, and a reader comparing
        this to their subscription needs to be told so."""
        assert "one TCP stream" in _bench().run(1).detail["note"]

    def test_the_endpoint_is_a_parameter_rather_than_a_fact(self) -> None:
        """A user on a restricted network has to be able to point it elsewhere."""
        bench = _bench(endpoint="https://example.invalid/pull?bytes={bytes}", cap_bytes=99)

        assert bench.url == "https://example.invalid/pull?bytes=99"


class TestWhenAPassProducesNothing:
    def test_a_download_that_returned_no_bytes_makes_the_bench_decline(self, monkeypatch) -> None:
        monkeypatch.setattr(network_load, "_download", lambda *_a: (0, 0.5))

        result = _bench().run(1)

        assert result.ran is False
        assert result.readings == {}

    def test_losing_every_idle_probe_declines_rather_than_guessing(self, monkeypatch) -> None:
        """With no baseline there is no bufferbloat to compute, and computing it
        against zero would report the whole loaded latency as a rise."""
        monkeypatch.setattr(network_load, "_tcp_rtt_ms", lambda *_a, **_k: _LOST)

        result = _bench().run(1)

        assert result.ran is False

    def test_the_suite_reports_the_decline_rather_than_dropping_it(self, monkeypatch) -> None:
        monkeypatch.setattr(network_load, "_download", lambda *_a: (0, 0.5))

        run = run_suite([_bench()], "before", repeats=2)

        assert len(run.results) == 1
        assert run.skipped[0].bench == "network_load"
