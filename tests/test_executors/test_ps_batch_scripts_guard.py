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

The same class sat in the detect scripts of the setting definitions: ``catch {
'not_available' }`` / ``catch { 'not_supported' }`` turned every failed read into an
ABSENT_READINGS value ("this feature is not on the machine"). So, over every
PowerShell string in ``src/fpstune``:

4. no ``catch`` block yields an ABSENT_READINGS sentinel, unless the snippet is on
   ``_CATCH_SENTINEL_ALLOWED`` with the reason the catch genuinely means "absent".
   A failed read ends the script (``catch { throw }``): PowerShell exits non-zero,
   the detect fails, and the row reads "unknown" with the reason.
   The guard matches a sentinel answered *directly* by the catch block. The
   sanctioned way to keep one is a catch that first proves absence -- a nested
   ``if`` over a readable feature list or ``Get-Command`` -- and rethrows otherwise;
   its scripted behaviour is tested where the script lives (test_optional_feature_detect,
   test_unread_tcp_snapshot).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import fpstune
import fpstune.settings.executors.ps_batch as ps_batch
from fpstune.settings.applicability import ABSENT_READINGS

_SEED = re.compile(r"\$\w+\s*=\s*'[^'\n]*'\s*;")
_SWALLOW = re.compile(
    r"-(?:EA|ErrorAction)\s+(?:SilentlyContinue|Ignore)\b|\$ErrorActionPreference\s*=\s*'?(?:SilentlyContinue|Ignore)",
    re.IGNORECASE,
)
_CMDLET = re.compile(r"\b(?:Get|Set|New|Remove)-[A-Za-z]+")


def _strings(tree: ast.AST) -> list[str]:
    """Every string literal in the tree, docstrings excluded."""
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
    ]


def _script_strings(tree: ast.AST) -> list[str]:
    """Every string literal that is PowerShell, docstrings excluded."""
    return [text for text in _strings(tree) if _CMDLET.search(text)]


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


# ---------------------------------------------------------------------------
# 4. a catch must not turn a failed read into "absent"
# ---------------------------------------------------------------------------

_CATCH_SENTINEL = re.compile(
    r"\bcatch\b(?:\s*\[[^\]]*\])?\s*\{[^{}]*['\"]("
    + "|".join(sorted(ABSENT_READINGS))
    + r")['\"][^{}]*\}",
    re.IGNORECASE,
)

# Snippet (the matched text, whitespace as written) -> why this catch genuinely
# means "the thing is absent here", and not "the read failed". Empty on purpose:
# every catch in the shipped scripts that used to answer an absent reading was a
# failed read (an unelevated Get-WindowsOptionalFeature, Get-NetTCPSetting, an
# adapter that went away mid-query). An entry needs a measured reason, in words.
_CATCH_SENTINEL_ALLOWED: dict[str, str] = {}


def catch_sentinels(source: str, allowed: dict[str, str] | None = None) -> list[str]:
    """Each ``catch { ... 'not_...' }`` in the PowerShell strings of ``source``."""
    allowed = _CATCH_SENTINEL_ALLOWED if allowed is None else allowed
    found: list[str] = []
    for text in _strings(ast.parse(source)):
        for match in _CATCH_SENTINEL.finditer(text):
            if match.group(0) not in allowed:
                found.append(match.group(0))
    return found


def _shipped_sources() -> list[Path]:
    root = Path(fpstune.__file__).parent
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_no_shipped_catch_turns_a_failed_read_into_an_absent_reading() -> None:
    found = {
        str(path.relative_to(Path(fpstune.__file__).parent)): hits
        for path in _shipped_sources()
        if (hits := catch_sentinels(path.read_text(encoding="utf-8")))
    }
    assert found == {}, (
        "a catch that answers an ABSENT_READINGS value reports a failed read as "
        "'not here': end the script with `catch { throw }`, or allow-list the "
        "snippet in _CATCH_SENTINEL_ALLOWED with the reason it really means absent"
    )


def test_the_catch_guard_sees_the_scripts_it_polices() -> None:
    # A guard over no catch blocks passes vacuously.
    catches = 0
    for path in _shipped_sources():
        catches += sum(
            len(re.findall(r"\bcatch\b\s*\{", text))
            for text in _strings(ast.parse(path.read_text(encoding="utf-8")))
        )
    assert catches >= 20, catches


@pytest.mark.parametrize("sentinel", sorted(ABSENT_READINGS))
def test_the_catch_guard_flags_every_absent_spelling(sentinel: str) -> None:
    script = f"try {{ Get-Item x -ErrorAction Stop }} catch {{ '{sentinel}' }}"
    assert catch_sentinels(f"X = {script!r}") == [f"catch {{ '{sentinel}' }}"]


@pytest.mark.parametrize(
    "script",
    [
        "try { Get-NetTCPSetting -ErrorAction Stop } catch { 'not_available' }",
        "try { Get-MMAgent -ErrorAction Stop } catch [System.Exception] { 'not_found' }",
        'try { Get-Item x } catch { "not_supported" }',
        "try { Get-Item x } catch { $v = 'not_installed' }",
    ],
)
def test_the_catch_guard_flags_each_shape_of_the_pattern(script: str) -> None:
    assert catch_sentinels(f"X = {script!r}")


@pytest.mark.parametrize(
    "script",
    [
        "try { Get-Item x -ErrorAction Stop } catch { throw }",
        "try { Get-Item x } catch { 'error:' + $_.Exception.Message }",
        # an absent answer from the try body is a read answer, not a catch
        "try { if (-not $drv) { 'not_supported'; return }; 'Enabled' } catch { throw }",
        # a sentinel in a later statement, outside the catch block
        "try { Get-Item x } catch { $f = $null }; if (-not $f) { 'not_available' }",
    ],
)
def test_the_catch_guard_leaves_a_catch_that_fails_the_read(script: str) -> None:
    assert catch_sentinels(f"X = {script!r}") == []


def test_an_allow_listed_catch_is_let_through_with_its_reason() -> None:
    script = "try { Get-Item x } catch { 'not_found' }"
    snippet = "catch { 'not_found' }"
    assert catch_sentinels(f"X = {script!r}", {}) == [snippet]
    assert catch_sentinels(f"X = {script!r}", {snippet: "the module is not on Home"}) == []
