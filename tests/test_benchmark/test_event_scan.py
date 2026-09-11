"""A crash counted twice is not two crashes, and a thin log is not a clean one.

The event scan is the first instrument here whose subject is failure, and both
ways of getting it wrong flatter the machine:

* counting the WER record *and* the minidump the same bug check wrote reports
  every crash as two, so a fix looks twice as good as it was;
* dividing by the window asked for rather than by the days the log actually
  holds turns a crash on a freshly installed machine into a seventh of a crash.

The third failure is the one C11 rule 3 exists for: a query Windows refuses must
come back as `ran=False` with a reason, never as a reading of zero — "no crashes"
and "we could not look" are opposite answers and they must never render the same.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from fpstune.benchmark.event_scan import (
    DISK_EVENT_IDS,
    MINIMUM_COVERED_DAYS,
    SECONDS_PER_DAY,
    EventScanBench,
    build_script,
    covered_days,
    minidump_count,
)
from fpstune.benchmark.suite import Bench, SuiteRun, compare_runs

_CLEAN = {
    "whea": 0,
    "bugcheck": 0,
    "unexpected_shutdown": 0,
    "tdr": 0,
    "disk_errors": 0,
    "disk_providers": "",
    "log_from": 0,
}


def _rows(**overrides: object) -> tuple[list[dict[str, object]], str]:
    row = dict(_CLEAN)
    row.update(overrides)
    return [row], ""


def _run(bench: EventScanBench, repeats: int = 2, dumps: int = 0, **overrides: object):
    with (
        patch("fpstune.benchmark.event_scan.query_rows", return_value=_rows(**overrides)),
        patch("fpstune.benchmark.event_scan.minidump_count", return_value=dumps),
        patch("fpstune.benchmark.event_scan.baseline_started_at", return_value=None),
    ):
        return bench.run(repeats)


class TestOneCrashIsCountedOnce:
    def test_a_wer_record_and_its_minidump_are_the_same_crash(self) -> None:
        """Summing the two reports every bug check as two crashes.

        Windows writes both for one stop: the WER record under event 1001 and
        the dump file beside it. A machine that crashed once would be reported
        at twice the rate it actually has, and a setting that halved crashes
        would look like it changed nothing.
        """
        result = _run(EventScanBench(window_days=1), dumps=1, bugcheck=1)

        assert result.readings["crash_rate"].median == pytest.approx(1.0)

    def test_a_dump_with_no_wer_record_still_counts_as_a_crash(self) -> None:
        """Error reporting can be switched off; the dump is still evidence."""
        result = _run(EventScanBench(window_days=1), dumps=2, bugcheck=0)

        assert result.readings["crash_rate"].median == pytest.approx(2.0)
        assert result.readings["bugcheck_count"].median == 0

    def test_an_unexpected_shutdown_is_not_filed_as_a_crash(self) -> None:
        """A power cut is a different event from a bug check and stays its own."""
        result = _run(EventScanBench(window_days=1), unexpected_shutdown=3)

        assert result.readings["crash_rate"].median == 0
        assert result.readings["unexpected_shutdown_count"].median == 3


class TestTheRateRestsOnWhatTheLogHolds:
    def test_a_log_shorter_than_the_window_shortens_the_denominator(self) -> None:
        """Seven days of window over one day of log is one day of evidence.

        Measured on the machine this was written on: the System log reached back
        three hours, so a seven-day denominator would have divided every count
        by fifty-six times more time than the log covers.
        """
        now = time.time()
        one_day = covered_days(now - SECONDS_PER_DAY, now - 7 * SECONDS_PER_DAY, now, 7.0)

        assert one_day == pytest.approx(1.0, abs=0.01)

    def test_a_log_older_than_the_window_keeps_the_window(self) -> None:
        now = time.time()
        assert covered_days(now - 90 * SECONDS_PER_DAY, now - 7 * SECONDS_PER_DAY, now, 7.0) == 7.0

    def test_a_log_cleared_moments_ago_cannot_produce_an_enormous_rate(self) -> None:
        """One crash over five minutes of log is not 288 crashes a day."""
        now = time.time()
        assert covered_days(now - 300, now - SECONDS_PER_DAY, now, 1.0) == MINIMUM_COVERED_DAYS

    def test_an_unreadable_log_start_falls_back_to_the_window(self) -> None:
        now = time.time()
        assert covered_days(0.0, now - SECONDS_PER_DAY, now, 1.0) == 1.0

    def test_the_reading_uses_the_covered_days_the_detail_reports(self) -> None:
        """The two must agree, or the detail explains a number nobody computed."""
        now = time.time()
        result = _run(
            EventScanBench(window_days=7),
            dumps=1,
            log_from=int(now - SECONDS_PER_DAY),
        )

        covered = result.detail["covered_days"]
        assert covered == pytest.approx(1.0, abs=0.01)
        assert result.readings["crash_rate"].median == pytest.approx(1.0 / covered, rel=1e-4)


class TestAQueryThatFailedIsNotACleanMachine:
    def test_a_refused_query_reports_no_readings_and_a_reason(self) -> None:
        """`ran=False` with a reason, never zero crashes.

        A reading of zero from a query that never ran is the exact shape C11
        rule 3 forbids: the screen would say this machine has not crashed all
        week on the strength of a command that failed.
        """
        with patch(
            "fpstune.benchmark.event_scan.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = EventScanBench().run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"
        assert not result.readings

    def test_an_empty_answer_is_a_failure_not_a_count(self) -> None:
        """The script always emits one object, so no rows means no answer."""
        with patch("fpstune.benchmark.event_scan.query_rows", return_value=([], "")):
            result = EventScanBench().run(2)

        assert not result.ran
        assert result.reason


class TestTheCountsAreExactEnoughToCompare:
    def test_a_single_new_crash_beats_the_noise_floor(self) -> None:
        """An event count does not drift, so one more crash is a real change.

        This is the property that makes the scan worth pairing at all: a metric
        whose repeats disagree by one would swallow the very event it exists to
        catch.
        """
        before = SuiteRun(label="before", started_at=0.0)
        before.results.append(_run(EventScanBench(window_days=1)))
        after = SuiteRun(label="after", started_at=1.0)
        after.results.append(_run(EventScanBench(window_days=1), dumps=1))

        crash = next(
            m for m in compare_runs(before, after).measurements if m.metric == "crash_rate"
        )

        assert crash.exceeds_noise
        assert crash.delta > 0

    def test_it_satisfies_the_bench_protocol(self) -> None:
        assert isinstance(EventScanBench(), Bench)

    def test_it_declares_a_deadline_that_grows_with_repeats(self) -> None:
        bench = EventScanBench()
        assert bench.timeout_seconds(10) > bench.timeout_seconds(2)


class TestTheScriptAsksInIdsRatherThanWords:
    def test_every_disk_event_id_reaches_the_query(self) -> None:
        """A localised machine renders the message in its own language.

        The ids do not change, which is why the scan is keyed to them; a scan
        matching on English text would report a clean machine on this one.
        """
        script = build_script(1_700_000_000)

        for event_id in DISK_EVENT_IDS:
            assert str(event_id) in script

    def test_the_window_start_is_an_integer_in_the_script(self) -> None:
        """Nothing a caller typed reaches a command line."""
        assert "FromUnixTimeSeconds(1700000000)" in build_script(1_700_000_000.9)

    def test_the_providers_named_are_the_ones_that_raise_these_ids(self) -> None:
        script = build_script(0)

        assert "Microsoft-Windows-WHEA-Logger" in script
        assert "Microsoft-Windows-WER-SystemErrorReporting" in script
        assert "Microsoft-Windows-Kernel-Power" in script


class TestCountingDumpsOffDisk:
    def test_only_dumps_written_inside_the_window_are_counted(self, tmp_path: Path) -> None:
        """An old dump is a crash the current configuration did not cause."""
        recent = tmp_path / "011026-12345-01.dmp"
        recent.write_bytes(b"dump")
        stale = tmp_path / "010126-99999-01.dmp"
        stale.write_bytes(b"dump")
        cutoff = time.time() - SECONDS_PER_DAY
        import os

        os.utime(stale, (cutoff - 10, cutoff - 10))

        assert minidump_count(cutoff, tmp_path) == 1

    def test_a_machine_with_no_dump_directory_counts_zero(self, tmp_path: Path) -> None:
        """Dumps are off by default on some installs; that is not a failure."""
        assert minidump_count(0.0, tmp_path / "nothing-here") == 0

    def test_a_file_that_is_not_a_dump_is_not_a_crash(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("not a crash", encoding="utf-8")

        assert minidump_count(0.0, tmp_path) == 0
