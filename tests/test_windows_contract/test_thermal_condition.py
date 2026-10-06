"""The thermal advisory answers where it can, and says nothing where it cannot.

Reported on 2026-09-02: the advisory showed a warning with no current value
behind it. Two separate defects met there. The reading itself came only from
`MSAcpi_ThermalZoneTemperature`, which is absent on a great many machines
(measured absent on the reporting laptop), so the advisory had nothing to say;
and an unread advisory was being rendered as a finding anyway, which the Home
change fixes on the other side.

This is the reading half. The performance counter reads the same ACPI zones
through a different provider and answers where the WMI class does not, and the
verdict comes from what the firmware states — ThrottleReasons and
PercentPassiveLimit — rather than from a temperature threshold, because the
same zone idles at 81 °C on hardware that is not throttling at all.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.settings.definitions.system import SYSTEM_THERMAL_CONDITION
from fpstune.settings.executors.powershell import _split_detect_output

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="runs real powershell.exe")

SCRIPT = SYSTEM_THERMAL_CONDITION.detect_command

# Both CIM classes the script asks for, shadowed by a function of the same name
# so the shipped command runs unmodified against a described machine.
_HARNESS = r"""
$ErrorActionPreference = 'Stop'
$fake = Get-Content -LiteralPath $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-CimInstance {
    param([Parameter(ValueFromRemainingArguments = $true)] $Ignored)
    $wanted = ''
    for ($i = 0; $i -lt $Ignored.Count; $i++) {
        if ("$($Ignored[$i])" -eq '-ClassName') { $wanted = "$($Ignored[$i + 1])" }
    }
    # How a source fails: 'unreadable' is any refusal (access denied, a broken provider);
    # 'class_absent' is the real cmdlet answering a class that does not exist, so the
    # exception is the genuine InvalidClass one and not a stand-in.
    # A failing cmdlet honours the caller's -ErrorAction, as the real one does: silenced
    # it answers nothing, which is how a failed read became "absent".
    # (A function with a [Parameter] attribute is advanced: the common -ErrorAction/-EA
    # binds to it and lands in $ErrorActionPreference.)
    $ea = "$ErrorActionPreference"
    $failure = $null
    if ($wanted -eq 'MSAcpi_ThermalZoneTemperature') { $failure = $fake.acpi_failure }
    if ($wanted -eq 'Win32_PerfFormattedData_Counters_ThermalZoneInformation') { $failure = $fake.perf_failure }
    if ($failure -eq 'unreadable') {
        if ($ea -in 'SilentlyContinue', 'Ignore') { return $null }
        throw 'simulated read failure'
    }
    if ($failure -eq 'class_absent') {
        return CimCmdlets\Get-CimInstance -ClassName Win32_NoSuchClass_Fpstune -ErrorAction $ea
    }
    if ($wanted -eq 'MSAcpi_ThermalZoneTemperature') {
        if ($null -eq $fake.acpi) { return $null }
        return [pscustomobject]@{
            CurrentTemperature = $fake.acpi.CurrentTemperature
            InstanceName       = $fake.acpi.InstanceName
        }
    }
    if ($wanted -eq 'Win32_PerfFormattedData_Counters_ThermalZoneInformation') {
        if ($null -eq $fake.perf) { return $null }
        return [pscustomobject]@{
            Name                     = $fake.perf.Name
            HighPrecisionTemperature = $fake.perf.HighPrecisionTemperature
            ThrottleReasons          = $fake.perf.ThrottleReasons
            PercentPassiveLimit      = $fake.perf.PercentPassiveLimit
        }
    }
    return $null
}

