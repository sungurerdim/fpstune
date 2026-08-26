"""The evidence engine, reachable from outside the process.

`verify_round` and `sources` are careful about what they are entitled to say.
None of that survives if the HTTP layer answers a different question — and the
two ways it could are both here:

*Reporting on fewer settings than it was asked about.* An unknown id skipped
silently produces a round about four settings while the caller believes it is
about five, and the round's whole claim to meaning is that it knows how many
things changed. The apply path already had to learn this one.

*Turning half a measurement into a verdict.* A metric sampled before but not
after is not a small result, it is no result, and inventing the missing side is
the shape every flattering benchmark has.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app

# A real shipped setting with a measurable claim: `{"latency_ms": -1.5}`.
MEASURABLE = "power:usb_selective_suspend"
# A real shipped setting whose only claim is a ceiling, so nothing can score it.
CEILING = "game_config:mw3:fps_cap_out_of_focus"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


class TestCoverageIsAnsweredBeforeAnythingIsMeasured:
    def test_it_says_what_could_be_checked_and_what_could_not(self, client: TestClient) -> None:
        response = client.post(
            "/api/benchmark/verify/coverage", json={"setting_ids": [MEASURABLE, CEILING]}
        )
        assert response.status_code == 200

        payload = response.json()
        assert payload["total_claims"] >= 2
        assert payload["measurable"], "a latency claim should be measurable here"
        assert payload["unmeasurable"], "a ceiling claim should not be"

    def test_every_unmeasurable_claim_carries_its_reason(self, client: TestClient) -> None:
        """A coverage report without reasons is a number nobody can act on."""
        payload = client.post(
            "/api/benchmark/verify/coverage", json={"setting_ids": [CEILING]}
        ).json()

        assert payload["unmeasurable"]
        for entry in payload["unmeasurable"]:
            assert entry["reason"], entry

    def test_it_names_what_the_user_would_have_to_arrange(self, client: TestClient) -> None:
        payload = client.post(
            "/api/benchmark/verify/coverage", json={"setting_ids": [MEASURABLE]}
        ).json()
        assert payload["required_conditions"]

    def test_no_settings_is_not_an_error(self, client: TestClient) -> None:
        payload = client.post("/api/benchmark/verify/coverage", json={"setting_ids": []}).json()
        assert payload["total_claims"] == 0
        assert "no claims" in payload["summary"]

    def test_an_unknown_setting_is_refused_rather_than_skipped(self, client: TestClient) -> None:
        """Silently dropping it answers a question nobody asked."""
        response = client.post(
            "/api/benchmark/verify/coverage",
            json={"setting_ids": [MEASURABLE, "does:not:exist"]},
        )
        assert response.status_code == 404
        assert "does:not:exist" in response.json()["detail"]


class TestARound:
    def test_a_claim_that_moved_the_right_way_is_verified(self, client: TestClient) -> None:
        response = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {"latency_ms": [20.0, 20.1, 19.9]},
                "after": {"latency_ms": [10.0, 10.1, 9.9]},
            },
        )
        assert response.status_code == 200

        payload = response.json()
        assert payload["verified"] == 1
        assert payload["contradicted"] == 0

    def test_a_claim_that_moved_the_wrong_way_is_reported(self, client: TestClient) -> None:
        """The result that makes the endpoint worth having."""
        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {"latency_ms": [10.0, 10.1, 9.9]},
                "after": {"latency_ms": [30.0, 30.1, 29.9]},
            },
        ).json()

        assert payload["contradicted"] == 1
        assert "contradicted" in payload["summary"]

    def test_half_a_measurement_is_not_judged_and_says_so(self, client: TestClient) -> None:
        """One side of a pair is not a small result, it is no result."""
        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {"latency_ms": [20.0, 20.1]},
                "after": {},
            },
        ).json()

        assert payload["verified"] == 0
        assert any("only one side" in note for note in payload["notes"])

    def test_a_metric_measured_only_afterwards_is_reported_too(self, client: TestClient) -> None:
        """The mirror case, which a single loop over `before` would miss."""
        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {},
                "after": {"jitter_ms": [1.0, 1.1]},
            },
        ).json()

        assert any("jitter_ms" in note and "only one side" in note for note in payload["notes"])

    def test_changing_many_settings_at_once_credits_none_of_them(self, client: TestClient) -> None:
        """Forty settings and one measurement tells you about forty settings."""
        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE, CEILING],
                "before": {"latency_ms": [20.0, 20.1]},
                "after": {"latency_ms": [10.0, 10.1]},
            },
        ).json()

        assert payload["verified"] == 0
        assert "none of the 2 claims can be credited individually" in payload["summary"]

    def test_a_round_is_returned_and_not_filed(
        self, client: TestClient, tmp_path, monkeypatch
    ) -> None:
        """Ninety reports had accumulated in the state directory, each describing
        a machine state that no longer existed. A verdict about the machine as it
        is now has exactly one current answer, so it is returned and nothing is
        left behind to go stale."""
        monkeypatch.setattr("fpstune.utils.config.get_config_dir", lambda: tmp_path, raising=True)

        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {"latency_ms": [20.0, 20.1]},
                "after": {"latency_ms": [10.0, 10.1]},
            },
        ).json()

        assert payload["verdicts"], "the verdict itself still comes back"
        assert "report_html" not in payload
        # The whole tree, not just the old file names: any future write into the
        # state directory during a round is the same defect wearing a new stem.
        assert list(tmp_path.rglob("*")) == []

    def test_the_caller_s_own_caveats_reach_the_report(self, client: TestClient) -> None:
        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {"latency_ms": [20.0, 20.1]},
                "after": {"latency_ms": [10.0, 10.1]},
                "notes": ["Measured on WiFi, not Ethernet"],
            },
        ).json()

        assert "Measured on WiFi, not Ethernet" in payload["notes"]

    def test_an_unknown_setting_is_refused_here_too(self, client: TestClient) -> None:
        response = client.post(
            "/api/benchmark/verify/round",
            json={"setting_ids": ["does:not:exist"], "before": {}, "after": {}},
        )
        assert response.status_code == 404


class TestTheMappingIsPublishedRatherThanCopied:
    """The browser has to know which metric a sample belongs to.

    The alternative is a second copy of sources.py's mapping in TypeScript,
    which drifts from this one the first time an instrument gains a field and
    nobody notices — so the mapping is read out over HTTP and the equality is
    asserted here rather than trusted.
    """

    def test_it_publishes_exactly_what_sources_owns(self, client: TestClient) -> None:
        from fpstune.benchmark.sources import SOURCES

        payload = client.get("/api/benchmark/verify/sources").json()
        published = {entry["name"]: entry for entry in payload["sources"]}

        assert set(published) == {source.name for source in SOURCES}
        for source in SOURCES:
            entry = published[source.name]
            assert entry["metrics"] == sorted(source.fields), (
                f"{source.name} publishes a different metric set than it owns"
            )
            assert entry["requires"] == source.requires
            assert entry["units"] == source.units

    def test_the_gaps_ship_with_the_coverage(self, client: TestClient) -> None:
        # A coverage figure that lists only its successes is what sources.py was
        # written to avoid, so the endpoint that feeds the UI carries both halves.
        from fpstune.benchmark.sources import NO_INSTRUMENT

        payload = client.get("/api/benchmark/verify/sources").json()
        assert payload["no_instrument"] == NO_INSTRUMENT
        assert all(reason for reason in payload["no_instrument"].values())

    def test_the_instruments_that_need_arranging_are_not_offered_as_buttons(
        self, client: TestClient
    ) -> None:
        # presentmon has nothing to read without a game already rendering, and
        # furmark heats the card on purpose. Both stay listed, with what they
        # need, so the user is told what to arrange rather than told nothing.
        published = {
            entry["name"]: entry
            for entry in client.get("/api/benchmark/verify/sources").json()["sources"]
        }
        for name in ("presentmon", "furmark"):
            assert published[name]["runnable"] is False
            assert published[name]["requires"]
        assert published["dpc"]["runnable"] is True


class TestOneSample:
    def test_a_reading_comes_back_keyed_by_claim_metric(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of doing this server-side.

        The instrument answers in its own field names (`timing_jitter_max_us`);
        a round is judged in claim metrics (`latency_spike_ms`). Handing the raw
        names to the browser would make the caller guess at the translation,
        which is how a timer's jitter comes to "verify" a network claim.
        """
        from fpstune.api.routes import benchmark as routes

        monkeypatch.setattr(
            routes,
            "_sample_dpc",
            lambda: {"timing_jitter_max_us": 42.5, "timer_resolution_ms": 0.5},
        )

        payload = client.post("/api/benchmark/verify/sample", json={"instrument": "dpc"}).json()

        assert payload["instrument"] == "dpc"
        assert payload["metrics"] == {"latency_spike_ms": 42.5}
        assert payload["requires"]

    def test_a_field_the_instrument_did_not_produce_is_left_out(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent and zero are different, and the round is entitled to know which.

        Sending 0.0 for a reading that never happened would put a number into a
        median and let a sample the machine could not take drag a verdict.
        """
        from fpstune.api.routes import benchmark as routes

        monkeypatch.setattr(
            routes,
            "_sample_network",
            lambda _target_name: {"ping_avg": 12.0, "jitter_avg": None},
        )

        payload = client.post("/api/benchmark/verify/sample", json={"instrument": "network"}).json()

        assert payload["metrics"] == {"latency_ms": 12.0}
        assert "jitter_ms" not in payload["metrics"]

    def test_an_unknown_target_is_refused_and_the_known_ones_named(
        self, client: TestClient
    ) -> None:
        # Refusing without saying what would have worked leaves the caller
        # guessing at a list the server already has.
        response = client.post(
            "/api/benchmark/verify/sample",
            json={"instrument": "network", "target_name": "not-a-target"},
        )
        assert response.status_code == 400
        assert "not-a-target" in response.json()["detail"]
        assert "known targets" in response.json()["detail"]

    def test_an_instrument_that_cannot_be_started_on_demand_is_rejected(
        self, client: TestClient
    ) -> None:
        # Not a 500 from deep inside a runner: the schema refuses it at the door,
        # because "run furmark" is a request to heat the card.
        response = client.post("/api/benchmark/verify/sample", json={"instrument": "furmark"})
        assert response.status_code == 422

    def test_a_sample_feeds_the_round_it_was_taken_for(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The two endpoints have to compose, or the panel has nothing to submit.

        Proves the metric names /verify/sample emits are the ones
        /verify/round accepts — the seam where two correct halves most easily
        fail to meet.
        """
        from fpstune.api.routes import benchmark as routes

        readings = iter([30.0, 30.2, 10.0, 10.1])
        monkeypatch.setattr(
            routes, "_sample_network", lambda _target_name: {"ping_avg": next(readings)}
        )

        samples = [
            client.post("/api/benchmark/verify/sample", json={"instrument": "network"}).json()[
                "metrics"
            ]
            for _ in range(4)
        ]
        metric = next(iter(samples[0]))

        payload = client.post(
            "/api/benchmark/verify/round",
            json={
                "setting_ids": [MEASURABLE],
                "before": {metric: [s[metric] for s in samples[:2]]},
                "after": {metric: [s[metric] for s in samples[2:]]},
            },
        ).json()

        assert payload["verified"] == 1, payload["summary"]
