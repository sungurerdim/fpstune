"""`reset` has to write what Windows shipped on *this* machine.

C6 contracts `POST /settings/{id}/reset` to write "the curated stock value
(Windows stock)". Eight of the shipped powercfg settings carried a
`default_value` that Windows never shipped here, and three of them were the
*battery* default written onto mains:

    cpu_min_parking 0 (machine: AC 100, DC 10) · cpu_boost "enabled" (AC 2) ·
    cpu_increase_threshold 90 (AC 60, DC 90) · cpu_decrease_threshold 5 (AC 20,
    DC 30) · cpu_epp 50 (AC 33, DC 50) · disk_timeout 600 (AC 1200, DC 600) ·
    thermal_cooling "passive" (AC active, DC passive) · wlan_power_saving
    "medium" (AC maximum_performance, DC medium)

`cpu_epp`'s 50 is the figure Microsoft's tuning document quotes for Windows
Server. Taking a default from a document instead of from the machine is the
C1 defect the product goal opens with, and the fix is the same one every other
value gets: derive it. Windows publishes its own answer beside each setting,

    ...\\Power\\PowerSettings\\<subgroup>\\<setting>
        \\DefaultPowerSchemeValues\\381b4222-...\\ACSettingIndex

which is populated per machine by the processor driver, so an AMD or a
14th-gen host may legitimately answer differently. This file reads that key
itself rather than through the shipped reader: a test that calls the same
function the product calls only ever proves the two agree, including when they
agree on the wrong scheme GUID.

The shipped constants stay in the source as the fallback for a machine that
publishes no default — corrected, so the fallback is right too.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)
from fpstune.settings.definitions.power import (
    POWER_CPU_DECREASE_THRESHOLD,
    POWER_SETTINGS,
    adopt_windows_defaults,
)
from fpstune.settings.executors import map_raw_to_display

if sys.platform == "win32":
    import winreg

_POWER_CATALOGUE = r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings"
_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"


def _powercfg_settings() -> list[tuple[SettingExecutor, str, str]]:
    """Every shipped power setting powercfg reads by subgroup + setting GUID."""
    out: list[tuple[SettingExecutor, str, str]] = []
    for setting in POWER_SETTINGS:
        if setting.detect_type is not DetectType.POWERCFG:
            continue
        subgroup = setting.detect_args.get("subgroup")
        guid = setting.detect_args.get("setting")
        if subgroup and guid:
            out.append((setting, subgroup, guid))
    return out


def _balanced_ac_index(subgroup: str, guid: str) -> int | None:
    """Windows' own Balanced mains default for one setting, read here, not recalled."""
    path = f"{_POWER_CATALOGUE}\\{subgroup}\\{guid}\\DefaultPowerSchemeValues\\{_BALANCED}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            raw, _ = winreg.QueryValueEx(key, "ACSettingIndex")
    except OSError:
        return None
    return raw if isinstance(raw, int) else None


def _setting(**overrides: object) -> SettingExecutor:
    """A powercfg setting with no machine of its own, for the fake-reader tests."""
    args = {"subgroup": "sub-guid", "setting": "setting-guid"}
    defaults: dict = {
        "id": "power:test_setting",
        "category": SettingCategory.POWER,
        "display_name": "Test",
        "description": "A test setting.",
        "value_type": SettingValueType.CHOICE,
        "choices": ("off", "on"),
        "default_value": "off",
        "recommended_value": "on",
        "current_impact": "",
        "recommended_impact": "",
        "effect": "",
        "impact_scores": {"fps": "+1%"},
        "detect_type": DetectType.POWERCFG,
        "detect_command": "",
        "detect_args": dict(args),
        "value_map": {0: "off", 1: "on"},
        "apply_type": DetectType.POWERCFG,
        "apply_command": "",
        "apply_args": dict(args),
        "apply_value_map": {"off": 0, "on": 1},
    }
    defaults.update(overrides)
    return SettingExecutor(**defaults)  # type: ignore[arg-type]


