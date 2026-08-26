"""Every generated command must be a command Windows actually accepts.

This is the test layer that was missing, and its absence is why seven defects
shipped with the whole suite green. The existing tests check that
``substitute_placeholders`` substitutes; nothing checked that the string it
produced was something PowerShell would bind. So
``Get-NetAdapterAdvancedProperty -InterfaceIndex 19`` passed CI for as long as it
existed, while on a real host it failed with

    A parameter cannot be found that matches parameter name 'InterfaceIndex'.

Detection therefore returned nothing and -- the damaging half --
``Set-NetAdapterAdvancedProperty`` wrote nothing while apply reported success.

Rather than pin a hand-written table of valid parameters (which would drift from
Windows exactly the way the definitions did), this asks the host: PowerShell's
own parser extracts each command and the parameters passed to it, and
``Get-Command`` supplies the parameters that command really has.

Two things the first version of this test got wrong, both confirmed against the
host before being accommodated:

* ``Set-ItemProperty -Type`` is a *provider dynamic* parameter. It does not
  appear in ``(Get-Command Set-ItemProperty).Parameters``, but it does appear in
  ``Get-Command Set-ItemProperty -ArgumentList 'HKCU:\\Software'``, and
  ``-WhatIf`` confirms it binds. All 72 initial "failures" were this.
* fpstune's own cleanup scripts define helpers (``Get-DirSizeBytes``,
  ``Emit-DirCleanup``) inside the command text. ``Get-Command`` cannot see them,
  so they are resolved from the script's own AST instead.

Windows-only by nature: there is no PowerShell parser or cmdlet metadata to ask
on other platforms.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils.powershell import substitute_placeholders

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Validates generated commands against real cmdlet metadata, which only Windows has",
)

# A placeholder the executor was supposed to fill. `%` alone is a legal
# PowerShell alias for ForEach-Object, so the name is required to match.
_UNRENDERED = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%")

_VALIDATOR = r"""
$ErrorActionPreference = 'Stop'
$items = Get-Content -LiteralPath $env:FPSTUNE_COMMANDS_JSON -Raw | ConvertFrom-Json

$staticCache = @{}
$dynamicCache = @{}
$problems = [System.Collections.ArrayList]::new()
$externals = [System.Collections.ArrayList]::new()

# Provider contexts used to surface dynamic parameters when the command's own
# path argument is a variable and therefore unresolvable at parse time. This is
# the one deliberately permissive part of the check, and it is scoped to
# provider dynamic parameters only -- a genuinely misspelled static parameter is
# absent from every context.
$fallbackContexts = @('HKCU:\Software', $env:TEMP)

function New-NameSet {
    New-Object 'System.Collections.Generic.HashSet[string]' (
        [System.StringComparer]::OrdinalIgnoreCase
    )
}

function Get-ParameterNames($info) {
    if (-not $info -or -not $info.Parameters -or $info.Parameters.Count -eq 0) { return $null }
    $set = New-NameSet
    foreach ($entry in $info.Parameters.GetEnumerator()) {
        [void]$set.Add($entry.Key)
        foreach ($alias in $entry.Value.Aliases) { [void]$set.Add($alias) }
    }
    return $set
}

function Get-StaticParameters([string]$name) {
    if (-not $staticCache.ContainsKey($name)) {
        $info = Get-Command -Name $name -ErrorAction SilentlyContinue
        while ($info -and $info.CommandType -eq 'Alias' -and $info.ResolvedCommand) {
            $info = $info.ResolvedCommand
        }
        $staticCache[$name] = @{ Info = $info; Parameters = (Get-ParameterNames $info) }
    }
    return $staticCache[$name]
}

