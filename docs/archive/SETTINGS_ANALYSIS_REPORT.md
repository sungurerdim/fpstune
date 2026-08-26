# fpstune Settings Definition Analysis Report

## Executive Summary

Analysis of all settings definitions across 11 modules found **1 CRITICAL BUG** and **multiple HIGH RISK mismatches** where:
- Detection/apply commands can return values NOT in the defined choices
- Empty value_map with detection that expects translation
- Default/recommended values that may not be reached due to detection/apply value mismatches

---

## CRITICAL FINDINGS

### 1. DNS_SECURITY (network.py) - CRITICAL BUG

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/network.py` (lines 537-589)

```python
DNS_SECURITY = SettingExecutor(
    id="network:dns_security",
    choices=("default", "cloudflare_security", "cloudflare_family"),
    value_map={},  # ❌ EMPTY
    detect_type=DetectType.POWERSHELL,
    detect_command=(...
        "if ($dns -eq '1.1.1.1' -or $dns -eq '1.0.0.1') { $result = 'cloudflare' }"  # ❌ Returns 'cloudflare'
    ...),
)
```

**Issue:** Detection can return `'cloudflare'` (line 567) but it's NOT in choices `("default", "cloudflare_security", "cloudflare_family")`

**Verification will fail when:**
- User has Cloudflare Standard DNS (1.1.1.1 / 1.0.0.1) configured
- Detection returns `'cloudflare'` which is NOT a valid choice
- Verification logic will reject this as an invalid value

**Fix Required:** Add `'cloudflare'` to choices tuple, or fix detection to map it to one of the valid choices

---

### 2. TEREDO (network.py) - HIGH RISK VALUE MISMATCH

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/network.py` (lines 799-827)

```python
TEREDO = SettingExecutor(
    id="network:teredo",
    choices=("default", "disabled"),
    default_value="default",          # ✓ IN CHOICES
    recommended_value="disabled",     # ✓ IN CHOICES
    value_map={},                     # ❌ EMPTY
    detect_type=DetectType.NETSH,
    detect_command="interface teredo show state",
    detect_args={"parse_key": "type"},
)
```

**Available teredo states from netsh:**
- `default`, `client`, `enterpriseclient`, `relay`, `server`, `none`, `disabled`

**Issue:** 
- Only `"default"` and `"disabled"` are valid choices
- But netsh can return: `"client"`, `"enterpriseclient"`, `"relay"`, `"server"`, `"none"`
- With empty value_map, these unmapped values will pass through unchanged
- Verification will FAIL if current state is `"client"` or other non-choice values

**Specific Answer to Your Request:**
| Property | Value |
|----------|-------|
| Available values | default, client, enterpriseclient, relay, server, none, disabled |
| Choices defined | ("default", "disabled") |
| default_value | "default" |
| recommended_value | "disabled" |
| Does "default" exist as option? | YES ✓ |
| Root cause | Empty value_map with netsh that returns many possible states |

---

## HIGH RISK MISMATCHES

### 3. CONGESTION_PROVIDER (network.py) - Case Sensitivity Risk

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/network.py` (lines 110-148)

```python
CONGESTION_PROVIDER = SettingExecutor(
    id="network:congestion_provider",
    choices=("CUBIC", "NewReno", "CTCP", "DCTCP", "Default"),
    value_map={},  # ❌ EMPTY
    detect_type=DetectType.POWERSHELL,
    detect_command=(...
        "if ($setting.CongestionProvider) { $setting.CongestionProvider } "
    ...),
)
```

**Issue:**
- Choices have specific casing: `"CUBIC"`, `"NewReno"`, `"CTCP"`, `"DCTCP"`, `"Default"`
- PowerShell's `$setting.CongestionProvider` may return different casing
- Empty value_map means no case normalization
- Verification could fail on case mismatch: `"cubic"` vs `"CUBIC"`

---

### 4. TCP Network Settings - Case & Format Risk

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/network.py`

