"""Four more processor keys a "gaming optimizer" commonly moves.

`power:cpu_max_frequency`, `power:cpu_idle_state_max`, `power:cpu_throttle_states`
and `power:cpu_duty_cycling` never had an fpstune setting before this pass, so a
tool that capped the turbo frequency, pinned idle depth to a shallow C-state,
forced throttle states Off, or turned duty cycling on went entirely unnoticed —
consequence 2 and 6's guard shape closes that gap the same way
`power:cpu_min_parking` and `power:thermal_cooling` already do:
`recommended_value == default_value == Windows' own mains value on this
machine`, so applying on a stock machine changes nothing and the setting exists
only to put the value back.

All four GUIDs were confirmed present under this machine's own
``HKLM\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerSettings\\
54533251-82be-4824-96c1-47b60b740d00\\<guid>`` before being written into
`power.py`, and their `ACSettingIndex` under
``DefaultPowerSchemeValues\\381b4222-f694-41f0-9685-ff5bb260df2e`` (Balanced,
mains) is what `test_default_is_this_machines_measured_registry_value` pins
below: 0, 0, 2 (Automatic) and 0 (Disabled).

Before this pass none of these four ids existed, so every test in this file
was red (``ImportError: cannot import name 'POWER_CPU_MAX_FREQUENCY'``); they
are green now that the settings are defined.
"""

from __future__ import annotations

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions.power import (
    POWER_CPU_DUTY_CYCLING,
    POWER_CPU_IDLE_STATE_MAX,
    POWER_CPU_MAX_FREQUENCY,
    POWER_CPU_THROTTLE_STATES,
    POWER_SETTINGS,
)
from fpstune.settings.executors import map_raw_to_display

_NEW_GUARDS: tuple[SettingExecutor, ...] = (
    POWER_CPU_MAX_FREQUENCY,
    POWER_CPU_IDLE_STATE_MAX,
    POWER_CPU_THROTTLE_STATES,
    POWER_CPU_DUTY_CYCLING,
)


def test_all_four_are_registered() -> None:
    """Positive control: a setting built but never added to the list is invisible."""
    ids = {s.id for s in POWER_SETTINGS}
    assert {
        "power:cpu_max_frequency",
        "power:cpu_idle_state_max",
        "power:cpu_throttle_states",
        "power:cpu_duty_cycling",
    } <= ids


@pytest.mark.parametrize("setting", _NEW_GUARDS, ids=lambda s: s.id)
def test_recommended_equals_default(setting: SettingExecutor) -> None:
    """The drift-guard shape: nothing to apply on a machine already at stock."""
    assert values_equal(setting.recommended_value, setting.default_value)


@pytest.mark.parametrize(
    ("setting", "harmful_raw"),
    [
        pytest.param(POWER_CPU_MAX_FREQUENCY, 3000, id="cpu_max_frequency-capped-at-3000mhz"),
        pytest.param(POWER_CPU_IDLE_STATE_MAX, 1, id="cpu_idle_state_max-pinned-to-shallow-state"),
        pytest.param(POWER_CPU_THROTTLE_STATES, 0, id="cpu_throttle_states-forced-off"),
        pytest.param(POWER_CPU_DUTY_CYCLING, 1, id="cpu_duty_cycling-forced-on"),
    ],
)
def test_a_harmful_value_reads_as_drifted(setting: SettingExecutor, harmful_raw: int) -> None:
    """A value another optimizer wrote must not read as already-optimized.

    This is what makes the guard a guard: detection has to notice the harmful
    reading and disagree with `recommended_value`, or a machine another tool
    already lowered the ceiling on would show the row as green.
    """
    display = map_raw_to_display(setting.value_map, harmful_raw)
    assert not values_equal(display, setting.recommended_value), (
        f"{setting.id} read raw {harmful_raw!r} (-> {display!r}) as matching its own "
        f"recommended value {setting.recommended_value!r}; a machine another optimizer "
        "changed would show as already optimized instead of needing a fix."
    )


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        pytest.param(POWER_CPU_MAX_FREQUENCY, 0, id="cpu_max_frequency"),
        pytest.param(POWER_CPU_IDLE_STATE_MAX, 0, id="cpu_idle_state_max"),
        pytest.param(POWER_CPU_THROTTLE_STATES, "automatic", id="cpu_throttle_states"),
        pytest.param(POWER_CPU_DUTY_CYCLING, "disabled", id="cpu_duty_cycling"),
    ],
)
def test_default_is_this_machines_measured_registry_value(
    setting: SettingExecutor, expected: object
) -> None:
    """Pins the constant measured 2026-09-11 to what `ACSettingIndex` answered.

    `tests/test_settings/test_power_windows_defaults.py::TestAgainstThisMachine`
    already re-reads the live registry for every powercfg setting, including
    these four, and would catch a machine that disagrees; this test pins what
    that read produced here so an edit to the source constant without
    re-reading the registry is caught even off this machine.
    """
    assert values_equal(setting.default_value, expected)
    assert values_equal(setting.recommended_value, expected)


class TestGUIDsAreSubProcessorSettings:
    """Every new setting reads powercfg's own processor subgroup, not a guess."""

    _SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"

    @pytest.mark.parametrize("setting", _NEW_GUARDS, ids=lambda s: s.id)
    def test_subgroup_is_sub_processor(self, setting: SettingExecutor) -> None:
        assert setting.detect_args.get("subgroup") == self._SUB_PROCESSOR
        assert setting.apply_args.get("subgroup") == self._SUB_PROCESSOR

    def test_no_two_new_settings_share_a_guid(self) -> None:
        guids = [s.detect_args["setting"] for s in _NEW_GUARDS]
        assert len(guids) == len(set(guids)), guids
