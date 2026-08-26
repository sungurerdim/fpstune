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
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from fpstune.api.schemas import NetworkAdapterInfo
from fpstune.utils.debug import debug_log
from fpstune.utils.powershell import run_powershell

logger = logging.getLogger(__name__)

# Get basic adapter info with IP configuration
# Include AdminStatus (enabled/disabled) and MediaConnectState (connected/disconnected)
# Show ALL physical adapters including disabled ones (via PnpDevice fallback)
_ADAPTER_INVENTORY_SCRIPT = """
    $results = @()
    $seenIds = @{}

    # Method 1: Get adapters from Get-NetAdapter (has detailed info for active adapters)
    $netAdapters = Get-NetAdapter -IncludeHidden -EA SilentlyContinue | Where-Object {
        -not $_.Virtual -and
        $_.Name -notlike '*vEthernet*' -and
        $_.InterfaceDescription -notlike '*Loopback*' -and
        $_.InterfaceDescription -notlike '*Miniport*' -and
        $_.InterfaceDescription -notlike '*Virtual*' -and
        $_.InterfaceDescription -notlike '*Hyper-V*' -and
        $_.InterfaceDescription -notlike '*Wi-Fi Direct*' -and
        $_.InterfaceDescription -notlike '*Bluetooth*'
    }

    # Cache all network PnpDevices once for efficiency
    $allNetPnp = Get-PnpDevice -Class Net -EA SilentlyContinue

    foreach ($adapter in $netAdapters) {
        $seenIds[$adapter.InterfaceDescription] = $true
        $idx = $adapter.InterfaceIndex
        $adapterDesc = $adapter.InterfaceDescription

        # Get PnpDevice InstanceId for this adapter (needed for enable/disable)
        # IMPORTANT: Only accept physical device IDs (PCI, USB) - reject virtual (SWD, ROOT)
        $pnpInstanceId = $null

        # Helper function to check if InstanceId is a physical device
        function Test-PhysicalDevice($id) {
            if (-not $id) { return $false }
            return ($id -like 'PCI\\*' -or $id -like 'USB\\*' -or $id -like 'ACPI\\*')
        }

        # Strategy 1: WMI Win32_NetworkAdapter using Description match (most reliable)
        # This correctly maps adapter description to PNPDeviceID
        # Also capture NetEnabled which is the authoritative hardware state
        $wmiAdapter = Get-CimInstance -ClassName Win32_NetworkAdapter -EA SilentlyContinue | Where-Object {
            $_.Description -eq $adapterDesc -and $_.PNPDeviceID -and (Test-PhysicalDevice $_.PNPDeviceID)
        } | Select-Object -First 1
        $wmiNetEnabled = $null
        if ($wmiAdapter) {
            $pnpInstanceId = $wmiAdapter.PNPDeviceID
            $wmiNetEnabled = $wmiAdapter.NetEnabled
        }

        # Strategy 2: WMI using NetConnectionID (adapter name shown in Windows)
        if (-not $pnpInstanceId) {
            $escapedName = $adapter.Name -replace "'", "''"
            $wmiAdapter = Get-CimInstance -ClassName Win32_NetworkAdapter -Filter "NetConnectionID='$escapedName'" -EA SilentlyContinue
            if ($wmiAdapter -and $wmiAdapter.PNPDeviceID -and (Test-PhysicalDevice $wmiAdapter.PNPDeviceID)) {
                $pnpInstanceId = $wmiAdapter.PNPDeviceID
                if ($null -eq $wmiNetEnabled) { $wmiNetEnabled = $wmiAdapter.NetEnabled }
            }
        }

        # Strategy 3: PnpDevice exact FriendlyName match (only physical devices)
        if (-not $pnpInstanceId) {
            $pnpDev = $allNetPnp | Where-Object {
                $_.FriendlyName -eq $adapterDesc -and (Test-PhysicalDevice $_.InstanceId)
            } | Select-Object -First 1
            if ($pnpDev) { $pnpInstanceId = $pnpDev.InstanceId }
        }

        # Strategy 4: PnpDevice partial match (only physical devices)
        if (-not $pnpInstanceId) {
            $pnpDev = $allNetPnp | Where-Object {
                $_.FriendlyName -and (Test-PhysicalDevice $_.InstanceId) -and (
                    $_.FriendlyName -like "*$adapterDesc*" -or
                    $adapterDesc -like "*$($_.FriendlyName)*"
                )
            } | Select-Object -First 1
            if ($pnpDev) { $pnpInstanceId = $pnpDev.InstanceId }
        }

        # Strategy 5: Vendor-specific match from PnpDevice (only physical devices)
        if (-not $pnpInstanceId -and $adapterDesc -match '(Realtek|Intel|Killer|Broadcom|Qualcomm|Marvell|Aquantia|NVIDIA)') {
            $vendor = $Matches[1]
            $pnpDev = $allNetPnp | Where-Object {
                $_.FriendlyName -like "*$vendor*" -and (Test-PhysicalDevice $_.InstanceId)
            } | Select-Object -First 1
            if ($pnpDev) { $pnpInstanceId = $pnpDev.InstanceId }
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
    $pnpDevices = Get-PnpDevice -Class Net -EA SilentlyContinue | Where-Object {
        $_.FriendlyName -and
        $_.FriendlyName -notlike '*Miniport*' -and
        $_.FriendlyName -notlike '*Virtual*' -and
        $_.FriendlyName -notlike '*Hyper-V*' -and
        $_.FriendlyName -notlike '*Wi-Fi Direct*' -and
        $_.FriendlyName -notlike '*Bluetooth*' -and
        $_.FriendlyName -notlike '*Debug*' -and
        $_.FriendlyName -notlike '*Extension*' -and
        ($_.InstanceId -like 'PCI\\*' -or $_.InstanceId -like 'USB\\*')
    }

    foreach ($pnp in $pnpDevices) {
        # Skip if already found via Get-NetAdapter
        if ($seenIds.ContainsKey($pnp.FriendlyName)) { continue }

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
        $mediaType = if ($pnp.FriendlyName -match 'Wi-Fi|Wireless') { 'Native 802.11' } else { '802.3' }

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
        $pnpWmiAdapter = Get-CimInstance -ClassName Win32_NetworkAdapter -EA SilentlyContinue | Where-Object {
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
    """

