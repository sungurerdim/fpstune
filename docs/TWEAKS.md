# fpstune Tweaks Reference

A hand-maintained reference of manual **Apply** and **Reset** commands for
PowerShell (Admin), covering a representative subset of the tweaks. The source
of truth for what ships is the settings registry itself
(`src/fpstune/settings/definitions/`); the README's category table is held to
the registry's own count by a test, and the counts below are the same
registry's, per category.

## Registry counts

**395 settings across 13 categories** (static registry — a real machine adds
per-adapter and per-monitor settings discovered from its own hardware):

| Category | Settings | Description |
|----------|:--------:|-------------|
| Game Configs | 174 | Per-game config file optimization (MW3, MW4, CS2, Heroes of the Storm) |
| System | 65 | Services, privacy, telemetry, cleanup |
| Maintenance | 38 | SFC, DISM, temp/cache cleanup |
| GPU | 30 | NVIDIA/AMD driver profile optimizations |
| Network | 28 | TCP/IP, DNS, QoS, per-adapter keywords |
| Power | 25 | CPU clock behaviour, core parking, USB suspend |
| Launchers | 12 | Steam, Battle.net overlay/GPU/shader settings |
| Core | 6 | Priority separation, responsiveness, GPU priority |
| Game | 5 | Game Mode, Game Bar, HAGS |
| Audio | 5 | Audio enhancements, loudness EQ |
| Visual | 3 | Animations, transparency, smooth scrolling |
| Storage | 3 | NVMe, disk timeout, write caching |
| Timer | 1 | Timer resolution |

The sections below do not map one-to-one onto those categories: they document
the tweaks worth doing by hand, grouped the way a person would look for them.
Everything not listed here is still in the app, with its own detect, apply,
reset and verify.

---

## Timer

### HPET (High Precision Event Timer)

> ⚠️ **EXPERIMENTAL** - Results vary by hardware. Benchmark before/after.

Platform clock for timing. Disabling may improve performance on some systems.

```powershell
# Apply (Disable HPET)
bcdedit /deletevalue useplatformclock

# Reset (Windows default)
bcdedit /deletevalue useplatformclock
```

> Note: Windows default is to NOT have this value set. Both apply and reset use `deletevalue`.

### Dynamic Tick

> ⚠️ **EXPERIMENTAL** - Results vary by hardware. Benchmark before/after.

Allows CPU to skip timer interrupts when idle. Disabling ensures consistent timing.

```powershell
# Apply (Disable dynamic tick)
bcdedit /set disabledynamictick yes

# Reset (Windows default)
bcdedit /deletevalue disabledynamictick
```

### TSC Sync Policy

> ⚠️ **EXPERIMENTAL** - Results vary by hardware. Benchmark before/after.

Time Stamp Counter synchronization between CPU cores.

```powershell
# Apply (Enhanced - better for multi-core)
bcdedit /set tscsyncpolicy enhanced

# Reset (Windows default)
bcdedit /deletevalue tscsyncpolicy
```

### Timer Resolution

> ⚠️ **EXPERIMENTAL** - May increase power usage. Effects vary by hardware.

Forces high-resolution timer (0.5ms).

```powershell
# Apply (Enable high resolution)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\kernel" -Name "GlobalTimerResolutionRequests" -Value 1 -Type DWord -Force

# Reset (Windows default)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\kernel" -Name "GlobalTimerResolutionRequests" -Value 0 -Type DWord -Force
```

---

## Power

### Power Plan

Active power scheme for system performance.

```powershell
# Apply (High Performance)
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c

# Apply (Ultimate Performance - requires unlocking first)
powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61
powercfg /setactive e9a42b02-d5df-448d-aa00-03f14749eb61

# Reset (Balanced)
powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e
```

### CPU Min/Max States

Processor performance states (P-states).

```powershell
# Apply (5% min, 100% max - balanced gaming)
powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 893dee8e-2bef-41e0-89c6-b55d0929964c 5
powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 bc5038f7-23e0-4960-96da-33abaf5935ec 100
powercfg /setactive SCHEME_CURRENT

# Reset (Windows default - 5% min, 100% max)
powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 893dee8e-2bef-41e0-89c6-b55d0929964c 5
powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 bc5038f7-23e0-4960-96da-33abaf5935ec 100
powercfg /setactive SCHEME_CURRENT
```

> Note: Setting min to 100% wastes power without measurable gaming benefit. 5% allows CPU to idle efficiently while still boosting quickly when needed.

---

## Priority

### Win32 Priority Separation

CPU scheduling for foreground applications.

```powershell
# Apply (Prioritize programs - 0x26)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\PriorityControl" -Name "Win32PrioritySeparation" -Value 38 -Type DWord -Force

# Reset (Default - 0x02)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\PriorityControl" -Name "Win32PrioritySeparation" -Value 2 -Type DWord -Force
```

### System Responsiveness (MMCSS)

Percentage of CPU reserved for background tasks.

