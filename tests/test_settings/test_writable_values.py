"""A setting can only be told to write a state fpstune is able to write.

Four real-machine undo failures shared one cause: the recorded original was a
label the writer could not turn into a stored value.

  * `priority:win32_priority_separation` recorded "gaming" and `network:qos_bandwidth`
    recorded "disabled" — labels an earlier release declared and this one does not,
    so the registry writer failed with "Cannot convert 'gaming' to DWORD integer".
  * `perf:shutdown_service_timeout` recorded "2000ms", and with no map entry the
    writer put the literal text "2000ms" into `WaitToKillServiceTimeout` — a write
    that succeeded and then failed its own verification.
  * `network:wifi_radio_when_wired` recorded "radio_off", which its command refuses
    to write by design.

`can_write` is the one place that knows which states a setting may be written to.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import SettingExecutor, SettingValueType
from fpstune.settings.definitions import get_all_static_settings

_BY_ID: dict[str, SettingExecutor] = {s.id: s for s in get_all_static_settings()}


def _setting(setting_id: str) -> SettingExecutor:
    return _BY_ID[setting_id]


class TestAStateTheMapDoesNotCoverCannotBeWritten:
    """A guard's detect-only "changed" state has no stored value to write."""

    @pytest.mark.parametrize(
        ("setting_id", "label"),
        [
            ("priority:win32_priority_separation", "gaming"),
            ("priority:win32_priority_separation", "changed"),
            ("network:qos_bandwidth", "disabled"),
            ("network:qos_bandwidth", "changed"),
            ("perf:shutdown_service_timeout", "2000ms"),
            ("perf:shutdown_service_timeout", "changed"),
        ],
    )
    def test_a_label_outside_the_apply_map_is_refused(self, setting_id: str, label: str) -> None:
        assert _setting(setting_id).can_write(label) is False

    @pytest.mark.parametrize(
        ("setting_id", "label"),
        [
            ("priority:win32_priority_separation", "standard"),
            ("network:qos_bandwidth", "standard"),
            ("perf:shutdown_service_timeout", "stock"),
        ],
    )
    def test_the_state_the_map_covers_is_written(self, setting_id: str, label: str) -> None:
        assert _setting(setting_id).can_write(label) is True


class TestAStateTheCommandRefusesIsDeclared:
    def test_the_wifi_radio_is_never_switched_off(self) -> None:
        setting = _setting("network:wifi_radio_when_wired")
        assert setting.can_write("radio_off") is False
        assert setting.can_write("not_applicable") is False
        assert setting.can_write("radio_on") is True

    def test_a_script_that_only_restores_cannot_write_the_changed_state(self) -> None:
        """`shutdown_app_timeout` removes the two values whatever it is asked for."""
        setting = _setting("perf:shutdown_app_timeout")
        assert setting.can_write("changed") is False
        assert setting.can_write("stock") is True


class TestKnownStates:
    def test_a_label_an_earlier_release_declared_is_not_a_state_now(self) -> None:
        setting = _setting("priority:win32_priority_separation")
        assert setting.is_known_state("gaming") is False
        assert setting.is_known_state("changed") is True


def test_every_setting_can_write_its_own_default_and_recommended_value() -> None:
    """Reset writes `default_value` and apply writes `recommended_value`; a
    declaration that made either unwritable would break both buttons."""
    broken = [
        f"{s.id}: {value!r}"
        for s in _BY_ID.values()
        if s.value_type == SettingValueType.CHOICE and not s.is_action and not s.is_readonly
        for value in (s.default_value, s.recommended_value)
        if value is not None and not s.can_write(value)
    ]
    assert broken == []


def test_a_state_that_cannot_be_written_is_rejected_by_apply_validation() -> None:
    """Posting "changed" for a guard used to reach the registry writer and fail
    there with "Cannot convert 'changed' to DWORD integer"."""
    from fpstune.api.routes.settings import _validate_apply_value

    setting = _setting("priority:win32_priority_separation")
    error = _validate_apply_value(setting, "changed")
    assert error is not None
    assert "standard" in error, "the message names what can be set"
    assert _validate_apply_value(setting, "standard") is None
