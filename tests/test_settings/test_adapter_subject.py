"""Every per-adapter setting names the adapter it belongs to, apart from its name.

A machine with Wi-Fi and Ethernet registers `power_management` twice. The
English short name ends in the adapter, but a translated name is keyed per
setting, so without a separate `subject` the two rows rendered identically on
Home and read as one finding listed twice.
"""

from __future__ import annotations

from fpstune.api.definitions_view import setting_to_response
from fpstune.settings.definitions.network import adapter_key
from fpstune.settings.discovery.network import register_adapter_settings
from fpstune.settings.registry import SettingsRegistry

WIFI_ID = "PCI\\VEN_8086&DEV_2725&SUBSYS_00248086&REV_1A\\4&2B0C1E0&0&00E0"
ETHERNET_ID = "PCI\\VEN_10EC&DEV_8125&SUBSYS_86771043&REV_05\\01000000684CE00000"


def _registry() -> SettingsRegistry:
    registry = SettingsRegistry(discover_dynamic=False)
    register_adapter_settings(registry, 7, "Wi-Fi", "Native 802.11", instance_id=WIFI_ID)
    register_adapter_settings(registry, 14, "Ethernet", "802.3", instance_id=ETHERNET_ID)
    return registry


def test_two_adapters_same_setting_carry_their_own_subject() -> None:
    registry = _registry()
    wifi = registry.get(f"network:{adapter_key(WIFI_ID)}:power_management")
    ethernet = registry.get(f"network:{adapter_key(ETHERNET_ID)}:power_management")
    assert wifi is not None and ethernet is not None
    assert (wifi.subject, ethernet.subject) == ("Wi-Fi", "Ethernet")


def test_every_per_adapter_setting_has_a_subject_and_reaches_the_api() -> None:
    keys = (f"network:{adapter_key(WIFI_ID)}:", f"network:{adapter_key(ETHERNET_ID)}:")
    per_adapter = [s for s in _registry().get_all() if s.id.startswith(keys)]
    assert per_adapter
    assert [s.id for s in per_adapter if not s.subject] == []
    assert {setting_to_response(s).subject for s in per_adapter} == {"Wi-Fi", "Ethernet"}
