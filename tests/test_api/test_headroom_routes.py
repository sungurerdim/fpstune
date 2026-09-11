"""The last measurement, reachable from the panel that has to show it.

The user's requirement was three things at once: measure without being asked,
measure again on demand, and always know the last result — while keeping no
history. The first and third used to pull against each other, because the
reading came from a game and at startup nothing is playing. The fixed scene
(`benchmark.gpu_scene`) settles that: it can be rendered whenever the machine is
free, so "measure without being asked" is the scheduler's ordinary pass and this
route is only the "again, now" half.

So the contract these tests hold the HTTP layer to is: **the read is always
answerable and the write is allowed to decline.** ``GET /headroom`` works before
anything has ever been measured, and ``POST /headroom/measure`` returns a named
reason rather than an error when the scene cannot run right now — "a game is
running" is a true statement about the world, and a 500 would tell the user
something is broken when nothing is.

Nothing here reads the developer's state file, renders a scene, or touches the
display.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.settings import performance_headroom
from fpstune.settings.performance_headroom import record_headroom

NOW = 1_800_000_000.0


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "fpstune.settings.performance_headroom.HEADROOM_PATH",
        tmp_path / "headroom.json",
        raising=True,
    )
    # The scene is a 3D engine and a 1.3 GB install. No route test may reach it,
    # and a test that silently did would render on the machine running the suite.
    monkeypatch.setattr(
        performance_headroom,
        "measure_now",
        lambda **_kwargs: pytest.fail("no test should reach the real scene"),
    )
    monkeypatch.setattr(
        "fpstune.api.routes.benchmark.measure_now",
        lambda **_kwargs: pytest.fail("no test should reach the real scene"),
    )
    return None


def outcome(
    name: str, detail: str, headroom: performance_headroom.PerformanceHeadroom | None
) -> performance_headroom.MeasurementOutcome:
    return performance_headroom.MeasurementOutcome(outcome=name, detail=detail, headroom=headroom)


class TestTheReadIsAlwaysAnswerable:
    def test_it_answers_before_anything_has_been_measured(self, client: TestClient) -> None:
        """A panel that 404s until the first measurement can never show the button
        that takes the first measurement."""
        payload = client.get("/api/benchmark/headroom").json()

        assert payload["headroom"]["is_measured"] is False
        assert payload["headroom"]["measured_fps"] is None
        assert payload["headroom"]["tier"] == "unknown"

    def test_it_reports_one_reading_for_the_machine(self, client: TestClient) -> None:
        """The scene is the same load on every run, so the number describes the
        machine. A list keyed by game would invite the reader to compare two
        titles that were never measured on the same workload."""
        record_headroom(
            measured_fps=197.0,
            fps_1_percent_low=120.0,
            target_fps=297,
            measured_at=NOW,
            bottleneck="gpu",
            present_mode="Composed: Copy with GPU GDI",
            width=2560,
            height=1440,
        )

        payload = client.get("/api/benchmark/headroom").json()

        assert "games" not in payload
        reading = payload["headroom"]
        assert reading["measured_fps"] == 197.0
        assert reading["fps_1_percent_low"] == 120.0
        assert reading["target_fps"] == 297
        assert reading["achievement_percent"] == 66
        assert reading["tier"] == "short"
        assert reading["bottleneck"] == "gpu"
        assert reading["present_mode"] == "Composed: Copy with GPU GDI"
        assert (reading["width"], reading["height"]) == (2560, 1440)

    def test_the_percentage_is_computed_here_not_in_the_browser(self, client: TestClient) -> None:
        """The number shown and the number the recommendation engine acts on come
        from one property, so they cannot drift apart."""
        record_headroom(measured_fps=297.0, target_fps=297, measured_at=NOW)

        reading = client.get("/api/benchmark/headroom").json()["headroom"]

        assert reading["achievement_percent"] == 100
        assert reading["tier"] == "met"


class TestTheWriteIsAllowedToDecline:
    def test_a_game_running_is_a_reason_not_an_error(self, client: TestClient, monkeypatch) -> None:
        """The scene renders at full speed and would take the card from the match
        — consequence 3 applied to our own tooling."""
        monkeypatch.setattr(
            "fpstune.api.routes.benchmark.measure_now",
            lambda **_kwargs: outcome(
                performance_headroom.SCENE_UNAVAILABLE,
                "Modern Warfare IV is running. The scene renders at full speed and would "
                "take the card away from the game, so it waits until you are done.",
                performance_headroom.PerformanceHeadroom(),
            ),
        )

        response = client.post("/api/benchmark/headroom/measure")

        assert response.status_code == 200
        payload = response.json()
        assert payload["measured"] is False
        assert payload["outcome"] == performance_headroom.SCENE_UNAVAILABLE
        assert "waits until you are done" in payload["detail"]

    def test_a_missing_scene_says_what_installing_it_costs(
        self, client: TestClient, monkeypatch
    ) -> None:
        """1.3 GB is the part of that sentence the user decides on, so it has to
        survive the trip to the browser intact."""
        monkeypatch.setattr(
            "fpstune.api.routes.benchmark.measure_now",
            lambda **_kwargs: outcome(
                performance_headroom.SCENE_UNAVAILABLE,
                "Unigine Superposition Basic is not installed; installing it is a "
                "1.3 GB download, which fpstune never starts on its own.",
                performance_headroom.PerformanceHeadroom(),
            ),
        )

        payload = client.post("/api/benchmark/headroom/measure").json()

        assert payload["outcome"] == performance_headroom.SCENE_UNAVAILABLE
        assert "1.3 GB" in payload["detail"]

    def test_a_measurement_comes_back_with_the_new_reading(
        self, client: TestClient, monkeypatch
    ) -> None:
        def measured(**_kwargs: object) -> performance_headroom.MeasurementOutcome:
            record_headroom(measured_fps=197.0, target_fps=297, measured_at=NOW)
            return outcome(
                performance_headroom.MEASURED,
                "This machine measured against the panel's 297 fps target",
                performance_headroom.read_headroom(),
            )

        monkeypatch.setattr("fpstune.api.routes.benchmark.measure_now", measured)

        payload = client.post("/api/benchmark/headroom/measure").json()

        assert payload["measured"] is True
        assert payload["headroom"]["measured_fps"] == 197.0
        assert payload["headroom"]["target_fps"] == 297

    def test_a_declined_measurement_still_returns_the_last_known_reading(
        self, client: TestClient, monkeypatch
    ) -> None:
        """Blanking a number the user could read a second ago, because the newest
        attempt declined, loses information for no reason."""
        record_headroom(measured_fps=197.0, target_fps=297, measured_at=NOW)
        monkeypatch.setattr(
            "fpstune.api.routes.benchmark.measure_now",
            lambda **_kwargs: outcome(
                performance_headroom.MEASURE_FAILED,
                "the scene engine would not start",
                performance_headroom.read_headroom(),
            ),
        )

        payload = client.post("/api/benchmark/headroom/measure").json()

        assert payload["measured"] is False
        assert payload["headroom"]["measured_fps"] == 197.0

    def test_the_caller_cannot_name_a_game_any_more(self) -> None:
        """The scene is the load, so there is nothing to pick. A body that still
        named one would be a request the product cannot honour, answered as if it
        had."""
        import inspect

        from fpstune.api.routes import benchmark

        assert inspect.signature(benchmark.measure_headroom).parameters == {}
