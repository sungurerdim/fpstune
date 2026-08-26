# Windows Tweak Detection Best Practices

Reference guide for implementing locale-independent, reliable tweak detection and application methods.

## Quick Reference Table

| Detection Type | Locale-Safe Method | Avoid |
|---------------|-------------------|-------|
| **Registry** | DWORD/QWORD numeric values | String parsing |
| **Services** | `[int]$s.StartType` (2=Auto, 3=Manual, 4=Disabled) | `$s.Status` for verification |
| **Scheduled Tasks** | `[int]$task.State` (0=Disabled, 3=Ready) | String comparison |
| **BCD Settings** | WMI BcdStore element type IDs | bcdedit text parsing |
| **Power Settings** | GUIDs + hex values | powercfg text output |
| **Network Adapters** | RegistryKeyword (`*FlowControl`) + InterfaceIndex | DisplayName, adapter Name |
| **Network Virtual Filter** | `$_.Virtual` property (boolean) | Pattern matching `*Virtual*` |
| **Command Placeholders** | `%value%` syntax | `{value}` (conflicts with PowerShell braces) |
| **Audio Effects** | Check both HKLM and HKCU | HKLM only |

---

## 1. Service Detection

### Recommended Pattern: StartType (for verification)

For verifying if a service is enabled/disabled after applying settings, use `StartType`:

```powershell
# CORRECT: Check StartType for verification (reflects configuration, not runtime state)
$s = Get-Service -Name 'ServiceName' -ErrorAction SilentlyContinue
if ($s) { [int]$s.StartType } else { 'not_found' }
```

### ServiceStartMode (StartType) Values

| Value | StartType | Description |
|-------|-----------|-------------|
| 2 | Automatic | Starts at boot |
| 3 | Manual | Starts on demand |
| 4 | Disabled | Cannot start |

### ServiceControllerStatus (Status) Values

Use Status only when you need to know if the service is currently running:

| Value | Status | Description |
|-------|--------|-------------|
| 1 | Stopped | Service is not running |
| 4 | Running | Service is running |

### When to Use Which

| Use Case | Property | Why |
|----------|----------|-----|
| **Verification after enable/disable** | `StartType` | Reflects configured state, not runtime |
| **Check if currently running** | `Status` | Reflects runtime state |
| **Apply + verify cycle** | `StartType` | Services may not start immediately (dependencies, triggers) |

### Example: Service Toggle with Verification

```powershell
# Apply: Set to Manual (3) when enabling, Disabled (4) when disabling
Set-Service -Name 'ServiceName' -StartupType Manual

# Verify: Check StartType, not Status (service may not be running yet)
$s = Get-Service -Name 'ServiceName'
if ([int]$s.StartType -eq 3) { 'enabled' }  # Manual = enabled
```

### Anti-Patterns

```powershell
# WRONG: Verifying enable/disable with Status (service may not start immediately)
if ($s.Status -eq 4) { 'enabled' }  # Running doesn't mean "enabled", Stopped doesn't mean "disabled"

# WRONG: String comparison (potentially locale-dependent)
if ($s.Status -eq "Running") { ... }
```

---

## 2. Scheduled Task Detection

### Recommended Pattern

```powershell
# CORRECT: Numeric state (locale-independent)
$task = Get-ScheduledTask -TaskPath '\Path\' -TaskName 'Name' -ErrorAction SilentlyContinue
if ($task) { [int]$task.State } else { 3 }
```

### TaskState Values

| Value | State | Description |
|-------|-------|-------------|
| 0 | Unknown | State unknown |
| 1 | Disabled | Task is disabled |
| 2 | Queued | Task instances are queued |
| 3 | Ready | Task is ready to run |
| 4 | Running | Task is currently running |

### PowerShell Version Note

- PowerShell Desktop (5.1): Returns enum object
- PowerShell Core on older Windows: May return raw `SInt32`
- Solution: Always cast with `[int]` for consistency

### Error Handling

