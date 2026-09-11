"""A bench that hangs must not hang everything behind it.

`run_suite` and `_stream_suite` both wrapped `bench.run` in a try/except and
nothing else. A bench that raises is handled well — `ran=False` with the reason,
and the suite carries on. A bench that never returns was handled not at all: the
SSE stream sat open, the scheduler's tick never ended, and the only visible
symptom was a progress bar that stopped moving.

PC-Check's `Wait-ProcessProgress` is the shape absorbed here — a deadline, a
kill on overrun, and a `finally` that runs on every path — plus the startup
sweep that clears tools a previous session left running.

Two things this deliberately does not do. It does not impose one timeout on
every bench: a 2-second frame-pacing pass and a 12-second download have
different notions of overdue, so each bench derives its own from its own
configuration. And it does not report a timeout as a failure to measure
*something* — it is `ran=False` with a reason naming the deadline, because C11
rule 3 does not make an exception for the cases we caused ourselves.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest

from fpstune.benchmark import benches as bench_registry
from fpstune.benchmark.suite import (
    BenchReading,
    BenchResult,
    SuiteRun,
    run_bench_with_deadline,
    run_suite,
)


class _SlowBench:
    """Sleeps far past its own deadline, and says when it was let go."""

    key = "slow"
    label = "A bench that does not come back"
    requires = "nothing"

    def __init__(self, sleep_for: float = 30.0, timeout: float = 0.2) -> None:
        self.sleep_for = sleep_for
        self.timeout = timeout
        self.terminated = threading.Event()
        self.started = threading.Event()

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def timeout_seconds(self, _repeats: int) -> float:
        return self.timeout

    def run(self, _repeats: int) -> BenchResult:
        self.started.set()
        time.sleep(self.sleep_for)
        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={"latency_ms": BenchReading("latency_ms", [1.0, 1.0], "ms")},
        )

    def terminate_child(self) -> None:
        self.terminated.set()


class _QuickBench:
    """A normal bench, so the suite can be shown to carry on past a timeout."""

    key = "quick"
    label = "A bench that answers"
    requires = "nothing"

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def timeout_seconds(self, _repeats: int) -> float:
        return 30.0

    def run(self, _repeats: int) -> BenchResult:
        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={"jitter_ms": BenchReading("jitter_ms", [1.0, 1.2], "ms")},
        )


class _SpawningBench:
    """Starts a real child process and hands it over to be killed."""

    key = "spawner"
    label = "A bench with a child process"
    requires = "nothing"

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def timeout_seconds(self, _repeats: int) -> float:
        return 0.4

    def run(self, _repeats: int) -> BenchResult:
        # A child that would outlive the test by minutes if nothing killed it.
        self.process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.process.wait()
        raise AssertionError("the child was never killed")

    def terminate_child(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()


class TestADeadlineIsEnforced:
    def test_a_bench_that_overruns_comes_back_as_not_run(self) -> None:
        bench = _SlowBench()

        result = run_bench_with_deadline(bench, 2)  # type: ignore[arg-type]

        assert result.ran is False
        assert result.bench == "slow"

    def test_the_reason_names_the_deadline_rather_than_guessing(self) -> None:
        """C11 rule 3: a bench that produced nothing says why, in the user's words."""
        result = run_bench_with_deadline(_SlowBench(timeout=0.2), 2)  # type: ignore[arg-type]

        assert "timed out" in result.reason
        assert "0.2" in result.reason or "0" in result.reason

    def test_the_call_returns_at_the_deadline_not_at_the_bench_s_leisure(self) -> None:
        """The whole point: the caller gets control back on time."""
        started = time.perf_counter()

        run_bench_with_deadline(_SlowBench(sleep_for=30.0, timeout=0.2), 2)  # type: ignore[arg-type]

        assert time.perf_counter() - started < 5.0

    def test_a_bench_that_finishes_in_time_is_untouched(self) -> None:
        bench = _QuickBench()

        result = run_bench_with_deadline(bench, 2)  # type: ignore[arg-type]

        assert result.ran is True
        assert result.readings["jitter_ms"].samples == [1.0, 1.2]

    def test_a_bench_that_raises_still_reports_its_own_reason(self) -> None:
        """The existing behaviour must survive the new wrapper."""

        class _Exploding(_QuickBench):
            key = "exploding"

            def run(self, _repeats: int) -> BenchResult:
                raise RuntimeError("the instrument fell over")

        result = run_bench_with_deadline(_Exploding(), 2)  # type: ignore[arg-type]

        assert result.ran is False
        assert "the instrument fell over" in result.reason


class TestTheChildProcessIsKilled:
    def test_the_bench_is_asked_to_let_its_child_go(self) -> None:
        bench = _SlowBench()

        run_bench_with_deadline(bench, 2)  # type: ignore[arg-type]

        assert bench.terminated.is_set()

    def test_a_real_child_process_does_not_outlive_the_deadline(self) -> None:
        """A terminate that reaches nothing is the bug wearing a fix."""
        bench = _SpawningBench()

        result = run_bench_with_deadline(bench, 2)  # type: ignore[arg-type]

        assert result.ran is False
        assert bench.process is not None
        # It was killed, not merely abandoned to finish its 120 seconds.
        assert bench.process.wait(timeout=10) != 0

    def test_a_bench_with_no_child_to_kill_is_not_asked_to(self) -> None:
        """`terminate_child` is optional; a pure-Python bench has no process."""

        class _NoChild(_QuickBench):
            key = "nochild"

            def timeout_seconds(self, _repeats: int) -> float:
                return 0.2

            def run(self, _repeats: int) -> BenchResult:
                time.sleep(10)
                raise AssertionError("unreachable")

        result = run_bench_with_deadline(_NoChild(), 2)  # type: ignore[arg-type]

        assert result.ran is False
        assert "timed out" in result.reason


