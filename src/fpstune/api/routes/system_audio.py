"""Audio device management API routes (split from routes/system.py)."""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fpstune.api.hardware import get_audio_devices
from fpstune.api.routes.system_common import (
    _escape_ps_string,
    _run_powershell_async,
)
from fpstune.api.schemas import AudioDeviceInfo
from fpstune.utils.debug import debug_log
from fpstune.utils.hardware_manager import hardware_manager
from fpstune.utils.logger import activity_log

router = APIRouter()


class AudioRefreshResponse(BaseModel):
    """Response for audio devices refresh."""

    success: bool
    audio_devices: list[AudioDeviceInfo]


@router.post("/audio/refresh", response_model=AudioRefreshResponse)
async def refresh_audio_devices() -> AudioRefreshResponse:
    """Refresh only audio device detection.

    Fast endpoint (~300ms) that only refreshes audio devices
    without touching monitors, GPU, or other hardware.

    Returns:
        AudioRefreshResponse with updated device list.
    """

    debug_log("audio", "API: /audio/refresh called (granular refresh)")

    # Invalidate just audio cache
    hardware_manager.invalidate_cache("audio_devices")

    try:
        devices = await asyncio.to_thread(get_audio_devices)
        hardware_manager.set_audio_devices(devices)
        return AudioRefreshResponse(success=True, audio_devices=devices)
    except Exception as e:
        logging.getLogger(__name__).warning("Audio refresh failed: %s", e)
        return AudioRefreshResponse(success=False, audio_devices=[])


