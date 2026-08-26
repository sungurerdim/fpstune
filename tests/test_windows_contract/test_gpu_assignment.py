"""`gpu-hardware:gpu_assignment` — which GPU the games actually run on.

The defect this file exists for: the setting tested `DirectXUserGlobalSettings` for
`*GpuPreference=2*`, and that value can never contain it. Windows stores a GPU
preference as its own value **per executable path**; DirectXUserGlobalSettings holds
the three global toggles from the same Settings page. Measured on a hybrid laptop
with the preference already set for three games:

    DirectXUserGlobalSettings    = VRROptimizeEnable=1;SwapEffectUpgradeEnable=1;
                                   AutoHDREnable=1;        <- no GpuPreference, ever
    ...\\cod23-cod.exe            = GpuPreference=2;
    ...\\cs2.exe                  = GpuPreference=2;

So it answered `not_configured` on a configured machine — on every hybrid machine,
however it was set up. It was also `is_readonly`, on the grounds that fpstune could
not act; the registry it needs is plain HKCU.

These tests run the shipped commands verbatim against a described host. The rule
they exist to hold is the #56 rule: detect inspects exactly the executables apply
writes, and every one of them must be on the discrete GPU — one game left on "Let
Windows decide" is the whole problem the setting is for.
"""

from __future__ import annotations

import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command

from fpstune.settings.definitions.gpu import _GAME_EXE_SCAN, GPU_LAPTOP_ASSIGNMENT

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

CS2 = r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe"
MW3 = r"D:\Games\Call of Duty Modern Warfare III\_retail_\cod23-cod.exe"

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
$script:FpsFakeWrites = @{}

function Get-CimInstance {
    [CmdletBinding()] param([Parameter(Position = 0)]$ClassName)
    [pscustomobject]@{ Name = 'NVIDIA GeForce RTX 4070 Laptop GPU' }
    if ($FpsFake.hybrid) { [pscustomobject]@{ Name = 'Intel(R) UHD Graphics' } }
}

function Get-ChildItem {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path)
    if ($Path -like '*\Uninstall') {
        foreach ($e in $FpsFake.uninstall) {
            [pscustomobject]@{ PSPath = "$Path\$($e.key)"; PSChildName = $e.key }
        }
    }
}

function Get-ItemProperty {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path, [string]$Name)
    if ($Path -like '*Valve\Steam') {
        if ($FpsFake.steam) { return [pscustomobject]@{ InstallPath = $FpsFake.steam } }
        return $null
    }
    if ($Path -like '*\Uninstall\*') {
        $leaf = Split-Path $Path -Leaf
        foreach ($e in $FpsFake.uninstall) {
            if ($e.key -eq $leaf) {
                return [pscustomobject]@{ DisplayName = $e.name; InstallLocation = $e.location }
            }
        }
        return $null
    }
    if ($Path -like '*UserGpuPreferences*') {
        if (-not $FpsFake.prefs) { return $null }
        $o = New-Object psobject
        foreach ($p in $FpsFake.prefs.PSObject.Properties) {
            $o | Add-Member -NotePropertyName $p.Name -NotePropertyValue $p.Value
        }
        foreach ($k in $script:FpsFakeWrites.Keys) {
            $o | Add-Member -NotePropertyName $k -NotePropertyValue $script:FpsFakeWrites[$k] -Force
        }
        return $o
    }
    return $null
}

function Test-Path {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path)
    if ($Path -like '*UserGpuPreferences*') { return [bool]$FpsFake.prefs }
    return ([string[]]$FpsFake.exists -contains $Path)
}

function Get-Content {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path, [switch]$Raw)
    return $FpsFake.vdf
}

function Set-ItemProperty {
    [CmdletBinding()]
    param([Parameter(Position = 0)][string]$Path, [string]$Name, $Value, [switch]$Force)
    $script:FpsFakeWrites[$Name] = $Value
}

function Remove-ItemProperty {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path, [string]$Name, [switch]$Force)
    $script:FpsFakeWrites[$Name] = '<removed>'
}

function New-Item {
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path, [switch]$Force)
}

