@echo off
:: No delayed expansion on purpose: it would eat a '!' out of this file's own
:: path when it is stored below.
setlocal

:: ──────────────────────────────────────────────────────────────────────────
:: MW3 Crash Recovery  —  double-click and run, no installs required
:: Cache/temp cleanup ONLY: clears every cache that can cause MW3 crashes,
:: shader-preload hangs or launch failures — game caches, GPU driver shader
:: caches, Battle.net and Steam launcher caches, and Windows temp files.
:: Scans first, lists every found location with its size, and deletes ONLY
:: after one explicit confirmation. Nothing is removed on 'N'.
:: Changes NO settings, NO registry, NO firewall — nothing to undo.
:: Runs WITHOUT administrator rights: every cache lives in a user-writable
:: folder (Battle.net/Steam keep their install dirs user-writable so their
:: unelevated clients can update). Anything undeletable is reported, never
:: silently skipped.
:: Requires Windows 10/11 + PowerShell 5.1 (built-in on all modern Windows)
:: ──────────────────────────────────────────────────────────────────────────

:: The script's own path travels in an environment variable, never spliced into
:: the PowerShell command line: a folder named with a quote, '&' or '%' would
:: otherwise turn this line into a different command.
set "FPSTUNE_BAT=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $f=$env:FPSTUNE_BAT; $c=[IO.File]::ReadAllText($f,[Text.Encoding]::UTF8); $m=[string]::Concat('__BEGIN','_PS__'); $i=$c.IndexOf($m); if($i -lt 0){ Write-Host '[ERROR] Marker not found.' -ForegroundColor Red; Read-Host 'Press Enter'; exit 1 }; $p=$c.Substring($i+$m.Length); $t=[IO.Path]::Combine([IO.Path]::GetTempPath(),[IO.Path]::GetRandomFileName()+'.ps1'); [IO.File]::WriteAllText($t,$p,[Text.Encoding]::UTF8); $env:FPSTUNE_SELF=$t; try{ & $t }finally{ Remove-Item -LiteralPath $t -EA SilentlyContinue } }"
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
Write-Host "  MW3 Crash Recovery" -ForegroundColor Cyan
Write-Host "  -------------------------------------------------------------"
Write-Host "  Clears the caches that can cause MW3 crashes, shader-preload"
Write-Host "  hangs and launch failures: game caches, GPU driver shader"
Write-Host "  caches, Battle.net / Steam launcher caches, Windows temp."
Write-Host "  Your settings, configs and keybinds are NOT touched."
Write-Host ""
Write-Host "  Nothing is deleted yet: the script first scans, shows you the"
Write-Host "  full list with sizes, and asks for one confirmation."
Write-Host ""

# ── Refuse to run while the game is open ─────────────────────────────────────
# MW3 holds its caches open and rewrites some on exit; deleting them under a
# running game leaves them half-rebuilt, which is the crash we are fixing.
$running = @(Get-Process -Name 'cod', 'ModernWarfareIII' -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    Write-Err "MW3 is running ($(($running | Select-Object -ExpandProperty ProcessName -Unique) -join ', '))."
    Write-Err "Close the game completely, then re-run this script."
    Write-Host ""
    Read-Host "  Press Enter to exit"
    exit 1
}

# Launchers lock their own caches while running. Not fatal -- locked files are
# reported at the end -- but a closed launcher gives a complete clean.
$launchers = @(Get-Process -Name 'Battle.net', 'Agent', 'steam' -ErrorAction SilentlyContinue)
if ($launchers.Count -gt 0) {
    Write-Host ("  Note: {0} is running -- launcher caches may be partially locked." -f (($launchers | Select-Object -ExpandProperty ProcessName -Unique) -join ', ')) -ForegroundColor Yellow
    Write-Host "  For a complete clean, close Battle.net / Steam first (optional)." -ForegroundColor Yellow
}

