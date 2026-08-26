"""Network setting definitions.

Contains global TCP settings and per-adapter setting factories.
Uses netsh, PowerShell, and registry executors.

The value_map pattern is used to translate between raw system values and
human-readable display values. For example, registry DWORD 0xFFFFFFFF maps to "disabled".
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# Note: escape_single_quoted no longer needed - InterfaceIndex (numeric) is used instead

# === DNS IP Address Constants ===
CLOUDFLARE_SECURITY_IPS = ("1.1.1.2", "1.0.0.2")
CLOUDFLARE_FAMILY_IPS = ("1.1.1.3", "1.0.0.3")
CLOUDFLARE_STANDARD_IPS = ("1.1.1.1", "1.0.0.1")

# === Registry Path Constants ===
NETWORK_THROTTLING_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
TCPIP_PARAMS_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
TCPIP_INTERFACES_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
SERVICE_PROVIDER_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\ServiceProvider"
QOS_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\QoS"
PSCHED_KEY = r"SOFTWARE\Policies\Microsoft\Windows\Psched"

# An adapter name reaches no command from this module: every use below is a
# `display_name=` label, and `utils/powershell.py` rewrites `-InterfaceIndex N`
# into a `-Name $var` lookup PowerShell resolves for itself. The one route that
# does spell a name into a command (`api/routes/system_network.py`) escapes it
# there. So a name-shape allowlist here could only lose real hardware — a vendor
# name carries parentheses and dots, and a non-English Windows names adapters in
# the system language. `discovery/network.py::filter_valid_adapters` is the only
# filter, and it drops nothing but the empty name.

# === Global TCP Settings (netsh) ===

# TCP Auto-Tuning
TCP_AUTO_TUNING = SettingExecutor(
    id="network:tcp_auto_tuning",
    category=SettingCategory.NETWORK,
    display_name="TCP Auto-Tuning",
    description="Dynamically adjusts TCP receive window size. Normal mode provides optimal throughput for most connections.",
    value_type=SettingValueType.CHOICE,
    choices=("normal", "disabled", "highlyrestricted", "restricted", "experimental"),
    default_value="normal",
    recommended_value="normal",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
    ],
    current_impact="Normal: Windows dynamically adjusts TCP window → balanced performance",
    recommended_impact="Normal is optimal for both speed and latency",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for TCP performance
    category_order=1,  # Primary TCP setting
    effect="Enables dynamic TCP window sizing for optimal throughput",
    impact_scores={"throughput": "high", "latency_ms": 0, "stability": "high"},
    # Detection - exact key from netsh output
    detect_type=DetectType.NETSH,
    detect_command="interface tcp show global",
    detect_args={"parse_key": "receive window auto-tuning level"},
    value_map={},  # Direct pass-through (lowercase)
    # Apply
    apply_type=DetectType.NETSH,
    apply_command="interface tcp set global autotuninglevel=%value%",
    apply_args={},
    apply_value_map={},
)

# Scaling Heuristics
# NOTE: The 'wsh' parameter is LEGACY and has NO EFFECT on Windows 8.1+
# Heuristics have been disabled by default since Windows 8.1
# This setting is kept for compatibility but marked as COMPLETE scope (low priority)
# Reference: https://learn.microsoft.com/en-us/windows-server/networking/technologies/netsh/netsh-interface-tcp
SCALING_HEURISTICS = SettingExecutor(
    id="network:scaling_heuristics",
    category=SettingCategory.NETWORK,
    display_name="Scaling Heuristics",
    description="Legacy setting (no effect on Windows 8.1+). Heuristics disabled by default.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
    ],
    current_impact="Legacy: No effect on modern Windows",
    recommended_impact="Legacy: No effect on modern Windows",
    scope=SettingScope.COMPLETE,  # Low priority - legacy setting
    category_order=99,  # Move to bottom since it's legacy
    effect="Legacy setting with no effect on Windows 8.1+",
    impact_scores={"latency_ms": 0, "stability": "high"},
    # Detection - uses separate heuristics command
    detect_type=DetectType.NETSH,
    detect_command="interface tcp show heuristics",
    detect_args={"parse_key": "window scaling heuristics"},
    value_map={},
    # Apply - wsh parameter is legacy but still accepted
    apply_type=DetectType.NETSH,
    apply_command="interface tcp set heuristics wsh=%value%",
    apply_args={},
    apply_value_map={},
)

# Congestion Provider
# NOTE: The old "netsh int tcp set global congestionprovider=xxx" is deprecated in Windows 11.
# The new method uses supplemental templates for Internet/Datacenter profiles.
# We use PowerShell Set-NetTCPSetting for reliable cross-version support.
CONGESTION_PROVIDER = SettingExecutor(
    id="network:congestion_provider",
    category=SettingCategory.NETWORK,
    display_name="Congestion Provider",
    description="Controls how TCP responds to network congestion. CUBIC is the most optimized algorithm for modern networks.",
    value_type=SettingValueType.CHOICE,
    choices=("CUBIC", "NewReno", "CTCP", "DCTCP", "Default"),
    default_value="CUBIC",
    recommended_value="CUBIC",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
    ],
    current_impact="Determines how TCP responds to network congestion",
    recommended_impact="CUBIC is the most optimized algorithm for modern networks",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for congestion handling
    category_order=3,  # Congestion algorithm
    effect="Optimizes TCP congestion handling for better network performance",
    impact_scores={"throughput": "medium", "latency_ms": 0, "stability": "high"},
    # Detection - PowerShell for reliable cross-version support
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "try { "
        "$setting = Get-NetTCPSetting -SettingName Internet -ErrorAction Stop; "
        "if ($setting.CongestionProvider) { $setting.CongestionProvider } else { 'CUBIC' } "
        "} catch { "
        "$netsh = netsh int tcp show global 2>$null | Select-String 'Congestion'; "
        "if ($netsh -match 'ctcp') { 'CTCP' } elseif ($netsh -match 'cubic') { 'CUBIC' } else { 'CUBIC' } "
        "}"
    ),
    detect_args={},
    value_map={},  # Direct pass-through
    # Apply - PowerShell Set-NetTCPSetting works on both Windows 10 and 11
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "Set-NetTCPSetting -SettingName Internet -CongestionProvider %value% -ErrorAction Stop; "
        "Set-NetTCPSetting -SettingName Datacenter -CongestionProvider %value% -ErrorAction SilentlyContinue; "
        "'ok'"
    ),
    apply_args={},
    apply_value_map={},
)

# Receive Side Scaling
RECEIVE_SIDE_SCALING = SettingExecutor(
    id="network:receive_side_scaling",
    category=SettingCategory.NETWORK,
    display_name="Receive Side Scaling (RSS)",
    description="Distributes network packet processing across multiple CPU cores instead of a single core. Enables higher throughput and prevents one core from becoming the network bottleneck.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Distributes network load across CPU cores → better parallel processing",
    recommended_impact="Keep enabled: Multi-core utilization for higher network performance",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for multi-core
    category_order=4,  # Multi-core network processing
    effect="Distributes network load across CPU cores for parallel processing",
    impact_scores={"throughput": "high", "cpu_usage": -2, "latency_ms": -1, "stability": "high"},
    # Detection - exact key from netsh output (lowercase)
    detect_type=DetectType.NETSH,
    detect_command="interface tcp show global",
    detect_args={"parse_key": "receive-side scaling state"},
    value_map={},
    # Apply
    apply_type=DetectType.NETSH,
    apply_command="interface tcp set global rss=%value%",
    apply_args={},
    apply_value_map={},
)

# Receive Segment Coalescing
RECEIVE_SEGMENT_COALESCING = SettingExecutor(
    id="network:receive_segment_coalescing",
    category=SettingCategory.NETWORK,
    display_name="Receive Segment Coalescing (RSC)",
    description="Coalesces multiple incoming TCP segments into larger units before delivering them to the host. Disabling prevents the artificial latency this batching introduces.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Packets batched → less CPU but extra latency",
    recommended_impact="Disabled: Packets processed immediately → lower network latency",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for network latency
    category_order=5,  # Packet batching latency
    effect="Disabling prevents packet batching for lower network latency",
    impact_scores={"latency_ms": -2, "throughput": "medium", "stability": "high"},
    # Detection - exact key from netsh output (lowercase)
    detect_type=DetectType.NETSH,
    detect_command="interface tcp show global",
    detect_args={"parse_key": "receive segment coalescing state"},
    value_map={},
    # Apply
    apply_type=DetectType.NETSH,
    apply_command="interface tcp set global rsc=%value%",
    apply_args={},
    apply_value_map={},
)

# NOTE: TCP Chimney Offload is REMOVED in Windows 11
# The netsh "chimney" parameter no longer exists
# Do not include it in NETWORK_SETTINGS


# === Per-Adapter Setting Factories ===


def create_interrupt_moderation_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create an interrupt moderation setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.
    This avoids issues with special characters and localization in adapter names.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for interrupt moderation.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:interrupt_moderation",
        category=SettingCategory.NETWORK,
        display_name=f"Interrupt Moderation ({display_name})",
        description="Controls whether the network adapter batches CPU interrupt requests for multiple packets. Disabling processes each packet immediately, trading slightly higher CPU usage for lower per-packet latency.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "The adapter interrupts the CPU per packet instead of per batch, so CPU use rises with packet rate. Harmless on a modern desktop CPU at game traffic rates; noticeable on a weak CPU under a heavy download."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Interrupts batched → less CPU but 1-5ms extra latency",
        recommended_impact="Disabled: Every packet processed immediately → lowest network latency",
        scope=SettingScope.RECOMMENDED,  # Noticeable benefit for network latency
        category_order=10,  # Per-adapter setting
        effect="Disabling processes every packet immediately for lowest latency",
        impact_scores={"latency_ms": -3.0, "cpu_usage": 5.0, "stability": "high"},
        # Detection - Use InterfaceIndex (numeric) for reliable command execution
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*InterruptModeration' -ErrorAction SilentlyContinue; "
            "if ($prop) { [int](@($prop.RegistryValue)[0]) } else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index, "batch_adapter_keyword": "*InterruptModeration"},
        # Map numeric registry values to choice names
        value_map={
            0: "Disabled",
            "0": "Disabled",
            1: "Enabled",
            "1": "Enabled",
        },
        # Apply - use InterfaceIndex with explicit int cast and error handling
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*InterruptModeration' -ErrorAction Stop; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*InterruptModeration' -RegistryValue ([int]%value%) -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={"Enabled": 1, "Disabled": 0},
    )


def create_flow_control_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a flow control setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for flow control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:flow_control",
        category=SettingCategory.NETWORK,
        display_name=f"Flow Control ({display_name})",
        description="Hardware-level flow control uses pause frames to stop packet transmission when receive buffers fill. Disabling eliminates the latency spikes caused by these pause frames.",
        value_type=SettingValueType.CHOICE,
        choices=("Rx & Tx Enabled", "Tx Enabled", "Rx Enabled", "Disabled"),
        default_value="Rx & Tx Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "Pause frames exist to stop a congested receiver dropping packets. Without them a saturated link drops instead of pausing, which is the right trade for a game and the wrong one for bulk transfers over a congested switch."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Flow control adds latency when enabled",
        recommended_impact="Disabled: Lower latency for gaming",
        scope=SettingScope.RECOMMENDED,  # Noticeable benefit for network latency
        category_order=11,  # Per-adapter setting
        effect="Disabling removes hardware flow control latency",
        impact_scores={"latency_ms": -1.0, "stability": "medium"},
        # Detection - Use InterfaceIndex (numeric) for reliable command execution
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*FlowControl' -ErrorAction SilentlyContinue; "
            "if ($prop) { [int](@($prop.RegistryValue)[0]) } else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index, "batch_adapter_keyword": "*FlowControl"},
        # Map numeric registry values to choice names
        # Per Microsoft docs: 0=Disabled, 1=Tx Enabled, 2=Rx Enabled, 3=Rx & Tx Enabled
        value_map={
            0: "Disabled",
            "0": "Disabled",
            1: "Tx Enabled",
            "1": "Tx Enabled",
            2: "Rx Enabled",
            "2": "Rx Enabled",
            3: "Rx & Tx Enabled",
            "3": "Rx & Tx Enabled",
        },
        # Apply - use InterfaceIndex with explicit int cast and error handling
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*FlowControl' -ErrorAction Stop; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*FlowControl' -RegistryValue ([int]%value%) -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        # Per Microsoft docs: 0=Disabled, 1=Tx Enabled, 2=Rx Enabled, 3=Rx & Tx Enabled
        apply_value_map={
            "Disabled": 0,
            "Tx Enabled": 1,
            "Rx Enabled": 2,
            "Rx & Tx Enabled": 3,
        },
    )


def create_eee_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create an Energy Efficient Ethernet (EEE) setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    EEE (IEEE 802.3az) allows network adapters to enter low-power states during idle periods.
    Disabling EEE ensures the adapter is always at full speed with no wake-up latency.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for EEE control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:eee",
        category=SettingCategory.NETWORK,
        display_name=f"Energy Efficient Ethernet ({display_name})",
        description="IEEE 802.3az power saving. Disabling prevents latency spikes on idle-to-active transition.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "Keeps the PHY awake, so the adapter draws a little more power continuously. On a laptop on battery that is a real cost; on a desktop it is negligible."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Adapter sleeps during idle → 1-5ms wake-up latency on first packet",
        recommended_impact="Disabled: Adapter always active → no wake-up latency, instant response",
        scope=SettingScope.RECOMMENDED,  # Noticeable benefit for network latency
        category_order=12,  # Per-adapter setting
        effect="Disabling prevents adapter sleep for instant network response",
        impact_scores={"latency_ms": -3.0, "power_watts": 1.0, "stability": "high"},
        # Detection - Use InterfaceIndex (numeric) for reliable command execution
        # Intel: *EEE, Realtek: EEE, Broadcom: EEEControl
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$keywords = @('*EEE', 'EEE', 'EEEControl', 'EnergyEfficientEthernet'); "
            "$result = $null; "
            "foreach ($kw in $keywords) { "
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $kw -ErrorAction SilentlyContinue; "
            "if ($prop) { $result = [int]$prop.RegistryValue; break } "
            "}; "
            "if ($null -ne $result) { $result } else { 'not_supported' }"
        ),
        # The live command above probes four fixed spellings, one PowerShell call each
        # — measured at ~3.3 s. The prefetched snapshot already holds every keyword the
        # adapter publishes, so it can answer all four for free. Safe to batch
        # precisely because the candidates are a closed literal set: a setting whose
        # keyword is found by regex must stay on the live path, or a spelling missing
        # from the list would report "not supported" for hardware that has it.
        detect_args={
            "ifindex": interface_index,
            "batch_adapter_keyword": ["*EEE", "EEE", "EEEControl", "EnergyEfficientEthernet"],
        },
        # Map numeric registry values to choice names
        value_map={
            0: "Disabled",
            "0": "Disabled",
            1: "Enabled",
            "1": "Enabled",
        },
        # Apply - Try each keyword until one works
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "$keywords = @('*EEE', 'EEE', 'EEEControl', 'EnergyEfficientEthernet'); "
            "$regVal = if ('%value%' -eq 'Enabled') { 1 } else { 0 }; "
            "$success = $false; "
            "foreach ($kw in $keywords) { "
            "try { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $kw -RegistryValue $regVal -ErrorAction Stop; "
            "$success = $true; break "
            "} catch { }"
            "}; "
            "if ($success) { 'ok' } else { 'not_supported' }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},  # PowerShell handles conversion
    )


def create_power_management_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a power management setting for a specific network adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Controls whether Windows can turn off the network adapter to save power.
    For gaming, this should be disabled to maintain constant connectivity.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for power management control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:power_management",
        category=SettingCategory.NETWORK,
        display_name=f"Power Management ({display_name})",
        description="Allows Windows to turn off adapter to save power. Disabling prevents disconnects.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "Windows may no longer power the adapter down when idle, which costs a little power and prevents the link drops and reconnect stalls that the power-down causes."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Windows may disconnect adapter during idle → connection drops, 100-200ms resume delay",
        recommended_impact="Disabled: Adapter always on → stable connection, no resume latency",
        scope=SettingScope.RECOMMENDED,  # Noticeable benefit for connection stability
        category_order=13,  # Per-adapter setting
        effect="Disabling prevents adapter disconnects and resume delays",
        impact_scores={"latency_ms": -150.0, "stability": "high", "power_watts": 0.5},
        # Detection - Use InterfaceIndex to get adapter, then find PnP device
        # PnPCapabilities: 0 or absent = Enabled, 24 = Disabled
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "try { "
            "$adapter = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction Stop; "
            "$pnpDevice = Get-PnpDevice | Where-Object { $_.FriendlyName -eq $adapter.InterfaceDescription } | Select-Object -First 1; "
            "if ($pnpDevice) { "
            '$regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($pnpDevice.InstanceId)\\Device Parameters"; '
            "$val = (Get-ItemProperty -Path $regPath -Name 'PnPCapabilities' -ErrorAction SilentlyContinue).PnPCapabilities; "
            "if ($val -eq 24) { 'Disabled' } else { 'Enabled' } "
            "} else { 'Enabled' } "
            "} catch { 'Enabled' }"
        ),
        # Batched: Get-PnpDevice enumerates every device on the machine, so one
        # sweep answers every adapter. detect_command stays as the fallback for a
        # single-setting detect outside a scan.
        detect_args={"ifindex": interface_index, "batch_pnp_power": True},
        value_map={},  # Direct pass-through
        # Apply - Use InterfaceIndex, set PnPCapabilities registry
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$adapter = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction Stop; "
            "$pnpDevice = Get-PnpDevice | Where-Object { $_.FriendlyName -eq $adapter.InterfaceDescription } | Select-Object -First 1; "
            "if ($pnpDevice) { "
            '$regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($pnpDevice.InstanceId)\\Device Parameters"; '
            "$val = if ('%value%' -eq 'Disabled') { 24 } else { 0 }; "
            "Set-ItemProperty -Path $regPath -Name 'PnPCapabilities' -Value $val -Type DWord -Force -ErrorAction Stop; "
            "'ok' "
            "} else { 'not_supported' } "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},  # PowerShell handles conversion
    )


# === Network Throttling Index ===
# Windows throttles network traffic for multimedia applications
# Setting to max (0xFFFFFFFF) removes this limit
NETWORK_THROTTLING = SettingExecutor(
    id="network:throttling_index",
    category=SettingCategory.NETWORK,
    display_name="Network Throttling Index",
    description="Windows limits network bandwidth for multimedia. Disable for full speed.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service"
    ],
    risk_level="advanced",
    risk_warning="The throttle exists to reserve headroom for multimedia playback. Removing it "
    "lets bulk network traffic compete freely with audio, so heavy downloads during a game can "
    "introduce audio crackling. The gaming benefit is unmeasured on Windows 11 — this knob dates "
    "from an era of much slower links.",
    current_impact="Enabled: Windows limits network to 10 packets/ms for multimedia",
    recommended_impact="Disabled: No throttling → full network bandwidth available",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for bandwidth
    category_order=6,  # Bandwidth throttling
    effect="Removes Windows multimedia network throttling limit",
    impact_scores={"throughput": "high", "latency_ms": -1, "stability": "medium"},
    # Detection - Registry (uses NETWORK_THROTTLING_KEY constant)
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": NETWORK_THROTTLING_KEY,
        "name": "NetworkThrottlingIndex",
        "hive": "HKLM",
    },
    # 0xFFFFFFFF (4294967295) = disabled, 10 (default) = enabled
    value_map={
        0xFFFFFFFF: "disabled",
        "4294967295": "disabled",
        10: "enabled",
        "10": "enabled",
        None: "enabled",
    },
    # Apply
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": NETWORK_THROTTLING_KEY,
        "name": "NetworkThrottlingIndex",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0xFFFFFFFF, "enabled": 10},
)

# === DNS Security Setting ===
# Recommends Quad9 (9.9.9.9 / 149.112.112.112) with malware and phishing filtering.
# Cloudflare's resolvers stay available as choices; see the recommended_value note
# below for why the recommendation moved off them.
# NOTE: On any non-ISP choice the resolver sees every name this machine looks up.
# See: https://quad9.net/service/service-addresses-and-features/
DNS_SECURITY = SettingExecutor(
    id="network:dns_security",
    category=SettingCategory.NETWORK,
    # Named for what it recommends. It read "Secure DNS (Cloudflare)" while
    # recommending Quad9, because the recommendation moved and the label did not.
    display_name="Secure DNS (Quad9)",
    short_name="Secure DNS",
    description="Which resolver answers name lookups, and whether malware and phishing domains "
    "are blocked before they resolve. Quad9 filters those domains and returns the client-subnet "
    "hint a game CDN uses to pick a nearer edge for patch downloads, which the Cloudflare "
    "resolvers offered here do not send.",
    value_type=SettingValueType.CHOICE,
    choices=("isp", "cloudflare", "cloudflare_security", "cloudflare_family", "quad9"),
    default_value="isp",
    # Quad9 over Cloudflare Security, by user decision. The two are level on
    # lookup speed — measured here at median 7 ms against 8 ms over 25 domains
    # x 2 rounds with the servers interleaved, which is noise — and both filter
    # malware. Quad9 answers with EDNS Client Subnet where Cloudflare does not,
    # and that hint is what a CDN uses to pick an edge, so patch and asset
    # downloads steer to a nearer server. That is the tiebreak.
    recommended_value="quad9",
    requires_reboot=False,
    current_impact="ISP resolver: No malware filtering, and the provider sees every name resolved",
    recommended_impact="Quad9 9.9.9.9: Blocks malware and phishing domains, median lookup 7 ms, "
    "and sends the client-subnet hint a game CDN uses to pick a nearer edge",
    scope=SettingScope.RECOMMENDED,  # Security benefit
    category_order=7,  # DNS security
    effect="Blocks malware and phishing domains at the resolver",
    # latency_ms is deliberately 0.0, not the -12.0 this used to claim. That figure
    # was the deterministic cap applied by the impact_scores sweep, not a
    # measurement, and `lib/impact.ts` sums latency_ms into the user-visible
    # Gained/Potential headline -- so it was showing an invented 12 ms saving.
    # DNS cannot move in-game latency: resolution happens once at connect time and
    # match traffic goes straight to an IP. Measured here over 25 domains x 2
    # rounds, servers interleaved per domain (single vantage point, Turkey,
    # 100 Mbit): 1.1.1.2 median 8 ms / p99 295 ms, 1.1.1.1 median 7 ms / p99 28 ms.
    # The gain is on menu and page loads, and the cost is a fatter tail.
    #
    # `quad9` (9.9.9.9 / 149.112.112.112) is now the recommendation, and this
    # paragraph used to end "an additional choice, not a new default" — left
    # behind when the recommendation moved, so the file argued both sides at
    # once. The speed case is still a tie: measured in the same run at median
    # 7 ms against 1.1.1.2's 8 ms, which is noise, so speed is not the reason.
    # It wins on answering with EDNS Client Subnet where Cloudflare does not,
    # and that hint is what a CDN uses to pick an edge — a measurement
    # study across 10,923 hosts in 99 countries found ECS cut Akamai's median
    # latency by 40%, which is patch-download speed, not in-game ping.
    # Deliberately NOT offered: Quad9's ECS endpoint 9.9.9.11, measured p90
    # 267 ms here.
    impact_scores={"latency_ms": 0.0, "security": "high", "privacy": "improved"},
    # Detection - Get current DNS servers via PowerShell
    # IMPORTANT: Must use same filter as apply (physical adapters only) for consistent verification
    detect_type=DetectType.POWERSHELL,
    # Use numeric InterfaceOperationalStatus (1=Up) to avoid localization issues
    # Detection must observe everything apply writes, or it reports success over a
    # state that was never reached. The old version read `Select-Object -First 1`
    # and then only `ServerAddresses[0]`, while apply loops over every adapter:
    #   - one adapter drifting (Wi-Fi on ISP DNS, Ethernet on Cloudflare) was
    #     invisible, because only the first adapter was ever looked at
    #   - a resolver appended after apply was invisible, because only index 0 was
    #     compared. On the dev machine Ethernet held
    #     {1.1.1.2, 1.0.0.2, 192.168.1.1} and this reported cloudflare_security;
    #     any fallback to that third entry is unfiltered AND unencrypted.
    # A choice therefore holds only when *every* adapter apply would touch carries
    # exactly that resolver pair. Anything else reads as 'isp' -- the default --
    # so the UI shows it as needing apply, and applying rewrites the full list.
    detect_command=(
        "try { "
        "$result = 'isp'; "
        # Must match the apply filter exactly: physical adapters only.
        "$adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { "
        "[int]$_.InterfaceOperationalStatus -eq 1 -and "
        "-not $_.Virtual -and "
        "$_.InterfaceDescription -notlike '*Virtual*' -and "
        "$_.InterfaceDescription -notlike '*Hyper-V*' -and "
        "$_.InterfaceDescription -notlike '*VPN*' -and "
        "$_.InterfaceDescription -notlike '*Tunnel*' "
        "}); "
        "if ($adapters.Count -gt 0) { "
        # Values are pre-sorted so they can be compared against Sort-Object output.
        # Comparing the whole sorted list, not one element, is what makes an extra
        # resolver visible.
        "$expected = [ordered]@{ "
        "cloudflare_security = '1.0.0.2,1.1.1.2'; "
        "cloudflare_family = '1.0.0.3,1.1.1.3'; "
        "cloudflare = '1.0.0.1,1.1.1.1'; "
        "quad9 = '149.112.112.112,9.9.9.9' "
        "}; "
        "foreach ($name in $expected.Keys) { "
        "$allMatch = $true; "
        "foreach ($adapter in $adapters) { "
        "$dns = @((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex "
        "-AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses); "
        "if ($dns.Count -eq 0 -or ((($dns | Sort-Object) -join ',') -ne $expected[$name])) { "
        "$allMatch = $false; break "
        "} }; "
        "if ($allMatch) { $result = $name; break } "
        "} }; $result "
        "} catch { 'isp' }"
    ),
    detect_args={},
    value_map={},  # Direct pass-through
    # Apply - Set DNS servers on physical adapters only (exclude VPN, virtual, Hyper-V)
    # Use numeric InterfaceOperationalStatus (1=Up) to avoid localization issues
    # After DNS change, flush cache and register with DHCP to ensure immediate effect
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$adapters = Get-NetAdapter | Where-Object { "
        "[int]$_.InterfaceOperationalStatus -eq 1 -and "
        "-not $_.Virtual -and "
        "$_.InterfaceDescription -notlike '*Virtual*' -and "
        "$_.InterfaceDescription -notlike '*Hyper-V*' -and "
        "$_.InterfaceDescription -notlike '*VPN*' -and "
        "$_.InterfaceDescription -notlike '*Tunnel*' "
        "}; "
        "$changed = 0; "
        "foreach ($adapter in $adapters) { "
        "if ('%value%' -eq 'cloudflare_security') { "
        "Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ('1.1.1.2','1.0.0.2'); "
        "$changed++ "
        "} elseif ('%value%' -eq 'cloudflare_family') { "
        "Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ('1.1.1.3','1.0.0.3'); "
        "$changed++ "
        "} elseif ('%value%' -eq 'cloudflare') { "
        "Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ('1.1.1.1','1.0.0.1'); "
        "$changed++ "
        "} elseif ('%value%' -eq 'quad9') { "
        "Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ('9.9.9.9','149.112.112.112'); "
        "$changed++ "
        "} else { "
        # Reset to DHCP: clear manual DNS, flush cache, register with DHCP
        "Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses; "
        "$changed++ "
        "} }; "
        # Flush DNS cache and register with DHCP for immediate effect
        "Clear-DnsClientCache -ErrorAction SilentlyContinue; "
        "Register-DnsClient -ErrorAction SilentlyContinue; "
        "if ($changed -gt 0) { 'ok' } else { 'no_adapters_found' }"
    ),
    apply_args={},
    apply_value_map={},
    # Skip verification for 'default' value since DHCP DNS may take time to propagate
    # The reset itself is successful, but detection might still show old DNS temporarily
)


# === DNS over HTTPS ===
# Setting the resolver addresses is only half of a private lookup: without DoH the
# queries still leave the machine as plaintext UDP/53, so the ISP (or anyone on the
# path) sees and can rewrite every name the machine resolves, and the malware
# filtering the resolver provides can be stripped.
#
# Two registry surfaces are involved and BOTH are required. Measured on the dev
# machine: `netsh dns add encryption` had registered 16 templates and DoH was still
# not in use, because no adapter carried an interface entry.
#   1. The template table (Dnscache\Parameters\DohWellKnownServers) maps a resolver
#      IP to its DoH URL. Windows ships templates for 1.1.1.1, 8.8.8.8, 9.9.9.9 and
#      friends but NOT for Cloudflare's filtered 1.1.1.2/1.1.1.3 -- which is also
#      why the Windows Settings UI offers no encryption option after fpstune's
#      dns_security applies. Handled by Add-DnsClientDohServerAddress.
#   2. The per-interface flag, which has no cmdlet:
#      Dnscache\InterfaceSpecificParameters\<GUID>\DohInterfaceSettings\Doh\<ip>
#      DohFlags (REG_QWORD). Keyed by adapter GUID, which is the immutable
#      identifier C5 asks for.
#
# DohFlags = 2 is MEASURED, not taken from a guide: enabling DoH through the
# Windows UI with the automatic template and plaintext fallback disabled makes
# Windows write exactly 2, and DoH is then confirmed active. EnableAutoDoh is not
# set on that machine and DoH works regardless, so this does not touch it.
_DOH_TEMPLATES = {
    # Cloudflare, including the filtered variants Windows does not ship
    "1.1.1.1": "https://cloudflare-dns.com/dns-query",
    "1.0.0.1": "https://cloudflare-dns.com/dns-query",
    "1.1.1.2": "https://security.cloudflare-dns.com/dns-query",
    "1.0.0.2": "https://security.cloudflare-dns.com/dns-query",
    "1.1.1.3": "https://family.cloudflare-dns.com/dns-query",
    "1.0.0.3": "https://family.cloudflare-dns.com/dns-query",
    # Quad9 and Google, so the setting still works if the user picks those
    "9.9.9.9": "https://dns.quad9.net/dns-query",
    "149.112.112.112": "https://dns.quad9.net/dns-query",
    "8.8.8.8": "https://dns.google/dns-query",
    "8.8.4.4": "https://dns.google/dns-query",
}

# Identical to dns_security's filter. Sharing the text is what stops the two
# settings disagreeing about which adapters count, which is the defect fixed in
# dns_security's own detect (it read one adapter while apply wrote all of them).
_PHYSICAL_ADAPTER_FILTER = (
    "Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { "
    "[int]$_.InterfaceOperationalStatus -eq 1 -and "
    "-not $_.Virtual -and "
    "$_.InterfaceDescription -notlike '*Virtual*' -and "
    "$_.InterfaceDescription -notlike '*Hyper-V*' -and "
    "$_.InterfaceDescription -notlike '*VPN*' -and "
    "$_.InterfaceDescription -notlike '*Tunnel*' "
    "}"
)

_DOH_TEMPLATE_TABLE_PS = "; ".join(
    f"'{address}' = '{template}'" for address, template in _DOH_TEMPLATES.items()
)

_DOH_INTERFACE_KEY_PS = (
    "'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Dnscache"
    "\\InterfaceSpecificParameters\\' + $guid + '\\DohInterfaceSettings\\Doh\\' + $server"
)

DNS_OVER_HTTPS = SettingExecutor(
    id="network:dns_over_https",
    category=SettingCategory.NETWORK,
    display_name="Encrypted DNS (DNS over HTTPS)",
    short_name="DNS over HTTPS",
    description="Sends DNS queries over HTTPS instead of plaintext UDP port 53. Without it the "
    "chosen resolver is visible to the network and its malware filtering can be stripped in "
    "transit.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "enabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Disabled: DNS queries leave the machine as readable plaintext on port 53",
    recommended_impact="Enabled: Queries are encrypted, so the resolver's filtering cannot be "
    "stripped on the path",
    scope=SettingScope.RECOMMENDED,
    category_order=8,  # Immediately after dns_security, which it completes
    effect="Encrypts DNS queries so they cannot be read or rewritten in transit",
    # No FPS or ping claim: resolution happens at connect time and match traffic
    # goes straight to an IP, so this cannot move in-game latency. The measurable
    # cost is a one-off TLS handshake per resolver, which lands on menu and page
    # loads, not gameplay.
    impact_scores={"latency_ms": 0.0, "security": "high", "privacy": "high"},
    evidence_level="proven",
    risk_level="low",
    sources=[
        "https://developers.cloudflare.com/1.1.1.1/setup/",
        "https://learn.microsoft.com/en-us/windows-server/networking/dns/doh-client-support",
    ],
    detect_type=DetectType.POWERSHELL,
    # Reads the per-interface flag, never the template table. A registered template
    # with no interface entry does nothing at all, and reporting on the table would
    # have called the dev machine's dead configuration "enabled".
    # Windows writes the entry for the PRIMARY resolver only, so requiring one for
    # every configured address would be stricter than Windows itself and would read
    # a working setup as unapplied.
    detect_command=(
        "try { "
        "$result = 'disabled'; "
        f"$adapters = @({_PHYSICAL_ADAPTER_FILTER}); "
        "if ($adapters.Count -gt 0) { "
        "$allOn = $true; "
        "foreach ($adapter in $adapters) { "
        "$servers = @((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex "
        "-AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses); "
        "if ($servers.Count -eq 0) { $allOn = $false; break } "
        "$guid = $adapter.InterfaceGuid; $server = $servers[0]; "
        f"$key = {_DOH_INTERFACE_KEY_PS}; "
        "$flags = $null; "
        "if (Test-Path -LiteralPath $key) { "
        "$flags = (Get-ItemProperty -LiteralPath $key -Name DohFlags "
        "-ErrorAction SilentlyContinue).DohFlags "
        "} "
        "if (-not $flags) { $allOn = $false; break } "
        "}; "
        "if ($allOn) { $result = 'enabled' } "
        "}; $result "
        "} catch { 'disabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    # Registers the template for every configured resolver it knows, then writes the
    # interface flag. Resolvers with no known template are counted and reported
    # rather than skipped silently -- a partial result must not read as success.
    apply_command=(
        "try { "
        f"$templates = @{{ {_DOH_TEMPLATE_TABLE_PS} }}; "
        f"$adapters = @({_PHYSICAL_ADAPTER_FILTER}); "
        "$done = 0; $unknown = 0; "
        "foreach ($adapter in $adapters) { "
        "$guid = $adapter.InterfaceGuid; "
        "$servers = @((Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex "
        "-AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses); "
        "foreach ($server in $servers) { "
        f"$key = {_DOH_INTERFACE_KEY_PS}; "
        "if ('%value%' -eq 'enabled') { "
        "$template = $templates[$server]; "
        "if (-not $template) { $unknown++; continue } "
        "if (-not (Get-DnsClientDohServerAddress -ServerAddress $server "
        "-ErrorAction SilentlyContinue)) { "
        "Add-DnsClientDohServerAddress -ServerAddress $server -DohTemplate $template "
        "-AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction SilentlyContinue | Out-Null "
        "}; "
        "New-Item -Path $key -Force -ErrorAction Stop | Out-Null; "
        # 2 = the value Windows writes for "known template, no plaintext fallback",
        # measured rather than assumed.
        "New-ItemProperty -Path $key -Name DohFlags -Value 2 -PropertyType QWord -Force "
        "-ErrorAction Stop | Out-Null; "
        "$done++ "
        "} else { "
        "if (Test-Path -LiteralPath $key) { "
        "Remove-Item -LiteralPath $key -Recurse -Force -ErrorAction SilentlyContinue; $done++ "
        "} } } }; "
        "Clear-DnsClientCache -ErrorAction SilentlyContinue; "
        "if ($done -gt 0) { 'ok' } "
        "elseif ($unknown -gt 0) { 'error:no DoH template known for the configured resolvers' } "
        "else { 'error:no applicable adapter found' } "
        "} catch { 'error:' + $_.Exception.Message }"
    ),
    apply_args={},
    apply_value_map={},
)


# === Nagle's Algorithm (Physical adapters only) ===
# TcpNoDelay=1, TcpAckFrequency=1, TcpDelAckTicks=0 per interface
# Only applies to interfaces with DefaultGateway or DhcpDefaultGateway (active connections)
# to avoid affecting VPN, WSL, Hyper-V, etc.
# NOTE: DHCP-configured interfaces use DhcpDefaultGateway, not DefaultGateway
NAGLE_ALGORITHM = SettingExecutor(
    id="network:nagle_algorithm",
    category=SettingCategory.NETWORK,
    display_name="Nagle's Algorithm (TcpNoDelay)",
    short_name="Nagle",
    description="TCP small-packet batching, disabled via TcpNoDelay. Nagle never touches UDP, "
    "and essentially every modern competitive title is UDP, so this changes nothing for them.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    # Was "disabled". fpstune's own risk_warning already ended with "Remove the
    # values to restore Windows behaviour" while the recommendation told it to
    # write them — the copy and the action disagreed. The recommendation now
    # matches the research: Nagle never touches UDP, every modern competitive
    # title is UDP, most TCP titles set TCP_NODELAY themselves (which overrides
    # this key anyway), and forcing it costs download throughput. TCP Optimizer,
    # arriving at this independently, deletes these values too.
    # It stays as a setting so fpstune can remove the keys from the machines its
    # own earlier recommendation wrote them to — applying "enabled" deletes them.
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="low",
    risk_warning="Benefit applies only to TCP-based titles, and most of those already set "
    "TCP_NODELAY themselves — an application-level socket option overrides this registry key. "
    "It is not free: acknowledging every segment burns upstream bandwidth and lowers download "
    "throughput. Microsoft advises against changing the default without studying the specific "
    "environment, and a crash has been reported after a new interface appeared while these keys "
    "were set. Remove the values to restore Windows behaviour.",
    sources=[
        "https://brooker.co.za/blog/2024/05/09/nagle.html",
        "https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/registry-entry-control-tcp-acknowledgment-behavior",
    ],
    current_impact="Enabled: Small TCP writes batched briefly — no effect on UDP game traffic",
    recommended_impact="Disabled: Small TCP packets sent immediately — helps TCP titles only",
    # Demoted from ESSENTIAL in the 2026-08 audit: a tweak that does nothing for
    # UDP traffic cannot sit in the preset meant for proven, universal wins.
    scope=SettingScope.COMPLETE,
    category_order=2,  # Right after auto-tuning
    effect="Sets TcpNoDelay=1 to disable Nagle's algorithm (physical adapters only)",
    impact_scores={"latency_ms": "0 to -5 (TCP titles only)", "download_throughput": "reduced"},
    # Detection - Check TcpNoDelay on interfaces with gateway (static or DHCP)
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$interfaces = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces' -ErrorAction SilentlyContinue; "
        "$result = 'enabled'; "
        "foreach ($iface in $interfaces) { "
        "$props = Get-ItemProperty -Path $iface.PSPath -ErrorAction SilentlyContinue; "
        # Check both static (DefaultGateway) and DHCP (DhcpDefaultGateway) configurations
        "$hasGateway = ($props.DefaultGateway -and $props.DefaultGateway.Count -gt 0) -or "
        "($props.DhcpDefaultGateway -and $props.DhcpDefaultGateway.Length -gt 0); "
        "if ($hasGateway -and $props.TcpNoDelay -eq 1) { $result = 'disabled'; break } "
        "}; "
        "$result"
    ),
    detect_args={},
    value_map={},
    # Apply - Only manages TcpNoDelay (Nagle's algorithm itself).
    # TcpAckFrequency and TcpDelAckTicks are separate tweaks.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$interfaces = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces' -ErrorAction SilentlyContinue; "
        "$changed = 0; "
        "foreach ($iface in $interfaces) { "
        "$props = Get-ItemProperty -Path $iface.PSPath -ErrorAction SilentlyContinue; "
        # Check both static (DefaultGateway) and DHCP (DhcpDefaultGateway) configurations
        "$hasGateway = ($props.DefaultGateway -and $props.DefaultGateway.Count -gt 0) -or "
        "($props.DhcpDefaultGateway -and $props.DhcpDefaultGateway.Length -gt 0); "
        "if ('%value%' -eq 'disabled' -and $hasGateway) { "
        "Set-ItemProperty -Path $iface.PSPath -Name 'TcpNoDelay' -Value 1 -Type DWord -Force; "
        "$changed++ "
        "} elseif ('%value%' -eq 'enabled' -and $hasGateway) { "
        "Remove-ItemProperty -Path $iface.PSPath -Name 'TcpNoDelay' -ErrorAction SilentlyContinue; "
        "$changed++ "
        "} }; "
        "if ($changed -gt 0) { 'ok' } else { 'no_interfaces_found' }"
    ),
    apply_args={},
    apply_value_map={},
)

# === TCP ACK Frequency ===
# Controls how many data segments to wait before sending an ACK.
# Value 1 = send ACK for every received segment (immediate feedback).
# Per-interface registry key, only on active physical connections.
TCP_ACK_FREQUENCY = SettingExecutor(
    id="network:tcp_ack_frequency",
    category=SettingCategory.NETWORK,
    display_name="TCP ACK Frequency",
    short_name="ACK Freq",
    description="Segments to wait before acknowledging (TcpAckFrequency); Windows defaults to 2 "
    "and 1 acknowledges every segment. Affects TCP only, so UDP game traffic is untouched.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "immediate"),
    default_value="default",
    # Was "immediate" — see NAGLE_ALGORITHM. The copy already said to delete the
    # value; the recommendation now agrees, and applying "default" removes it.
    recommended_value="default",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="low",
    risk_warning="Acknowledging every segment consumes upstream bandwidth and measurably lowers "
    "download throughput on bulk transfers, in exchange for a benefit that reaches TCP titles "
    "only. Microsoft documents the default as 2 and advises against changing it without studying "
    "the environment. Delete the value to restore Windows behaviour.",
    sources=[
        "https://brooker.co.za/blog/2024/05/09/nagle.html",
        "https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/registry-entry-control-tcp-acknowledgment-behavior",
    ],
    current_impact="Default (2): ACK after 2 segments or timeout — no effect on UDP traffic",
    recommended_impact="Immediate (1): ACK per segment — faster TCP feedback, less download headroom",
    # Demoted from ESSENTIAL in the 2026-08 audit; see NAGLE_ALGORITHM.
    scope=SettingScope.COMPLETE,
    category_order=2,
    effect="Sets TcpAckFrequency=1 for per-segment ACK on physical interfaces",
    impact_scores={"latency_ms": "0 to -2 (TCP titles only)", "download_throughput": "reduced"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$interfaces = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces' -ErrorAction SilentlyContinue; "
        "$result = 'default'; "
        "foreach ($iface in $interfaces) { "
        "$props = Get-ItemProperty -Path $iface.PSPath -ErrorAction SilentlyContinue; "
        "$hasGateway = ($props.DefaultGateway -and $props.DefaultGateway.Count -gt 0) -or "
        "($props.DhcpDefaultGateway -and $props.DhcpDefaultGateway.Length -gt 0); "
        "if ($hasGateway -and $props.TcpAckFrequency -eq 1) { $result = 'immediate'; break } "
        "}; "
        "$result"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$interfaces = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces' -ErrorAction SilentlyContinue; "
        "$changed = 0; "
        "foreach ($iface in $interfaces) { "
        "$props = Get-ItemProperty -Path $iface.PSPath -ErrorAction SilentlyContinue; "
        "$hasGateway = ($props.DefaultGateway -and $props.DefaultGateway.Count -gt 0) -or "
        "($props.DhcpDefaultGateway -and $props.DhcpDefaultGateway.Length -gt 0); "
        "if ('%value%' -eq 'immediate' -and $hasGateway) { "
        "Set-ItemProperty -Path $iface.PSPath -Name 'TcpAckFrequency' -Value 1 -Type DWord -Force; "
        "$changed++ "
        "} elseif ('%value%' -eq 'default' -and $hasGateway) { "
        "Remove-ItemProperty -Path $iface.PSPath -Name 'TcpAckFrequency' -ErrorAction SilentlyContinue; "
        "$changed++ "
        "} }; "
        "if ($changed -gt 0) { 'ok' } else { 'no_interfaces_found' }"
    ),
    apply_args={},
    apply_value_map={},
    value_hints={"default": "not set", "immediate": "1"},
)

# === TCP Delayed ACK Ticks ===
# TcpDelAckTicks controls the delayed ACK timer in 10ms increments.
# Value 0 disables the timer entirely so ACKs are sent without delay.
# Per-interface registry key, only on active physical connections.
TCP_DEL_ACK_TICKS = SettingExecutor(
    id="network:tcp_del_ack_ticks",
    category=SettingCategory.NETWORK,
    display_name="TCP Delayed ACK Timer",
    short_name="Del ACK",
    # Microsoft documents TcpDelAckTicks in 100 ms intervals, range 0-6, default 2.
    # This file previously described the unit as 10 ms, which understated the timer
    # by a factor of ten in user-facing text.
    description="Delayed ACK timer in 100ms intervals (TcpDelAckTicks); Windows defaults to 2 "
    "and 0 disables it. A Windows 2000-era key that affects TCP only, not UDP game traffic.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "disabled"),
    default_value="default",
    # Was "disabled" — see NAGLE_ALGORITHM. A Windows 2000-era key that the copy
    # already told users to delete; the recommendation now says the same.
    recommended_value="default",
    requires_reboot=False,
    evidence_level="proven",
    risk_level="low",
    risk_warning="A legacy key predating the post-Vista TCP stack rework, and it does nothing for "
    "the UDP traffic modern games use. Disabling the timer forces more frequent acknowledgements, "
    "which costs upstream bandwidth and download throughput. Microsoft advises against changing "
    "the default without studying the environment. Delete the value to restore Windows behaviour.",
    sources=[
        "https://brooker.co.za/blog/2024/05/09/nagle.html",
        "https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/registry-entry-control-tcp-acknowledgment-behavior",
    ],
    current_impact="Default (2): 200ms delayed ACK timer — no effect on UDP traffic",
    recommended_impact="Disabled (0): ACK sent on segment receipt — helps TCP titles only",
    # Demoted from ESSENTIAL in the 2026-08 audit; see NAGLE_ALGORITHM.
    scope=SettingScope.COMPLETE,
    category_order=2,
    effect="Sets TcpDelAckTicks=0 to disable delayed ACK timer on physical interfaces",
    impact_scores={"latency_ms": "0 to -2 (TCP titles only)", "download_throughput": "reduced"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$interfaces = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces' -ErrorAction SilentlyContinue; "
        "$result = 'default'; "
        "foreach ($iface in $interfaces) { "
        "$props = Get-ItemProperty -Path $iface.PSPath -ErrorAction SilentlyContinue; "
        "$hasGateway = ($props.DefaultGateway -and $props.DefaultGateway.Count -gt 0) -or "
        "($props.DhcpDefaultGateway -and $props.DhcpDefaultGateway.Length -gt 0); "
        "if ($hasGateway -and $null -ne $props.TcpDelAckTicks -and [int]$props.TcpDelAckTicks -eq 0) { $result = 'disabled'; break } "
        "}; "
        "$result"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$interfaces = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces' -ErrorAction SilentlyContinue; "
        "$changed = 0; "
        "foreach ($iface in $interfaces) { "
        "$props = Get-ItemProperty -Path $iface.PSPath -ErrorAction SilentlyContinue; "
        "$hasGateway = ($props.DefaultGateway -and $props.DefaultGateway.Count -gt 0) -or "
        "($props.DhcpDefaultGateway -and $props.DhcpDefaultGateway.Length -gt 0); "
        "if ('%value%' -eq 'disabled' -and $hasGateway) { "
        "Set-ItemProperty -Path $iface.PSPath -Name 'TcpDelAckTicks' -Value 0 -Type DWord -Force; "
        "$changed++ "
        "} elseif ('%value%' -eq 'default' -and $hasGateway) { "
        "Remove-ItemProperty -Path $iface.PSPath -Name 'TcpDelAckTicks' -ErrorAction SilentlyContinue; "
        "$changed++ "
        "} }; "
        "if ($changed -gt 0) { 'ok' } else { 'no_interfaces_found' }"
    ),
    apply_args={},
    apply_value_map={},
    value_hints={"default": "not set", "disabled": "0"},
)

# === Host Resolution Priority (split into 4 single-value tweaks) ===
# Controls DNS lookup order: Local cache → Hosts file → DNS → NetBIOS
# Lower numeric value = higher priority in the resolver chain.
# Default: Local=499, Hosts=500, DNS=2000, Netbt=2001
# Optimized: Local=4, Hosts=5, DNS=6, Netbt=7  (cache-first order)

DNS_LOCAL_PRIORITY = SettingExecutor(
    id="network:dns_local_priority",
    category=SettingCategory.NETWORK,
    display_name="DNS Local Cache Priority (LocalPriority)",
    short_name="Local Priority",
    description="Local resolver cache lookup priority. Lower = checked earlier. Optimized: 4 (default: 499).",
    value_type=SettingValueType.CHOICE,
    choices=("standard", "optimized"),
    default_value="standard",
    recommended_value="optimized",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Standard (499): Local cache checked after other resolvers → slower DNS hits",
    recommended_impact="Optimized (4): Local cache checked first → fastest possible DNS resolution",
    scope=SettingScope.RECOMMENDED,
    category_order=8,
    effect="Sets LocalPriority=4 so local DNS cache is consulted first",
    impact_scores={"latency_ms": -1, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": SERVICE_PROVIDER_KEY, "name": "LocalPriority", "hive": "HKLM"},
    value_map={
        4: "optimized",
        "4": "optimized",
        499: "standard",
        "499": "standard",
        None: "standard",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": SERVICE_PROVIDER_KEY,
        "name": "LocalPriority",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 4, "standard": 499},
    value_hints={"standard": "499", "optimized": "4"},
)

DNS_HOSTS_PRIORITY = SettingExecutor(
    id="network:dns_hosts_priority",
    category=SettingCategory.NETWORK,
    display_name="DNS Hosts File Priority (HostsPriority)",
    short_name="Hosts Priority",
    description="Hosts file lookup priority. Lower = checked earlier. Optimized: 5 (default: 500).",
    value_type=SettingValueType.CHOICE,
    choices=("standard", "optimized"),
    default_value="standard",
    recommended_value="optimized",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Standard (500): Hosts file checked after cache miss with low priority",
    recommended_impact="Optimized (5): Hosts file checked second → overrides apply faster",
    scope=SettingScope.RECOMMENDED,
    category_order=8,
    effect="Sets HostsPriority=5 so hosts file overrides are applied immediately after cache",
    impact_scores={"latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": SERVICE_PROVIDER_KEY, "name": "HostsPriority", "hive": "HKLM"},
    value_map={
        5: "optimized",
        "5": "optimized",
        500: "standard",
        "500": "standard",
        None: "standard",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": SERVICE_PROVIDER_KEY,
        "name": "HostsPriority",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 5, "standard": 500},
    value_hints={"standard": "500", "optimized": "5"},
)

DNS_QUERY_PRIORITY = SettingExecutor(
    id="network:dns_query_priority",
    category=SettingCategory.NETWORK,
    display_name="DNS Server Query Priority (DnsPriority)",
    short_name="DNS Priority",
    description="DNS server query priority. Lower = queried earlier. Optimized: 6 (default: 2000).",
    value_type=SettingValueType.CHOICE,
    choices=("standard", "optimized"),
    default_value="standard",
    recommended_value="optimized",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Standard (2000): DNS server queried late → slow cold-start resolution",
    recommended_impact="Optimized (6): DNS queried early → faster cold-start name resolution",
    scope=SettingScope.RECOMMENDED,
    category_order=8,
    effect="Sets DnsPriority=6 to bring DNS server queries earlier in the resolver chain",
    impact_scores={"latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": SERVICE_PROVIDER_KEY, "name": "DnsPriority", "hive": "HKLM"},
    value_map={
        6: "optimized",
        "6": "optimized",
        2000: "standard",
        "2000": "standard",
        None: "standard",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": SERVICE_PROVIDER_KEY,
        "name": "DnsPriority",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 6, "standard": 2000},
    value_hints={"standard": "2000", "optimized": "6"},
)

DNS_NETBT_PRIORITY = SettingExecutor(
    id="network:dns_netbt_priority",
    category=SettingCategory.NETWORK,
    display_name="NetBIOS Name Resolution Priority (NetbtPriority)",
    short_name="NetBT Priority",
    description="NetBIOS resolution priority. Lower = queried earlier. Optimized: 7 (default: 2001).",
    value_type=SettingValueType.CHOICE,
    choices=("standard", "optimized"),
    default_value="standard",
    recommended_value="optimized",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Standard (2001): NetBIOS queried last by default ordering",
    recommended_impact="Optimized (7): NetBIOS queried after DNS in the new priority order",
    scope=SettingScope.RECOMMENDED,
    category_order=8,
    effect="Sets NetbtPriority=7 to maintain correct resolver order after other priority tweaks",
    impact_scores={"latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": SERVICE_PROVIDER_KEY, "name": "NetbtPriority", "hive": "HKLM"},
    value_map={
        7: "optimized",
        "7": "optimized",
        2001: "standard",
        "2001": "standard",
        None: "standard",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": SERVICE_PROVIDER_KEY,
        "name": "NetbtPriority",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 7, "standard": 2001},
    value_hints={"standard": "2001", "optimized": "7"},
)

# === QoS Bandwidth Reservation (split into 2 single-value tweaks) ===

# Part 1: NonBestEffortLimit — caps the % of bandwidth Windows reserves for QoS.
# 0 = no reservation (all bandwidth available), default is 10-20% reserved.
QOS_BANDWIDTH = SettingExecutor(
    id="network:qos_bandwidth",
    category=SettingCategory.NETWORK,
    display_name="QoS Bandwidth Reservation (NonBestEffortLimit)",
    short_name="QoS Bandwidth",
    description="% of bandwidth Windows reserves for QoS (NonBestEffortLimit). 0 = no reservation.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="The popular claim that Windows permanently reserves 20% of your bandwidth is a "
    "myth: the reserve is only claimed while an application actively requests QoS, and is "
    "released otherwise. Setting the limit to 0 therefore recovers little or nothing on a normal "
    "desktop, while removing the headroom that VoIP and conferencing apps rely on to stay smooth.",
    current_impact="Enabled: Reserve available to apps that request QoS — unused otherwise",
    recommended_impact="Disabled (0): No reservation possible → recovers little on a normal desktop",
    scope=SettingScope.RECOMMENDED,
    category_order=9,
    effect="Sets NonBestEffortLimit=0 to remove Windows QoS bandwidth reservation",
    impact_scores={"throughput": "low", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": PSCHED_KEY, "name": "NonBestEffortLimit", "hive": "HKLM"},
    value_map={0: "disabled", "0": "disabled", 10: "enabled", 20: "enabled", None: "enabled"},
    # Single-setting apply: only NonBestEffortLimit. QoS NLA flag is a separate tweak.
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$pschedPath = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Psched'; "
        "if (-not (Test-Path $pschedPath)) { New-Item -Path $pschedPath -Force | Out-Null }; "
        "if ('%value%' -eq 'disabled') { "
        "Set-ItemProperty -Path $pschedPath -Name 'NonBestEffortLimit' -Value 0 -Type DWord -Force "
        "} else { "
        "Remove-ItemProperty -Path $pschedPath -Name 'NonBestEffortLimit' -ErrorAction SilentlyContinue "
        "}; 'ok'"
    ),
    apply_args={},
    apply_value_map={},
)

# Part 2: QoS NLA flag — tells the QoS subsystem to not use Network Location Awareness.
# This prevents QoS from throttling traffic on "non-home" networks.
QOS_NLA = SettingExecutor(
    id="network:qos_nla",
    category=SettingCategory.NETWORK,
    display_name="QoS NLA Override (Do not use NLA)",
    short_name="QoS NLA",
    description="Prevents QoS from throttling on non-home networks. Sets 'Do not use NLA'=1.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Bypassing Network Location Awareness makes QoS policies apply on every network "
    "profile, including public and corporate ones. On a managed network this can conflict with "
    "policy pushed by the domain, and it removes the profile-based separation that stops home "
    "rules from following you onto untrusted networks.",
    current_impact="Enabled: QoS may throttle on non-home network profiles",
    recommended_impact="Disabled (NLA bypassed): QoS behaves consistently on all networks",
    scope=SettingScope.RECOMMENDED,
    category_order=9,
    effect="Sets QoS 'Do not use NLA'=1 to prevent network-profile-based throttling",
    impact_scores={"throughput": "low", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": QOS_KEY, "name": "Do not use NLA", "hive": "HKLM"},
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$qosPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\QoS'; "
        "if (-not (Test-Path $qosPath)) { New-Item -Path $qosPath -Force | Out-Null }; "
        "if ('%value%' -eq 'disabled') { "
        "Set-ItemProperty -Path $qosPath -Name 'Do not use NLA' -Value 1 -Type DWord -Force "
        "} else { "
        "Remove-ItemProperty -Path $qosPath -Name 'Do not use NLA' -ErrorAction SilentlyContinue "
        "}; 'ok'"
    ),
    apply_args={},
    apply_value_map={},
)

# === IPv6 Privacy Extension ===
IPV6_PRIVACY = SettingExecutor(
    id="network:ipv6_privacy",
    category=SettingCategory.NETWORK,
    display_name="IPv6 Privacy Extension",
    short_name="IPv6 Privacy",
    description="Creates temporary IPv6 addresses for privacy. Disabling reduces overhead.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="This is a privacy regression, not just a performance setting. RFC 4941 temporary "
    "addresses exist so remote servers cannot correlate your traffic across sessions; disabling "
    "them makes your machine present one stable IPv6 address that follows you and is trivially "
    "loggable. The overhead removed is negligible on any modern system.",
    current_impact="Enabled: Temporary IPv6 addresses rotate → traffic cannot be correlated",
    recommended_impact="Disabled: Fixed IPv6 address → less overhead, stable connections",
    scope=SettingScope.COMPLETE,  # Minor benefit
    category_order=20,
    effect="Disabling reduces IPv6 address generation overhead",
    impact_scores={"latency_ms": 0, "privacy": "reduced"},
    # Detection
    detect_type=DetectType.NETSH,
    detect_command="interface ipv6 show privacy",
    detect_args={"parse_key": "use temporary addresses"},
    value_map={},
    # Apply
    apply_type=DetectType.NETSH,
    apply_command="interface ipv6 set privacy state=%value%",
    apply_args={},
    apply_value_map={},
)

# === IPv6 Random Identifiers ===
IPV6_RANDOM_IDS = SettingExecutor(
    id="network:ipv6_random_identifiers",
    category=SettingCategory.NETWORK,
    display_name="IPv6 Random Identifiers",
    short_name="IPv6 Random IDs",
    description="Randomizes IPv6 interface identifiers. Disabling provides stable connections.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Also a privacy regression: with randomisation off, the IPv6 interface identifier "
    "is derived from your MAC address, so the same device fingerprint travels with you onto every "
    "network you join. The claimed connection-stability benefit is anecdotal.",
    current_impact="Enabled: Random interface IDs → device is not identifiable across networks",
    recommended_impact="Disabled: Consistent IDs → stable, predictable connections",
    scope=SettingScope.COMPLETE,  # Minor benefit
    category_order=21,
    effect="Disabling provides consistent IPv6 interface identifiers",
    impact_scores={"latency_ms": 0, "stability": "improved"},
    # Detection
    detect_type=DetectType.NETSH,
    detect_command="interface ipv6 show global",
    detect_args={"parse_key": "randomize identifiers"},
    value_map={},
    # Apply
    apply_type=DetectType.NETSH,
    apply_command="interface ipv6 set global randomizeidentifiers=%value%",
    apply_args={},
    apply_value_map={},
)

# === Teredo Tunneling ===
TEREDO = SettingExecutor(
    id="network:teredo",
    category=SettingCategory.NETWORK,
    display_name="Teredo Tunneling",
    short_name="Teredo",
    description="IPv6 tunneling over IPv4 NAT. Not needed for gaming, adds latency when active.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",  # Windows 11 default is effectively disabled
    recommended_value="disabled",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    current_impact="Enabled: IPv6 tunneled over IPv4 → extra latency when active",
    recommended_impact="Disabled: No tunneling overhead → cleaner network stack",
    scope=SettingScope.COMPLETE,  # Minor benefit
    category_order=22,
    effect="Disabling removes IPv6-over-IPv4 tunneling overhead",
    impact_scores={"latency_ms": 0, "stability": "improved"},
    # Detection
    detect_type=DetectType.NETSH,
    detect_command="interface teredo show state",
    detect_args={"parse_key": "type"},
    # netsh returns: default, client, enterpriseclient, relay, server, none, disabled, nondomain
    # Active types → "enabled", inactive types → "disabled"
    value_map={
        "default": "enabled",
        "client": "enabled",
        "enterpriseclient": "enabled",
        "relay": "enabled",
        "server": "enabled",
        "none": "disabled",
        "disabled": "disabled",
        "nondomain": "disabled",
    },
    # Apply - Use type= prefix for proper netsh syntax
    apply_type=DetectType.NETSH,
    apply_command="interface teredo set state type=%value%",
    apply_args={},
    # Map our choices to netsh values
    apply_value_map={
        "enabled": "default",  # "default" tells Windows to enable teredo
        "disabled": "disabled",
    },
)


# === Per-Adapter Setting Factories (continued) ===


def create_roaming_aggressiveness_setting(
    interface_index: int, display_name: str
) -> SettingExecutor:
    """Create a WiFi roaming aggressiveness setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Controls how aggressively the WiFi adapter scans for better access points.
    For gaming, use lowest to minimize scanning interruptions.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for roaming aggressiveness.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:roaming_aggressiveness",
        category=SettingCategory.NETWORK,
        display_name=f"Roaming Aggressiveness ({display_name})",
        description="WiFi AP scanning frequency. Lower = less ping spikes during gaming.",
        value_type=SettingValueType.CHOICE,
        choices=("Lowest", "Medium-Low", "Medium", "Medium-High", "Highest"),
        default_value="Medium",
        recommended_value="Lowest",
        requires_reboot=False,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "The client holds on to the current access point instead of switching to a stronger one. In a single-AP home that avoids needless roams mid-match; with mesh or multiple APs it can leave you on a weak signal as you move. No measurement supports either direction."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Higher values: Frequent AP scanning → periodic ping spikes (50-200ms)",
        recommended_impact="Lowest: Minimal scanning → stable connection, no ping spikes",
        scope=SettingScope.RECOMMENDED,
        category_order=14,  # Per-adapter WiFi setting
        effect="Lowest setting minimizes WiFi AP scanning ping spikes",
        impact_scores={"latency_ms": -100.0, "stability": "high"},
        # Detection - Use InterfaceIndex (numeric) for reliable command execution
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*RoamAggressiveness' -ErrorAction SilentlyContinue; "
            "if ($prop) { [int](@($prop.RegistryValue)[0]) } else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index, "batch_adapter_keyword": "*RoamAggressiveness"},
        # Map numeric registry values (0-4) to choice names
        value_map={
            0: "Lowest",
            "0": "Lowest",
            1: "Medium-Low",
            "1": "Medium-Low",
            2: "Medium",
            "2": "Medium",
            3: "Medium-High",
            "3": "Medium-High",
            4: "Highest",
            "4": "Highest",
        },
        # Apply - Use InterfaceIndex with explicit int cast
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            # Third occurrence of the same class (see advanced_eee): the Intel
            # driver publishes the bare vendor keyword "RoamAggressiveness" while
            # this asked for "*RoamAggressiveness". The write reported success and
            # changed nothing. Resolve the spelling from the adapter's own list —
            # probing with an unsupported keyword raises a terminating CIM error.
            "try { "
            "$all = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-AllProperties -ErrorAction SilentlyContinue; "
            "$kw = ($all | Where-Object { $_.RegistryKeyword -in "
            "@('*RoamAggressiveness','RoamAggressiveness') } "
            "| Select-Object -First 1).RegistryKeyword; "
            "if (-not $kw) { 'not_supported' } else { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $kw -RegistryValue ([int]%value%) -ErrorAction Stop; "
            "'ok' } "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={
            "Lowest": 0,
            "Medium-Low": 1,
            "Medium": 2,
            "Medium-High": 3,
            "Highest": 4,
        },
    )