"""


def _detect(
    *, acpi: dict[str, Any] | None = None, perf: dict[str, Any] | None = None
) -> tuple[str | None, dict[str, Any] | None]:
    """Run the shipped command and split it the way the executor does."""
    output = run_shipped_script(_HARNESS + SCRIPT, {"acpi": acpi, "perf": perf})
    lines, finding = _split_detect_output(SYSTEM_THERMAL_CONDITION.id, output)
    return (lines[-1] if lines else None), finding


def _detect_raises(*, acpi_failure: str | None = None, perf_failure: str | None = None) -> str:
    """Run the shipped command against failing sources; return what it threw.

    The shipped command ends with an uncaught throw when it cannot read, which the
    executor reads as a failed detect. The harness catches it only to hand the
    message back; ``THREW:`` never appears when the command answered.
    """
    script = _HARNESS + "try { " + SCRIPT + " } catch { 'THREW: ' + $_.Exception.Message }"
    output = run_shipped_script(
        script,
        {"acpi": None, "perf": None, "acpi_failure": acpi_failure, "perf_failure": perf_failure},
    )
    return output.strip().splitlines()[-1]


# The development laptop's own numbers, read on 2026-09-02: no ACPI WMI class,
# two performance-counter zones, neither throttling.
THIS_MACHINE_PERF = {
    "Name": r"\_SB.ECTZ",
    "HighPrecisionTemperature": 3542,
    "ThrottleReasons": 0,
    "PercentPassiveLimit": 100,
}


class TestTheFallbackThatMakesItWork:
    def test_it_reads_the_counter_when_the_wmi_class_is_absent(self) -> None:
        """The whole point: this machine used to report nothing at all."""
        value, finding = _detect(acpi=None, perf=THIS_MACHINE_PERF)

        assert value == "not_throttling"
        assert finding == {
            "kind": "thermal",
            "celsius": 81,
            "throttling": False,
            "zone": r"\_SB.ECTZ",
        }

    def test_the_wmi_class_wins_when_both_answer(self) -> None:
        """A real ACPI zone temperature is the better of the two readings."""
        value, finding = _detect(
            acpi={"CurrentTemperature": 3231, "InstanceName": "ACPI\\ThermalZone\\TZ00"},
            perf=THIS_MACHINE_PERF,
        )
        assert value == "not_throttling"
        assert finding is not None
        assert finding["celsius"] == 50  # 323.1 K
        # The label must name the sensor the number came from. It used to prefer
        # the counter's name whenever the counter existed, so an elevated run
        # reading the ACPI class reported a zone belonging to a different source.
        assert finding["zone"] == r"ACPI\ThermalZone\TZ00"

    def test_the_zone_names_the_counter_when_the_counter_is_the_source(self) -> None:
        _, finding = _detect(acpi=None, perf=THIS_MACHINE_PERF)
        assert finding is not None
        assert finding["zone"] == THIS_MACHINE_PERF["Name"]


class TestTheVerdictIsAFactNotAThreshold:
    def test_a_hot_zone_that_is_not_throttling_is_not_a_finding(self) -> None:
        """81 °C on the reporting machine was not throttling, and must not warn."""
        value, _ = _detect(perf=THIS_MACHINE_PERF)
        assert value == "not_throttling"

    def test_throttle_reasons_makes_it_a_finding(self) -> None:
        value, finding = _detect(
            perf={**THIS_MACHINE_PERF, "ThrottleReasons": 1},
        )
        assert value == "throttling"
        assert finding is not None
        assert finding["throttling"] is True

    def test_a_passive_limit_below_full_makes_it_a_finding(self) -> None:
        """The firmware capping performance passively is throttling by another name."""
        value, _ = _detect(perf={**THIS_MACHINE_PERF, "PercentPassiveLimit": 70})
        assert value == "throttling"

    def test_a_cool_machine_is_not_a_finding(self) -> None:
        value, finding = _detect(perf={**THIS_MACHINE_PERF, "HighPrecisionTemperature": 3131})
        assert value == "not_throttling"
        assert finding is not None
        assert finding["celsius"] == 40


class TestWhenNothingAnswers:
    def test_neither_source_present_is_the_absent_sentinel(self) -> None:
        """No reading is 'we could not check', never 'you are fine' and never a warning."""
        from fpstune.settings.applicability import ABSENT_READINGS

        value, finding = _detect(acpi=None, perf=None)
        assert value in ABSENT_READINGS
        assert finding is None

    def test_both_classes_missing_is_proven_absence(self) -> None:
        """The cmdlet itself says InvalidClass for both: that is "not on this machine"."""
        from fpstune.settings.applicability import ABSENT_READINGS

        answer = _detect_raises(acpi_failure="class_absent", perf_failure="class_absent")
        assert answer in ABSENT_READINGS


class TestWhenReadsFailTheRowSaysSo:
    """A read that failed proves nothing about the machine (issue #104 follow-up).

    Both CIM reads used to run ``-EA SilentlyContinue``: an access-denied ACPI read
    plus a broken counter provider left both empty, and the empty pair read as
    ``not_available`` — "this machine has no thermal zone" — instead of "could not
    read". Absence is proven only by a read that ran and found nothing, or by the
    provider answering that the class does not exist.
    """

    def test_both_sources_failing_throws_instead_of_reading_absent(self) -> None:
        answer = _detect_raises(acpi_failure="unreadable", perf_failure="unreadable")
        assert answer.startswith("THREW: could not read the thermal state")

    def test_a_failed_counter_read_does_not_become_absence_beside_an_empty_acpi_read(self) -> None:
        answer = _detect_raises(perf_failure="unreadable")
        assert answer.startswith("THREW: ")

    def test_a_refused_acpi_read_does_not_become_absence_beside_an_empty_counter_read(self) -> None:
        """MSAcpi answers only elevated; unelevated and no zone in the counter is "could not read"."""
        answer = _detect_raises(acpi_failure="unreadable")
        assert answer.startswith("THREW: ")

    def test_a_refused_acpi_read_still_lets_the_counter_answer(self) -> None:
        """The normal unelevated case: ACPI refuses, the counter reads, the verdict stands."""
        output = run_shipped_script(
            _HARNESS + SCRIPT,
            {"acpi": None, "perf": THIS_MACHINE_PERF, "acpi_failure": "unreadable"},
        )
        lines, finding = _split_detect_output(SYSTEM_THERMAL_CONDITION.id, output)
        assert lines[-1] == "not_throttling"
        assert finding is not None
        assert finding["zone"] == THIS_MACHINE_PERF["Name"]


class TestTheDefinitionItself:
    def test_no_temperature_threshold_decides_the_verdict(self) -> None:
        """A threshold over a zone temperature is an inference, not a measurement."""
        assert "ThrottleReasons" in SCRIPT
        assert "PercentPassiveLimit" in SCRIPT
        assert not re.search(r"\$celsius\s+-gt\s+\d+", SCRIPT)

    def test_the_choices_name_the_two_states_it_can_prove(self) -> None:
        assert SYSTEM_THERMAL_CONDITION.choices == ("not_throttling", "throttling")
        assert SYSTEM_THERMAL_CONDITION.recommended_value == "not_throttling"
        assert SYSTEM_THERMAL_CONDITION.is_readonly

    def test_the_finding_is_valid_json_the_ui_can_key_on(self) -> None:
        _, finding = _detect(perf=THIS_MACHINE_PERF)
        assert finding is not None
        assert json.dumps(finding)  # round-trips, so nothing exotic reached the UI
        assert finding["kind"] == "thermal"