class TestTheSuiteKeepsGoing:
    def test_one_bench_timing_out_does_not_end_the_run(self) -> None:
        run = run_suite([_SlowBench(), _QuickBench()], "before", repeats=2)  # type: ignore[list-item]

        assert isinstance(run, SuiteRun)
        assert [result.bench for result in run.results] == ["slow", "quick"]
        assert run.results[0].ran is False
        assert run.results[1].ran is True

    def test_the_timed_out_bench_still_appears_in_the_run(self) -> None:
        """A run of two benches reports two results, always."""
        run = run_suite([_SlowBench(), _QuickBench()], "before", repeats=2)  # type: ignore[list-item]

        assert len(run.results) == 2
        assert run.skipped[0].reason


class TestEveryShippedBenchDeclaresItsOwnDeadline:
    @pytest.mark.parametrize("entry", bench_registry.all_entries(), ids=lambda e: e.key)
    def test_it_has_one(self, entry: bench_registry.Entry) -> None:
        assert hasattr(entry.bench, "timeout_seconds"), (
            f"{entry.key} has no deadline, so it can hang the suite indefinitely"
        )

    @pytest.mark.parametrize("entry", bench_registry.all_entries(), ids=lambda e: e.key)
    def test_it_grows_with_the_repeat_count(self, entry: bench_registry.Entry) -> None:
        """Derived from the bench's own work, never a flat constant.

        A flat timeout is the same bug as a hardcoded buffer size: it is correct
        on the machine it was measured on and wrong on the one that runs the
        suite ten times over.
        """
        if getattr(entry.bench, "ignores_repeats", False):
            # A bench that reads a log measures once however many repeats it is
            # given — re-reading the same records is one measurement copied. Its
            # deadline still has to be derived from *something* it does, so the
            # rule becomes: more of its own work, more time. The opt-out is a
            # declared attribute rather than a silent flat number, so a bench
            # that simply forgot to derive its deadline still fails here.
            pytest.skip(f"{entry.key} declares that repeats do not change its work")

        few = entry.bench.timeout_seconds(2)
        many = entry.bench.timeout_seconds(10)

        assert many > few, f"{entry.key} gives 10 repeats no more time than 2"

    def test_a_bench_that_ignores_repeats_still_derives_its_deadline(self) -> None:
        """The opt-out above cannot become a way to ship a flat constant."""
        from fpstune.benchmark.boot_time import BootTimeBench

        assert BootTimeBench(occurrences=50).timeout_seconds(2) > BootTimeBench(
            occurrences=2
        ).timeout_seconds(2)

    @pytest.mark.parametrize("entry", bench_registry.all_entries(), ids=lambda e: e.key)
    def test_it_is_generous_enough_to_be_a_deadline_not_a_limit(
        self, entry: bench_registry.Entry
    ) -> None:
        """A deadline that a healthy bench trips is a broken feature."""
        assert entry.bench.timeout_seconds(2) >= 30.0

    def test_a_bench_configured_to_do_more_work_gets_more_time(self) -> None:
        """The derivation is from the bench's own parameters, provably."""
        from fpstune.benchmark.frame_pacing import FramePacingBench

        brief = FramePacingBench(seconds=1.0)
        lengthy = FramePacingBench(seconds=60.0)

        assert lengthy.timeout_seconds(3) > brief.timeout_seconds(3)


class TestTheStartupSweep:
    def test_the_names_come_from_the_benches_own_executables(self) -> None:
        """C9: a hardcoded list of tool names drifts the moment one is renamed.

        `presentmon.py` already knows what its executable is called, because it
        has to find it on disk; asking it is the derivation, and a second list
        somewhere else is the copy that goes stale.
        """
        from fpstune.benchmark.presentmon import PresentMonBenchmark

        names = bench_registry.tool_executable_names()

        assert names
        assert PresentMonBenchmark().presentmon_path.name.lower() in names

    def test_every_name_is_a_bare_executable_not_a_path(self) -> None:
        """A sweep matching on a path would miss a tool started from elsewhere."""
        for name in bench_registry.tool_executable_names():
            assert "\\" not in name and "/" not in name
            assert name.endswith(".exe")

    def test_the_names_are_lowercased_so_matching_is_case_insensitive(self) -> None:
        """Windows process names come back in whatever case the image carries."""
        for name in bench_registry.tool_executable_names():
            assert name == name.lower()

    def test_sweeping_with_nothing_running_is_not_an_error(self) -> None:
        from fpstune.benchmark.scheduler import sweep_leftover_tools

        assert sweep_leftover_tools(names=["fpstune-no-such-tool.exe"]) == 0