Multiple settings rely on netsh/PowerShell returning exact choice strings with no mapping:

| Setting | Choices | Detection | Risk |
|---------|---------|-----------|------|
| **TCP_AUTO_TUNING** (line 45) | ("normal", "disabled", "highlyrestricted", "restricted", "experimental") | netsh returns `parse_key: "receive window auto-tuning level"` | Case sensitivity, format mismatch |
| **SCALING_HEURISTICS** (line 78) | ("enabled", "disabled") | netsh returns `parse_key: "window scaling heuristics"` | Output parsing reliability |
| **RECEIVE_SIDE_SCALING** (line 151) | ("enabled", "disabled") | netsh returns `parse_key: "receive-side scaling state"` | Hyphenation in key but not value |
| **RECEIVE_SEGMENT_COALESCING** (line 180) | ("enabled", "disabled") | netsh returns `parse_key: "receive segment coalescing state"` | Space vs underscore in key |
| **NAGLE_ALGORITHM** (line 594) | ("enabled", "disabled") | PowerShell registry inspection | Registry value type coercion |
| **IPV6_PRIVACY** (line 740) | ("enabled", "disabled") | netsh returns `parse_key: "use temporary addresses"` | Output parsing format unknown |
| **IPV6_RANDOM_IDS** (line 770) | ("enabled", "disabled") | netsh returns `parse_key: "randomize identifiers"` | Output parsing format unknown |

**Root Cause:** All have `value_map={}` (empty), relying on detection to return exact choice strings

---

### 5. NVIDIA GPU Settings - Unknown Mapping

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/gpu.py`

Multiple NVIDIA settings use NVPROFILE executor with empty value_map, but no documentation of what NVPROFILE returns:

| Setting ID | Choices | value_map |
|-----------|---------|-----------|
| `gpu-nvidia:shader_cache` | ("off", "on") | {} |
| `gpu-nvidia:texture_quality` | ("high_quality", "quality", "performance", "high_performance") | {} |
| `gpu-nvidia:aniso_sample_opt` | ("off", "on") | {} |
| `gpu-nvidia:texture_lod_bias` | ("allow", "clamp") | {} |
| `gpu-nvidia:ogl_thread_opt` | ("off", "on", "auto") | {} |
| `gpu-nvidia:cuda_force_p2` | ("off", "on") | {} |
| `gpu-nvidia:vrr_mode` | ("off", "on", "fullscreen") | {} |

**Risk:** NVPROFILE executor internals unknown - if it returns different formats (e.g., `"OFF"` vs `"off"`), verification fails

---

## MEDIUM RISK MISMATCHES

### 6. Per-Adapter Network Settings

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/network.py`

Three settings with missing value_map but PowerShell detection returns exact choice strings:

| Setting | Factory Function | Choices | value_map | Detection Return Format |
|---------|------------------|---------|-----------|------------------------|
| **Power Management** | `create_power_management_setting()` | ("Enabled", "Disabled") | {} | PowerShell returns choice strings |
| **LSO (Large Send Offload)** | `create_lso_setting()` | ("Enabled", "Disabled") | {} | PowerShell Get-NetAdapterLso returns boolean |
| **Checksum Offload** | `create_checksum_offload_setting()` | ("Enabled", "Disabled") | {} | PowerShell Get-NetAdapterChecksumOffload returns numeric |

**Risk:** If PowerShell returns numeric values but choices are strings, verification fails

---

### 7. FPS_BALANCED_PROFILE (power.py) - Custom Executor

**File:** `/home/node/fpstune/src/fpstune/settings/definitions/power.py` (lines 25-52)

```python
FPS_BALANCED_PROFILE = SettingExecutor(
    id="power:fps_balanced_profile",
    choices=("disabled", "enabled"),
    detect_command="fps_balanced_detect",  # ❌ Custom function name
    apply_command="fps_balanced_toggle",   # ❌ Custom function name
    value_map={"active": "enabled", "inactive": "disabled", "none": "disabled"},
)
```