def create_lso_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Large Send Offload (LSO) setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    LSO allows the network adapter to segment large packets, reducing CPU load.
    However, it can add latency for small, real-time packets used in gaming.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for LSO control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:lso",
        category=SettingCategory.NETWORK,
        display_name=f"Large Send Offload ({display_name})",
        description="Network card segments large packets. Disabling reduces latency for small packets.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "The CPU segments every packet instead of handing a large buffer to the adapter, so CPU use rises on bulk transfers. The claimed latency benefit is a reduction in burstiness and no isolated measurement of it was found — treat it as unproven."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Large packets batched → extra delay for small game packets",
        recommended_impact="Disabled: All packets processed immediately → ideal for real-time gaming",
        scope=SettingScope.RECOMMENDED,
        category_order=15,
        effect="Disabling prevents large packet batching for real-time gaming",
        impact_scores={"latency_ms": -2.0, "cpu_usage": 3.0, "stability": "high"},
        # Detection - Use InterfaceIndex for reliable command execution
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$lso = Get-NetAdapterLso -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue; "
            "if ($lso) { "
            "if ($lso.IPv4Enabled -or $lso.IPv6Enabled) { 'Enabled' } else { 'Disabled' } "
            "} else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        # Apply - Use InterfaceIndex
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "if ('%value%' -eq 'Enabled') { "
            "Enable-NetAdapterLso -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue "
            "} else { "
            "Disable-NetAdapterLso -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue "
            "}; 'ok'"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


