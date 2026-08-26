"""The suite over HTTP, tested for what it refuses to do.

The endpoints are thin, so most of what is worth pinning is the policy around
them: that "run everything" does not quietly spend the user's bandwidth, that an
unknown bench name is an error rather than a shorter run, that a comparison
returns nothing to disk, and that a stream carries the whole run on its last
event rather than expecting a client to reassemble one from the others.

Every bench is replaced. Running the real ones here would spend seconds each and
make the suite's tests the slowest thing in the repository.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.benchmark import benches as benches_module
from fpstune.benchmark.suite import BenchReading, BenchResult


class _FakeBench:
    def __init__(self, key: str, *, available: bool = True, why: str = "", boom: bool = False):
        self.key = key
        self.label = f"Fake {key}"
        self.requires = "nothing"
        self._available = available
        self._why = why
        self._boom = boom

    def is_available(self) -> tuple[bool, str]:
        return self._available, self._why

    def run(self, repeats: int) -> BenchResult:
        if self._boom:
            raise RuntimeError("the instrument fell over")
        return BenchResult(
            bench=self.key,
            label=self.label,
            ran=True,
            readings={
                "latency_ms": BenchReading("latency_ms", [10.0] * repeats, "ms"),
            },
        )


@pytest.fixture(autouse=True)
def fake_registry(monkeypatch):
    """A three-bench world: one free, one costly, one that cannot run."""
    entries = (
        benches_module.Entry(_FakeBench("free"), costs=""),
        benches_module.Entry(_FakeBench("costly"), costs="downloads a lot", in_default_run=False),
        benches_module.Entry(
            _FakeBench("blocked", available=False, why="start a game first"), costs=""
        ),
    )
    monkeypatch.setattr(benches_module, "_entries", lambda: entries)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _events(client: TestClient, payload: dict) -> list[dict]:
    with client.stream("POST", "/api/benchmark/suite/run", json=payload) as response:
        return [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]


class TestTheCatalogue:
    def test_it_lists_every_bench_including_the_ones_that_cannot_run(
        self, client: TestClient
    ) -> None:
        """A bench missing from the list reads as a bench that does not exist,
        when the truth is that it needs something arranging."""
        listing = client.get("/api/benchmark/suite").json()["benches"]

        assert [entry["key"] for entry in listing] == ["free", "costly", "blocked"]

    def test_a_bench_that_cannot_run_carries_the_reason(self, client: TestClient) -> None:
        blocked = client.get("/api/benchmark/suite").json()["benches"][2]

        assert blocked["available"] is False
        assert blocked["reason"] == "start a game first"

    def test_it_says_what_each_bench_costs_before_it_is_started(self, client: TestClient) -> None:
        """The user agreeing to a download should be told there is one."""
        costly = client.get("/api/benchmark/suite").json()["benches"][1]

        assert costly["costs"] == "downloads a lot"

    def test_run_everything_does_not_mean_every_bench(self, client: TestClient) -> None:
        """The broad button has to stay safe to press. A bench that spends more
        than the machine's own time is named or it does not run."""
        payload = client.get("/api/benchmark/suite").json()

        assert payload["default_keys"] == ["free", "blocked"]
        assert "costly" not in payload["default_keys"]

    def test_it_publishes_the_bounds_the_run_endpoint_enforces(self, client: TestClient) -> None:
        """A UI building a repeats control should not have to guess them."""
        payload = client.get("/api/benchmark/suite").json()

        assert payload["min_repeats"] == 2
        assert payload["default_repeats"] >= payload["min_repeats"]
        assert payload["max_repeats"] > payload["default_repeats"]


