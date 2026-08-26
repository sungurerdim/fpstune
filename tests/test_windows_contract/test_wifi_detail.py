"""WiFi facts come from wlanapi's numbers, never from netsh's words.

The defect this file exists for: the WiFi enrichment regexed
``netsh wlan show interfaces`` for the English labels 'SSID', 'Channel',
'Radio type', 'Signal' — and netsh answers in the system language. On the
Turkish dev machine (labels: Kanal, Sinyal, Radyo türü) every field silently
became empty, on every non-English Windows in the world. The band was then
guessed from the channel number, which cannot place Wi-Fi 6E: 6 GHz channels
reuse 2.4 GHz numbering, so a 6 GHz channel-1 network read as 2.4 GHz — the
old comment admitted it.

The shipped path reads wlanapi.dll's numeric enums and the BSS entry's own
center frequency; ``Convert-WlanRecords`` is the pure mapping these tests run
against described records.
"""

from __future__ import annotations

import json
import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.api.hardware.network_adapters import _WIFI_DETAIL_SCRIPT, _WIFI_MAP_PS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

GUID = "aaaabbbb-cccc-dddd-eeee-ffff00001111"

_DRIVER = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
$adapters = @()
foreach ($a in $FpsFake.adapters) {
    $adapters += [pscustomobject]@{ Name = $a.name; InterfaceGuid = $a.guid }
}
"""

_EMIT = r"""
$out = @(Convert-WlanRecords -records ([string[]]$FpsFake.records) -wifiAdapters $adapters)
ConvertTo-Json -InputObject $out -Depth 2 -Compress
"""

# The band rule as it shipped, kept verbatim so the fix can be shown to change
# the answer: a channel number was the only input, and 6 GHz reuses 2.4 GHz
# channel numbering.
_PREVIOUS_BAND_RULE = r"""
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
$channel = [int]$FpsFake.channel
if ($channel -ge 1 -and $channel -le 14) { $freq = 2.4 }
elseif ($channel -ge 36) { $freq = 5.0 }
else { $freq = 0 }
Write-Output $freq
"""


def _convert(records: list[str], adapters: list[dict[str, str]]) -> list[dict]:
    out = run_shipped_command(
        _DRIVER + _WIFI_MAP_PS + _EMIT, {"records": records, "adapters": adapters}
    )
    parsed = json.loads(out)
    return parsed if isinstance(parsed, list) else [parsed]


WIFI = [{"name": "Wi-Fi", "guid": "{" + GUID.upper() + "}"}]


def _record(
    *,
    guid: str = GUID,
    channel: int = 1,
    freq_khz: int = 5955000,
    phy: int = 10,
    signal: int = 84,
    auth: int = 9,
    ssid: str = "HomeNet",
) -> str:
    return f"{guid}|{channel}|{freq_khz}|{phy}|{signal}|{auth}|{ssid}"


class TestTheBandIsTheFrequencysAnswer:
    def test_a_6ghz_channel_1_network_is_6ghz(self) -> None:
        """The gate: channel 1 at 5955 MHz is Wi-Fi 6E, not 2.4 GHz."""
        rows = _convert([_record(channel=1, freq_khz=5955000)], WIFI)
        assert rows[0]["FrequencyGHz"] == 6.0

    def test_the_previous_rule_called_the_same_network_24ghz(self) -> None:
        # On a non-English host PowerShell even *renders* the wrong answer in
        # the system locale ("2,4" here) — one more way the old path depended
        # on words where the new one hands numbers to a culture-invariant
        # JSON serializer.
        answer = run_shipped_command(_PREVIOUS_BAND_RULE, {"channel": 1})
        assert answer.replace(",", ".") == "2.4"

    @pytest.mark.parametrize(("freq_khz", "band"), [(2412000, 2.4), (5180000, 5.0), (5955000, 6.0)])
    def test_each_band_from_its_own_frequency(self, freq_khz: int, band: float) -> None:
        rows = _convert([_record(freq_khz=freq_khz)], WIFI)
        assert rows[0]["FrequencyGHz"] == band

    def test_an_unknown_frequency_stays_unknown(self) -> None:
        """No BSS entry answered — the channel number may not guess for it."""
        rows = _convert([_record(channel=36, freq_khz=0)], WIFI)
        assert rows[0]["FrequencyGHz"] == 0


class TestTheEnumsAreTheApisOwn:
    def test_phy_and_auth_map_from_numbers_not_words(self) -> None:
        rows = _convert([_record(phy=10, auth=9)], WIFI)
        assert rows[0]["RadioType"] == "802.11ax"
        assert rows[0]["AuthType"] == "WPA3-Personal"
        assert rows[0]["SignalPercent"] == 84

    def test_an_unknown_enum_stays_empty_rather_than_wrong(self) -> None:
        rows = _convert([_record(phy=99, auth=99)], WIFI)
        assert rows[0]["RadioType"] == ""
        assert rows[0]["AuthType"] == ""

    def test_an_ssid_carrying_the_separator_survives(self) -> None:
        rows = _convert([_record(ssid="cafe|guest")], WIFI)
        assert rows[0]["SSID"] == "cafe|guest"


class TestAdapterMatching:
    def test_the_guid_matches_across_braces_and_case(self) -> None:
        rows = _convert([_record(guid=GUID.lower())], WIFI)
        assert rows and rows[0]["AdapterName"] == "Wi-Fi"

    def test_a_record_for_another_interface_produces_no_row(self) -> None:
        stranger = _record(guid="99999999-9999-9999-9999-999999999999")
        assert _convert([stranger], WIFI) == []


class TestNoWordsAreParsedAtAll:
    def test_the_shipped_script_never_reads_netsh_text(self) -> None:
        """The Turkish-host failure cannot return if no label is ever matched."""
        assert "netsh" not in _WIFI_DETAIL_SCRIPT
        assert "Radio type" not in _WIFI_DETAIL_SCRIPT
        assert "'SSID\\s" not in _WIFI_DETAIL_SCRIPT
