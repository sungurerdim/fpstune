"""What the machine measured, per area, over HTTP.

`/suite/compare` answers "here are two runs, judge them" and stores nothing. This
answers the question a user actually has — *did any of this help?* — without them
having had to know to take a "before" first. The ledger holds both halves; this
endpoint reads them and reports one verdict per area.

The whole design pressure here is C11 rule 1. A per-area report is exactly the
shape that invites a headline, and a headline is exactly what fpstune has
shipped wrong three times. So two rules are asserted throughout:

*Each area comes from exactly one instrument.* Never a blend, never a total. Two
instruments measuring "latency" measure two different events, and averaging them
produces a number with no referent.

*An area with no pair carries a reason, never a number.* Not zero, not "no
change", not an empty string — a sentence saying why it could not be checked,
in the same voice `sources.py` and `benches.catalogue()` already use.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.benchmark import ledger as led
from fpstune.benchmark.suite import BenchReading, BenchResult


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def own_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(led, "bench_dir", lambda: tmp_path)
    monkeypatch.setattr(led, "machine_id", lambda: "machine-under-test")
    return tmp_path


def _result(bench: str, metric: str, samples: list[float], unit: str = "ms") -> BenchResult:
    return BenchResult(
        bench=bench,
        label=f"{bench} label",
        ran=True,
        readings={metric: BenchReading(metric, samples, unit)},
    )


def _finish(trigger: str, results: list[BenchResult]) -> None:
    job = led.open_job(trigger, [result.bench for result in results])
    for result in results:
        led.record_step(job, result)
    led.finish_job(job)


def _timing(samples: list[float]) -> BenchResult:
    return _result("timing", "latency_spike_ms", samples)


class TestTheLedgerEndpointAnswersBeforeAnythingHasBeenMeasured:
    def test_it_is_not_an_error_to_have_measured_nothing(self, client: TestClient) -> None:
        """ "We have not looked yet" is the answer that makes the button worth
        pressing, and a 404 would render as a broken panel."""
        response = client.get("/api/benchmark/ledger")

        assert response.status_code == 200

    def test_it_reports_no_job_and_no_runs(self, client: TestClient) -> None:
        payload = client.get("/api/benchmark/ledger").json()

        assert payload["job"] is None
        assert payload["baseline"] is None
        assert payload["after"] is None

    def test_every_area_is_listed_rather_than_omitted(self, client: TestClient) -> None:
        """An area left out of the list looks like an area that does not exist."""
        payload = client.get("/api/benchmark/ledger").json()

        named = {area["area"] for area in payload["areas"]}
        assert named == {
            "fps",
            "input_latency",
            "timing",
            "cpu",
            "disk",
            "network",
            "memory",
            "thermal",
            "stability",
            "storage_health",
            "boot",
        }

    def test_an_area_with_no_instrument_says_so_rather_than_promising_a_pair(self) -> None:
        """ "Measure twice and this will appear" is a promise some builds cannot
        keep: what such an area lacks is an instrument, not a second run.

        Caught by curling the live endpoint — it told every area the same "no
        pair yet" story, which for an instrument-less one invents a to-do that
        can never be closed (C11 rule 4's mistake, arriving through the pair
        check). Exercised against an area built here rather than against
        thermal, which has had an instrument since the sensor bench landed: a
        rule tested only through whichever area happens to lack one today stops
        being tested the day that area gains one.
        """
        from fpstune.api.routes.benchmark_ledger import Area, _unmeasured, area_verdicts

        nothing_measures_it = Area(
            key="phantom",
            label="Something with no instrument",
            instrument="none",
            metric=None,
            absent_reason="Nothing in this build measures that.",
        )

        verdict = _unmeasured(nothing_measures_it, nothing_measures_it.absent_reason)
        with_no_pair = area_verdicts(None)

        assert verdict["reason"] == "Nothing in this build measures that."
        assert verdict["measured"] is False
        # And every real area, having an instrument, is told the pair story.
        assert all(area["reason"] for area in with_no_pair)

    def test_the_thermal_area_names_the_instrument_it_now_has(self, client: TestClient) -> None:
        """It read "FurMark measures heat under a load nobody plays at" for as
        long as nothing else sampled a temperature. The sensor bench does."""
        payload = client.get("/api/benchmark/ledger").json()
        thermal = next(a for a in payload["areas"] if a["area"] == "thermal")

        assert thermal["instrument"] == "sensors"
        assert thermal["metric"] == "gpu_temp_c"

    def test_every_unmeasured_area_carries_a_reason_and_no_number(self, client: TestClient) -> None:
        """C11 rule 3, and the one that matters most on this screen."""
        payload = client.get("/api/benchmark/ledger").json()

        for area in payload["areas"]:
            assert area["measured"] is False
            assert area["reason"], f"{area['area']} dropped out without saying why"
            assert area["before"] is None
            assert area["after"] is None
            assert area["percent_change"] is None


class TestAnOpenJobIsReported:
    def test_the_job_and_its_progress_come_back(self, client: TestClient) -> None:
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        led.record_step(job, _timing([1.0, 1.1]))

        payload = client.get("/api/benchmark/ledger").json()

        assert payload["job"]["id"] == job.id
        assert payload["job"]["step_index"] == 1
        assert payload["job"]["plan"] == ["timing", "memory"]
        assert payload["job"]["trigger"] == led.BASELINE

    def test_it_names_the_bench_currently_due(self, client: TestClient) -> None:
        job = led.open_job(led.BASELINE, ["timing", "memory"])
        led.record_step(job, _timing([1.0, 1.1]))

        payload = client.get("/api/benchmark/ledger").json()

        assert payload["job"]["current_bench"] == "memory"

    def test_a_finished_job_is_not_reported_as_open(self, client: TestClient) -> None:
        _finish(led.BASELINE, [_timing([1.0, 1.1])])

        payload = client.get("/api/benchmark/ledger").json()

        assert payload["job"] is None


class TestTheTwoHalvesAreSummarised:
    def test_a_baseline_alone_is_reported_without_an_after(self, client: TestClient) -> None:
        _finish(led.BASELINE, [_timing([2.0, 2.1])])

        payload = client.get("/api/benchmark/ledger").json()

        assert payload["baseline"] is not None
        assert payload["baseline"]["label"] == led.BASELINE_LABEL
        assert payload["after"] is None

    def test_the_summary_is_the_run_s_own_words(self, client: TestClient) -> None:
        """`SuiteRun.summary` leads with the shortfall; re-deriving it in the
        browser would be a second opinion about the same run."""
        _finish(led.BASELINE, [_timing([2.0, 2.1])])

        payload = client.get("/api/benchmark/ledger").json()

        assert payload["baseline"]["summary"]
        assert payload["baseline"]["bench_count"] == 1

    def test_both_halves_come_back_once_both_exist(self, client: TestClient) -> None:
        _finish(led.BASELINE, [_timing([2.0, 2.1])])
        _finish(led.AFTER, [_timing([1.0, 1.1])])

        payload = client.get("/api/benchmark/ledger").json()

        assert payload["baseline"] is not None
        assert payload["after"] is not None


class TestPerAreaVerdicts:
    def _both_halves(self) -> None:
        _finish(
            led.BASELINE,
            [
                _timing([4.0, 4.2, 4.1]),
                _result("memory", "memory_bandwidth", [900.0, 905.0, 902.0], "MB/s"),
            ],
        )
        _finish(
            led.AFTER,
            [
                _timing([1.0, 1.1, 1.05]),
                _result("memory", "memory_bandwidth", [1400.0, 1410.0, 1405.0], "MB/s"),
            ],
        )

    def test_a_paired_area_carries_numbers_and_no_reason(self, client: TestClient) -> None:
        self._both_halves()

        payload = client.get("/api/benchmark/ledger").json()
        timing = next(a for a in payload["areas"] if a["area"] == "timing")

        assert timing["measured"] is True
        assert timing["before"] == pytest.approx(4.1)
        assert timing["after"] == pytest.approx(1.05)
        assert timing["reason"] == ""

    def test_it_says_whether_the_move_beat_this_machine_s_own_noise(
        self, client: TestClient
    ) -> None:
        """C11 rule 2: a difference smaller than the noise floor is not a
        difference, and the panel has to be able to say so."""
        self._both_halves()

        payload = client.get("/api/benchmark/ledger").json()
        timing = next(a for a in payload["areas"] if a["area"] == "timing")

        assert timing["exceeds_noise"] is True
        assert "noise" in timing

    def test_each_area_names_the_one_instrument_it_came_from(self, client: TestClient) -> None:
        """Never a blend. Two instruments measuring "latency" measure two
        different events, and a number averaging them refers to nothing."""
        self._both_halves()

        payload = client.get("/api/benchmark/ledger").json()

        for area in payload["areas"]:
            assert area["instrument"], area["area"]
            assert isinstance(area["instrument"], str)

    def test_an_area_no_bench_in_the_pair_measured_carries_a_reason(
        self, client: TestClient
    ) -> None:
        """The pair exists; this area is simply not in it."""
        self._both_halves()

        payload = client.get("/api/benchmark/ledger").json()
        disk = next(a for a in payload["areas"] if a["area"] == "disk")

        assert disk["measured"] is False
        assert disk["reason"]
        assert disk["before"] is None and disk["after"] is None

    def test_an_area_measured_on_one_side_only_is_not_judged(self, client: TestClient) -> None:
        """Half a measurement is not a small result, it is no result."""
        _finish(
            led.BASELINE,
            [
                _timing([4.0, 4.2]),
                _result("disk_io", "storage_performance", [500.0, 510.0], "MB/s"),
            ],
        )
        _finish(led.AFTER, [_timing([1.0, 1.1])])

        payload = client.get("/api/benchmark/ledger").json()
        disk = next(a for a in payload["areas"] if a["area"] == "disk")

        assert disk["measured"] is False
        assert disk["reason"]

    def test_thermal_names_its_missing_instrument_rather_than_a_gap(
        self, client: TestClient
    ) -> None:
        """FurMark is a power virus and stays off the performance path (C11 rule
        6), so thermal has no instrument on this path — and says which."""
        self._both_halves()

        payload = client.get("/api/benchmark/ledger").json()
        thermal = next(a for a in payload["areas"] if a["area"] == "thermal")

        assert thermal["measured"] is False
        assert thermal["reason"]

    def test_no_total_is_reported_anywhere_in_the_payload(self, client: TestClient) -> None:
        """C11 rule 1, asserted rather than trusted: a per-area screen is exactly
        where a summed headline gets added back in six months."""
        self._both_halves()

        payload = client.get("/api/benchmark/ledger").json()

        for forbidden in ("total", "overall", "score", "headline", "gain"):
            assert forbidden not in payload, f"{forbidden} is a sum of claims (C11 rule 1)"


class TestEnqueuingAManualRun:
    def test_it_opens_a_manual_job(self, client: TestClient) -> None:
        response = client.post("/api/benchmark/ledger/run")

        assert response.status_code == 200
        job = led.read_job()
        assert job is not None
        assert job.trigger == led.MANUAL

    def test_it_reports_the_job_it_opened(self, client: TestClient) -> None:
        payload = client.post("/api/benchmark/ledger/run").json()

        assert payload["job"]["trigger"] == led.MANUAL
        assert payload["job"]["plan"]
        assert payload["queued"] is True

    def test_the_first_manual_run_becomes_the_baseline(self, client: TestClient) -> None:
        """Measuring for the first time because the user asked is still a first
        measurement; filing it as an "after" would leave it nothing to pair
        with, forever."""
        payload = client.post("/api/benchmark/ledger/run").json()

        assert payload["job"]["label"] == led.BASELINE_LABEL

    def test_a_later_manual_run_becomes_an_after(self, client: TestClient) -> None:
        _finish(led.BASELINE, [_timing([2.0, 2.1])])

        payload = client.post("/api/benchmark/ledger/run").json()

        assert payload["job"]["label"] == led.AFTER_LABEL

    def test_it_does_not_open_a_second_job_over_an_open_one(self, client: TestClient) -> None:
        """Two jobs would write two runs under one label and race each other."""
        existing = led.open_job(led.BASELINE, ["timing", "memory"])

        payload = client.post("/api/benchmark/ledger/run").json()

        assert payload["queued"] is False
        assert payload["job"]["id"] == existing.id

    def test_it_runs_through_the_same_pipeline_rather_than_measuring_inline(
        self, client: TestClient
    ) -> None:
        """Enqueued, not executed: the request must not hold a connection open
        for the minutes a suite takes, and the guards live in the scheduler."""
        payload = client.post("/api/benchmark/ledger/run").json()

        assert payload["job"]["step_index"] == 0


class TestTheAreasCarryAVerdictRatherThanOnlyANumber:
    """A delta is not a verdict. `-3 ms` on a metric where lower is better and
    `-3 ms` on one where higher is better read identically and mean opposite
    things, and the panel that renders them cannot be the place that decides
    which — the direction lives beside the metric, in `verify_round`."""

    def test_an_unpaired_area_is_unmeasured_rather_than_unchanged(self, client: TestClient) -> None:
        """ "Unchanged" is a finding. Never measured is not, and a screen that
        renders them the same way has said something it did not measure."""
        areas = {a["area"]: a for a in client.get("/api/benchmark/ledger").json()["areas"]}

        assert areas["timing"]["verdict"] == "unmeasured"
        assert areas["timing"]["samples_before"] == 0
        assert areas["timing"]["samples_after"] == 0

    def test_a_move_beyond_the_noise_the_right_way_is_improved(self, client: TestClient) -> None:
        """Timer jitter: lower is better, so a fall is a gain."""
        _finish(led.BASELINE, [_timing([9.0, 9.1, 9.05])])
        _finish(led.AFTER, [_timing([2.0, 2.1, 2.05])])

        areas = {a["area"]: a for a in client.get("/api/benchmark/ledger").json()["areas"]}

        assert areas["timing"]["verdict"] == "improved"
        assert areas["timing"]["improves_upward"] is False
        assert areas["timing"]["samples_before"] == 3
        assert areas["timing"]["samples_after"] == 3

    def test_the_same_move_the_wrong_way_is_worse(self, client: TestClient) -> None:
        _finish(led.BASELINE, [_timing([2.0, 2.1, 2.05])])
        _finish(led.AFTER, [_timing([9.0, 9.1, 9.05])])

        areas = {a["area"]: a for a in client.get("/api/benchmark/ledger").json()["areas"]}

        assert areas["timing"]["verdict"] == "worse"

    def test_a_move_inside_the_machines_own_noise_is_unchanged(self, client: TestClient) -> None:
        """C11 rule 2: a difference whose noise floor could not be beaten is not
        a difference. Calling it one is how a rounding error becomes a feature."""
        _finish(led.BASELINE, [_timing([5.0, 9.0, 1.0])])
        _finish(led.AFTER, [_timing([5.1, 9.1, 1.1])])

        areas = {a["area"]: a for a in client.get("/api/benchmark/ledger").json()["areas"]}

        assert areas["timing"]["verdict"] == "unchanged"
        assert areas["timing"]["measured"] is True

    def test_direction_comes_from_the_claim_vocabulary_not_from_this_module(
        self, client: TestClient
    ) -> None:
        """A second opinion about which way a metric improves is a second
        opinion that will eventually disagree with the first."""
        from fpstune.benchmark.verify_round import direction_of

        _finish(led.BASELINE, [_result("memory", "memory_bandwidth", [1000.0, 1010.0], "MB/s")])
        _finish(led.AFTER, [_result("memory", "memory_bandwidth", [4000.0, 4010.0], "MB/s")])

        areas = {a["area"]: a for a in client.get("/api/benchmark/ledger").json()["areas"]}

        assert direction_of("memory_bandwidth") is False  # lower is not better
        assert areas["memory"]["improves_upward"] is True
        assert areas["memory"]["verdict"] == "improved"


class TestTheRunsEndpointHandsBackWholeRuns:
    """The summary on `/ledger` is for a panel. `VerifyPanel` judges the runs
    themselves, and it cannot do that from a metric-name list — it needs the
    samples, which is what `SuiteRun.to_dict()` carries."""

    def test_it_answers_null_for_a_machine_that_has_measured_nothing(
        self, client: TestClient
    ) -> None:
        payload = client.get("/api/benchmark/ledger/runs").json()

        assert payload == {"baseline": None, "after": None}

    def test_it_returns_the_whole_run_including_its_samples(self, client: TestClient) -> None:
        _finish(led.BASELINE, [_timing([9.0, 9.1, 9.05])])

        payload = client.get("/api/benchmark/ledger/runs").json()

        assert payload["after"] is None
        baseline = payload["baseline"]
        assert baseline["label"] == led.BASELINE_LABEL
        reading = baseline["results"][0]["readings"]["latency_spike_ms"]
        assert reading["samples"] == [9.0, 9.1, 9.05]

    def test_what_it_returns_rebuilds_into_a_run(self, client: TestClient) -> None:
        """The shape is `SuiteRun.to_dict()` exactly, so `/suite/compare` can be
        handed it back unchanged. A second serialiser is a second thing to keep
        in step."""
        from fpstune.benchmark.suite import SuiteRun

        _finish(led.BASELINE, [_timing([9.0, 9.1, 9.05])])
        _finish(led.AFTER, [_timing([2.0, 2.1, 2.05])])

        payload = client.get("/api/benchmark/ledger/runs").json()

        before = SuiteRun.from_dict(payload["baseline"])
        after = SuiteRun.from_dict(payload["after"])
        assert before.reading("latency_spike_ms") is not None
        assert after.reading("latency_spike_ms") is not None