```powershell
# Proper error handling for non-existent tasks
try {
    $task = Get-ScheduledTask -TaskPath '\Path\' -TaskName 'Name' -ErrorAction Stop
    $state = [int]$task.State
} catch {
    # Task doesn't exist
    $state = 3  # Default to Ready
}
```

**Note:** `Get-ScheduledTask` produces non-terminating errors by default. Use `-ErrorAction Stop` or `SilentlyContinue`.

---

## 3. Registry Detection

### Recommended Pattern

```python
# Python with winreg - always numeric
import winreg
with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ) as key:
    value, reg_type = winreg.QueryValueEx(key, name)
    # value is numeric (DWORD) or string (REG_SZ)
```

### Value Types

| Type | Python Type | Locale-Safe |
|------|-------------|-------------|
| REG_DWORD | int | Yes |
| REG_QWORD | int | Yes |
| REG_SZ | str | Yes (if storing numbers as strings) |
| REG_BINARY | bytes | Yes |

### Best Practices

1. **Always use DWORD for boolean settings**: 0 = disabled, 1 = enabled
2. **Use value_map for translation**: Map numeric values to display strings
3. **Handle None case**: Registry key may not exist

```python
# Example value_map
value_map = {
    0: "disabled",
    1: "enabled",
    "0": "disabled",  # Handle string representation
    "1": "enabled",
    None: "enabled",  # Default when key doesn't exist
}
```

---

## 4. BCD (Boot Configuration Data) Detection

### Recommended: WMI BcdStore

```powershell
# CORRECT: WMI with element type IDs (numeric, never localized)
$bcdStore = Get-WmiObject -Namespace root\WMI -Class BcdStore
$result = $bcdStore.OpenStore("")
$store = [WMI]"$($result.Store)"

# Query element by type ID
$elem = $loader.GetElement(0x26000081)  # useplatformclock
if ($elem.ReturnValue -eq 0) {
    $value = $elem.Element.Boolean
}
```

### BCD Element Type IDs

| Setting | Element Type ID | Data Type |
|---------|----------------|-----------|
| useplatformclock | 0x26000081 | Boolean |
| useplatformtick | 0x26000082 | Boolean |
| disabledynamictick | 0x26000083 | Boolean |
| tscsyncpolicy | 0x25000084 | Integer |

### Anti-Patterns

```powershell
# WRONG: Parsing bcdedit text output
bcdedit /enum {current}
# Output contains localized "Yes/No" (e.g. German: Ja/Nein, French: Oui/Non, etc.)
```

### Fallback Strategy

If WMI fails, property names in bcdedit output are NOT localized:
- Look for `useplatformclock`, `disabledynamictick`, etc.
- If the line exists, the setting is enabled (bcdedit only shows true booleans)

---

## 5. Power Settings (powercfg)

### Recommended: GUIDs + Hex Values

```powershell
# CORRECT: Use GUIDs (never localized)
powercfg /query SCHEME_CURRENT {subgroup_guid} {setting_guid}

# Parse hex values from output
# "Current AC Power Setting Index: 0x00000001"
```

### Power Setting GUIDs

| Setting | Subgroup GUID | Setting GUID |
|---------|--------------|--------------|
| USB Selective Suspend | 2a737441-1930-4402-8d77-b2bebba308a3 | 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 |
| PCI Express ASPM | 501a4d13-42af-4429-9fd1-a8218c268e20 | ee12f906-d277-404b-b6da-e5fa1a576df5 |
| Processor Min State | 54533251-82be-4824-96c1-47b60b740d00 | 893dee8e-2bef-41e0-89c6-b55d0929964c |

### Registry Fallback

```powershell
# If powercfg parsing fails, read directly from registry
$path = "HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\{scheme}\{subgroup}\{setting}"
$val = (Get-ItemProperty -Path $path -Name 'ACSettingIndex').ACSettingIndex
```

### Parse Strategies (in order)

