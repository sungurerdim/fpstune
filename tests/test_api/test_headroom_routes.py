"""The last measurement, reachable from the panel that has to show it.

The user's requirement was three things at once: measure without being asked,
measure again on demand, and always know the last result — while keeping no
history. The first and third pull against each other, because a frame rate
cannot be measured with nothing rendering and at startup nothing is.

So the contract these tests hold the HTTP layer to is: **the read is always
answerable and the write is allowed to decline.** ``GET /headroom`` works before
anything has ever been measured, and ``POST /headroom/measure`` returns a named
reason rather than an error when the machine cannot be measured right now — "no
game is running" is a true statement about the world, and a 500 would tell the
user something is broken when nothing is.

Nothing here reads the developer's state file, process list, or display.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app
from fpstune.benchmark import headroom_watch
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
    monkeypatch.setattr(headroom_watch, "game_is_running", lambda _game: False)
    # The route imported the same function straight from `game_processes`, so
    # pinning only the `headroom_watch` copy left the payload's `is_running`
    # asking the developer's actual process list. Everything passed right up
    # until somebody launched the game these tests are named after. Both import
    # paths get pinned, or the suite is testing the room it runs in.
    monkeypatch.setattr("fpstune.api.routes.benchmark.game_is_running", lambda _game: False)
    monkeypatch.setattr(headroom_watch, "panel_target_fps", lambda: 297)
    monkeypatch.setattr(headroom_watch, "_presentmon_is_installed", lambda: True)
    monkeypatch.setattr(
        headroom_watch,
        "probe_running_game",
        lambda *_a, **_k: pytest.fail("no test should reach the real capture"),
    )
    headroom_watch.reset_watch_state()
    yield
    headroom_watch.reset_watch_state()


class TestTheReadIsAlwaysAnswerable:
    def test_it_answers_before_anything_has_been_measured(self, client: TestClient) -> None:
        """A panel that 404s until the first measurement can never show the button
        that takes the first measurement."""
        payload = client.get("/api/benchmark/headroom").json()

        assert payload["games"], "every known game should be listed, measured or not"
        assert all(game["is_measured"] is False for game in payload["games"])
        assert all(game["measured_fps"] is None for game in payload["games"])

    def test_a_measured_game_reports_what_it_reached_and_what_that_permits(
        self, client: TestClient, monkeypatch
    ) -> None:
        """The measured case this whole feature came from: 57.4 fps on a panel
        that could show 297."""
        monkeypatch.setattr(headroom_watch, "game_is_running", lambda game: game == "mw4")
        record_headroom(
            "mw4",
            measured_fps=57.4,
            fps_1_percent_low=36.4,
            target_fps=297,
            measured_at=NOW,
            bottleneck="both",
            cpu_busy_ms=17.18,
            gpu_time_ms=17.33,
        )

        games = {g["game"]: g for g in client.get("/api/benchmark/headroom").json()["games"]}

        mw4 = games["mw4"]
        assert mw4["label"] == "Modern Warfare IV"
        assert mw4["is_running"] is True
        assert mw4["measured_fps"] == 57.4
        assert mw4["fps_1_percent_low"] == 36.4
        assert mw4["target_fps"] == 297
        assert mw4["achievement_percent"] == 19
        assert mw4["tier"] == "critical"
        assert mw4["bottleneck"] == "both"
        assert games["mw3"]["is_measured"] is False

    def test_the_percentage_is_computed_here_not_in_the_browser(self, client: TestClient) -> None:
        """The number shown and the number the recommendation engine acts on come
        from one property, so they cannot drift apart."""
        record_headroom("mw4", measured_fps=297.0, target_fps=297, measured_at=NOW)

        games = {g["game"]: g for g in client.get("/api/benchmark/headroom").json()["games"]}

        assert games["mw4"]["achievement_percent"] == 100
        assert games["mw4"]["tier"] == "met"


class TestTheWriteIsAllowedToDecline:
    def test_nothing_running_is_a_reason_not_an_error(self, client: TestClient) -> None:
        response = client.post("/api/benchmark/headroom/measure", json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["measured"] is False
        assert payload["outcome"] == headroom_watch.NO_GAME_RUNNING
        assert "Start one" in payload["detail"]

    def test_a_missing_capture_tool_says_which_thing_is_missing(
        self, client: TestClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(headroom_watch, "game_is_running", lambda game: game == "mw4")
        monkeypatch.setattr(headroom_watch, "_presentmon_is_installed", lambda: False)

        payload = client.post("/api/benchmark/headroom/measure", json={}).json()

        assert payload["outcome"] == headroom_watch.PRESENTMON_MISSING
        assert "PresentMon" in payload["detail"]

    def test_a_measurement_comes_back_with_the_new_reading(
        self, client: TestClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(headroom_watch, "game_is_running", lambda game: game == "mw4")
        monkeypatch.setattr(
            headroom_watch,
            "probe_running_game",
            lambda game, target_fps, *, now, **_ignored: (
                record_headroom(game, measured_fps=120.0, target_fps=target_fps, measured_at=now),
                "",
            ),
        )

        payload = client.post("/api/benchmark/headroom/measure", json={"game": "mw4"}).json()

        assert payload["measured"] is True
        assert payload["game"] == "mw4"
        assert payload["headroom"]["measured_fps"] == 120.0
        assert payload["headroom"]["target_fps"] == 297

    def test_a_declined_measurement_still_returns_the_last_known_reading(
        self, client: TestClient
    ) -> None:
        """Blanking a number the user could read a second ago, because the newest
        attempt found the game closed, loses information for no reason."""
        record_headroom("mw4", measured_fps=57.4, target_fps=297, measured_at=NOW)

        payload = client.post("/api/benchmark/headroom/measure", json={"game": "mw4"}).json()

        assert payload["measured"] is False
        assert payload["headroom"]["measured_fps"] == 57.4
        assert payload["headroom"]["is_running"] is False

    def test_an_unknown_game_name_is_refused_without_touching_the_machine(
        self, client: TestClient
    ) -> None:
        payload = client.post("/api/benchmark/headroom/measure", json={"game": "not-a-game"}).json()

        assert payload["measured"] is False
        assert payload["headroom"] is None

    def test_an_overlong_game_name_never_reaches_the_process_check(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/benchmark/headroom/measure", json={"game": "x" * 64})
        assert response.status_code == 422