# WiFi facts come from wlanapi.dll, never from netsh text: `netsh wlan show
# interfaces` answers in the system language (a Turkish install labels the
# fields "Kanal", "Sinyal", "Radyo türü"), so every English-label regex
# silently yielded nothing there — and a channel number alone cannot place a Wi-Fi 6E
# network, whose 6 GHz channels overlap 2.4 GHz numbering. The API hands back
# numeric enums and the BSS entry's own center frequency in kHz, which answer
# both problems at once. The walk lives inside the C# class (the A1 lesson: a
# variable-length native buffer never crosses PowerShell's binder). Each record
# is "guid|channel|freqKHz|phy|signal|auth|ssid" — SSID last because an SSID
# may itself contain the separator.
_WLANAPI_CSHARP = r"""
Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class WlanQuery {
    [DllImport("wlanapi.dll")]
    private static extern int WlanOpenHandle(uint version, IntPtr reserved, out uint negotiated, out IntPtr handle);
    [DllImport("wlanapi.dll")]
    private static extern int WlanCloseHandle(IntPtr handle, IntPtr reserved);
    [DllImport("wlanapi.dll")]
    private static extern int WlanEnumInterfaces(IntPtr handle, IntPtr reserved, out IntPtr list);
    [DllImport("wlanapi.dll")]
    private static extern int WlanQueryInterface(IntPtr handle, ref Guid guid, int opcode, IntPtr reserved, out uint size, out IntPtr data, IntPtr valueType);
    [DllImport("wlanapi.dll")]
    private static extern int WlanGetNetworkBssList(IntPtr handle, ref Guid guid, IntPtr ssid, int bssType, bool securityEnabled, IntPtr reserved, out IntPtr list);
    [DllImport("wlanapi.dll")]
    private static extern void WlanFreeMemory(IntPtr memory);

    [StructLayout(LayoutKind.Sequential)]
    private struct DOT11_SSID {
        public uint length;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)] public byte[] ssid;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct WLAN_ASSOCIATION_ATTRIBUTES {
        public DOT11_SSID ssid;
        public int bssType;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)] public byte[] bssid;
        public int phyType;
        public uint phyIndex;
        public uint signalQuality;
        public uint rxRate;
        public uint txRate;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct WLAN_SECURITY_ATTRIBUTES {
        [MarshalAs(UnmanagedType.Bool)] public bool securityEnabled;
        [MarshalAs(UnmanagedType.Bool)] public bool oneXEnabled;
        public int authAlgorithm;
        public int cipherAlgorithm;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WLAN_CONNECTION_ATTRIBUTES {
        public int state;
        public int mode;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string profile;
        public WLAN_ASSOCIATION_ATTRIBUTES association;
        public WLAN_SECURITY_ATTRIBUTES security;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct WLAN_RATE_SET {
        public ushort length;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 126)] public ushort[] rates;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct WLAN_BSS_ENTRY {
        public DOT11_SSID ssid;
        public uint phyId;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 6)] public byte[] bssid;
        public int bssType;
        public int bssPhyType;
        public int rssi;
        public uint linkQuality;
        public byte inRegDomain;
        public ushort beaconPeriod;
        public ulong timestamp;
        public ulong hostTimestamp;
        public ushort capability;
        public uint chCenterFrequency;
        public WLAN_RATE_SET rateSet;
        public uint ieOffset;
        public uint ieSize;
    }

    private static bool SameMac(byte[] a, byte[] b) {
        if (a == null || b == null) { return false; }
        for (int i = 0; i < 6; i++) { if (a[i] != b[i]) { return false; } }
        return true;
    }

    public static string[] Query() {
        var results = new List<string>();
        uint negotiated; IntPtr handle;
        if (WlanOpenHandle(2, IntPtr.Zero, out negotiated, out handle) != 0) { return results.ToArray(); }
        try {
            IntPtr pList;
            if (WlanEnumInterfaces(handle, IntPtr.Zero, out pList) != 0) { return results.ToArray(); }
            try {
                int count = Marshal.ReadInt32(pList);
                IntPtr items = IntPtr.Add(pList, 8);
                int itemSize = 16 + 512 + 4; // GUID + WCHAR[256] + state
                for (int i = 0; i < count; i++) {
                    IntPtr item = IntPtr.Add(items, i * itemSize);
                    byte[] guidBytes = new byte[16];
                    Marshal.Copy(item, guidBytes, 0, 16);
                    Guid guid = new Guid(guidBytes);
                    int state = Marshal.ReadInt32(item, 16 + 512);
                    if (state != 1) { continue; } // connected only

                    uint size; IntPtr data;
                    if (WlanQueryInterface(handle, ref guid, 7, IntPtr.Zero, out size, out data, IntPtr.Zero) != 0) { continue; }
                    WLAN_CONNECTION_ATTRIBUTES conn;
                    try {
                        conn = (WLAN_CONNECTION_ATTRIBUTES)Marshal.PtrToStructure(data, typeof(WLAN_CONNECTION_ATTRIBUTES));
                    } finally { WlanFreeMemory(data); }

                    ulong channel = 0;
                    if (WlanQueryInterface(handle, ref guid, 8, IntPtr.Zero, out size, out data, IntPtr.Zero) == 0) {
                        try { channel = (uint)Marshal.ReadInt32(data); } finally { WlanFreeMemory(data); }
                    }

                    ulong freqKHz = 0;
                    IntPtr pBss;
                    if (WlanGetNetworkBssList(handle, ref guid, IntPtr.Zero, 1, false, IntPtr.Zero, out pBss) == 0) {
                        try {
                            int bssCount = Marshal.ReadInt32(pBss, 4);
                            int entrySize = Marshal.SizeOf(typeof(WLAN_BSS_ENTRY));
                            IntPtr entries = IntPtr.Add(pBss, 8);
                            for (int j = 0; j < bssCount; j++) {
                                WLAN_BSS_ENTRY entry = (WLAN_BSS_ENTRY)Marshal.PtrToStructure(
                                    IntPtr.Add(entries, j * entrySize), typeof(WLAN_BSS_ENTRY));
                                if (SameMac(entry.bssid, conn.association.bssid)) {
                                    freqKHz = entry.chCenterFrequency;
                                    break;
                                }
                            }
                        } finally { WlanFreeMemory(pBss); }
                    }

                    string ssid = "";
                    if (conn.association.ssid.length > 0 && conn.association.ssid.length <= 32) {
                        ssid = System.Text.Encoding.UTF8.GetString(
                            conn.association.ssid.ssid, 0, (int)conn.association.ssid.length);
                    }
                    results.Add(guid.ToString("D") + "|" + channel + "|" + freqKHz + "|" +
                        conn.association.phyType + "|" + conn.association.signalQuality + "|" +
                        conn.security.authAlgorithm + "|" + ssid);
                }
            } finally { WlanFreeMemory(pList); }
        } finally { WlanCloseHandle(handle, IntPtr.Zero); }
        return results.ToArray();
    }
}
'@
"""

