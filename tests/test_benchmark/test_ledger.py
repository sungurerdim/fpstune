"""The job ledger: what fpstune is measuring, and how far it got.

`SuiteRun` has never survived a page reload — the browser held both halves of a
comparison and `/suite/compare` stored nothing by design. That is fine for a
button a human presses twice in one sitting and impossible for a scheduler,
which has to remember across a crash, a restart and a reboot which run is the
baseline and which bench it was on.

Four properties are asserted here, and each one is a failure mode PC-Check's
`state.json` had already been through:

*The step index advances only after the result is on disk.* Otherwise a crash
mid-bench re-runs the whole plan, or worse, skips the bench that crashed.

*A ledger from another machine is archived, never resumed.* A baseline is a
statement about one machine's hardware; pairing it with an "after" from a
different one produces a verdict that is confidently wrong.

*The write is atomic.* A ledger truncated by a power cut is a ledger that reads
back as no job at all, and the run it described is lost with it.

*Attempts are persisted, not counted in memory.* A bench that fails because a
reboot is pending must not get three fresh attempts after every reboot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpstune.benchmark import ledger as led
from fpstune.benchmark.suite import BenchReading, BenchResult, SuiteRun


@pytest.fixture(autouse=True)
def bench_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own ~/.fpstune/bench, and one stable machine."""
    monkeypatch.setattr(led, "bench_dir", lambda: tmp_path)
    monkeypatch.setattr(led, "machine_id", lambda: "machine-under-test")
    return tmp_path


def _result(bench: str, metric: str, samples: list[float]) -> BenchResult:
    return BenchResult(
        bench=bench,
        label=f"{bench} label",
        ran=True,
        readings={metric: BenchReading(metric, samples, "ms")},
    )


class TestMachineIdentity:
    def test_it_is_derived_rather_than_written_down(self) -> None:
        """C9: nothing about the developer's machine may sit in the source.

        Also not a hostname — a machine that gets renamed is the same machine,
        and two machines can carry the same name on different networks. Asserted
        against the real derivation, not the fixture's stand-in, because the
        stand-in is exactly what would hide a hostname creeping in.
        """
        import socket

        identity = led._compute_machine_id()

        assert identity
        assert socket.gethostname().lower() not in identity.lower()
        assert socket.gethostname() not in led.__file__

    def test_it_never_answers_empty(self) -> None:
        """An identity that compared equal to nothing would archive this
        machine's own ledger on every tick and never reach a comparison."""
        assert led._compute_machine_id().strip()

    def test_the_same_machine_answers_the_same_thing_twice(self) -> None:
        led.reset_machine_id()
        first = led._compute_machine_id()
        second = led._compute_machine_id()

        assert first == second


