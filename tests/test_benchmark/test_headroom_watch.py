"""Tests for when a measurement is taken, and when it is deliberately not.

``probe_running_game`` was already correct and already unused: nothing in the
product called it, so every recommendation that depends on a measurement ran on
a number typed in by hand. These tests are about the half that was missing —
*deciding* to measure — and the decisions that matter are the negative ones.

A measurement needs the game rendering, so the whole design turns on refusing to
claim one when it cannot be taken: no game open, no panel refresh to measure
against, no capture tool installed. Each of those has to stay a named answer
rather than collapsing into a silent failure, because the user's next action is
different in each case.

Nothing here touches the real state directory, the real process list, or the
real display.
"""

from __future__ import annotations

import pytest

from fpstune.benchmark import headroom_watch
from fpstune.benchmark.headroom_watch import (
    ALREADY_FRESH,
    MEASURED,
    NO_GAME_RUNNING,
    PANEL_UNKNOWN,
    PRESENTMON_MISSING,
    PROBE_FAILED,
    known_games,
    last_results,
    measure_game,
    measure_now,
    panel_target_fps,
    poll_once,
    running_games,
)
from fpstune.settings.performance_headroom import record_headroom

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """No real state file, no real processes, no real panel, no real capture."""
    monkeypatch.setattr(
        "fpstune.settings.performance_headroom.HEADROOM_PATH",
        tmp_path / "headroom.json",
        raising=True,
    )
    monkeypatch.setattr(headroom_watch, "game_is_running", lambda _game: False)
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


def _running(monkeypatch, *games: str) -> None:
    live = set(games)
    monkeypatch.setattr(headroom_watch, "game_is_running", lambda game: game in live)


def _probe_records(monkeypatch, *, fps: float) -> list[str]:
    """Stand in for PresentMon: record the reading the real probe would have."""
    seen: list[str] = []

    def fake(game: str, target_fps: int, *, now: float, **_ignored: object) -> bool:
        seen.append(game)
        return record_headroom(
            game,
            measured_fps=fps,
            target_fps=target_fps,
            measured_at=now,
            bottleneck="gpu",
        ), ""

    monkeypatch.setattr(headroom_watch, "probe_running_game", fake)
    return seen


class TestWhatItRefusesToClaim:
    def test_a_closed_game_is_not_a_failure_it_is_an_answer(self) -> None:
        outcome = measure_game("mw4", now=NOW)
        assert outcome.outcome == NO_GAME_RUNNING
        assert outcome.measured is False
        assert "not running" in outcome.detail

    def test_an_unreadable_panel_stops_the_measurement(self, monkeypatch) -> None:
        """Without a target there is nothing to measure the frame rate against,
        and a guessed 60 would report a 300 Hz machine as having met its ceiling
        at a fifth of it."""
        _running(monkeypatch, "mw4")
        monkeypatch.setattr(headroom_watch, "panel_target_fps", lambda: None)
        assert measure_game("mw4", now=NOW).outcome == PANEL_UNKNOWN

    def test_a_missing_capture_tool_is_named_not_hidden(self, monkeypatch) -> None:
        """The user's next action is "install PresentMon", which they cannot take
        if the answer was a bare false."""
        _running(monkeypatch, "mw4")
        monkeypatch.setattr(headroom_watch, "_presentmon_is_installed", lambda: False)
        outcome = measure_game("mw4", now=NOW)
        assert outcome.outcome == PRESENTMON_MISSING
        assert "PresentMon" in outcome.detail

    def test_a_game_with_no_known_process_name_cannot_be_watched(self) -> None:
        outcome = measure_game("not-a-game", now=NOW)
        assert outcome.outcome == NO_GAME_RUNNING
        assert outcome.headroom is None

    def test_a_capture_that_produced_no_frames_says_so(self, monkeypatch) -> None:
        _running(monkeypatch, "mw4")
        monkeypatch.setattr(headroom_watch, "probe_running_game", lambda *_a, **_k: (False, ""))
        assert measure_game("mw4", now=NOW).outcome == PROBE_FAILED

    def test_a_failure_still_reports_the_last_known_reading(self) -> None:
        """A panel that could show a number a minute ago must not blank it because
        the newest attempt found the game closed."""
        record_headroom("mw4", measured_fps=57.4, target_fps=297, measured_at=NOW)
        outcome = measure_game("mw4", now=NOW + 60)
        assert outcome.measured is False
        assert outcome.headroom is not None
        assert outcome.headroom.measured_fps == 57.4