@router.post("/audio/device/{device_id}/loudness-eq")
async def toggle_loudness_eq(device_id: str, enabled: bool) -> dict[str, bool | str]:
    """Toggle loudness equalization for an audio device.

    Args:
        device_id: Device GUID from registry
        enabled: True to enable, False to disable

    Returns:
        Dict with success status and new state.
    """

    logger = logging.getLogger(__name__)
    debug_log("audio", f"toggle_loudness_eq called: device_id={device_id}, enabled={enabled}")

    # Validate device_id is a valid GUID format
    guid_pattern = (
        r"^[{]?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}[}]?$"
    )
    if not re.match(guid_pattern, device_id):
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    # Escape device_id for PowerShell (though GUID format should be safe)
    safe_device_id = _escape_ps_string(device_id)

    # Byte values from https://github.com/Falcosc/enable-loudness-equalisation:
    # Enabled:  0b,00,00,00,01,00,00,00,ff,ff,00,00 (12 bytes) - bytes 8-9 = ff,ff
    # Disabled: 0b,00,00,00,01,00,00,00,00,00,00,00 (12 bytes) - bytes 8-9 = 00,00
    # .NET byte array format for Methods 1 & 2
    dotnet_bytes = (
        "0x0b,0x00,0x00,0x00,0x01,0x00,0x00,0x00,0xff,0xff,0x00,0x00"
        if enabled
        else "0x0b,0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00"
    )
    # .reg file hex format for Method 3 (regedit /s)
    reg_hex = (
        "hex:0b,00,00,00,01,00,00,00,ff,ff,00,00"
        if enabled
        else "hex:0b,00,00,00,01,00,00,00,00,00,00,00"
    )

    # Strategy:
    # 1. .NET Registry direct write (more reliable than reg.exe for protected keys)
    # 2. .NET Registry + explicit ACL takeover (handles SYSTEM/AudioEndpointBuilder owned keys)
    # 3. regedit.exe /s fallback (Falcosc method - highest registry write privilege)
    ps_command = f"""
    $deviceId = '{safe_device_id}'
    $propName = '{{fc52a749-4be9-4510-896e-966ba6525980}},3'
    $dotnetBytes = [byte[]]@({dotnet_bytes})
    $regHex = '{reg_hex}'


    # Find the device in Render or Capture
    $basePath = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio'
    $fxPathReg = $null
    $foundIn = $null

    foreach ($devType in @('Render', 'Capture')) {{
        $testPath = "$basePath\\$devType\\$deviceId\\FxProperties"
        if (Test-Path $testPath) {{
            $fxPathReg = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\$devType\\$deviceId\\FxProperties"
            $foundIn = $devType
            break
        }}
    }}

    if (-not $fxPathReg) {{
        Write-Output "NOT_FOUND:$deviceId"
        exit
    }}

    # Check if device has enhancement support
    $fxProps = Get-ItemProperty -Path "HKLM:\\$fxPathReg" -EA SilentlyContinue
    if (-not $fxProps -or -not ($fxProps.PSObject.Properties.Name -join ',' | Select-String 'd04e05a6')) {{
        Write-Output 'NOT_SUPPORTED'
        exit
    }}

    # Method 1: .NET Registry direct write (more reliable than reg.exe for protected keys)
    $m1Success = $false
    try {{
        $key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($fxPathReg, $true)
        if ($key) {{
            $key.SetValue($propName, $dotnetBytes, [Microsoft.Win32.RegistryValueKind]::Binary)
            $key.Close()
            $m1Success = $true
        }}
    }} catch {{
    }}

    if ($m1Success) {{
        Restart-Service -Name 'AudioEndpointBuilder' -Force -EA SilentlyContinue
        Start-Sleep -Milliseconds 500
        Write-Output 'OK'
        exit
    }}

    # Method 2: .NET Registry + explicit ACL takeover
    $originalOwner = $null
    $m2Success = $false

    try {{
        # Check current owner first using Get-Acl
        $aclCheck = Get-Acl "HKLM:\\$fxPathReg" -EA Stop
        $originalOwner = $aclCheck.Owner

        if ($originalOwner -like '*TrustedInstaller*') {{
            Write-Output "TRUSTEDINSTALLER:Manual configuration required for this device"
            exit
        }}

        $adminSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
        $adminAccount = $adminSid.Translate([System.Security.Principal.NTAccount])

        # Open key with TakeOwnership + ChangePermissions rights via .NET API
        $takeOwnershipKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
            $fxPathReg,
            [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
            [System.Security.AccessControl.RegistryRights]::TakeOwnership -bor
            [System.Security.AccessControl.RegistryRights]::ChangePermissions
        )

        if ($takeOwnershipKey) {{
            # Take ownership
            $acl = $takeOwnershipKey.GetAccessControl([System.Security.AccessControl.AccessControlSections]::Owner)
            $acl.SetOwner($adminAccount)
            $takeOwnershipKey.SetAccessControl($acl)

            # Grant FullControl
            $acl2 = $takeOwnershipKey.GetAccessControl()
            $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
                $adminAccount,
                [System.Security.AccessControl.RegistryRights]::FullControl,
                [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',
                [System.Security.AccessControl.PropagationFlags]::None,
                [System.Security.AccessControl.AccessControlType]::Allow
            )
            $acl2.AddAccessRule($rule)
            $takeOwnershipKey.SetAccessControl($acl2)
            $takeOwnershipKey.Close()

            # Now write with full access
            $writeKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($fxPathReg, $true)
            if ($writeKey) {{
                $writeKey.SetValue($propName, $dotnetBytes, [Microsoft.Win32.RegistryValueKind]::Binary)
                $writeKey.Close()
                $m2Success = $true
            }}
        }}
    }} catch {{
    }}

    # Restore original owner (best effort)
    if ($originalOwner) {{
        try {{
            $restoreKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
                $fxPathReg,
                [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
                [System.Security.AccessControl.RegistryRights]::TakeOwnership
            )
            if ($restoreKey) {{
                $restoreAcl = $restoreKey.GetAccessControl([System.Security.AccessControl.AccessControlSections]::Owner)
                $restoreAcl.SetOwner((New-Object System.Security.Principal.NTAccount($originalOwner)))
                $restoreKey.SetAccessControl($restoreAcl)
                $restoreKey.Close()
            }}
        }} catch {{ }}
    }}

    if ($m2Success) {{
        Restart-Service -Name 'AudioEndpointBuilder' -Force -EA SilentlyContinue
        Start-Sleep -Milliseconds 500
        Write-Output 'OK'
        exit
    }}

    # Method 3: regedit.exe /s fallback (Falcosc method - highest registry write privilege)
    $m3Success = $false
    $regFile = "$env:TEMP\\fpstune_leq_{safe_device_id}.reg"
    try {{
        $regContent = "Windows Registry Editor Version 5.00`r`n`r`n[HKEY_LOCAL_MACHINE\\$fxPathReg]`r`n`"$propName`"=$regHex`r`n"
        $regContent | Out-File -FilePath $regFile -Encoding ASCII -Force
        $proc = Start-Process regedit.exe -ArgumentList '/s', $regFile -Wait -NoNewWindow -PassThru
        $m3Success = ($proc.ExitCode -eq 0)
    }} catch {{
    }} finally {{
        Remove-Item $regFile -Force -EA SilentlyContinue
    }}

    if ($m3Success) {{
        Restart-Service -Name 'AudioEndpointBuilder' -Force -EA SilentlyContinue
        Start-Sleep -Milliseconds 500
        Write-Output 'OK'
    }} else {{
        Write-Output "ERROR: Registry write failed after all methods (direct .NET, ACL takeover, regedit)"
    }}
    """

    success, output = await _run_powershell_async(ps_command, component="audio")
    debug_log("audio", f"LEQ toggle PS success={success}, output='{output}'")

    if not success:
        logger.warning(f"Failed to toggle loudness EQ for {device_id}: {output}")
        debug_log("audio", f"PROBLEM: LEQ toggle PS failed: {output}")
        raise HTTPException(status_code=500, detail="PowerShell command failed")

    # Get the last non-empty line (the actual result, ignoring DEBUG lines)
    lines = [
        line.strip()
        for line in output.strip().split("\n")
        if line.strip() and not line.strip().startswith("DEBUG:")
    ]
    result = lines[-1] if lines else output.strip()
    debug_log("audio", f"LEQ toggle result line: '{result}'")

    if result == "NOT_SUPPORTED":
        debug_log("audio", f"PROBLEM: Device {device_id} does not support LEQ")
        raise HTTPException(status_code=400, detail="Device does not support loudness equalization")

    if "NOT_FOUND" in result:
        debug_log("audio", f"PROBLEM: Device {device_id} not found in registry")
        raise HTTPException(status_code=404, detail=f"Device not found: {result}")

    if result.startswith("TRUSTEDINSTALLER:"):
        # TrustedInstaller protected - tell user to configure manually
        msg = result.split(":", 1)[1] if ":" in result else "Manual configuration required"
        debug_log("audio", f"LEQ: TrustedInstaller protected device {device_id}")
        raise HTTPException(
            status_code=403,
            detail=f"This audio device is protected by Windows. {msg}. "
            "Use Sound settings > Device properties > Enhancements to configure LEQ manually.",
        )

    if result.startswith("ERROR:") or "ERROR:" in result:
        debug_log("audio", f"PROBLEM: LEQ toggle error: {result}")
        raise HTTPException(status_code=500, detail=result)

    if result != "OK":
        debug_log("audio", f"PROBLEM: Unexpected LEQ result: {result}")
        raise HTTPException(status_code=500, detail=f"Unexpected result: {result}")

    debug_log("audio", f"LEQ toggle success for device {device_id}")
    logger.info(f"Loudness EQ {'enabled' if enabled else 'disabled'} for device {device_id}")
    activity_log.log(
        f"Volume normalization {'enabled' if enabled else 'disabled'} for audio device",
        level="info",
    )

    return {
        "success": True,
        "device_id": device_id,
        "enabled": enabled,
        "message": f"Volume normalization {'enabled' if enabled else 'disabled'}",
    }


