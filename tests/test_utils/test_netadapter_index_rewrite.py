"""NetAdapter* cmdlets must never be called with -InterfaceIndex.

Only the bare ``Get-NetAdapter`` accepts that parameter. Every other cmdlet in
the family takes ``-Name`` and fails at parameter binding, which is how ~41
generated commands came to fail silently: detection returned nothing, and
``Set-NetAdapterAdvancedProperty`` wrote nothing while apply still reported
success. The user believed every network tweak was applied; none were.

These tests pin the rewrite, and the last one scans the real definitions so a
newly written command cannot reintroduce the pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fpstune.utils.powershell import substitute_placeholders

# Cmdlets confirmed against Get-Command on Windows: InterfaceIndex=False, Name=True
REWRITTEN_CMDLETS = [
    "Get-NetAdapterAdvancedProperty",
    "Set-NetAdapterAdvancedProperty",
    "Get-NetAdapterLso",
    "Set-NetAdapterLso",
    "Get-NetAdapterRss",
    "Set-NetAdapterRss",
    "Get-NetAdapterPowerManagement",
    "Enable-NetAdapterChecksumOffload",
    "Disable-NetAdapterChecksumOffload",
    "Restart-NetAdapterAdvancedProperty",
]


@pytest.mark.parametrize("cmdlet", REWRITTEN_CMDLETS)
def test_interface_index_is_rewritten_to_name(cmdlet: str) -> None:
    out = substitute_placeholders(f"{cmdlet} -InterfaceIndex %ifindex% -Foo bar", ifindex=19)
    assert f"{cmdlet} -Name $fpstuneAdapterName" in out
    assert f"{cmdlet} -InterfaceIndex" not in out


@pytest.mark.parametrize("cmdlet", REWRITTEN_CMDLETS)
def test_rewrite_emits_a_resolution_preamble(cmdlet: str) -> None:
    out = substitute_placeholders(f"{cmdlet} -InterfaceIndex %ifindex%", ifindex=19)
    assert out.startswith("$fpstuneAdapterName = (Get-NetAdapter -InterfaceIndex 19")
    assert "-ErrorAction SilentlyContinue).Name;" in out


def test_bare_get_netadapter_is_left_alone() -> None:
    # Get-NetAdapter is the one cmdlet that does accept -InterfaceIndex, and it is
    # what the preamble itself relies on. Rewriting it would break the rewrite.
    src = "Get-NetAdapter -InterfaceIndex %ifindex% | Select-Object Name"
    assert substitute_placeholders(src, ifindex=19) == (
        "Get-NetAdapter -InterfaceIndex 19 | Select-Object Name"
    )


def test_apply_path_is_rewritten_too() -> None:
    # The apply half is the damaging one: a failed Set- wrote nothing while the
    # caller still reported success.
    out = substitute_placeholders(
        "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
        "-RegistryKeyword '*FlowControl' -RegistryValue 0",
        ifindex=19,
    )
    assert "-Name $fpstuneAdapterName" in out
    assert "-InterfaceIndex 19 -RegistryKeyword" not in out


def test_commands_without_the_pattern_are_untouched() -> None:
    src = "Get-Service -Name Spooler | Select-Object Status"
    assert substitute_placeholders(src) == src


def test_adapter_name_variable_is_used_unquoted_but_as_a_single_token() -> None:
    # Adapter names contain spaces ("Yerel Ag Baglantisi* 9"). Passing the
    # variable rather than an interpolated literal keeps it one argument.
    out = substitute_placeholders(
        "Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex%", ifindex=4
    )
    assert "-Name $fpstuneAdapterName" in out
    assert '-Name "' not in out


def test_no_definition_still_calls_a_netadapter_cmdlet_by_index() -> None:
    """Scan the real definitions, not just the rewrite in isolation.

    The rewrite is a safety net; a definition should not rely on it silently.
    This asserts the net actually covers everything currently shipped, so a new
    command written with -InterfaceIndex is caught by the same rewrite rather
    than failing at runtime.
    """
    pattern = re.compile(
        r"\b(?:Get|Set|Enable|Disable|Restart|New|Remove)-NetAdapter[A-Za-z]+"
        r"\s+-InterfaceIndex\s+%ifindex%"
    )
    definitions = Path(__file__).resolve().parents[2] / "src" / "fpstune" / "settings"

    uncovered = []
    for path in definitions.rglob("*.py"):
        for raw in pattern.findall(path.read_text(encoding="utf-8")):
            rewritten = substitute_placeholders(raw, ifindex=1)
            if "-InterfaceIndex" in rewritten.split(").Name;", 1)[-1]:
                uncovered.append(f"{path.name}: {raw}")

    assert uncovered == [], (
        "These calls pass -InterfaceIndex to a cmdlet that rejects it, and the "
        f"rewrite did not catch them: {uncovered}"
    )
