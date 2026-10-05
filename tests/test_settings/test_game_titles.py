"""Fortnite, Apex, Overwatch 2 and Siege rows: the coherent frame cap, V-Sync off.

Each test names the failure it guards: a fixed panel given a cap that only
lowers the frame rate, a VRR panel's cap drifting from the driver's, a second
screen deciding for the primary one, a write refused while a game is closed or
allowed while it is open.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingScope
from fpstune.settings.definitions.game_configs_titles import (
    TITLE_SETTINGS,
    create_fortnite_fps_cap_setting,
    create_siege_fps_cap_setting,
)
from fpstune.settings.discovery.games_titles import discover_title_frame_caps
from fpstune.settings.executors import game_processes
from fpstune.settings.performance_headroom import frame_cap_for_refresh

_CAPS = (create_fortnite_fps_cap_setting, create_siege_fps_cap_setting)


@pytest.mark.parametrize("factory", _CAPS)
@pytest.mark.parametrize("hz", [60, 144, 240, 360])
def test_a_vrr_panel_gets_the_drivers_own_cap(factory, hz: int) -> None:
    # One rule for driver, in-game and headroom target: if two caps disagree
    # the lower one silently becomes the ceiling.
    setting = factory(hz, vrr=True)
    assert setting.recommended_value == frame_cap_for_refresh(hz)
    assert setting.recommended_value >= 30  # Siege reads anything lower as "no limit"


@pytest.mark.parametrize("factory", _CAPS)
def test_a_fixed_panel_is_left_uncapped(factory) -> None:
    # Without a VRR window a cap only lowers the ceiling (consequence 3).
    setting = factory(144, vrr=False)
    assert setting.recommended_value == 0
    assert setting.scope is SettingScope.ESSENTIAL


def test_every_vsync_row_recommends_off_and_is_a_drift_guard() -> None:
    vsync = [s for s in TITLE_SETTINGS if s.id.endswith(":vsync")]
    assert {s.id.split(":")[1] for s in vsync} == {"fortnite", "apex", "overwatch", "r6siege"}
    for setting in vsync:
        assert setting.recommended_value == setting.default_value
        # A game adds one ESSENTIAL row, its frame cap; the conservative preset
        # must not grow by a V-Sync row per game (test_essential_stays_small).
        assert setting.scope is SettingScope.RECOMMENDED
        assert setting.value_map[setting.apply_value_map[str(setting.recommended_value)]] == (
            setting.recommended_value
        )


def test_every_choice_round_trips_through_the_file_value() -> None:
    # A choice whose write value reads back as another choice would fail
    # verify forever on the machine that applied it.
    for setting in TITLE_SETTINGS:
        for choice in setting.choices:
            assert setting.value_map[setting.apply_value_map[choice]] == choice


class TestDiscovery:
    def _discover(self, monkeypatch: pytest.MonkeyPatch, monitors: list) -> dict:
        from fpstune.settings import registry as registry_mod

        reg = registry_mod.SettingsRegistry(discover_dynamic=False)
        monkeypatch.setattr(
            "fpstune.utils.hardware_manager.hardware_manager.detect_monitors",
            lambda *_a, **_k: monitors,
        )
        count = discover_title_frame_caps(reg, reg._probes)
        caps = {
            sid: reg.get(sid)
            for sid in ("game_config:fortnite:fps_cap", "game_config:r6siege:fps_cap")
        }
        return {"count": count, **caps}

    def test_the_primary_vrr_panel_sets_the_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Primary:
            supports_vrr = True
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 240
            native_refresh_rate_hz = 240

        found = self._discover(monkeypatch, [Primary()])
        assert found["count"] == 2
        assert found["game_config:fortnite:fps_cap"].recommended_value == 224
        assert found["game_config:r6siege:fps_cap"].recommended_value == 224

    def test_a_vrr_second_screen_does_not_cap_a_fixed_primary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Primary:
            supports_vrr = False
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 144
            native_refresh_rate_hz = 144

        class Secondary:
            supports_vrr = True
            is_primary = False
            is_active = True
            max_refresh_rate_hz = 240
            native_refresh_rate_hz = 240

        found = self._discover(monkeypatch, [Secondary(), Primary()])
        assert found["game_config:fortnite:fps_cap"].recommended_value == 0

    def test_an_unknown_refresh_registers_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Unknown:
            supports_vrr = True
            is_primary = True
            is_active = True
            max_refresh_rate_hz = 0
            native_refresh_rate_hz = 0
            refresh_rate = 0

        assert self._discover(monkeypatch, [Unknown()])["count"] == 0


@pytest.mark.parametrize(
    ("game", "process"),
    [
        ("fortnite", "fortniteclient-win64-shipping"),
        ("apex", "r5apex"),
        ("overwatch", "overwatch"),
        ("r6siege", "rainbowsix"),
    ],
)
def test_a_write_is_refused_while_its_game_runs(
    monkeypatch: pytest.MonkeyPatch, game: str, process: str
) -> None:
    # Each of these games writes its settings back from memory on exit, which
    # would undo a write that apply and verify both passed.
    monkeypatch.setattr(game_processes, "running_process_names", lambda: frozenset({process}))
    message = game_processes.refuse_if_game_is_running(f"game_config:{game}:vsync")
    assert message is not None and game_processes.GAME_LABELS[game] in message

    monkeypatch.setattr(game_processes, "running_process_names", lambda: frozenset())
    assert game_processes.refuse_if_game_is_running(f"game_config:{game}:vsync") is None