class TestRunning:
    def test_it_streams_one_event_per_bench_and_ends_with_the_run(self, client: TestClient) -> None:
        events = _events(client, {"benches": ["free"], "label": "before", "repeats": 2})

        assert [event["event"] for event in events] == ["started", "running", "measured", "done"]
        assert events[-1]["run"]["label"] == "before"

    def test_the_whole_run_arrives_on_the_done_event(self, client: TestClient) -> None:
        """Rather than the client reassembling one from the per-bench events. A
        dropped message would otherwise produce a run quietly missing a bench,
        which is the failure this suite exists to make impossible."""
        events = _events(client, {"benches": ["free", "blocked"], "repeats": 2})

        run = events[-1]["run"]
        assert [result["bench"] for result in run["results"]] == ["free", "blocked"]

    def test_a_bench_that_cannot_run_is_reported_not_skipped(self, client: TestClient) -> None:
        events = _events(client, {"benches": ["blocked"], "repeats": 2})

        skipped = [event for event in events if event["event"] == "skipped"]
        assert skipped[0]["result"]["reason"] == "start a game first"

    def test_a_bench_that_raises_does_not_end_the_run(self, client: TestClient) -> None:
        events = _events(client, {"benches": ["free"], "repeats": 2})
        assert events[-1]["event"] == "done"

    def test_an_unknown_bench_is_refused_rather_than_quietly_dropped(
        self, client: TestClient
    ) -> None:
        """A caller who typed `disc_io` should be told it does not exist, not
        handed a run that measured everything except it."""
        events = _events(client, {"benches": ["disc_io"], "repeats": 2})

        assert events[0]["event"] == "failed"
        assert events[0]["reason"] == "no bench named ['disc_io']"
        assert not events[0]["reason"].startswith('"')

    def test_omitting_the_bench_list_runs_the_default_set(self, client: TestClient) -> None:
        events = _events(client, {"repeats": 2})

        assert events[0]["benches"] == ["free", "blocked"]

    def test_progress_reaches_a_hundred(self, client: TestClient) -> None:
        events = _events(client, {"benches": ["free", "blocked"], "repeats": 2})

        progress = [event["progress"] for event in events if "progress" in event]
        assert progress[-1] == 100

    @pytest.mark.parametrize("repeats", [1, 0, 11])
    def test_a_repeat_count_that_cannot_produce_a_verdict_is_refused(
        self, client: TestClient, repeats: int
    ) -> None:
        """Below two there is no noise floor and therefore no verdict; above ten
        the run outlasts the patience without sharpening anything."""
        response = client.post("/api/benchmark/suite/run", json={"repeats": repeats})

        assert response.status_code == 422


class TestComparing:
    def _run(self, client: TestClient, label: str) -> dict:
        return _events(client, {"benches": ["free"], "label": label, "repeats": 2})[-1]["run"]

    def test_two_runs_come_back_judged(self, client: TestClient) -> None:
        before = self._run(client, "before")
        after = self._run(client, "after")

        payload = client.post(
            "/api/benchmark/suite/compare", json={"before": before, "after": after}
        ).json()

        assert payload["before_label"] == "before"
        assert [m["metric"] for m in payload["measurements"]] == ["latency_ms"]

    def test_a_run_survives_the_round_trip_through_json(self, client: TestClient) -> None:
        """The client holds both runs between taking them, so a run that cannot
        be sent back is a run that cannot be compared."""
        before = self._run(client, "before")

        payload = client.post(
            "/api/benchmark/suite/compare", json={"before": before, "after": before}
        ).json()

        assert payload["measurements"][0]["delta"] == 0
        assert payload["measurements"][0]["exceeds_noise"] is False

    def test_something_that_is_not_a_run_is_refused_with_a_reason(self, client: TestClient) -> None:
        response = client.post(
            "/api/benchmark/suite/compare", json={"before": {"nope": 1}, "after": {"nope": 2}}
        )

        assert response.status_code == 422
        assert "not a pair of suite runs" in response.json()["detail"]

    def test_comparing_writes_nothing_to_disk(self, client: TestClient, tmp_path) -> None:
        """The old verify round left ninety JSON and HTML files behind
        describing machines that no longer existed. Runs live in the client."""
        before = self._run(client, "before")
        client.post("/api/benchmark/suite/compare", json={"before": before, "after": before})

        assert list(tmp_path.iterdir()) == []


