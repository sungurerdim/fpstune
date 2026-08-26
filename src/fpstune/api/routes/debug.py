"""Debug API routes for fpstune.

Provides endpoints for debugging and diagnostics.
Enable debug mode by setting FPSTUNE_DEBUG=1 environment variable.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from typing import Any

from fastapi import APIRouter, HTTPException

from fpstune.utils.debug import (
    clear_debug_entries,
    get_debug_entries,
    get_debug_status,
    is_debug_enabled,
)
from fpstune.utils.powershell import run_powershell

router = APIRouter(prefix="/api/debug", tags=["debug"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def debug_status() -> dict[str, Any]:
    """Get debug mode status and statistics."""
    return get_debug_status()


@router.get("/entries")
async def debug_entries_list(
    limit: int = 100,
    component: str | None = None,
) -> dict[str, Any]:
    """Get debug log entries.

    Args:
        limit: Maximum number of entries to return.
        component: Filter by component name.

    Returns:
        Dict with entries and metadata.
    """
    entries = get_debug_entries(limit=limit, component=component)
    return {
        "count": len(entries),
        "entries": entries,
        "debug_enabled": is_debug_enabled(),
    }


@router.delete("/entries")
async def debug_entries_clear() -> dict[str, bool]:
    """Clear all debug entries."""
    clear_debug_entries()
    return {"success": True}


@router.get("/diagnose/monitors")
async def diagnose_monitors() -> dict[str, Any]:
    """Run monitor detection diagnostics.

    Returns detailed information about monitor detection process.
    """
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    results: dict[str, Any] = {
        "platform": sys.platform,
        "steps": [],
        "errors": [],
        "monitors": [],
    }

    # Step 1: Check WMI service
    step1_cmd = """
    $service = Get-Service -Name winmgmt -ErrorAction SilentlyContinue
    if ($service) {
        [PSCustomObject]@{
            Name = $service.Name
            Status = $service.Status.ToString()
            StartType = $service.StartType.ToString()
        } | ConvertTo-Json
    } else {
        '{"error": "WMI service not found"}'
    }
    """
    success, output = await asyncio.to_thread(run_powershell, step1_cmd)
    results["steps"].append(
        {
            "name": "WMI Service Check",
            "success": success,
            "output": output[:1000],
        }
    )

    # Step 2: List WMI monitor classes
    step2_cmd = """
    $classes = @()
    try {
        $modes = Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorListedSupportedSourceModes -ErrorAction Stop
        $classes += [PSCustomObject]@{
            ClassName = "WmiMonitorListedSupportedSourceModes"
            Count = @($modes).Count
            Instances = @($modes | ForEach-Object { $_.InstanceName }) -join "; "
        }
    } catch {
        $classes += [PSCustomObject]@{
            ClassName = "WmiMonitorListedSupportedSourceModes"
            Error = $_.Exception.Message
        }
    }
    try {
        $ids = Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorID -ErrorAction Stop
        $classes += [PSCustomObject]@{
            ClassName = "WmiMonitorID"
            Count = @($ids).Count
            Instances = @($ids | ForEach-Object { $_.InstanceName }) -join "; "
        }
    } catch {
        $classes += [PSCustomObject]@{
            ClassName = "WmiMonitorID"
            Error = $_.Exception.Message
        }
    }
    $classes | ConvertTo-Json -Depth 3
    """
    success, output = await asyncio.to_thread(run_powershell, step2_cmd, timeout=30)
    results["steps"].append(
        {
            "name": "WMI Monitor Classes",
            "success": success,
            "output": output[:2000],
        }
    )

    # Step 3: EnumDisplayDevices via C# interop
    step3_cmd = r"""
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public class DisplayDiag {
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern bool EnumDisplayDevices(string lpDevice, uint iDevNum, ref DISPLAY_DEVICE lpDisplayDevice, uint dwFlags);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    public struct DISPLAY_DEVICE {
        public int cb;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string DeviceName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceString;
        public uint StateFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceID;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceKey;
    }

    public const uint DISPLAY_DEVICE_ACTIVE = 0x00000001;
    public const uint DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000002;
    public const uint DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004;

    public static List<object> GetDisplayDevices() {
        var devices = new List<object>();
        DISPLAY_DEVICE dd = new DISPLAY_DEVICE();
        dd.cb = Marshal.SizeOf(dd);

        uint i = 0;
        while (EnumDisplayDevices(null, i, ref dd, 0)) {
            DISPLAY_DEVICE monitor = new DISPLAY_DEVICE();
            monitor.cb = Marshal.SizeOf(monitor);
            uint j = 0;
            var monitors = new List<object>();
            while (EnumDisplayDevices(dd.DeviceName, j, ref monitor, 0)) {
                monitors.Add(new {
                    MonitorName = monitor.DeviceName,
                    MonitorString = monitor.DeviceString,
                    MonitorID = monitor.DeviceID,
                    MonitorFlags = monitor.StateFlags
                });
                j++;
            }
            devices.Add(new {
                AdapterName = dd.DeviceName,
                AdapterString = dd.DeviceString,
                AdapterID = dd.DeviceID,
                Flags = dd.StateFlags,
                IsActive = (dd.StateFlags & DISPLAY_DEVICE_ACTIVE) != 0,
                IsAttached = (dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP) != 0,
                IsPrimary = (dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE) != 0,
                Monitors = monitors
            });
            i++;
        }
        return devices;
    }
}
"@ -ErrorAction SilentlyContinue