"""


def _host(
    *,
    hybrid: bool = True,
    steam: str | None = r"C:\Program Files (x86)\Steam",
    libraries: tuple[str, ...] = (r"D:\SteamLibrary",),
    installed: tuple[str, ...] = (CS2, MW3),
    prefs: dict[str, str] | None = None,
) -> dict:
    vdf = "".join(f'"path"\t\t"{lib}"\n' for lib in libraries)
    # Everything the command probes with Test-Path: Steam's library index, and each
    # game executable that is genuinely on disk.
    exists = list(installed)
    if steam:
        exists.append(rf"{steam}\steamapps\libraryfolders.vdf")
    return {
        "hybrid": hybrid,
        "steam": steam,
        "vdf": vdf,
        "exists": exists,
        "uninstall": [
            {
                "key": "Call of Duty Modern Warfare III",
                "name": "Call of Duty Modern Warfare III",
                "location": r"D:\Games\Call of Duty Modern Warfare III",
            }
        ],
        "prefs": prefs,
    }


def _detect(host: dict) -> str:
    return run_shipped_command(_PRELUDE + GPU_LAPTOP_ASSIGNMENT.detect_command, host)


def _apply(host: dict, value: str) -> str:
    command = GPU_LAPTOP_ASSIGNMENT.apply_command.replace("%value%", value)
    return run_shipped_command(_PRELUDE + command, host)


BOTH_ON_DGPU = {CS2: "GpuPreference=2;", MW3: "GpuPreference=2;"}


# The command as it shipped, kept verbatim so the fix can be shown to change the
# answer rather than merely to pass. Without this the test below could be green for
# any number of reasons that have nothing to do with the defect.
_PREVIOUS_DETECT = (
    "$gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue; "
    "$igpu = $gpus | Where-Object { $_.Name -match 'Intel|UHD|Iris' }; "
    "$dgpu = $gpus | Where-Object { $_.Name -match 'NVIDIA|GeForce|Radeon' -and "
    "$_.Name -notmatch 'Intel' }; "
    "if (-not $igpu -or -not $dgpu) { 'single_gpu' } "
    "else { $pref = (Get-ItemProperty -Path "
    r"'HKCU:\Software\Microsoft\DirectX\UserGpuPreferences' "
    "-Name 'DirectXUserGlobalSettings' -ErrorAction SilentlyContinue"
    ").DirectXUserGlobalSettings; "
    "if ($pref -like '*GpuPreference=2*') { 'dgpu_preferred' } else { 'not_configured' } }"
)


class TestTheGlobalValueRegression:
    def test_a_configured_machine_reads_as_configured(self) -> None:
        """The exact failure: games set to High performance, read as unset."""
        assert _detect(_host(prefs=BOTH_ON_DGPU)) == "dgpu_preferred"

    def test_the_previous_command_got_this_host_wrong(self) -> None:
        """Same host, same harness — only the command differs."""
        answer = run_shipped_command(_PRELUDE + _PREVIOUS_DETECT, _host(prefs=BOTH_ON_DGPU))
        assert answer == "not_configured"

    def test_the_global_toggles_alone_are_not_a_gpu_preference(self) -> None:
        """DirectXUserGlobalSettings never carries GpuPreference — it must not decide."""
        prefs = {
            "DirectXUserGlobalSettings": "VRROptimizeEnable=1;SwapEffectUpgradeEnable=1;",
        }
        assert _detect(_host(prefs=prefs)) == "not_configured"

    def test_the_shipped_detect_no_longer_reads_that_value(self) -> None:
        assert "DirectXUserGlobalSettings" not in GPU_LAPTOP_ASSIGNMENT.detect_command


class TestEveryGameCounts:
    def test_one_game_left_behind_is_not_configured(self) -> None:
        """Any-of would call this machine done while a game still runs on the iGPU."""
        prefs = {CS2: "GpuPreference=2;", MW3: "GpuPreference=0;"}
        assert _detect(_host(prefs=prefs)) == "not_configured"

    def test_a_game_with_no_entry_at_all_is_not_configured(self) -> None:
        assert _detect(_host(prefs={CS2: "GpuPreference=2;"})) == "not_configured"

    def test_power_saving_is_not_high_performance(self) -> None:
        prefs = {CS2: "GpuPreference=1;", MW3: "GpuPreference=1;"}
        assert _detect(_host(prefs=prefs)) == "not_configured"


class TestWhenTheQuestionDoesNotArise:
    def test_a_single_gpu_machine_says_so(self) -> None:
        assert _detect(_host(hybrid=False, prefs=BOTH_ON_DGPU)) == "single_gpu"

    def test_no_known_game_installed_is_not_available(self) -> None:
        """Not `not_configured` — there is nothing to configure, which is not a fault."""
        assert _detect(_host(installed=(), prefs=None)) == "not_available"

    def test_apply_refuses_a_single_gpu_machine(self) -> None:
        assert _apply(_host(hybrid=False), "dgpu_preferred").startswith("error:")


class TestApply:
    def test_it_writes_every_game_it_found(self) -> None:
        assert _apply(_host(prefs=None), "dgpu_preferred") == "ok:2"

    def test_it_walks_the_same_games_detect_does(self) -> None:
        """One scan, so neither command can reach further than the other (#56)."""
        assert _GAME_EXE_SCAN in GPU_LAPTOP_ASSIGNMENT.detect_command
        assert _GAME_EXE_SCAN in GPU_LAPTOP_ASSIGNMENT.apply_command

    def test_reset_removes_the_entry_rather_than_zeroing_it(self) -> None:
        """A GpuPreference=0 would read as a deliberate choice fpstune made for you."""
        command = GPU_LAPTOP_ASSIGNMENT.apply_command
        assert "Remove-ItemProperty" in command
        assert "GpuPreference=0" not in command

    def test_it_finds_a_game_on_a_secondary_steam_library(self) -> None:
        """CS2 is usually not on the drive Steam itself is installed on."""
        assert _apply(_host(installed=(CS2,)), "dgpu_preferred") == "ok:1"
