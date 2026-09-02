"""The Wi-Fi security advisory: which standard, which cipher, and who can do better.

Two findings on two axes. A TKIP or WEP cipher is a performance finding —
802.11n and later refuse HT rates on such a link, so the radio runs at 802.11g
speed. WPA2-Personal on a link where *both* the adapter and the access point
can do WPA3 is a security finding at the same speed. Both ends are read from
wlanapi (the adapter's own auth/cipher pairs; the BSS entry's RSN element),
never assumed, and a WPA2-only router is not the user's to fix here.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, NOT_AVAILABLE
from fpstune.settings.base import Reading
from fpstune.settings.definitions.network import create_wifi_security_setting
from fpstune.settings.executors import python_actions
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.python_actions import (
    classify_wifi_security,
    wifi_security,
    wifi_security_reading,
)
from fpstune.utils.winapi import wlan
from fpstune.utils.winapi.wlan import WlanRecord, rsn_offers_sae

GUID = "ffffffff-0000-4000-8000-000000000001"

WPA_PSK, WPA2_PSK, WPA3_SAE, WPA2_ENT = 4, 7, 9, 6
TKIP, CCMP, WEP104 = 0x02, 0x04, 0x05


def _record(
    *,
    auth: int = WPA2_PSK,
    cipher: int = CCMP,
    adapter_sae: bool = True,
    ap_sae: bool = False,
    guid: str = GUID,
) -> WlanRecord:
    return WlanRecord(
        interface_guid=guid,
        channel=36,
        center_khz=5_180_000,
        phy_type=10,
        signal_percent=80,
        auth_algorithm=auth,
        ssid="home",
        profile_name="home",
        bssid="aa:bb:cc:dd:ee:ff",
        cipher_algorithm=cipher,
        ap_offers_sae=ap_sae,
        adapter_supports_sae=adapter_sae,
    )


class TestTheClassifier:
    def test_a_legacy_cipher_is_the_performance_finding(self) -> None:
        assert classify_wifi_security(WPA2_PSK, TKIP, True, True) == "legacy_cipher"
        assert classify_wifi_security(WPA_PSK, TKIP, False, False) == "legacy_cipher"
        assert classify_wifi_security(2, WEP104, False, False) == "legacy_cipher"

    def test_the_cipher_outranks_the_standard(self) -> None:
        """A TKIP link where WPA3 is on offer: the speed loss is the nearer problem."""
        assert classify_wifi_security(WPA2_PSK, TKIP, True, True) == "legacy_cipher"

    def test_wpa2_is_a_finding_only_when_both_ends_can_do_wpa3(self) -> None:
        assert classify_wifi_security(WPA2_PSK, CCMP, True, True) == "wpa3_available"
        assert classify_wifi_security(WPA_PSK, CCMP, True, True) == "wpa3_available"
        # The router does not offer it: nothing here for the user to change.
        assert classify_wifi_security(WPA2_PSK, CCMP, True, False) == "good"
        # The adapter cannot do it: no profile change would help.
        assert classify_wifi_security(WPA2_PSK, CCMP, False, True) == "good"

    def test_wpa3_and_enterprise_links_are_left_alone(self) -> None:
        assert classify_wifi_security(WPA3_SAE, CCMP, True, True) == "good"
        assert classify_wifi_security(WPA2_ENT, CCMP, True, True) == "good"


class TestTheReading:
    def test_the_names_travel_with_the_word(self) -> None:
        reading = wifi_security_reading(_record(auth=WPA2_PSK, cipher=CCMP, ap_sae=True))
        assert reading.value == "wpa3_available"
        assert reading.finding == {
            "kind": "wifi_security",
            "auth": "WPA2-Personal",
            "cipher": "AES-CCMP",
            "adapter_wpa3": True,
            "ap_wpa3": True,
        }

    def test_an_unknown_enum_is_an_empty_name_not_a_guess(self) -> None:
        reading = wifi_security_reading(_record(auth=99, cipher=77))
        assert reading.finding is not None
        assert (reading.finding["auth"], reading.finding["cipher"]) == ("", "")


class TestTheRsnElement:
    """Bytes as a beacon carries them: RSN version 1, group CCMP, pairwise CCMP, then AKMs."""

    _HEAD = bytes.fromhex("0100000fac040100000fac04")

    def _rsn(self, akms: bytes) -> bytes:
        count = len(akms) // 4
        body = self._HEAD + count.to_bytes(2, "little") + akms
        return bytes([48, len(body)]) + body

    def test_sae_in_the_akm_list_is_wpa3(self) -> None:
        assert rsn_offers_sae(self._rsn(bytes.fromhex("000fac08")))

    def test_transition_mode_lists_psk_and_sae(self) -> None:
        assert rsn_offers_sae(self._rsn(bytes.fromhex("000fac02000fac08")))

    def test_sae_ext_key_counts_as_wpa3(self) -> None:
        assert rsn_offers_sae(self._rsn(bytes.fromhex("000fac18")))

    def test_psk_only_is_not_wpa3(self) -> None:
        assert not rsn_offers_sae(self._rsn(bytes.fromhex("000fac02")))

    def test_the_element_is_found_after_other_elements(self) -> None:
        ssid_element = bytes([0, 4]) + b"home"
        assert rsn_offers_sae(ssid_element + self._rsn(bytes.fromhex("000fac08")))

    def test_a_truncated_element_answers_no_rather_than_reading_past_it(self) -> None:
        assert not rsn_offers_sae(bytes([48, 6]) + self._HEAD[:6])
        assert not rsn_offers_sae(b"")
        assert not rsn_offers_sae(bytes([48]))


class TestTheDetector:
    def test_it_answers_for_the_radio_it_was_asked_about(self, monkeypatch) -> None:
        other = _record(guid="ffffffff-0000-4000-8000-000000000002", cipher=TKIP)
        monkeypatch.setattr(wlan, "query_connected", lambda: [other, _record(ap_sae=True)])
        answer = wifi_security({"interface_guid": GUID})
        assert isinstance(answer, Reading)
        assert answer.value == "wpa3_available"

    def test_a_disconnected_radio_is_the_absent_sentinel(self, monkeypatch) -> None:
        monkeypatch.setattr(wlan, "query_connected", lambda: [])
        answer = wifi_security({"interface_guid": GUID})
        assert answer == NOT_AVAILABLE
        assert answer in ABSENT_READINGS


class TestThroughTheExecutor:
    def test_detect_reads_python_not_powershell(self, monkeypatch) -> None:
        setting = create_wifi_security_setting(12, GUID, "Intel Wi-Fi 6 AX201")

        def no_powershell(*_a: object, **_k: object) -> tuple[bool, str]:
            raise AssertionError("a Python detector must never spawn PowerShell")

        monkeypatch.setattr("fpstune.settings.executors.powershell.run_powershell", no_powershell)
        monkeypatch.setattr(wlan, "query_connected", lambda: [_record(cipher=TKIP)])

        reading, error = PowerShellExecutor().detect(setting)

        assert error is None
        assert isinstance(reading, Reading)
        assert reading.value == "legacy_cipher"
        assert reading.value in setting.choices
        assert reading.finding is not None
        assert reading.finding["cipher"] == "TKIP"

    def test_the_detector_table_names_the_settings_key(self) -> None:
        setting = create_wifi_security_setting(12, GUID, "x")
        assert setting.detect_command in python_actions.PYTHON_DETECTORS


class TestTheAdvisoryItself:
    def test_it_is_read_only_and_keyed_like_its_adapter_siblings(self) -> None:
        setting = create_wifi_security_setting(12, GUID, "Intel Wi-Fi 6 AX201")
        assert setting.is_readonly
        assert setting.id == "network:12:wifi_security"
        assert setting.recommended_value == setting.default_value == "good"
        assert setting.detect_args == {"interface_guid": GUID}
        assert setting.description.endswith(".")
        assert not setting.effect.endswith(".")
        assert any(key != "stability" for key in setting.impact_scores)

    def test_the_copy_claims_no_speed_for_wpa3(self) -> None:
        """WPA2-AES and WPA3 run the same cipher; only the legacy cipher costs rate."""
        setting = create_wifi_security_setting(12, GUID, "x")
        bandwidth = str(setting.impact_scores["bandwidth"])
        assert "802.11g" in bandwidth
        assert "WPA3" not in bandwidth


@pytest.mark.skipif(not hasattr(wlan, "interfaces"), reason="wlanapi port missing")
class TestAgainstThisMachine:
    def test_the_live_answer_is_a_choice_or_the_sentinel(self) -> None:
        setting = create_wifi_security_setting(12, GUID, "x")
        for record in wlan.query_connected():
            answer: Any = wifi_security({"interface_guid": record.interface_guid})
            assert isinstance(answer, Reading)
            assert answer.value in setting.choices
            assert answer.finding is not None
            assert isinstance(answer.finding["adapter_wpa3"], bool)
