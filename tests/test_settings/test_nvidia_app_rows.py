"""The NVIDIA App's three switches recommend the state the owner asked for: off.

The rule these tests pin is the product decision behind the rows, not the code:
Battery Boost, Whisper Mode and the App's own game optimization are all caps or
writers that cost the player something they did not ask for, so fpstune's
recommendation for every one of them is ``disabled``. The same file holds the
neighbour that must not drift the other way — ``gpu-nvidia:bg_app_fps`` is off,
and stays off, for the same reason.

A row is only a recommendation if it could be acted on, so each one is also held
to its writer: the three NVIDIA App rows must reach their own executor, and none
of them may still be the read-only advisory Battery Boost used to be.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import DetectType, SettingScope
from fpstune.settings.definitions.gpu import (
    NVIDIA_BATTERY_BOOST,
    NVIDIA_BG_APP_FPS,
    NVIDIA_NVAPP_AUTO_OPTIMIZE,
    NVIDIA_WHISPER_MODE,
)

APP_ROWS = (NVIDIA_BATTERY_BOOST, NVIDIA_WHISPER_MODE, NVIDIA_NVAPP_AUTO_OPTIMIZE)


@pytest.mark.parametrize("setting", APP_ROWS, ids=lambda s: s.id)
def test_the_recommended_state_is_off(setting) -> None:
    assert setting.recommended_value == "disabled"


@pytest.mark.parametrize("setting", APP_ROWS, ids=lambda s: s.id)
def test_the_row_can_be_applied_from_the_ui(setting) -> None:
    """A recommendation nobody can act on is a finding, not a tweak."""
    assert setting.is_readonly is False
    assert setting.value_type.value == "choice"
    assert setting.choices == ("enabled", "disabled")
    assert setting.detect_type is DetectType.POWERSHELL
    assert setting.apply_type is DetectType.POWERSHELL
    assert setting.detect_command
    assert setting.apply_command


@pytest.mark.parametrize("setting", APP_ROWS, ids=lambda s: s.id)
def test_the_default_is_not_invented(setting) -> None:
    """The App publishes the state in force, never its stock, so no reset is offered.

    C6: a default that cannot be derived is not invented. ``default_source`` names
    that decision, and ``test_default_source`` holds it to ``default_value=None``.
    """
    assert setting.default_source.value == "none"
    assert setting.default_value is None


def test_battery_boost_is_no_longer_a_read_only_advisory() -> None:
    """It used to report supportability and tell the user to act in the App.

    The reason was that nothing could read the state (the criteria file answers
    support only). The App's MCP endpoint answers the state itself, so the row is
    a tweak now — and the supportability reading must not come back as its value.
    """
    assert NVIDIA_BATTERY_BOOST.is_readonly is False
    assert "no_cap_possible" not in NVIDIA_BATTERY_BOOST.choices
    assert "cap_possible" not in NVIDIA_BATTERY_BOOST.choices
    assert NVIDIA_BATTERY_BOOST.detect_args == {"feature": "battery_boost"}


def test_whisper_mode_writes_its_own_feature() -> None:
    assert NVIDIA_WHISPER_MODE.detect_args == {"feature": "whisper_mode"}
    assert NVIDIA_WHISPER_MODE.apply_args["feature"] == "whisper_mode"


def test_the_game_optimization_row_writes_the_apps_own_switch() -> None:
    assert NVIDIA_NVAPP_AUTO_OPTIMIZE.detect_command == "nvapp_auto_apply_read"
    assert NVIDIA_NVAPP_AUTO_OPTIMIZE.apply_command == "nvapp_auto_apply_write"


def test_the_background_cap_stays_off() -> None:
    """The third switch the owner named: the driver's background frame cap."""
    assert NVIDIA_BG_APP_FPS.recommended_value == 0
    assert NVIDIA_BG_APP_FPS.scope is SettingScope.ESSENTIAL