@router.post("/audio/device/{device_id}/enabled")
async def toggle_audio_device(device_id: str, enabled: bool) -> dict[str, bool | str]:
    """Enable or disable an audio device.

    Args:
        device_id: Device instance ID from PnpDevice
        enabled: True to enable, False to disable

    Returns:
        Dict with success status and new state.
    """
    logger = logging.getLogger(__name__)

    # Sanitize device_id to prevent injection
    if not device_id or len(device_id) > 500:
        raise HTTPException(status_code=400, detail="Invalid device ID")

    # Escape device_id for PowerShell single-quoted string
    safe_device_id = _escape_ps_string(device_id)

    action = "Enable" if enabled else "Disable"
    # PowerShell to enable/disable audio endpoint device
    ps_command = f"""
    $deviceId = '{safe_device_id}'
    try {{
        $device = Get-PnpDevice -InstanceId $deviceId -ErrorAction Stop
        {action}-PnpDevice -InstanceId $deviceId -Confirm:$false -ErrorAction Stop
        Write-Output 'OK'
    }} catch {{
        Write-Output "ERROR: $($_.Exception.Message)"
    }}
    """

    success, output = await _run_powershell_async(ps_command)

    if not success:
        logger.warning(f"Failed to {action.lower()} audio device {device_id}: {output}")
        raise HTTPException(status_code=500, detail="PowerShell command failed")

    output = output.strip()
    if output.startswith("ERROR:"):
        raise HTTPException(status_code=500, detail=output)

    logger.info(f"Audio device {action.lower()}d: {device_id}")
    activity_log.log(f"Audio device {action.lower()}d", level="info")

    return {
        "success": True,
        "device_id": device_id,
        "enabled": enabled,
        "message": f"Audio device {action.lower()}d",
    }
