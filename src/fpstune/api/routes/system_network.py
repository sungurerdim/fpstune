"""Network adapter management API routes (split from routes/system.py)."""

from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fpstune.api.hardware import get_detailed_network_adapters
from fpstune.api.routes.system_common import (
    _escape_ps_string,
    _run_powershell_async,
)
from fpstune.api.schemas import NetworkAdapterInfo
from fpstune.utils.admin import is_admin
from fpstune.utils.debug import debug_log
from fpstune.utils.hardware_manager import hardware_manager
from fpstune.utils.logger import activity_log

router = APIRouter()


class NetworkRefreshResponse(BaseModel):
    """Response for network adapters refresh."""

    success: bool
    network_adapters: list[NetworkAdapterInfo]


@router.post("/network/refresh", response_model=NetworkRefreshResponse)
async def refresh_network_adapters() -> NetworkRefreshResponse:
    """Refresh only network adapter detection.

    Fast endpoint (~500ms) that only refreshes network adapters
    without touching monitors, GPU, or other hardware.

    Returns:
        NetworkRefreshResponse with updated adapter list.
    """

    debug_log("network", "API: /network/refresh called (granular refresh)")

    # Invalidate just network cache
    hardware_manager.invalidate_cache("network_adapters")

    try:
        adapters = await asyncio.to_thread(get_detailed_network_adapters)
        hardware_manager.set_network_adapters(adapters)
        return NetworkRefreshResponse(success=True, network_adapters=adapters)
    except Exception as e:
        logging.getLogger(__name__).warning("Network refresh failed: %s", e)
        return NetworkRefreshResponse(success=False, network_adapters=[])