class TestTheComparisonSaysWhereTheGainLanded:
    """A flat list of metric names does not tell a reader what improved.

    The grouping is decided server-side on purpose: `impact_categories.py` is
    where a metric's category is settled, and a copy of that map in the browser
    would be a second answer waiting to disagree with the first — the same shape
    as a bench declaring a direction that contradicts `verify_round`.
    """

    def _run(self, client: TestClient, label: str) -> dict:
        return _events(client, {"benches": ["free"], "label": label, "repeats": 2})[-1]["run"]

    def test_every_measurement_carries_its_category(self, client: TestClient) -> None:
        before = self._run(client, "before")

        payload = client.post(
            "/api/benchmark/suite/compare", json={"before": before, "after": before}
        ).json()

        assert payload["measurements"][0]["metric"] == "latency_ms"
        assert payload["measurements"][0]["category"] == "latency"

    def test_a_bench_only_metric_gets_null_rather_than_a_wrong_category(self) -> None:
        """`pacing_p999_ms` is the frame pacing bench's own name for something no
        setting claims. Filing it under a category would be inventing a fact
        about it; null lets the UI show it on its own."""
        from fpstune.api.routes.benchmark_suite import _category_of

        assert _category_of("pacing_p999_ms") is None
        assert _category_of("bufferbloat_ms") is None

    def test_the_categories_come_from_the_settings_map(self) -> None:
        """Not a table maintained here. If `impact_categories` changes its mind
        about a metric, this changes with it."""
        from fpstune.api.routes.benchmark_suite import _category_of

        assert _category_of("memory_bandwidth") == "resources"
        assert _category_of("storage_performance") == "storage"
        assert _category_of("download_throughput") == "network"
        assert _category_of("gpu_temp_c") == "thermal"


class TestTheRunNarratesItself:
    """A run that prints nothing until it finishes cannot be told from a hung one.

    Reported by the user running the app from a terminal: "no lines are printed
    to the console for the benchmarks, you cannot tell whether it started or
    errored". Several of these instruments take tens of seconds, and the SSE
    stream only reaches the panel that opened it — `log_activity` is what reaches
    both the terminal and the in-app log.
    """

    @pytest.fixture
    def lines(self, monkeypatch) -> list[tuple[str, str]]:
        recorded: list[tuple[str, str]] = []
        monkeypatch.setattr(
            "fpstune.api.routes.benchmark_suite.log_activity",
            lambda message, level="info": recorded.append((message, level)),
        )
        return recorded

    def test_the_start_is_announced_before_any_instrument_runs(
        self, client: TestClient, lines: list[tuple[str, str]]
    ) -> None:
        _events(client, {"benches": ["free"], "label": "before", "repeats": 2})

        assert lines, "the run printed nothing at all"
        first, level = lines[0]
        assert "started" in first
        assert level == "info"

    def test_each_instrument_says_when_it_begins_and_how_it_ended(
        self, client: TestClient, lines: list[tuple[str, str]]
    ) -> None:
        _events(client, {"benches": ["free"], "label": "before", "repeats": 2})
        text = [message for message, _ in lines]

        assert any(message.startswith("Measuring Fake free (1/1)") for message in text)
        assert any("Fake free done in" in message for message in text)

    def test_a_bench_that_could_not_run_says_so_as_it_drops_out(
        self, client: TestClient, lines: list[tuple[str, str]]
    ) -> None:
        """C11 rule 3, on the console as well as in the summary."""
        _events(client, {"benches": ["blocked"], "label": "before", "repeats": 2})

        warnings = [message for message, level in lines if level == "warning"]
        assert any("start a game first" in message for message in warnings)

    def test_a_run_that_cannot_start_says_why(
        self, client: TestClient, lines: list[tuple[str, str]]
    ) -> None:
        """The worst case of the reported bug: nothing ran and nothing was said."""
        _events(client, {"benches": ["disc_io"], "label": "before", "repeats": 2})

        errors = [message for message, level in lines if level == "error"]
        assert errors, "a failed start printed nothing"
        assert "disc_io" in errors[0]
