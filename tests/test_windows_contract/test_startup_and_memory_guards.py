"""The startup-apps advisory and the memory-compression guard, run as shipped.

Both read state a fake cannot get wrong by accident: the startup advisory walks
three Run keys, their StartupApproved flags and two Startup folders, and must
leave out security software without a vendor list; the memory-compression read
must not turn a property it cannot see into "disabled", which would have the
guard write over a state nobody read.
"""

from __future__ import annotations

import json
import sys

import pytest
from tests.test_windows_contract.conftest import run_shipped_command, run_shipped_script

from fpstune.settings.definitions.system import MEMORY_COMPRESSION, SYSTEM_STARTUP_APPS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_CV = r"Software\Microsoft\Windows\CurrentVersion"
_APPROVED = _CV + r"\Explorer\StartupApproved"

# Registry keys and folders come from the payload; a function shadows the
# cmdlet of the same name for the whole script.
_STARTUP_PRELUDE = r"""
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json

function Get-CimInstance {
    param([string]$Namespace, [string]$ClassName)
    foreach ($p in @($FpsFake.av)) {
        if ($p) { [pscustomobject]@{ pathToSignedProductExe = $p; pathToSignedReportingExe = $null } }
    }
}
function Get-Item {
    param([string]$LiteralPath)
    $vals = $FpsFake.keys.$LiteralPath
    if ($null -eq $vals) { return $null }
    $o = [pscustomobject]@{ V = $vals }
    $o | Add-Member -MemberType ScriptMethod -Name GetValueNames -Value { @($this.V.PSObject.Properties.Name) }
    $o | Add-Member -MemberType ScriptMethod -Name GetValue -Value { param($n) $this.V.$n }
    $o
}
function Get-ItemProperty {
    param([string]$LiteralPath, [string]$Name)
    $vals = $FpsFake.keys.$LiteralPath
    if ($null -eq $vals) { return $null }
    if (-not $Name) { return $vals }
    $raw = $vals.$Name
    if ($null -eq $raw) { return $null }
    [pscustomobject]@{ $Name = [byte[]]@($raw) }
}
function Get-ChildItem {
    param([string]$LiteralPath, [switch]$File)
    $key = if ($LiteralPath -eq [Environment]::GetFolderPath('CommonStartup')) { 'COMMON' } else { $LiteralPath }
    foreach ($n in @($FpsFake.folders.$key)) { if ($n) { [pscustomobject]@{ Name = $n } } }
}
"""

_USER_STARTUP = r"C:\Users\player\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"


def _startup(payload: dict) -> tuple[str, dict]:
    out = run_shipped_script(_STARTUP_PRELUDE + SYSTEM_STARTUP_APPS.detect_command, payload)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    finding_lines = [line for line in lines if line.startswith("FPSTUNE_FINDING:")]
    assert finding_lines, f"no finding line in: {out[:500]}"
    finding = json.loads(finding_lines[-1][len("FPSTUNE_FINDING:") :])
    return lines[-1], finding


def test_enabled_entries_are_named_and_security_disabled_and_hidden_ones_are_not() -> None:
    enabled_blob = [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    task_manager_on = [6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    disabled_blob = [3, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]
    payload = {
        "av": [r"%ProgramFiles%\Contoso Antivirus\shield.exe"],
        "keys": {
            "HKCU:\\" + _CV + r"\Run": {
                "Discord": r'"C:\Users\player\AppData\Local\Discord\Update.exe" --processStart Discord.exe',
                "SecurityHealth": r"%windir%\system32\SecurityHealthSystray.exe",
            },
            "HKLM:\\" + _CV + r"\Run": {
                "ContosoTray": r'"C:\Program Files\Contoso Antivirus\tray.exe" /background',
                "RtkAudUService": r'"C:\Windows\System32\RtkAudUService64.exe" -background',
            },
            "HKLM:\\" + _APPROVED + r"\Run": {"RtkAudUService": enabled_blob},
            r"HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run": {
                "Steam": r'"C:\Program Files (x86)\Steam\steam.exe" -silent',
            },
            "HKLM:\\" + _APPROVED + r"\Run32": {"Steam": disabled_blob},
            "HKCU:\\" + _CV + r"\Explorer\Shell Folders": {"Startup": _USER_STARTUP},
            "HKLM:\\" + _APPROVED + r"\StartupFolder": {"Vendor Panel.lnk": task_manager_on},
            "HKCU:\\" + _APPROVED + r"\StartupFolder": {"Old Thing.lnk": disabled_blob},
        },
        "folders": {
            _USER_STARTUP: ["Spotify.lnk", "desktop.ini", "Old Thing.lnk"],
            "COMMON": ["Vendor Panel.lnk"],
        },
    }

    value, finding = _startup(payload)

    assert value == "apps_at_startup"
    assert finding["kind"] == "startup_apps"
    # Windows Security's tray and the antivirus product's own entry are never
    # candidates; Steam and "Old Thing" were turned off in Task Manager.
    assert finding["names"] == ["Discord", "RtkAudUService", "Spotify", "Vendor Panel"]
    assert finding["count"] == 4


def test_a_machine_with_nothing_starting_reads_none_with_an_empty_list() -> None:
    value, finding = _startup({"av": [], "keys": {}, "folders": {}})

    assert value == "none_at_startup"
    assert finding["count"] == 0
    assert finding["names"] == []


_MMAGENT_PRELUDE = r"""
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw | ConvertFrom-Json
function Get-MMAgent {
    [CmdletBinding()] param()
    if ($FpsFake.throws) { throw 'The service cannot be started' }
    if ($FpsFake.has_property) { [pscustomobject]@{ MemoryCompression = [bool]$FpsFake.on } }
    else { [pscustomobject]@{ PageCombining = $true } }
}
"""


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ({"has_property": True, "on": True}, "enabled"),
        ({"has_property": True, "on": False}, "disabled"),
        # A property the build does not return is unknown, never "disabled".
        ({"has_property": False}, "not_available"),
        ({"throws": True}, "not_available"),
    ],
)
def test_memory_compression_reads_only_what_mmagent_states(host: dict, expected: str) -> None:
    assert (
        run_shipped_command(_MMAGENT_PRELUDE + MEMORY_COMPRESSION.detect_command, host) == expected
    )