**Risk:** Uses custom command names `"fps_balanced_detect"` and `"fps_balanced_toggle"` that must be implemented by the executor framework. If not properly implemented, detection/apply will fail silently.

---

## GOOD PATTERNS (Reference)

These settings demonstrate correct implementation with proper value_map:

| Setting | ID | value_map Quality |
|---------|-----|------------------|
| **NETWORK_THROTTLING** | network:throttling_index | ✓ Handles registry DWORD (0xFFFFFFFF → "disabled") |
| **HOST_RESOLUTION_PRIORITY** | network:host_resolution_priority | ✓ Maps 4 → "optimized", 499 → "default" |
| **GAME_MODE** | game:game_mode | ✓ Handles registry 0/1 → "disabled"/"enabled" |
| **TRIM_ENABLED** | storage:trim_enabled | ✓ Handles registry 0/1 → "enabled"/"disabled" |
| **HPET** | timer:hpet | ✓ Maps bcdedit "yes"/"no"/None → choice strings |
| **All service settings** | services:* | ✓ Maps StartType (2/4/3) → "enabled"/"disabled" |

---

## DETAILED SETTINGS MATRIX

### Legend
- ✓ GOOD: value_map properly handles detection output
- ⚠ MEDIUM: Assumes exact string match, no mapping
- ❌ HIGH: Can return invalid choice values
- 🔴 CRITICAL: Detection returns undocumented values not in choices

### Timer Settings (timer.py)
| Setting | Default | Recommended | Choices | value_map | Status |
|---------|---------|-------------|---------|-----------|--------|
| HPET | enabled | disabled | (enabled, disabled) | {yes→enabled, no→disabled, None→enabled} | ✓ |
| PLATFORM_TICK | disabled | disabled | (enabled, disabled) | {yes→enabled, no→disabled, None→disabled} | ✓ |
| DYNAMIC_TICK | enabled | enabled | (enabled, disabled) | {yes→disabled, no→enabled, None→enabled} | ✓ |
| GLOBAL_TIMER_RESOLUTION | disabled | enabled | (enabled, disabled) | {1→enabled, 0→disabled, None→disabled} | ✓ |
| TSC_SYNC_POLICY | auto | auto | (auto, legacy, enhanced) | {legacy→legacy, enhanced→enhanced, None→auto} | ✓ |

### Power Settings (power.py)
| Setting | Default | Recommended | Choices | value_map | Status |
|---------|---------|-------------|---------|-----------|--------|
| FPS_BALANCED_PROFILE | disabled | enabled | (disabled, enabled) | {active→enabled, inactive→disabled} | ⚠ Custom exec |
| USB_SELECTIVE_SUSPEND | enabled | disabled | (enabled, disabled) | {0→disabled, 1→enabled} | ✓ |
| PCIE_LINK_STATE | moderate | off | (off, moderate, maximum) | {0→off, 1→moderate, 2→maximum} | ✓ |
| WLAN_POWER_SAVING | medium | maximum_performance | (maximum_performance, low, medium, maximum) | {0→max_perf, 1→low, 2→medium, 3→maximum} | ✓ |

