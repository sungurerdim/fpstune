"""The shipped adapter-property commands, against adapters that answer in other languages.

A driver publishes each advanced property under its ``RegistryKeyword`` (the INF's
own name) and shows a *translated* ``DisplayName`` beside it. U-APSD and
Throughput Booster used to be found by keyword **or** by that label, so the same
adapter was found on an English Windows and silently missed on a Turkish or German
one. They now go through the keyword resolver, which has no way to read a label.

As everywhere in this directory the shipped command runs verbatim; only the cmdlets
it calls are shadowed by functions that answer from the fake host's JSON.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
from tests.test_windows_contract.conftest import run_shipped_command, run_shipped_script

from fpstune.settings.definitions.network import (
    create_eee_setting,
    create_flow_control_setting,
    create_roaming_aggressiveness_setting,
    create_throughput_booster_setting,
    create_uapsd_setting,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw -Encoding UTF8 | ConvertFrom-Json

function Get-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([int]$InterfaceIndex, [string[]]$RegistryKeyword, [switch]$AllProperties)
    foreach ($p in $FpsFake.props) {
        [pscustomobject]@{
            RegistryKeyword = $p.keyword
            DisplayName = $p.label
            RegistryValue = @([string]$p.value)
            ValidRegistryValues = $p.valid
            NumericParameterMinValue = $p.min
            NumericParameterMaxValue = $p.max
        }
    }
}

function Set-NetAdapterAdvancedProperty {
    [CmdletBinding()] param([int]$InterfaceIndex, [string]$RegistryKeyword, $RegistryValue, [switch]$NoRestart)
    Write-Output "WROTE=$RegistryKeyword=$RegistryValue"
}
"""

# The Throughput Booster detect command as it shipped before the resolver, kept
# verbatim so the fix can be shown to change the answer: it matched the translated
# label as well.
_PREVIOUS_BOOSTER_DETECT = (
    "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex 5 "
    "-ErrorAction SilentlyContinue | Where-Object { "
    "$_.RegistryKeyword -match 'ThroughputBoost' -or $_.DisplayName -match 'Throughput.?Booster' "
    "} | Select-Object -First 1; "
    "if ($p) { if ([int](@($p.RegistryValue)[0]) -eq 0) { 'Disabled' } else { 'Enabled' } } "
    "else { 'not_supported' }"
)


def prop(
    keyword: str,
    label: str,
    value: str,
    valid: list[str] | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "label": label,
        "value": value,
        "valid": valid,
        "min": minimum,
        "max": maximum,
    }


def detect(setting: Any, *props: dict[str, Any]) -> str:
    command = setting.detect_command.replace("%ifindex%", "5")
    return run_shipped_command(_PRELUDE + command, {"props": list(props)})


def apply(setting: Any, choice: str, *props: dict[str, Any]) -> list[str]:
    command = setting.apply_command.replace("%ifindex%", "5").replace(
        "%value%", str(setting.apply_value_map[choice])
    )
    output = run_shipped_script(_PRELUDE + command, {"props": list(props)})
    return [line.strip() for line in output.splitlines() if line.strip()]


# What the control panel shows for the same Intel keyword on each Windows language.
TURKISH_UAPSD = "U-APSD deste\u011fi"
GERMAN_UAPSD = "U-APSD-Unterst\u00fctzung"
TURKISH_BOOSTER = "Verimlilik art\u0131r\u0131c\u0131"
GERMAN_BOOSTER = "Durchsatz-Booster"


class TestAnAdapterAnsweringInAnotherLanguage:
    @pytest.mark.parametrize("label", [TURKISH_UAPSD, GERMAN_UAPSD, "U-APSD support"])
    def test_uapsd_is_found_by_keyword_whatever_language_labels_it(self, label: str) -> None:
        setting = create_uapsd_setting(5, "Wi-Fi")
        on = prop("uAPSDSupport", label, "1", ["0", "1"])
        off = prop("uAPSDSupport", label, "0", ["0", "1"])
        assert detect(setting, on) == "Enabled"
        assert detect(setting, off) == "Disabled"

    @pytest.mark.parametrize("label", [TURKISH_UAPSD, GERMAN_UAPSD, "U-APSD support"])
    def test_uapsd_is_written_under_the_drivers_own_keyword(self, label: str) -> None:
        setting = create_uapsd_setting(5, "Wi-Fi")
        lines = apply(setting, "Disabled", prop("uAPSDSupport", label, "1", ["0", "1"]))
        assert lines == ["WROTE=uAPSDSupport=0", "ok"]

    @pytest.mark.parametrize("label", [TURKISH_BOOSTER, GERMAN_BOOSTER, "Throughput Booster"])
    def test_throughput_booster_is_found_and_written_by_keyword(self, label: str) -> None:
        setting = create_throughput_booster_setting(5, "Wi-Fi")
        current = prop("ThroughputBoosterEnabled", label, "1", ["0", "1"])
        assert detect(setting, current) == "Enabled"
        assert apply(setting, "Disabled", current) == ["WROTE=ThroughputBoosterEnabled=0", "ok"]


