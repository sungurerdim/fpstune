"""A log nobody was allowed to open is not a machine that never boots.

The refusal is the whole reason this file exists. Asked for boot events with a
filter, `Get-WinEvent` answers "no events were found" for a log the process may
not read — indistinguishable from a machine with no boot records, and in a
translated sentence besides. So the bench probes access by log name first, where
the refusal arrives as `UnauthorizedAccessException`, and the two outcomes get
two different reasons a user can act on.

The other property under test is that repeats are ignored. Reading one log three
times is one measurement copied three times, and a noise floor computed from
copies would be zero — which would make every difference, however small, beat it.
The samples are separate boots or there are no samples.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.boot_time import (
    ACCESS_DENIED,
    NO_RECORDS,
    BootTimeBench,
    build_script,
    forget_access_probe,
)
from fpstune.benchmark.suite import Bench

_OK = {"kind": "status", "access": "ok"}


@pytest.fixture(autouse=True)
def _fresh_access_probe() -> None:
    """The availability answer is cached per session; tests get a fresh one."""
    forget_access_probe()


def _boot(boot_ms: int, main_ms: int = 30_000, at: int = 1_789_000_000) -> dict[str, Any]:
    return {
        "kind": "100",
        "at": at,
        "boot_ms": boot_ms,
        "main_path_ms": main_ms,
        "post_boot_ms": 12_000,
        "shutdown_ms": None,
    }


def _shutdown(shutdown_ms: int, at: int = 1_788_900_000) -> dict[str, Any]:
    return {
        "kind": "200",
        "at": at,
        "boot_ms": None,
        "main_path_ms": None,
        "post_boot_ms": None,
        "shutdown_ms": shutdown_ms,
    }


def _run(rows: list[dict[str, Any]], repeats: int = 3):
    with patch("fpstune.benchmark.boot_time.query_rows", return_value=(rows, "")):
        return BootTimeBench().run(repeats)


class TestTheSamplesAreBootsAndNotRepeats:
    def test_each_boot_is_its_own_sample(self) -> None:
        result = _run([_OK, _boot(42_000), _boot(51_000), _boot(45_000)])

        assert result.readings["boot_time_s"].samples == [42.0, 51.0, 45.0]

    def test_asking_for_more_repeats_does_not_reread_the_log(self) -> None:
        """Three reads of one log is one measurement, copied.

        Copied samples have a noise floor of zero, and a metric whose noise
        floor is zero calls every difference a change — including the second of
        variation between two boots of an unchanged machine.
        """
        with patch(
            "fpstune.benchmark.boot_time.query_rows", return_value=([_OK, _boot(42_000)], "")
        ) as query:
            BootTimeBench().run(5)

        assert query.call_count == 1

    def test_a_machine_that_has_booted_once_has_an_unknown_noise_floor(self) -> None:
        """One sample, infinite noise: nothing gets called a change on it."""
        result = _run([_OK, _boot(42_000)])

        assert result.readings["boot_time_s"].noise == float("inf")

    def test_the_deadline_does_not_grow_with_repeats_it_ignores(self) -> None:
        bench = BootTimeBench()

        assert bench.timeout_seconds(10) == bench.timeout_seconds(2)


class TestBootAndShutdownAreDifferentEvents:
    def test_a_shutdown_duration_is_published_under_its_own_name(self) -> None:
        result = _run([_OK, _boot(42_000), _shutdown(9_500)])

        assert result.readings["shutdown_time_s"].samples == [9.5]
        assert result.readings["boot_time_s"].samples == [42.0]

    def test_faster_is_the_improvement_for_both(self) -> None:
        """The claims say "faster"; the instrument reports seconds taken."""
        result = _run([_OK, _boot(42_000), _shutdown(9_500)])

        assert result.readings["boot_time_s"].improves_upward is False
        assert result.readings["shutdown_time_s"].improves_upward is False

    def test_the_main_path_is_kept_apart_from_the_whole_boot(self) -> None:
        """A startup-item change moves one of these and not the other."""
        result = _run([_OK, _boot(42_000, main_ms=30_000)])

        assert result.readings["main_path_boot_s"].samples == [30.0]

    def test_a_record_with_no_duration_is_not_a_zero_second_boot(self) -> None:
        result = _run([_OK, _boot(0, main_ms=0)])

        assert not result.ran
        assert result.reason
        assert not result.readings

    def test_how_many_records_were_read_is_on_the_record(self) -> None:
        result = _run([_OK, _boot(42_000), _boot(45_000), _shutdown(9_500)])

        assert result.detail["boots_read"] == 2
        assert result.detail["shutdowns_read"] == 1


class TestARefusalAndAnEmptyLogAreDifferentAnswers:
    def test_a_refused_log_says_it_needs_administrator(self) -> None:
        """Measured unelevated on the machine this was written on."""
        result = _run([{"kind": "status", "access": "denied"}])

        assert not result.ran
        assert result.reason == ACCESS_DENIED

    def test_the_panel_is_told_before_a_run_is_wasted(self) -> None:
        """`is_available` asks the log rather than asking whether we are admin.

        A member of Event Log Readers may open it without being an
        administrator, and a privilege check would refuse that machine for a
        reason that is not true of it.
        """
        with patch(
            "fpstune.benchmark.boot_time.query_rows",
            return_value=([{"kind": "status", "access": "denied"}], ""),
        ):
            available, why = BootTimeBench().is_available()

        assert not available
        assert why == ACCESS_DENIED

    def test_the_access_probe_runs_once_per_session(self) -> None:
        with patch(
            "fpstune.benchmark.boot_time.query_rows",
            return_value=([_OK, _boot(42_000)], ""),
        ) as query:
            assert BootTimeBench().is_available() == (True, "")
            BootTimeBench().is_available()

        assert query.call_count == 1

    def test_a_readable_log_with_no_boot_records_says_that_instead(self) -> None:
        result = _run([_OK])

        assert not result.ran
        assert result.reason == NO_RECORDS

    def test_a_failed_query_carries_its_own_reason(self) -> None:
        with patch(
            "fpstune.benchmark.boot_time.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = BootTimeBench().run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"


class TestTheScriptAsksTheWayWindowsAnswers:
    def test_the_access_probe_is_by_log_name(self) -> None:
        """Only that form reports a refusal as an unauthorized-access error.

        The filtered form answers "no events were found" for a log it was never
        allowed to open, in the system's own language.
        """
        script = build_script(5)

        assert "Get-WinEvent -LogName $log -MaxEvents 1 -ErrorAction Stop" in script
        assert "catch [System.UnauthorizedAccessException]" in script

    def test_both_event_ids_are_asked_for(self) -> None:
        script = build_script(5)

        assert "$read 100" in script
        assert "$read 200" in script

    def test_the_occurrence_count_is_an_integer_in_the_script(self) -> None:
        assert "-MaxEvents 7" in build_script(7)

    def test_an_occurrence_count_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError):
            BootTimeBench(occurrences=0)

    def test_it_satisfies_the_bench_protocol(self) -> None:
        assert isinstance(BootTimeBench(), Bench)