### Network Settings (network.py)
| Setting | Default | Recommended | Choices | value_map | Status |
|---------|---------|-------------|---------|-----------|--------|
| TCP_AUTO_TUNING | normal | normal | 5 choices | {} | ⚠ Assumes exact match |
| SCALING_HEURISTICS | disabled | disabled | (enabled, disabled) | {} | ⚠ Assumes exact match |
| CONGESTION_PROVIDER | CUBIC | CUBIC | 5 choices | {} | ❌ Case sensitivity |
| RECEIVE_SIDE_SCALING | enabled | enabled | (enabled, disabled) | {} | ⚠ Assumes exact match |
| RECEIVE_SEGMENT_COALESCING | enabled | disabled | (enabled, disabled) | {} | ⚠ Assumes exact match |
| NETWORK_THROTTLING | enabled | disabled | (enabled, disabled) | {0xFFFFFFFF→disabled, 10→enabled} | ✓ |
| **DNS_SECURITY** | default | cloudflare_security | (default, cloudflare_security, cloudflare_family) | {} | 🔴 CRITICAL |
| NAGLE_ALGORITHM | enabled | disabled | (enabled, disabled) | {} | ⚠ Assumes exact match |
| HOST_RESOLUTION_PRIORITY | default | optimized | (default, optimized) | {4→optimized, 499→default} | ✓ |
| QOS_BANDWIDTH | default | disabled | (default, disabled) | {0→disabled, None→default} | ✓ |
| IPV6_PRIVACY | enabled | disabled | (enabled, disabled) | {} | ⚠ Assumes exact match |
| IPV6_RANDOM_IDS | enabled | disabled | (enabled, disabled) | {} | ⚠ Assumes exact match |
| **TEREDO** | default | disabled | (default, disabled) | {} | ❌ HIGH risk |
| Interrupt Moderation | Enabled | Disabled | (Enabled, Disabled) | {0→Disabled, 1→Enabled} | ✓ |
| Flow Control | Rx & Tx Enabled | Disabled | 4 choices | {0→Disabled, 1→Tx, 2→Rx, 3→Rx&Tx} | ✓ |
| EEE | Enabled | Disabled | (Enabled, Disabled) | {0→Disabled, 1→Enabled} | ✓ |
| Power Management | Enabled | Disabled | (Enabled, Disabled) | {} | ⚠ PowerShell detection |
| Roaming Aggressiveness | Medium | Lowest | 5 choices | {0→Lowest, 1→Med-Low, 2→Medium, 3→Med-High, 4→Highest} | ✓ |
| LSO | Enabled | Disabled | (Enabled, Disabled) | {} | ⚠ PowerShell detection |
| Checksum Offload | Enabled | Enabled | (Enabled, Disabled) | {} | ⚠ PowerShell detection |

### GPU Settings (gpu.py)
| Setting | Default | Recommended | value_map | Status |
|---------|---------|-------------|-----------|--------|
| NVIDIA Low Latency | off | ultra | {} | ⚠ NVPROFILE unknown |
| NVIDIA Power Mode | optimal | optimal | {} | ⚠ NVPROFILE unknown |
| NVIDIA Threaded Opt | auto | on | {} | ⚠ NVPROFILE unknown |
| NVIDIA VSync | on | off | {} | ⚠ NVPROFILE unknown |
| NVIDIA Shader Cache | on | on | {} | ⚠ NVPROFILE unknown |
| NVIDIA Texture Quality | quality | performance | {} | ⚠ NVPROFILE unknown |
| NVIDIA VRR Mode | off | off | {} | ⚠ NVPROFILE unknown |
| NVIDIA BG App FPS | 0 | 30 | {} | ⚠ NVPROFILE unknown |
| NVIDIA Aniso Opt | off | on | {} | ⚠ NVPROFILE unknown |
| NVIDIA Texture LOD | allow | clamp | {} | ⚠ NVPROFILE unknown |
| NVIDIA OGL Thread | auto | on | {} | ⚠ NVPROFILE unknown |
| NVIDIA CUDA Force P2 | off | off | {} | ⚠ NVPROFILE unknown |
| AMD Anti-Lag | disabled | enabled | {0→disabled, 1→enabled} | ✓ |
| AMD Shader Cache | enabled | enabled | {0→disabled, 1→enabled} | ✓ |
| AMD VSync | enabled | disabled | {0→disabled, 1→enabled} | ✓ |

### Game Settings (game.py)
| Setting | Default | Recommended | value_map | Status |
|---------|---------|-------------|-----------|--------|
| Game Mode | enabled | enabled | {0→disabled, 1→enabled} | ✓ |
| Game Bar | enabled | disabled | {0→disabled, 1→enabled} | ✓ |
| Background Recording | disabled | disabled | {0→disabled, 1→enabled} | ✓ |
| HAGS | disabled | enabled | {1→disabled, 2→enabled} | ✓ |
| Windows VRR | disabled | enabled | {} | ⚠ PowerShell returns exact |