# ── Scan phase: collect targets, delete nothing ──────────────────────────────
$script:targets = @()
$script:absent  = @()
$script:refused = @()

# Folders that must never be handed to a recursive delete, resolved from the
# running system rather than spelled out. A discovery bug upstream (an empty
# registry value, a truncated path) must dead-end here instead of becoming a
# recursive delete of a profile or of Windows itself.
$script:protected = @(
    [Environment]::GetFolderPath('Windows')
    [Environment]::GetFolderPath('System')
    [Environment]::GetFolderPath('UserProfile')
    [Environment]::GetFolderPath('MyDocuments')
    [Environment]::GetFolderPath('LocalApplicationData')
    [Environment]::GetFolderPath('ApplicationData')
    [Environment]::GetFolderPath('CommonApplicationData')
    [Environment]::GetFolderPath('ProgramFiles')
    [Environment]::GetFolderPath('ProgramFilesX86')
) | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\').ToLowerInvariant() }

# The only folder names a whole-folder delete may ever land on. Discovery
# reads the registry, a Battle.net database and Steam manifests; if any of
# those ever hands over a wrong path, a wrong path whose own name is not a
# known cache is dropped instead of deleted. "Documents", "Saved Games",
# "screenshots" and every other real folder fail this by construction.
$script:cacheLeafNames = @(
    'shadercache', 'telescopecache', 'xpak_cache',   # the game's own caches
    'd3dscache',                                     # Windows DirectX
    'cache', 'browsercaches', 'gpucache',            # launcher caches
    'appcache', 'htmlcache',                         # Steam client
    'dxcache', 'glcache', 'vkcache', 'nv_cache'      # GPU driver caches
)

