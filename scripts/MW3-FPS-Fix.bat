@echo off
setlocal EnableDelayedExpansion

:: ──────────────────────────────────────────────────────────────────────────
:: MW3 FPS Fix  —  double-click and run, no installs required
:: Requires Windows 10/11 + PowerShell 5.1 (built-in on all modern Windows)
:: ──────────────────────────────────────────────────────────────────────────

:: Admin check — net session needs elevation
net session >nul 2>&1
if not errorlevel 1 goto :run

echo.
echo  Requesting administrator access (needed for firewall rules)...
powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c \"%~f0\"' -Verb RunAs"
exit /b

:run
set "_b=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $f='%_b%'; $c=[IO.File]::ReadAllText($f,[Text.Encoding]::UTF8); $m=[string]::Concat('__BEGIN','_PS__'); $i=$c.IndexOf($m); if($i -lt 0){ Write-Host '[ERROR] Marker not found.' -ForegroundColor Red; Read-Host 'Press Enter'; exit 1 }; $p=$c.Substring($i+$m.Length); $t=[IO.Path]::Combine([IO.Path]::GetTempPath(),[IO.Path]::GetRandomFileName()+'.ps1'); [IO.File]::WriteAllText($t,$p,[Text.Encoding]::UTF8); try{ & $t }finally{ Remove-Item $t -EA SilentlyContinue } }"
endlocal
exit /b

__BEGIN_PS__
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Header { param($t) Write-Host "`n$t" -ForegroundColor White }
function Write-OK     { param($t) Write-Host "  [+] $t" -ForegroundColor Green }
function Write-Skip   { param($t) Write-Host "  [-] $t" -ForegroundColor DarkGray }
function Write-Err    { param($t) Write-Host "  [X] $t" -ForegroundColor Red }

Write-Host ""
Write-Host "  MW3 FPS Fix" -ForegroundColor Cyan
Write-Host "  -------------------------------------------------------------"
Write-Host ""
Write-Host "  What would you like to do?" -ForegroundColor Cyan
Write-Host "    [1]  FPS Optimization  -- graphics tweaks, firewall, GPU stability"
Write-Host "    [2]  Crash Fix         -- clear shader / texture / crash caches"
Write-Host "    [3]  Both"
Write-Host ""
Write-Host "  Choice [1/2/3]: " -NoNewline
$choice = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown").Character
Write-Host $choice

$doFps   = $false
$doCrash = $false
switch ($choice) {
    '1' { $doFps = $true }
    '2' { $doCrash = $true }
    '3' { $doFps = $true; $doCrash = $true }
    default {
        Write-Host ""
        Write-Err "Invalid choice '$choice'. Enter 1, 2, or 3."
        Read-Host "  Press Enter to exit"
        exit 1
    }
}

# ── Locate MW3 config folder ─────────────────────────────────────────────────
Write-Header "Locating config files..."

$docPath = [System.Environment]::GetFolderPath('MyDocuments')
$codPath = Join-Path $docPath "Call of Duty MWIII\players"

if (-not (Test-Path $codPath)) {
    Write-Err "MW3 config folder not found: $codPath"
    Write-Err "Launch MW3 at least once to create config files, then re-run."
    Write-Host ""
    Read-Host "  Press Enter to exit"
    exit 1
}
Write-OK "Config folder: $codPath"

