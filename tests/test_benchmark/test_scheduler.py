"""The daemon that decides when to measure, and when to keep out of the way.

`headroom_watch` already answers "measure a game when one is running". This
answers the harder half: the synthetic benches need the machine *not* to be
doing anything, they change nothing themselves, and nobody is watching — so
every decision has to be defensible without a user to confirm it.

The guards are the substance. A synthetic bench that runs during a match steals
frames from the thing it exists to protect; one that runs during a bulk apply
measures a machine that is halfway between two states and cannot say which; one
that runs while the user is typing measures the typing. Each of those is a
number that looks exactly like a good one afterwards, which is why they are
refused at the source rather than filtered later.

`poll_once` is split out from the loop for the same reason it is in
`headroom_watch`: the decision is worth testing without waiting a minute for a
timer to come round.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpstune.benchmark import ledger as led
from fpstune.benchmark import scheduler as sched
from fpstune.benchmark.suite import BenchReading, BenchResult


class _FakeBench:
    """A bench that answers instantly, and remembers being asked."""

    def __init__(self, key: str, *, fails: int = 0) -> None:
        self.key = key
        self.label = f"{key} label"
        self.requires = "nothing"
        self.calls = 0
        self._fails = fails

    def is_available(self) -> tuple[bool, str]:
        return True, ""

    def timeout_seconds(self, _repeats: int) -> float:
        return 30.0

    def run(self, _repeats: int) -> BenchResult:
        self.calls += 1
        if self.calls <= self._fails:
            raise RuntimeError(f"{self.key} could not read the counter")
        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={"latency_ms": BenchReading("latency_ms", [1.0, 1.1], "ms")},
        )


@pytest.fixture
def benches() -> dict[str, _FakeBench]:
    return {"timing": _FakeBench("timing"), "memory": _FakeBench("memory")}


@pytest.fixture(autouse=True)
def quiet_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, benches: dict[str, _FakeBench]
) -> None:
    """An idle machine with no game running, its own ledger, and fake benches."""
    monkeypatch.setattr(led, "bench_dir", lambda: tmp_path)
    monkeypatch.setattr(led, "machine_id", lambda: "machine-under-test")
    monkeypatch.setattr(sched, "running_games", lambda: [])
    monkeypatch.setattr(sched, "idle_seconds", lambda: 9999.0)
    monkeypatch.setattr(sched, "plan_keys", lambda: list(benches))
    monkeypatch.setattr(sched, "bench_named", lambda key: benches[key])
    monkeypatch.setattr(sched, "sweep_leftover_tools", lambda _names=None: 0)


class TestTriggers:
    def test_the_first_tick_with_no_baseline_opens_a_baseline_job(self) -> None:
        outcome = sched.poll_once()

        assert outcome.outcome == sched.RAN
        job = led.read_job()
        assert job is not None
        assert job.trigger == led.BASELINE

    def test_it_does_not_open_a_second_baseline_once_one_exists(self) -> None:
        while sched.poll_once().outcome == sched.RAN:
            pass

        assert led.baseline() is not None
        assert sched.poll_once().outcome == sched.NOTHING_TO_DO

    def test_a_finished_bulk_apply_opens_an_after_job(self) -> None:
        while sched.poll_once().outcome == sched.RAN:
            pass

        led.mark_bulk_apply_finished()
        outcome = sched.poll_once()

        assert outcome.outcome == sched.RAN
        job = led.read_job()
        assert job is not None
        assert job.trigger == led.AFTER

    def test_the_sentinel_is_consumed_so_one_apply_is_one_job(self) -> None:
        while sched.poll_once().outcome == sched.RAN:
            pass
        led.mark_bulk_apply_finished()

        sched.poll_once()

        assert led.bulk_apply_pending() is False

    def test_with_nothing_to_do_it_says_so_rather_than_measuring(self) -> None:
        while sched.poll_once().outcome == sched.RAN:
            pass

        outcome = sched.poll_once()

        assert outcome.outcome == sched.NOTHING_TO_DO
        assert outcome.detail


class TestResumingAnOpenJob:
    def test_an_open_job_is_resumed_before_any_trigger_is_considered(self) -> None:
        """A half-measured run is worth more than a fresh one: it already holds
        results this machine will not otherwise take again."""
        led.mark_bulk_apply_finished()
        job = led.open_job(led.BASELINE, ["timing", "memory"])

        sched.poll_once()

        resumed = led.read_job()
        assert resumed is not None
        assert resumed.id == job.id, "a new job was opened over an unfinished one"
        assert led.bulk_apply_pending() is True, "the sentinel was spent on a resume"

    def test_it_picks_up_at_the_bench_that_did_not_finish(
        self, benches: dict[str, _FakeBench]
    ) -> None:
        """A crash mid-plan, simulated the only honest way: a ledger written to
        the middle of its plan, then a tick from code with no memory of it."""
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        led.record_step(
            job,
            BenchResult(
                bench="timing",
                label="timing label",
                ran=True,
                readings={"latency_ms": BenchReading("latency_ms", [1.0, 1.1], "ms")},
            ),
        )

        outcome = sched.poll_once()

        assert outcome.bench == "memory"
        assert benches["timing"].calls == 0, "a finished bench was measured again"
        assert benches["memory"].calls == 1

    def test_one_bench_runs_per_tick(self, benches: dict[str, _FakeBench]) -> None:
        """A whole plan in one tick would hold the operation lock for minutes and
        make every guard a decision taken once rather than continuously."""
        sched.poll_once()

        assert sum(bench.calls for bench in benches.values()) == 1

    def test_the_job_closes_once_its_plan_is_done(self) -> None:
        while sched.poll_once().outcome == sched.RAN:
            pass

        job = led.read_job()
        assert job is not None
        assert job.is_complete
        assert job.status == led.DONE


class TestTheGuards:
    def test_a_running_game_defers_the_tick(
        self, monkeypatch: pytest.MonkeyPatch, benches: dict[str, _FakeBench]
    ) -> None:
        """A synthetic bench during a match steals frames from the thing the
        whole product exists to protect."""
        monkeypatch.setattr(sched, "running_games", lambda: ["mw4"])

        outcome = sched.poll_once()

        assert outcome.outcome == sched.GAME_RUNNING
        assert sum(bench.calls for bench in benches.values()) == 0

    def test_the_deferral_names_the_game(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sched, "running_games", lambda: ["mw4"])

        assert "mw4" in sched.poll_once().detail

    def test_a_machine_in_use_defers_the_tick(
        self, monkeypatch: pytest.MonkeyPatch, benches: dict[str, _FakeBench]
    ) -> None:
        """Measuring while somebody types measures the typing."""
        monkeypatch.setattr(sched, "idle_seconds", lambda: 5.0)

        outcome = sched.poll_once()

        assert outcome.outcome == sched.NOT_IDLE
        assert sum(bench.calls for bench in benches.values()) == 0

    def test_idle_is_measured_against_a_stated_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sched, "idle_seconds", lambda: sched.IDLE_REQUIRED_SECONDS - 1)
        assert sched.poll_once().outcome == sched.NOT_IDLE

        monkeypatch.setattr(sched, "idle_seconds", lambda: sched.IDLE_REQUIRED_SECONDS + 1)
        assert sched.poll_once().outcome == sched.RAN

    def test_an_unreadable_idle_time_counts_as_in_use(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The conservative direction. An idle time nothing could read must not
        license a benchmark in the middle of a match."""
        monkeypatch.setattr(sched, "idle_seconds", lambda: 0.0)

        assert sched.poll_once().outcome == sched.NOT_IDLE

    def test_a_held_operation_lock_defers_the_tick(
        self, monkeypatch: pytest.MonkeyPatch, benches: dict[str, _FakeBench]
    ) -> None:
        """An apply and a bench must never overlap: the measurement would
        describe a machine halfway between two states."""
        import contextlib

        @contextlib.contextmanager
        def held(_name: str = "") -> object:
            yield False

        monkeypatch.setattr(sched, "operation_lock", held)

        outcome = sched.poll_once()

        assert outcome.outcome == sched.BUSY
        assert sum(bench.calls for bench in benches.values()) == 0

    def test_an_apply_running_in_this_process_defers_the_tick(
        self, benches: dict[str, _FakeBench], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The operation mutex is per-thread, so a bulk apply running on the
        pool's threads does not hold it against this one. The apply path keeps a
        counter for exactly that hole, and a bench that ignored it would measure
        a machine halfway through forty writes."""
        monkeypatch.setattr(sched, "applies_in_flight", lambda: 3)

        outcome = sched.poll_once()

        assert outcome.outcome == sched.BUSY
        assert "apply" in outcome.detail
        assert sum(bench.calls for bench in benches.values()) == 0

    def test_the_apply_counter_is_read_from_the_apply_path(self) -> None:
        """Read live rather than mirrored here: a second copy of the count is a
        copy that goes stale exactly when it matters."""
        from fpstune.api.routes import settings_apply

        assert sched.applies_in_flight() == settings_apply.applies_in_flight()

    def test_a_deferred_tick_leaves_the_job_for_next_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deferring is not abandoning: the plan has to still be there."""
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        monkeypatch.setattr(sched, "running_games", lambda: ["mw4"])

        sched.poll_once()

        still_open = led.current_job()
        assert still_open is not None
        assert still_open.id == job.id
        assert still_open.step_index == 0

    def test_no_job_is_opened_by_a_deferred_tick(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Opening one and refusing to run it would burn the apply sentinel."""
        monkeypatch.setattr(sched, "running_games", lambda: ["mw4"])

        sched.poll_once()

        assert led.read_job() is None


class TestRetryAndGiveUp:
    def test_a_failed_bench_is_counted_and_not_advanced_past(
        self, benches: dict[str, _FakeBench]
    ) -> None:
        benches["timing"]._fails = 99

        sched.poll_once()

        job = led.read_job()
        assert job is not None
        assert job.attempts["timing"] == 1
        assert job.step_index == 0, "a bench that failed was treated as done"

    def test_the_backoff_holds_the_next_attempt_off(self, benches: dict[str, _FakeBench]) -> None:
        benches["timing"]._fails = 99
        sched.poll_once()

        outcome = sched.poll_once()

        assert outcome.outcome == sched.WAITING_BACKOFF
        assert benches["timing"].calls == 1, "it retried inside its own backoff"

    def test_it_retries_once_the_backoff_has_passed(self, benches: dict[str, _FakeBench]) -> None:
        benches["timing"]._fails = 1
        sched.poll_once()

        outcome = sched.poll_once(now=_far_future())

        assert outcome.outcome == sched.RAN
        assert benches["timing"].calls == 2

    def test_the_attempt_count_survives_a_fresh_process(
        self, benches: dict[str, _FakeBench]
    ) -> None:
        """Counted in memory, a reboot would hand a hopeless bench three fresh
        attempts every time fpstune opened."""
        benches["timing"]._fails = 99
        sched.poll_once()
        sched.poll_once(now=_far_future())

        reread = led.current_job()

        assert reread is not None
        assert reread.attempts["timing"] == 2

    def test_exhaustion_records_the_bench_as_not_run(self, benches: dict[str, _FakeBench]) -> None:
        benches["timing"]._fails = 99
        for step in range(led.MAX_ATTEMPTS):
            sched.poll_once(now=_far_future(step))

        run = led.read_run(led.current_job() or led.read_job())  # type: ignore[arg-type]

        assert run is not None
        timing = next(result for result in run.results if result.bench == "timing")
        assert timing.ran is False

    def test_the_last_failure_is_carried_verbatim_into_the_reason(
        self, benches: dict[str, _FakeBench]
    ) -> None:
        """C11 rule 3: a bench that produced nothing says why, in its own words.

        Paraphrasing it into "the bench failed" deletes the only thing that
        would tell the user whether they can do something about it."""
        benches["timing"]._fails = 99
        for step in range(led.MAX_ATTEMPTS):
            sched.poll_once(now=_far_future(step))

        run = led.read_run(led.current_job() or led.read_job())  # type: ignore[arg-type]
        timing = next(  # type: ignore[union-attr]
            result for result in run.results if result.bench == "timing"
        )

        assert "timing could not read the counter" in timing.reason

    def test_the_plan_carries_on_past_an_exhausted_bench(
        self, benches: dict[str, _FakeBench]
    ) -> None:
        """A bench that will never run must not block the ones that would."""
        benches["timing"]._fails = 99
        for step in range(led.MAX_ATTEMPTS + 2):
            sched.poll_once(now=_far_future(step))

        assert benches["memory"].calls >= 1


class TestIdleDetection:
    def test_it_reads_the_machine_rather_than_asking_powershell(self) -> None:
        """`Add-Type` is banned outright — Defender flagged it as a trojan — so
        the last-input time comes through ctypes like every other native call in
        this codebase.

        Checked against executable lines only, the same carve-out the C4 and C9
        gates make: naming the banned thing in a comment to explain why the code
        avoids it is the opposite of using it, and a check that cannot tell the
        two apart is a check that gets deleted.
        """
        import ast
        import inspect

        source = inspect.getsource(sched)
        tree = ast.parse(source)
        docstrings = {
            ast.get_docstring(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }
        executable = "\n".join(
            line
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
            and not any(doc and line.strip() and line.strip() in doc for doc in docstrings)
        )

        assert "Add-Type" not in executable
        assert "powershell" not in executable.lower()
        assert "ctypes" in executable

    def test_it_returns_a_number_of_seconds(self) -> None:
        value = sched.idle_seconds()

        assert isinstance(value, float)
        assert value >= 0.0


class TestTheStartupSweep:
    def test_a_sweep_runs_before_the_first_tick(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tools left running by a previous session compete with the bench that
        is about to start, and one of them is a power virus."""
        swept: list[bool] = []
        monkeypatch.setattr(sched, "sweep_leftover_tools", lambda _names=None: swept.append(True))

        sched.poll_once(first_tick=True)

        assert swept == [True]

    def test_later_ticks_do_not_sweep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        swept: list[bool] = []
        monkeypatch.setattr(sched, "sweep_leftover_tools", lambda _names=None: swept.append(True))

        sched.poll_once()

        assert swept == []


class TestTheThread:
    def test_starting_twice_only_starts_one(self) -> None:
        try:
            assert sched.start_bench_scheduler() is True
            assert sched.start_bench_scheduler() is False
        finally:
            sched.stop_bench_scheduler()

    def test_it_stops_when_asked(self) -> None:
        sched.start_bench_scheduler()
        sched.stop_bench_scheduler()

        assert sched._thread is None

    def test_it_matches_the_headroom_watch_shape(self) -> None:
        """Two daemons started side by side in one lifespan should be startable
        and stoppable the same way, or the lifespan grows a special case."""
        from fpstune.benchmark import headroom_watch

        for name in ("poll_once", "_stop", "_thread"):
            assert hasattr(sched, name), name
            assert hasattr(headroom_watch, name), name


def _far_future(step: int = 0) -> float:
    import time

    return time.time() + 3600.0 * (step + 1)