class TestOpeningAJob:
    def test_a_new_job_starts_at_the_first_step(self) -> None:
        job = led.open_job(led.BASELINE, ["timing", "memory"])

        assert job.step_index == 0
        assert job.status == led.QUEUED
        assert job.plan == ["timing", "memory"]
        assert job.machine == "machine-under-test"

    def test_it_is_readable_back_from_disk_immediately(self) -> None:
        opened = led.open_job(led.BASELINE, ["timing"])

        reloaded = led.current_job()

        assert reloaded is not None
        assert reloaded.id == opened.id
        assert reloaded.plan == opened.plan

    def test_a_baseline_job_reserves_the_baseline_label(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])

        assert job.label == led.BASELINE_LABEL
        assert led.BASELINE_LABEL in job.runs

    def test_an_after_job_reserves_the_after_label(self) -> None:
        job = led.open_job(led.AFTER, ["timing"])

        assert job.label == led.AFTER_LABEL

    def test_a_manual_job_is_the_baseline_when_there_is_not_one_yet(self) -> None:
        """Measuring for the first time on demand is still a first measurement.

        Filing it as an "after" would leave the ledger with a comparison half
        that has nothing to compare against, forever.
        """
        assert led.baseline() is None

        job = led.open_job(led.MANUAL, ["timing"])

        assert job.label == led.BASELINE_LABEL

    def test_a_manual_job_is_an_after_once_a_baseline_exists(self) -> None:
        first = led.open_job(led.MANUAL, ["timing"])
        led.record_step(first, _result("timing", "latency_spike_ms", [1.0, 1.1]))
        led.finish_job(first)

        second = led.open_job(led.MANUAL, ["timing"])

        assert second.label == led.AFTER_LABEL

    def test_the_run_file_lands_where_the_job_says_it_does(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        path = Path(job.runs[led.BASELINE_LABEL])

        assert path.exists()
        assert path.parent == led.runs_dir()
        assert job.id in path.name


class TestStepIndexOnlyAdvancesOnceTheResultIsOnDisk:
    def test_recording_a_step_advances_the_index(self) -> None:
        job = led.open_job(led.BASELINE, ["timing", "memory"])

        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        assert job.step_index == 1
        assert led.current_job().step_index == 1  # type: ignore[union-attr]

    def test_the_result_is_on_disk_before_the_index_moves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ordering is the whole guarantee, so it is asserted, not assumed.

        If the index moved first, a crash between the two writes would leave a
        ledger claiming a bench was done and a run file that never held it —
        and that bench would never be measured.
        """
        job = led.open_job(led.BASELINE, ["timing"])
        observed: list[int] = []
        original = led._write_run

        def spy(path: Path, run: SuiteRun) -> None:
            observed.append(led.read_job().step_index)  # type: ignore[union-attr]
            original(path, run)

        monkeypatch.setattr(led, "_write_run", spy)
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        assert observed == [0], "the run was written while the ledger still said step 0"
        assert led.read_job().step_index == 1  # type: ignore[union-attr]

    def test_a_crash_mid_plan_resumes_at_the_bench_that_did_not_finish(self) -> None:
        """Simulated the only honest way: a ledger written mid-plan, then re-read
        by code that has no memory of having written it."""
        job = led.open_job(led.BASELINE, ["timing", "memory", "disk_io"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))
        led.record_step(job, _result("memory", "memory_bandwidth", [900.0, 910.0]))

        resumed = led.current_job()

        assert resumed is not None
        assert resumed.step_index == 2
        assert resumed.remaining == ["disk_io"]
        assert resumed.current_bench == "disk_io"

    def test_the_partial_run_survives_the_resume(self) -> None:
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        run = led.read_run(led.current_job())  # type: ignore[arg-type]

        assert run is not None
        assert [r.bench for r in run.results] == ["timing"]
        assert run.reading("latency_spike_ms") is not None

    def test_a_finished_plan_reports_itself_complete(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        assert job.is_complete
        assert job.remaining == []
        assert job.current_bench is None


class TestAForeignLedgerIsArchivedRatherThanResumed:
    def test_a_job_from_another_machine_is_not_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        led.open_job(led.BASELINE, ["timing"])

        monkeypatch.setattr(led, "machine_id", lambda: "a-different-machine")

        assert led.current_job() is None

    def test_the_archiving_is_recorded_rather_than_deleted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deleting it would hide that a ledger arrived from somewhere else."""
        led.open_job(led.BASELINE, ["timing"])
        monkeypatch.setattr(led, "machine_id", lambda: "a-different-machine")

        led.current_job()

        assert led.read_job().status == led.ARCHIVED  # type: ignore[union-attr]

    def test_a_foreign_baseline_is_never_offered_as_a_comparison_half(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The reason the check exists: pairing two machines' runs produces a
        verdict that is confidently about nothing."""
        job = led.open_job(led.BASELINE, ["timing"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))
        led.finish_job(job)

        monkeypatch.setattr(led, "machine_id", lambda: "a-different-machine")

        assert led.baseline() is None
        assert led.pair() is None

    def test_the_same_machine_keeps_its_job(self) -> None:
        led.open_job(led.BASELINE, ["timing"])

        assert led.current_job() is not None
        assert led.read_job().status != led.ARCHIVED  # type: ignore[union-attr]


class TestTheWriteIsAtomic:
    def test_no_temporary_file_is_left_behind(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        assert list(led.bench_dir().glob("*.tmp")) == []
        assert list(led.runs_dir().glob("*.tmp")) == []

    def test_a_failed_write_leaves_the_previous_ledger_intact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Truncate-in-place is how a ledger becomes an empty file, and an empty
        ledger is a baseline nobody can find any more."""
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))
        before = led.ledger_path().read_text(encoding="utf-8")

        def explode(*_args: object, **_kwargs: object) -> None:
            raise OSError("the disk went away mid-write")

        monkeypatch.setattr(led, "_atomic_write", explode)
        with pytest.raises(OSError):
            led.record_step(job, _result("memory", "memory_bandwidth", [900.0, 910.0]))

        assert led.ledger_path().read_text(encoding="utf-8") == before

    def test_an_unreadable_ledger_says_so_rather_than_vanishing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """C11 rule 3, applied to the file that says what was measured.

        Asserted against the logger rather than `caplog`: fpstune's logger writes
        through the Rich console, so a message that is plainly on screen never
        reaches pytest's capture handler and a `caplog` assertion here fails on a
        working path.
        """
        led.ledger_path().parent.mkdir(parents=True, exist_ok=True)
        led.ledger_path().write_text("{not json at all", encoding="utf-8")

        said: list[str] = []
        monkeypatch.setattr(led.logger, "warning", lambda msg, *args: said.append(str(msg) % args))

        assert led.read_job() is None

        assert said, "an unreadable ledger dropped out in silence"
        assert "ledger" in said[0].lower()
        assert str(led.ledger_path()) in said[0]

    def test_the_file_is_json_a_person_can_read(self) -> None:
        led.open_job(led.BASELINE, ["timing"])

        payload = json.loads(led.ledger_path().read_text(encoding="utf-8"))

        assert payload["plan"] == ["timing"]
        assert payload["trigger"] == led.BASELINE


