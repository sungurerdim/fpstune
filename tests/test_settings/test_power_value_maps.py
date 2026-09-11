"""A power setting must be able to read back every state Windows can hold.

`test_powercfg_guids.py` checks one direction — every index fpstune *writes* is
one Windows accepts. The other direction had no test, and that is where the
defect was: `cpu_boost`'s map went 0, 1, 3, 4, 5 while Windows publishes 0..6
here, so a machine sitting on Windows' own stock value (index 2, Aggressive)
detected as the bare integer `2` — outside the setting's own `choices`, which
C6 forbids — and a machine on 5 (Aggressive At Guaranteed) read as though it
were on 4 (Efficient Aggressive), a different control.

The published indices come from Windows' own catalogue on this machine,

    ...\\Power\\PowerSettings\\<subgroup>\\<setting>\\<n>\\FriendlyName

not from a list in this file: a vendor that publishes an eighth boost mode
tomorrow must fail here rather than surface as an unmapped integer in the UI.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.base import DetectType, SettingExecutor, SettingValueType
from fpstune.settings.definitions.power import POWER_SETTINGS
from fpstune.settings.executors import map_raw_to_display

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="reads Windows' own power catalogue"
)

if sys.platform == "win32":
    import winreg

_POWER_CATALOGUE = r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings"


def _enum_settings() -> list[tuple[SettingExecutor, str, str]]:
    """Every shipped powercfg setting whose value is one of a published set."""
    out: list[tuple[SettingExecutor, str, str]] = []
    for setting in POWER_SETTINGS:
        if setting.detect_type is not DetectType.POWERCFG:
            continue
        if setting.value_type is not SettingValueType.CHOICE or not setting.value_map:
            continue
        subgroup = setting.detect_args.get("subgroup")
        guid = setting.detect_args.get("setting")
        if subgroup and guid:
            out.append((setting, subgroup, guid))
    return out


def _published_indices(subgroup: str, guid: str) -> set[int]:
    """The raw indices Windows publishes for one setting, empty when it is a range."""
    indices: set[int] = set()
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{_POWER_CATALOGUE}\\{subgroup}\\{guid}")
    except OSError:
        return indices
    with key:
        position = 0
        while True:
            try:
                name = winreg.EnumKey(key, position)
            except OSError:
                break
            position += 1
            if name.isdigit():
                indices.add(int(name))
    return indices


def test_the_catalogue_is_readable() -> None:
    """Positive control: an empty catalogue would make every test below vacuous."""
    settings = _enum_settings()
    assert settings, "no powercfg choice settings found — harness is broken"
    assert any(_published_indices(sub, g) for _s, sub, g in settings), (
        "no setting published any index — harness is broken"
    )


@pytest.mark.parametrize(
    ("setting", "subgroup", "guid"),
    [pytest.param(s, sub, g, id=s.id) for s, sub, g in _enum_settings()],
)
def test_every_index_windows_publishes_is_mapped(
    setting: SettingExecutor, subgroup: str, guid: str
) -> None:
    published = _published_indices(subgroup, guid)
    if not published:
        pytest.skip(f"{setting.id} publishes no indices on this machine")

    unmapped = {
        index for index in published if map_raw_to_display(setting.value_map, index) == index
    }
    assert not unmapped, (
        f"{setting.id} has no name for {sorted(unmapped)}, which Windows publishes here "
        f"(it publishes {sorted(published)}). A machine holding one of those detects as a "
        "bare integer, outside the setting's own choices."
    )


@pytest.mark.parametrize(
    ("setting", "subgroup", "guid"),
    [pytest.param(s, sub, g, id=s.id) for s, sub, g in _enum_settings()],
)
def test_every_published_index_reads_back_as_one_of_the_choices(
    setting: SettingExecutor, subgroup: str, guid: str
) -> None:
    """C6: detection never returns a value outside `choices`."""
    published = _published_indices(subgroup, guid)
    if not published:
        pytest.skip(f"{setting.id} publishes no indices on this machine")

    outside = {
        index
        for index in published
        if map_raw_to_display(setting.value_map, index) not in setting.choices
    }
    assert not outside, (
        f"{setting.id} maps {sorted(outside)} to something that is not in its choices "
        f"{setting.choices}"
    )