### System Settings (system.py)
| Setting | Default | Recommended | value_map | Status |
|---------|---------|-------------|-----------|--------|
| Memory Purge Standby | False | False | {True→True, False→False} | ✓ |
| SysMain | enabled | disabled | {2→enabled, 4→disabled, 3→enabled} | ✓ |
| DiagTrack | enabled | disabled | {2→enabled, 4→disabled, 3→enabled} | ✓ |
| WSearch | enabled | disabled | {2→enabled, 4→disabled, 3→enabled} | ✓ |
| NvTelemetry | enabled | disabled | {2→enabled, 4→disabled, 3→enabled} | ✓ |
| Nahimic | enabled | disabled | {2→enabled, 4→disabled, 3→enabled} | ✓ |

### Visual Settings (visual.py)
| Setting | Default | Recommended | value_map | Status |
|---------|---------|-------------|-----------|--------|
| Animations | enabled | disabled | {0→disabled, 400→enabled, None→enabled} | ✓ |
| Transparency | enabled | disabled | {0→disabled, 1→enabled} | ✓ |
| Smooth Scrolling | enabled | disabled | {0→disabled, 1→enabled} | ✓ |

### Audio Settings (audio.py)
| Setting | Default | Recommended | value_map | Status |
|---------|---------|-------------|-----------|--------|
| Audio Enhancements | enabled | disabled | {0→enabled, 1→disabled} | ✓ |
| Exclusive Mode | enabled | disabled | {0→enabled, 1→disabled} | ✓ |

### Storage Settings (storage.py)
| Setting | Default | Recommended | value_map | Status |
|---------|---------|-------------|-----------|--------|
| TRIM Enabled | enabled | enabled | {0→enabled, 1→disabled} | ✓ |
| Disable 8.3 | enabled | disabled | {0→enabled, 1→disabled, 2→disabled, 3→enabled} | ✓ |
| Disable Last Access | enabled | disabled | {0→enabled, 1→disabled} | ✓ |

---

## SUMMARY BY SEVERITY

### 🔴 CRITICAL (Must Fix)
1. **DNS_SECURITY** - Detection returns "cloudflare" which is NOT a valid choice

### ❌ HIGH (Fix Required)
1. **TEREDO** - Detection can return 6+ values, only 2 are in choices

### ⚠️ MEDIUM (Should Fix)
1. **CONGESTION_PROVIDER** - Case sensitivity without mapping
2. **TCP Settings** (7 settings) - Assume exact string match from netsh
3. **NVIDIA Settings** (12 settings) - Unknown NVPROFILE return format
4. **Network Adapter Settings** (3 settings) - PowerShell type coercion unknown
5. **FPS_BALANCED_PROFILE** - Custom executor, implementation unknown

### ✓ GOOD
- Timer, Power, Game, System, Visual, Audio, Storage settings (✓ proper mappings)
- Registry-based settings with proper DWORD mappings

---

## RECOMMENDATIONS

1. **Immediate (P0):**
   - Fix DNS_SECURITY: Add "cloudflare" to choices or map it in detection
   - Fix TEREDO: Add value_map for all possible netsh states

2. **High Priority (P1):**
   - Document NVPROFILE return formats
   - Add case-normalization for CONGESTION_PROVIDER
   - Add output parsing validation for netsh commands

3. **Medium Priority (P2):**
   - Test netsh output parsing for TCP settings
   - Verify PowerShell type coercion for adapter settings
   - Add unit tests for value_map completeness

4. **Best Practice:**
   - All CHOICE type settings MUST have a value_map that covers all possible detection outputs
   - No empty value_map unless detection output exactly matches one of the choices
   - Test with real system outputs, not just expected values