1. Look for "AC" keyword + hex value (`0x00000001`)
2. Look for pattern `: 0x` followed by hex digits
3. Take last hex value in output (current values come after possible values)

---

## 6. Network Adapter Advanced Properties

### Recommended: RegistryKeyword

```powershell
# CORRECT: RegistryKeyword (never localized)
$prop = Get-NetAdapterAdvancedProperty -Name 'Ethernet' `
    -RegistryKeyword '*FlowControl' -ErrorAction SilentlyContinue
$value = [int](@($prop.RegistryValue)[0])
```

### Standard RegistryKeywords

| Property | RegistryKeyword | Values |
|----------|-----------------|--------|
| Flow Control | `*FlowControl` | 0=Disabled, 1=Tx, 2=Rx, 3=Both |
| Interrupt Moderation | `*InterruptModeration` | 0=Disabled, 1=Enabled |
| RSS | `*RSS` | 0=Disabled, 1=Enabled |
| EEE | `*EEE`, `EEE`, `EEEControl` | 0=Disabled, 1=Enabled |
| Roaming Aggressiveness | `*RoamAggressiveness` | 0-4 (Lowest to Highest) |

### Handling Array Values

`RegistryValue` property may return `String[]` (array). Always use safe access:

```powershell
# CORRECT: Safe array access
[int](@($prop.RegistryValue)[0])

# WRONG: Direct cast (fails on arrays)
[int]$prop.RegistryValue  # Error: Cannot convert System.String[] to System.Int32
```

### Anti-Patterns

```powershell
# WRONG: DisplayName is localized
Get-NetAdapterAdvancedProperty -Name 'Ethernet' -DisplayName 'Flow Control'
# "Flow Control" may appear in the local language on non-English Windows
```

### Vendor Variations

Some settings use different keywords per vendor:
- **Intel**: `*EEE`
- **Realtek**: `EEE`
- **Broadcom**: `EEEControl`

Solution: Try multiple keywords:

```powershell
$keywords = @('*EEE', 'EEE', 'EEEControl', 'EnergyEfficientEthernet')
foreach ($kw in $keywords) {
    $prop = Get-NetAdapterAdvancedProperty -Name $adapter -RegistryKeyword $kw -ErrorAction SilentlyContinue
    if ($prop) { break }
}
```

---

## 7. Display Settings

### Recommended: QueryDisplayConfig API

```python
# Best modern API for Windows 10/11
from ctypes import windll, byref, sizeof

# Get buffer sizes
windll.user32.GetDisplayConfigBufferSizes(QDC_DATABASE_CURRENT, byref(path_count), byref(mode_count))

# Query display config
windll.user32.QueryDisplayConfig(QDC_DATABASE_CURRENT, byref(path_count), paths, byref(mode_count), modes, None)

# Refresh rate from mode info (rational for precision)
refresh_rate = mode.targetMode.targetVideoSignalInfo.vSyncFreq
```

### Native Resolution Detection

**EDID Preferred Timing** (most accurate):
- Parse first Detailed Timing Descriptor (DTD) at bytes 54-71
- Byte 2: H active low 8 bits
- Byte 4 (upper nibble): H active high 4 bits
- Byte 5: V active low 8 bits
- Byte 7 (upper nibble): V active high 4 bits

**EnumDisplaySettings** (fallback):
- Returns driver-supported resolutions
- Max resolution usually equals native for LCD displays

### Key Points

- QueryDisplayConfig is current best API (no newer replacement for Win11)
- EDID parsing can be unreliable (driver may ignore DTDs)
- Use QueryDisplayConfig + EDID for validation
- Display device names may have encoding issues with non-English characters

---

## 8. Netsh Commands

### Locale Considerations

- **TCP settings**: Mostly safe (`enabled`/`disabled` are not localized in values)
- **Parsing keys**: Use lowercase pattern matching
- **Fallback**: PowerShell cmdlets (Get-NetTCPSetting)

### Recommended Pattern

```python
# Primary: netsh with key pattern matching
cmd = "netsh interface tcp show global"
# Look for key in lowercase, parse value