$gamerProfile = $null
$optPath      = $null
if ($doFps) {
    $gamerProfile = Get-ChildItem -Path $codPath -Recurse `
        -Filter "gamerprofile*.BASE.cst" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch 'mw3fix_backup' } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if ($gamerProfile) {
        Write-OK "gamerprofile: $($gamerProfile.Name)"
    } else {
        Write-Skip "gamerprofile*.BASE.cst not found -- texture streaming tweak will be skipped"
    }

    $optPath = Join-Path $codPath "options.4.cod23.cst"
    if (-not (Test-Path $optPath)) {
        Write-Err "options.4.cod23.cst not found: $optPath"
        Write-Err "Launch MW3, open Graphics settings once, then re-run."
        Write-Host ""
        Read-Host "  Press Enter to exit"
        exit 1
    }
    Write-OK "Options file: options.4.cod23.cst"
}

# ── Backup (FPS mode only — config files are modified) ──────────────────────
if ($doFps) {
    Write-Header "Creating backup..."

    $backupDir = Join-Path $codPath "mw3fix_backup"
    if (Test-Path $backupDir) { Remove-Item -Recurse -Force $backupDir }
    $null = New-Item -ItemType Directory -Path $backupDir -Force

    if ($gamerProfile) {
        Copy-Item $gamerProfile.FullName -Destination $backupDir -Force
        Write-OK "Backed up: $($gamerProfile.Name)"
    }
    Copy-Item $optPath -Destination $backupDir -Force
    Write-OK "Backed up: options.4.cod23.cst"
    Write-OK "Backup dir: $backupDir  (overwritten each run)"
}

# ── GPU Detection (FPS mode only) ────────────────────────────────────────────
$isNvidia = $false
$isAMD    = $false
if ($doFps) {
    Write-Header "Detecting GPU..."

    $allGpus = @(Get-WmiObject -Class Win32_VideoController)
    # Prefer confirmed discrete NVIDIA or AMD over integrated/unknown
    $gpuInfo = $allGpus | Where-Object { $_.PNPDeviceID -match 'VEN_10DE' } | Select-Object -First 1
    if (-not $gpuInfo) {
        $gpuInfo = $allGpus | Where-Object { $_.PNPDeviceID -match 'VEN_1002' } | Select-Object -First 1
    }
    if (-not $gpuInfo) { $gpuInfo = $allGpus | Select-Object -First 1 }

    if ($gpuInfo -and $gpuInfo.PNPDeviceID -match 'VEN_([0-9A-Fa-f]{4})') {
        $ven      = $Matches[1].ToUpper()
        $isNvidia = ($ven -eq '10DE')
        $isAMD    = ($ven -eq '1002')
    }
    $gpuLabel = if ($isNvidia) { 'NVIDIA' } elseif ($isAMD) { 'AMD' } else { 'Unknown vendor' }
    if ($gpuInfo) {
        Write-OK "GPU: $($gpuInfo.Name)  ($gpuLabel)"
    } else {
        Write-Skip "No GPU detected via WMI -- GPU-specific settings will be skipped"
    }
}

# ── Helper: replace one key in options.4.cod23.cst ──────────────────────────
# CST key format:  KeyName:version = "value"
# Anchors to line-start so ShadowQuality never matches ScreenSpaceShadowQuality.
function Set-CstKey {
    param([string]$FilePath, [string]$KeyName, [string]$NewValue)
    $content = [IO.File]::ReadAllText($FilePath, [Text.Encoding]::UTF8)
    $pattern = '(?m)(^\s*' + [regex]::Escape($KeyName) + ':[0-9.]+\s*=\s*)"[^"]*"'
    $attrs = (Get-Item $FilePath).Attributes
    if ($attrs -band [IO.FileAttributes]::ReadOnly) {
        Set-ItemProperty $FilePath -Name Attributes -Value ($attrs -band (-bnot [IO.FileAttributes]::ReadOnly))
    }
    if ($content -match $pattern) {
        $newContent = [regex]::Replace($content, $pattern, '$1"' + $NewValue + '"')
    } else {
        $newContent = $content.TrimEnd() + "`r`n// fpstune-appended`r`n$KeyName`:0.0 = `"$NewValue`"`r`n"
    }
    [IO.File]::WriteAllText($FilePath, $newContent, [Text.Encoding]::UTF8)
    return $true
}

$script:nApplied = 0
$script:nSkipped = 0

function Apply-Setting {
    param([string]$KeyName, [string]$Value, [string]$Label)
    if (Set-CstKey -FilePath $optPath -KeyName $KeyName -NewValue $Value) {
        Write-OK "$Label  ->  $Value"
        $script:nApplied++
    } else {
        Write-Skip "$Label  (key absent, skipped)"
        $script:nSkipped++
    }
}