class TestMeasuringWhenItCan:
    def test_a_running_game_is_measured_against_the_panel(self, monkeypatch) -> None:
        _running(monkeypatch, "mw4")
        probed = _probe_records(monkeypatch, fps=57.4)

        outcome = measure_game("mw4", now=NOW)

        assert probed == ["mw4"]
        assert outcome.outcome == MEASURED
        assert outcome.headroom is not None
        assert outcome.headroom.measured_fps == 57.4
        assert outcome.headroom.target_fps == 297

    def test_on_demand_finds_the_running_game_without_being_told(self, monkeypatch) -> None:
        """The button in the UI sends no game name: the user knows what they have
        open and should not have to say."""
        _running(monkeypatch, "mw3")
        probed = _probe_records(monkeypatch, fps=280.0)

        outcome = measure_now(None, now=NOW)

        assert probed == ["mw3"]
        assert outcome.game == "mw3"
        assert outcome.measured is True

    def test_on_demand_with_nothing_open_asks_for_a_game(self) -> None:
        outcome = measure_now(None, now=NOW)
        assert outcome.outcome == NO_GAME_RUNNING
        assert outcome.game is None
        assert "Start one" in outcome.detail

    def test_on_demand_ignores_a_fresh_reading(self, monkeypatch) -> None:
        """The freshness rule exists to stop the *background* watch re-capturing
        an unchanged session. A user who presses the button has changed something
        and is entitled to a new number."""
        _running(monkeypatch, "mw4")
        record_headroom("mw4", measured_fps=57.4, target_fps=297, measured_at=NOW)
        probed = _probe_records(monkeypatch, fps=120.0)

        outcome = measure_now("mw4", now=NOW + 1)

        assert probed == ["mw4"]
        assert outcome.headroom is not None
        assert outcome.headroom.measured_fps == 120.0


class TestTheBackgroundPass:
    def test_nothing_running_measures_nothing(self) -> None:
        assert poll_once(now=NOW) == []

    def test_a_running_game_is_measured_once_per_session(self, monkeypatch) -> None:
        """Ten seconds of capture every minute against an unchanged session is a
        cost with no reading behind it."""
        _running(monkeypatch, "mw4")
        probed = _probe_records(monkeypatch, fps=57.4)

        first = poll_once(now=NOW)
        second = poll_once(now=NOW + 60)

        assert [o.outcome for o in first] == [MEASURED]
        assert second == []
        assert probed == ["mw4"]

    def test_closing_and_reopening_earns_a_fresh_measurement(self, monkeypatch) -> None:
        """A new launch may follow a settings change, so the old number is no
        longer a statement about the current configuration."""
        _running(monkeypatch, "mw4")
        probed = _probe_records(monkeypatch, fps=57.4)
        poll_once(now=NOW)

        _running(monkeypatch)  # the user closed it
        poll_once(now=NOW + 60)

        _running(monkeypatch, "mw4")  # and launched it again, hours later
        poll_once(now=NOW + headroom_watch.REMEASURE_AFTER_SECONDS + 1)

        assert probed == ["mw4", "mw4"]

    def test_a_recent_reading_is_left_alone(self, monkeypatch) -> None:
        _running(monkeypatch, "mw4")
        record_headroom("mw4", measured_fps=57.4, target_fps=297, measured_at=NOW)

        outcomes = poll_once(now=NOW + 60)

        assert [o.outcome for o in outcomes] == [ALREADY_FRESH]

    def test_a_stale_reading_is_retaken(self, monkeypatch) -> None:
        _running(monkeypatch, "mw4")
        record_headroom("mw4", measured_fps=57.4, target_fps=297, measured_at=NOW)
        probed = _probe_records(monkeypatch, fps=120.0)

        outcomes = poll_once(now=NOW + headroom_watch.REMEASURE_AFTER_SECONDS + 1)

        assert [o.outcome for o in outcomes] == [MEASURED]
        assert probed == ["mw4"]

    def test_a_failed_probe_is_not_retried_every_minute(self, monkeypatch) -> None:
        """Without this a game that PresentMon cannot read would be attempted
        sixty times an hour for as long as it stays open."""
        _running(monkeypatch, "mw4")
        attempts: list[str] = []
        monkeypatch.setattr(
            headroom_watch,
            "probe_running_game",
            lambda game, *_a, **_k: (bool(attempts.append(game)), ""),
        )

        poll_once(now=NOW)
        poll_once(now=NOW + 60)
        poll_once(now=NOW + 120)

        assert attempts == ["mw4"]