def create_checksum_offload_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Checksum Offload setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Checksum offload lets the NIC calculate checksums, reducing CPU load.
    This is generally safe to leave enabled as it doesn't affect latency.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for checksum offload.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:checksum_offload",
        category=SettingCategory.NETWORK,
        display_name=f"Checksum Offload ({display_name})",
        description="NIC calculates packet checksums. Safe optimization, no latency impact.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Enabled",  # Keep enabled - safe optimization
        requires_reboot=False,
        evidence_level="proven",
        risk_level="low",
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: NIC handles checksums → reduces CPU load",
        recommended_impact="Keep enabled: No latency penalty, reduces CPU usage",
        scope=SettingScope.COMPLETE,  # Low priority, keep default
        category_order=16,
        effect="NIC handles checksums reducing CPU load",
        impact_scores={"cpu_usage": -2.0, "stability": "high"},
        # Detection - Use InterfaceIndex for reliable command execution
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            # The cmdlet exposes TcpIPv4Enabled — an enum whose values are
            # Disabled / TxEnabled / RxEnabled / RxTxEnabled — not TcpIPv4.
            # Reading the missing property gave $null, [int]$null is 0, so this
            # reported "Disabled" on every system regardless of the real state,
            # including immediately after a successful apply, which then failed
            # verification.
            "$cs = Get-NetAdapterChecksumOffload -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue; "
            "if (-not $cs) { 'not_supported' } "
            "elseif ([string]$cs.TcpIPv4Enabled -eq 'Disabled') { 'Disabled' } "
            "else { 'Enabled' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        # Apply - Use InterfaceIndex
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "if ('%value%' -eq 'Enabled') { "
            "Enable-NetAdapterChecksumOffload -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue "
            "} else { "
            "Disable-NetAdapterChecksumOffload -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue "
            "}; 'ok'"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


