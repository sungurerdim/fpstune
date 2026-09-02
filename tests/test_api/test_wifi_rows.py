"""WiFi facts come from wlanapi's numbers, never from netsh's words.

The defect this file exists for: the WiFi enrichment regexed
``netsh wlan show interfaces`` for the English labels 'SSID', 'Channel',
'Radio type', 'Signal' — and netsh answers in the system language. On the
Turkish dev machine (labels: Kanal, Sinyal, Radyo türü) every field silently
became empty, on every non-English Windows in the world. The band was then
guessed from the channel number, which cannot place Wi-Fi 6E: 6 GHz channels
reuse 2.4 GHz numbering, so a 6 GHz channel-1 network read as 2.4 GHz.

The mapping from the API's records to the report used to be a PowerShell
function run by a contract test; it is now ``wifi_rows`` in Python and these are
the same cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fpstune.api.hardware.network_adapters as network_adapters
from fpstune.api.hardware.network_adapters import wifi_rows
from fpstune.utils.winapi.wlan import WlanRecord, band_ghz

GUID = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
WIFI = [{"Name": "Wi-Fi", "InterfaceGuid": "{" + GUID.upper() + "}", "MediaType": "Native 802.11"}]


def _record(
    *,
    guid: str = GUID,
    channel: int = 1,
    freq_khz: int = 5955000,
    phy: int = 10,
    signal: int = 84,
    auth: int = 9,
    ssid: str = "HomeNet",
) -> WlanRecord:
    return WlanRecord(
        interface_guid=guid,
        channel=channel,
        center_khz=freq_khz,
        phy_type=phy,
        signal_percent=signal,
        auth_algorithm=auth,
        ssid=ssid,
        profile_name=ssid,
        bssid="00:11:22:33:44:55",
    )


def _previous_band_rule(channel: int) -> float:
    """The rule as it shipped: a channel number was the only input."""
    if 1 <= channel <= 14:
        return 2.4
    if channel >= 36:
        return 5.0
    return 0.0


class TestTheBandIsTheFrequencysAnswer:
    def test_a_6ghz_channel_1_network_is_6ghz(self) -> None:
        """The gate: channel 1 at 5955 MHz is Wi-Fi 6E, not 2.4 GHz."""
        rows = wifi_rows([_record(channel=1, freq_khz=5955000)], WIFI)
        assert rows[0]["FrequencyGHz"] == 6.0

    def test_the_previous_rule_called_the_same_network_24ghz(self) -> None:
        assert _previous_band_rule(1) == 2.4

    @pytest.mark.parametrize(("freq_khz", "band"), [(2412000, 2.4), (5180000, 5.0), (5955000, 6.0)])
    def test_each_band_from_its_own_frequency(self, freq_khz: int, band: float) -> None:
        assert band_ghz(freq_khz) == band
        assert wifi_rows([_record(freq_khz=freq_khz)], WIFI)[0]["FrequencyGHz"] == band

    def test_an_unknown_frequency_stays_unknown(self) -> None:
        """No BSS entry answered — the channel number may not guess for it."""
        rows = wifi_rows([_record(channel=36, freq_khz=0)], WIFI)
        assert rows[0]["FrequencyGHz"] == 0


class TestTheEnumsAreTheApisOwn:
    def test_phy_and_auth_map_from_numbers_not_words(self) -> None:
        rows = wifi_rows([_record(phy=10, auth=9)], WIFI)
        assert rows[0]["RadioType"] == "802.11ax"
        assert rows[0]["AuthType"] == "WPA3-Personal"
        assert rows[0]["SignalPercent"] == 84

    def test_an_unknown_enum_stays_empty_rather_than_wrong(self) -> None:
        rows = wifi_rows([_record(phy=99, auth=99)], WIFI)
        assert rows[0]["RadioType"] == ""
        assert rows[0]["AuthType"] == ""

    def test_an_ssid_carrying_the_separator_survives(self) -> None:
        rows = wifi_rows([_record(ssid="cafe|guest")], WIFI)
        assert rows[0]["SSID"] == "cafe|guest"


class TestAdapterMatching:
    def test_the_guid_matches_across_braces_and_case(self) -> None:
        rows = wifi_rows([_record(guid=GUID.lower())], WIFI)
        assert rows and rows[0]["AdapterName"] == "Wi-Fi"

    def test_a_record_for_another_interface_produces_no_row(self) -> None:
        stranger = _record(guid="99999999-9999-9999-9999-999999999999")
        assert wifi_rows([stranger], WIFI) == []

    def test_an_adapter_without_a_guid_produces_no_row(self) -> None:
        """A disabled adapter the inventory found through PnP carries no GUID."""
        assert wifi_rows([_record()], [{"Name": "Ghost", "MediaType": "Native 802.11"}]) == []


class TestNoWordsAreParsedAtAll:
    def test_the_module_never_reads_netsh_text_or_compiles_code(self) -> None:
        """The Turkish-host failure cannot return if no label is ever matched, and
        the Defender-flagged Add-Type class is gone for good."""
        source = Path(network_adapters.__file__).read_text(encoding="utf-8")
        assert "netsh wlan show" not in source
        assert "Radio type" not in source
        for compile_form in ("Add-Type @'", "Add-Type -TypeDefinition", "DllImport"):
            assert compile_form not in source, compile_form
