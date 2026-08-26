"""Active audio endpoints and whether each supports loudness equalisation.

PnpDevice is the source of truth for what is active; the MMDevices GUID carried
in the endpoint's own ``InstanceId`` is the key the LEQ toggle API takes, so no
lookup table between the two is needed or kept.
"""

from __future__ import annotations

import json
import logging

from fpstune.api.schemas import AudioDeviceInfo
from fpstune.utils.debug import debug_log
from fpstune.utils.powershell import run_powershell

logger = logging.getLogger(__name__)

# Use PnpDevice as source of truth for ACTIVE devices (Status=OK)
# Then match with MMDevices registry for LEQ detection
_AUDIO_SCRIPT = """
    $results = @()
    $lb = [char]123  # {
    $rb = [char]125  # }

    # LEQ property GUID in FxProperties
    $leqPropGuid = "${lb}fc52a749-4be9-4510-896e-966ba6525980${rb},3"

    $mmBase = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio'

    # Get ONLY active audio endpoints from PnpDevice (Status=OK)
    $activeEndpoints = Get-PnpDevice -Class AudioEndpoint -Status OK -EA SilentlyContinue

    # PnpDevice InstanceId format: SWD\\MMDEVAPI\\{0.0.0.00000000}.{GUID}
    # The trailing {GUID} is the exact MMDevices registry key name — no lookup table needed.
    $seenNames = @{}
    foreach ($endpoint in $activeEndpoints) {
        $name = $endpoint.FriendlyName
        if (-not $name -or $seenNames.ContainsKey($name)) { continue }
        $seenNames[$name] = $true

        # Extract MMDevices GUID from InstanceId
        $mmGuid = $null
        if ($endpoint.InstanceId -match '\\.\\{([^}]+)\\}$') {
            $mmGuid = "{$($Matches[1])}"
        }

        # Determine Render vs Capture from InstanceId prefix (0.0.0 = Render, 0.0.1 = Capture)
        $isRender = $endpoint.InstanceId -match '0\\.0\\.0\\.'
        $devType = if ($isRender) { 'Playback' } else { 'Recording' }

        $deviceId = $endpoint.InstanceId
        $leqSupported = $false
        $leqEnabled = $false

        if ($mmGuid) {
            $subDir = if ($isRender) { 'Render' } else { 'Capture' }
            $mmKeyPath = "$mmBase\\$subDir\\$mmGuid"
            $fxPath = "$mmKeyPath\\FxProperties"

            # MMDevices GUID is the canonical device ID for LEQ toggle API
            $deviceId = $mmGuid

            # Check LEQ support and state (Playback only)
            if ($isRender -and (Test-Path $fxPath)) {
                try {
                    $leqValue = Get-ItemPropertyValue -Path $fxPath -Name $leqPropGuid -EA Stop
                    $leqSupported = $true
                    # Bytes 8-9: 0xff,0xff = enabled; 0x00,0x00 = disabled
                    if ($leqValue -is [byte[]] -and $leqValue.Length -ge 10) {
                        $leqEnabled = ($leqValue[8] -eq 0xff -and $leqValue[9] -eq 0xff)
                    }
                } catch {
                    # LEQ property not yet written — device has FxProperties so it supports effects
                    $leqSupported = (Test-Path $fxPath)
                }
            }
        }

        $results += [PSCustomObject]@{
            Id = $deviceId
            Name = $name
            DeviceType = $devType
            IsEnabled = $true
            IsDefault = $false
            LeqSupported = $leqSupported
            LeqEnabled = $leqEnabled
        }
    }

    $results | ConvertTo-Json -Depth 2
    """


def get_audio_devices() -> list[AudioDeviceInfo]:
    """Get audio playback and capture devices with volume normalization support."""
    devices: list[AudioDeviceInfo] = []
    debug_log("audio", "get_audio_devices() called")

    success, output = run_powershell(_AUDIO_SCRIPT, timeout=15, component="audio")
    debug_log(
        "audio", f"Audio device PS success={success}, output_len={len(output) if output else 0}"
    )
    debug_log("audio", f"Audio device PS output: {output[:1000] if output else '(empty)'}")

    if not success:
        logger.warning(f"Audio device detection failed: {output}")
        debug_log(
            "audio", f"PROBLEM: Audio device PS failed: {output[:500] if output else 'no output'}"
        )
        return devices

    if not output or output.strip() in ("", "null", "[]"):
        logger.warning("Audio device detection returned empty output")
        debug_log("audio", "PROBLEM: Audio device PS returned empty output")
        return devices

    try:
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse audio JSON: {e}")
        return devices

    for dev_data in data:
        if not dev_data:
            continue

        devices.append(
            AudioDeviceInfo(
                id=str(dev_data.get("Id", "")),
                name=str(dev_data.get("Name", "Unknown")),
                device_type=str(dev_data.get("DeviceType", "Playback")),
                is_enabled=bool(dev_data.get("IsEnabled", True)),
                is_default=bool(dev_data.get("IsDefault", False)),
                loudness_eq_supported=bool(dev_data.get("LeqSupported", False)),
                loudness_eq_enabled=bool(dev_data.get("LeqEnabled", False)),
            )
        )

    logger.debug(f"Detected {len(devices)} audio devices")
    return devices