class TestAttemptsSurviveAFreshProcess:
    def test_a_failed_attempt_is_counted(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])

        led.record_attempt(job, "timing")

        assert job.attempts["timing"] == 1

    def test_the_count_is_read_back_by_code_that_never_wrote_it(self) -> None:
        """A reboot must not hand a hopeless bench three fresh attempts."""
        job = led.open_job(led.BASELINE, ["timing"])
        led.record_attempt(job, "timing")
        led.record_attempt(job, "timing")

        reloaded = led.current_job()

        assert reloaded is not None
        assert reloaded.attempts["timing"] == 2

    def test_a_bench_with_no_attempts_yet_reports_zero(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])

        assert job.attempts.get("timing", 0) == 0

    def test_exhaustion_is_reached_at_the_third_attempt(self) -> None:
        job = led.open_job(led.BASELINE, ["timing"])
        for _ in range(led.MAX_ATTEMPTS):
            led.record_attempt(job, "timing")

        assert job.attempts_exhausted("timing")

    def test_the_backoff_lengthens_with_each_attempt(self) -> None:
        """30 s, 2 min, 8 min: a bench blocked by something that clears takes the
        short wait, and one blocked by something that does not stops asking."""
        assert led.backoff_for(0) == 30.0
        assert led.backoff_for(1) == 120.0
        assert led.backoff_for(2) == 480.0

    def test_the_backoff_never_shortens_past_the_last_step(self) -> None:
        assert led.backoff_for(99) == led.backoff_for(led.MAX_ATTEMPTS - 1)


class TestTheBulkApplySentinel:
    def test_nothing_is_pending_before_an_apply(self) -> None:
        assert led.bulk_apply_pending() is False

    def test_marking_it_makes_it_pending(self) -> None:
        led.mark_bulk_apply_finished()

        assert led.bulk_apply_pending() is True

    def test_it_survives_a_process_that_never_wrote_it(self) -> None:
        """The whole reason it is a file: the trigger has to outlive a restart
        between the bulk apply and the next scheduler tick."""
        led.mark_bulk_apply_finished()

        assert led.sentinel_path().exists()
        assert led.bulk_apply_pending() is True

    def test_taking_it_consumes_it(self) -> None:
        led.mark_bulk_apply_finished()

        assert led.take_bulk_apply_sentinel() is True
        assert led.bulk_apply_pending() is False
        assert led.take_bulk_apply_sentinel() is False

    def test_marking_it_twice_is_still_one_pending_trigger(self) -> None:
        led.mark_bulk_apply_finished()
        led.mark_bulk_apply_finished()

        assert led.take_bulk_apply_sentinel() is True
        assert led.take_bulk_apply_sentinel() is False


class TestReadingRunsBack:
    def _finished(self, trigger: str, samples: list[float]) -> None:
        job = led.open_job(trigger, ["timing"])
        led.record_step(job, _result("timing", "latency_spike_ms", samples))
        led.finish_job(job)

    def test_no_baseline_before_anything_ran(self) -> None:
        assert led.baseline() is None
        assert led.latest_after() is None
        assert led.pair() is None

    def test_a_finished_baseline_reads_back_as_a_suite_run(self) -> None:
        self._finished(led.BASELINE, [1.0, 1.1])

        run = led.baseline()

        assert isinstance(run, SuiteRun)
        assert run.label == led.BASELINE_LABEL
        assert run.reading("latency_spike_ms").median == pytest.approx(1.05)  # type: ignore[union-attr]

    def test_a_pair_needs_both_halves(self) -> None:
        self._finished(led.BASELINE, [1.0, 1.1])

        assert led.baseline() is not None
        assert led.pair() is None, "one run is not a comparison"

    def test_a_pair_is_before_then_after_in_that_order(self) -> None:
        self._finished(led.BASELINE, [2.0, 2.1])
        self._finished(led.AFTER, [1.0, 1.1])

        pair = led.pair()

        assert pair is not None
        before, after = pair
        assert before.label == led.BASELINE_LABEL
        assert after.label == led.AFTER_LABEL
        assert (
            before.reading("latency_spike_ms").median
            > after.reading(  # type: ignore[union-attr]
                "latency_spike_ms"
            ).median
        )  # type: ignore[union-attr]

    def test_the_newest_after_wins(self) -> None:
        """One current answer per label, like `headroom.json` — an archive of
        every "after" ever taken is a directory that grows and nobody reads."""
        self._finished(led.BASELINE, [3.0, 3.1])
        self._finished(led.AFTER, [2.0, 2.1])
        self._finished(led.AFTER, [1.0, 1.1])

        after = led.latest_after()

        assert after is not None
        assert after.reading("latency_spike_ms").median == pytest.approx(1.05)  # type: ignore[union-attr]

    def test_an_unfinished_job_is_not_offered_as_a_run(self) -> None:
        """Half a plan is half a measurement, and comparing against it would
        pair four benches with six."""
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        led.record_step(job, _result("timing", "latency_spike_ms", [1.0, 1.1]))

        assert led.baseline() is None

    def test_a_run_whose_file_went_missing_says_so_rather_than_raising(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._finished(led.BASELINE, [1.0, 1.1])
        for path in led.runs_dir().glob("*.json"):
            path.unlink()

        import logging

        with caplog.at_level(logging.WARNING):
            assert led.baseline() is None