# === TCP Timestamps ===
# Adds 12 bytes to every TCP packet header. Disabling reduces overhead for gaming.
TCP_TIMESTAMPS = SettingExecutor(
    id="network:tcp_timestamps",
    category=SettingCategory.NETWORK,
    display_name="TCP Timestamps",
    description="Adds timestamp to each TCP packet. Disabling reduces header overhead for gaming.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    # RFC 1323 timestamps cost 12 bytes a segment and buy PAWS protection plus a
    # usable RTT estimate. Disabling them is a TCP-only change, and every modern
    # competitive title is UDP, so there is nothing here for a game to gain.
    recommended_value="enabled",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/powershell/module/nettcpip/set-nettcpsetting"],
    current_impact="Enabled: 12 bytes added to every TCP packet header",
    recommended_impact="Disabled: Reduced packet overhead → 1-2ms latency improvement",
    scope=SettingScope.COMPLETE,
    category_order=7,
    effect="Removes TCP timestamp headers for marginally lower network latency",
    impact_scores={"latency_ms": -0.2, "cpu_usage": -0.1},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        # Kept as the single-setting fallback; a scan answers from the shared
        # snapshot via detect_args below instead of running this.
        "try { $s = Get-NetTCPSetting -SettingName Internet -EA Stop; "
        "$s.Timestamps.ToString().ToLower() } "
        "catch { "
        "Write-Host 'FPSTUNE_WARN: Get-NetTCPSetting failed. "
        "The NetTCPIP module may be unavailable (LTSC/IoT edition) or "
        "PowerShell is running in a constrained environment.'; "
        "'not_available' }"
    ),
    detect_args={"batch_tcp": "Timestamps"},
    value_map={"disabled": "disabled", "enabled": "enabled", "allowed": "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="Set-NetTCPSetting -SettingName Internet -Timestamps %value% -ErrorAction Stop; Write-Output 'TCP Timestamps %value%'",
    apply_args={},
    apply_value_map={"disabled": "Disabled", "enabled": "Enabled"},
)