# ════════════════════════════════════════════════════════════════════════════
#  FPS OPTIMIZATION
# ════════════════════════════════════════════════════════════════════════════
if ($doFps) {

    # ── 1. gamerprofile: disable HTTP texture streaming ───────────────────────
    if ($gamerProfile) {
        Write-Header "Texture streaming (gamerprofile)..."

        $attrs = (Get-Item $gamerProfile.FullName).Attributes
        if ($attrs -band [IO.FileAttributes]::ReadOnly) {
            Set-ItemProperty $gamerProfile.FullName -Name IsReadOnly -Value $false
            Write-Skip "Removed prior read-only lock"
        }

        $gpContent = [IO.File]::ReadAllText($gamerProfile.FullName, [Text.Encoding]::UTF8)
        # MW3 writes gamerprofile as either `Key@0 = value` or `Key@ value`,
        # depending on the profile. The separator is captured and written back
        # unchanged so neither shape is assumed.
        $gpPattern = '(?m)(^[ \t]*HTTPStreamLimitMBytes@(?:\d*[ \t]*=[ \t]*|[ \t]+))(\d+)'

        if ($gpContent -match $gpPattern) {
            $current = $Matches[2]
            if ($current -eq "0") {
                Write-Skip "HTTPStreamLimitMBytes already 0"
            } else {
                $gpContent = [regex]::Replace($gpContent, $gpPattern, '${1}0')
                Write-OK "HTTPStreamLimitMBytes  $current -> 0  (HTTP texture streaming disabled)"
            }
            [IO.File]::WriteAllText($gamerProfile.FullName, $gpContent, [Text.Encoding]::UTF8)
            # Deliberately NOT locked read-only. Locking froze the whole profile:
            # MW3 could no longer save any setting stored in it, so every in-game
            # change reverted on the next launch.
        } else {
            Write-Skip "HTTPStreamLimitMBytes key not found in gamerprofile"
        }
    }

    # ── 2. options.4.cod23.cst ────────────────────────────────────────────────
    Write-Header "Graphics -- performance..."
    Apply-Setting "ShadowQuality"                 "Low"             "Shadow Quality"
    Apply-Setting "ScreenSpaceShadowQuality"      "High"            "Screen Space Shadows  (keep High: enemy silhouettes)"
    Apply-Setting "VolumetricQuality"             "QUALITY_LOW"     "Volumetric Quality"
    Apply-Setting "ParticleQuality"               "low"             "Particle Resolution"
    Apply-Setting "SSAOTechnique"                 "Off"             "Ambient Occlusion"
    Apply-Setting "SSRMode"                       "Off"             "Screen Space Reflections"
    Apply-Setting "ShaderQuality"                 "Low"             "Shader Quality"
    Apply-Setting "DxrMode"                       "Off"             "Ray Tracing  (OFF = +20-40% FPS)"
    Apply-Setting "PathTracing"                   "false"           "Path Tracing  (OFF = lower GPU heat in lobby/Gunsmith, no match impact)"
    Apply-Setting "WaterQuality"                  "Low"             "Water Quality"
    Apply-Setting "WaterCausticsMode"             "Off"             "Water Caustics  (OFF = free FPS, purely cosmetic)"
    Apply-Setting "ReflectionProbeHalfResolution" "true"            "Half-Res Reflection Probes  (saves VRAM, no visible difference)"
    Apply-Setting "SunShadowCascade"              "Low    (1 cascade)" "Sun Shadow Cascades  (Low = +5-8% FPS)"
    Apply-Setting "WaterWaveWetness"              "false"           "Water Wave Wetness  (OFF = marginal GPU saving)"
    Apply-Setting "ModelQuality"                  "Low Quality"     "Detail Quality Level"
    Apply-Setting "ReflectionProbeRelighting"     "1"               "Static Reflection Quality"
    Apply-Setting "DeferredPhysics"               "Low Quality"     "Deferred Physics"
    Apply-Setting "WeatherGridVolumesQuality"     "Off"             "Weather Grid Volumes"
    Apply-Setting "Tessellation"                  "0_Off"           "Tessellation"

    Write-Header "Texture streaming (options)..."
    Apply-Setting "WorldStreamingQuality"         "Low"             "On-Demand Texture Streaming"
    Apply-Setting "VirtualTexturingMemoryMode"    "Medium"          "Local Texture Cache"
    Apply-Setting "TextureResolution"             "Normal"          "Texture Resolution  (Normal = best VRAM balance for 8 GB)"

    Write-Header "Visibility..."
    Apply-Setting "DepthOfField"                  "false"           "Depth of Field  (OFF = sharper ADS)"
    Apply-Setting "PersistentDamageLayer"         "true"            "Persistent Effects  (ON = see enemy bullet trails)"
    Apply-Setting "BulletImpacts"                 "true"            "Bullet Impact Markers"
    Apply-Setting "WeaponMotionBlur"              "false"           "Weapon Motion Blur  (OFF = sharp sights while moving)"
    Apply-Setting "EnableVelocityBasedBlur"       "false"           "Velocity-Based Blur  (OFF = sharper enemy tracking)"

    Write-Header "Upscaler / AA..."
    Apply-Setting "FSRFrameInterpolation"         "false"           "FSR 3 Frame Interpolation  (OFF = no input latency penalty)"
    if ($isNvidia) {
        Apply-Setting "AATechniquePreferred"      "DLSS"            "Anti-Aliasing  (DLSS -- NVIDIA RTX)"
        Apply-Setting "DLSSMode"                  "DLSS"            "DLSS Upscaling Mode  (max FPS)"
        Apply-Setting "DLSSFrameGeneration"       "false"           "DLSS Frame Generation  (OFF for multiplayer)"
        Apply-Setting "DlssRR"                    "false"           "DLSS Ray Reconstruction  (OFF = no lobby GPU overhead)"
        Apply-Setting "DLSSRRPerfMode"            "Maximum Quality" "DLSS-RR Mode  (Maximum Quality = best denoising when RR active)"
        Apply-Setting "DLSSPerfMode"              "Maximum Quality" "DLSS Performance Mode"
        Apply-Setting "DLSSSharpness"             "0.250000"        "DLSS Sharpness  (0.25 = subtle, sharper distant targets)"
    } elseif ($isAMD) {
        Apply-Setting "AATechniquePreferred"      "FSR"             "Anti-Aliasing  (FSR -- AMD)"
    } else {
        Write-Skip "DLSS/FSR  (GPU vendor unknown -- upscaler settings skipped)"
    }
    Apply-Setting "TextureFilterAnisotropic"      "Normal"          "Anisotropic Filtering"

    Write-Header "Cloud sync (prevents settings reverting on restart)..."
    Apply-Setting "ConfigCloudSavegameEnabled"    "false"           "Cloud Config Savegame  (OFF = local settings not overwritten by cloud on launch)"
    Apply-Setting "ConfigCloudStorageEnabled"     "false"           "Cloud Config Storage   (OFF = disables cloud sync for settings)"

    Write-Header "Display & resolution..."
    Apply-Setting "ResolutionMultiplier"          "100"             "Render Resolution"
    Apply-Setting "VideoMemoryScale"              "0.850000"        "VRAM Scale Target  (85% headroom)"
    Apply-Setting "DisplayMode"                   "Fullscreen borderless window" "Display Mode  (borderless = instant alt-tab, flip-model costs no measurable latency on Win11)"
    Apply-Setting "PreferredDisplayMode"          "Fullscreen borderless window" "Preferred Display Mode  (must match Display Mode or the game drifts back)"
    :: Value is the amount of REDUCTION, not the resolution: off=Native (none),
    :: min=Optimal (slight), full=Maximal (most). "min" was the wrong end.
    Apply-Setting "SustainabilityMenuSceneResolution" "full"        "Menu Render Resolution  (Maximal reduction = least GPU in menus)"
    Apply-Setting "PauseRenderingEnabled"         "true"            "Pause Game Rendering  (ON = saves GPU when tabbed out)"
    Apply-Setting "VSync"                         "disabled"        "VSync In-Game  (OFF = no sync latency, use G-Sync/FreeSync instead)"
    Apply-Setting "VSyncInMenu"                   "100%"            "VSync In-Menu  (100% = caps menu FPS, less GPU heat in lobby)"

    Write-Header "Input latency..."
    if ($isNvidia) {
        Apply-Setting "NvidiaReflex"              "Enabled + boost" "NVIDIA Reflex  (RTX only)"
    } else {
        Write-Skip "NvidiaReflex  (NVIDIA RTX only -- skipped)"
    }

    Write-Header "Audio..."
    Apply-Setting "AudioMix"                      "5"               "Audio Mix  (5 = Treble Boost, clearer footsteps)"

    # ── 3. Firewall -- Open NAT ───────────────────────────────────────────────
    Write-Header "Firewall -- Open NAT..."

    $existingRule = Get-NetFirewallRule -DisplayName "fpstune-MW3-NAT-UDP-In" -ErrorAction SilentlyContinue
    if ($existingRule) {
        Write-Skip "Firewall rules already exist"
    } else {
        try {
            $udpPorts = @("3074","4380","27000-27036","28950")
            $tcpPorts = @("3074","3075","27015-27030","27036-27037")

            New-NetFirewallRule -DisplayName "fpstune-MW3-NAT-UDP-In"  -Direction Inbound  -Protocol UDP -LocalPort  $udpPorts -Action Allow -Profile Any | Out-Null
            New-NetFirewallRule -DisplayName "fpstune-MW3-NAT-UDP-Out" -Direction Outbound -Protocol UDP -RemotePort $udpPorts -Action Allow -Profile Any | Out-Null
            New-NetFirewallRule -DisplayName "fpstune-MW3-NAT-TCP-In"  -Direction Inbound  -Protocol TCP -LocalPort  $tcpPorts -Action Allow -Profile Any | Out-Null
            New-NetFirewallRule -DisplayName "fpstune-MW3-NAT-TCP-Out" -Direction Outbound -Protocol TCP -RemotePort $tcpPorts -Action Allow -Profile Any | Out-Null

            Write-OK "Rules created: UDP+TCP In+Out -- Open NAT enabled"
        } catch {
            Write-Err "Firewall rules failed: $_"
        }
    }

    # ── 4. GPU TDR Delay ──────────────────────────────────────────────────────
    Write-Header "GPU stability..."

    $tdrPath    = 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers'
    $currentTdr = (Get-ItemProperty $tdrPath -Name TdrDelay -ErrorAction SilentlyContinue).TdrDelay
    if ($currentTdr -ge 10) {
        Write-Skip "TdrDelay already >= 10 s ($currentTdr s)"
    } else {
        Set-ItemProperty $tdrPath -Name TdrDelay -Value 10 -Type DWord -Force
        Set-ItemProperty $tdrPath -Name TdrLevel -Value 3  -Type DWord -Force
        $was = if ($null -ne $currentTdr) { "$currentTdr s" } else { "not set (Windows default 2 s)" }
        Write-OK "TdrDelay = 10 s, TdrLevel = 3  (was: $was)  -> prevents Dev Error GPU crashes"
    }

} # end $doFps