@router.post("/network/adapter/{action}")
async def toggle_network_adapter(
    action: str,
    instance_id: str | None = None,
    interface_index: int | None = None,
) -> dict[str, bool | str]:
    """Enable or disable a network adapter using system identifiers.

    Args:
        action: Either 'enable' or 'disable'.
        instance_id: PnpDevice InstanceId (preferred, works for all adapters).
        interface_index: NetAdapter InterfaceIndex (only works for active adapters).

    Returns:
        Dict with success status and message.
    """
    if action not in ("enable", "disable"):
        raise HTTPException(status_code=400, detail="Action must be 'enable' or 'disable'")

    if not instance_id and interface_index is None:
        raise HTTPException(
            status_code=400,
            detail="Either instance_id or interface_index must be provided",
        )

    if not is_admin():
        raise HTTPException(status_code=403, detail="Administrator privileges required")

    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    logger = logging.getLogger(__name__)

    debug_log(
        "network",
        f"toggle_adapter called: action={action}, instance_id={instance_id}, interface_index={interface_index}",
    )

    # SAFE APPROACH: Use NetAdapter cmdlets first (doesn't hide device)
    # Only fall back to PnpDevice for already-hidden devices
    if instance_id:
        safe_id = _escape_ps_string(instance_id)
        debug_log("network", f"toggle_adapter: action={action}, instance_id={safe_id}")

        # Strategy:
        # 1. Try NetAdapter (safe - just disables networking, doesn't hide device)
        # 2. Only use PnpDevice for enable if device is already hidden/phantom
        ps_command = f"""
        $instanceId = '{safe_id}'
        $action = '{action}'
        $success = $false
        $lastError = ''

        # Method 1: Find adapter by matching PnpDevice to NetAdapter (SAFE)
        try {{
            # Get PnpDevice info
            $pnp = Get-PnpDevice -InstanceId $instanceId -ErrorAction SilentlyContinue
            if ($pnp) {{
                # Find matching NetAdapter by PnpDeviceID (most reliable match)
                $adapter = Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue |
                    Where-Object {{ $_.PnpDeviceID -eq $instanceId }}

                if ($adapter) {{
                    if ($action -eq 'enable') {{
                        Enable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
                    }} else {{
                        Disable-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
                    }}

                    # Poll WMI for actual hardware state (NetAdapter returns cached state)
                    $adapterName = $adapter.Name
                    $expectedState = ($action -eq 'enable')
                    $timeout = 5
                    $elapsed = 0
                    $verified = $false

                    do {{
                        Start-Sleep -Milliseconds 200
                        $wmiAdapter = Get-CimInstance Win32_NetworkAdapter |
                            Where-Object {{ $_.NetConnectionID -eq $adapterName }}
                        $elapsed += 0.2

                        if ($wmiAdapter) {{
                            $currentState = $wmiAdapter.NetEnabled
                            if ($currentState -eq $expectedState) {{
                                $verified = $true
                            }}
                        }}
                    }} while (-not $verified -and $elapsed -lt $timeout)

                    if ($verified) {{
                        $success = $true
                    }} else {{
                        $lastError = "State change timeout - adapter may not have changed"
                    }}
                }} else {{
                    $lastError = "No matching NetAdapter found"
                }}
            }} else {{
                $lastError = "PnpDevice not found"
            }}
        }} catch {{
            $lastError = $_.Exception.Message
        }}

        # Method 2: PnpDevice cmdlet (ONLY for enable - to unhide phantom devices)
        # WARNING: Disable-PnpDevice hides the device, so we only use Enable-PnpDevice
        if (-not $success -and $action -eq 'enable') {{
            try {{
                Enable-PnpDevice -InstanceId $instanceId -Confirm:$false -ErrorAction Stop

                # Poll PnpDevice status for phantom devices (WMI may not have them yet)
                $timeout = 5
                $elapsed = 0
                $verified = $false

                do {{
                    Start-Sleep -Milliseconds 200
                    $pnpStatus = (Get-PnpDevice -InstanceId $instanceId -ErrorAction SilentlyContinue).Status
                    $elapsed += 0.2
                    if ($pnpStatus -eq 'OK') {{
                        $verified = $true
                    }}
                }} while (-not $verified -and $elapsed -lt $timeout)

                if ($verified) {{
                    $success = $true
                }} else {{
                    $lastError = "PnpDevice enable timeout"
                }}
            }} catch {{
                $lastError = $_.Exception.Message
            }}
        }}

        # For disable: If NetAdapter failed, report error (don't use PnpDevice)
        if (-not $success -and $action -eq 'disable') {{
            $lastError = "Cannot disable: NetAdapter method failed. Device may already be disabled."
        }}

        if ($success) {{
            Write-Output 'OK'
        }} else {{
            Write-Output "ERROR: $lastError"
        }}
        """
        identifier = instance_id
    else:
        # Use InterfaceIndex with NetAdapter (only for active adapters).
        # Coerce explicitly to int so the value reaching the PS command is always
        # a bare integer, never an attacker-influenced token (SEC-14).
        try:
            safe_index = int(interface_index)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail="interface_index must be an integer"
            ) from None
        ps_action = "Enable-NetAdapter" if action == "enable" else "Disable-NetAdapter"
        expected_state = "true" if action == "enable" else "false"
        ps_command = f"""
        try {{
            $adapter = Get-NetAdapter -InterfaceIndex {safe_index} -ErrorAction Stop
            {ps_action} -InterfaceIndex {safe_index} -Confirm:$false -ErrorAction Stop

            # Poll WMI for actual hardware state
            $adapterName = $adapter.Name
            $expectedState = ${expected_state}
            $timeout = 5
            $elapsed = 0
            $verified = $false

            do {{
                Start-Sleep -Milliseconds 200
                $wmiAdapter = Get-CimInstance Win32_NetworkAdapter |
                    Where-Object {{ $_.NetConnectionID -eq $adapterName }}
                $elapsed += 0.2

                if ($wmiAdapter) {{
                    $currentState = $wmiAdapter.NetEnabled
                    if ($currentState -eq $expectedState) {{
                        $verified = $true
                    }}
                }}
            }} while (-not $verified -and $elapsed -lt $timeout)

            if ($verified) {{
                Write-Output 'OK'
            }} else {{
                Write-Output "ERROR: State change timeout after $($elapsed)s"
            }}
        }} catch {{
            Write-Output "ERROR: $($_.Exception.Message)"
        }}
        """
        identifier = f"index:{safe_index}"

    success, output = await _run_powershell_async(ps_command, component="network", timeout=30)
    debug_log("network", f"toggle_adapter PS result: success={success}, output='{output}'")

    if not success:
        logger.warning(f"PowerShell failed for adapter '{identifier}': {output}")
        debug_log("network", f"PROBLEM: toggle_adapter PS failed: {output}")
        raise HTTPException(status_code=500, detail=f"PowerShell error: {output}")

    # Get the last non-empty line (the actual result, ignoring DEBUG lines)
    lines = [
        line.strip()
        for line in output.strip().split("\n")
        if line.strip() and not line.strip().startswith("DEBUG:")
    ]
    result = lines[-1] if lines else output.strip()
    debug_log("network", f"toggle_adapter result line: '{result}'")

    if result == "OK":
        activity_log.log(f"Network adapter {action}d", level="info")
        return {
            "success": True,
            "enabled": action == "enable",
            "message": f"Adapter {action}d successfully",
        }
    elif result.startswith("ERROR:"):
        error_msg = result[6:].strip()
        logger.warning(f"Failed to {action} adapter '{identifier}': {error_msg}")
        debug_log("network", f"PROBLEM: toggle_adapter error: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
    else:
        logger.warning(f"Unexpected output for adapter '{identifier}': {result}")
        debug_log("network", f"PROBLEM: Unexpected toggle_adapter result: {result}")
        raise HTTPException(status_code=500, detail=f"Unexpected response: {output}")


@router.post("/network/adapter/{adapter_name}/connection/{action}")
async def toggle_network_connection(adapter_name: str, action: str) -> dict[str, bool | str]:
    """Connect or disconnect a network adapter without disabling the hardware.

    For WiFi: Disconnects from current network or reconnects to last profile.
    For Ethernet: Releases or renews DHCP lease.

    Args:
        adapter_name: Name of the network adapter.
        action: Either 'connect' or 'disconnect'.

    Returns:
        Dict with success status, connection state, and adapter info.
    """
    if action not in ("connect", "disconnect"):
        raise HTTPException(status_code=400, detail="Action must be 'connect' or 'disconnect'")

    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Only available on Windows")

    logger = logging.getLogger(__name__)

    # Escape adapter name for PowerShell/netsh
    safe_name = _escape_ps_string(adapter_name)

    # First, detect if this is a WiFi or Ethernet adapter
    detect_cmd = f"""
    $adapter = Get-NetAdapter -Name '{safe_name}' -ErrorAction SilentlyContinue
    if (-not $adapter) {{ Write-Output 'NOT_FOUND'; exit }}
    if ($adapter.MediaType -like '*802.11*') {{ Write-Output 'WIFI' }}
    else {{ Write-Output 'ETHERNET' }}
    """
    success, output = await _run_powershell_async(detect_cmd)
    adapter_type = output.strip() if success else "ETHERNET"

    if adapter_type == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

    if adapter_type == "WIFI":
        # WiFi: Use netsh wlan disconnect/connect
        if action == "disconnect":
            ps_command = f"""
            try {{
                $result = netsh wlan disconnect interface='{safe_name}' 2>&1
                if ($LASTEXITCODE -eq 0 -or $result -match 'successfully') {{
                    Write-Output 'OK'
                }} else {{
                    Write-Output "ERROR: $result"
                }}
            }} catch {{
                Write-Output "ERROR: $($_.Exception.Message)"
            }}
            """
        else:  # connect
            # Try to reconnect to the last used profile
            ps_command = f"""
            try {{
                # Get the last connected profile for this interface
                $profiles = netsh wlan show profiles interface='{safe_name}' 2>&1
                $lastProfile = ($profiles | Select-String 'All User Profile\\s+:\\s+(.+)' |
                    Select-Object -First 1).Matches.Groups[1].Value.Trim()

                if ($lastProfile) {{
                    $result = netsh wlan connect interface='{safe_name}' name="$lastProfile" 2>&1
                    if ($LASTEXITCODE -eq 0 -or $result -match 'successfully') {{
                        Write-Output "OK:$lastProfile"
                    }} else {{
                        Write-Output "ERROR: $result"
                    }}
                }} else {{
                    Write-Output 'ERROR: No saved WiFi profiles found'
                }}
            }} catch {{
                Write-Output "ERROR: $($_.Exception.Message)"
            }}
            """
    else:
        # Ethernet: Use ipconfig /release and /renew
        if action == "disconnect":
            ps_command = f"""
            try {{
                $result = ipconfig /release '{safe_name}' 2>&1
                # Release might fail if already disconnected, that's OK
                Write-Output 'OK'
            }} catch {{
                Write-Output "ERROR: $($_.Exception.Message)"
            }}
            """
        else:  # connect
            ps_command = f"""
            try {{
                $result = ipconfig /renew '{safe_name}' 2>&1
                if ($result -match 'error|failed') {{
                    Write-Output "ERROR: $result"
                }} else {{
                    Write-Output 'OK'
                }}
            }} catch {{
                Write-Output "ERROR: $($_.Exception.Message)"
            }}
            """

    success, output = await _run_powershell_async(ps_command, timeout=30)

    if not success:
        logger.warning(f"PowerShell failed for connection toggle '{adapter_name}': {output}")
        raise HTTPException(status_code=500, detail=f"PowerShell error: {output}")

    output = output.strip()

    if output.startswith("OK"):
        # Extract profile name if present (for WiFi connect)
        profile_name = None
        if ":" in output:
            profile_name = output.split(":", 1)[1]

        is_connected = action == "connect"
        msg = (
            f"{'Connected to ' + profile_name if profile_name else 'Connected'}"
            if is_connected
            else "Disconnected"
        )

        activity_log.log(f"Network adapter '{adapter_name}' {msg.lower()}", level="info")
        return {
            "success": True,
            "adapter_name": adapter_name,
            "adapter_type": adapter_type.lower(),
            "is_connected": is_connected,
            "profile": profile_name or "",
            "message": f"Adapter '{adapter_name}' {msg.lower()}",
        }
    elif output.startswith("ERROR:"):
        error_msg = output[6:].strip()
        logger.warning(f"Failed to {action} adapter '{adapter_name}': {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
    else:
        logger.warning(f"Unexpected output for adapter '{adapter_name}': {output}")
        raise HTTPException(status_code=500, detail=f"Unexpected response: {output}")
