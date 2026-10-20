"""An action exposes a reading, not a value state.

`current` is the value a setting holds; an action holds nothing. Its size/status
string goes to `reading`, and `is_action` tells every consumer which shape it is.
"""

from __future__ import annotations

from fpstune.api.routes.settings import setting_state
from fpstune.settings.detection import DetectionResult
from fpstune.settings.registry import SettingsRegistry


def _result(value: str | None) -> DetectionResult:
    return DetectionResult(
        setting_id="test",
        value=value,
        error=None,
        time_ms=1,
        is_optimized=False,
        is_applicable=True,
    )


def test_an_action_state_carries_a_reading_not_a_current() -> None:
    setting = SettingsRegistry(discover_dynamic=False).get("cleanup:temp_files")
    assert setting is not None and setting.is_action

    state = setting_state(setting, _result("ready|12 MB"))

    assert state.current is None
    assert state.is_action is True
    assert state.reading == "ready|12 MB"


def test_a_normal_setting_still_carries_current() -> None:
    setting = SettingsRegistry(discover_dynamic=False).get("power:disk_timeout")
    assert setting is not None and not setting.is_action

    state = setting_state(setting, _result("1200"))

    assert state.current == "1200"
    assert state.is_action is False
    assert state.reading is None