# === Explicit Congestion Notification (ECN) ===
# Network congestion signaling that can cause latency spikes with some routers.
TCP_ECN = SettingExecutor(
    id="network:tcp_ecn",
    category=SettingCategory.NETWORK,
    display_name="Explicit Congestion Notification (ECN)",
    description="Network congestion signaling. Can cause latency spikes with some routers.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    # ECN lets a congested router signal by marking rather than by dropping, which
    # is the opposite of a packet-loss problem. No measurement was found showing a
    # gaming benefit from turning it off, and it is TCP-only regardless.
    recommended_value="enabled",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/powershell/module/nettcpip/set-nettcpsetting"],
    current_impact="Enabled: Router may add congestion signals → latency spikes",
    recommended_impact="Disabled: No ECN → more consistent latency, avoids router-induced jitter",
    scope=SettingScope.COMPLETE,
    category_order=8,
    effect="Disables ECN to prevent router-induced latency spikes during gaming",
    impact_scores={"latency_ms": -0.5, "network_consistency": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "try { $s = Get-NetTCPSetting -SettingName Internet -EA Stop; "
        "$s.EcnCapability.ToString().ToLower() } "
        "catch { "
        "Write-Host 'FPSTUNE_WARN: Get-NetTCPSetting failed. "
        "The NetTCPIP module may be unavailable (LTSC/IoT edition) or "
        "PowerShell is running in a constrained environment.'; "
        "'not_available' }"
    ),
    detect_args={"batch_tcp": "EcnCapability"},
    value_map={"disabled": "disabled", "enabled": "enabled", "allowed": "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="Set-NetTCPSetting -SettingName Internet -EcnCapability %value% -ErrorAction Stop; Write-Output 'ECN %value%'",
    apply_args={},
    apply_value_map={"disabled": "Disabled", "enabled": "Enabled"},
)

# === TCP Fast Open ===
# Reduces connection establishment latency by sending data during the TCP handshake.
# Saves 1 full RTT on new connections (matchmaking, server switching).
TCP_FAST_OPEN = SettingExecutor(
    id="network:tcp_fast_open",
    category=SettingCategory.NETWORK,
    display_name="TCP Fast Open (TFO)",
    short_name="TCP Fast Open",
    description="Sends data during TCP handshake, saving 1 RTT on new connections. Speeds up matchmaking.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "enabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/powershell/module/nettcpip/set-nettcpsetting",
        "https://datatracker.ietf.org/doc/html/rfc7413",
    ],
    current_impact="Disabled: Standard 3-way handshake → 1 RTT delay per new connection",
    recommended_impact="Enabled: Data sent during SYN → saves 1 RTT on server connect, faster matchmaking",
    scope=SettingScope.RECOMMENDED,
    category_order=9,
    effect="Reduces TCP connection setup time by 1 round-trip for faster server connections",
    impact_scores={"latency_ms": -3, "stability": "high"},
    # Detection via netsh (reliable on all Win11 versions)
    detect_type=DetectType.NETSH,
    detect_command="interface tcp show global",
    detect_args={"parse_key": "fast open"},
    value_map={},  # Direct pass-through (lowercase: "enabled"/"disabled")
    # Apply via netsh
    apply_type=DetectType.NETSH,
    apply_command="interface tcp set global fastopen=%value%",
    apply_args={},
    apply_value_map={},
)

# === Max User Ports ===
# Increases the range of ephemeral ports available for outbound connections.
# Default 5000 port range can bottleneck during rapid matchmaking/reconnects.
MAX_USER_PORT = SettingExecutor(
    id="network:max_user_port",
    category=SettingCategory.NETWORK,
    display_name="Max Ephemeral Ports (MaxUserPort)",
    short_name="Max Ports",
    description="Ephemeral port range upper bound. Higher = more outbound ports for simultaneous connections.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "maximum"),
    default_value="default",
    recommended_value="maximum",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/connect-tcp-greater-than-5000-error-702-702b",
    ],
    current_impact="Default: ~5000 ephemeral ports → possible port exhaustion during rapid reconnects",
    recommended_impact="Maximum (65534): Full port range → no exhaustion, instant reconnect availability",
    scope=SettingScope.RECOMMENDED,
    category_order=10,
    effect="Sets MaxUserPort=65534 to expand the ephemeral port range",
    impact_scores={"latency_ms": 0, "stability": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "MaxUserPort",
        "hive": "HKLM",
    },
    value_map={65534: "maximum", "65534": "maximum", None: "default"},
    # Single-setting apply: only MaxUserPort. TcpNumConnections is a separate tweak.
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "MaxUserPort",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"maximum": 65534, "default": None},  # None → delete key (restore default)
    value_hints={"default": "not set", "maximum": "65534"},
)

# === TCP Max Connections ===
# TcpNumConnections caps the total number of simultaneous TCP connections.
# Default is absent (system limit). Setting to 65534 matches MaxUserPort.
TCP_NUM_CONNECTIONS = SettingExecutor(
    id="network:tcp_num_connections",
    category=SettingCategory.NETWORK,
    display_name="TCP Max Connections (TcpNumConnections)",
    short_name="Max TCP Conn",
    description="Maximum simultaneous TCP connections. 65534 prevents connection table overflow.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "maximum"),
    default_value="default",
    recommended_value="maximum",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/connect-tcp-greater-than-5000-error-702-702b",
    ],
    current_impact="Default: OS-managed limit → possible bottleneck during burst matchmaking",
    recommended_impact="Maximum (65534): Explicit high limit → handles burst parallel connections",
    scope=SettingScope.RECOMMENDED,
    category_order=10,
    effect="Sets TcpNumConnections=65534 to raise the simultaneous connection limit",
    impact_scores={"latency_ms": 0, "stability": "neutral"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "TcpNumConnections",
        "hive": "HKLM",
    },
    value_map={65534: "maximum", "65534": "maximum", None: "default"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "TcpNumConnections",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"maximum": 65534, "default": None},  # None → delete key (restore default)
    value_hints={"default": "not set", "maximum": "65534"},
)

# === TCP TIME_WAIT Delay ===
# Reduces the time closed sockets stay in TIME_WAIT state.
# Default 120s → 30s: freed ports are reusable faster for new connections.
TCP_TIMED_WAIT_DELAY = SettingExecutor(
    id="network:tcp_timed_wait_delay",
    category=SettingCategory.NETWORK,
    display_name="TCP TIME_WAIT Delay",
    short_name="TIME_WAIT",
    description="How long closed sockets wait before port reuse. Lower = faster port recycling.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "fast"),
    default_value="default",
    recommended_value="fast",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/tcpip-and-nbt-configuration-parameters",
    ],
    current_impact="Default: 120s TIME_WAIT → ports locked after close, slow recycling",
    recommended_impact="Fast: 30s TIME_WAIT → ports freed 4x faster, helps rapid server reconnects",
    scope=SettingScope.RECOMMENDED,
    category_order=11,
    effect="Reduces socket TIME_WAIT from 120s to 30s for faster port recycling",
    impact_scores={"latency_ms": 0, "stability": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "TcpTimedWaitDelay",
        "hive": "HKLM",
    },
    value_map={30: "fast", "30": "fast", None: "default", 120: "default", "120": "default"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "TcpTimedWaitDelay",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"fast": 30, "default": 120},
    value_hints={"default": "120s", "fast": "30s"},
)

# === Default TTL ===
# Sets the initial Time-To-Live for outbound packets.
# 64 is optimal for gaming (Linux/macOS default). Windows default is 128.
# Lower TTL = packets expire faster if misrouted, reducing stale routing latency.
DEFAULT_TTL = SettingExecutor(
    id="network:default_ttl",
    category=SettingCategory.NETWORK,
    display_name="Default Packet TTL",
    short_name="TTL",
    description="Initial Time-To-Live for packets. 64 is optimal (Linux/macOS default).",
    value_type=SettingValueType.CHOICE,
    choices=("default", "optimized"),
    default_value="default",
    # TTL is a hop limit. It cannot change latency, throughput or loss — a packet
    # either has enough hops left or it is discarded. This recommendation was
    # pure placebo and is the clearest case of the class.
    recommended_value="default",
    requires_reboot=False,
    # Not "experimental": the claim here is that the Windows default is
    # already correct, which is evidenced by the vendor shipping it and by
    # the research that rejected changing it. `evidence_level` grades the
    # benefit, and "leave this alone" is a well-supported benefit.
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/tcpip-and-nbt-configuration-parameters",
    ],
    current_impact="Default: TTL=128 → extra hops before expiry, some ISPs route differently",
    recommended_impact="Optimized: TTL=64 → matches Linux/macOS, some ISPs prioritize lower TTL traffic",
    scope=SettingScope.COMPLETE,
    category_order=23,
    effect="Sets packet TTL to 64 (cross-platform standard) for optimized routing",
    impact_scores={"latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "DefaultTTL",
        "hive": "HKLM",
    },
    value_map={
        64: "optimized",
        "64": "optimized",
        128: "default",
        "128": "default",
        None: "default",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": TCPIP_PARAMS_KEY,
        "name": "DefaultTTL",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 64, "default": 128},
    value_hints={"default": "128", "optimized": "64"},
)