function Test-SafeTarget {
    param([string]$Path, [string]$Kind = 'dir')
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    # Must be fully qualified with something below its root. "D:" is not a
    # drive root to .NET -- it resolves to the current directory on D:, so a
    # truncated path would otherwise sail through as a deletable folder.
    if ($Path -notmatch '^([A-Za-z]:\\[^\\]|\\\\[^\\]+\\[^\\]+\\[^\\])') { return $false }
    $full = $null
    try { $full = [IO.Path]::GetFullPath($Path) } catch { return $false }
    $t = $full.TrimEnd('\')
    if ($t.Length -eq 0) { return $false }
    # A drive root ("D:", "D:\") is never a cache.
    if ($t -eq ([IO.Path]::GetPathRoot($full)).TrimEnd('\')) { return $false }
    $lower = $t.ToLowerInvariant()
    foreach ($p in $script:protected) {
        if ($lower -eq $p) { return $false }             # is a protected folder
        if ($p.StartsWith($lower + '\')) { return $false } # contains one
    }
    # Whole-folder deletes must additionally be named like a cache. Steam's
    # per-game shader cache is the one numeric name, and only directly under
    # a folder called shadercache.
    if ($Kind -eq 'dir') {
        $leaf   = [IO.Path]::GetFileName($t)
        $parent = [IO.Path]::GetFileName([IO.Path]::GetDirectoryName($t))
        $known  = $script:cacheLeafNames -contains $leaf.ToLowerInvariant()
        $appId  = ($leaf -match '^\d+$') -and ($parent -and $parent.ToLowerInvariant() -eq 'shadercache')
        if (-not ($known -or $appId)) { return $false }
    }
    return $true
}

# Kind 'dir'      -> the folder itself is deleted (auto-recreated by its owner)
# Kind 'contents' -> only the folder's contents are deleted, the folder stays
# -LiteralPath everywhere: a path holding '[' or ']' (a Steam library named
# "Games [SSD]") is a wildcard to -Path, which then matches nothing and
# silently cleans nothing -- or matches a different folder and deletes that.
function Get-SizeMB {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0.0 }
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return [math]::Round((Get-Item -LiteralPath $Path -Force).Length / 1MB, 1)
    }
    # Summed by hand rather than with Measure-Object, which has two failure
    # modes here that are both terminating under Set-StrictMode: a folder of
    # nothing but subfolders yields objects with no Length, and an empty
    # folder yields no result object at all to read .Sum from.
    $sum = [double]0
    Get-ChildItem -LiteralPath $Path -Recurse -Force -File -EA SilentlyContinue |
        ForEach-Object { $sum += $_.Length }
    return [math]::Round($sum / 1MB, 1)
}

# The single rule for what may be removed out of a contents-only folder, used
# by the scan and by the delete so the list you approve is exactly the list
# that goes. Three exclusions: this script's own running copy, junctions and
# symlinks (a recursive delete on PowerShell 5.1 can follow one into whatever
# it points at), and anything touched within the cutoff window -- a file
# somebody opened from a mail attachment or a zip today lives in temp and is
# not this script's business.
function Get-CleanableItems {
    param([string]$Path, [datetime]$Cutoff, [string]$Self)
    return @(Get-ChildItem -LiteralPath $Path -Force -EA SilentlyContinue | Where-Object {
        -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
        $_.FullName -ne $Self -and
        $_.LastWriteTime -lt $Cutoff
    })
}

function Add-Target {
    param([string]$Label, [string]$Path, [string]$Kind = 'dir', [int]$OlderThanDays = 0)
    if (-not (Test-SafeTarget $Path $Kind)) {
        $script:refused += "$Label  ->  $Path"
        return
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        $script:absent += $Label
        return
    }
    if ($Kind -eq 'contents') {
        $cutoff = (Get-Date).AddDays(-$OlderThanDays)
        $items  = Get-CleanableItems -Path $Path -Cutoff $cutoff -Self $env:FPSTUNE_SELF
        if ($items.Count -eq 0) {
            $script:absent += "$Label  (nothing older than $OlderThanDays days)"
            return
        }
        $mb = 0.0
        foreach ($it in $items) { $mb += Get-SizeMB $it.FullName }
        $script:targets += @{ Label = $Label; Path = $Path; MB = [math]::Round($mb, 1); Kind = $Kind; Days = $OlderThanDays; Count = $items.Count }
        return
    }
    $script:targets += @{ Label = $Label; Path = $Path; MB = (Get-SizeMB $Path); Kind = $Kind; Days = 0; Count = 0 }
}

Write-Header "Scanning (read-only, this can take a minute)..."

# Locate Steam and its libraries (used for install dir + launcher caches)
$steamPath = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -Name 'SteamPath' -EA SilentlyContinue).SteamPath
if ($steamPath) { $steamPath = $steamPath -replace '/', '\' }
if (-not $steamPath) {
    $steamPath = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
}
if (-not $steamPath) {
    $steamPath = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
}

$steamLibs = @()
if ($steamPath) {
    $steamLibs = @($steamPath)
    $libVdf = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $libVdf) {
        [regex]::Matches([IO.File]::ReadAllText($libVdf), '"path"\s+"([^"]+)"') | ForEach-Object {
            $steamLibs += $_.Groups[1].Value -replace '\\\\', '\'
        }
    }
}

# Steam copy of COD: read each library's appmanifest files instead of assuming
# a folder name or an app id -- the manifest names the install dir, its
# filename carries the app id, and _retail_\cod23 confirms it is the COD HQ
# client with MW3 content.
$steamCod = $null
foreach ($lib in $steamLibs) {
    $apps = Join-Path $lib 'steamapps'
    foreach ($mf in Get-ChildItem -LiteralPath $apps -Filter 'appmanifest_*.acf' -EA SilentlyContinue) {
        $txt = [IO.File]::ReadAllText($mf.FullName)
        if ($txt -match '"installdir"\s+"([^"]+)"') {
            $retail = Join-Path $apps (Join-Path 'common' (Join-Path $Matches[1] '_retail_'))
            if (Test-Path -LiteralPath (Join-Path $retail 'cod23')) {
                $appId = $null
                if ($mf.Name -match 'appmanifest_(\d+)\.acf') { $appId = $Matches[1] }
                $steamCod = @{ Lib = $lib; AppId = $appId; Retail = $retail }
                break
            }
        }
    }
    if ($steamCod) { break }
}

# Locate COD install dir: Battle.net product.db first, then Steam
$codInstall = $null

$agentDb = Join-Path $env:ProgramData 'Battle.net\Agent\product.db'
if (Test-Path -LiteralPath $agentDb) {
    try {
        $bytes = [IO.File]::ReadAllBytes($agentDb)
        $enc   = [System.Text.Encoding]::GetEncoding(1252)
        $text  = $enc.GetString($bytes)
        foreach ($m in [regex]::Matches($text, '[A-Za-z]:[/\\][A-Za-z0-9 ()_\\\\/-]{5,150}')) {
            $ip     = ($m.Value.TrimEnd() -replace '/', '\')
            $retail = Join-Path $ip '_retail_'
            if (Test-Path -LiteralPath (Join-Path $retail 'cod23')) { $codInstall = $retail; break }
        }
    } catch { }
}

if (-not $codInstall -and $steamCod) { $codInstall = $steamCod.Retail }

# Game caches
if ($codInstall) {
    Add-Target "MW3 PSO shader cache  (recompiles on next launch ~5-15 min)" (Join-Path $codInstall 'cod23\shadercache')
    Add-Target "MW3 telescope cache  (CDN content cache)"                    (Join-Path $codInstall 'telescopeCache')
    Add-Target "MW3 xpak cache  (content package cache)"                     (Join-Path $codInstall 'xpak_cache')
} else {
    $script:absent += "MW3 install dir (Battle.net product.db not found or game not installed via Battle.net/Steam)"
}

Add-Target "Windows DX shader cache D3DSCache  (auto-rebuilt)" (Join-Path $env:LOCALAPPDATA 'D3DSCache')

# MW3 config-folder texture streaming cache (the cache subfolder only --
# config files next to it are deliberately never touched)
$docPath = [System.Environment]::GetFolderPath('MyDocuments')
Add-Target "MW3 texture streaming cache  (fixes pop-in)" (Join-Path $docPath 'Call of Duty MWIII\players\cache')

# Crash dumps in Documents\Call of Duty MWIII\crashes are left in place on
# purpose: they never cause crashes, and they are the evidence support (or a
# helpful friend) needs to diagnose one.

# LocalLow has no environment variable; ask Windows where it is (User Shell
# Folders known-folder GUID) and only then fall back to deriving it from
# LOCALAPPDATA's parent -- never a hardcoded profile path.
$localLow = $null
try {
    $shellFolders = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' -EA Stop
    $raw = $shellFolders.'{A520A1A4-1780-4FF6-BD18-167343C5AF16}'
    if ($raw) { $localLow = [Environment]::ExpandEnvironmentVariables($raw) }
} catch { }
if (-not $localLow) { $localLow = Join-Path (Split-Path $env:LOCALAPPDATA -Parent) 'LocalLow' }

# NVIDIA shader caches (absent paths just land in the skipped list on AMD-only systems)
foreach ($base in @(
    @{ Tag = 'LocalAppData'; Path = (Join-Path $env:LOCALAPPDATA 'NVIDIA') },
    @{ Tag = 'LocalLow';     Path = (Join-Path $localLow 'NVIDIA\PerDriverVersion') }
)) {
    foreach ($sub in @('DXCache', 'GLCache')) {
        Add-Target "NVIDIA $sub ($($base.Tag))  (driver shader cache)" (Join-Path $base.Path $sub)
    }
}
Add-Target "NVIDIA NV_Cache  (driver shader cache)" (Join-Path $env:ProgramData 'NVIDIA Corporation\NV_Cache')

# AMD shader caches (absent paths just land in the skipped list on NVIDIA-only systems)
foreach ($sub in @('DxCache', 'VkCache', 'GLCache')) {
    Add-Target "AMD $sub  (driver shader cache)" (Join-Path $env:LOCALAPPDATA "AMD\$sub")
}

# Battle.net: cache folders only -- Battle.net.config and account data are
# never touched.
Add-Target "Battle.net cache (ProgramData)"  (Join-Path $env:ProgramData 'Blizzard Entertainment\Battle.net\Cache')
Add-Target "Battle.net cache (LocalAppData)" (Join-Path $env:LOCALAPPDATA 'Blizzard Entertainment\Battle.net\Cache')
foreach ($sub in @('BrowserCaches', 'Cache', 'GPUCache')) {
    Add-Target "Battle.net client $sub" (Join-Path $env:LOCALAPPDATA "Battle.net\$sub")
}

# Steam: appcache (app metadata, rebuilt on next Steam start -- the classic
# "COD HQ won't launch" fix), the client's web cache, and the per-game
# precompiled shader cache for the COD app id found in the manifest above.
if ($steamPath) {
    Add-Target "Steam appcache  (rebuilt on next Steam start)" (Join-Path $steamPath 'appcache')
    Add-Target "Steam web cache htmlcache" (Join-Path $env:LOCALAPPDATA 'Steam\htmlcache')
} else {
    $script:absent += "Steam (not installed)"
}
if ($steamCod -and $steamCod.AppId) {
    Add-Target "Steam per-game shader cache (COD, app $($steamCod.AppId))" (Join-Path $steamCod.Lib "steamapps\shadercache\$($steamCod.AppId)")
} elseif ($steamPath) {
    $script:absent += "Steam per-game shader cache (COD not installed via Steam)"
}

# Windows temp: contents only, and only entries untouched for a week --
# Windows' own Disk Cleanup uses the same 7-day rule, for the same reason.
# Anything from this week (a document opened straight out of a zip or a mail
# attachment, an installer mid-run) is left alone.
Add-Target "Windows temp files  (only items unused for 7+ days)" ([IO.Path]::GetTempPath()) 'contents' 7

# ── Review phase: list everything, then ask once ─────────────────────────────
if ($script:targets.Count -eq 0) {
    Write-Host ""
    Write-Skip "Nothing found to clean -- all known cache locations are absent."
    Read-Host "  Press Enter to exit"
    exit 0
}

Write-Header "Found -- will be deleted ONLY after your approval:"
$i = 0
$totalMB = 0.0
foreach ($t in $script:targets) {
    $i++
    $totalMB += $t.MB
    $suffix = if ($t.Kind -eq 'contents') { "  [$($t.Count) items, folder stays]" } else { '' }
    Write-Host ("  {0,2}. {1,9:N1} MB  {2}{3}" -f $i, $t.MB, $t.Label, $suffix) -ForegroundColor Green
    Write-Host ("        {0}" -f $t.Path) -ForegroundColor DarkGray
}

if ($script:absent.Count -gt 0) {
    Write-Header "Not present on this machine (nothing to do):"
    foreach ($a in $script:absent) { Write-Skip $a }
}

if ($script:refused.Count -gt 0) {
    Write-Header "Refused by the safety check (never deleted):"
    foreach ($r in $script:refused) { Write-Err $r }
    Write-Host "  A location resolved to a drive root or a protected system" -ForegroundColor Yellow
    Write-Host "  folder, so it was dropped instead of being cleaned." -ForegroundColor Yellow
}

Write-Host ""
Write-Host ("  Total: {0} locations, {1:N1} MB." -f $script:targets.Count, $totalMB) -ForegroundColor Cyan
Write-Host ""
Write-Host "  Only the paths printed above are touched. Nothing is searched" -ForegroundColor Cyan
Write-Host "  for, no other folder is visited, and a whole-folder delete only" -ForegroundColor Cyan
Write-Host "  ever lands on a folder named like a cache (shadercache, DXCache," -ForegroundColor Cyan
Write-Host "  appcache, ...). Documents, saves, screenshots, configs and" -ForegroundColor Cyan
Write-Host "  keybinds are outside that list and cannot be reached." -ForegroundColor Cyan
Write-Host ""
$answer = Read-Host "  Delete ALL items listed above? [Y/N]"
if ($answer -notmatch '^[yY]') {
    Write-Host ""
    Write-Skip "Cancelled -- nothing was deleted."
    Read-Host "  Press Enter to exit"
    exit 0
}

# ── Delete phase ─────────────────────────────────────────────────────────────
$script:totalFreedMB = 0.0
$script:nLocked      = 0

Write-Header "Deleting..."
$self = $env:FPSTUNE_SELF
foreach ($t in $script:targets) {
    if ($t.Kind -eq 'contents') {
        # Same rule as the scan, so nothing outside the approved list can be
        # caught by the delete.
        $cutoff = (Get-Date).AddDays(-$t.Days)
        foreach ($it in (Get-CleanableItems -Path $t.Path -Cutoff $cutoff -Self $self)) {
            Remove-Item -LiteralPath $it.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        # Re-measure under the same rule: whatever is left is either in use or
        # newer than the cutoff, and neither is a failure.
        $stillMB = 0.0
        foreach ($it in (Get-CleanableItems -Path $t.Path -Cutoff $cutoff -Self $self)) {
            $stillMB += Get-SizeMB $it.FullName
        }
        $freed = [math]::Round([math]::Max(0, $t.MB - $stillMB), 1)
        $script:totalFreedMB += $freed
        Write-OK "$($t.Label)  ($freed MB freed)"
        continue
    }

    Remove-Item -LiteralPath $t.Path -Recurse -Force -ErrorAction SilentlyContinue
    $leftFiles = 0
    $leftMB    = 0.0
    if (Test-Path -LiteralPath $t.Path) {
        $leftFiles = @(Get-ChildItem -LiteralPath $t.Path -Recurse -Force -File -EA SilentlyContinue).Count
        $leftMB    = Get-SizeMB $t.Path
    }
    if ($leftFiles -gt 0) {
        $script:nLocked++
        $script:totalFreedMB += [math]::Max(0, $t.MB - $leftMB)
        Write-Err "$($t.Label)  ($leftFiles files could not be deleted -- in use or access denied)`n        $($t.Path)"
    } elseif ($t.MB -gt 0) {
        $script:totalFreedMB += $t.MB
        Write-OK "$($t.Label)  ($($t.MB) MB freed)"
    } else {
        Write-Skip "$($t.Label)  (0 MB, already empty)"
    }
}

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  -------------------------------------------------------------"
$totalRounded = [math]::Round($script:totalFreedMB, 0)
Write-Host ("  Cache cleanup complete.  Total freed: {0} MB" -f $totalRounded) -ForegroundColor Cyan
if ($script:nLocked -gt 0) {
    Write-Host ""
    Write-Host ("  {0} location(s) had files that could not be deleted." -f $script:nLocked) -ForegroundColor Yellow
    Write-Host "  Close Battle.net / Steam / NVIDIA-AMD overlays and re-run;" -ForegroundColor Yellow
    Write-Host "  if it persists, run this script once as administrator." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  If crashes continue after cleanup, run the launcher's own repair:" -ForegroundColor Yellow
Write-Host "  Battle.net: gear icon > Scan and Repair | Steam: Properties >" -ForegroundColor Yellow
Write-Host "  Installed Files > Verify integrity of game files." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Start MW3 and let it sit through shader compilation before" -ForegroundColor Yellow
Write-Host "  joining a match (~5-15 min on first launch)." -ForegroundColor Yellow
Write-Host ""
Read-Host "  Press Enter to exit"
