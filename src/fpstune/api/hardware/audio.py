"""Every audio endpoint, and whether each supports loudness equalisation.

The MMDevices registry is the source, not ``Get-PnpDevice -Status OK``: that view
dropped every disabled endpoint (so a device switched off from the panel could
never be switched back on), and the old walk de-duplicated by friendly name, so
two monitors of the same model showed as one card that toggled whichever came
first. Each endpoint is keyed by its full endpoint id, ``{0.0.0.00000000}.{guid}``
for an output and ``{0.0.1.00000000}.{guid}`` for an input — the id Windows
itself uses, and the one the per-device routes take.
"""

from __future__ import annotations

import json
import logging

from fpstune.api.schemas import AudioDeviceInfo
from fpstune.settings.definitions.audio import (
    _MMDEV_BASE,
    _SYSFX_KEY,
    FX_HELPERS,
)
from fpstune.utils.debug import debug_log
from fpstune.utils.powershell import run_powershell

logger = logging.getLogger(__name__)

# DeviceState: 1 active, 2 disabled, 4 not present, 8 unplugged. Active and
# disabled are the ones a user can act on; the other two are hardware that is
# not there.
#
# The friendly name is built the way Windows builds it, "<description>
# (<interface name>)", from PKEY_Device_DeviceDesc and
# PKEY_DeviceInterface_FriendlyName — both stored on the endpoint, both in the
# system language, so nothing here parses them.
#
# The default device: the audio service stamps "Role:0" (eConsole) on the
# endpoint it last made the default, as a SYSTEMTIME. The newest stamp among the
# active endpoints of a flow is that flow's default. An endpoint with no stamp is
# simply not marked; nothing is guessed.
_AUDIO_SCRIPT = (
    FX_HELPERS
    + f"$base = '{_MMDEV_BASE}'; $sysfxKey = '{_SYSFX_KEY}'; "
    + r"""
$results = @()
foreach ($flow in @('Render', 'Capture')) {
    $flowIndex = if ($flow -eq 'Render') { '0' } else { '1' }
    $defaultId = $null; $defaultStamp = ''
    foreach ($ep in (Get-ChildItem "$base\$flow" -EA SilentlyContinue)) {
        $key = Get-ItemProperty $ep.PSPath -EA SilentlyContinue
        $state = $key.DeviceState
        if ($state -ne 1 -and $state -ne 2) { continue }
        $p = Get-ItemProperty (Join-Path $ep.PSPath 'Properties') -EA SilentlyContinue
        $desc = [string]$p.'{a45c254e-df1c-4efd-8020-67d146a850e0},2'
        $iface = [string]$p.'{b3f8fa53-0004-438e-9003-51a46e139bfc},6'
        $name = if ($desc -and $iface) { "$desc ($iface)" } elseif ($desc) { $desc } else { $iface }
        if (-not $name) { continue }
        $id = "{0.0.$flowIndex.00000000}.$($ep.PSChildName)"

        $role = @($key.'Role:0')
        if ($state -eq 1 -and $role.Count -ge 16) {
            $stamp = ''
            foreach ($i in 0, 1, 3, 4, 5, 6, 7) {
                $stamp += '{0:D5}' -f [BitConverter]::ToUInt16([byte[]]$role, $i * 2)
            }
            if ($stamp -gt $defaultStamp) { $defaultStamp = $stamp; $defaultId = $id }
        }

        $leqSupported = $false; $leqEnabled = $false; $effectsOff = $false
        if ($flow -eq 'Render') {
            $fx = Get-ItemProperty (Join-Path $ep.PSPath 'FxProperties') -EA SilentlyContinue
            $leqSupported = Test-FpsMsSysFx $fx
            $effectsOff = ($fx -and $fx.$sysfxKey -eq 1)
            $leqEnabled = $leqSupported -and (Test-FpsLeqOn $fx) -and -not $effectsOff
        }
        $results += [PSCustomObject]@{
            Id = $id
            Name = $name
            DeviceType = if ($flow -eq 'Render') { 'Playback' } else { 'Recording' }
            IsEnabled = ($state -eq 1)
            IsDefault = $false
            LeqSupported = [bool]$leqSupported
            LeqEnabled = [bool]$leqEnabled
        }
    }
    if ($defaultId) {
        foreach ($r in $results) { if ($r.Id -eq $defaultId) { $r.IsDefault = $true } }
    }
}
ConvertTo-Json -InputObject @($results) -Depth 2 -Compress
"""
)


def get_audio_devices() -> list[AudioDeviceInfo]:
    """Every active or disabled audio endpoint, with its loudness-EQ state."""
    debug_log("audio", "get_audio_devices() called")
    success, output = run_powershell(_AUDIO_SCRIPT, component="audio")
    if not success:
        logger.warning("Audio device detection failed: %s", output)
        return []
    if not output or output.strip() in ("", "null", "[]"):
        logger.info("Audio device detection found no endpoints")
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        logger.warning("Audio device detection returned unreadable output: %s", exc)
        return []
    if isinstance(data, dict):
        data = [data]

    devices: list[AudioDeviceInfo] = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("Id"):
            continue
        devices.append(
            AudioDeviceInfo(
                id=str(entry["Id"]),
                name=str(entry.get("Name") or "Unknown"),
                device_type=str(entry.get("DeviceType", "Playback")),
                is_enabled=bool(entry.get("IsEnabled", True)),
                is_default=bool(entry.get("IsDefault", False)),
                loudness_eq_supported=bool(entry.get("LeqSupported", False)),
                loudness_eq_enabled=bool(entry.get("LeqEnabled", False)),
            )
        )
    logger.debug("Detected %d audio endpoints", len(devices))
    return devices
