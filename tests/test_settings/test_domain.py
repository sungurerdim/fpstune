"""Every tweak lands on exactly one page, and a hardware tweak names its component.

The category is the physical component a tweak acts on, never how it is set. The
failure these guard against shipped: PCIe link power saving, USB selective suspend
and Wi-Fi power saving are powercfg keys, so a module-based split filed them under
Software, away from the devices they slow down.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from fpstune.settings.base import SettingExecutor
from fpstune.settings.registry import SettingsRegistry

# A power-plan or system key whose name says it acts on hardware. Matching on the
# id's name is the gate's *check*, never the classification itself.
_HARDWARE_NAMED = re.compile(r"(pcie|usb|disk|wlan|processor|cpu_|xmp|thermal)")


@pytest.fixture(scope="module")
def settings() -> list[SettingExecutor]:
    return SettingsRegistry(discover_dynamic=False).get_all()


def test_every_setting_has_one_domain(settings: list[SettingExecutor]) -> None:
    for s in settings:
        assert s.domain in ("hardware", "software", "game"), s.id


def test_every_hardware_tweak_names_its_component(settings: list[SettingExecutor]) -> None:
    for s in settings:
        if s.domain == "hardware":
            assert s.component, s.id


def test_hardware_named_power_and_system_keys_are_not_software(
    settings: list[SettingExecutor],
) -> None:
    misfiled = [
        s.id
        for s in settings
        if s.module in ("power", "system")
        and _HARDWARE_NAMED.search(s.name)
        and s.domain == "software"
    ]
    assert misfiled == []


@pytest.mark.parametrize(
    ("setting_id", "component"),
    [
        ("power:pcie_link_state", "pcie"),
        ("power:usb_selective_suspend", "usb"),
        ("power:wlan_power_saving", "network_adapter"),
        ("power:disk_timeout", "storage"),
        ("power:cpu_min_state", "cpu"),
        ("power:thermal_cooling", "cpu"),
        ("system:xmp_expo", "memory"),
        ("system:thermal_condition", "cpu"),
        ("game:hags", "gpu"),
    ],
)
def test_moved_tweaks_sit_on_their_component(
    settings: list[SettingExecutor], setting_id: str, component: str
) -> None:
    by_id = {s.id: s for s in settings}
    assert by_id[setting_id].component == component
    assert by_id[setting_id].domain == "hardware"


def test_game_config_line_is_game_and_windows_game_mode_is_software(
    settings: list[SettingExecutor],
) -> None:
    by_id = {s.id: s for s in settings}
    assert by_id["game:game_mode"].domain == "software"
    assert all(s.domain == "game" for s in settings if s.module == "game_config")


def test_per_adapter_setting_is_a_network_adapter_tweak(
    settings: list[SettingExecutor],
) -> None:
    template = next(s for s in settings if s.id == "power:hibernation")
    adapter = replace(template, id="network:pci_ven_8086_dev_2725:eee", component=None)
    system_wide = replace(template, id="network:tcp_autotuning", component=None)
    assert adapter.component == "network_adapter"
    assert system_wide.domain == "software"