try {
    $devices = [DisplayDiag]::GetDisplayDevices()
    $devices | ConvertTo-Json -Depth 4
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
}
    """
    success, output = await asyncio.to_thread(run_powershell, step3_cmd, timeout=30)
    results["steps"].append(
        {
            "name": "EnumDisplayDevices",
            "success": success,
            "output": output[:3000],
        }
    )

    # Step 4: Check for NVIDIA GPU (for G-Sync detection)
    step4_cmd = """
    $nvidia = Get-CimInstance -ClassName Win32_VideoController | Where-Object { $_.Name -like '*NVIDIA*' }
    if ($nvidia) {
        [PSCustomObject]@{
            Name = $nvidia.Name
            DriverVersion = $nvidia.DriverVersion
            Status = $nvidia.Status
        } | ConvertTo-Json
    } else {
        '{"nvidia": false}'
    }
    """
    success, output = await asyncio.to_thread(run_powershell, step4_cmd)
    results["steps"].append(
        {
            "name": "GPU Detection",
            "success": success,
            "output": output[:500],
        }
    )

    return results


@router.get("/diagnose/network")
async def diagnose_network() -> dict[str, Any]:
    """Run network adapter detection diagnostics.

    Returns detailed information about network adapter detection.
    """
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    results: dict[str, Any] = {
        "platform": sys.platform,
        "steps": [],
        "adapters": [],
    }

    # Step 1: Get-NetAdapter output
    step1_cmd = """
    Get-NetAdapter | Select-Object Name, InterfaceIndex, InterfaceDescription, Status, MacAddress, LinkSpeed | ConvertTo-Json -Depth 2
    """
    success, output = await asyncio.to_thread(run_powershell, step1_cmd)
    results["steps"].append(
        {
            "name": "Get-NetAdapter",
            "success": success,
            "output": output[:3000],
        }
    )

    # Step 2: Get-PnpDevice for network adapters
    step2_cmd = """
    Get-PnpDevice -Class Net | Select-Object InstanceId, FriendlyName, Status, Problem, ConfigManagerErrorCode | ConvertTo-Json -Depth 2
    """
    success, output = await asyncio.to_thread(run_powershell, step2_cmd)
    results["steps"].append(
        {
            "name": "Get-PnpDevice (Net class)",
            "success": success,
            "output": output[:3000],
        }
    )

    # Step 3: Check adapter advanced properties (for disabled buttons)
    step3_cmd = """
    $adapters = Get-NetAdapter
    $result = @()
    foreach ($adapter in $adapters) {
        $props = Get-NetAdapterAdvancedProperty -Name $adapter.Name -ErrorAction SilentlyContinue
        $result += [PSCustomObject]@{
            Name = $adapter.Name
            InterfaceIndex = $adapter.InterfaceIndex
            Status = $adapter.Status
            PropertyCount = @($props).Count
            Properties = @($props | Select-Object -First 5 | ForEach-Object { $_.RegistryKeyword })
        }
    }
    $result | ConvertTo-Json -Depth 3
    """
    success, output = await asyncio.to_thread(run_powershell, step3_cmd, timeout=30)
    results["steps"].append(
        {
            "name": "NetAdapter Advanced Properties",
            "success": success,
            "output": output[:3000],
        }
    )

    return results


@router.get("/diagnose/audio")
async def diagnose_audio() -> dict[str, Any]:
    """Run audio device diagnostics.

    Returns detailed information about audio devices and LEQ support.
    """
    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    results: dict[str, Any] = {
        "platform": sys.platform,
        "steps": [],
        "devices": [],
    }

    # Step 1: Get audio devices from registry
    step1_cmd = """
    $devices = @()
    $folders = @(
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render',
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Capture'
    )
    foreach ($folder in $folders) {
        $type = if ($folder -match 'Render') { 'Playback' } else { 'Recording' }
        Get-ChildItem -Path $folder -ErrorAction SilentlyContinue | ForEach-Object {
            $propPath = Join-Path $_.PSPath 'Properties'
            $fxPath = Join-Path $_.PSPath 'FxProperties'
            $props = Get-ItemProperty -Path $propPath -ErrorAction SilentlyContinue
            $fxProps = Get-ItemProperty -Path $fxPath -ErrorAction SilentlyContinue

            $devices += [PSCustomObject]@{
                DeviceId = $_.PSChildName
                Type = $type
                HasFxProperties = (Test-Path $fxPath)
                FxPropertyCount = if ($fxProps) { @($fxProps.PSObject.Properties).Count } else { 0 }
                FxPropertyNames = if ($fxProps) { @($fxProps.PSObject.Properties.Name | Select-Object -First 10) } else { @() }
            }
        }
    }
    $devices | ConvertTo-Json -Depth 3
    """
    success, output = await asyncio.to_thread(run_powershell, step1_cmd, timeout=30)
    results["steps"].append(
        {
            "name": "Audio Device Registry",
            "success": success,
            "output": output[:5000],
        }
    )

    # Step 2: Check LEQ property GUID
    step2_cmd = """
    $propGuid = '{fc52a749-4be9-4510-896e-966ba6525980},3'
    $folders = @(
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render',
        'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Capture'
    )
    $leqDevices = @()
    foreach ($folder in $folders) {
        Get-ChildItem -Path $folder -ErrorAction SilentlyContinue | ForEach-Object {
            $fxPath = Join-Path $_.PSPath 'FxProperties'
            if (Test-Path $fxPath) {
                $fxProps = Get-ItemProperty -Path $fxPath -ErrorAction SilentlyContinue
                $hasLeq = $null -ne $fxProps.$propGuid
                $leqValue = if ($hasLeq) { [BitConverter]::ToString($fxProps.$propGuid) } else { 'N/A' }
                $leqDevices += [PSCustomObject]@{
                    DeviceId = $_.PSChildName
                    FxPath = $fxPath
                    HasLEQ = $hasLeq
                    LEQValue = $leqValue
                }
            }
        }
    }
    $leqDevices | ConvertTo-Json -Depth 2
    """
    success, output = await asyncio.to_thread(run_powershell, step2_cmd)
    results["steps"].append(
        {
            "name": "LEQ Property Check",
            "success": success,
            "output": output[:3000],
        }
    )

    return results


SETTINGS_DIAGNOSTIC_SAMPLE_SIZE = 20


def _collect_settings_diagnostics(results: dict[str, Any]) -> None:
    """Fill ``results`` with registry counts and a sample of live detections.

    Synchronous on purpose: every call in here is a blocking subprocess, so the
    whole body runs in one worker thread rather than each statement fighting the
    event loop from inside an ``async def``.
    """
    from fpstune.api.routes.settings import _get_registry
    from fpstune.settings.detection import DetectionEngine

    # The registry singleton, never a fresh SettingsRegistry(): constructing one
    # re-runs adapter, monitor and game discovery — seconds of PowerShell — for
    # a diagnostic that only wants to read what is already registered.
    registry = _get_registry()
    all_settings = registry.get_all()
    results["settings_count"] = len(all_settings)
    results["categories"] = list(registry.get_categories())

    engine = DetectionEngine()
    sample_settings: list[dict[str, Any]] = []
    for setting in all_settings[:SETTINGS_DIAGNOSTIC_SAMPLE_SIZE]:
        try:
            result = engine.detect_one(setting)
            sample_settings.append(
                {
                    "id": setting.id,
                    "value": str(result.value)[:100] if result.value is not None else None,
                    "is_applicable": result.is_applicable,
                    "reason": result.applicable_reason,
                }
            )
        except Exception as e:
            sample_settings.append(
                {
                    "id": setting.id,
                    "error": str(e)[:200],
                }
            )

    results["sample_settings"] = sample_settings


@router.get("/diagnose/settings")
async def diagnose_settings() -> dict[str, Any]:
    """Run settings system diagnostics.

    Returns information about setting detection and apply mechanisms.
    """
    results: dict[str, Any] = {
        "steps": [],
        "settings_count": 0,
        "categories": [],
    }

    try:
        await asyncio.to_thread(_collect_settings_diagnostics, results)
    except Exception as e:
        results["error"] = str(e)

    return results


# An allowlist of shapes, not a list of forbidden tokens.
#
# The denylist this replaces named `iex`, `&`, `;` and `|`, and a two-statement
# command walked past all four: PowerShell ends a statement at a bare newline,
# and `$( )` runs a subexpression without needing any of them. Every token added
# to such a list is added after someone found the way around the last one, and
# the list can never state what it does allow — which is the whole question for
# a route that runs elevated PowerShell.
#
# So the rule is inverted: the command must be one line, the first token must be
# a read-only verb, and every remaining token must be a parameter name, a plain
# argument or a single-quoted literal (PowerShell interpolates nothing inside
# one). Anything carrying an operator — `;`, `|`, `&`, `$(`, a backtick, a
# double-quoted string — matches no shape here and is refused without needing to
# be enumerated.

# Deliberately the same heads the prefix check already allowed: this change is
# about making the rule expressible, not about widening what it admits.
_READ_ONLY_VERB = re.compile(r"^(?:Get|Test)-[A-Za-z][A-Za-z0-9]*$")
_LITERAL_HEAD = re.compile(r"^(?:Write-Output|\$PSVersionTable(?:\.[A-Za-z][A-Za-z0-9]*)*)$")
# A path (`C:\Windows\System32`), a number, a property name, a cmdlet argument.
_PLAIN_ARGUMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\\/-]*$")
_PARAMETER_NAME = re.compile(r"^-[A-Za-z][A-Za-z0-9]*$")
_SINGLE_QUOTED = re.compile(r"^'[^']*'$")
# Statement separators PowerShell honours that whitespace-splitting would
# otherwise swallow, leaving the second statement looking like an argument.
_LINE_BREAK = re.compile("[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]")


def _reject_unless_read_only(command: str) -> str | None:
    """Return why this command is not an allowed read-only shape, or None.

    Every rejection reads the same to the caller on purpose: the endpoint is a
    diagnostic, and telling an unauthorised caller which half of the rule it
    tripped is free reconnaissance.
    """
    refusal = "Command is not an allowed read-only PowerShell shape"

    if _LINE_BREAK.search(command):
        return refusal

    tokens = [token for token in re.split(r"[ \t]+", command.strip()) if token]
    if not tokens:
        return refusal

    head = tokens[0]
    if not (_READ_ONLY_VERB.match(head) or _LITERAL_HEAD.match(head)):
        return refusal

    for token in tokens[1:]:
        if not (
            _PARAMETER_NAME.match(token)
            or _PLAIN_ARGUMENT.match(token)
            or _SINGLE_QUOTED.match(token)
        ):
            return refusal

    return None


@router.post("/test/powershell")
async def test_powershell(command: str) -> dict[str, Any]:
    """Execute a test PowerShell command (debug mode only).

    This is only available when FPSTUNE_DEBUG=1.
    """
    if not is_debug_enabled():
        raise HTTPException(
            status_code=403,
            detail="Debug mode not enabled. Set FPSTUNE_DEBUG=1 to enable.",
        )

    # Safety check - limit command length
    if len(command) > 5000:
        raise HTTPException(status_code=400, detail="Command too long")

    rejection = _reject_unless_read_only(command)
    if rejection:
        raise HTTPException(status_code=400, detail=rejection)

    success, output = await asyncio.to_thread(run_powershell, command.strip(), timeout=30)
    return {
        "success": success,
        "output": output[:10000],
    }
