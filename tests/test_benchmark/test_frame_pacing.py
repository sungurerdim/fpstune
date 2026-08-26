"""The frame pacing bench has to measure pacing, and it did not at first.

Its first version timed the *work* inside each frame rather than the interval
between frames, which is a different quantity: a frame whose work takes 1 ms of
an 8.3 ms budget can still arrive late, and arriving late is the whole subject.
Two of the tests below exist because of that, and pin the interval rather than
the work.

Everything here runs at a tiny `seconds` so the suite stays fast. That is safe
for the shape of the output and not for the numbers, so nothing asserts a
timing value — only that the loop delivers what it claims to deliver, and that
its readings are the shape the suite can compare.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator

import pytest

from fpstune.benchmark.frame_pacing import FramePacingBench, _percentile, _wait_until
from fpstune.benchmark.suite import Bench, compare_runs, run_suite


@pytest.fixture
def fine_timer() -> Iterator[None]:
    """Hold a 1 ms timer period while a delivered cadence is asserted.

    The bench sleeps through ``kernel32.Sleep`` on purpose — the module
    docstring records that ``time.sleep`` could not see the timer-resolution
    setting class the bench exists for. The cost of that fidelity is that the
    cadence it delivers depends on the process-wide timer period: at the
    Windows default of 15.625 ms, ``Sleep`` overshoots a 20 ms budget to
    ~31 ms, the loop's absolute schedule then has every other deadline already
    in the past, the intervals alternate ~31 ms / ~0.5 ms, and the median
    lands near 15.8 ms — under a budget a paced loop can never legitimately
    beat. The cadence tests below were green only while some *other* process
    happened to hold the machine at 0.5 ms, and went red the day none did.

    So a test asserting a cadence requests the fine period itself, the way a
    game engine does, instead of inheriting whatever the rest of the machine
    leaves behind. ``timeEndPeriod`` withdraws exactly that request afterwards,
    so the system returns to whatever period its other processes still hold.
    Off Windows there is nothing to request: the bench's fallback path is
    ``time.sleep``, which is already high-resolution there.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes

    winmm = ctypes.WinDLL("winmm")
    assert winmm.timeBeginPeriod(1) == 0, "the host refused a 1 ms timer period"
    try:
        yield
    finally:
        winmm.timeEndPeriod(1)


def _quick(**kwargs: object) -> FramePacingBench:
    """Enough frames to have percentiles, few enough to finish instantly."""
    defaults: dict = {"target_fps": 200, "seconds": 0.1, "working_set_mb": 1, "chase_steps": 100}
    defaults.update(kwargs)
    return FramePacingBench(**defaults)  # type: ignore[arg-type]


class TestItRunsAnywhere:
    def test_it_never_declines(self) -> None:
        """The reason this bench was written: PresentMon needs a game, and 74
        claims went unmeasured because nothing else could speak to them."""
        assert _quick().is_available() == (True, "")

    def test_it_satisfies_the_suite_protocol(self) -> None:
        assert isinstance(_quick(), Bench)

    def test_a_target_with_no_deadline_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to have a deadline"):
            FramePacingBench(target_fps=0)

    def test_a_pass_with_no_frames_in_it_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive to have any frames"):
            FramePacingBench(seconds=0)


