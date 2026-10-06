"""Mechanical guard: no batch script in ps_batch.py seeds a default and swallows errors.

Issue #104 class B. The adapter power batch declared ``$state = 'Enabled'`` before
it read anything and ran every read with ``-EA SilentlyContinue``. A read that
failed (the adapter was restarting) left the seed in place, and the seed went out
as if it had been read. The scripts are Python string literals, so the structure
is checked on the module's AST rather than by running them:

1. no PowerShell string assigns a bare quoted literal to a variable
   (``$state = 'Enabled'``) — a result is assigned from a read, or not at all;
2. no PowerShell string silences errors (``-EA SilentlyContinue``, ``-ErrorAction
   Ignore``): a failed cmdlet must end the read, which is then unread (``None``);
3. every ``_fetch_*_snapshot`` can say it failed: its return type admits ``None``,
   so "could not read" has a spelling that is not an empty map.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import fpstune.settings.executors.ps_batch as ps_batch

_SEED = re.compile(r"\$\w+\s*=\s*'[^'\n]*'\s*;")
_SWALLOW = re.compile(
    r"-(?:EA|ErrorAction)\s+(?:SilentlyContinue|Ignore)\b|\$ErrorActionPreference\s*=\s*'?(?:SilentlyContinue|Ignore)",
    re.IGNORECASE,
)
_CMDLET = re.compile(r"\b(?:Get|Set|New|Remove)-[A-Za-z]+")


def _script_strings(tree: ast.AST) -> list[str]:
    """Every string literal that is PowerShell, docstrings excluded."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and _CMDLET.search(node.value)
    ]


def violations(source: str) -> list[str]:
    """What is wrong with the batch scripts and snapshot fetchers in ``source``."""
    tree = ast.parse(source)
    found: list[str] = []
    for text in _script_strings(tree):
        if match := _SEED.search(text):
            found.append(f"seeds a default before the read: {match.group(0)!r}")
        if match := _SWALLOW.search(text):
            found.append(f"swallows read errors: {match.group(0)!r}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and re.fullmatch(r"_fetch_\w*snapshot", node.name)
            and node.returns is not None
            and "None" not in ast.unparse(node.returns)
        ):
            found.append(f"{node.name} cannot report a failed read (return type has no None)")
    return found


def test_the_batch_scripts_in_ps_batch_seed_no_default_and_swallow_no_error() -> None:
    source = Path(ps_batch.__file__).read_text(encoding="utf-8")
    assert violations(source) == []


def test_the_guard_actually_sees_the_scripts_it_polices() -> None:
    # A guard over zero scripts passes vacuously.
    tree = ast.parse(Path(ps_batch.__file__).read_text(encoding="utf-8"))
    scripts = _script_strings(tree)
    assert any("Get-NetAdapter" in s for s in scripts)
    assert any("Get-Service" in s for s in scripts)


# The shape that shipped: seed the answer, read with errors silenced.
_OLD_POWER_SCRIPT = """
def _fetch_adapter_power_snapshot() -> dict[str, str]:
    cmd = (
        "$out = @{}; "
        "Get-NetAdapter -EA SilentlyContinue | ForEach-Object { "
        "$state = 'Enabled'; "
        "$drv = (Get-PnpDeviceProperty -InstanceId $_.PnPDeviceID "
        "-KeyName 'DEVPKEY_Device_Driver' -EA SilentlyContinue).Data; "
        "$out[[string]$_.InterfaceIndex] = $state }; "
        "$out | ConvertTo-Json -Compress"
    )
    return {}
"""


def test_the_guard_flags_the_script_that_shipped_the_bug() -> None:
    found = violations(_OLD_POWER_SCRIPT)
    assert any("seeds a default" in f and "$state = 'Enabled'" in f for f in found), found
    assert any("swallows read errors" in f for f in found), found
    assert any("cannot report a failed read" in f for f in found), found


@pytest.mark.parametrize(
    "script",
    [
        "$state = 'Enabled'; Get-Item x",
        "Get-Item x -ErrorAction SilentlyContinue",
        "Get-Item x -ErrorAction Ignore",
        "$ErrorActionPreference = 'SilentlyContinue'; Get-Item x",
    ],
)
def test_the_guard_flags_each_form_of_the_pattern(script: str) -> None:
    assert violations(f"X = {script!r}")


@pytest.mark.parametrize(
    "script",
    [
        "$out = @{}; Get-Item x -ErrorAction Stop",
        "try { $v = (Get-Item x -ErrorAction Stop).Value } catch { 'error:' + $_.Exception.Message }",
        "$out[$k] = if ($v) { 'Disabled' } else { 'Enabled' }",
    ],
)
def test_the_guard_leaves_a_script_that_reads_before_it_assigns(script: str) -> None:
    assert violations(f"X = {script!r}") == []