# Fallback: PowerShell (more reliable)
cmd = "Get-NetTCPSetting -SettingName Internet | Select-Object -ExpandProperty CongestionProvider"
```

### Known Safe Keys

| Netsh Key | Safe | Notes |
|-----------|------|-------|
| `receive window auto-tuning level` | Yes | Values: normal, disabled, etc. |
| `receive-side scaling state` | Yes | Values: enabled, disabled |
| `congestion control provider` | Mostly | May need PowerShell fallback |

---

## 9. Command Placeholder Syntax

### Use `%value%` Instead of `{value}`

PowerShell scripts contain many curly braces (`{}`) which conflict with Python's `.format()` method. Use `%key%` placeholder syntax:

```python
# CORRECT: Use %key% syntax (no conflicts with PowerShell braces)
detect_command = "if ($s) { [int]$s.StartType } else { 'not_found' }"
apply_command = "Set-Service -Name 'SysMain' -StartupType %value%"
apply_args = {"value": "Manual"}

# Use substitute_placeholders() to replace %key% with values
from fpstune.utils.powershell import substitute_placeholders
cmd = substitute_placeholders(apply_command, **apply_args)
# Result: "Set-Service -Name 'SysMain' -StartupType Manual"
```

### Why %key% is Better

| Syntax | Conflicts | Escaping Needed |
|--------|-----------|-----------------|
| `{value}` | PowerShell script blocks, regex quantifiers | Yes - `{{` and `}}` everywhere |
| `%value%` | None | No escaping needed |

### Anti-Patterns

```python
# WRONG: Using {value} with PowerShell
detect_command = "if ($s) { 'ok' } else { 'fail' }".format(...)
# Raises KeyError: 's' because {} is interpreted as placeholder

# WRONG: Escaping all braces (unreadable)
detect_command = "if ($s) {{ 'ok' }} else {{ 'fail' }}"

# CORRECT: Use %key% for placeholders
detect_command = "if ($val -eq %value%) { 'match' } else { 'no' }"
```

---

## 10. Network Adapter Identification

### Use InterfaceIndex Instead of Name

Network adapter names can contain special characters, spaces, and localized text. Use `InterfaceIndex` (numeric) for commands:

```powershell
# CORRECT: Use InterfaceIndex (numeric, always safe)
Get-NetAdapterAdvancedProperty -InterfaceIndex 12 -RegistryKeyword '*FlowControl'
Set-NetAdapterLso -InterfaceIndex 12 -IPv4Enabled $true

# WRONG: Use Name (may contain special characters)
Get-NetAdapterAdvancedProperty -Name 'Realtek PCIe GbE (TM)' -RegistryKeyword '*FlowControl'
# Issues: parentheses, spaces, trademark symbol
```

### Discovery Pattern

```python
# Get both InterfaceIndex (for commands) and Name (for display)
result = subprocess.run([
    "powershell", "-NoProfile", "-Command",
    "Get-NetAdapter | ForEach-Object { \"$($_.InterfaceIndex)|$($_.Name)\" }"
], capture_output=True, text=True)

# Parse: "12|Ethernet" -> (12, "Ethernet")
for line in result.stdout.strip().split("\n"):
    idx, name = line.split("|", 1)
    interface_index = int(idx)
    display_name = name.strip()  # Use only for UI
```

### Setting ID Pattern

```python
# Use InterfaceIndex in setting ID (unique, stable)
id = f"network:{interface_index}:flow_control"  # "network:12:flow_control"