class TestWhatItMeasures:
    @pytest.fixture(scope="class")
    def result(self):
        return _quick().run(2)

    def test_it_reports_every_metric_the_suite_can_compare(self, result) -> None:
        assert set(result.readings) == {
            "pacing_interval_ms",
            "pacing_p99_ms",
            "pacing_p999_ms",
            "pacing_jitter_ms",
            "missed_frame_percent",
        }

    def test_one_sample_per_repeat_so_a_noise_floor_exists(self, result) -> None:
        """Two repeats, two samples, so `noise_floor` returns a number rather
        than infinity — which is the difference between a verdict and none."""
        for reading in result.readings.values():
            assert len(reading.samples) == 2
            assert reading.noise != float("inf")

    @pytest.mark.usefixtures("fine_timer")
    def test_frame_time_is_the_delivered_interval_not_the_work(self) -> None:
        """The bug this replaced. The work here is a fraction of a millisecond
        against a 20 ms budget, so timing the work would report ~0.1 ms and call
        it a frame time — blind to a loop running at any cadence at all.

        One-sided, and that is deliberate. A paced loop cannot beat its own
        target, so the interval can only be at or above the budget; a busy
        machine pushes it further up and can never make this fail. The earlier
        two-sided form went red on CI at 0.76 ms — which was the bench genuinely
        running unpaced, not the assertion being unlucky.

        `fine_timer` holds the period the assertion presumes: under the default
        15.625 ms tick the median alternates down to ~15.8 ms and this went red
        with the bench behaving exactly as designed (see the fixture).
        """
        result = _quick(target_fps=50, seconds=0.4).run(2)
        budget_ms = result.detail["frame_budget_ms"]

        assert result.readings["pacing_interval_ms"].median >= budget_ms * 0.8

    @pytest.mark.usefixtures("fine_timer")
    def test_a_slower_target_delivers_a_longer_interval(self) -> None:
        """The other half of the same bug: an interval that does not follow the
        target is not an interval.

        Both targets are slow enough to be reachable on a loaded runner, because
        an unpaced pass reports its work time and the two would then be equal.

        `fine_timer` for the same reason as the sibling above: with a 15.625 ms
        tick both cadences quantise to multiples of the tick and the ratio
        being asserted is the timer period's, not the target's.
        """
        fast = _quick(target_fps=100, seconds=0.2).run(2).readings["pacing_interval_ms"].median
        slow = _quick(target_fps=25, seconds=0.8).run(2).readings["pacing_interval_ms"].median

        assert slow > fast * 2

    def test_the_direction_of_every_metric_is_known(self, result) -> None:
        """A metric with no direction is dropped by `compare_runs` as unpaired,
        so a bench whose readings have none produces nothing comparable."""
        for reading in result.readings.values():
            assert reading.improves_upward is False

    def test_the_target_travels_with_the_result(self, result) -> None:
        """`missed_frame_percent` is meaningless without knowing what was
        missed, and a reader should never have to guess the denominator."""
        assert result.detail["target_fps"] == 200
        assert result.detail["frame_budget_ms"] == pytest.approx(5.0)

    def test_the_load_is_the_same_load_every_time(self) -> None:
        """The permutation is seeded, so the cache-miss pattern before a change
        is the cache-miss pattern after it. A fresh shuffle each run would put
        the seed into the difference."""
        first = _quick().run(2)
        second = _quick().run(2)

        assert first.detail["chase_steps"] == second.detail["chase_steps"]
        assert first.detail["working_set_mb"] == second.detail["working_set_mb"]


class TestTheWait:
    def test_it_holds_until_the_deadline_rather_than_past_it(self) -> None:
        """Overshooting is what a coarse timer does, and the spin exists to stop
        it: a frame loop that wakes 7 ms late has missed the frame it was
        waiting for and the one after.

        The bound is a whole frame at 60 Hz rather than something tight. A
        tighter one measures how busy the machine running the tests is — it went
        red at 2 ms on a loaded runner — and the failure this guards against is
        the wait returning a timer tick late, which is far larger than that.
        """
        deadline = time.perf_counter() + 0.02
        _wait_until(deadline)
        overshoot_ms = (time.perf_counter() - deadline) * 1000.0

        assert overshoot_ms >= 0, "returned before the deadline"
        assert overshoot_ms < 16.0, "returned a timer tick late"

    def test_a_deadline_already_past_returns_immediately(self) -> None:
        """A late frame must not wait out a whole extra period to catch up."""
        started = time.perf_counter()
        _wait_until(started - 1.0)

        assert (time.perf_counter() - started) < 0.05


class TestPercentiles:
    def test_it_names_a_frame_that_actually_happened(self) -> None:
        """Nearest-rank, not interpolated: p99.9 is supposed to be the worst
        frame, and interpolation invents a value between two real ones."""
        values = [float(n) for n in range(1, 101)]

        assert _percentile(values, 0.99) in values
        assert _percentile(values, 0.999) in values

    def test_the_top_percentile_is_the_worst_value(self) -> None:
        values = [1.0, 2.0, 99.0]
        assert _percentile(values, 0.999) == 99.0

    def test_the_median_percentile_sits_in_the_middle(self) -> None:
        assert _percentile([float(n) for n in range(1, 101)], 0.5) == 50.0

    def test_an_empty_list_is_refused_rather_than_returning_zero(self) -> None:
        """Zero would read as a perfect frame time all the way to the screen."""
        with pytest.raises(ValueError, match="no values"):
            _percentile([], 0.99)


class TestThroughTheSuite:
    def test_two_runs_of_it_compare(self) -> None:
        """End to end: the bench's readings are what `measure_pair` consumes, so
        a metric that moves is reported and one that does not is not."""
        before = run_suite([_quick()], "before", repeats=2)
        after = run_suite([_quick()], "after", repeats=2)

        comparison = compare_runs(before, after)

        assert {m.metric for m in comparison.measurements} == set(before.metrics)
        assert comparison.unpaired == []

    def test_a_slower_target_shows_up_as_a_moved_metric(self) -> None:
        """A deliberately large, known difference — if the bench cannot see the
        cadence halving, it cannot see anything a tweak would do either."""
        before = run_suite([_quick(target_fps=200)], "before", repeats=3)
        after = run_suite([_quick(target_fps=50)], "after", repeats=3)

        moved = {m.metric for m in compare_runs(before, after).moved}

        assert "pacing_interval_ms" in moved