def create_wake_on_lan_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Wake-on-LAN setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Wake-on-LAN/Pattern wakes the PC from sleep via network packets.
    For gaming, this can cause unexpected wakeups and keeps the adapter
    partially powered during sleep, adding idle power draw.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for Wake-on-LAN control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:wake_on_lan",
        category=SettingCategory.NETWORK,
        display_name=f"Wake on LAN ({display_name})",
        description="Wakes PC via network packets. Disabling prevents unexpected wakeups.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "The machine can no longer be woken over the network. Only disable this if you do not use Wake-on-LAN or remote power-on."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Adapter stays partially powered during sleep → unexpected wakeups",
        recommended_impact="Disabled: No WoL power draw → cleaner sleep, no surprise wakeups",
        scope=SettingScope.RECOMMENDED,
        category_order=17,
        effect="Disabling prevents unexpected system wakeups from network traffic",
        impact_scores={"stability": "high", "power_watts": 0.2},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$magic = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*WakeOnMagicPacket' -ErrorAction SilentlyContinue; "
            "$pattern = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*WakeOnPattern' -ErrorAction SilentlyContinue; "
            "if ($magic -or $pattern) { "
            "$mVal = if ($magic) { [int](@($magic.RegistryValue)[0]) } else { 1 }; "
            "$pVal = if ($pattern) { [int](@($pattern.RegistryValue)[0]) } else { 1 }; "
            "if ($mVal -eq 0 -and $pVal -eq 0) { 'Disabled' } else { 'Enabled' } "
            "} else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "$regVal = if ('%value%' -eq 'Enabled') { 1 } else { 0 }; "
            "$changed = $false; "
            "foreach ($kw in @('*WakeOnMagicPacket', '*WakeOnPattern')) { "
            "try { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $kw -RegistryValue $regVal -ErrorAction Stop; "
            "$changed = $true "
            "} catch { } "
            "}; "
            "if ($changed) { 'ok' } else { 'not_supported' }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


def create_speed_duplex_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Speed & Duplex setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Auto-negotiation can occasionally settle on suboptimal speeds.
    For wired gaming, forcing 1Gbps Full-Duplex ensures maximum stable throughput.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for Speed & Duplex control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:speed_duplex",
        category=SettingCategory.NETWORK,
        display_name=f"Speed & Duplex ({display_name})",
        description="How the adapter agrees a link speed with the switch. Auto-negotiation is the "
        "standard and the only safe choice; a forced speed breaks it.",
        value_type=SettingValueType.CHOICE,
        choices=(
            "Auto_Negotiation",
            "10Mbps_Half",
            "10Mbps_Full",
            "100Mbps_Half",
            "100Mbps_Full",
            "1Gbps_Half",
            "1Gbps_Full",
            "2.5Gbps_Full",
            # Detect-only. Vendors extend this enum past the NDIS range — this
            # Realtek uses 2500 for 2.5 Gbps where the spec would suggest 7 — so
            # a map built from one driver leaves every other adapter reporting a
            # bare number outside its own `choices`. Anything unrecognised
            # normalises here instead: "forced" is the actionable fact, and the
            # exact speed is not needed to say "this link is not negotiating".
            "Forced_Other",
        ),
        default_value="Auto_Negotiation",
        # This used to recommend "1Gbps_Full", and it was actively harmful.
        # IEEE 802.3 recommends auto-negotiation on every connection and makes it
        # mandatory at 1 GbE and above. Forcing one end while the far end still
        # auto-negotiates is the textbook cause of a duplex mismatch: the
        # negotiating end can read the speed but not the duplex, so the standard
        # requires it to fall back to half duplex. The link then works and is
        # quietly broken — collisions, retransmissions, latency spikes and loss,
        # which is exactly the "packet loss / packet burst" symptom picture.
        # Measured on the dev machine: a Realtek 2.5GbE adapter forced to 6
        # (1.0 Gbps Full) by this very setting was linked at 100 Mbps.
        # Forcing also caps the adapter below its own capability — this driver
        # exposes 2500 for 2.5 Gbps, so "force 1 Gbps" threw away 60% of the link.
        recommended_value="Auto_Negotiation",
        requires_reboot=False,
        evidence_level="proven",
        sources=[
            "https://www.cisco.com/c/en/us/support/docs/lan-switching/ethernet/10561-3.html",
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics",
        ],
        current_impact="Forced: the far end cannot detect duplex → mismatch, retransmits, packet loss",
        recommended_impact="Auto: both ends agree the fastest common speed → full link, no mismatch",
        scope=SettingScope.ESSENTIAL,
        category_order=18,
        effect="Restores standard link negotiation so the adapter runs at its real speed",
        impact_scores={"packet_loss": "eliminates duplex-mismatch loss", "stability": "high"},
        # Values 0-4 and 2500 were read from this driver's own ValidRegistryValues
        # rather than assumed. The command normalises rather than leaving the
        # translation to `value_map`, because the enum is vendor-extended: any
        # number the map does not know would otherwise reach the UI as a bare
        # integer outside `choices`. The batch snapshot is deliberately not used
        # here for the same reason it was dropped for the buffer settings (#45) —
        # it hands back the raw number with no way to say "unrecognised". This
        # stays in the shared PowerShell sessions, so it costs no extra process.
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*SpeedDuplex' -ErrorAction SilentlyContinue; "
            "if (-not $prop) { 'not_supported' } else { "
            "switch ([int](@($prop.RegistryValue)[0])) { "
            "0 { 'Auto_Negotiation' } "
            "1 { '10Mbps_Half' } "
            "2 { '10Mbps_Full' } "
            "3 { '100Mbps_Half' } "
            "4 { '100Mbps_Full' } "
            "5 { '1Gbps_Half' } "
            "6 { '1Gbps_Full' } "
            "2500 { '2.5Gbps_Full' } "
            "default { 'Forced_Other' } "
            "} }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*SpeedDuplex' -RegistryValue ([int]%value%) -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        # Forced_Other is absent on purpose: it is a reading, not a target. There
        # is no single number it could write, and fpstune has no reason to help a
        # user force a speed — the recommendation is always to negotiate.
        apply_value_map={
            "Auto_Negotiation": 0,
            "10Mbps_Half": 1,
            "10Mbps_Full": 2,
            "100Mbps_Half": 3,
            "100Mbps_Full": 4,
            "1Gbps_Half": 5,
            "1Gbps_Full": 6,
            "2.5Gbps_Full": 2500,
        },
    )


def _make_vendor_power_setting(
    *,
    interface_index: int,
    display_name: str,
    slug: str,
    label: str,
    keyword: str,
    description: str,
    current_impact: str,
    recommended_impact: str,
    effect: str,
    category_order: int,
    risk_warning: str,
) -> SettingExecutor:
    """Build an Enabled/Disabled setting for a vendor-specific NIC power keyword.

    Vendor keywords carry no ``*`` prefix — that prefix marks the standardised NDIS
    keywords. Realtek exposes its power savers as bare names (``EnableGreenEthernet``,
    ``GigaLite``, ``PowerSavingMode``), so querying them with a ``*`` returns
    not_supported and the setting silently does nothing on exactly the adapters it
    was written for.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:{slug}",
        category=SettingCategory.NETWORK,
        display_name=f"{label} ({display_name})",
        description=description,
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=risk_warning,
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact=current_impact,
        recommended_impact=recommended_impact,
        scope=SettingScope.RECOMMENDED,
        category_order=category_order,
        effect=effect,
        impact_scores={"latency_ms": -1.0, "jitter_ms": "reduced"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            f"$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            f"-RegistryKeyword '{keyword}' -ErrorAction SilentlyContinue; "
            "if ($prop) { [int](@($prop.RegistryValue)[0]) } else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index, "batch_adapter_keyword": keyword},
        value_map={0: "Disabled", "0": "Disabled", 1: "Enabled", "1": "Enabled"},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            f"Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            f"-RegistryKeyword '{keyword}' -RegistryValue ([int]%value%) -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={"Enabled": 1, "Disabled": 0},
    )


def create_green_ethernet_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Realtek Green Ethernet: reduces PHY signal power on short cable runs."""
    return _make_vendor_power_setting(
        interface_index=interface_index,
        display_name=display_name,
        slug="green_ethernet",
        label="Green Ethernet",
        keyword="EnableGreenEthernet",
        description="Realtek power saving that lowers PHY transmit power based on estimated cable "
        "length. On a marginal cable the reduced signal margin shows up as link renegotiation and "
        "brief stalls rather than as a clean error.",
        current_impact="Enabled: PHY power reduced → less signal margin, renegotiation on marginal cable",
        recommended_impact="Disabled: Full signal margin → stable link, no renegotiation stalls",
        effect="Disables Realtek Green Ethernet to keep full PHY signal margin",
        category_order=20,
        risk_warning="Raises adapter power draw slightly, which matters on battery. If the adapter "
        "does not expose this keyword the setting reports not_supported and does nothing.",
    )


def create_gigalite_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Realtek Gigabit Lite: trades link rate for power."""
    return _make_vendor_power_setting(
        interface_index=interface_index,
        display_name=display_name,
        slug="gigalite",
        label="Gigabit Lite",
        keyword="GigaLite",
        description="Realtek power saving that lets the adapter negotiate a reduced-power link "
        "mode. It can settle on a lower rate than the cable and switch actually support, which "
        "shrinks the headroom a background transfer needs before it starts queueing game packets.",
        current_impact="Enabled: Adapter may negotiate below the link's real capability",
        recommended_impact="Disabled: Full negotiated rate → more headroom before congestion",
        effect="Disables Realtek Gigabit Lite so the link negotiates its full rate",
        category_order=21,
        risk_warning="Raises idle power draw. If the low rate is caused by the cable or the "
        "upstream port rather than by this setting, disabling it will not raise the link speed.",
    )


def create_nic_power_saving_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Realtek Power Saving Mode: aggregate idle power management."""
    return _make_vendor_power_setting(
        interface_index=interface_index,
        display_name=display_name,
        slug="nic_power_saving",
        label="Adapter Power Saving Mode",
        keyword="PowerSavingMode",
        description="Realtek aggregate idle power management for the adapter. Entering and leaving "
        "the low-power state costs wake time on the first packet after an idle gap, which is "
        "exactly the pattern of a game sending sparse UDP updates.",
        current_impact="Enabled: Adapter idles down → wake delay on the first packet after a gap",
        recommended_impact="Disabled: Adapter always ready → no wake delay on sparse traffic",
        effect="Disables Realtek adapter power saving to remove wake-up delay",
        category_order=22,
        risk_warning="Raises idle power draw, which shortens battery runtime on a laptop. Prefer "
        "this while on AC power.",
    )


def create_advanced_eee_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create an Advanced EEE setting for Intel adapters.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Advanced EEE (IEEE 802.3az extended) is an Intel-specific deeper power saving mode
    that adds more aggressive low-power transitions. Disabling ensures consistent
    adapter performance with no wake-up latency spikes.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for Advanced EEE control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:advanced_eee",
        category=SettingCategory.NETWORK,
        display_name=f"Advanced EEE ({display_name})",
        description="Intel extended power saving (deeper EEE). Disabling prevents latency spikes.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "Same trade as Energy Efficient Ethernet: the link never enters low-power idle, so it never has to wake up, at the cost of a little continuous power."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Deep power transitions → latency spikes on wake (Intel adapters)",
        recommended_impact="Disabled: No deep power saving → consistent adapter latency",
        scope=SettingScope.RECOMMENDED,
        category_order=19,
        effect="Disabling prevents Intel adapter deep-sleep latency spikes",
        impact_scores={"latency_ms": -2.0, "power_watts": 0.5, "stability": "high"},
        # Intel-specific keyword: *AdvancedEEE
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*AdvancedEEE' -ErrorAction SilentlyContinue; "
            "if ($prop) { [int](@($prop.RegistryValue)[0]) } else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index, "batch_adapter_keyword": "*AdvancedEEE"},
        value_map={
            0: "Disabled",
            "0": "Disabled",
            1: "Enabled",
            "1": "Enabled",
        },
        apply_type=DetectType.POWERSHELL,
        # The '*' prefix marks a standardised NDIS keyword; vendor keywords are
        # bare. Intel publishes "*AdvancedEEE", Realtek publishes "AdvancedEEE",
        # and writing the spelling the driver does not expose fails silently —
        # the value stayed Enabled while apply reported success, and only the
        # verify step caught it. Pick whichever spelling this adapter actually
        # exposes before writing.
        apply_command=(
            "try { "
            # Probing with an unsupported keyword raises a terminating CIM error
            # ("No matching MSFT_NetAdapterAdvancedPropertySettingData objects
            # found"), so the spelling is picked out of the adapter's own
            # property list instead of by trial query.
            "$all = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-AllProperties -ErrorAction SilentlyContinue; "
            "$kw = ($all | Where-Object { $_.RegistryKeyword -in "
            "@('*AdvancedEEE','AdvancedEEE') } | Select-Object -First 1).RegistryKeyword; "
            "if (-not $kw) { 'not_supported' } else { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $kw -RegistryValue ([int]%value%) -ErrorAction Stop; "
            "'ok' } "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={"Enabled": 1, "Disabled": 0},
    )


def create_receive_buffers_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Receive Buffers setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    NIC receive buffers hold incoming packets before the driver processes them.
    Increasing the count prevents packet drops during burst traffic (e.g., game state updates).

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for receive buffers control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:receive_buffers",
        category=SettingCategory.NETWORK,
        display_name=f"Receive Buffers ({display_name})",
        description="NIC packet receive buffer size. Higher = fewer dropped packets during bursts.",
        value_type=SettingValueType.CHOICE,
        choices=("default", "maximum"),
        default_value="default",
        recommended_value="maximum",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "More descriptors mean fewer drops when traffic arrives in bursts, at the cost of a little non-paged memory and a slightly longer worst-case queue."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Default: Small receive buffer → packet drops during burst traffic",
        recommended_impact="Maximum: buffer at this adapter's own ceiling → absorbs burst traffic, less packet loss.",
        scope=SettingScope.RECOMMENDED,
        category_order=20,
        effect="Maximizing receive buffers reduces packet loss during network bursts",
        impact_scores={"latency_ms": -1.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*ReceiveBuffers' -ErrorAction SilentlyContinue; "
            "if (-not $prop) { 'not_supported' } else { "
            "$cur = [int](@($prop.RegistryValue)[0]); "
            "$max = [int]$prop.NumericParameterMaxValue; "
            "if ($max -gt 0 -and $cur -ge $max) { 'maximum' } else { 'default' } }"
        ),
        # No batch keyword on purpose: the snapshot returns the raw count, and
        # "is this the maximum" cannot be answered without the adapter's own
        # ceiling. Hardcoding 1024 was wrong — this Realtek part reports
        # NumericParameterMaxValue=512 for receive, so a 1024 write was clamped
        # to 512 and verification then failed permanently. The live command asks
        # the driver for its maximum and classifies against that.
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*ReceiveBuffers' -ErrorAction Stop; "
            "$max = [int]$prop.NumericParameterMaxValue; "
            "$val = if ('%value%' -eq 'maximum') { $max } else { "
            "[Math]::Max([int]$prop.NumericParameterMinValue, 256) }; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*ReceiveBuffers' -RegistryValue $val -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
        value_hints={"default": "Driver default", "maximum": "This adapter's own maximum"},
    )