# Use display name only in UI labels
display_name = f"Flow Control ({display_name})"  # "Flow Control (Ethernet)"
```

### Why InterfaceIndex is Better

| Property | InterfaceIndex | Name |
|----------|---------------|------|
| Type | Integer | String |
| Characters | Numeric only | Any (spaces, parens, unicode) |
| Escaping | None needed | Complex escaping required |
| Localization | Not affected | May be localized |
| Stability | Changes on hardware change | Can be renamed by user |

### Anti-Patterns

```powershell
# WRONG: Using adapter name in commands
$adapter = 'Intel(R) Wi-Fi 6 AX201'  # Contains parens, spaces
Get-NetAdapter -Name $adapter  # May fail with special characters

# CORRECT: Use InterfaceIndex
$ifIndex = 12
Get-NetAdapter -InterfaceIndex $ifIndex  # Always works
```

---

## 11. Detection/Apply Consistency

### The Golden Rule

**Detection MUST read exactly what Apply writes.**

If Apply modifies a registry value, Detection must read that same registry value. If they read/write different things, verification will fail even when apply succeeds.

### Example: Power Management Setting

```python
# WRONG: Detection reads WMI, Apply writes Registry
# Apply sets PnPCapabilities registry value
# Detection checks MSPower_DeviceWakeEnable WMI (different thing!)
# Result: Verification fails even when apply succeeds

# CORRECT: Both use same source
# Apply: Sets PnPCapabilities = 24 (disable power mgmt)
# Detection: Reads PnPCapabilities value
# If PnPCapabilities == 24: 'Disabled', else: 'Enabled'
```

### Verification Flow

```
1. Apply writes value X to location L
2. Detection reads from location L
3. Compare: read_value == expected_value
4. If match: verification passes
```

### Common Mistakes

| Mistake | Apply | Detection | Why It Fails |
|---------|-------|-----------|--------------|
| WMI vs Registry | Registry write | WMI query | Different data sources |
| Status vs StartType | Set-Service | Check Status | Status is runtime, StartType is config |
| DisplayValue vs RegistryValue | Set RegistryValue | Get DisplayValue | DisplayValue is localized |

### Debugging Verification Failures

When verification fails with "expected X, got Y":

1. **Check what apply actually writes**: Log the exact value and location
2. **Check what detection reads**: Log the raw value before mapping
3. **Compare locations**: Are they the same registry key / WMI path?
4. **Check value mapping**: Is the value_map correct for both directions?

---

## 12. Network Adapter Virtual Detection

### Use `$_.Virtual` Property Instead of Pattern Matching

Windows provides a `Virtual` boolean property on network adapters. This is more reliable than pattern matching on InterfaceDescription:

```powershell
# CORRECT: Use Virtual property (reliable, handles all edge cases)
Get-NetAdapter | Where-Object { -not $_.Virtual }

# WRONG: Pattern matching on InterfaceDescription (misses edge cases)
Get-NetAdapter | Where-Object {
    $_.InterfaceDescription -notlike '*Virtual*' -and
    $_.InterfaceDescription -notlike '*Hyper-V*'
}
```

### Why Pattern Matching Fails

| Adapter Type | InterfaceDescription | Virtual Property | Pattern Match Result |
|-------------|---------------------|------------------|---------------------|
| USB Ethernet | "ASIX AX88179A USB Ethernet" | `$false` | Correctly included |
| USB Docking Ethernet | "Surface Dock Virtual Ethernet" | `$true` | Incorrectly excluded (contains "Virtual") |
| USB-C Hub Ethernet | "Realtek NDIS Virtual Miniport" | `$false` | **Incorrectly excluded** (contains "Virtual") |
| Hyper-V Virtual | "Hyper-V Virtual Ethernet Adapter" | `$true` | Correctly excluded |

Many USB ethernet adapters (especially through docking stations) use NDIS Virtual Miniport drivers but are still physical adapters. The `Virtual` property correctly identifies these as non-virtual.

### Recommended Filter

```powershell
# Keep it simple - use Virtual property for primary filter
Get-NetAdapter | Where-Object {
    -not $_.Virtual -and
    $_.Name -notlike '*vEthernet*' -and           # Hyper-V virtual switches
    $_.InterfaceDescription -notlike '*Loopback*'  # Loopback adapters
}
```

### Anti-Patterns

```powershell
# WRONG: Over-filtering with InterfaceDescription patterns
$_.InterfaceDescription -notlike '*Virtual*'  # Excludes USB ethernet adapters
$_.InterfaceDescription -notlike '*VPN*'      # May exclude legitimate adapters
$_.InterfaceDescription -notlike '*Tunnel*'   # Often unnecessary
```

---

## 13. Audio Effects Registry Locations

### Check Both HKLM and HKCU

Windows stores audio effects in two registry locations. Per-user settings in HKCU may override system settings in HKLM:

```powershell
# Check both locations for complete coverage
$audioLocations = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render',  # System
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'   # Per-user
)
```

### Loudness Equalization (LEQ) Detection

LEQ settings are stored in `FxProperties` subfolder with a specific GUID:

```powershell
# LEQ property GUID: {fc52a749-4be9-4510-896e-966ba6525980},3
$leqGuid = '{fc52a749-4be9-4510-896e-966ba6525980},3'
$fxPath = Join-Path $devicePath 'FxProperties'