```powershell
# Apply (10% reserved - more for games)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" -Name "SystemResponsiveness" -Value 10 -Type DWord -Force

# Reset (20% reserved)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" -Name "SystemResponsiveness" -Value 20 -Type DWord -Force
```

### Network Throttling Index

Network throttling for multimedia applications.

```powershell
# Apply (Disable throttling)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" -Name "NetworkThrottlingIndex" -Value 0xFFFFFFFF -Type DWord -Force

# Reset (Default - 10 packets/ms)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" -Name "NetworkThrottlingIndex" -Value 10 -Type DWord -Force
```

---

## Visual

### Visual Effects

Windows animations and visual effects.

```powershell
# Apply (Disable all for performance)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects" -Name "VisualFXSetting" -Value 2 -Type DWord -Force

# Reset (Let Windows decide)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects" -Name "VisualFXSetting" -Value 0 -Type DWord -Force
```

### Menu Show Delay

Delay before menus appear.

```powershell
# Apply (Fast - 50ms)
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "MenuShowDelay" -Value "50" -Type String -Force

# Reset (Default - 400ms)
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "MenuShowDelay" -Value "400" -Type String -Force
```

---

## Storage

### NTFS Last Access Update

Updates file access timestamps. Disabling reduces disk I/O.

```powershell
# Apply (Disable)
fsutil behavior set disablelastaccess 1

# Reset (Enable)
fsutil behavior set disablelastaccess 0
```

### Long Paths

Enable paths longer than 260 characters.

```powershell
# Apply (Enable)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -Type DWord -Force

# Reset (Disable)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 0 -Type DWord -Force
```

### Prefetch

Application prefetching. Safe to keep enabled on SSDs.

```powershell
# Apply (Enable for apps and boot)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters" -Name "EnablePrefetcher" -Value 3 -Type DWord -Force

# Disable
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters" -Name "EnablePrefetcher" -Value 0 -Type DWord -Force
```

---

## GPU

### NVIDIA Settings

> ⚠️ **USE NVIDIA CONTROL PANEL** - Registry-based NVIDIA tweaks are unreliable.

The registry path `...\Class\{4d36e968...}\0000` is **not consistent** across systems:
- Multi-GPU systems have different adapter indices
- Driver updates can change paths
- Effects vary by driver version