def create_transmit_buffers_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Transmit Buffers setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    NIC transmit buffers hold outgoing packets before sending.
    Increasing prevents send stalls during burst uploads (e.g., game input packets).

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for transmit buffers control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:transmit_buffers",
        category=SettingCategory.NETWORK,
        display_name=f"Transmit Buffers ({display_name})",
        description="NIC packet transmit buffer size. Higher = fewer send stalls during burst uploads.",
        value_type=SettingValueType.CHOICE,
        choices=("default", "maximum"),
        default_value="default",
        recommended_value="maximum",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "More descriptors mean fewer drops when traffic leaves in bursts, at the cost of a little non-paged memory and a slightly longer worst-case queue."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Default: Small transmit buffer → send stalls during burst traffic",
        recommended_impact="Maximum: buffer at this adapter's own ceiling → absorbs send bursts, stable upload.",
        scope=SettingScope.RECOMMENDED,
        category_order=21,
        effect="Maximizing transmit buffers reduces upload stalls during gaming",
        impact_scores={"latency_ms": -1.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*TransmitBuffers' -ErrorAction SilentlyContinue; "
            "if (-not $prop) { 'not_supported' } else { "
            "$cur = [int](@($prop.RegistryValue)[0]); "
            "$max = [int]$prop.NumericParameterMaxValue; "
            "if ($max -gt 0 -and $cur -ge $max) { 'maximum' } else { 'default' } }"
        ),
        # See create_receive_buffers_setting. The 1024 assumption was wrong in both
        # directions: it exceeds the receive ceiling on this Realtek part (512) and
        # falls well short of its transmit ceiling (4096), so "maximum" verified
        # against a value that was not the maximum at all.
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*TransmitBuffers' -ErrorAction Stop; "
            "$max = [int]$prop.NumericParameterMaxValue; "
            "$val = if ('%value%' -eq 'maximum') { $max } else { "
            "[Math]::Max([int]$prop.NumericParameterMinValue, 256) }; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*TransmitBuffers' -RegistryValue $val -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
        value_hints={"default": "driver minimum", "maximum": "adapter maximum"},
    )


def rss_queue_recommendation(queue_counts: tuple[str, ...]) -> str:
    """Pick the queue count to recommend from what this driver actually offers.

    Two queues is the target: one is not enough to absorb a burst while the
    stack is still processing the previous one, and every queue past that
    spreads interrupts onto another core the game wanted. But "2" is only a
    recommendation the driver has to support — some expose 1/2/4/8/16 and some
    only 1/2 — so the choice is the smallest offered count that is at least two,
    and the largest available when even that does not exist.
    """
    numeric = sorted({int(count) for count in queue_counts})
    at_least_two = [count for count in numeric if count >= 2]
    return str(at_least_two[0] if at_least_two else numeric[-1])


def create_rss_queues_setting(
    interface_index: int,
    display_name: str,
    queue_counts: tuple[str, ...],
    driver_default: str,
) -> SettingExecutor:
    """Create an RSS Queue Count setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    RSS (Receive Side Scaling) queues distribute NIC interrupts across CPU cores.
    Two is the gaming target: one core cannot absorb a burst while it is still
    processing the last one, and each further queue takes a core the game wanted.

    `choices` and `default_value` are the driver's own, not a constant. This
    setting used to declare `("1", "2", "4")` and default `"4"` for every
    adapter on every machine. The CI runner's NIC offers sixteen queues and was
    running at sixteen, so it read a value outside its own `choices` and could
    never verify — and an adapter that offers eight would have been told four
    was its default when the driver had never said so.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).
        queue_counts: Queue counts this adapter's driver accepts, read from its
            own `*NumRssQueues` metadata.
        driver_default: The driver's own default queue count.

    Returns:
        SettingExecutor for RSS queue count control.
    """
    if not queue_counts:
        raise ValueError(
            f"rss_queues for interface {interface_index} was given no queue counts; "
            "the caller must read them from the adapter rather than register a guess"
        )

    return SettingExecutor(
        id=f"network:{interface_index}:rss_queues",
        category=SettingCategory.NETWORK,
        display_name=f"RSS Queue Count ({display_name})",
        description="Number of CPU cores handling network interrupts. 2 queues optimal for gaming.",
        value_type=SettingValueType.CHOICE,
        choices=queue_counts,
        default_value=driver_default,
        recommended_value=rss_queue_recommendation(queue_counts),
        requires_reboot=False,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "A game's traffic is one flow and therefore lands on one queue regardless, so extra queues mostly spread other traffic. Reducing them concentrates interrupts on fewer cores, which helps or hurts depending on what else runs there. Unmeasured."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact=(
            f"{driver_default} queues: interrupts spread over {driver_default} cores, "
            "including ones the game wanted"
        ),
        recommended_impact=(
            f"{rss_queue_recommendation(queue_counts)} queues: absorbs a burst without "
            "taking a core off rendering"
        ),
        scope=SettingScope.COMPLETE,
        category_order=22,
        effect=(
            f"Concentrates NIC interrupts on {rss_queue_recommendation(queue_counts)} "
            "cores, freeing the rest for game rendering"
        ),
        impact_scores={"cpu_usage": -2.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*NumRssQueues' -ErrorAction SilentlyContinue; "
            "if ($prop) { [string]([int](@($prop.RegistryValue)[0])) } else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index, "batch_adapter_keyword": "*NumRssQueues"},
        value_map={},  # Direct pass-through; choices are this driver's own values
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*NumRssQueues' -RegistryValue ([int]'%value%') -ErrorAction Stop; "
            "'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},  # Direct pass-through
    )


def create_uapsd_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a WiFi U-APSD (power-save delivery) setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    U-APSD (Unscheduled Automatic Power Save Delivery, WMM-PS) lets the WiFi adapter
    buffer downlink packets and deliver them on a power-save schedule, which adds
    latency and jitter. Disabling delivers packets immediately. WiFi adapters only;
    Ethernet adapters report not_supported.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for U-APSD control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:uapsd",
        category=SettingCategory.NETWORK,
        display_name=f"WiFi U-APSD Power Save ({display_name})",
        description="WiFi power-save packet delivery scheduling (U-APSD/WMM-PS). Disabling delivers downlink packets immediately for lower latency and jitter.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "The Wi-Fi radio stops sleeping between frames, so it stays at full power. Measurably shorter battery life on a laptop, in exchange for not waiting on a buffered frame."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Packets buffered for power-save delivery → 1-10ms WiFi latency and jitter",
        recommended_impact="Disabled: Immediate packet delivery → lower, more consistent WiFi latency",
        scope=SettingScope.RECOMMENDED,
        category_order=23,
        effect="Disabling U-APSD removes WiFi power-save delivery latency",
        impact_scores={"latency_ms": -2.0, "stability": "high"},
        # Detection - discover by RegistryKeyword or localized DisplayName (driver-specific)
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.RegistryKeyword -match 'UAPSD|APSD' -or $_.DisplayName -match 'U.?APSD' "
            "} | Select-Object -First 1; "
            "if ($p) { if ([int](@($p.RegistryValue)[0]) -eq 0) { 'Disabled' } else { 'Enabled' } } "
            "else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.RegistryKeyword -match 'UAPSD|APSD' -or $_.DisplayName -match 'U.?APSD' "
            "} | Select-Object -First 1; "
            "if ($p) { "
            "$val = if ('%value%' -eq 'Enabled') { 1 } else { 0 }; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $p.RegistryKeyword -RegistryValue $val -ErrorAction Stop; 'ok' "
            "} else { 'not_supported' }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


def create_throughput_booster_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a WiFi Throughput Booster setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Throughput Booster (Intel WiFi) bursts packets to raise raw throughput, but the
    bursting introduces jitter spikes that hurt real-time gaming. Disabling favors
    consistent, low-jitter delivery. WiFi adapters only; others report not_supported.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for Throughput Booster control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:throughput_booster",
        category=SettingCategory.NETWORK,
        display_name=f"WiFi Throughput Booster ({display_name})",
        description="WiFi packet-bursting feature that raises throughput at the cost of jitter. Disabling favors consistent low-jitter delivery for gaming.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "A vendor feature whose implementation is not documented, so what it actually changes differs per driver. Disabling it is a guess that it aggregates frames and adds delay."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Packet bursting → periodic jitter spikes during gameplay",
        recommended_impact="Disabled: Steady delivery → lower jitter, smoother gameplay",
        scope=SettingScope.RECOMMENDED,
        category_order=24,
        effect="Disabling Throughput Booster removes WiFi bursting jitter",
        impact_scores={"latency_ms": -1.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.RegistryKeyword -match 'ThroughputBoost' -or $_.DisplayName -match 'Throughput.?Booster' "
            "} | Select-Object -First 1; "
            "if ($p) { if ([int](@($p.RegistryValue)[0]) -eq 0) { 'Disabled' } else { 'Enabled' } } "
            "else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.RegistryKeyword -match 'ThroughputBoost' -or $_.DisplayName -match 'Throughput.?Booster' "
            "} | Select-Object -First 1; "
            "if ($p) { "
            "$val = if ('%value%' -eq 'Enabled') { 1 } else { 0 }; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $p.RegistryKeyword -RegistryValue $val -ErrorAction Stop; 'ok' "
            "} else { 'not_supported' }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


def create_packet_coalescing_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a D0 Packet Coalescing setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    Packet Coalescing batches incoming packets in the active (D0) power state to reduce
    CPU notifications, which adds DPC latency spikes (notably on WiFi/ndis.sys). Disabling
    forces per-packet notification. Adapters without the property report not_supported.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for Packet Coalescing control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:packet_coalescing",
        category=SettingCategory.NETWORK,
        display_name=f"D0 Packet Coalescing ({display_name})",
        description="Batches incoming packets in the active power state to cut CPU notifications. Disabling forces per-packet processing to remove DPC latency spikes.",
        value_type=SettingValueType.CHOICE,
        choices=("Enabled", "Disabled"),
        default_value="Enabled",
        recommended_value="Disabled",
        requires_reboot=False,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "A vendor feature with no consistent documentation across drivers, so its exact effect differs per adapter. The reasoning — fewer, larger receive batches add delay — is sound, but no measurement was found for it."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
        ],
        current_impact="Enabled: Packets batched in D0 → ndis.sys DPC latency spikes",
        recommended_impact="Disabled: Per-packet notification → lower DPC latency, less jitter",
        scope=SettingScope.RECOMMENDED,
        category_order=25,
        effect="Disabling D0 packet coalescing removes batching DPC latency",
        impact_scores={"latency_ms": -1.0, "cpu_usage": 1.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.RegistryKeyword -match 'PacketCoalescing|Coalesc' -or "
            "$_.DisplayName -match 'Packet.?Coalescing' "
            "} | Select-Object -First 1; "
            "if ($p) { if ([int](@($p.RegistryValue)[0]) -eq 0) { 'Disabled' } else { 'Enabled' } } "
            "else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "$p = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.RegistryKeyword -match 'PacketCoalescing|Coalesc' -or "
            "$_.DisplayName -match 'Packet.?Coalescing' "
            "} | Select-Object -First 1; "
            "if ($p) { "
            "$val = if ('%value%' -eq 'Enabled') { 1 } else { 0 }; "
            "Set-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword $p.RegistryKeyword -RegistryValue $val -ErrorAction Stop; 'ok' "
            "} else { 'not_supported' }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


def create_rss_base_processor_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create an RSS Base Processor setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    RSS distributes NIC interrupts across CPU cores starting at the base processor.
    Core 0 is heavily contended by Windows default process affinity, so moving the RSS
    base off Core 0 lowers DPC latency. Adapters without RSS report not_supported.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for RSS base processor control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:rss_base_processor",
        category=SettingCategory.NETWORK,
        display_name=f"RSS Base Processor ({display_name})",
        description="The first CPU core that handles NIC interrupts via RSS. Moving the base off contended Core 0 lowers DPC latency.",
        value_type=SettingValueType.CHOICE,
        choices=("default", "optimized"),
        default_value="default",
        recommended_value="optimized",
        requires_reboot=False,
        evidence_level="likely",
        risk_level="low",
        risk_warning=(
            "Moves receive processing off CPU 0, which also serves timers and other DPCs. If the chosen core is one the game pins a thread to, the two now compete."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/powershell/module/netadapter/set-netadapterrss"
        ],
        current_impact="Default: RSS base on Core 0 → contends with Windows default affinity",
        recommended_impact="Optimized: RSS base on Core 2 → fewer DPC stalls, lower jitter",
        scope=SettingScope.COMPLETE,
        category_order=26,
        effect="Moves the RSS base processor off Core 0 to reduce DPC latency",
        impact_scores={"latency_ms": -1.0, "cpu_usage": -1.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$a = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue; "
            "if ($a) { "
            "$rss = Get-NetAdapterRSS -Name $a.Name -ErrorAction SilentlyContinue; "
            "if ($rss) { if ([int]$rss.BaseProcessorNumber -ge 2) { 'optimized' } else { 'default' } } "
            "else { 'not_supported' } "
            "} else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$a = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction Stop; "
            "$base = if ('%value%' -eq 'optimized') { 2 } else { 0 }; "
            "Set-NetAdapterRSS -Name $a.Name -BaseProcessorNumber $base -ErrorAction Stop; 'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
        value_hints={"default": "Core 0", "optimized": "Core 2"},
    )


def create_msi_mode_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a Message-Signaled Interrupts (MSI) setting for a specific adapter.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.

    MSI/MSI-X lets the NIC deliver interrupts directly per-device instead of sharing
    legacy line-based IRQs, eliminating shared-interrupt latency. This edits the device's
    Interrupt Management registry key and requires a reboot. Marked advanced because an
    incorrect device that ignores MSI can fail to initialize until reverted.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).

    Returns:
        SettingExecutor for MSI mode control.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:msi_mode",
        category=SettingCategory.NETWORK,
        display_name=f"Message-Signaled Interrupts ({display_name})",
        description="Delivers NIC interrupts per-device via MSI/MSI-X instead of shared legacy IRQ lines. Enabling removes shared-interrupt latency for lower DPC times.",
        value_type=SettingValueType.CHOICE,
        choices=("default", "enabled"),
        default_value="default",
        recommended_value="enabled",
        requires_reboot=True,
        evidence_level="experimental",
        risk_level="advanced",
        risk_warning=(
            "Edits the adapter's Interrupt Management registry key and needs a reboot. "
            "If the adapter does not support MSI, reset this setting and reboot to restore "
            "line-based interrupts."
        ),
        sources=[
            "https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/enabling-message-signaled-interrupts-in-the-registry"
        ],
        current_impact="Default: Shared line-based IRQ → cross-device interrupt latency",
        recommended_impact="Enabled: Per-device MSI/MSI-X → lower interrupt latency and DPC time",
        scope=SettingScope.COMPLETE,
        category_order=27,
        effect="Enables MSI/MSI-X interrupt delivery for the network adapter",
        impact_scores={"latency_ms": -1.0, "stability": "high"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$a = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue; "
            "if ($a) { "
            "$pnp = Get-PnpDevice | Where-Object { $_.FriendlyName -eq $a.InterfaceDescription } "
            "| Select-Object -First 1; "
            "if ($pnp) { "
            '$rp = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($pnp.InstanceId)\\Device Parameters'
            '\\Interrupt Management\\MessageSignaledInterruptProperties"; '
            "$v = (Get-ItemProperty -Path $rp -Name 'MSISupported' -ErrorAction SilentlyContinue).MSISupported; "
            "if ($v -eq 1) { 'enabled' } else { 'default' } "
            "} else { 'not_supported' } "
            "} else { 'not_supported' }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command=(
            "try { "
            "$a = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction Stop; "
            "$pnp = Get-PnpDevice | Where-Object { $_.FriendlyName -eq $a.InterfaceDescription } "
            "| Select-Object -First 1; "
            "if (-not $pnp) { return 'not_supported' }; "
            '$rp = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($pnp.InstanceId)\\Device Parameters'
            '\\Interrupt Management\\MessageSignaledInterruptProperties"; '
            "if ('%value%' -eq 'enabled') { "
            "if (-not (Test-Path $rp)) { New-Item -Path $rp -Force | Out-Null }; "
            "Set-ItemProperty -Path $rp -Name 'MSISupported' -Value 1 -Type DWord -Force "
            "} else { "
            "Remove-ItemProperty -Path $rp -Name 'MSISupported' -ErrorAction SilentlyContinue "
            "}; 'ok' "
            "} catch { 'error:' + $_.Exception.Message }"
        ),
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


# Global network settings (static)
# NOTE: TCP_CHIMNEY removed - deprecated in Windows 11
# NOTE: HOST_RESOLUTION_PRIORITY split into DNS_LOCAL_PRIORITY, DNS_HOSTS_PRIORITY,
#       DNS_QUERY_PRIORITY, DNS_NETBT_PRIORITY (each manages 1 registry value)
# NOTE: NAGLE_ALGORITHM split: TCP_ACK_FREQUENCY and TCP_DEL_ACK_TICKS are separate
# NOTE: MAX_USER_PORT split: TCP_NUM_CONNECTIONS is a separate tweak
# NOTE: QOS_BANDWIDTH split: QOS_NLA is a separate tweak
# === Idle Wi-Fi radio while a wired link is up ===
# A Wi-Fi adapter that is enabled but not connected still scans for networks on
# a timer, and each scan is kernel-mode work on the same cores the game uses.
# LatencyMon's own guidance when chasing DPC spikes is to disable the WLAN
# adapter and re-measure, which is as close to a documented mechanism as this
# gets. The dev machine is the exact case: Wi-Fi present, Disconnected, enabled,
# with Ethernet carrying all the traffic.
#
# This is `advanced` on purpose, and it is the one setting here whose risk is
# not about performance: turning the radio off and later unplugging the cable
# leaves a machine with no network and no obvious reason why. The user asked for
# it to require an explicit confirmation, which is what `advanced` plus a
# risk_warning surfaces in the UI.
#
# The safety that matters is in the command, not the warning: apply refuses to
# disable anything unless it can first see a connected wired link. A warning the
# user clicked past three weeks ago is not a safeguard.
# Finding the Wi-Fi adapter, shared by detect and apply so they cannot disagree.
#
# `-Physical` is deliberately absent, and this is the whole bug. Once
# `Disable-NetAdapter` has run, the adapter reports `Status = 'Not Present'` and
# `Get-NetAdapter -Physical` stops returning it at all — measured on the host, and
# not even `-IncludeHidden` brings it back. So after a successful apply:
#   * detect saw no Wi-Fi adapter and answered `not_applicable`, which is why
#     verification failed with expected='radio_off' detected='not_applicable'
#   * and apply's *enable* branch answered "no Wi-Fi adapter on this machine",
#     so fpstune could switch the radio off and then could not switch it back on
# A one-way door, dressed as a tweak. Without `-Physical` the adapter is still
# there (`Virtual = False`, `HardwareInterface = True`), so those two properties
# reproduce what `-Physical` meant while surviving the state this setting creates.
_WIFI_ADAPTERS = (
    "$wifi = @(Get-NetAdapter -EA SilentlyContinue | Where-Object { "
    "$_.PhysicalMediaType -like '*802.11*' -and -not $_.Virtual -and $_.HardwareInterface }); "
)

# The wired link the guard depends on is by definition connected, so `-Physical`
# would work here — it uses the same lookup anyway, because two spellings of "which
# adapters count" in one setting is how they drift apart.
_WIRED_LINKS_UP = (
    "$wired = @(Get-NetAdapter -EA SilentlyContinue | Where-Object { "
    "$_.PhysicalMediaType -eq '802.3' -and -not $_.Virtual -and $_.Status -eq 'Up' }); "
)

# `AdminStatus`, not `Status`. Status describes what the link is doing and takes at
# least three values here — 'Up', 'Disconnected', 'Not Present' — so the old
# `Status -ne 'Disabled'` test would have called a disabled adapter 'radio_on' even
# once it could see it. AdminStatus is the administrative state that
# Disable-NetAdapter actually writes: 'Down' when off, 'Up' when on, whether or not
# anything is connected. An enabled-but-unconnected radio still scans, and that is
# exactly the case this setting exists for, so it must read as radio_on.
_RADIO_IS_ON = "@($wifi | Where-Object { $_.AdminStatus -ne 'Down' }).Count -gt 0"

NETWORK_WIFI_RADIO_WHEN_WIRED = SettingExecutor(
    id="network:wifi_radio_when_wired",
    category=SettingCategory.NETWORK,
    display_name="Wi-Fi Radio While Wired",
    description="An enabled Wi-Fi adapter keeps scanning for networks even with nothing "
    "connected, and every scan is kernel work competing with the game.",
    value_type=SettingValueType.CHOICE,
    choices=("radio_on", "radio_off", "not_applicable"),
    default_value="radio_on",
    recommended_value="radio_off",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="This switches your Wi-Fi adapter off. If you later unplug the Ethernet cable "
    "you will have no network at all, with nothing on screen explaining why — re-enable it here, "
    "or in Windows' network adapter settings. Applying is refused while no wired link is "
    "connected, so it cannot strand you at the moment you press it, only afterwards. The benefit "
    "is a mechanism rather than a measurement: periodic scans are real kernel work, but no "
    "isolated figure for their cost was found.",
    sources=["https://www.resplendence.com/latencymon"],
    current_impact="Radio on: the adapter scans on a timer, adding kernel work during play",
    recommended_impact="Radio off: no scans while you are on the cable",
    scope=SettingScope.COMPLETE,
    category_order=30,
    impact_scores={"latency_spike_ms": "removes periodic scan wakeups", "stability": "high"},
    effect="Turns off an idle Wi-Fi radio while the wired link carries the traffic",
    # not_applicable covers both "no Wi-Fi adapter" and "no wired link", because
    # in either case the recommendation is meaningless rather than unapplied.
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _WIFI_ADAPTERS + _WIRED_LINKS_UP + "if ($wifi.Count -eq 0 -or $wired.Count -eq 0) "
        "{ 'not_applicable' } "
        f"elseif ({_RADIO_IS_ON}) {{ 'radio_on' }} "
        "else { 'radio_off' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        _WIFI_ADAPTERS + "if ($wifi.Count -eq 0) { 'error: no Wi-Fi adapter on this machine' } "
        "elseif ('%value%' -eq 'radio_off') { "
        # The guard: never take away the only link the machine has.
        + _WIRED_LINKS_UP
        + "if ($wired.Count -eq 0) { 'error: no connected wired link, refusing to disable Wi-Fi' } "
        "else { try { $wifi | Disable-NetAdapter -Confirm:$false -EA Stop; 'ok' } "
        "catch { 'error: ' + $_.Exception.Message } } "
        "} else { try { $wifi | Enable-NetAdapter -Confirm:$false -EA Stop; 'ok' } "
        "catch { 'error: ' + $_.Exception.Message } }"
    ),
    apply_args={},
    apply_value_map={},
)


