"""Every powercfg GUID fpstune ships must be one Windows actually publishes.

Four shipped GUIDs were not. powercfg answers

    The power scheme, subgroup or setting specified does not exist.

for a GUID it does not know, and the executor turned that into `not_available` —
which an earlier pass read as "the active plan does not carry this subgroup" and
closed. It was never the plan. `power:cpu_min_parking` is ESSENTIAL scope and
`evidence_level="proven"`, and had never detected or written anything anywhere.

Nothing could have caught it: a wrong GUID and an absent subgroup are the same
observation from outside. The only distinguishing source is Windows' own catalogue
of settings, which is what these tests read.

    HKLM\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerSettings
        <subgroup>\\<setting>              the setting exists
            FriendlyName                   what it is called
            <n>\\FriendlyName              each value it accepts
            ValueMin / ValueMax            or the range, for numeric settings

The second half matters as much as the first: even with the right GUID, the scale
policies mapped `1` to "rocket" when Windows defines 1 as Single and 2 as Rocket,
so applying the recommendation would have written a different policy than the one
the UI named.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.base import DetectType, SettingValueType
from fpstune.settings.registry import SettingsRegistry

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

if sys.platform == "win32":
    import winreg

_POWER_SETTINGS = r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings"


def _powercfg_settings() -> list:
    """Every shipped setting that talks to powercfg by subgroup + setting GUID."""
    out = []
    for setting in SettingsRegistry().get_all():
        uses_powercfg = DetectType.POWERCFG in (setting.detect_type, setting.apply_type)
        if not uses_powercfg:
            continue
        for args in (setting.detect_args or {}, setting.apply_args or {}):
            if args.get("subgroup") and args.get("setting"):
                out.append((setting, args["subgroup"], args["setting"]))
    return out


def _open(subgroup: str, setting: str):
    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{_POWER_SETTINGS}\\{subgroup}\\{setting}")


def _friendly_name(key) -> str:
    try:
        return str(winreg.QueryValueEx(key, "FriendlyName")[0])
    except OSError:
        return "<unnamed>"


def _accepted_values(key) -> set[int]:
    """The raw indices this setting publishes, empty for numeric-range settings."""
    values: set[int] = set()
    index = 0
    while True:
        try:
            name = winreg.EnumKey(key, index)
        except OSError:
            break
        index += 1
        if name.isdigit():
            values.add(int(name))
    return values


def _range(key) -> tuple[int, int] | None:
    try:
        low = int(winreg.QueryValueEx(key, "ValueMin")[0])
        high = int(winreg.QueryValueEx(key, "ValueMax")[0])
    except OSError:
        return None
    return low, high


def test_the_registry_catalogue_is_readable() -> None:
    """Positive control: if this key were unreadable every test below would pass empty."""
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _POWER_SETTINGS) as key:
        assert winreg.QueryInfoKey(key)[0] > 0, "no power subgroups — harness is broken"
    assert _powercfg_settings(), "no powercfg settings found — harness is broken"


@pytest.mark.parametrize(
    ("setting", "subgroup", "guid"),
    [pytest.param(s, sub, g, id=f"{s.id}") for s, sub, g in _powercfg_settings()],
)
def test_windows_publishes_this_setting(setting, subgroup: str, guid: str) -> None:
    """A GUID Windows does not publish is one powercfg will refuse outright."""
    try:
        key = _open(subgroup, guid)
    except FileNotFoundError:
        pytest.fail(
            f"{setting.id} points at {subgroup}\\{guid}, which is not a power setting "
            "Windows publishes. powercfg will answer 'does not exist' for it, and the "
            "executor will report not_available forever."
        )
    with key:
        assert _friendly_name(key) != "<unnamed>"


@pytest.mark.parametrize(
    ("setting", "subgroup", "guid"),
    [
        pytest.param(s, sub, g, id=f"{s.id}")
        for s, sub, g in _powercfg_settings()
        if s.value_type == SettingValueType.CHOICE and s.apply_value_map
    ],
)
def test_every_value_it_writes_is_one_windows_accepts(setting, subgroup, guid) -> None:
    """The scale-policy bug: "rocket" was mapped to 1, but 1 is Single and 2 is Rocket."""
    with _open(subgroup, guid) as key:
        accepted = _accepted_values(key)
    if not accepted:
        pytest.skip(f"{setting.id} is a numeric-range setting, covered by the range test")

    written = {v for v in setting.apply_value_map.values() if isinstance(v, int)}
    unknown = written - accepted
    assert not unknown, (
        f"{setting.id} would write {sorted(unknown)}, which Windows does not accept "
        f"here (it accepts {sorted(accepted)})"
    )


@pytest.mark.parametrize(
    ("setting", "subgroup", "guid"),
    [
        pytest.param(s, sub, g, id=f"{s.id}")
        for s, sub, g in _powercfg_settings()
        if s.value_type == SettingValueType.INT
    ],
)
def test_numeric_recommendations_are_inside_the_published_range(setting, subgroup, guid) -> None:
    with _open(subgroup, guid) as key:
        bounds = _range(key)
    if bounds is None:
        pytest.skip(f"{setting.id} publishes no ValueMin/ValueMax")

    low, high = bounds
    for label, value in (
        ("default_value", setting.default_value),
        ("recommended_value", setting.recommended_value),
    ):
        if isinstance(value, int):
            assert low <= value <= high, (
                f"{setting.id}.{label} is {value}, outside Windows' own range {low}-{high}"
            )