**Recommended:** Use NVIDIA Control Panel or [NVIDIA Profile Inspector](https://github.com/Orbmu2k/nvidiaProfileInspector) for:
- Power Management Mode → Prefer Maximum Performance
- Threaded Optimization → Off (per-game basis)
- Low Latency Mode → Ultra (per-game basis)

### Hardware Accelerated GPU Scheduling (HAGS)

> ⚠️ **EXPERIMENTAL** - Benchmark your specific games. May help or hurt depending on title.

```powershell
# Apply (Enable)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "HwSchMode" -Value 2 -Type DWord -Force

# Reset (Disable)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "HwSchMode" -Value 1 -Type DWord -Force
```

### Multiplane Overlay (MPO)

> ⚠️ **ONLY DISABLE IF EXPERIENCING ISSUES** - Stutter, flickering, or black screens.

MPO is a valid optimization. Only disable if you have visible problems.

```powershell
# Apply (Disable - only if issues)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\Dwm" -Name "OverlayTestMode" -Value 5 -Type DWord -Force

# Reset (Enable - recommended default)
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\Dwm" -Name "OverlayTestMode" -ErrorAction SilentlyContinue
```

### Fullscreen Optimizations

Windows fullscreen optimizations (borderless windowed).

```powershell
# Apply (Disable globally)
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_FSEBehaviorMode" -Value 2 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_HonorUserFSEBehaviorMode" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_FSEBehavior" -Value 2 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_FSEBehaviorMode" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_HonorUserFSEBehaviorMode" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_FSEBehavior" -Value 0 -Type DWord -Force
```

---

## Game

### Game Mode

Windows Game Mode for gaming optimizations.

```powershell
# Apply (Enable)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "AllowAutoGameMode" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "AutoGameModeEnabled" -Value 1 -Type DWord -Force

# Reset (Disable)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "AllowAutoGameMode" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "AutoGameModeEnabled" -Value 0 -Type DWord -Force
```

### Game Bar

Xbox Game Bar overlay.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "UseNexusForGameBarEnabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\GameDVR" -Name "AllowGameDVR" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "UseNexusForGameBarEnabled" -Value 1 -Type DWord -Force
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\GameDVR" -Name "AllowGameDVR" -ErrorAction SilentlyContinue
```

### Background Recording (Game DVR)

Automatic game recording.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_Enabled" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\System\GameConfigStore" -Name "GameDVR_Enabled" -Value 1 -Type DWord -Force
```

### Variable Refresh Rate (VRR)

System-wide VRR support.

```powershell
# Apply (Enable VRR - merges with existing settings)
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
$current = (Get-ItemProperty -Path $regPath -Name "DirectXUserGlobalSettings" -EA SilentlyContinue).DirectXUserGlobalSettings
if ($current -and $current -match "VRROptimizeEnable=\d") {
    $new = $current -replace "VRROptimizeEnable=\d", "VRROptimizeEnable=1"
} elseif ($current) {
    $new = $current.TrimEnd(";") + ";VRROptimizeEnable=1;"
} else {
    $new = "VRROptimizeEnable=1;"
}
Set-ItemProperty -Path $regPath -Name "DirectXUserGlobalSettings" -Value $new -Type String -Force

# Reset (Disable VRR - merges with existing settings)
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
$current = (Get-ItemProperty -Path $regPath -Name "DirectXUserGlobalSettings" -EA SilentlyContinue).DirectXUserGlobalSettings
if ($current -and $current -match "VRROptimizeEnable=\d") {
    $new = $current -replace "VRROptimizeEnable=\d", "VRROptimizeEnable=0"
    Set-ItemProperty -Path $regPath -Name "DirectXUserGlobalSettings" -Value $new -Type String -Force
}
```

> Note: This properly merges with existing DirectXUserGlobalSettings rather than overwriting other flags.

---

## Audio

### Audio Enhancements

System-wide audio processing.

```powershell
# Note: Best configured per-device via Sound Settings
# Registry method varies by audio driver
```

### Exclusive Mode

Allow applications exclusive audio device access.

```powershell
# Note: Configured per-device in Sound Settings > Properties > Advanced
# "Allow applications to take exclusive control of this device"
```

---

## Network

### TCP Auto-Tuning

Automatic TCP window size adjustment.

```powershell
# Apply (Normal - recommended)
netsh interface tcp set global autotuninglevel=normal

# Disable (may help with some routers)
netsh interface tcp set global autotuninglevel=disabled
```

### Nagle's Algorithm

> ℹ️ **TCP LATENCY ONLY** - Only affects TCP traffic. Most modern games use UDP.

TCP packet batching. Disabling reduces latency for TCP connections.

```powershell
# Apply (Disable for physical adapters only)
# Get physical adapter interface GUIDs
$physicalGuids = Get-NetAdapter | Where-Object {
    $_.Status -eq 'Up' -and
    -not $_.Virtual -and
    $_.InterfaceDescription -notlike '*Virtual*' -and
    $_.InterfaceDescription -notlike '*Hyper-V*' -and
    $_.InterfaceDescription -notlike '*VPN*'
} | ForEach-Object {
    (Get-NetAdapterAdvancedProperty -Name $_.Name -RegistryKeyword 'NetworkAddress' -EA SilentlyContinue).RegistryValue
    # Fallback: use interface GUID from registry
    $guid = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Adapters\$($_.InterfaceGuid)" -EA SilentlyContinue).IpConfig
    if ($guid) { $guid -replace '.*\\',''}
}

$interfaces = Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces'
foreach ($iface in $interfaces) {
    $ifaceGuid = $iface.PSChildName
    # Only apply to physical adapters (check if has DefaultGateway = active network)
    $gw = (Get-ItemProperty $iface.PSPath -EA SilentlyContinue).DefaultGateway
    if ($gw) {
        Set-ItemProperty -Path $iface.PSPath -Name 'TcpNoDelay' -Value 1 -Type DWord -Force
        Set-ItemProperty -Path $iface.PSPath -Name 'TcpAckFrequency' -Value 1 -Type DWord -Force
        Set-ItemProperty -Path $iface.PSPath -Name 'TcpDelAckTicks' -Value 0 -Type DWord -Force
    }
}

# Reset (Remove keys from all interfaces)
$interfaces = Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces'
foreach ($iface in $interfaces) {
    Remove-ItemProperty -Path $iface.PSPath -Name 'TcpNoDelay' -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $iface.PSPath -Name 'TcpAckFrequency' -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $iface.PSPath -Name 'TcpDelAckTicks' -ErrorAction SilentlyContinue
}
```

### Receive Side Scaling (RSS)

Distribute network processing across CPU cores.

```powershell
# Apply (Enable)
netsh interface tcp set global rss=enabled

# Disable
netsh interface tcp set global rss=disabled
```

### Receive Segment Coalescing (RSC)

Packet batching. Disabling reduces latency.

```powershell
# Apply (Disable for lower latency)
netsh interface tcp set global rsc=disabled

# Reset (Enable)
netsh interface tcp set global rsc=enabled
```

### DNS (Cloudflare Security)

Fast DNS with malware blocking.

```powershell
# Apply (Cloudflare Security DNS - physical adapters only)
$adapters = Get-NetAdapter | Where-Object {
    $_.Status -eq 'Up' -and
    -not $_.Virtual -and
    $_.InterfaceDescription -notlike '*Virtual*' -and
    $_.InterfaceDescription -notlike '*Hyper-V*' -and
    $_.InterfaceDescription -notlike '*VPN*' -and
    $_.InterfaceDescription -notlike '*Tunnel*'
}
foreach ($adapter in $adapters) {
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses ('1.1.1.2','1.0.0.2')
}

# Reset (DHCP/Automatic - physical adapters only)
$adapters = Get-NetAdapter | Where-Object {
    $_.Status -eq 'Up' -and
    -not $_.Virtual -and
    $_.InterfaceDescription -notlike '*Virtual*' -and
    $_.InterfaceDescription -notlike '*Hyper-V*'
}
foreach ($adapter in $adapters) {
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses
}
```

> Note: Only applies to physical adapters (Ethernet/Wi-Fi). VPN and tunnel adapters are excluded to avoid breaking connectivity.

### Per-Adapter: Interrupt Moderation

> ℹ️ Replace `$adapterName` with your adapter name (e.g., "Ethernet", "Wi-Fi").

```powershell
# List available physical adapters
Get-NetAdapter | Where-Object {-not $_.Virtual -and $_.Status -eq 'Up'} | Select Name, InterfaceDescription

# Apply (Disable for lower latency)
$adapterName = "Ethernet"  # Change to your adapter name
Set-NetAdapterAdvancedProperty -Name $adapterName -RegistryKeyword "*InterruptModeration" -RegistryValue 0 -EA SilentlyContinue

# Reset (Enable)
Set-NetAdapterAdvancedProperty -Name $adapterName -RegistryKeyword "*InterruptModeration" -RegistryValue 1 -EA SilentlyContinue
```

### Per-Adapter: Flow Control

```powershell
# Apply (Disable)
$adapterName = "Ethernet"  # Change to your adapter name
Set-NetAdapterAdvancedProperty -Name $adapterName -RegistryKeyword "*FlowControl" -RegistryValue 0 -EA SilentlyContinue

# Reset (Enable - Rx & Tx)
Set-NetAdapterAdvancedProperty -Name $adapterName -RegistryKeyword "*FlowControl" -RegistryValue 3 -EA SilentlyContinue
```

### Per-Adapter: Energy Efficient Ethernet (EEE)

```powershell
# Apply (Disable - prevents wake-up latency)
$adapterName = "Ethernet"  # Change to your adapter name
Set-NetAdapterAdvancedProperty -Name $adapterName -RegistryKeyword "*EEE" -RegistryValue 0 -EA SilentlyContinue

# Reset (Enable)
Set-NetAdapterAdvancedProperty -Name $adapterName -RegistryKeyword "*EEE" -RegistryValue 1 -EA SilentlyContinue
```

> Note: Not all adapters support all properties. Use `-EA SilentlyContinue` to skip unsupported properties.

---

## Display

There is no "display" category in the registry: resolution and refresh-rate
settings are generated per monitor at runtime (from the panel's own supported
modes) and filed under the GPU category in the app. They appear here as their
own heading because a person looking for them thinks "display", not "GPU".

### Resolution & Refresh Rate

Dynamic settings per monitor. Use the fpstune web UI or Windows Settings.

```powershell
# List available modes
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorListedSupportedSourceModes

# Setting a mode goes through the Windows display API (native code), so fpstune
# does it from the web UI (Hardware tab), not from a shell command.
```

---

## System

### Memory

#### Standby Memory Purge

> ⚠️ **REQUIRES EXTERNAL TOOL** - PowerShell cannot directly clear standby memory.

Clears standby memory list to free RAM for games.

```powershell
# The [System.GC]::Collect() method does NOT clear Windows standby memory!
# It only affects .NET managed memory within the current process.

# Option 1: Use RAMMap from Sysinternals (recommended)
# Download: https://learn.microsoft.com/en-us/sysinternals/downloads/rammap
# Run: rammap.exe -Et

# Option 2: Use EmptyStandbyList (requires download)
# https://github.com/svcondor/EmptyStandbyList
# Run: EmptyStandbyList.exe standbylist

# Option 3: Windows built-in (limited)
# This only works within current process, not system-wide
# [System.GC]::Collect() - NOT effective for this purpose

# Reset: Not applicable (one-time action)
```

> Note: Standby memory is NOT wasted memory. Windows uses it for caching and will release it when needed. Only clear if you have specific memory pressure issues.

### Services

#### SysMain (Superfetch)

Preloads apps into RAM. Unnecessary on SSD systems.

```powershell
# Apply (Disable)
Stop-Service -Name "SysMain" -Force
Set-Service -Name "SysMain" -StartupType Disabled

# Reset (Enable)
Set-Service -Name "SysMain" -StartupType Automatic
Start-Service -Name "SysMain"
```

#### DiagTrack (Telemetry)

Windows telemetry service.

```powershell
# Apply (Disable)
Stop-Service -Name "DiagTrack" -Force
Set-Service -Name "DiagTrack" -StartupType Disabled

# Reset (Enable)
Set-Service -Name "DiagTrack" -StartupType Automatic
Start-Service -Name "DiagTrack"
```

#### Windows Search (WSearch)

File indexing service.

```powershell
# Apply (Disable)
Stop-Service -Name "WSearch" -Force
Set-Service -Name "WSearch" -StartupType Disabled

# Reset (Enable)
Set-Service -Name "WSearch" -StartupType Automatic
Start-Service -Name "WSearch"
```

#### NVIDIA Telemetry

NVIDIA usage data collection. (Only for NVIDIA GPUs)

```powershell
# Apply (Disable)
Stop-Service -Name "NvTelemetryContainer" -Force -ErrorAction SilentlyContinue
Set-Service -Name "NvTelemetryContainer" -StartupType Disabled -ErrorAction SilentlyContinue

# Reset (Enable)
Set-Service -Name "NvTelemetryContainer" -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service -Name "NvTelemetryContainer" -ErrorAction SilentlyContinue
```

#### Nahimic Audio Service

Audio enhancement that can cause micro-stutters.

```powershell
# Apply (Disable)
Stop-Service -Name "NahimicService" -Force -ErrorAction SilentlyContinue
Set-Service -Name "NahimicService" -StartupType Disabled -ErrorAction SilentlyContinue

# Reset (Enable)
Set-Service -Name "NahimicService" -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service -Name "NahimicService" -ErrorAction SilentlyContinue
```

#### Fax Service

Legacy fax service.

```powershell
# Apply (Disable)
Stop-Service -Name "Fax" -Force -ErrorAction SilentlyContinue
Set-Service -Name "Fax" -StartupType Disabled -ErrorAction SilentlyContinue

# Reset (Enable)
Set-Service -Name "Fax" -StartupType Manual -ErrorAction SilentlyContinue
```

#### Windows Error Reporting

Crash reporting to Microsoft.

```powershell
# Apply (Disable)
Stop-Service -Name "WerSvc" -Force -ErrorAction SilentlyContinue
Set-Service -Name "WerSvc" -StartupType Disabled -ErrorAction SilentlyContinue

# Reset (Enable)
Set-Service -Name "WerSvc" -StartupType Manual -ErrorAction SilentlyContinue
```

#### Retail Demo Service

Demo mode for retail stores.

```powershell
# Apply (Disable)
Stop-Service -Name "RetailDemo" -Force -ErrorAction SilentlyContinue
Set-Service -Name "RetailDemo" -StartupType Disabled -ErrorAction SilentlyContinue

# Reset (Enable)
Set-Service -Name "RetailDemo" -StartupType Manual -ErrorAction SilentlyContinue
```

#### WAP Push Message Routing (dmwappushservice)

MDM/Intune device management. Keep enabled if work/school managed.

```powershell
# Apply (Disable)
Stop-Service -Name "dmwappushservice" -Force -ErrorAction SilentlyContinue
Set-Service -Name "dmwappushservice" -StartupType Disabled -ErrorAction SilentlyContinue

# Reset (Enable)
Set-Service -Name "dmwappushservice" -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service -Name "dmwappushservice" -ErrorAction SilentlyContinue
```

#### Xbox Services

Keep enabled if using Xbox Game Pass or Play Anywhere titles.

```powershell
# Apply (Disable all Xbox services)
$xboxServices = @("XblAuthManager", "XblGameSave", "XboxNetApiSvc", "XboxGipSvc")
foreach ($svc in $xboxServices) {
    Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
    Set-Service -Name $svc -StartupType Disabled -ErrorAction SilentlyContinue
}

# Reset (Enable all Xbox services)
$xboxServices = @("XblAuthManager", "XblGameSave", "XboxNetApiSvc", "XboxGipSvc")
foreach ($svc in $xboxServices) {
    Set-Service -Name $svc -StartupType Manual -ErrorAction SilentlyContinue
}
```

#### Background Apps

Prevents apps from running in background. Saves 500MB-1.2GB RAM.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" -Name "GlobalUserDisabled" -Value 1 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" -Name "GlobalUserDisabled" -Value 0 -Type DWord -Force
```

#### Telemetry Scheduled Tasks (9 tasks)

Disables telemetry data collection tasks including Microsoft Compatibility Appraiser.

```powershell
# Apply (Disable all)
$tasks = @(
    "\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
    "\Microsoft\Windows\Customer Experience Improvement Program\KernelCeipTask",
    "\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
    "\Microsoft\Windows\Application Experience\ProgramDataUpdater",
    "\Microsoft\Windows\Application Experience\StartupAppTask",
    "\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
    "\Microsoft\Windows\Autochk\Proxy",
    "\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector",
    "\Microsoft\Windows\Device Information\Device"
)
foreach ($task in $tasks) {
    Disable-ScheduledTask -TaskName ($task -split '\\')[-1] -TaskPath ($task -replace '\\[^\\]*$','') -ErrorAction SilentlyContinue
}

# Reset (Enable all)
foreach ($task in $tasks) {
    Enable-ScheduledTask -TaskName ($task -split '\\')[-1] -TaskPath ($task -replace '\\[^\\]*$','') -ErrorAction SilentlyContinue
}
```

### Privacy

#### Advertising ID

Unique ID for cross-app ad tracking.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo" -Name "Enabled" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo" -Name "Enabled" -Value 1 -Type DWord -Force
```

#### Activity History (Timeline)

Tracks app usage for Timeline feature.

```powershell
# Apply (Disable)
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Name "EnableActivityFeed" -Value 0 -Type DWord -Force

# Reset (Enable)
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Name "EnableActivityFeed" -ErrorAction SilentlyContinue
```

#### Windows Consumer Features

Suggestions, tips, and promoted apps in Start menu.

```powershell
# Apply (Disable)
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent" -Name "DisableWindowsConsumerFeatures" -Value 1 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent" -Name "DisableWindowsConsumerFeatures" -Value 0 -Type DWord -Force
```

#### Microsoft Edge Telemetry

Edge browser diagnostic data collection.

```powershell
# Apply (Disable)
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" -Name "DiagnosticData" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" -Name "DiagnosticData" -Value 2 -Type DWord -Force
```

#### Cortana

Microsoft's voice assistant. Deprecated in Win11 but still collects data.

```powershell
# Apply (Disable)
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search" -Name "AllowCortana" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search" -Name "AllowCortana" -Value 1 -Type DWord -Force
```

#### Bing Search in Start Menu

Web search results in Start menu searches.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Search" -Name "BingSearchEnabled" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Search" -Name "BingSearchEnabled" -Value 1 -Type DWord -Force
```

#### Typing & Inking Personalization

Collects typing/handwriting data for ML training.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\InputPersonalization" -Name "RestrictImplicitTextCollection" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\InputPersonalization" -Name "RestrictImplicitInkCollection" -Value 1 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\InputPersonalization" -Name "RestrictImplicitTextCollection" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\InputPersonalization" -Name "RestrictImplicitInkCollection" -Value 0 -Type DWord -Force
```

#### Diagnostic Data Level (AllowTelemetry)

System-wide telemetry policy. Enterprise=Off, Home/Pro=Basic minimum.

```powershell
# Apply (Disable - set to minimum)
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -Name "AllowTelemetry" -Value 0 -Type DWord -Force

# Reset (Enable - full telemetry)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -Name "AllowTelemetry" -Value 3 -Type DWord -Force
```

#### Windows Copilot

AI assistant in Windows 11.

```powershell
# Apply (Disable)
New-Item -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" -Name "TurnOffWindowsCopilot" -Value 1 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" -Name "TurnOffWindowsCopilot" -Value 0 -Type DWord -Force
```

#### Windows Ads & Suggestions (13 registry keys)

Ads in File Explorer, Start menu, lock screen, and auto-installed apps.

```powershell
# Apply (Disable all)
$cdm = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
Set-ItemProperty -Path $cdm -Name "SilentInstalledAppsEnabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SoftLandingEnabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338387Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338388Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338389Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338393Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-353694Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-353696Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "RotatingLockScreenEnabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "RotatingLockScreenOverlayEnabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced" -Name "ShowSyncProviderNotifications" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced" -Name "Start_IrisRecommendations" -Value 0 -Type DWord -Force
New-Item -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\UserProfileEngagement" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\UserProfileEngagement" -Name "ScoobeSystemSettingEnabled" -Value 0 -Type DWord -Force

# Reset (Enable all)
$cdm = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
Set-ItemProperty -Path $cdm -Name "SilentInstalledAppsEnabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SoftLandingEnabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338387Enabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338388Enabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338389Enabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-338393Enabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-353694Enabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "SubscribedContent-353696Enabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "RotatingLockScreenEnabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $cdm -Name "RotatingLockScreenOverlayEnabled" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced" -Name "ShowSyncProviderNotifications" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced" -Name "Start_IrisRecommendations" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\UserProfileEngagement" -Name "ScoobeSystemSettingEnabled" -Value 1 -Type DWord -Force
```

### UX/Shutdown Tweaks

> ⚠️ **NOT A GAMING PERFORMANCE TWEAK** - These affect shutdown behavior, not FPS.

#### Fast Shutdown/Startup (5 registry keys)

> ⚠️ **DATA LOSS RISK** - Reduces time for apps to save data on shutdown.

Reduces timeouts for hung apps and services. May cause unsaved work to be lost.

**NOT recommended for default profile. Only enable if you understand the risks.**

```powershell
# Apply (Faster shutdown - with data loss risk)
New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize" -Name "StartupDelayInMSec" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "AutoEndTasks" -Value "1" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "HungAppTimeout" -Value "2000" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "WaitToKillAppTimeout" -Value "2000" -Type String -Force
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control" -Name "WaitToKillServiceTimeout" -Value "2000" -Type String -Force

# Reset (Safe defaults)
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize" -Name "StartupDelayInMSec" -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "AutoEndTasks" -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "HungAppTimeout" -Value "5000" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "WaitToKillAppTimeout" -Value "5000" -Type String -Force
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control" -Name "WaitToKillServiceTimeout" -Value "5000" -Type String -Force
```

### Performance

#### Gaming Priority - MMCSS (6 registry keys)

Increases CPU/GPU priority for games and disables network throttling.

```powershell
# Apply (Optimize)
$mmcss = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
$games = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
Set-ItemProperty -Path $mmcss -Name "SystemResponsiveness" -Value 10 -Type DWord -Force
Set-ItemProperty -Path $mmcss -Name "NetworkThrottlingIndex" -Value 0xFFFFFFFF -Type DWord -Force
New-Item -Path $games -Force | Out-Null
Set-ItemProperty -Path $games -Name "GPU Priority" -Value 8 -Type DWord -Force
Set-ItemProperty -Path $games -Name "Priority" -Value 6 -Type DWord -Force
Set-ItemProperty -Path $games -Name "Scheduling Category" -Value "High" -Type String -Force
Set-ItemProperty -Path $games -Name "SFIO Priority" -Value "High" -Type String -Force

# Reset (Default)
Set-ItemProperty -Path $mmcss -Name "SystemResponsiveness" -Value 20 -Type DWord -Force
Set-ItemProperty -Path $mmcss -Name "NetworkThrottlingIndex" -Value 10 -Type DWord -Force
Set-ItemProperty -Path $games -Name "GPU Priority" -Value 2 -Type DWord -Force
Set-ItemProperty -Path $games -Name "Priority" -Value 2 -Type DWord -Force
Set-ItemProperty -Path $games -Name "Scheduling Category" -Value "Medium" -Type String -Force
Set-ItemProperty -Path $games -Name "SFIO Priority" -Value "Normal" -Type String -Force
```

#### Accessibility Key Popups (3 registry keys)

Disables Sticky Keys (Shift x5), Filter Keys, Toggle Keys popups.

```powershell
# Apply (Disable popups)
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\StickyKeys" -Name "Flags" -Value "506" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\Keyboard Response" -Name "Flags" -Value "122" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\ToggleKeys" -Name "Flags" -Value "58" -Type String -Force

# Reset (Enable popups)
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\StickyKeys" -Name "Flags" -Value "510" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\Keyboard Response" -Name "Flags" -Value "126" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\ToggleKeys" -Name "Flags" -Value "62" -Type String -Force
```

#### Mouse Acceleration (3 registry keys)

Disabling gives raw 1:1 mouse input for FPS games.

```powershell
# Apply (Disable acceleration)
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseSpeed" -Value "0" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseThreshold1" -Value "0" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseThreshold2" -Value "0" -Type String -Force

# Reset (Enable acceleration)
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseSpeed" -Value "1" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseThreshold1" -Value "6" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseThreshold2" -Value "10" -Type String -Force
```

#### Fast Startup (Hybrid Boot)

Hybrid shutdown that saves kernel state. Can cause driver issues.

```powershell
# Apply (Disable)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name "HiberbootEnabled" -Value 0 -Type DWord -Force

# Reset (Enable)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name "HiberbootEnabled" -Value 1 -Type DWord -Force
```

### Cleanup

#### DISM Cleanup

Cleans Windows component store. Can free several GB. Takes 5-15 minutes.

```powershell
# Apply (Run cleanup)
Dism.exe /online /Cleanup-Image /StartComponentCleanup /ResetBase

# Reset: Not applicable (one-time action)
```

#### Temp Files Cleanup

Clears Windows and user temp directories.

```powershell
# Apply (Run cleanup)
Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Windows\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue

# Reset: Not applicable (one-time action)
```

#### Shader Cache Cleanup

Clears GPU shader cache. Games rebuild shaders on next launch.

```powershell
# Apply (Run cleanup)
Remove-Item -Path "$env:LOCALAPPDATA\NVIDIA\DXCache\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:LOCALAPPDATA\NVIDIA\GLCache\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:LOCALAPPDATA\AMD\DXCache\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:LOCALAPPDATA\D3DSCache\*" -Recurse -Force -ErrorAction SilentlyContinue

# Reset: Not applicable (one-time action)
```

### Maintenance

#### System File Checker

Scans and repairs Windows system files.

```powershell
# Apply (Run scan)
sfc /scannow

# Reset: Not applicable (repair action)
```

#### DISM Health Check

Checks and repairs Windows image health.

```powershell
# Apply (Run health check)
Dism.exe /online /Cleanup-Image /RestoreHealth

# Reset: Not applicable (repair action)
```

---

## All-in-One Scripts

### Apply All Privacy Tweaks

```powershell
# Run as Administrator
# Disable all telemetry and privacy-invasive features

# Services
Stop-Service -Name "DiagTrack" -Force -ErrorAction SilentlyContinue
Set-Service -Name "DiagTrack" -StartupType Disabled -ErrorAction SilentlyContinue
Stop-Service -Name "dmwappushservice" -Force -ErrorAction SilentlyContinue
Set-Service -Name "dmwappushservice" -StartupType Disabled -ErrorAction SilentlyContinue

# Scheduled Tasks
$tasks = @(
    "\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
    "\Microsoft\Windows\Customer Experience Improvement Program\KernelCeipTask",
    "\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
    "\Microsoft\Windows\Application Experience\ProgramDataUpdater",
    "\Microsoft\Windows\Application Experience\StartupAppTask",
    "\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
    "\Microsoft\Windows\Autochk\Proxy",
    "\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector",
    "\Microsoft\Windows\Device Information\Device"
)
foreach ($task in $tasks) {
    Disable-ScheduledTask -TaskName ($task -split '\\')[-1] -TaskPath ($task -replace '\\[^\\]*$','') -ErrorAction SilentlyContinue
}

# Registry - Privacy
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo" -Name "Enabled" -Value 0 -Type DWord -Force
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Name "EnableActivityFeed" -Value 0 -Type DWord -Force
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -Name "AllowTelemetry" -Value 0 -Type DWord -Force
New-Item -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" -Name "TurnOffWindowsCopilot" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Search" -Name "BingSearchEnabled" -Value 0 -Type DWord -Force

Write-Host "Privacy tweaks applied!" -ForegroundColor Green
```

### Apply All Gaming Performance Tweaks

```powershell
# Run as Administrator
# Optimize for gaming performance

# MMCSS Gaming Priority
$mmcss = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
$games = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
Set-ItemProperty -Path $mmcss -Name "SystemResponsiveness" -Value 10 -Type DWord -Force
Set-ItemProperty -Path $mmcss -Name "NetworkThrottlingIndex" -Value 0xFFFFFFFF -Type DWord -Force
New-Item -Path $games -Force | Out-Null
Set-ItemProperty -Path $games -Name "GPU Priority" -Value 8 -Type DWord -Force
Set-ItemProperty -Path $games -Name "Priority" -Value 6 -Type DWord -Force
Set-ItemProperty -Path $games -Name "Scheduling Category" -Value "High" -Type String -Force
Set-ItemProperty -Path $games -Name "SFIO Priority" -Value "High" -Type String -Force

# Fast Shutdown
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "HungAppTimeout" -Value "2000" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "WaitToKillAppTimeout" -Value "2000" -Type String -Force
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control" -Name "WaitToKillServiceTimeout" -Value "2000" -Type String -Force

# Mouse Acceleration Off
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseSpeed" -Value "0" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseThreshold1" -Value "0" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseThreshold2" -Value "0" -Type String -Force

# Accessibility Popups Off
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\StickyKeys" -Name "Flags" -Value "506" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\Keyboard Response" -Name "Flags" -Value "122" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Accessibility\ToggleKeys" -Name "Flags" -Value "58" -Type String -Force

# Menu Delay
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "MenuShowDelay" -Value "50" -Type String -Force

Write-Host "Gaming performance tweaks applied!" -ForegroundColor Green
```

### Reset All to Defaults

```powershell
# Run as Administrator
# Reset all fpstune tweaks to Windows defaults

# Services - Enable
$services = @("DiagTrack", "dmwappushservice", "SysMain")
foreach ($svc in $services) {
    Set-Service -Name $svc -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service -Name $svc -ErrorAction SilentlyContinue
}

# Scheduled Tasks - Enable
$tasks = @(
    "\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
    "\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
    "\Microsoft\Windows\Device Information\Device"
)
foreach ($task in $tasks) {
    Enable-ScheduledTask -TaskName ($task -split '\\')[-1] -TaskPath ($task -replace '\\[^\\]*$','') -ErrorAction SilentlyContinue
}

# Registry - Reset to defaults
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo" -Name "Enabled" -Value 1 -Type DWord -Force
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Name "EnableActivityFeed" -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" -Name "AllowTelemetry" -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" -Name "TurnOffWindowsCopilot" -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Search" -Name "BingSearchEnabled" -Value 1 -Type DWord -Force

# Performance - Reset
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "HungAppTimeout" -Value "5000" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "WaitToKillAppTimeout" -Value "5000" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Mouse" -Name "MouseSpeed" -Value "1" -Type String -Force
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "MenuShowDelay" -Value "400" -Type String -Force

Write-Host "All tweaks reset to defaults!" -ForegroundColor Yellow
```

---

## Sources & References

- [Microsoft Learn: Configure Windows Diagnostic Data](https://learn.microsoft.com/en-us/windows/privacy/configure-windows-diagnostic-data-in-your-organization)
- [Microsoft Learn: MMCSS](https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service)
- [Microsoft Learn: QueryDisplayConfig](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig)
- [Microsoft Learn: Network Adapter Performance Tuning](https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics)
- [GamingPCSetup Research](https://djdallmann.github.io/GamingPCSetup/)
- [Winaero Tweaker](https://winaero.com/)
- [O&O ShutUp10++](https://www.oo-software.com/en/shutup10)
- [Win11Debloat](https://github.com/Raphire/Win11Debloat)
- [Chris Titus WinUtil](https://github.com/ChrisTitusTech/winutil)
