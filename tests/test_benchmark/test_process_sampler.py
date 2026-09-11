"""The idle process is most of a quiet machine, and forgetting it reports 1653%.

`_Total` in the process performance class includes `Idle`, so on the sixteen-
thread machine this was written on a machine doing nothing reads as 1653 rather
than as 0. Two bugs live in that one fact: a sampler that publishes the raw total
reports impossible percentages, and one that divides without subtracting reports
a quiet machine as fully loaded. Both would have made every `cpu_usage` verdict
in the registry meaningless while looking like a measurement.

The rest of this file guards the two directions and the boundary:

* `ram_available_mb` must rise when memory is freed, because the claim it
  answers (`ram_saved`) rises. Sampling working set instead would report freed
  memory as a regression.
* a game's cost is its own reading and never part of the machine-wide figure.
* a filter built from a process name is built from an allowlist, so a name with
  a quote in it cannot end the WQL literal and continue the query.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fpstune.benchmark.process_sampler import (
    NOTHING_SAMPLED,
    ProcessSamplerBench,
    build_script,
    busy_percent,
    running_game,
)
from fpstune.benchmark.suite import Bench

# The shape one second of sampling returns. The CPU figures are this machine's
# own idle reading, quoted as fixture input rather than read from the
# environment (C9's second exclusion).
_IDLE_SECOND: dict[str, Any] = {
    "total_cpu": 1653,
    "idle_cpu": 1418,
    "total_io": 4_016_661,
    "total_ws": 9_582_886_912,
    "available_mb": 17066,
    "game_cpu": 0,
    "game_ws": 0,
    "game_instances": 0,
}


def _second(**overrides: Any) -> dict[str, Any]:
    row = dict(_IDLE_SECOND)
    row.update(overrides)
    return row


def _run(rows: list[dict[str, Any]], *, repeats: int = 2, game: str | None = None, cpus: int = 16):
    with (
        patch("fpstune.benchmark.process_sampler.query_rows", return_value=(rows, "")),
        patch("fpstune.benchmark.process_sampler.running_game", return_value=game),
        patch("fpstune.benchmark.process_sampler.os.cpu_count", return_value=cpus),
    ):
        return ProcessSamplerBench(window_samples=len(rows)).run(repeats)


class TestIdleIsNotLoad:
    def test_a_machine_at_rest_does_not_read_as_sixteen_hundred_per_cent(self) -> None:
        """1653 total against 1418 idle on sixteen threads is about 15%."""
        assert busy_percent(1653, 1418, 16) == pytest.approx(14.7, abs=0.1)

    def test_a_fully_loaded_machine_reads_as_one_hundred(self) -> None:
        assert busy_percent(1600, 0, 16) == pytest.approx(100.0)

    def test_the_reading_can_never_leave_its_own_range(self) -> None:
        """Formatted counters round, and a total under the idle figure happens."""
        assert busy_percent(1400, 1418, 16) == 0.0
        assert busy_percent(9999, 0, 16) == 100.0

    def test_an_unknown_processor_count_falls_back_to_the_measured_total(self) -> None:
        """Still a share of the machine, arrived at by measurement."""
        assert busy_percent(1653, 1418, None) == pytest.approx(14.2, abs=0.1)

    def test_the_bench_publishes_the_busy_share_rather_than_the_raw_counter(self) -> None:
        result = _run([_second(), _second()])

        assert result.readings["cpu_usage"].median == pytest.approx(14.7, abs=0.2)
        assert result.readings["cpu_usage"].improves_upward is False


class TestMemoryIsMeasuredTheWayTheClaimIsStated:
    def test_freed_memory_reads_as_a_rise(self) -> None:
        """`ram_saved` goes up when the setting works, so this must too.

        Measured as working set, the same event — memory handed back — would
        arrive as a smaller number and be judged a regression.
        """
        reading = _run([_second(available_mb=17066)]).readings["ram_available_mb"]

        assert reading.median == pytest.approx(17066.0)
        assert reading.improves_upward is True

    def test_disk_traffic_is_reported_as_bytes_a_second_and_lower_is_better(self) -> None:
        reading = _run([_second(total_io=4_016_661)]).readings["disk_io"]

        assert reading.median == pytest.approx(4_016_661.0)
        assert reading.unit == "bytes/s"
        assert reading.improves_upward is False

    def test_every_second_of_the_window_is_on_the_record(self) -> None:
        """The mean is the reading; the samples behind it stay auditable."""
        result = _run([_second(total_cpu=1653), _second(total_cpu=1600)], repeats=2)

        assert len(result.detail["samples"][0]["cpu_percent"]) == 2


class TestAGameIsSampledBesideTheMachineAndNotInsideIt:
    def test_no_game_running_means_no_game_readings(self) -> None:
        result = _run([_second()])

        assert "game_cpu_usage" not in result.readings
        assert result.detail["game"] is None

    def test_a_running_game_gets_its_own_readings(self) -> None:
        result = _run(
            [_second(game_cpu=800, game_ws=6 * 1024 * 1024 * 1024, game_instances=1)],
            game="mw4",
        )

        assert result.readings["game_cpu_usage"].median == pytest.approx(50.0)
        assert result.readings["game_working_set_mb"].median == pytest.approx(6144.0)
        assert result.detail["game_label"] == "Modern Warfare IV"

    def test_the_machine_wide_figure_is_not_the_game_figure(self) -> None:
        """Folding the two together would credit closing a game to a setting."""
        result = _run(
            [_second(game_cpu=800, game_instances=1)],
            game="mw4",
        )

        assert result.readings["cpu_usage"].median != result.readings["game_cpu_usage"].median

    def test_a_game_that_reported_no_instances_produces_no_game_reading(self) -> None:
        """The process list is the authority, not the fact that a game launched."""
        result = _run([_second(game_instances=0)], game="mw4")

        assert "game_cpu_usage" not in result.readings

    def test_running_game_answers_none_when_nothing_known_is_open(self) -> None:
        with patch("fpstune.benchmark.process_sampler.game_is_running", return_value=False):
            assert running_game() is None


class TestTheFilterCannotBeEscaped:
    def test_a_name_with_a_quote_never_reaches_the_query(self) -> None:
        """It would end the literal and continue the WQL statement."""
        script = build_script(2, ("cod26-cod", "evil' OR Name LIKE '%"))

        assert "cod26-cod%" in script
        assert "evil" not in script

    def test_a_process_is_matched_by_prefix_so_a_second_copy_still_counts(self) -> None:
        """The performance class appends `#1` to the second instance."""
        assert "Name LIKE 'cod26-cod%'" in build_script(2, ("cod26-cod",))

    def test_the_window_length_is_an_integer_in_the_script(self) -> None:
        assert "1..4 |" in build_script(4)


class TestWhatItCannotSample:
    def test_a_failed_query_says_why_and_reads_nothing(self) -> None:
        with patch(
            "fpstune.benchmark.process_sampler.query_rows",
            return_value=([], "Windows did not answer this query"),
        ):
            result = ProcessSamplerBench(window_samples=2).run(2)

        assert not result.ran
        assert result.reason == "Windows did not answer this query"
        assert not result.readings

    def test_an_empty_window_is_a_failure_not_an_idle_machine(self) -> None:
        with patch("fpstune.benchmark.process_sampler.query_rows", return_value=([], "")):
            result = ProcessSamplerBench(window_samples=2).run(2)

        assert not result.ran
        assert result.reason == NOTHING_SAMPLED

    def test_a_window_needs_at_least_one_sample(self) -> None:
        with pytest.raises(ValueError):
            ProcessSamplerBench(window_samples=0)


class TestItIsABench:
    def test_it_satisfies_the_protocol(self) -> None:
        assert isinstance(ProcessSamplerBench(), Bench)

    def test_the_deadline_covers_the_sleeps_it_asked_for(self) -> None:
        """A deadline shorter than the window would kill every healthy run."""
        bench = ProcessSamplerBench(window_samples=10)

        assert bench.timeout_seconds(3) > 10 * 3
