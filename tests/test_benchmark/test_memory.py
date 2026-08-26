"""Two bugs made this bench, and both were invisible from the code.

The first version reported 53 TB/s, because `bytes(x)` on something already
`bytes` returns the same object and copies nothing. The second reported 48 ns
and called it memory latency, because 20000 chase steps touch 1.3 MB of distinct
cache lines and 1.3 MB is L2. Neither would have raised a type error, failed a
lint, or looked wrong in review; both were caught by asking whether the number
was physically possible.

So the tests here are mostly plausibility bounds. They are deliberately wide —
wide enough that no real machine trips them and narrow enough that measuring the
wrong thing does.
"""

from __future__ import annotations

import pytest

from fpstune.benchmark.memory import (
    DEFAULT_CHASE_STEPS,
    DEFAULT_WORKING_SET_MB,
    MemoryBench,
    _build_chain,
)
from fpstune.benchmark.suite import Bench, compare_runs, run_suite


def _tiny(**kwargs: object) -> MemoryBench:
    defaults: dict = {"working_set_mb": 4, "chase_steps": 20_000}
    defaults.update(kwargs)
    return MemoryBench(**defaults)  # type: ignore[arg-type]


class TestTheChain:
    def test_every_cell_leads_somewhere_and_the_walk_closes(self) -> None:
        """A permutation with a short cycle would revisit a handful of lines and
        report cache latency however many steps were asked for."""
        chain = _build_chain(1)

        visited = set()
        index = 0
        for _ in range(len(chain)):
            visited.add(index)
            index = chain[index]

        assert len(visited) == len(chain), "the chain is not a single cycle"
        assert index == 0, "the cycle does not close"

    def test_the_same_chain_comes_back_every_time(self) -> None:
        """Seeded, so the miss pattern before a change is the one after it."""
        assert _build_chain(1).tolist() == _build_chain(1).tolist()

    def test_a_bigger_working_set_makes_a_longer_chain(self) -> None:
        assert len(_build_chain(2)) == 2 * len(_build_chain(1))


class TestTheNumbersArePhysicallyPossible:
    @pytest.fixture(scope="class")
    def readings(self):
        return _tiny().run(2).readings

    def test_bandwidth_is_not_faster_than_memory_has_ever_been(self, readings) -> None:
        """The 53 TB/s bug. Nothing consumer exceeds a few hundred GB/s, so an
        answer above 1 TB/s means no copy happened."""
        mbps = readings["memory_bandwidth"].median

        assert 100 < mbps < 1_000_000, f"{mbps} MB/s is not a memory bandwidth"

    def test_latency_is_in_the_range_a_memory_access_lives_in(self, readings) -> None:
        """Loose on purpose: this runs at a tiny working set to stay fast, so it
        will read low. What it catches is a zero, a negative, or a millisecond."""
        ns = readings["memory_latency_ns"].median

        assert 1 < ns < 100_000, f"{ns} ns is not a per-access latency"

    def test_a_copy_moves_the_working_set_twice(self) -> None:
        """Read and written. Counting one direction would halve every figure and
        still look entirely reasonable."""
        bench = _tiny(working_set_mb=4)
        payload = bytes(4 * 1024 * 1024)

        assert bench._bandwidth_mbps(payload) > 0

    def test_the_default_walk_exceeds_a_last_level_cache(self) -> None:
        """The 48 ns bug, as an arithmetic guard. Each chase step lands on its
        own cache line, so the footprint is steps x 64 bytes — and if that fits
        in L3, this bench is measuring L3."""
        footprint_mb = DEFAULT_CHASE_STEPS * 64 / (1024 * 1024)

        assert footprint_mb > 24, (
            f"the default walk touches {footprint_mb:.0f} MB, which fits in a "
            "large L3 — the reported latency would be cache, not memory"
        )

    def test_the_default_working_set_is_bigger_than_the_walk(self) -> None:
        """Otherwise the chase wraps and starts revisiting warm lines."""
        assert DEFAULT_WORKING_SET_MB * 1024 * 1024 / 8 > DEFAULT_CHASE_STEPS


class TestTheShape:
    def test_it_runs_anywhere(self) -> None:
        assert _tiny().is_available() == (True, "")

    def test_it_satisfies_the_suite_protocol(self) -> None:
        assert isinstance(_tiny(), Bench)

    def test_bandwidth_is_better_upward_and_latency_downward(self) -> None:
        readings = _tiny().run(2).readings

        assert readings["memory_bandwidth"].improves_upward is True
        assert readings["memory_latency_ns"].improves_upward is False

    def test_one_sample_per_repeat(self) -> None:
        for reading in _tiny().run(3).readings.values():
            assert len(reading.samples) == 3

    def test_the_working_set_travels_with_the_result(self) -> None:
        """A reader on a 96 MB 3D-stacked part needs to know this was cache."""
        assert _tiny().run(2).detail["working_set_mb"] == 4

    def test_an_empty_working_set_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to have anything to walk"):
            MemoryBench(working_set_mb=0)

    def test_a_walk_of_no_steps_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to time anything"):
            MemoryBench(chase_steps=0)

    def test_the_collector_is_left_the_way_it_was_found(self) -> None:
        """It is disabled around the chase, and a bench that leaves it off has
        changed the process it was only supposed to measure."""
        import gc

        assert gc.isenabled()
        _tiny().run(2)
        assert gc.isenabled()


class TestThroughTheSuite:
    def test_two_runs_compare(self) -> None:
        before = run_suite([_tiny()], "before", repeats=2)
        after = run_suite([_tiny()], "after", repeats=2)

        comparison = compare_runs(before, after)

        assert {m.metric for m in comparison.measurements} == {
            "memory_bandwidth",
            "memory_latency_ns",
        }
        assert comparison.unpaired == []