# Check if LEQ is supported and enabled
if (Test-Path $fxPath) {
    try {
        $val = Get-ItemPropertyValue -Path $fxPath -Name $leqGuid -EA Stop
        $leqEnabled = ($val[0] -eq 1)
    } catch {
        # Property doesn't exist - device may still support LEQ via Enhancements tab
    }
}
```

### Effects Detection Strategy

1. **Primary**: Check standard LEQ property GUID
2. **Fallback**: Check for ANY effects properties (indicates enhancement support)
3. **Alternative**: Some drivers use different GUIDs

```powershell
# Check for effects framework presence
$props = Get-ItemProperty -Path $fxPath -EA SilentlyContinue
if ($props) {
    # Look for any GUID-based properties (effect CLSIDs)
    $effectProps = $props.PSObject.Properties | Where-Object {
        $_.Name -match '^\{[0-9a-f-]+\}'
    }
    if ($effectProps.Count -gt 0) {
        # Device has effects framework - Enhancements tab should work
    }
}
```

### Device State Filter

Only active devices should be shown:

```powershell
# Device state property: {a45c254e-df1c-4efd-8020-67d146a850e0},7
# Values: 1=Active, 2=Disabled, 4=Not present, 8=Unplugged
$devState = Get-ItemPropertyValue -Path $propsPath -Name $devStateGuid
if ($devState -ne 1) { continue }  # Skip non-active devices
```

---

## 14. General Best Practices

### Error Handling

1. **Check existence first**: Service/task may not exist on all systems
2. **Use ErrorAction**: `SilentlyContinue` for detection, `Stop` for apply
3. **Provide fallbacks**: Multiple detection strategies

### Value Mapping

```python
# Always include both int and string keys (PowerShell may return either)
value_map = {
    0: "disabled",
    "0": "disabled",
    1: "enabled",
    "1": "enabled",
    None: "enabled",  # Default
}
```

### Apply Operations

1. **Use same locale-safe approach**: GUIDs, numeric values
2. **bcdedit accepts English keywords**: `yes`, `no`, `legacy`, `enhanced` work regardless of locale
3. **PowerShell Set-* cmdlets**: Generally locale-safe (use GUIDs/numeric parameters)

### Testing

- Test on non-English Windows (Turkish, German, Chinese)
- Verify detection works after language pack installation
- Check both fresh install and upgraded systems

---

## Sources

- [ServiceControllerStatus Enum - Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/api/system.serviceprocess.servicecontrollerstatus)
- [TASK_STATE Enumeration - Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/ne-taskschd-task_state)
- [BCD Reference - Microsoft Learn](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/bcd/bcd-reference)
- [QueryDisplayConfig - Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig)
- [Get-NetAdapterAdvancedProperty - Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/netadapter/get-netadapteradvancedproperty)
- [Network Adapter Performance Tuning - Microsoft Learn](https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics)
