"""Reset writes the driver's own default for the on/off adapter settings that read
their state through a cmdlet or a keyword search.

``with_driver_default`` only ever saw settings declaring ``batch_adapter_keyword``.
LSO, checksum offload, Wake-on-LAN, U-APSD and Throughput Booster find their
property another way (a cmdlet, two keywords, a regex over keyword and display
name), so their ``default_value`` stayed one vendor's ``Enabled`` and reset wrote it
to a driver that ships the feature off. The driver publishes every default in the
same table the flow-control and EEE settings already read.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from unittest.mock import patch

import pytest

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions.network import (
    adapter_key,
    create_checksum_offload_setting,
    create_lso_setting,
    create_power_management_setting,
    create_speed_duplex_setting,
    create_throughput_booster_setting,
    create_uapsd_setting,
    create_wake_on_lan_setting,
)
from fpstune.settings.discovery.network import (
    discover_network_adapter_settings,
    with_driver_default,
)
from fpstune.settings.discovery.probes import NetworkAdapter
from fpstune.settings.registry import SettingsRegistry

Factory = Callable[[int, str], SettingExecutor]

# factory -> the keywords a real driver publishes for that feature (lowercased,
# the way the discovery probe stores them) and which of them count together.
PUBLISHED: dict[str, tuple[Factory, tuple[str, ...]]] = {
    "lso": (create_lso_setting, ("*lsov2ipv4", "*lsov2ipv6")),
    "checksum": (create_checksum_offload_setting, ("*tcpchecksumoffloadipv4",)),
    "wol": (create_wake_on_lan_setting, ("*wakeonmagicpacket", "*wakeonpattern")),
    "uapsd": (create_uapsd_setting, ("uapsdsupport",)),
    "booster": (create_throughput_booster_setting, ("throughputbooster",)),
}


@pytest.mark.parametrize("name", sorted(PUBLISHED))
class TestFeatureShippedOff:
    def test_every_published_keyword_off_makes_disabled_the_stock_value(self, name: str) -> None:
        factory, keywords = PUBLISHED[name]
        declared = factory(14, "Ethernet")
        assert declared.default_value == "Enabled"  # the constant this replaces
        adopted = with_driver_default(declared, dict.fromkeys(keywords, "0"))
        assert adopted.default_value == "Disabled"
        assert adopted.default_value in adopted.choices

    def test_one_keyword_still_on_keeps_enabled(self, name: str) -> None:
        """Detection calls a feature Disabled only when every keyword is 0, so the
        stock value is read the same way: a half-on driver ships it Enabled."""
        factory, keywords = PUBLISHED[name]
        declared = factory(14, "Ethernet")
        defaults = dict.fromkeys(keywords, "0")
        defaults[keywords[-1]] = "1"
        assert with_driver_default(declared, defaults).default_value == "Enabled"

    def test_nothing_published_keeps_the_declared_default(self, name: str) -> None:
        factory, _ = PUBLISHED[name]
        declared = factory(14, "Ethernet")
        assert with_driver_default(declared, {}).default_value == declared.default_value
        unrelated = {"*flowcontrol": "0", "*eee": "0"}
        assert with_driver_default(declared, unrelated).default_value == declared.default_value

    def test_a_default_that_is_not_a_number_is_not_a_reading(self, name: str) -> None:
        factory, keywords = PUBLISHED[name]
        declared = factory(14, "Ethernet")
        garbled = dict.fromkeys(keywords, "n/a")
        assert with_driver_default(declared, garbled).default_value == declared.default_value


class TestMatchTracksTheCommand:
    """The pattern that picks the stock value must pick what detect reads."""

    @pytest.mark.parametrize(
        ("factory", "keyword"),
        [
            (create_lso_setting, "*LsoV2IPv4"),
            (create_lso_setting, "*LsoV2IPv6"),
            (create_checksum_offload_setting, "*TCPChecksumOffloadIPv4"),
            (create_wake_on_lan_setting, "*WakeOnMagicPacket"),
            (create_wake_on_lan_setting, "*WakeOnPattern"),
        ],
    )
    def test_the_keywords_the_commands_use_are_matched(
        self, factory: Factory, keyword: str
    ) -> None:
        setting = factory(14, "Ethernet")
        pattern = str(setting.detect_args["driver_default_match"])
        assert re.search(pattern, keyword, re.IGNORECASE)

    @pytest.mark.parametrize(
        ("factory", "ps_pattern"),
        [
            (create_uapsd_setting, "UAPSD|APSD"),
            (create_throughput_booster_setting, "ThroughputBoost"),
        ],
    )
    def test_the_search_is_the_one_the_detect_script_runs(
        self, factory: Factory, ps_pattern: str
    ) -> None:
        setting = factory(14, "Ethernet")
        assert setting.detect_args["driver_default_match"] == ps_pattern
        assert f"-match '{ps_pattern}'" in setting.detect_command

    def test_lso_does_not_borrow_the_v1_keyword(self) -> None:
        """Detection reads IPv4Enabled/IPv6Enabled, the V2 pair; V1 is a different knob."""
        pattern = str(create_lso_setting(14, "Ethernet").detect_args["driver_default_match"])
        assert not re.search(pattern, "*LsoV1IPv4", re.IGNORECASE)

    def test_checksum_ignores_the_udp_and_ip_siblings(self) -> None:
        """Detection reads TcpIPv4Enabled alone."""
        declared = create_checksum_offload_setting(14, "Ethernet")
        siblings = {"*udpchecksumoffloadipv4": "0", "*ipchecksumoffloadipv4": "0"}
        assert with_driver_default(declared, siblings).default_value == "Enabled"


class TestFoundOnlyByDisplayName:
    """U-APSD and Throughput Booster are found by keyword *or* by display name.

    A driver that spells the keyword its own way is matched only through the
    name its control panel shows, and its default used to be ignored: reset
    wrote the declared ``Enabled`` to a driver that ships the feature off.
    """

    @pytest.mark.parametrize(
        ("factory", "keyword", "display_name"),
        [
            (create_uapsd_setting, "vendorpowersavepoll", "WMM U-APSD Support"),
            (create_throughput_booster_setting, "vendorburstmode", "Throughput Booster"),
        ],
    )
    def test_the_default_of_a_name_matched_property_is_the_stock_value(
        self, factory: Factory, keyword: str, display_name: str
    ) -> None:
        declared = factory(14, "Wi-Fi")
        adopted = with_driver_default(declared, {keyword: "0"}, {keyword: display_name})
        assert adopted.default_value == "Disabled"

    def test_a_property_the_name_does_not_match_is_not_borrowed(self) -> None:
        declared = create_uapsd_setting(14, "Wi-Fi")
        names = {"vendorfragmentation": "Fragmentation Threshold"}
        adopted = with_driver_default(declared, {"vendorfragmentation": "0"}, names)
        assert adopted.default_value == declared.default_value

    def test_no_published_default_writes_no_invented_value(self) -> None:
        """The keyword path leaves the declared default when the driver names none; so does this."""
        declared = create_uapsd_setting(14, "Wi-Fi")
        adopted = with_driver_default(declared, {}, {"vendorpowersavepoll": "WMM U-APSD Support"})
        assert adopted.default_value == declared.default_value

    def test_a_default_that_is_not_a_number_is_not_a_reading_here_either(self) -> None:
        declared = create_uapsd_setting(14, "Wi-Fi")
        adopted = with_driver_default(
            declared, {"vendorpowersavepoll": "n/a"}, {"vendorpowersavepoll": "WMM U-APSD"}
        )
        assert adopted.default_value == declared.default_value

    @pytest.mark.parametrize(
        ("factory", "ps_pattern"),
        [
            (create_uapsd_setting, "U.?APSD"),
            (create_throughput_booster_setting, "Throughput.?Booster"),
        ],
    )
    def test_the_name_search_is_the_one_the_detect_script_runs(
        self, factory: Factory, ps_pattern: str
    ) -> None:
        setting = factory(14, "Wi-Fi")
        assert setting.detect_args["driver_default_display_match"] == ps_pattern
        assert f"$_.DisplayName -match '{ps_pattern}'" in setting.detect_command

    def test_the_probe_reads_every_keywords_display_name(self) -> None:
        registry = SettingsRegistry(discover_dynamic=False)
        payload = {
            "7": {"names": {"*FlowControl": "Flow Control", "Empty": "", "UAPSD": " U-APSD "}}
        }
        completed = subprocess.CompletedProcess(
            args=["powershell"], returncode=0, stdout=json.dumps(payload), stderr=""
        )
        with patch("fpstune.utils.process_watch.run", return_value=completed):
            assert registry._probes.adapter_property_names() == {
                7: {"*flowcontrol": "Flow Control", "uapsd": "U-APSD"}
            }

    def test_discovery_hands_the_names_to_the_derivation(self) -> None:
        """End to end: what the probe reads reaches the registered setting."""
        registry = SettingsRegistry(discover_dynamic=False)
        payload = {
            "7": {
                "defaults": {"VendorPowerSavePoll": "0"},
                "names": {"VendorPowerSavePoll": "WMM U-APSD Support"},
            }
        }
        instance_id = "PCI\\VEN_8086&DEV_2725&SUBSYS_00248086&REV_1A\\4&2B0C1E0&0&00E0"
        probes = registry._probes
        with (
            patch.object(
                probes,
                "active_adapters",
                return_value=[NetworkAdapter(7, "Wi-Fi", "Native 802.11", instance_id)],
            ),
            patch.object(probes, "adapter_advanced", return_value=payload),
        ):
            discover_network_adapter_settings(registry, probes)
        setting = registry.get(f"network:{adapter_key(instance_id)}:uapsd")
        assert setting is not None
        assert setting.default_value == "Disabled"


@pytest.mark.parametrize("factory", [create_speed_duplex_setting, create_power_management_setting])
class TestStaysConstantOnPurpose:
    """Auto-negotiation and the Windows-stock power bits are not the driver's to set.

    Forcing a speed lowers the ceiling (C1), so reset never adopts a forced default;
    adapter power management is PnPCapabilities, which no driver publishes a default
    for. Declaring a match here would invite a derivation that has no source.
    """

    def test_no_driver_default_is_adopted(self, factory: Factory) -> None:
        declared = factory(14, "Ethernet")
        assert "driver_default_match" not in declared.detect_args
        everything_off = {"*speedduplex": "6", "*wakeonmagicpacket": "0"}
        assert with_driver_default(declared, everything_off).default_value == declared.default_value
