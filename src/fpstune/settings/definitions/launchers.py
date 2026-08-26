"""Game launcher setting definitions.

Contains Steam and Battle.net optimization settings configurable
via VDF files, JSON config, and registry.

Detection notes:
- Steam settings use PowerShell to read VDF (plain text key-value) files.
- Battle.net settings use PowerShell to read/write Battle.net.config JSON.
- All settings return "not_installed" when the launcher is not found.
"""

from __future__ import annotations

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# === Steam Path Detection Helper ===
# Reused in all Steam detect commands
_STEAM_PATH_PS = (
    "$sp = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Valve\\Steam' "
    "-Name 'InstallPath' -EA SilentlyContinue).InstallPath; "
    "if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\\SOFTWARE\\WOW6432Node\\Valve\\Steam' "
    "-Name 'InstallPath' -EA SilentlyContinue).InstallPath }; "
)

# === Steam Settings ===

STEAM_DOWNLOADS_DURING_GAMEPLAY = SettingExecutor(
    id="launcher:steam:downloads_during_gameplay",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Downloads During Gameplay",
    short_name="Steam downloads while playing",
    description="Allow Steam to download game updates while you are in-game. "
    "Disabling prevents bandwidth contention and CPU spikes.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://help.steampowered.com/en/faqs/view/15CD-2049-E4DD-B255"],
    current_impact="Enabled: Steam downloads updates mid-game → bandwidth spikes, micro-stutters",
    recommended_impact="Disabled: No downloads during gameplay → consistent network and CPU",
    scope=SettingScope.RECOMMENDED,
    category_order=0,
    effect="Prevents Steam from downloading during active gaming sessions",
    impact_scores={"fps_1_percent_low": "+0-3%", "latency_ms": -3, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _STEAM_PATH_PS + "if (-not $sp) { Write-Output 'not_installed'; return }; "
        "$vdf = Join-Path $sp 'config\\config.vdf'; "
        "if (-not (Test-Path $vdf)) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($vdf, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'"AllowDownloadsDuringGameplay"\\s+"([^"]+)"\') { '
        "if ($Matches[1] -eq '0') { Write-Output 'disabled' } else { Write-Output 'enabled' } "
        "} else { Write-Output 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_config_vdf_toggle",
    apply_args={"key": "AllowDownloadsDuringGameplay"},
    apply_value_map={"disabled": "0", "enabled": "1"},
)

STEAM_OVERLAY = SettingExecutor(
    id="launcher:steam:overlay",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Overlay",
    short_name="Steam overlay",
    description="In-game overlay (Shift+Tab). Disabling frees GPU memory and reduces micro-stutters.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://help.steampowered.com/en/faqs/view/37E2-5A3C-D72E-0C45"],
    current_impact="Enabled: Overlay hooks into game process → GPU memory overhead, rare stutters",
    recommended_impact="Disabled: No overlay hook → slightly less GPU/RAM overhead",
    scope=SettingScope.COMPLETE,
    category_order=1,
    effect="Disabling Steam overlay reduces process hook overhead",
    impact_scores={"fps_cpu_bound": "+0-2%", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _STEAM_PATH_PS + "if (-not $sp) { Write-Output 'not_installed'; return }; "
        '$lcfg = Get-ChildItem "$sp\\userdata\\*\\config\\localconfig.vdf" -EA SilentlyContinue | '
        "Sort-Object LastWriteTime -Descending | Select-Object -First 1; "
        "if (-not $lcfg) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($lcfg.FullName, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'"EnableGameOverlay"\\s+"([^"]+)"\') { '
        "if ($Matches[1] -eq '0') { Write-Output 'disabled' } else { Write-Output 'enabled' } "
        "} else { Write-Output 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_localconfig_vdf_toggle",
    apply_args={"key": "EnableGameOverlay"},
    apply_value_map={"disabled": "0", "enabled": "1"},
)

STEAM_CEF_GPU = SettingExecutor(
    id="launcher:steam:cef_gpu",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Browser GPU Compositing",
    short_name="Steam browser GPU use",
    description="Steam UI uses Chromium Embedded Framework with GPU. "
    "Disabling reduces idle GPU usage while Steam is open.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Forces the Steam client UI onto CPU rendering. Expect a slower, less responsive "
    "store and library, and on some systems visual glitches or a blank client window. Steam must "
    "be fully exited for the change to take effect. Reset this setting if the client misbehaves.",
    sources=["https://github.com/nicehash/NiceHashQuickMiner/issues/135"],
    current_impact="Enabled: Steam UI renders with GPU compositing → idle GPU usage",
    recommended_impact="Disabled: Steam UI uses CPU rendering → less GPU memory/heat at idle",
    scope=SettingScope.COMPLETE,
    category_order=2,
    effect="Disabling Steam CEF GPU compositing lowers idle GPU usage",
    impact_scores={"vram_mb": -300, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$sp = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Valve\\Steam' "
        "-Name 'InstallPath' -EA SilentlyContinue).InstallPath; "
        "if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\\SOFTWARE\\WOW6432Node\\Valve\\Steam' "
        "-Name 'InstallPath' -EA SilentlyContinue).InstallPath }; "
        "if (-not $sp) { Write-Output 'not_installed'; return }; "
        "$val = (Get-ItemProperty -Path 'HKCU:\\Software\\Valve\\Steam' "
        "-Name 'BrowserFlags' -EA SilentlyContinue).BrowserFlags; "
        "if ($val -and $val -like '*cef-disable-gpu*') { Write-Output 'disabled' } "
        "else { Write-Output 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_cef_toggle",
    apply_args={},
    apply_value_map={"disabled": "disabled", "enabled": "enabled"},
)

STEAM_SHADER_PRECACHE = SettingExecutor(
    id="launcher:steam:shader_precache",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Shader Pre-Caching",
    short_name="Steam shader pre-caching",
    description="Pre-downloads shader caches. Enabling reduces first-launch stutters.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://help.steampowered.com/en/faqs/view/23FF-E5B3-97E1-42B9"],
    current_impact="Enabled: Shaders downloaded in background → less in-game compilation stutter",
    recommended_impact="Keep enabled: Prevents shader compile micro-stutters on first game launch",
    scope=SettingScope.COMPLETE,
    category_order=3,
    effect="Pre-cached shaders prevent in-game compilation micro-stutters",
    impact_scores={"fps_1_percent_low": "+0-2%", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _STEAM_PATH_PS + "if (-not $sp) { Write-Output 'not_installed'; return }; "
        '$lcfg = Get-ChildItem "$sp\\userdata\\*\\config\\localconfig.vdf" -EA SilentlyContinue | '
        "Sort-Object LastWriteTime -Descending | Select-Object -First 1; "
        "if (-not $lcfg) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($lcfg.FullName, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'"DisableShaderCache"\\s+"([^"]+)"\') { '
        "if ($Matches[1] -eq '1') { Write-Output 'disabled' } else { Write-Output 'enabled' } "
        "} else { Write-Output 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_localconfig_vdf_toggle",
    apply_args={"key": "DisableShaderCache"},
    # DisableShaderCache=1 means caching is DISABLED, so invert
    apply_value_map={"enabled": "0", "disabled": "1"},
)

STEAM_BROADCAST = SettingExecutor(
    id="launcher:steam:broadcast",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Broadcasting",
    short_name="Steam broadcasting",
    description="Steam live stream feature. Disabling removes background encode overhead.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "friends_only", "public"),
    default_value="friends_only",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Turns off Steam Broadcasting entirely, so friends can no longer watch your "
    "games and you cannot start a broadcast without re-enabling it. The overhead this removes "
    "only exists while a broadcast is actually running — if you never stream, it changes nothing.",
    sources=["https://help.steampowered.com/en/faqs/view/7FA5-1EA7-CEB6-B5AC"],
    current_impact="Enabled: Stream encoding runs in background → CPU/GPU overhead when streaming",
    recommended_impact="Disabled: No stream capture overhead",
    scope=SettingScope.COMPLETE,
    category_order=4,
    effect="Disabling Steam broadcasting removes background encode CPU overhead",
    impact_scores={"fps_cpu_bound": "+0-1%", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _STEAM_PATH_PS + "if (-not $sp) { Write-Output 'not_installed'; return }; "
        '$lcfg = Get-ChildItem "$sp\\userdata\\*\\config\\localconfig.vdf" -EA SilentlyContinue | '
        "Sort-Object LastWriteTime -Descending | Select-Object -First 1; "
        "if (-not $lcfg) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($lcfg.FullName, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'"BroadcastPermission"\\s+"([^"]+)"\') { '
        "$v = $Matches[1]; "
        "switch ($v) { '0' { 'disabled' } '2' { 'friends_only' } '4' { 'public' } default { 'friends_only' } } "
        "} else { Write-Output 'friends_only' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_localconfig_vdf_toggle",
    apply_args={"key": "BroadcastPermission"},
    apply_value_map={"disabled": "0", "friends_only": "2", "public": "4"},
)

# === Battle.net Settings ===

BNET_HARDWARE_ACCEL = SettingExecutor(
    id="launcher:bnet:hardware_accel",
    category=SettingCategory.LAUNCHER,
    display_name="Battle.net Hardware Acceleration",
    short_name="Battle.net hardware acceleration",
    description="Battle.net app UI uses GPU for rendering. "
    "Disabling reduces idle GPU usage while the launcher is open.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Moves the Battle.net client UI to CPU rendering. The launcher becomes slower to "
    "navigate and some users see rendering artifacts or a black client area. Battle.net must be "
    "fully closed for it to apply. Reset this setting if the launcher stops drawing correctly.",
    sources=["https://us.battle.net/support/en/article/76459"],
    current_impact="Enabled: GPU renders Battle.net UI → idle GPU memory/power usage",
    recommended_impact="Disabled: CPU renders UI → less GPU memory pressure while gaming",
    scope=SettingScope.COMPLETE,  # experimental risk is offered, never assumed (C2/#30)
    category_order=10,
    effect="Disabling Battle.net hardware acceleration frees GPU resources for games",
    impact_scores={"vram_mb": -20, "cpu_usage": 0.5, "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$bnetCfg = Join-Path $env:APPDATA 'Battle.net\\Battle.net.config'; "
        "if (-not (Test-Path $bnetCfg)) { Write-Output 'not_installed'; return }; "
        "try { "
        "$j = Get-Content $bnetCfg -Raw | ConvertFrom-Json; "
        "$val = $j.Application.BrowserHardwareAcceleration; "
        "if ($null -eq $val) { Write-Output 'enabled' } "
        "elseif ($val -eq 'false' -or $val -eq $false) { Write-Output 'disabled' } "
        "else { Write-Output 'enabled' } "
        "} catch { Write-Output 'not_installed' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="bnet_json_toggle",
    apply_args={"section": "Application", "key": "BrowserHardwareAcceleration"},
    apply_value_map={"disabled": "false", "enabled": "true"},
)

BNET_P2P = SettingExecutor(
    id="launcher:bnet:p2p",
    category=SettingCategory.LAUNCHER,
    display_name="Battle.net P2P Downloads",
    short_name="Battle.net P2P downloads",
    description="Peer-to-peer update distribution. Disabling stops upload bandwidth usage.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://us.battle.net/support/en/article/76459"],
    current_impact="Enabled: Battle.net uploads game data to other users → background upload bandwidth",
    recommended_impact="Disabled: No P2P uploads → full upload bandwidth available for gaming",
    scope=SettingScope.RECOMMENDED,
    category_order=11,
    effect="Disabling P2P eliminates background upload bandwidth usage",
    impact_scores={"latency_ms": -1, "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$bnetCfg = Join-Path $env:APPDATA 'Battle.net\\Battle.net.config'; "
        "if (-not (Test-Path $bnetCfg)) { Write-Output 'not_installed'; return }; "
        "try { "
        "$j = Get-Content $bnetCfg -Raw | ConvertFrom-Json; "
        "$val = $j.Client.P2PEnabled; "
        "if ($null -eq $val) { Write-Output 'enabled' } "
        "elseif ($val -eq 'false' -or $val -eq $false) { Write-Output 'disabled' } "
        "else { Write-Output 'enabled' } "
        "} catch { Write-Output 'not_installed' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="bnet_json_toggle",
    apply_args={"section": "Client", "key": "P2PEnabled"},
    apply_value_map={"disabled": "false", "enabled": "true"},
)

BNET_BACKGROUND_DOWNLOAD = SettingExecutor(
    id="launcher:bnet:background_download",
    category=SettingCategory.LAUNCHER,
    display_name="Battle.net Background Downloads",
    short_name="Battle.net background downloads",
    description="Download game updates while in-game. Disabling prevents bandwidth contention.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://us.battle.net/support/en/article/76459"],
    current_impact="Enabled: Updates download during gameplay → bandwidth spikes, CPU overhead",
    recommended_impact="Disabled: No downloads during gameplay → consistent network performance",
    scope=SettingScope.RECOMMENDED,
    category_order=12,
    effect="Prevents Battle.net from downloading during active gaming sessions",
    impact_scores={"latency_ms": -2, "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$bnetCfg = Join-Path $env:APPDATA 'Battle.net\\Battle.net.config'; "
        "if (-not (Test-Path $bnetCfg)) { Write-Output 'not_installed'; return }; "
        "try { "
        "$j = Get-Content $bnetCfg -Raw | ConvertFrom-Json; "
        "$val = $j.Client.BackgroundDownload; "
        "if ($null -eq $val) { Write-Output 'enabled' } "
        "elseif ($val -eq 'false' -or $val -eq $false) { Write-Output 'disabled' } "
        "else { Write-Output 'enabled' } "
        "} catch { Write-Output 'not_installed' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="bnet_json_toggle",
    apply_args={"section": "Client", "key": "BackgroundDownload"},
    apply_value_map={"disabled": "false", "enabled": "true"},
)

STEAM_DOWNLOAD_THROTTLE = SettingExecutor(
    id="launcher:steam:download_throttle",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Download Speed Limit",
    short_name="Steam download speed cap",
    description="Cap Steam download speed (KB/s). Set to -1 to remove the limit entirely.",
    value_type=SettingValueType.CHOICE,
    choices=("unlimited", "limited"),
    default_value="limited",
    recommended_value="unlimited",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://help.steampowered.com/en/faqs/view/15CD-2049-E4DD-B255"],
    current_impact="Limited: Steam caps download bandwidth → slower game updates",
    recommended_impact="Unlimited: Full ISP bandwidth used for downloads",
    scope=SettingScope.RECOMMENDED,
    category_order=5,
    effect="Removes Steam download speed throttle for maximum download speed",
    impact_scores={"throughput": "high", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _STEAM_PATH_PS + "if (-not $sp) { Write-Output 'not_installed'; return }; "
        "$vdf = Join-Path $sp 'config\\config.vdf'; "
        "if (-not (Test-Path $vdf)) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($vdf, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'"DownloadThrottleKbps"\\s+"([^"]+)"\') { '
        "$v = $Matches[1]; "
        "if ($v -eq '-1' -or $v -eq '0') { Write-Output 'unlimited' } else { Write-Output 'limited' } "
        "} else { Write-Output 'unlimited' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_config_vdf_toggle",
    apply_args={"key": "DownloadThrottleKbps"},
    apply_value_map={"unlimited": "-1", "limited": "10240"},
)

STEAM_STREAMING_THROTTLE = SettingExecutor(
    id="launcher:steam:streaming_throttle",
    category=SettingCategory.LAUNCHER,
    display_name="Steam Remote Play Throttle",
    short_name="Steam Remote Play throttle",
    description="Throttle Steam Remote Play streaming bandwidth. Disabling maximizes streaming quality.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Removes the Remote Play bandwidth cap, so streaming will consume as much of "
    "your connection as it can. On a shared or limited link this starves other traffic and can "
    "raise latency for everything else on the network, including the game you are streaming.",
    sources=["https://help.steampowered.com/en/faqs/view/7FA5-1EA7-CEB6-B5AC"],
    current_impact="Enabled: Streaming bandwidth artificially capped → lower quality",
    recommended_impact="Disabled: Full bandwidth used for Remote Play → maximum quality",
    scope=SettingScope.COMPLETE,
    category_order=6,
    effect="Removes Steam Remote Play bandwidth throttle",
    impact_scores={"throughput": "high", "latency_ms": 0, "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        _STEAM_PATH_PS + "if (-not $sp) { Write-Output 'not_installed'; return }; "
        "$vdf = Join-Path $sp 'config\\config.vdf'; "
        "if (-not (Test-Path $vdf)) { Write-Output 'not_installed'; return }; "
        "$c = [System.IO.File]::ReadAllText($vdf, [System.Text.Encoding]::UTF8); "
        'if ($c -match \'"StreamingThrottleEnabled"\\s+"([^"]+)"\') { '
        "if ($Matches[1] -eq '0') { Write-Output 'disabled' } else { Write-Output 'enabled' } "
        "} else { Write-Output 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_config_vdf_toggle",
    apply_args={"key": "StreamingThrottleEnabled"},
    apply_value_map={"disabled": "0", "enabled": "1"},
)

BNET_DOWNLOAD_LIMIT = SettingExecutor(
    id="launcher:bnet:download_limit",
    category=SettingCategory.LAUNCHER,
    display_name="Battle.net Download Speed Limit",
    short_name="Battle.net download cap",
    description="Cap Battle.net download speed. Set to maximum to remove the limit.",
    value_type=SettingValueType.CHOICE,
    choices=("unlimited", "limited"),
    default_value="limited",
    recommended_value="unlimited",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://us.battle.net/support/en/article/76459"],
    current_impact="Limited: Battle.net caps download speed → slower game updates",
    recommended_impact="Unlimited: Full ISP bandwidth used for downloads",
    scope=SettingScope.RECOMMENDED,
    category_order=13,
    effect="Removes Battle.net download speed cap for faster game updates",
    impact_scores={"throughput": "high", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$bnetCfg = Join-Path $env:APPDATA 'Battle.net\\Battle.net.config'; "
        "if (-not (Test-Path $bnetCfg)) { Write-Output 'not_installed'; return }; "
        "try { "
        "$j = Get-Content $bnetCfg -Raw | ConvertFrom-Json; "
        "$val = $j.Client.DownloadLimit; "
        "if ($null -eq $val -or [int]$val -ge 9999999) { Write-Output 'unlimited' } "
        "else { Write-Output 'limited' } "
        "} catch { Write-Output 'not_installed' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="bnet_json_toggle",
    apply_args={"section": "Client", "key": "DownloadLimit"},
    apply_value_map={"unlimited": "9999999", "limited": "1024"},
)

BNET_BACKGROUND_DOWNLOAD_LIMIT = SettingExecutor(
    id="launcher:bnet:background_download_limit",
    category=SettingCategory.LAUNCHER,
    display_name="Battle.net Background Download Limit",
    short_name="Battle.net background cap",
    description="Cap Battle.net background download speed. Remove limit for faster in-background updates.",
    value_type=SettingValueType.CHOICE,
    choices=("unlimited", "limited"),
    default_value="limited",
    recommended_value="unlimited",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://us.battle.net/support/en/article/76459"],
    current_impact="Limited: Background downloads throttled → slow patching when minimized",
    recommended_impact="Unlimited: Full bandwidth available for background patching",
    scope=SettingScope.RECOMMENDED,
    category_order=14,
    effect="Removes Battle.net background download speed cap",
    impact_scores={"throughput": "medium", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$bnetCfg = Join-Path $env:APPDATA 'Battle.net\\Battle.net.config'; "
        "if (-not (Test-Path $bnetCfg)) { Write-Output 'not_installed'; return }; "
        "try { "
        "$j = Get-Content $bnetCfg -Raw | ConvertFrom-Json; "
        "$val = $j.Client.BackgroundDownloadLimit; "
        "if ($null -eq $val -or [int]$val -ge 9999999) { Write-Output 'unlimited' } "
        "else { Write-Output 'limited' } "
        "} catch { Write-Output 'not_installed' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="bnet_json_toggle",
    apply_args={"section": "Client", "key": "BackgroundDownloadLimit"},
    apply_value_map={"unlimited": "9999999", "limited": "512"},
)

STEAM_SETTINGS: list[SettingExecutor] = [
    STEAM_DOWNLOADS_DURING_GAMEPLAY,
    STEAM_OVERLAY,
    STEAM_CEF_GPU,
    STEAM_SHADER_PRECACHE,
    STEAM_BROADCAST,
    STEAM_DOWNLOAD_THROTTLE,
    STEAM_STREAMING_THROTTLE,
]

BNET_SETTINGS: list[SettingExecutor] = [
    BNET_HARDWARE_ACCEL,
    BNET_P2P,
    BNET_BACKGROUND_DOWNLOAD,
    BNET_DOWNLOAD_LIMIT,
    BNET_BACKGROUND_DOWNLOAD_LIMIT,
]

LAUNCHER_SETTINGS: list[SettingExecutor] = [*STEAM_SETTINGS, *BNET_SETTINGS]