def create_mtu_setting(interface_index: int, display_name: str, path_mtu: int) -> SettingExecutor:
    """Create an MTU setting whose target is the measured path MTU.

    ``path_mtu`` comes from ``utils.path_mtu.probe_path_mtu()`` — a binary search over
    don't-fragment probes — and the setting is only registered when that search
    concluded. There is no fallback constant on purpose: 1492 is right on a PPPoE
    line and wrong on the majority of connections that carry 1500, and either
    hardcoded guess is the class of defect the product goal's first clause names.

    Frames larger than the path carries get fragmented at best, and on a router that
    swallows the "fragmentation needed" reply they are dropped with no notice at all
    — a PMTU black hole, where a download stalls until TCP times out and retries
    smaller. Game traffic itself is unaffected: an FPS sends a few hundred bytes per
    packet, nowhere near any MTU. The copy says so rather than implying a latency win.

    Args:
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).
        path_mtu: Measured path MTU in bytes.

    Returns:
        SettingExecutor for this adapter's IPv4 MTU.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:mtu",
        category=SettingCategory.NETWORK,
        display_name=f"MTU ({display_name})",
        description="The largest frame this adapter sends without fragmenting. It should match "
        "what the line actually carries, which fpstune measures rather than assumes.",
        value_type=SettingValueType.INT,
        # 1280 is the IPv6 minimum link MTU; below it a path is broken, not small.
        min_value=1280,
        max_value=1500,
        default_value=1500,
        recommended_value=path_mtu,
        requires_reboot=False,
        evidence_level="proven",
        risk_level="low",
        sources=[
            "https://datatracker.ietf.org/doc/html/rfc1191",
            "https://datatracker.ietf.org/doc/html/rfc2516",
            "https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/network-communication-fails-mtu-size",
        ],
        current_impact=f"Above {path_mtu}: oversized frames fragment, or vanish where the "
        "reply is filtered",
        recommended_impact=f"{path_mtu}: every frame fits the path, so nothing fragments or stalls",
        scope=SettingScope.RECOMMENDED,
        category_order=23,
        effect="Matches the interface MTU to the measured path MTU",
        # No latency figure: fragmentation costs throughput and stall time on large
        # transfers, and game packets are far below any MTU. Claiming milliseconds
        # here would be the invented-number defect this file has paid for before.
        impact_scores={"packet_loss": "removes PMTU black-hole stalls"},
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$i = Get-NetIPInterface -InterfaceIndex %ifindex% -AddressFamily IPv4 "
            "-ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if (-not $i) { 'not_available' } else { [int]$i.NlMtu }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        # netsh, not Set-NetIPInterface: the cmdlet writes the interface MTU for the
        # current boot, while `store=persistent` survives a restart, which is what a
        # tweak has to mean. The index is a command argument here, not stored
        # identity, which is the C5 exception netsh already has.
        apply_type=DetectType.NETSH,
        apply_command="interface ipv4 set subinterface %ifindex% mtu=%value% store=persistent",
        apply_args={"ifindex": interface_index},
        apply_value_map={},
    )


def create_link_capability_setting(interface_index: int, display_name: str) -> SettingExecutor:
    """Create a read-only advisory comparing the negotiated link to the adapter's own ceiling.

    fpstune can read this and cannot fix it: a link below the adapter's capability is
    a cable, a port or a far-end limit, none of which is a registry value. C1 calls
    that advisory, so it reports and never writes.

    The ceiling comes from the adapter's own ``*SpeedDuplex`` ``ValidRegistryValues``,
    and two traps decide how it is read:

    * ``ValidDisplayValues`` is localised — this Turkish install returns
      "1.0 Gbps Tam İkili" — so the human-readable list is unparseable by design.
      Only the numeric list is stable.
    * That numeric enum is vendor-extended. The NDIS range documents 0-7, while this
      Realtek publishes 2500 for 2.5 Gbps (measured: ``0,1,2,3,4,6,2500``). A value
      outside both the documented range and the set of real Ethernet rates is not
      guessed at — the whole reading is reported ``not_available``, because a wrong
      ceiling means telling a user their perfectly good link is broken.
    """
    return SettingExecutor(
        id=f"network:{interface_index}:link_capability",
        category=SettingCategory.NETWORK,
        display_name=f"Link Speed vs Adapter Capability ({display_name})",
        description="Compares the speed this link negotiated with the fastest speed the adapter "
        "itself supports. A gap is a cable, switch port or far-end limit, not a Windows setting.",
        value_type=SettingValueType.CHOICE,
        choices=("at_capability", "below_capability"),
        default_value="below_capability",
        recommended_value="at_capability",
        requires_reboot=False,
        evidence_level="proven",
        risk_level="safe",
        sources=[
            "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics",
            "https://www.cisco.com/c/en/us/support/docs/lan-switching/ethernet/10561-3.html",
        ],
        current_impact="Below capability: the line is capped by cable or port, not by the adapter",
        recommended_impact="At capability: the link runs at the fastest rate the adapter supports",
        scope=SettingScope.RECOMMENDED,
        category_order=24,
        effect="Reports a link running below the adapter's own maximum. Check the cable "
        "(Cat 5e or better for 1 Gbps, Cat 6 for 2.5 Gbps and above), try another switch port, "
        "and confirm the far end supports the higher rate",
        impact_scores={"bandwidth": "up to the full gap between negotiated and supported rate"},
        is_readonly=True,
        detect_type=DetectType.POWERSHELL,
        detect_command=(
            "$a = Get-NetAdapter -InterfaceIndex %ifindex% -ErrorAction SilentlyContinue; "
            "if (-not $a -or $a.Status -ne 'Up' -or -not $a.Speed) { 'not_available' } else { "
            "$prop = Get-NetAdapterAdvancedProperty -InterfaceIndex %ifindex% "
            "-RegistryKeyword '*SpeedDuplex' -ErrorAction SilentlyContinue; "
            "if (-not $prop -or -not $prop.ValidRegistryValues) { 'not_available' } else { "
            # Documented NDIS members, then the real Ethernet rates a vendor may
            # splice in as a literal Mbps figure. Anything else is unrecognised.
            "$known = @{1=10;2=10;3=100;4=100;5=1000;6=1000;7=10000;"
            "2500=2500;5000=5000;10000=10000;25000=25000;40000=40000}; "
            "$ceiling = 0; $unknown = $false; "
            "foreach ($v in $prop.ValidRegistryValues) { "
            "$n = 0; if (-not [int]::TryParse($v, [ref]$n)) { continue }; "
            "if ($n -eq 0) { continue }; "
            "if ($known.ContainsKey($n)) { if ($known[$n] -gt $ceiling) { $ceiling = $known[$n] } } "
            "else { $unknown = $true } } "
            "$linked = [int]([math]::Round($a.Speed / 1000000)); "
            # Write-Output, not Write-Host. Host output bypasses the pipeline, so a
            # batch group's `| Out-String` never sees it — the warning is lost and
            # the stray line costs every setting in that group a live subprocess
            # (measured: two such commands took a group of 12 down). Through the
            # pipeline it becomes part of the captured value, and the detect path
            # strips FPSTUNE_WARN lines before reading the value off the last line.
            "if ($unknown -or $ceiling -le 0) { "
            "Write-Output ('FPSTUNE_WARN: unrecognised *SpeedDuplex values on ' + $a.Name + "
            "' (' + ($prop.ValidRegistryValues -join ',') + '), cannot derive a link ceiling'); "
            "'not_available' } "
            "elseif ($linked -ge $ceiling) { 'at_capability' } "
            "else { Write-Output ('FPSTUNE_WARN: ' + $a.Name + ' linked at ' + $linked + "
            "' Mbps but the adapter supports ' + $ceiling + ' Mbps'); 'below_capability' } } }"
        ),
        detect_args={"ifindex": interface_index},
        value_map={},
        apply_type=DetectType.POWERSHELL,
        apply_command="",
        apply_args={},
        apply_value_map={},
    )


NETWORK_SETTINGS: list[SettingExecutor] = [
    NETWORK_WIFI_RADIO_WHEN_WIRED,
    TCP_AUTO_TUNING,
    NAGLE_ALGORITHM,
    TCP_ACK_FREQUENCY,
    TCP_DEL_ACK_TICKS,
    SCALING_HEURISTICS,
    CONGESTION_PROVIDER,
    RECEIVE_SIDE_SCALING,
    RECEIVE_SEGMENT_COALESCING,
    NETWORK_THROTTLING,
    DNS_SECURITY,
    DNS_OVER_HTTPS,
    DNS_LOCAL_PRIORITY,
    DNS_HOSTS_PRIORITY,
    DNS_QUERY_PRIORITY,
    DNS_NETBT_PRIORITY,
    QOS_BANDWIDTH,
    QOS_NLA,
    TCP_FAST_OPEN,
    MAX_USER_PORT,
    TCP_NUM_CONNECTIONS,
    TCP_TIMED_WAIT_DELAY,
    IPV6_PRIVACY,
    IPV6_RANDOM_IDS,
    TEREDO,
    TCP_TIMESTAMPS,
    TCP_ECN,
    DEFAULT_TTL,
]
