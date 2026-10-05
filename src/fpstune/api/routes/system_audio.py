"""Audio device management API routes (split from routes/system.py)."""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fpstune.api.hardware import get_audio_devices
from fpstune.api.routes.system_common import _run_powershell_async
from fpstune.api.schemas import AudioDeviceInfo
from fpstune.settings.definitions.audio import (
    _MIN_RIGHTS_WRITER,
    _MMDEV_SUBKEY,
    _SYSFX_KEY,
    FX_HELPERS,
)
from fpstune.utils.debug import debug_log
from fpstune.utils.hardware_manager import hardware_manager
from fpstune.utils.logger import log_activity

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


# The endpoint ids detection hands out. Matching the whole shape is the injection
# defence for both routes below: a value that passes contains nothing but hex,
# dots, dashes and braces, so it cannot leave a PowerShell string literal.
_ENDPOINT_ID = re.compile(
    r"\{0\.0\.(?P<flow>[01])\.00000000\}\."
    r"(?P<guid>\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\})"
)


def _parse_endpoint_id(device_id: str) -> re.Match[str]:
    match = _ENDPOINT_ID.fullmatch(device_id)
    if match is None:
        raise HTTPException(status_code=400, detail="Invalid audio endpoint id")
    return match


def _last_line(output: str) -> str:
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


@router.post("/audio/device/{device_id}/loudness-eq")
async def toggle_loudness_eq(device_id: str, enabled: bool) -> dict[str, bool | str]:
    """Switch Loudness Equalization on one output, and prove it held.

    The write is the same minimal-rights open the per-output effects setting uses
    — no ownership change, no ACL edit, no .reg import and no restart of the audio
    service, all of which an earlier version did. A stream that is already playing
    keeps the chain it opened with; the next stream gets the new state.

    Turning it on also clears Disable_SysFx on that output, because Loudness
    Equalization is one of the effects that switch governs: "on" with every effect
    disabled is a state Windows reports and never plays.
    """
    logger = logging.getLogger(__name__)
    match = _parse_endpoint_id(device_id)
    if match["flow"] != "0":
        raise HTTPException(status_code=400, detail="Loudness equalization applies to outputs only")

    flag = "0xff,0xff" if enabled else "0x00,0x00"
    ps_command = (
        FX_HELPERS
        + _MIN_RIGHTS_WRITER
        + f"$sub = '{_MMDEV_SUBKEY}\\Render\\{match['guid']}'; "
        + f"$sysfxKey = '{_SYSFX_KEY}'; $enable = ${'true' if enabled else 'false'}; "
        + f"$blob = [byte[]](0x0b,0x00,0x00,0x00,0x01,0x00,0x00,0x00,{flag},0x00,0x00); "
        + r"""
function Invoke-FpsLoudness {
if (-not (Test-Path "HKLM:\$sub")) { 'NOT_FOUND'; return }
$fxPath = "HKLM:\$sub\FxProperties"
$fx = Get-ItemProperty $fxPath -EA SilentlyContinue
if (-not (Test-FpsMsSysFx $fx)) { 'NOT_SUPPORTED'; return }
if (-not (Set-FpsEndpointValue "$sub\FxProperties" $fpsLeqKey $blob 'Binary')) {
    'ERROR: Windows refused the write to this output'; return
}
if ($enable -and $fx.$sysfxKey -eq 1) {
    if (-not (Set-FpsEndpointValue "$sub\FxProperties" $sysfxKey 0 'DWord')) {
        'ERROR: Windows refused to switch this output''s effects on'; return
    }
}
$after = Get-ItemProperty $fxPath -EA SilentlyContinue
$on = (Test-FpsLeqOn $after) -and ($after.$sysfxKey -ne 1)
if ($on -eq $enable) { 'OK' } else { 'ERROR: the output did not keep the new state' }
}
Invoke-FpsLoudness
"""
    )

    success, output = await _run_powershell_async(ps_command, component="audio")
    if not success:
        logger.warning("Loudness EQ toggle for %s failed to run: %s", device_id, output)
        raise HTTPException(status_code=500, detail="PowerShell command failed")

    result = _last_line(output)
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Audio output not found")
    if result == "NOT_SUPPORTED":
        raise HTTPException(
            status_code=400,
            detail="This output has no Windows loudness equalization: its driver does not "
            "load Microsoft's system effects",
        )
    if result.startswith("ERROR:"):
        raise HTTPException(status_code=500, detail=result.removeprefix("ERROR:").strip())
    if result != "OK":
        raise HTTPException(status_code=500, detail=f"Unexpected result: {result}")

    state = "enabled" if enabled else "disabled"
    logger.info("Loudness EQ %s for %s", state, device_id)
    log_activity(f"Volume normalization {state} for audio device", level="info")
    return {
        "success": True,
        "device_id": device_id,
        "enabled": enabled,
        "message": f"Volume normalization {state}",
    }


@router.post("/audio/device/{device_id}/enabled")
async def toggle_audio_device(device_id: str, enabled: bool) -> dict[str, bool | str]:
    """Enable or disable one audio endpoint.

    The endpoint's PnP instance id is ``SWD\\MMDEVAPI\\`` plus its endpoint id, so
    the route derives it rather than accepting any instance id — this endpoint can
    therefore switch audio endpoints and nothing else on the machine.
    """
    logger = logging.getLogger(__name__)
    _parse_endpoint_id(device_id)
    instance_id = f"SWD\\MMDEVAPI\\{device_id}"

    action = "Enable" if enabled else "Disable"
    ps_command = (
        f"try {{ {action}-PnpDevice -InstanceId '{instance_id}' -Confirm:$false -EA Stop; "
        "'OK' } catch { 'ERROR: ' + $_.Exception.Message }"
    )
    success, output = await _run_powershell_async(ps_command, component="audio")
    if not success:
        logger.warning("Failed to %s audio device %s: %s", action.lower(), device_id, output)
        raise HTTPException(status_code=500, detail="PowerShell command failed")

    result = _last_line(output)
    if result.startswith("ERROR:"):
        raise HTTPException(status_code=500, detail=result.removeprefix("ERROR:").strip())
    if result != "OK":
        raise HTTPException(status_code=500, detail=f"Unexpected result: {result}")

    logger.info("Audio device %sd: %s", action.lower(), device_id)
    log_activity(f"Audio device {action.lower()}d", level="info")
    return {
        "success": True,
        "device_id": device_id,
        "enabled": enabled,
        "message": f"Audio device {action.lower()}d",
    }