function Get-DynamicParameters([string]$name, [string]$context) {
    $key = "$name|$context"
    if (-not $dynamicCache.ContainsKey($key)) {
        $set = $null
        try {
            $set = Get-ParameterNames (
                Get-Command -Name $name -ArgumentList $context -ErrorAction Stop
            )
        } catch {
            $set = $null
        }
        $dynamicCache[$key] = $set
    }
    return $dynamicCache[$key]
}

function Test-ParameterAccepted([System.Collections.Generic.HashSet[string]]$accepted, [string]$name) {
    if (-not $accepted) { return $false }
    if ($accepted.Contains($name)) { return $true }
    # PowerShell accepts an unambiguous abbreviation, so -Reg binds when exactly
    # one real parameter starts with it.
    $prefixed = @($accepted | Where-Object {
        $_.StartsWith($name, [System.StringComparison]::OrdinalIgnoreCase)
    })
    return ($prefixed.Count -eq 1)
}

foreach ($item in $items) {
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput(
        $item.command, [ref]$tokens, [ref]$errors
    )
    if ($errors -and $errors.Count -gt 0) {
        [void]$problems.Add([pscustomobject]@{
            id = $item.id; kind = $item.kind; command = ''; parameter = ''
            reason = "does not parse as PowerShell: $($errors[0].Message)"
        })
        continue
    }

    # Helpers the script defines for itself. Get-Command cannot see these, and a
    # call to one that does not exist is a real defect worth catching.
    $localFunctions = @{}
    foreach ($fn in $ast.FindAll(
        { param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] },
        $true
    )) {
        $declared = $null
        $parameters = if ($fn.Parameters) { $fn.Parameters }
                      elseif ($fn.Body -and $fn.Body.ParamBlock) { $fn.Body.ParamBlock.Parameters }
                      else { $null }
        if ($parameters) {
            $declared = New-NameSet
            foreach ($p in $parameters) { [void]$declared.Add($p.Name.VariablePath.UserPath) }
        }
        $localFunctions[$fn.Name] = $declared
    }

    foreach ($command in $ast.FindAll(
        { param($node) $node -is [System.Management.Automation.Language.CommandAst] }, $true
    )) {
        $name = $command.GetCommandName()
        if (-not $name) { continue }

        $isLocal = $localFunctions.ContainsKey($name)
        $accepted = $null
        if ($isLocal) {
            $accepted = $localFunctions[$name]
        } else {
            $resolved = Get-StaticParameters $name
            if (-not $resolved.Info) {
                # Verb-Noun with nothing behind it is either a typo or a module
                # this host lacks; either way the command cannot run here.
                if ($name -match '^[A-Za-z]+-[A-Za-z]') {
                    [void]$problems.Add([pscustomobject]@{
                        id = $item.id; kind = $item.kind; command = $name; parameter = ''
                        reason = 'command does not resolve on this host and is not defined in the script'
                    })
                } else {
                    [void]$externals.Add("$name")
                }
                continue
            }
            $accepted = $resolved.Parameters
            if (-not $accepted) {
                # An external executable: parameters are its own business.
                [void]$externals.Add("$name")
                continue
            }
        }

        # Literal provider paths in this very command give the authoritative
        # context for dynamic parameters.
        $contexts = [System.Collections.ArrayList]::new()
        foreach ($element in $command.CommandElements) {
            if ($element -is [System.Management.Automation.Language.StringConstantExpressionAst]) {
                if ($element.Value -match '^(HK[A-Za-z_]*:|HKEY_|[A-Za-z]:\\)') {
                    [void]$contexts.Add($element.Value)
                }
            }
        }
        foreach ($fallback in $fallbackContexts) {
            if ($fallback) { [void]$contexts.Add($fallback) }
        }

        foreach ($element in $command.CommandElements) {
            if ($element -isnot [System.Management.Automation.Language.CommandParameterAst]) {
                continue
            }
            $parameter = $element.ParameterName
            if (Test-ParameterAccepted $accepted $parameter) { continue }
            if ($isLocal) {
                [void]$problems.Add([pscustomobject]@{
                    id = $item.id; kind = $item.kind; command = $name; parameter = $parameter
                    reason = 'not a parameter of the helper this script defines'
                })
                continue
            }

            $bound = $false
            foreach ($context in $contexts) {
                if (Test-ParameterAccepted (Get-DynamicParameters $name $context) $parameter) {
                    $bound = $true
                    break
                }
            }
            if (-not $bound) {
                [void]$problems.Add([pscustomobject]@{
                    id = $item.id; kind = $item.kind; command = $name; parameter = $parameter
                    reason = 'no such parameter, static or provider-dynamic'
                })
            }
        }
    }
}

