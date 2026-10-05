"""Undo never writes a recorded state the setting cannot write.

Observed on a real machine (bulk undo): originals recorded by an earlier release
("gaming", "disabled", "2000ms") reached the registry writer, which failed to
convert them or — for a text value — wrote the label itself into the registry.
`network:wifi_radio_when_wired` recorded "radio_off" and its undo was refused by
the setting's own command after the machine had been asked to restore it.

The refusal belongs before any write, and the UI must not be told an undo is on
offer for a state that cannot be written.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fpstune.api.routes.settings_apply import (
    offered_original,
    undo_refusal,
    undo_single_setting,
)
from fpstune.safety.originals import OriginalValues
from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions import get_all_static_settings

_BY_ID: dict[str, SettingExecutor] = {s.id: s for s in get_all_static_settings()}

_PRIORITY = "priority:win32_priority_separation"
_RAW_STANDARD = {"kind": "registry", "present": True, "value": 2, "type": 4}


@pytest.fixture
def store(tmp_path) -> OriginalValues:
    return OriginalValues(path=tmp_path / "originals.json")


@pytest.mark.parametrize(
    ("setting_id", "recorded"),
    [
        (_PRIORITY, "gaming"),
        ("network:qos_bandwidth", "disabled"),
        ("perf:shutdown_service_timeout", "2000ms"),
        ("perf:shutdown_app_timeout", "2000ms"),
        ("network:wifi_radio_when_wired", "radio_off"),
    ],
)
def test_an_unwritable_original_is_refused_before_anything_is_written(
    store: OriginalValues, setting_id: str, recorded: str
) -> None:
    setting = _BY_ID[setting_id]
    store.record_first_seen({setting_id: recorded})

    with (
        patch("fpstune.safety.originals._store", store),
        patch(
            "fpstune.api.routes.settings_apply.CommandExecutor.apply",
            side_effect=AssertionError("an unwritable state must never reach the writer"),
        ),
    ):
        _, response = undo_single_setting(setting)

    assert response.success is False
    assert recorded in (response.error or "")
    assert "Reset" in (response.error or ""), "the way forward must be named"


def test_a_writable_original_is_still_undone(store: OriginalValues) -> None:
    """The refusal is for states that cannot be written, not for undo itself."""
    setting = _BY_ID[_PRIORITY]
    store.record_first_seen({_PRIORITY: "standard"})

    with patch("fpstune.safety.originals._store", store):
        assert undo_refusal(setting) is None


def test_a_raw_state_restores_a_changed_original_that_has_no_label_to_write(
    store: OriginalValues,
) -> None:
    """ "changed" is detect-only, but the stored state behind it is written back
    verbatim, so another tool's value can still be undone."""
    setting = _BY_ID[_PRIORITY]
    store.record_first_seen({_PRIORITY: "changed"}, {_PRIORITY: _RAW_STANDARD})

    with patch("fpstune.safety.originals._store", store):
        assert undo_refusal(setting) is None


def test_the_detect_response_offers_no_undo_for_an_unwritable_original(
    store: OriginalValues,
) -> None:
    store.record_first_seen(
        {"network:wifi_radio_when_wired": "radio_off", _PRIORITY: "standard"},
    )
    with patch("fpstune.safety.originals._store", store):
        assert offered_original(_BY_ID["network:wifi_radio_when_wired"]) is None
        assert offered_original(_BY_ID[_PRIORITY]) == "standard"