class TestALabelNeverClaimsAProperty:
    """The defect: one adapter, a different answer on each Windows language."""

    ENGLISH = prop("VendorBurstMode", "Throughput Booster", "1", ["0", "1"])
    GERMAN = prop("VendorBurstMode", GERMAN_BOOSTER, "1", ["0", "1"])
    TURKISH = prop("VendorBurstMode", TURKISH_BOOSTER, "1", ["0", "1"])

    def test_the_previous_command_answered_by_the_label(self) -> None:
        """Same keyword, same value: found on an English label, missed on a translated one."""
        previous = _PRELUDE + _PREVIOUS_BOOSTER_DETECT
        assert run_shipped_command(previous, {"props": [self.ENGLISH]}) == "Enabled"
        assert run_shipped_command(previous, {"props": [self.GERMAN]}) == "not_supported"
        assert run_shipped_command(previous, {"props": [self.TURKISH]}) == "not_supported"

    @pytest.mark.parametrize(
        "adapter", [ENGLISH, GERMAN, TURKISH], ids=["english", "german", "turkish"]
    )
    def test_the_shipped_command_answers_the_same_in_every_language(
        self, adapter: dict[str, Any]
    ) -> None:
        setting = create_throughput_booster_setting(5, "Wi-Fi")
        assert detect(setting, adapter) == "not_supported"
        assert apply(setting, "Disabled", adapter) == ["not_supported"]

    def test_the_same_holds_for_uapsd(self) -> None:
        english = prop("VendorPowerSavePoll", "WMM U-APSD Support", "1", ["0", "1"])
        setting = create_uapsd_setting(5, "Wi-Fi")
        assert detect(setting, english) == "not_supported"
        assert apply(setting, "Disabled", english) == ["not_supported"]


class TestOldAndNewKeywordSpellings:
    @pytest.mark.parametrize("keyword", ["*EEE", "EEE", "EEEControl", "EnergyEfficientEthernet"])
    def test_eee_is_read_and_written_under_whichever_spelling_the_driver_has(
        self, keyword: str
    ) -> None:
        setting = create_eee_setting(5, "Ethernet")
        current = prop(keyword, "Energy-Efficient Ethernet", "1", ["0", "1"])
        assert detect(setting, current) == "1"
        assert apply(setting, "Disabled", current) == [f"WROTE={keyword}=0", "ok"]

    def test_the_standardised_spelling_is_preferred_when_both_exist(self) -> None:
        setting = create_eee_setting(5, "Ethernet")
        both = [
            prop("EEE", "Energy-Efficient Ethernet", "1", ["0", "1"]),
            prop("*EEE", "Energy-Efficient Ethernet", "1", ["0", "1"]),
        ]
        assert apply(setting, "Disabled", *both) == ["WROTE=*EEE=0", "ok"]


class TestAbsentKeywordIsTheSentinel:
    def test_an_adapter_without_the_property_reports_not_supported(self) -> None:
        unrelated = prop("*FlowControl", "Flow Control", "3", ["0", "1", "2", "3"])
        for setting in (create_uapsd_setting(5, "Wi-Fi"), create_eee_setting(5, "Ethernet")):
            assert detect(setting, unrelated) == "not_supported"
            assert apply(setting, "Disabled", unrelated) == ["not_supported"]

    def test_an_adapter_publishing_nothing_reports_not_supported(self) -> None:
        assert detect(create_roaming_aggressiveness_setting(5, "Wi-Fi")) == "not_supported"


class TestAValueTheDriverDoesNotListIsRefused:
    def test_an_enum_that_skips_the_value_names_its_own_list(self) -> None:
        setting = create_flow_control_setting(5, "Ethernet")
        driver = prop("*FlowControl", "Flow Control", "3", ["0", "3"])
        lines = apply(setting, "Rx Enabled", driver)
        assert len(lines) == 1
        assert lines[0].startswith("error:")
        assert "flow-control value 2" in lines[0]
        assert "its own list is 0,3" in lines[0]

    def test_a_listed_value_is_written(self) -> None:
        setting = create_flow_control_setting(5, "Ethernet")
        driver = prop("*FlowControl", "Flow Control", "3", ["0", "3"])
        assert apply(setting, "Disabled", driver) == ["WROTE=*FlowControl=0", "ok"]

    def test_a_numeric_range_refuses_what_is_past_its_maximum(self) -> None:
        setting = create_roaming_aggressiveness_setting(5, "Wi-Fi")
        driver = prop("RoamAggressiveness", "Roaming Aggressiveness", "2", None, 0, 2)
        lines = apply(setting, "Highest", driver)
        assert len(lines) == 1
        assert lines[0].startswith("error:")
        assert "its own range is 0..2" in lines[0]
        assert apply(setting, "Lowest", driver) == ["WROTE=RoamAggressiveness=0", "ok"]

    def test_a_driver_publishing_no_list_is_not_refused(self) -> None:
        """``@($null)`` has one element: an unpublished list must not read as a list."""
        setting = create_uapsd_setting(5, "Wi-Fi")
        driver = prop("uAPSDSupport", "U-APSD", "1", None, None, None)
        assert apply(setting, "Disabled", driver) == ["WROTE=uAPSDSupport=0", "ok"]

    def test_a_zero_to_zero_range_is_not_a_range(self) -> None:
        """Non-numeric properties report NumericParameterMaxValue 0; that bounds nothing."""
        setting = create_uapsd_setting(5, "Wi-Fi")
        driver = prop("uAPSDSupport", "U-APSD", "1", None, 0, 0)
        assert apply(setting, "Enabled", driver) == ["WROTE=uAPSDSupport=1", "ok"]