@pytest.mark.skipif(sys.platform != "win32", reason="reads Windows' own power catalogue")
class TestAgainstThisMachine:
    def test_the_catalogue_is_readable(self) -> None:
        """Positive control: an unreadable catalogue would skip every test below."""
        settings = _powercfg_settings()
        assert settings, "no powercfg settings found — harness is broken"
        answered = [s for s, sub, g in settings if _balanced_ac_index(sub, g) is not None]
        assert answered, "no setting published a Balanced default — harness is broken"

    @pytest.mark.parametrize(
        ("setting", "subgroup", "guid"),
        [pytest.param(s, sub, g, id=s.id) for s, sub, g in _powercfg_settings()],
    )
    def test_default_value_is_the_windows_default_here(
        self, setting: SettingExecutor, subgroup: str, guid: str
    ) -> None:
        raw = _balanced_ac_index(subgroup, guid)
        if raw is None:
            pytest.skip(f"{setting.id} publishes no Balanced default on this machine")

        expected = map_raw_to_display(setting.value_map, raw)
        assert values_equal(setting.default_value, expected), (
            f"{setting.id}.default_value is {setting.default_value!r}, but Windows ships "
            f"{expected!r} (index {raw}) here. reset would write a value this machine "
            "never had."
        )


class TestDerivation:
    def test_the_machines_own_default_replaces_the_shipped_constant(self) -> None:
        setting = _setting(default_value="off")
        adopt_windows_defaults([setting], reader=lambda _sub, _guid: 1)
        assert setting.default_value == "on"

    def test_an_unpublished_setting_keeps_the_shipped_constant(self) -> None:
        """A machine whose catalogue has no such key still needs a default to reset to."""
        setting = _setting(default_value="off")
        adopt_windows_defaults([setting], reader=lambda _sub, _guid: None)
        assert setting.default_value == "off"

    def test_a_free_form_setting_takes_the_index_itself(self) -> None:
        """An empty value_map means the index is the value — seconds, percent, ms."""
        setting = _setting(
            value_type=SettingValueType.INT,
            choices=(),
            value_map={},
            apply_value_map={},
            default_value=600,
            recommended_value=0,
        )
        adopt_windows_defaults([setting], reader=lambda _sub, _guid: 1200)
        assert setting.default_value == 1200

    def test_an_index_the_map_does_not_know_keeps_the_shipped_constant(self) -> None:
        """Never a default outside `choices` (C6): an unmapped index is not a value."""
        setting = _setting(default_value="off")
        adopt_windows_defaults([setting], reader=lambda _sub, _guid: 7)
        assert setting.default_value == "off"

    def test_a_setting_powercfg_does_not_read_is_left_alone(self) -> None:
        """Hibernation lives in one registry DWORD and has no scheme default."""
        registry_setting = _setting(
            id="power:hibernation",
            detect_type=DetectType.REGISTRY,
            detect_args={"path": "SYSTEM", "name": "HibernateEnabled", "hive": "HKLM"},
            default_value="off",
        )
        adopt_windows_defaults([registry_setting], reader=lambda _sub, _guid: 1)
        assert registry_setting.default_value == "off"

    def test_a_drift_guard_moves_its_recommendation_with_the_default(self) -> None:
        """A guard recommends whatever Windows ships — on every machine, not on one.

        `cpu_decrease_threshold` recommends Windows' own value (see the copy
        there). Pinning that to the constant 20 would, on a host whose driver
        publishes 40, turn the guard back into the harmful tweak it replaced:
        a lowered scale-down threshold holds clocks through idle periods.
        """
        guard = _setting(
            id="power:cpu_decrease_threshold",
            value_type=SettingValueType.INT,
            choices=(),
            value_map={},
            apply_value_map={},
            default_value=20,
            recommended_value=20,
        )
        adopt_windows_defaults([guard], reader=lambda _sub, _guid: 40)
        assert guard.default_value == 40
        assert guard.recommended_value == 40

    def test_an_ordinary_tweak_keeps_its_recommendation(self) -> None:
        """Deriving the default must never quietly delete the tweak itself."""
        tweak = _setting(default_value="off", recommended_value="on")
        adopt_windows_defaults([tweak], reader=lambda _sub, _guid: 1)
        assert tweak.recommended_value == "on"

    def test_the_shipped_guard_recommends_the_shipped_default(self) -> None:
        """Whatever this machine answered, the guard and the default agree."""
        assert values_equal(
            POWER_CPU_DECREASE_THRESHOLD.recommended_value,
            POWER_CPU_DECREASE_THRESHOLD.default_value,
        )