class TestWhatThePanelIsTold:
    def test_every_known_game_is_listed_even_unmeasured(self) -> None:
        """ "We have not looked yet" is the answer that makes the button make
        sense; a list that omits those games looks like the list of games that
        exist."""
        listed = last_results(now=NOW)
        assert [game for game, _, _ in listed] == list(known_games())
        assert all(not h.is_measured for _, h, _ in listed)

    def test_a_measured_game_carries_its_reading_and_its_state(self, monkeypatch) -> None:
        _running(monkeypatch, "mw4")
        record_headroom(
            "mw4",
            measured_fps=57.4,
            fps_1_percent_low=36.4,
            target_fps=297,
            measured_at=NOW,
            bottleneck="both",
        )

        by_game = {game: (h, running) for game, h, running in last_results(now=NOW)}

        headroom, running = by_game["mw4"]
        assert headroom.measured_fps == 57.4
        assert headroom.fps_1_percent_low == 36.4
        assert headroom.tier == "critical"
        assert headroom.bottleneck == "both"
        assert running is True
        assert by_game["mw3"][1] is False

    def test_running_games_reports_only_what_is_open(self, monkeypatch) -> None:
        _running(monkeypatch, "mw4", "cs2")
        assert running_games() == ["cs2", "mw4"]


class TestTheTargetComesFromThePanel:
    def test_the_target_is_the_panel_minus_the_vrr_headroom(self, monkeypatch) -> None:
        """The same rule the in-game and driver caps derive from. When the three
        disagree the lowest silently wins and the others look broken."""
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda: [_FakeMonitor(max_refresh_rate_hz=300)],
        )
        assert panel_target_fps() == 297

    def test_a_panel_that_will_not_answer_gives_no_target(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda: [_FakeMonitor(max_refresh_rate_hz=0, native_refresh_rate_hz=0)],
        )
        assert panel_target_fps() is None

    def test_no_monitor_at_all_gives_no_target(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda: [],
        )
        assert panel_target_fps() is None

    def test_detection_blowing_up_leaves_the_target_unknown(self, monkeypatch) -> None:
        def explode() -> list[object]:
            raise OSError("WMI is having a day")

        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors", explode
        )
        assert panel_target_fps() is None


class _FakeMonitor:
    def __init__(
        self,
        *,
        max_refresh_rate_hz: int = 0,
        native_refresh_rate_hz: int = 0,
        is_primary: bool = True,
    ) -> None:
        self.max_refresh_rate_hz = max_refresh_rate_hz
        self.native_refresh_rate_hz = native_refresh_rate_hz
        self.is_primary = is_primary
