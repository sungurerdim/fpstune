"""The Wi-Fi link-quality advisory: numbers from wlanapi, words the user can act on.

The owner's ask (2026-09-02): a player on a weak signal or on the 2.4 GHz band
should learn it on the home page, the way the Ethernet advisory already tells them
a cable is capping the line. Everything here is the WLAN API's own numbers — the
signal-quality percentage and the BSS centre frequency — never ``netsh`` text.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, NOT_AVAILABLE
from fpstune.settings.definitions.network import create_wifi_link_quality_setting
from fpstune.settings.discovery import all_discoverers
from fpstune.settings.discovery.network import discover_wifi_link_quality
from fpstune.settings.discovery.probes import HardwareProbes
from fpstune.settings.executors import python_actions
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.python_actions import (
    WEAK_SIGNAL_PERCENT,
    classify_wifi_link,
    wifi_link_quality,
)
from fpstune.utils.winapi import wlan
from fpstune.utils.winapi.wlan import WlanRecord

GUID = "a1b2c3d4-0000-4000-8000-000000000001"


def _record(guid: str = GUID, signal: int = 90, center_khz: int = 5_180_000) -> WlanRecord:
    return WlanRecord(
        interface_guid=guid,
        channel=36,
        center_khz=center_khz,
        phy_type=7,
        signal_percent=signal,
        auth_algorithm=4,
        ssid="home",
        profile_name="home",
        bssid="aa:bb:cc:dd:ee:ff",
    )


class TestTheClassification:
    def test_the_signal_threshold_sits_at_about_minus_70_dbm(self) -> None:
        assert WEAK_SIGNAL_PERCENT == 60
        assert classify_wifi_link(59, 5_180_000) == "weak_signal"
        assert classify_wifi_link(60, 5_180_000) == "good"

    def test_the_two_point_four_band_is_named_when_the_signal_is_fine(self) -> None:
        assert classify_wifi_link(90, 2_437_000) == "on_2_4ghz"  # channel 6
        assert classify_wifi_link(90, 5_180_000) == "good"  # channel 36
        assert classify_wifi_link(90, 5_955_000) == "good"  # 6 GHz

    def test_a_weak_signal_outranks_the_band(self) -> None:
        """Moving closer is the nearer fix; the band comes second."""
        assert classify_wifi_link(30, 2_437_000) == "weak_signal"

    def test_an_unknown_band_judges_the_signal_only(self) -> None:
        """center_khz 0 means no BSS entry matched; that is not 2.4 GHz."""
        assert classify_wifi_link(90, 0) == "good"
        assert classify_wifi_link(10, 0) == "weak_signal"


class TestTheDetector:
    def test_it_answers_for_the_radio_it_was_asked_about(self, monkeypatch) -> None:
        other = _record(guid="ffffffff-0000-4000-8000-000000000002", signal=10)
        monkeypatch.setattr(wlan, "query_connected", lambda: [other, _record(signal=45)])
        assert wifi_link_quality({"interface_guid": GUID}) == "weak_signal"

    def test_braces_and_case_in_the_guid_do_not_matter(self, monkeypatch) -> None:
        monkeypatch.setattr(wlan, "query_connected", lambda: [_record(center_khz=2_412_000)])
        assert wifi_link_quality({"interface_guid": "{" + GUID.upper() + "}"}) == "on_2_4ghz"

    def test_a_disconnected_radio_is_the_absent_sentinel(self, monkeypatch) -> None:
        """Not connected means nothing to advise on — the setting steps aside."""
        monkeypatch.setattr(wlan, "query_connected", lambda: [])
        answer = wifi_link_quality({"interface_guid": GUID})
        assert answer == NOT_AVAILABLE
        assert answer in ABSENT_READINGS


class TestThroughTheExecutor:
    def test_detect_reads_python_not_powershell(self, monkeypatch) -> None:
        setting = create_wifi_link_quality_setting(12, GUID, "Intel Wi-Fi 6 AX201")

        def no_powershell(*_a: object, **_k: object) -> tuple[bool, str]:
            raise AssertionError("a Python detector must never spawn PowerShell")

        monkeypatch.setattr("fpstune.settings.executors.powershell.run_powershell", no_powershell)
        monkeypatch.setattr(wlan, "query_connected", lambda: [_record(signal=40)])

        value, error = PowerShellExecutor().detect(setting)

        assert (value, error) == ("weak_signal", None)
        assert value in setting.choices

    def test_the_detector_table_names_the_settings_key(self) -> None:
        setting = create_wifi_link_quality_setting(12, GUID, "x")
        assert setting.detect_command in python_actions.PYTHON_DETECTORS


class TestTheAdvisoryItself:
    def test_it_is_read_only_and_keyed_like_its_adapter_siblings(self) -> None:
        setting = create_wifi_link_quality_setting(12, GUID, "Intel Wi-Fi 6 AX201")
        assert setting.is_readonly
        assert setting.id == "network:12:wifi_link_quality"
        assert setting.recommended_value == setting.default_value == "good"
        assert setting.detect_args == {"interface_guid": GUID}
        assert setting.description.endswith(".")
        assert not setting.effect.endswith(".")
        assert any(key != "stability" for key in setting.impact_scores)


class _FakeRegistrar:
    def __init__(self) -> None:
        self.registered: list[Any] = []

    def register(self, setting: Any) -> None:
        self.registered.append(setting)

    def get(self, setting_id: str) -> Any:
        return next((s for s in self.registered if s.id == setting_id), None)

    def get_all(self) -> list[Any]:
        return list(self.registered)


def _probes(adapters: list[tuple[int, str, str]], guids: dict[int, str]) -> HardwareProbes:
    fake = SimpleNamespace(active_adapters=lambda: adapters, adapter_guids=lambda: guids)
    return cast(HardwareProbes, fake)


class TestDiscovery:
    def test_one_advisory_per_wifi_adapter_keyed_by_its_index(self) -> None:
        registrar = _FakeRegistrar()
        adapters = [(7, "Ethernet", "802.3"), (12, "Wi-Fi", "Native 802.11")]
        count = discover_wifi_link_quality(registrar, _probes(adapters, {7: "eth-guid", 12: GUID}))

        assert count == 1
        [setting] = registrar.registered
        assert setting.id == "network:12:wifi_link_quality"
        assert setting.detect_args["interface_guid"] == GUID

    def test_a_radio_without_a_guid_is_skipped_rather_than_registered_blind(self) -> None:
        registrar = _FakeRegistrar()
        count = discover_wifi_link_quality(registrar, _probes([(12, "Wi-Fi", "Native 802.11")], {}))
        assert (count, registrar.registered) == (0, [])

    def test_an_ethernet_only_machine_registers_nothing_and_asks_for_no_guids(self) -> None:
        registrar = _FakeRegistrar()

        def explode() -> dict[int, str]:
            raise AssertionError("no Wi-Fi adapter, so the GUID probe must not run")

        probes = cast(
            HardwareProbes,
            SimpleNamespace(
                active_adapters=lambda: [(7, "Ethernet", "802.3")], adapter_guids=explode
            ),
        )
        assert discover_wifi_link_quality(registrar, probes) == 0

    def test_the_pass_runs_right_after_the_adapter_pass(self) -> None:
        names = [d.__name__ for d in all_discoverers()]
        assert (
            names.index("discover_wifi_link_quality")
            == names.index("discover_network_adapter_settings") + 1
        )


@pytest.mark.skipif(not hasattr(wlan, "interfaces"), reason="wlanapi port missing")
class TestAgainstThisMachine:
    def test_the_live_answer_is_a_choice_or_the_sentinel(self) -> None:
        """Whatever this machine's radio is doing, the detector says one of the
        words the setting owns, or steps aside."""
        for interface in wlan.interfaces():
            answer = wifi_link_quality({"interface_guid": interface.guid})
            assert answer in ("good", "weak_signal", "on_2_4ghz", NOT_AVAILABLE), answer