ConvertTo-Json -Depth 4 -Compress -InputObject ([pscustomobject]@{
    problems = @($problems)
    externals = @($externals | Sort-Object -Unique)
})
"""


def _render(template: str, args: dict[str, Any]) -> str:
    """Render exactly the way PowerShellExecutor does, NetAdapter rewrite included."""
    command = ACTION_COMMANDS.get(template.strip(), template)
    return substitute_placeholders(command, **args)


def _apply_sample(setting: SettingExecutor) -> Any:
    """The raw value the executor would substitute for %value%.

    Mirrors ``PowerShellExecutor.apply``: the display value goes through
    ``apply_value_map``, falling back to the display value itself. Any accepted
    value exercises the same command shape, so the recommended one is used.
    """
    display = setting.recommended_value
    if display is None and setting.apply_value_map:
        display = next(iter(setting.apply_value_map))
    return setting.apply_value_map.get(display, display)


def _collect_commands() -> list[dict[str, str]]:
    """Every PowerShell command the shipped definitions can generate on this host.

    Dynamic discovery is on, so the per-adapter settings -- the surface where all
    seven defects were found -- are included with this host's real interface
    indexes.
    """
    registry = SettingsRegistry(discover_dynamic=True)
    collected: list[dict[str, str]] = []

    for setting in registry.get_all():
        if setting.detect_type == DetectType.POWERSHELL and setting.detect_command.strip():
            collected.append(
                {
                    "id": setting.id,
                    "kind": "detect",
                    "command": _render(setting.detect_command, setting.detect_args),
                }
            )
        if setting.apply_type == DetectType.POWERSHELL and setting.apply_command.strip():
            args = {**setting.apply_args, "value": _apply_sample(setting)}
            collected.append(
                {
                    "id": setting.id,
                    "kind": "apply",
                    "command": _render(setting.apply_command, args),
                }
            )

    return collected


def _validate(commands: list[dict[str, str]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        commands_path = Path(tmp) / "commands.json"
        script_path = Path(tmp) / "validate.ps1"
        commands_path.write_text(json.dumps(commands), encoding="utf-8")
        script_path.write_text(_VALIDATOR, encoding="utf-8")

        result = subprocess.run(  # noqa: S603 - fixed argv, both paths are ours
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env={**os.environ, "FPSTUNE_COMMANDS_JSON": str(commands_path)},
            check=False,
        )

    assert result.returncode == 0, (
        f"The validator itself failed (exit {result.returncode}). This is not a "
        f"definition problem.\nstderr: {result.stderr[:2000]}"
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    commands = _collect_commands()
    assert commands, "No PowerShell-backed settings collected; the scan exercises nothing"
    return {"commands": commands, **_validate(commands)}


def test_every_parameter_exists_on_the_command_it_is_passed_to(report: dict[str, Any]) -> None:
    """The #40 class, generalised beyond the NetAdapter family.

    #40 was 41 call sites passing -InterfaceIndex to cmdlets that only accept
    -Name, 14 of them on the apply path, so those writes silently did nothing
    while reporting success. Asking the host means no cmdlet can be called with
    a parameter it does not have, and a call to an undefined script helper is
    caught by the same walk.
    """
    problems = report["problems"]
    detail = "\n".join(
        f"  {p['id']} [{p['kind']}]: {p['command']} -{p['parameter']} :: {p['reason']}"
        for p in problems
    )
    assert not problems, f"{len(problems)} generated command(s) Windows would reject:\n{detail}"


def test_no_placeholder_survives_rendering(report: dict[str, Any]) -> None:
    """An unfilled %placeholder% reaches PowerShell as a literal and cannot work.

    Separate from the parameter check because the failure mode differs: such a
    command can still parse, so the AST walk would not necessarily flag it.
    """
    leftover = [
        f"  {item['id']} [{item['kind']}]: {sorted(set(_UNRENDERED.findall(item['command'])))}"
        for item in report["commands"]
        if _UNRENDERED.search(item["command"])
    ]
    assert not leftover, "Commands still containing an unrendered placeholder:\n" + "\n".join(
        leftover
    )


def test_the_check_actually_fires() -> None:
    """A guard that has never been seen to fail is not known to work.

    The definitions are currently clean, so the test above passes vacuously as
    far as the reader can tell. This feeds the historical defect back through the
    same validator and pins that it is caught -- on the apply path too, which is
    the half that wrote nothing while reporting success -- while the two commands
    that merely look similar are left alone.
    """
    probes = [
        # #40 verbatim, both halves.
        {
            "id": "probe:detect_by_index",
            "kind": "detect",
            "command": "Get-NetAdapterAdvancedProperty -InterfaceIndex 19 -RegistryKeyword '*FlowControl'",
        },
        {
            "id": "probe:apply_by_index",
            "kind": "apply",
            "command": (
                "Set-NetAdapterAdvancedProperty -InterfaceIndex 19 "
                "-RegistryKeyword '*FlowControl' -RegistryValue 0"
            ),
        },
        # A misspelled call to a helper the script defines for itself.
        {
            "id": "probe:undefined_helper",
            "kind": "detect",
            "command": "function Get-DirSizeBytes { param($Path) 1 }; Get-DirSizeByte -Path C:\\Temp",
        },
        {
            "id": "probe:helper_bad_parameter",
            "kind": "detect",
            "command": "function Emit-Thing { param($Path) 1 }; Emit-Thing -Pathx C:\\Temp",
        },
        # Must NOT be flagged: the one cmdlet that does take -InterfaceIndex, and
        # a provider dynamic parameter that Get-Command cannot see statically.
        {
            "id": "probe:bare_get_netadapter_is_fine",
            "kind": "detect",
            "command": "Get-NetAdapter -InterfaceIndex 19 | Select-Object Name",
        },
        {
            "id": "probe:provider_dynamic_parameter_is_fine",
            "kind": "apply",
            "command": "Set-ItemProperty -Path 'HKCU:\\Software' -Name x -Value 1 -Type DWord",
        },
    ]

    flagged = {p["id"] for p in _validate(probes)["problems"]}

    assert flagged == {
        "probe:detect_by_index",
        "probe:apply_by_index",
        "probe:undefined_helper",
        "probe:helper_bad_parameter",
    }, f"The validator did not flag exactly the four broken probes, it flagged: {sorted(flagged)}"


def test_coverage_is_reported_not_assumed(report: dict[str, Any]) -> None:
    """Name what the check could not cover, so nothing is silently exempt.

    Commands with no introspectable parameters are external executables, whose
    arguments PowerShell does not model. Listing them keeps the exemption
    visible; the assertion only pins that the set stays small and non-cmdlet, so
    a cmdlet cannot quietly slip into the exempt bucket.
    """
    externals = report["externals"]
    cmdlet_shaped = [name for name in externals if re.match(r"^[A-Za-z]+-[A-Za-z]", name)]
    assert not cmdlet_shaped, (
        "These are Verb-Noun commands that ended up in the unchecked bucket, so "
        "their parameters were never validated: " + ", ".join(sorted(cmdlet_shaped))
    )
