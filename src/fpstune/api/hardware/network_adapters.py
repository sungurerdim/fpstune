"""Every network adapter this machine has, including the disabled ones.

Three separable jobs used to be one 398-line function: the inventory script, the
WiFi enrichment script, and the translation of a record into the schema object
the API returns. They are split because each fails differently — the inventory
can come back empty, the WiFi read can fail while the inventory succeeded, and a
single malformed record must not cost the other adapters — and because only the
translation can be exercised without a Windows machine attached.

An adapter is identified by its PnpDevice ``InstanceId`` (C5). ``InterfaceIndex``
travels with it because the netsh and Get-Net* commands take one, but it is never
the identity: it is reassigned when adapters are enabled and disabled.

Nothing in the inventory is matched against a name. ``Get-NetAdapter`` hands over the
adapter's own ``PnPDeviceID``; the WMI and PnP records are joined on that id; and a
device the network stack does not list (disabled in Device Manager) is told Wi-Fi from
Ethernet by the numbers its driver INF declares, not by the words in its FriendlyName,
which a non-English Windows translates.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from fpstune.api.schemas import NetworkAdapterInfo
from fpstune.utils.adapter_filter import PHYSICAL_ADAPTER
from fpstune.utils.debug import debug_log
from fpstune.utils.powershell import run_powershell
from fpstune.utils.winapi import wlan
from fpstune.utils.winapi.wlan import WlanRecord, auth_name, band_ghz, phy_name

logger = logging.getLogger(__name__)

# Get basic adapter info with IP configuration
# Include AdminStatus (enabled/disabled) and MediaConnectState (connected/disconnected)
# Show ALL physical adapters including disabled ones (via PnpDevice fallback)
_ADAPTER_INVENTORY_SCRIPT = """
    $results = @()
    $seenIds = @{}

    # Method 1: Get adapters from Get-NetAdapter (has detailed info for active adapters)
    # Real hardware is told from software by the driver's own flags and medium
    # number (HardwareInterface, Virtual, NdisPhysicalMedium), never by a word in
    # the description, which every Windows language translates.
    $allNetAdapters = @(Get-NetAdapter -IncludeHidden -EA SilentlyContinue)
    $netAdapters = $allNetAdapters | Where-Object { @PHYSICAL_ADAPTER@ }
    # The PnP ids of the adapters that were just refused, so the PnP pass below
    # cannot list a virtual or Bluetooth adapter again under its own name.
    $refusedIds = @($allNetAdapters | Where-Object { -not (@PHYSICAL_ADAPTER@) } |
        ForEach-Object { $_.PnPDeviceID } | Where-Object { $_ })

    # Cache all network PnpDevices and WMI adapters once for efficiency
    $allNetPnp = Get-PnpDevice -Class Net -EA SilentlyContinue
    $allWmi = @(Get-CimInstance -ClassName Win32_NetworkAdapter -EA SilentlyContinue)

    # Only accept physical device IDs (PCI, USB, ACPI) - reject virtual (SWD, ROOT).
    # These are bus prefixes, which no Windows language translates.
    function Test-PhysicalDevice($id) {
        if (-not $id) { return $false }
        return ($id -like 'PCI\\*' -or $id -like 'USB\\*' -or $id -like 'ACPI\\*')
    }

    foreach ($adapter in $netAdapters) {
        $idx = $adapter.InterfaceIndex

        # The adapter's identity is its PnP device id, which Get-NetAdapter already
        # carries (needed for enable/disable). Nothing here is matched by name: a
        # description or FriendlyName is the driver's text, translated on a
        # non-English Windows, so a join on it picked the wrong device or none.
        $pnpInstanceId = $null
        if (Test-PhysicalDevice $adapter.PnPDeviceID) {
            $pnpInstanceId = $adapter.PnPDeviceID
            $seenIds[$pnpInstanceId] = $true
        }

        # WMI NetEnabled is the authoritative hardware state; joined on the same id.
        $wmiNetEnabled = $null
        if ($pnpInstanceId) {
            $wmiAdapter = $allWmi | Where-Object { $_.PNPDeviceID -eq $pnpInstanceId } | Select-Object -First 1
            if ($wmiAdapter) { $wmiNetEnabled = $wmiAdapter.NetEnabled }
        }

        # Get IP addresses
        $ip4Obj = Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -EA SilentlyContinue | Where-Object { $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1
        $gwObj = Get-NetRoute -InterfaceIndex $idx -DestinationPrefix '0.0.0.0/0' -EA SilentlyContinue | Select-Object -First 1
        $dnsObj = Get-DnsClientServerAddress -InterfaceIndex $idx -AddressFamily IPv4 -EA SilentlyContinue

        $ipv4 = if ($ip4Obj) { $ip4Obj.IPAddress } else { $null }
        $gateway = if ($gwObj) { $gwObj.NextHop } else { $null }
        $dnsServers = if ($dnsObj) { $dnsObj.ServerAddresses } else { $null }

        # Status handling - use .value__ to get the underlying enum integer value
        # AdminStatus: 1=Up, 2=Down, 3=Testing
        $adminVal = [int]$adapter.AdminStatus
        $adminStr = if ($adminVal -eq 1) { 'Up' } else { 'Down' }
        $statusStr = $adapter.Status.ToString()
        $mediaStr = if ($statusStr -eq 'Up') { 'Connected' } elseif ($statusStr -eq 'Disconnected') { 'Disconnected' } else { 'Unknown' }

        $results += [PSCustomObject]@{
            Name = $adapter.Name
            InterfaceGuid = [string]$adapter.InterfaceGuid
            Description = $adapter.InterfaceDescription
            InterfaceIndex = $idx
            InstanceId = $pnpInstanceId
            Status = $statusStr
            AdminStatus = $adminStr
            MediaConnectState = $mediaStr
            MediaType = $adapter.MediaType
            MacAddress = $adapter.MacAddress
            LinkSpeed = $adapter.LinkSpeed
            IPv4 = $ipv4
            Gateway = $gateway
            DNS = if ($dnsServers) { $dnsServers -join ',' } else { $null }
            WmiNetEnabled = $wmiNetEnabled
        }
    }

    # Method 2: Get disabled/unknown adapters from PnpDevice (not in Get-NetAdapter)
    # Physical means a PCI or USB bus id (software adapters sit on ROOT, SWD, BTH,
    # VMBUS), and not an id Get-NetAdapter already refused as virtual or Bluetooth.
    $pnpDevices = $allNetPnp | Where-Object {
        $_.FriendlyName -and
        ($_.InstanceId -like 'PCI\\*' -or $_.InstanceId -like 'USB\\*') -and
        $refusedIds -notcontains $_.InstanceId
    }

    foreach ($pnp in $pnpDevices) {
        # Skip if already found via Get-NetAdapter (same PnP device id)
        if ($seenIds.ContainsKey($pnp.InstanceId)) { continue }

        # Determine status from PnpDevice
        $pnpStatus = $pnp.Status
        $pnpProblem = [int]$pnp.ConfigManagerErrorCode

        # CM_PROB_PHANTOM = 45 (device physically not present - e.g., USB unplugged)
        # CM_PROB_DISABLED = 22 (device manually disabled by user)
        # 0 = No problem (device is OK)
        # For PCI devices, 45 is rare - usually means driver issue, not physical absence
        $isPhantom = ($pnpProblem -eq 45) -and ($pnp.InstanceId -like 'USB*')
        $isDisabled = ($pnpProblem -eq 22) -or ($pnpStatus -eq 'Error') -or ($pnpStatus -eq 'Degraded')
        $isEnabled = ($pnpStatus -eq 'OK' -and $pnpProblem -eq 0)

        # Wi-Fi or Ethernet from the numbers the driver's INF declares, not from its
        # name: NdisPhysicalMedium (*PhysicalMediaType: 9 = Native 802.11, 1 = wireless
        # LAN, 14 = 802.3) and IANA ifType (*IfType: 71 = IEEE 802.11, 6 = Ethernet).
        # The driver key stays bound to a disabled device, so they are readable here.
        # A device whose driver key cannot be read has no medium: unknown, not Ethernet.
        $physicalMedium = $null
        $ifType = $null
        $driverKeyName = (Get-PnpDeviceProperty -InstanceId $pnp.InstanceId -KeyName 'DEVPKEY_Device_Driver' -EA SilentlyContinue).Data
        if ($driverKeyName) {
            $driverKey = Get-ItemProperty -LiteralPath "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\$driverKeyName" -EA SilentlyContinue
            if ($driverKey) {
                $physicalMedium = $driverKey.'*PhysicalMediaType'
                $ifType = $driverKey.'*IfType'
            }
        }
        $mediaType = if ($physicalMedium -eq 9 -or $physicalMedium -eq 1 -or $ifType -eq 71) { 'Native 802.11' } elseif ($physicalMedium -eq 14 -or $ifType -eq 6) { '802.3' } else { '' }

        # Status string for UI - be specific about disabled vs phantom vs unknown
        # Only USB devices can be truly "phantom" (physically removed)
        # PCI devices with code 45 are usually just disabled or have driver issues
        if ($isPhantom) {
            $statusStr = 'NotConnected'
        } elseif ($isDisabled -or $pnpProblem -eq 45) {
            # Treat PCI devices with code 45 as disabled (can be re-enabled)
            $statusStr = 'Disabled'
        } elseif ($pnpStatus -eq 'OK') {
            $statusStr = 'Up'
        } elseif ($pnpStatus -eq 'Unknown') {
            # Unknown = device has driver issue or is in phantom state
            $statusStr = 'Unknown'
        } else {
            $statusStr = 'Disabled'
        }

        # AdminStatus: Up = can be disabled, Down = can be enabled
        # For disabled devices, AdminStatus should be 'Down' to indicate it needs enabling
        $adminStr = if ($isEnabled) { 'Up' } elseif ($isPhantom) { 'NotConnected' } else { 'Down' }

        # Look up WMI NetEnabled for this PnpDevice
        $pnpWmiAdapter = $allWmi | Where-Object {
            $_.PNPDeviceID -eq $pnp.InstanceId
        } | Select-Object -First 1
        $pnpWmiNetEnabled = if ($pnpWmiAdapter) { $pnpWmiAdapter.NetEnabled } else { $null }

        $results += [PSCustomObject]@{
            Name = $pnp.FriendlyName -replace ' Controller$','' -replace ' Adapter$',''
            Description = $pnp.FriendlyName
            InterfaceIndex = $null
            InstanceId = $pnp.InstanceId
            Status = $statusStr
            AdminStatus = $adminStr
            MediaConnectState = if ($isPhantom) { 'NotConnected' } elseif ($isDisabled -or $pnpProblem -eq 45) { 'Disconnected' } else { 'Unknown' }
            MediaType = $mediaType
            MacAddress = $null
            LinkSpeed = $null
            IPv4 = $null
            Gateway = $null
            DNS = $null
            WmiNetEnabled = $pnpWmiNetEnabled
        }
    }

    $results | ConvertTo-Json -Depth 2
    """.replace("@PHYSICAL_ADAPTER@", PHYSICAL_ADAPTER)


# WiFi facts come from wlanapi.dll, never from netsh text: netsh's interface
# listing answers in the system language (a Turkish install labels the
# fields "Kanal", "Sinyal", "Radyo türü"), so every English-label regex
# silently yielded nothing there — and a channel number alone cannot place a
# Wi-Fi 6E network, whose 6 GHz channels overlap 2.4 GHz numbering. The API
# hands back numeric enums and the BSS entry's own centre frequency, which
# answer both problems at once. The walk lives in `utils/winapi/wlan.py`
# (ctypes); it used to be a C# class compiled at run time inside the PowerShell
# command, the pattern Windows Defender flagged on 2026-09-02.
#
# The record-to-report mapping is a pure function so it can be tested against
# described records. Every name comes from ``wlan``'s own enum tables
# (auth_name, phy_name, band_ghz), shared with the advisories that judge the
# same link, so the panel and the finding can never disagree on a word.
def _normal_guid(value: object) -> str:
    return str(value or "").strip().strip("{}").lower()


def wifi_rows(records: list[WlanRecord], adapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Connected-radio facts per adapter, keyed the way ``_to_adapter_info`` reads them.

    The join is on the interface GUID, compared without braces or case: the
    inventory quotes it with braces and upper-case, the API without.
    """
    rows: list[dict[str, Any]] = []
    for adapter in adapters:
        guid = _normal_guid(adapter.get("InterfaceGuid"))
        if not guid:
            continue
        for record in records:
            if record.interface_guid.lower() != guid:
                continue
            rows.append(
                {
                    "AdapterName": adapter.get("Name"),
                    "SSID": record.ssid,
                    "Channel": record.channel,
                    "FrequencyGHz": band_ghz(record.center_khz),
                    "RadioType": phy_name(record.phy_type),
                    "SignalPercent": record.signal_percent,
                    "AuthType": auth_name(record.auth_algorithm),
                }
            )
    return rows


def _query_adapter_records() -> list[dict[str, Any]]:
    """Run the inventory script and return its records, or an empty list.

    Every failure path returns empty rather than raising: a hardware panel that
    cannot read the adapters shows no adapters, and the reason goes to the log
    and the debug channel where a user can be asked for it.
    """
    success, output = run_powershell(_ADAPTER_INVENTORY_SCRIPT, component="network")
    debug_log(
        "network",
        f"Network adapter PS success={success}, output_len={len(output) if output else 0}",
    )
    debug_log("network", f"Network adapter PS output: {output[:1000] if output else '(empty)'}")

    if not success:
        logger.warning(
            f"Network adapter PowerShell failed: {output[:500] if output else 'no output'}"
        )
        debug_log(
            "network",
            f"PROBLEM: Network adapter PS failed: {output[:500] if output else 'no output'}",
        )
        return []

    if not output or output.strip() in ("", "null", "[]"):
        logger.warning("Network adapter detection returned empty result")
        debug_log("network", "PROBLEM: Network adapter PS returned empty result")
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse network adapter JSON: {e}")
        return []

    if isinstance(data, dict):
        data = [data]
    if not data:
        logger.debug("Network adapter JSON parsed to empty list")
        return []

    debug_log("network", f"Parsed {len(data)} adapter records from JSON")
    return [record for record in data if record]


def _query_wifi_by_adapter(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Read SSID, channel, band and signal for the connected radios.

    Keyed by adapter name because that is the field the report is built from.
    A failure here is silent by design: WiFi detail is enrichment, and an
    Ethernet-only machine legitimately produces nothing. No process starts —
    wlanapi answers in this one.
    """
    try:
        connected = wlan.query_connected()
    except Exception:
        logger.debug("wlanapi query failed", exc_info=True)
        return {}
    if not connected:
        return {}
    wifi_adapters = [r for r in records if "802.11" in str(r.get("MediaType") or "")]
    return {
        str(row["AdapterName"]): row
        for row in wifi_rows(connected, wifi_adapters)
        if row.get("AdapterName")
    }


def _to_adapter_info(
    adapter_data: dict[str, Any], wifi: dict[str, Any]
) -> NetworkAdapterInfo | None:
    """Translate one inventory record into the schema object the API returns.

    Returns None for a record with no name, which is the one field nothing
    downstream can work without.
    """
    # Skip adapters without a name - invalid data
    name = adapter_data.get("Name")
    if not name:
        logger.debug("Skipping adapter with missing name")
        debug_log("network", "Skipping adapter with missing name")
        return None

    # Log InstanceId for each adapter (critical for enable/disable)
    instance_id = adapter_data.get("InstanceId")
    debug_log("network", f"Adapter '{name}': InstanceId={instance_id}")

    media_type = adapter_data.get("MediaType") or ""
    adapter_type = "WiFi" if "802.11" in media_type else "Ethernet"

    # Parse link speed (e.g., "1 Gbps" -> 1000)
    speed_mbps = None
    link_speed = adapter_data.get("LinkSpeed")
    if link_speed:
        with contextlib.suppress(ValueError):
            if "Gbps" in link_speed:
                speed_mbps = int(float(link_speed.replace(" Gbps", "")) * 1000)
            elif "Mbps" in link_speed:
                speed_mbps = int(float(link_speed.replace(" Mbps", "")))

    # Parse DNS servers (only if we have actual data)
    dns_str = adapter_data.get("DNS")
    dns_servers = [d.strip() for d in dns_str.split(",") if d.strip()] if dns_str else []

    # Determine enabled/connected status - use WMI NetEnabled as authoritative source
    # WMI Win32_NetworkAdapter.NetEnabled reflects actual hardware state, not cached cmdlet state
    # MediaConnectState: Connected, Disconnected, Unknown/missing = unknown
    wmi_net_enabled = adapter_data.get("WmiNetEnabled")
    status = adapter_data.get("Status")
    admin_status = adapter_data.get("AdminStatus")
    media_state = adapter_data.get("MediaConnectState")
    link_speed = adapter_data.get("LinkSpeed", "")

    # Priority: WMI NetEnabled > Status/AdminStatus combo
    # WMI is authoritative because it reads hardware state directly
    if wmi_net_enabled is not None:
        is_enabled = bool(wmi_net_enabled)
    else:
        # Fallback to Status/AdminStatus for adapters without WMI data
        is_enabled = (
            (str(status) == "Up" and str(admin_status) == "Up" and link_speed != "0 bps")
            if status is not None
            else False
        )

    # Only report connected if we explicitly know it's "Connected"
    is_connected = str(media_state) == "Connected" if media_state is not None else False

    # WiFi-specific fields - only use if actually detected (not 0/empty placeholders)
    wifi_ssid = wifi.get("SSID") if wifi else None
    wifi_ssid = wifi_ssid if wifi_ssid else None  # Empty string -> None

    wifi_channel = wifi.get("Channel") if wifi else None
    wifi_channel = wifi_channel if wifi_channel and wifi_channel > 0 else None

    wifi_freq = wifi.get("FrequencyGHz") if wifi else None
    wifi_freq = wifi_freq if wifi_freq and wifi_freq > 0 else None

    wifi_radio = wifi.get("RadioType") if wifi else None
    wifi_radio = wifi_radio if wifi_radio else None

    wifi_signal = wifi.get("SignalPercent") if wifi else None
    wifi_signal = wifi_signal if wifi_signal and wifi_signal > 0 else None

    wifi_auth = wifi.get("AuthType") if wifi else None
    wifi_auth = wifi_auth if wifi_auth else None

    # Parse InterfaceIndex (may be null for disabled adapters)
    iface_idx = adapter_data.get("InterfaceIndex")
    interface_index = int(iface_idx) if iface_idx is not None else None
    instance_id = adapter_data.get("InstanceId")

    from fpstune.settings.definitions.network import adapter_key

    return NetworkAdapterInfo(
        name=name,
        description=adapter_data.get("Description") or "",
        adapter_type=adapter_type,
        status=adapter_data.get("Status") or "Unknown",
        is_enabled=is_enabled,
        is_connected=is_connected,
        mac_address=adapter_data.get("MacAddress"),
        speed_mbps=speed_mbps,
        ipv4_address=adapter_data.get("IPv4"),
        ipv6_address=adapter_data.get("IPv6"),
        gateway=adapter_data.get("Gateway"),
        dns_servers=dns_servers,
        interface_index=interface_index,
        instance_id=instance_id,
        setting_key=adapter_key(instance_id) if instance_id else None,
        ssid=wifi_ssid,
        channel=wifi_channel,
        frequency_ghz=wifi_freq,
        radio_type=wifi_radio,
        signal_percent=wifi_signal,
        auth_type=wifi_auth,
    )


def get_detailed_network_adapters() -> list[NetworkAdapterInfo]:
    """Get detailed network adapter information including IP, DNS, WiFi details."""
    debug_log("network", "get_detailed_network_adapters() called")

    records = _query_adapter_records()
    if not records:
        return []

    wifi_info = _query_wifi_by_adapter(records)

    adapters = [
        info
        for info in (
            _to_adapter_info(record, wifi_info.get(record.get("Name", ""), {}))
            for record in records
        )
        if info is not None
    ]

    logger.debug(f"Detected {len(adapters)} network adapters with details")
    return adapters