# The record-to-report mapping is a pure function so the contract tests can run
# the shipped text against described records. Both maps key on the API's own
# numeric enums (dot11_phy_type, DOT11_AUTH_ALGORITHM); the band comes from the
# BSS entry's center frequency, which is what tells a 6 GHz channel 1 from a
# 2.4 GHz channel 1. An unknown frequency stays 0 — never guessed from the
# channel number.
_WIFI_MAP_PS = r"""
function Convert-WlanRecords {
    param([string[]]$records, $wifiAdapters)
    $phyNames = @{ 4 = '802.11a'; 5 = '802.11b'; 6 = '802.11g'; 7 = '802.11n';
                   8 = '802.11ac'; 9 = '802.11ad'; 10 = '802.11ax'; 11 = '802.11be' }
    $authNames = @{ 1 = 'Open'; 2 = 'Shared'; 3 = 'WPA-Enterprise'; 4 = 'WPA-Personal';
                    6 = 'WPA2-Enterprise'; 7 = 'WPA2-Personal'; 8 = 'WPA3-Enterprise';
                    9 = 'WPA3-Personal'; 10 = 'OWE'; 11 = 'WPA3-Enterprise-192' }
    $results = @()
    foreach ($adapter in $wifiAdapters) {
        $adapterGuid = ($adapter.InterfaceGuid -replace '[{}]', '').ToLower()
        foreach ($rec in $records) {
            $f = $rec -split '\|', 7
            if ($f.Count -lt 7 -or $f[0].ToLower() -ne $adapterGuid) { continue }
            $freqKHz = [int64]$f[2]
            $freq = if ($freqKHz -ge 5925000) { 6.0 }
                    elseif ($freqKHz -ge 4900000) { 5.0 }
                    elseif ($freqKHz -ge 2400000) { 2.4 }
                    else { 0 }
            $phy = [int]$f[3]
            $auth = [int]$f[5]
            $results += [PSCustomObject]@{
                AdapterName = $adapter.Name
                SSID = $f[6]
                Channel = [int]$f[1]
                FrequencyGHz = $freq
                RadioType = if ($phyNames.ContainsKey($phy)) { $phyNames[$phy] } else { '' }
                SignalPercent = [int]$f[4]
                AuthType = if ($authNames.ContainsKey($auth)) { $authNames[$auth] } else { '' }
            }
        }
    }
    return $results
}
"""