# ════════════════════════════════════════════════════════════════════════════
#  CRASH FIX -- cache cleanup
# ════════════════════════════════════════════════════════════════════════════
if ($doCrash) {

    Write-Header "Cache cleanup..."

    $script:totalFreedMB = 0.0

    function Remove-CacheDir {
        param([string]$Label, [string]$Path)
        if (Test-Path $Path) {
            $sz = (Get-ChildItem $Path -Recurse -EA SilentlyContinue | Measure-Object -Property Length -Sum).Sum
            $mb = [math]::Round($sz / 1MB, 1)
            Remove-Item -Recurse -Force $Path -ErrorAction SilentlyContinue
            if ($mb -gt 0) {
                $script:totalFreedMB += $mb
                Write-OK "$Label  ($mb MB freed)`n        $Path"
            } else {
                Write-Skip "$Label  (0 MB, already empty)`n        $Path"
            }
        } else {
            Write-Skip "$Label  (already clean)`n        $Path"
        }
    }

    # Find COD install dir (_retail_) -- Battle.net product.db, then Steam library scan
    $codInstall = $null

    $agentDb = 'C:\ProgramData\Battle.net\Agent\product.db'
    if (Test-Path $agentDb) {
        try {
            $bytes = [IO.File]::ReadAllBytes($agentDb)
            $enc   = [System.Text.Encoding]::GetEncoding(1252)
            $text  = $enc.GetString($bytes)
            foreach ($m in [regex]::Matches($text, '[A-Za-z]:[/\\][A-Za-z0-9 ()_\\\\/-]{5,150}')) {
                $ip     = ($m.Value.TrimEnd() -replace '/', '\')
                $retail = Join-Path $ip '_retail_'
                if (Test-Path (Join-Path $retail 'cod23')) { $codInstall = $retail; break }
            }
        } catch { }
    }

    if (-not $codInstall) {
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) {
            $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        }
        if ($sp) {
            $libs = @($sp)
            $libVdf = Join-Path $sp 'steamapps\libraryfolders.vdf'
            if (Test-Path $libVdf) {
                [regex]::Matches([IO.File]::ReadAllText($libVdf), '"path"\s+"([^"]+)"') | ForEach-Object {
                    $libs += $_.Groups[1].Value -replace '\\\\', '\'
                }
            }
            foreach ($lib in $libs) {
                $c = Join-Path $lib 'steamapps\common\Call of Duty\_retail_'
                if (Test-Path $c) { $codInstall = $c; break }
            }
        }
    }

    # MW3 install-dir caches
    if ($codInstall) {
        Remove-CacheDir "MW3 PSO shader cache  (recompiles on next launch ~5-15 min)" (Join-Path $codInstall 'cod23\shadercache')
        Remove-CacheDir "MW3 telescope cache   (CDN content cache)"                   (Join-Path $codInstall 'telescopeCache')
        Remove-CacheDir "MW3 xpak cache        (content package cache)"               (Join-Path $codInstall 'xpak_cache')
    } else {
        Write-Skip "MW3 install dir not found -- shader/telescope/xpak caches skipped`n        (Battle.net product.db not found or game not installed via Battle.net/Steam)"
    }

    # Windows DX shader cache
    Remove-CacheDir "D3DSCache  (Windows DX shader cache, auto-rebuilt)" (Join-Path $env:LOCALAPPDATA 'D3DSCache')

    # MW3 config-folder caches
    Remove-CacheDir "MW3 texture streaming cache  (fixes pop-in)" (Join-Path $codPath 'cache')
    Remove-CacheDir "MW3 crash dumps" (Join-Path ([System.Environment]::GetFolderPath('MyDocuments')) 'Call of Duty MWIII\crashes')

    # NVIDIA shader caches (skipped silently if paths absent on non-NVIDIA systems)
    foreach ($base in @(
        (Join-Path $env:LOCALAPPDATA 'NVIDIA'),
        (Join-Path $env:USERPROFILE  'AppData\LocalLow\NVIDIA\PerDriverVersion')
    )) {
        foreach ($sub in @('DXCache', 'GLCache')) {
            Remove-CacheDir "NVIDIA $sub" (Join-Path $base $sub)
        }
    }

    # AMD shader caches (skipped silently if paths absent on non-AMD systems)
    foreach ($sub in @('DxCache', 'VkCache', 'GLCache')) {
        Remove-CacheDir "AMD $sub" (Join-Path $env:LOCALAPPDATA "AMD\$sub")
    }

    # Battle.net launcher cache
    Remove-CacheDir "Battle.net cache" (Join-Path $env:ProgramData 'Blizzard Entertainment\Battle.net\Cache')

} # end $doCrash

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  -------------------------------------------------------------"
if ($doFps) {
    Write-Host ("  Settings applied: {0}    Skipped: {1} (keys absent from file)" -f $script:nApplied, $script:nSkipped) -ForegroundColor Cyan
}
if ($doCrash) {
    $totalRounded = [math]::Round($script:totalFreedMB, 0)
    Write-Host ("  Cache cleanup complete.  Total freed: {0} MB" -f $totalRounded) -ForegroundColor Cyan
}
Write-Host ""
Write-Host "  Restart MW3 for all changes to take effect." -ForegroundColor Yellow
Write-Host ""
Read-Host "  Press Enter to exit"
