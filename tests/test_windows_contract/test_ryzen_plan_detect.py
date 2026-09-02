"""`power:ryzen_balanced_plan` reads powercfg by GUID pattern, not by word position.

The shipped detect took the active scheme's GUID as the fourth space-separated
token of ``powercfg /getactivescheme``. That is the GUID in English ("Power
Scheme GUID: <guid>"), Turkish and German — and in French the label is "GUID du
mode de gestion de l'alimentation : <guid>", whose fourth token is "de". ``-match
'de'`` then matched every line of the list, so a French machine on the Windows
Balanced plan reported the Ryzen plan as active and the setting never offered it.
The plan's own name, "AMD Ryzen Balanced", is AMD's string and does not change
with the Windows language.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.registry import SettingsRegistry

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

RYZEN = "9897998c-92de-4669-853f-b7cd3ecb2790"
BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"


@pytest.fixture(scope="module")
def detect_command() -> str:
    setting = SettingsRegistry(discover_dynamic=False).get("power:ryzen_balanced_plan")
    assert setting is not None
    return setting.detect_command


_PRELUDE = r"""
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
function powercfg {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)
    switch ($Rest[0].ToLower()) {
        '/getactivescheme' { [string[]]$FpsFake.active }
        '/list' { [string[]]$FpsFake.list }
        default { throw "unexpected powercfg $($Rest -join ' ')" }
    }
}
"""


def _french(active: str) -> dict:
    return {
        "active": [f"GUID du mode de gestion de l'alimentation : {active}  (plan actif)"],
        "list": [
            "",
            "Modes de gestion de l'alimentation existants (* Actif)",
            "-----------------------------------",
            f"GUID du mode de gestion de l'alimentation : {BALANCED}  (Utilisation normale)"
            + (" *" if active == BALANCED else ""),
            f"GUID du mode de gestion de l'alimentation : {RYZEN}  (AMD Ryzen Balanced)"
            + (" *" if active == RYZEN else ""),
        ],
    }


def _english(active: str, ryzen_installed: bool = True) -> dict:
    plans = [f"Power Scheme GUID: {BALANCED}  (Balanced)" + (" *" if active == BALANCED else "")]
    if ryzen_installed:
        plans.append(
            f"Power Scheme GUID: {RYZEN}  (AMD Ryzen Balanced)" + (" *" if active == RYZEN else "")
        )
    return {
        "active": [f"Power Scheme GUID: {active}  (whatever)"],
        "list": [
            "",
            "Existing Power Schemes (* Active)",
            "-----------------------------------",
            *plans,
        ],
    }


def test_french_windows_on_the_windows_plan_is_not_using_ryzen(detect_command: str) -> None:
    """The gate: word position said 'de' here and matched every line."""
    assert (
        run_shipped_command(_PRELUDE + detect_command, _french(BALANCED)) == "not_using_ryzen_plan"
    )


def test_french_windows_on_the_ryzen_plan_is_detected(detect_command: str) -> None:
    assert run_shipped_command(_PRELUDE + detect_command, _french(RYZEN)) == "ryzen_balanced"


def test_english_windows_answers_the_same_three_ways(detect_command: str) -> None:
    assert run_shipped_command(_PRELUDE + detect_command, _english(RYZEN)) == "ryzen_balanced"
    assert (
        run_shipped_command(_PRELUDE + detect_command, _english(BALANCED)) == "not_using_ryzen_plan"
    )
    assert (
        run_shipped_command(_PRELUDE + detect_command, _english(BALANCED, ryzen_installed=False))
        == "no_ryzen_plan"
    )


def test_an_unreadable_active_scheme_never_matches_everything(detect_command: str) -> None:
    """An empty GUID must not turn `-match` into 'match every line'."""
    host = _english(BALANCED)
    host["active"] = ["Access is denied."]
    assert run_shipped_command(_PRELUDE + detect_command, host) == "not_using_ryzen_plan"