_WIFI_DETAIL_SCRIPT = (
    _WLANAPI_CSHARP
    + _WIFI_MAP_PS
    + r"""
try {
    $records = [WlanQuery]::Query()
    $wifiAdapters = Get-NetAdapter | Where-Object { $_.MediaType -like '*802.11*' -and $_.Status -eq 'Up' }
    $results = @(Convert-WlanRecords -records $records -wifiAdapters $wifiAdapters)
    ConvertTo-Json -InputObject $results -Depth 2
} catch { '[]' }
"""
)


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


def _query_wifi_by_adapter() -> dict[str, dict[str, Any]]:
    """Read SSID, channel, band and signal for the connected radios.

    Keyed by adapter name because that is the only field both scripts carry.
    A failure here is silent by design: WiFi detail is enrichment, and an
    Ethernet-only machine legitimately produces nothing.
    """
    wifi_info: dict[str, dict[str, Any]] = {}
    success, output = run_powershell(_WIFI_DETAIL_SCRIPT)
    if not success or not output or output.strip() in ("", "[]", "null"):
        return wifi_info

    try:
        wifi_data = json.loads(output)
    except json.JSONDecodeError:
        return wifi_info

    if isinstance(wifi_data, dict):
        wifi_data = [wifi_data]
    for wifi in wifi_data:
        if wifi and isinstance(wifi, dict) and wifi.get("AdapterName"):
            wifi_info[wifi["AdapterName"]] = wifi
    return wifi_info


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
        instance_id=adapter_data.get("InstanceId"),
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

    wifi_info = _query_wifi_by_adapter()

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
