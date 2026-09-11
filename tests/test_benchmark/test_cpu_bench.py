"""Two numbers, and the traps that would make either of them a lie.

The workload is real work on the real processor — there is nothing to stub and
nothing worth stubbing — so what is tested here is the shape of the answer, not
its size: that the two legs are genuinely different measurements, that the block
is the same block every time, and that the thread count comes off the machine
rather than out of the source.

The one thing a test cannot check is that the numbers are right, so that was
done by hand on 2026-09-11: `zlib.compress` at level 1 over a 1 MB block ran
45.5 passes/s on one thread and 361 passes/s on sixteen — 7.94x on an eight-core
part with SMT, which is what an eight-core part gives and what a workload holding
the GIL could never show.
"""

from __future__ import annotations

import os

import pytest

from fpstune.benchmark.cpu_bench import CpuBench, _block
from fpstune.benchmark.suite import Bench


def _bench(**kwargs: object) -> CpuBench:
    defaults: dict = {"block_kb": 64, "iterations": 2}
    defaults.update(kwargs)
    return CpuBench(**defaults)  # type: ignore[arg-type]


class TestItRefusesAConfigurationThatCouldNotMeasure:
    def test_a_block_of_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to have anything to compress"):
            CpuBench(block_kb=0)

    def test_zero_iterations_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to time anything"):
            CpuBench(iterations=0)

    def test_it_satisfies_the_suite_protocol(self) -> None:
        assert isinstance(_bench(), Bench)

    def test_it_can_always_run(self) -> None:
        """Every machine has a processor, so there is no condition to arrange."""
        assert _bench().is_available() == (True, "")


class TestTheThreadCountComesOffTheMachine:
    def test_it_defaults_to_this_machines_own_thread_count(self) -> None:
        """A four-thread laptop and a thirty-two-thread desktop are the same
        code and different answers. A constant here is the hardcoded-buffer bug
        (C1) wearing a core count."""
        assert _bench().threads == os.cpu_count()

    def test_the_thread_count_reaches_the_result(self) -> None:
        """A reader comparing two machines' scaling has to know what it was
        scaled against."""
        assert _bench(threads=2).run(2).detail["threads"] == 2


class TestTheBlockIsTheSameBlockEveryTime:
    def test_two_calls_produce_identical_bytes(self) -> None:
        """zlib's work depends on what it is compressing. A fresh random block
        on each side of a comparison would put a different amount of work into
        each side and report the difference as a result."""
        assert _block(16) == _block(16)

    def test_the_block_is_the_size_it_was_asked_for(self) -> None:
        assert len(_block(16)) == 16 * 1024


class TestWhatItMeasures:
    def test_both_legs_produce_a_positive_throughput(self) -> None:
        readings = _bench().run(2).readings

        assert readings["cpu_single_core_ops"].median > 0
        assert readings["cpu_multi_core_ops"].median > 0

    def test_one_sample_per_repeat(self) -> None:
        for reading in _bench().run(3).readings.values():
            assert len(reading.samples) == 3

    def test_both_readings_know_which_way_is_better(self) -> None:
        """More work through the processor is the improvement, and a reading
        with no direction gets no verdict at all."""
        readings = _bench().run(2).readings

        assert readings["cpu_single_core_ops"].improves_upward is True
        assert readings["cpu_multi_core_ops"].improves_upward is True

    def test_the_all_thread_leg_is_not_the_single_thread_leg(self) -> None:
        """The GIL trap. A workload that held it would report the same figure
        twice and every machine would look single-core — which is the one thing
        `zlib.compress` was chosen to avoid.
        """
        readings = _bench(block_kb=256, iterations=4, threads=os.cpu_count() or 1).run(2)

        single = readings.readings["cpu_single_core_ops"].median
        multi = readings.readings["cpu_multi_core_ops"].median
        if (os.cpu_count() or 1) < 2:
            pytest.skip("a single-threaded machine cannot show scaling")
        assert multi > single

    def test_scaling_is_reported_as_detail_rather_than_as_a_third_reading(self) -> None:
        """It is derived from the two readings, so comparing it before and after
        would say nothing the pair does not already say — and a third number
        that moves whenever either of the other two does is how one finding
        becomes three on a panel (C11 rule 1)."""
        result = _bench().run(2)

        assert "scaling" in result.detail
        assert set(result.readings) == {"cpu_single_core_ops", "cpu_multi_core_ops"}

    def test_the_deadline_covers_both_legs_without_multiplying_by_the_thread_count(
        self,
    ) -> None:
        """The threads run at the same time, so the run takes as long as the
        slowest of them and not as long as their sum. Counting the sum would
        hand a thirty-two-thread machine a deadline that never fires."""
        few = CpuBench(block_kb=64, iterations=2, threads=2)
        many = CpuBench(block_kb=64, iterations=2, threads=32)

        assert few.timeout_seconds(3) == many.timeout_seconds(3)


class TestItIsNotSpawningCopiesOfFpstune:
    def test_the_parallel_leg_uses_threads_rather_than_processes(self) -> None:
        """fpstune ships frozen and calls `multiprocessing.freeze_support()`
        nowhere, so spawning re-runs the executable: a bench that spawned
        sixteen workers would open sixteen copies of fpstune, each of which
        would open sixteen more. The import list is the guard."""
        import fpstune.benchmark.cpu_bench as module

        source = module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as handle:
            text = handle.read()

        code = [
            line
            for line in text.splitlines()
            if line.startswith(("import ", "from ")) and "multiprocessing" in line
        ]
        assert code == []
