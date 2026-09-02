"""PowerShell action-command payloads.

Extracted from settings/executors/powershell.py to keep the executor module
focused on detect/apply logic. Each value is a self-contained PowerShell
script that uses %placeholder% substitution at execution time.
"""

from __future__ import annotations

# Read and write a config file without changing its byte-level shape.
#
# `[System.IO.File]::WriteAllText($p, $t, [System.Text.Encoding]::UTF8)` writes a
# BOM, because .NET's `Encoding.UTF8` is constructed with
# `encoderShouldEmitUTF8Identifier: true`. Every writer here used that form, so
# every BOM-less file fpstune touched came back with three bytes prepended.
#
# Measured 2026-08-30: a `line1\nline2\n` file went through that exact call and
# came back `\xef\xbb\xbfLINE1\nline2\n`. The files this actually happens to are
# MW3's `options.4.cod23.cst` (no BOM, pure LF) and Steam's `.vdf` files (no
# BOM) — while HotS's `Variables.txt` and CS2's `autoexec.cfg` do carry one, so
# unconditionally dropping the BOM would break those instead. Neither constant
# is right; the file's own answer is.
#
# This is the same rule `mw4_config.py` already follows in Python — "the read
# strips it and the write puts back exactly what was there" — brought to the
# PowerShell writers that were left behind.
_CONFIG_IO_HELPERS = r"""
    function Read-ConfigText([string]$Path) {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        $script:ConfigHadBom = ($bytes.Length -ge 3) -and ($bytes[0] -eq 0xEF) -and
                               ($bytes[1] -eq 0xBB) -and ($bytes[2] -eq 0xBF)
        $offset = 0
        if ($script:ConfigHadBom) { $offset = 3 }
        return [System.Text.Encoding]::UTF8.GetString($bytes, $offset, $bytes.Length - $offset)
    }
    function Write-ConfigText([string]$Path, [string]$Text) {
        # $ConfigHadBom is set by the matching Read-ConfigText. Defaulting to
        # $false when it is unset keeps a writer that forgot to read from
        # inventing a BOM, which is the failure this whole helper exists for.
        $emitBom = [bool]$script:ConfigHadBom
        [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($emitBom)))
    }
    function Get-ConfigNewline([string]$Text) {
        # Appending CRLF to a pure-LF file leaves it with two conventions. MW3's
        # options file is pure LF and the append path used a literal "`r`n".
        if ($Text -match "`r`n") { return "`r`n" }
        return "`n"
    }
"""

# Shared docker reclaim script. Docker Desktop's WSL2 backend keeps its data in a
# sparse vhdx that does NOT auto-shrink: `docker system prune` frees space inside
# the VM, but the host file stays large. To return real disk space we snapshot the
# vhdx size, prune, shut WSL down to release the file, compact it (set-sparse +
# diskpart fallback — the proven wsl_compact sequence), snapshot again, and report
# the file-size delta. We measure the vhdx file, not whole-disk free, because
# concurrent I/O corrupts a whole-disk before/after reading.
# __PRUNE_ARGS__ is replaced at module load with "-f" or "-a -f".
_DOCKER_RECLAIM_TEMPLATE = r"""
    $exe = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $exe) { Write-Output 'Docker not installed - nothing to prune'; exit 0 }

    # Collect docker-desktop WSL2 disks: known fixed paths (newer docker_data.vhdx,
    # older ext4.vhdx) plus any docker-desktop* distro found in the Lxss registry.
    $disks = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new()
    $fixed = @(
        (Join-Path $env:LOCALAPPDATA 'Docker\wsl\disk\docker_data.vhdx'),
        (Join-Path $env:LOCALAPPDATA 'Docker\wsl\data\ext4.vhdx')
    )
    foreach ($p in $fixed) {
        if ((Test-Path $p) -and $seen.Add($p)) {
            $disks.Add([pscustomobject]@{ Name = $null; Vhd = $p })
        }
    }
    $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (Test-Path $lxss) {
        foreach ($key in Get-ChildItem $lxss -EA SilentlyContinue) {
            $props = Get-ItemProperty $key.PSPath -EA SilentlyContinue
            if (-not $props.DistributionName) { continue }
            if ($props.DistributionName -notlike 'docker-desktop*') { continue }
            $bp = $props.BasePath
            if (-not $bp) { continue }
            $bp = $bp -replace '^\\\\\?\\',''
            foreach ($v in Get-ChildItem -Path $bp -Filter *.vhdx -EA SilentlyContinue) {
                if ($seen.Add($v.FullName)) {
                    $disks.Add([pscustomobject]@{ Name = $props.DistributionName; Vhd = $v.FullName })
                }
            }
        }
    }

    $before = [double]0
    foreach ($d in $disks) { $before += (Get-Item $d.Vhd -EA SilentlyContinue).Length }

    # Free space inside the VM first. If the engine is down the prune is skipped,
    # but compacting the existing sparse vhdx can still reclaim previously-freed space.
    $out = & docker system prune __PRUNE_ARGS__ 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Output "Docker prune skipped (engine not running); compacting existing disks: $out"
    }

    if ($disks.Count -eq 0) { Write-Output 'No docker WSL2 virtual disks found'; exit 0 }

    # Release the vhdx files (closes all distros + Docker Desktop WSL backend).
    & wsl.exe --shutdown 2>&1 | Out-Null
    Start-Sleep -Seconds 3
    foreach ($d in $disks) {
        if ($d.Name) {
            try { & wsl.exe --manage $d.Name --set-sparse true 2>&1 | Out-Null } catch {}
        }
        $tmp = [System.IO.Path]::GetTempFileName()
        $lines = @("select vdisk file=`"$($d.Vhd)`"", 'attach vdisk readonly', 'compact vdisk', 'detach vdisk', 'exit')
        Set-Content -Path $tmp -Value $lines -Encoding ASCII
        & diskpart /s $tmp 2>&1 | Out-Null
        Remove-Item $tmp -Force -EA SilentlyContinue
    }
    Start-Sleep -Seconds 1

    $after = [double]0
    foreach ($d in $disks) { $after += (Get-Item $d.Vhd -EA SilentlyContinue).Length }
    $freed = [math]::Max(0, $before - $after)
    Write-Output "Total reclaimed space: $([math]::Round($freed/1MB, 0)) MB"
"""


def _cod_install_lookup(flavor: str) -> str:
    """PowerShell that leaves ``$install`` at the folder holding ``flavor``.

    Call of Duty titles keep their caches beside the game data rather than in a
    user directory, and the install path is the user's own — a library on any
    drive, under any name (C9). Battle.net's ``product.db`` is the machine's own
    record of where it put them, so the path is read out of it rather than
    guessed.

    The build folder is globbed rather than named. MW3 ships under ``_retail_``
    and the MW4 beta under ``_beta_``; a literal ``_retail_`` is a constant that
    goes stale the moment a title is in beta — measured here, where MW4's 2.3 GB
    of cache sat in a folder the MW3 lookup could not see. What is stable is the
    flavor directory (`cod23`, `cod26`) inside it.

    Args:
        flavor: The engine flavor directory, e.g. ``cod23`` or ``cod26``.

    Returns:
        A PowerShell fragment. ``$install`` is ``$null`` when nothing matched.
    """
    return rf"""
        $install = $null
        $agentDb = 'C:\ProgramData\Battle.net\Agent\product.db'
        if ([System.IO.File]::Exists($agentDb)) {{
            try {{
                $bytes = [IO.File]::ReadAllBytes($agentDb)
                $enc   = [System.Text.Encoding]::GetEncoding(1252)
                $text  = $enc.GetString($bytes)
                foreach ($m in [regex]::Matches($text, '[A-Za-z]:[/\\][A-Za-z0-9 ()_\\/-]{{5,150}}')) {{
                    $ip = ($m.Value.TrimEnd() -replace '/', '\')
                    if (-not [System.IO.Directory]::Exists($ip)) {{ continue }}
                    foreach ($build in [System.IO.Directory]::EnumerateDirectories($ip, '_*_')) {{
                        if ([System.IO.Directory]::Exists((Join-Path $build '{flavor}'))) {{
                            $install = $build
                            break
                        }}
                    }}
                    if ($null -ne $install) {{ break }}
                }}
            }} catch {{}}
        }}
    """


#: The caches a Call of Duty install rebuilds on its next launch. `shadercache`
#: is under the flavor directory; the other two sit beside it.
_COD_CACHE_SUBDIRS = ("{flavor}\\shadercache", "telescopeCache", "xpak_cache")


def _cod_cache_cleanup(flavor: str, label: str) -> str:
    """The apply half: delete this title's rebuildable caches, report the bytes."""
    subs = ", ".join(f"'{sub.format(flavor=flavor)}'" for sub in _COD_CACHE_SUBDIRS)
    return (
        _cod_install_lookup(flavor)
        + rf"""
        if ($null -eq $install) {{
            Write-Output "FPSTUNE_WARN: {label} install dir not found — shader cache skipped"
            exit 0
        }}
        $freed = [long]0
        foreach ($sub in @({subs})) {{
            $p = Join-Path $install $sub
            if ([System.IO.Directory]::Exists($p)) {{
                foreach ($f in [System.IO.Directory]::EnumerateFiles($p, '*', [System.IO.SearchOption]::AllDirectories)) {{
                    try {{ $freed += [System.IO.FileInfo]::new($f).Length }} catch {{}}
                }}
                Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue
            }}
        }}
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """
    )


def _cod_cache_size(flavor: str, label: str) -> str:
    """The detect half: how much those caches currently hold."""
    subs = ",\n                        ".join(
        f"(Join-Path $install '{sub.format(flavor=flavor)}')" for sub in _COD_CACHE_SUBDIRS
    )
    return (
        _cod_install_lookup(flavor)
        + rf"""
                if ($null -ne $install) {{
                    Emit-DirCleanup @(
                        {subs}
                    )
                }} else {{
                    Write-Output "FPSTUNE_WARN: {label} install dir not found via Battle.net product.db"
                    Write-Output "ready|not_installed"
                }}
    """
    )


# DISM answers in the system language, and the old parser looked for the English
# words 'Reclaimable|Reduction|Cleanup' on a line that also carried a size — a
# line AnalyzeComponentStore never prints, in any language — so the estimate was
# "0 MB" on every machine. /English is DISM's own documented global option for
# invariant output, and the estimate is DISM's own accounting of what
# StartComponentCleanup can free: superseded backups plus the cache. No such
# line, or a non-zero exit (740 when not elevated), is "unavailable" — never a
# number nobody measured (C11).
_DISM_RECLAIMABLE_FUNCTION = r"""
        function Get-DismReclaimableMB {
            $out = & dism.exe /Online /English /Cleanup-Image /AnalyzeComponentStore 2>&1
            if ($LASTEXITCODE -ne 0) { return $null }
            $total = 0.0
            $found = $false
            foreach ($line in $out) {
                if ("$line" -match '^\s*(Backups and Disabled Features|Cache and Temporary Data)\s*:\s*([\d.]+)\s*(bytes|KB|MB|GB|TB)\s*$') {
                    $found = $true
                    $n = [double]$Matches[2]
                    switch ($Matches[3]) {
                        'bytes' { $total += $n / 1MB }
                        'KB' { $total += $n / 1024 }
                        'MB' { $total += $n }
                        'GB' { $total += $n * 1024 }
                        'TB' { $total += $n * 1048576 }
                    }
                }
            }
            if (-not $found) { return $null }
            return [int][math]::Round($total)
        }
"""

_CLEANUP_STATUS = (
    r"""        function Get-DirSizeBytes([string]$dirPath) {
            $size = [long]0
            if (-not [System.IO.Directory]::Exists($dirPath)) { return $size }
            try {
                $di = [System.IO.DirectoryInfo]::new($dirPath)
                foreach ($fi in $di.EnumerateFiles('*', [System.IO.SearchOption]::AllDirectories)) {
                    $size += $fi.Length
                }
            } catch {
                # Inaccessible subtree aborted enumeration mid-walk — keep the partial sum.
            }
            $size
        }
        function Get-MultiDirSizeBytes([string[]]$paths) {
            $total = [long]0
            foreach ($p in $paths) { $total += Get-DirSizeBytes $p }
            $total
        }
        # Emit a cleanup size from a candidate path list. If NONE of the paths exist,
        # the target software/feature is not installed → emit "ready|not_installed" so
        # the setting becomes not-applicable (hidden + excluded from all totals).
        function Emit-DirCleanup([string[]]$paths) {
            $existing = @($paths | Where-Object { $_ -and [System.IO.Directory]::Exists($_) })
            if ($existing.Count -eq 0) { Write-Output 'ready|not_installed'; return }
            $bytes = [long]0
            foreach ($p in $existing) { $bytes += Get-DirSizeBytes $p }
            Write-Output "ready|$([math]::Round($bytes/1MB, 0)) MB"
        }
        # Per-type reclaimable bytes from 'docker system df' as a hashtable
        # (Images/Containers/Build Cache/Local Volumes). Starts Docker Desktop if the
        # engine is down. Returns $null when docker is unavailable.
        function Get-DockerReclaimBytes() {
            $exe = Get-Command docker -ErrorAction SilentlyContinue
            if (-not $exe) { return $null }
            $rows = & docker system df --format "{{.Type}}|{{.Reclaimable}}" 2>$null
            if ($LASTEXITCODE -ne 0) {
                $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
                if (Test-Path $desktop) {
                    if (-not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
                        Start-Process $desktop | Out-Null
                    }
                    for ($i = 0; $i -lt 35; $i++) {
                        Start-Sleep -Seconds 2
                        $rows = & docker system df --format "{{.Type}}|{{.Reclaimable}}" 2>$null
                        if ($LASTEXITCODE -eq 0) { break }
                    }
                }
            }
            if ($LASTEXITCODE -ne 0 -or -not $rows) { return $null }
            $h = @{}
            foreach ($row in $rows) {
                $parts = $row -split '\|'
                if ($parts.Count -lt 2) { continue }
                if ($parts[1].Trim() -match '([\d.]+)\s*([kmgtKMGT]?B)') {
                    $num = [double]$Matches[1]
                    $mult = 1
                    switch ($Matches[2].ToUpper()) {
                        'KB' { $mult = 1KB }
                        'MB' { $mult = 1MB }
                        'GB' { $mult = 1GB }
                        'TB' { $mult = 1TB }
                    }
                    $h[$parts[0].Trim()] = $num * $mult
                }
            }
            return $h
        }
"""
    + _DISM_RECLAIMABLE_FUNCTION
    + r"""        # The dispatch is a function so that the ~15 KB of helpers above can be
        # parsed once and then asked about every cleanup type in the same
        # session. Measured on the dev machine: a cold scan spawned 26
        # PowerShell processes here, one per cleanup setting, each re-parsing
        # this whole script to answer one question. See prefetch_cleanup_sizes.
        function Get-CleanupStatus([string]$type) {
        switch ($type) {
            'dism' {
                try {
                    $mb = Get-DismReclaimableMB
                    if ($null -ne $mb) { Write-Output "ready|$mb MB" } else { Write-Output 'ready|unavailable' }
                } catch {
                    Write-Output 'ready|unavailable'
                }
            }
            'temp' {
                $mb = [math]::Round((Get-MultiDirSizeBytes @($env:TEMP, "$env:LOCALAPPDATA\Temp", "$env:windir\Temp"))/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'nvidia_shader' {
                $cachePaths = [System.Collections.Generic.List[string]]::new()
                foreach ($sub in @('DXCache','GLCache')) {
                    $p = "$env:LOCALAPPDATA\NVIDIA\$sub"
                    if (Test-Path $p) { $cachePaths.Add($p) }
                }
                $npdBase = "$env:USERPROFILE\AppData\LocalLow\NVIDIA\PerDriverVersion"
                if (Test-Path $npdBase) {
                    foreach ($sub in @('DXCache','GLCache')) {
                        $p = Join-Path $npdBase $sub
                        if (Test-Path $p) { $cachePaths.Add($p) }
                    }
                    foreach ($verDir in Get-ChildItem $npdBase -Directory -EA SilentlyContinue) {
                        foreach ($sub in @('DXCache','GLCache')) {
                            $p = Join-Path $verDir.FullName $sub
                            if (Test-Path $p) { $cachePaths.Add($p) }
                        }
                    }
                }
                Emit-DirCleanup $cachePaths
            }
            'amd_shader' {
                $cachePaths = [System.Collections.Generic.List[string]]::new()
                $amdBase = "$env:LOCALAPPDATA\AMD"
                if (Test-Path $amdBase) {
                    foreach ($sub in @('DxCache','VkCache','GLCache','DXCache')) {
                        $p = Join-Path $amdBase $sub
                        if (Test-Path $p) { $cachePaths.Add($p) }
                    }
                    foreach ($dir in Get-ChildItem $amdBase -Directory -EA SilentlyContinue) {
                        foreach ($sub in @('DxCache','VkCache','GLCache','DXCache')) {
                            $p = Join-Path $dir.FullName $sub
                            if (Test-Path $p) { $cachePaths.Add($p) }
                        }
                    }
                }
                Emit-DirCleanup $cachePaths
            }
            'intel_shader' {
                $cachePaths = [System.Collections.Generic.List[string]]::new()
                $intelBase = "$env:LOCALAPPDATA\Intel"
                if (Test-Path $intelBase) {
                    $p = Join-Path $intelBase 'ShaderCache'
                    if (Test-Path $p) { $cachePaths.Add($p) }
                    foreach ($dir in Get-ChildItem $intelBase -Directory -EA SilentlyContinue) {
                        $p = Join-Path $dir.FullName 'ShaderCache'
                        if (Test-Path $p) { $cachePaths.Add($p) }
                    }
                }
                Emit-DirCleanup $cachePaths
            }
            'directx_shader' { Emit-DirCleanup @("$env:LOCALAPPDATA\D3DSCache") }
            'battlenet_cache' { Emit-DirCleanup @("$env:ProgramData\Blizzard Entertainment\Battle.net\Cache") }
            'event_logs' {
                $mb = [math]::Round((Get-DirSizeBytes "$env:windir\System32\winevt\Logs")/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'wer' {
                $mb = [math]::Round((Get-MultiDirSizeBytes @("$env:ALLUSERSPROFILE\Microsoft\Windows\WER\ReportArchive","$env:ALLUSERSPROFILE\Microsoft\Windows\WER\ReportQueue","$env:LOCALAPPDATA\Microsoft\Windows\WER\ReportArchive","$env:LOCALAPPDATA\Microsoft\Windows\WER\ReportQueue"))/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'defender' {
                $mb = [math]::Round((Get-MultiDirSizeBytes @("$env:ALLUSERSPROFILE\Microsoft\Windows Defender\Scans\History\Service","$env:ALLUSERSPROFILE\Microsoft\Windows Defender\Scans\History\Store","$env:ALLUSERSPROFILE\Microsoft\Windows Defender\Scans\MetaStore","$env:ALLUSERSPROFILE\Microsoft\Windows Defender\Scans\ScanResults"))/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'prefetch' {
                $mb = [math]::Round((Get-DirSizeBytes "$env:windir\Prefetch")/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'browser' {
                $total = Get-MultiDirSizeBytes @("$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache\Cache_Data","$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Code Cache","$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache\Cache_Data","$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Code Cache","$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data\Default\Cache\Cache_Data")
                $ffBase = "$env:APPDATA\Mozilla\Firefox\Profiles"
                if ([System.IO.Directory]::Exists($ffBase)) {
                    foreach ($prof in [System.IO.Directory]::GetDirectories($ffBase)) {
                        $total += Get-MultiDirSizeBytes @("$prof\cache2","$prof\startupCache","$prof\OfflineCache")
                    }
                }
                Write-Output "ready|$([math]::Round($total/1MB, 0)) MB"
            }
            'windows_update_cache' {
                $mb = [math]::Round((Get-DirSizeBytes "$env:windir\SoftwareDistribution\Download")/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'delivery_optimization' {
                $mb = [math]::Round((Get-DirSizeBytes "$env:windir\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache")/1MB, 0)
                Write-Output "ready|$mb MB"
            }
            'thumbnail_cache' {
                $total = [long]0
                $explorerDir = "$env:LOCALAPPDATA\Microsoft\Windows\Explorer"
                if ([System.IO.Directory]::Exists($explorerDir)) {
                    foreach ($f in [System.IO.Directory]::GetFiles($explorerDir, "thumbcache_*.db")) {
                        try { $total += [System.IO.FileInfo]::new($f).Length } catch {}
                    }
                    $icdb = "$explorerDir\IconCache.db"
                    if ([System.IO.File]::Exists($icdb)) { try { $total += [System.IO.FileInfo]::new($icdb).Length } catch {} }
                }
                Write-Output "ready|$([math]::Round($total/1MB, 0)) MB"
            }
            'memory_dumps' {
                $total = Get-MultiDirSizeBytes @("$env:windir\Minidump","$env:windir\LiveKernelReports","$env:LOCALAPPDATA\CrashDumps")
                $mdmp = "$env:windir\MEMORY.DMP"
                if ([System.IO.File]::Exists($mdmp)) { try { $total += [System.IO.FileInfo]::new($mdmp).Length } catch {} }
                Write-Output "ready|$([math]::Round($total/1MB, 0)) MB"
            }
            'discord_cache' { Emit-DirCleanup @("$env:APPDATA\discord\Cache\Cache_Data","$env:APPDATA\discord\Code Cache","$env:APPDATA\discord\GPUCache") }
            'epic_cache' { Emit-DirCleanup @("$env:LOCALAPPDATA\EpicGamesLauncher\Saved\webcache","$env:LOCALAPPDATA\EpicGamesLauncher\Saved\webcache_4147","$env:LOCALAPPDATA\EpicGamesLauncher\Saved\Logs") }
            'steam_webcache' { Emit-DirCleanup @("$env:LOCALAPPDATA\Steam\htmlcache\Cache\Cache_Data","$env:LOCALAPPDATA\Steam\htmlcache\Code Cache") }
            'pip_cache' { Emit-DirCleanup @("$env:LOCALAPPDATA\pip\Cache") }
            'npm_cache' { Emit-DirCleanup @("$env:APPDATA\npm-cache") }
            'yarn_cache' { Emit-DirCleanup @("$env:LOCALAPPDATA\Yarn\Cache") }
            'pnpm_cache' { Emit-DirCleanup @("$env:LOCALAPPDATA\pnpm\store") }
            'nuget_cache' { Emit-DirCleanup @("$env:USERPROFILE\.nuget\packages") }
            'maven_cache' { Emit-DirCleanup @("$env:USERPROFILE\.m2\repository") }
            'gradle_cache' { Emit-DirCleanup @("$env:USERPROFILE\.gradle\caches") }
            'cargo_cache' { Emit-DirCleanup @("$env:USERPROFILE\.cargo\registry\cache","$env:USERPROFILE\.cargo\registry\src") }
            'mw3_shader' {
__MW3_SHADER_SIZE__
            }
            'mw4_shader' {
__MW4_SHADER_SIZE__
            }
            'mw3_crash' {
                $p = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Call of Duty MWIII\crashes'
                Emit-DirCleanup @($p)
            }
            'cod_crash_reports' {
                Emit-DirCleanup @((Join-Path $env:LOCALAPPDATA 'Activision\Call of Duty\crash_reports'))
            }
            'docker_prune' {
                # `docker system prune -f` reclaims build cache + stopped containers +
                # dangling images only — NOT unused tagged images (needs -a) or volumes.
                # df's "Images Reclaimable" lumps in unused-tagged images, so the full
                # total overcounts ~2x (e.g. 19 GB shown vs ~8 GB actually freed).
                # Build Cache + Containers tracks the real -f freed space closely.
                try {
                    $h = Get-DockerReclaimBytes
                    if ($null -eq $h) { Write-Output "ready|unavailable"; break }
                    $b = [double]0
                    if ($h.ContainsKey('Build Cache')) { $b += $h['Build Cache'] }
                    if ($h.ContainsKey('Containers'))   { $b += $h['Containers'] }
                    Write-Output "ready|$([math]::Round($b/1MB, 0)) MB"
                } catch { Write-Output "ready|unavailable" }
            }
            'docker_prune_all' {
                # `-a` additionally removes ALL unused images. Sum every reclaimable
                # type except Local Volumes (prune never deletes named volumes).
                try {
                    $h = Get-DockerReclaimBytes
                    if ($null -eq $h) { Write-Output "ready|unavailable"; break }
                    $b = [double]0
                    foreach ($k in $h.Keys) { if ($k -ne 'Local Volumes') { $b += $h[$k] } }
                    Write-Output "ready|$([math]::Round($b/1MB, 0)) MB"
                } catch { Write-Output "ready|unavailable" }
            }
            'wsl_compact' {
                $totalBytes = [double]0
                $foundVhd = $false
                $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
                if (Test-Path $lxss) {
                    foreach ($key in Get-ChildItem $lxss -EA SilentlyContinue) {
                        $bp = (Get-ItemProperty $key.PSPath -Name BasePath -EA SilentlyContinue).BasePath
                        if ($bp) {
                            $bp = $bp -replace '^\\\\\?\\',''
                            foreach ($vhd in Get-ChildItem -Path $bp -Filter *.vhdx -EA SilentlyContinue) {
                                $totalBytes += $vhd.Length
                                $foundVhd = $true
                            }
                        }
                    }
                }
                # No WSL2 virtual disk → WSL not in use → not applicable (hidden).
                if (-not $foundVhd) { Write-Output "ready|not_installed" }
                else { Write-Output "ready|$([math]::Round($totalBytes/1MB, 0)) MB" }
            }
            'shadow_copy' {
                try {
                    $sysDrive = $env:SystemDrive
                    $stores = Get-CimInstance -ClassName Win32_ShadowStorage -ErrorAction Stop
                    $reclaimable = [long]0
                    $any = $false
                    foreach ($s in $stores) {
                        $driveLetter = $null
                        $capacity = $null
                        try {
                            $driveLetter = $s.Volume.DriveLetter
                            $capacity = $s.Volume.Capacity
                        } catch {}
                        if (-not $driveLetter) {
                            $devId = $s.Volume.DeviceID
                            if ($devId) {
                                $safeId = $devId -replace "'", "''"
                                $volObj = Get-CimInstance -ClassName Win32_Volume -Filter "DeviceID='$safeId'" -ErrorAction SilentlyContinue
                                if ($volObj) { $driveLetter = $volObj.DriveLetter; $capacity = $volObj.Capacity }
                            }
                        }
                        if (-not $driveLetter -or -not $capacity -or $capacity -le 0) { continue }
                        if ($driveLetter -eq $sysDrive) { continue }
                        $any = $true
                        $targetMax = [long]([math]::Floor([double]$capacity * 0.10))
                        $currentMax = [long]$s.MaxSpace
                        $used = [long]$s.UsedSpace
                        if ($currentMax -gt $targetMax) {
                            $reclaimable += [math]::Max(0, $used - $targetMax)
                        }
                    }
                    if (-not $any) { Write-Output 'ready|not_installed' }
                    else { Write-Output "ready|$([math]::Round($reclaimable/1MB, 0)) MB" }
                } catch {
                    Write-Output 'ready|not_installed'
                }
            }
            default { Write-Output 'ready|unavailable' }
        }
        }
        Get-CleanupStatus '%type%'
""".replace("__MW3_SHADER_SIZE__", _cod_cache_size("cod23", "MW3")).replace(
        "__MW4_SHADER_SIZE__", _cod_cache_size("cod26", "MW4")
    )
)


# Special action commands mapped to actual PowerShell scripts
# Uses %key% placeholder syntax to avoid conflicts with PowerShell {} braces
ACTION_COMMANDS: dict[str, str] = {
    # Memory: purge_standby is a Python action (executors/python_actions.py). It
    # needs ntdll, and reaching that from a script meant compiling a C# class with
    # Add-Type — the pattern Windows Defender flagged as trojan behaviour on
    # 2026-09-02. The script also passed the command value as the buffer pointer,
    # so it never purged anything and always printed success.
    # Service management - with existence check and graceful handling
    # Uses Manual StartType when enabling (most services are on-demand)
    # Verification checks StartType (2=Auto, 3=Manual, 4=Disabled)
    # Returns "NOT_FOUND" for non-existent services (handled by verification)
    "service_toggle": """
        $service = '%service%'
        $action = '%value%'
        if ($action -eq 'not_available') {
            Write-Output "SKIPPED:$service not_available"
            exit 0
        }
        $svc = Get-Service -Name $service -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Output "NOT_FOUND:$service"
            exit 0
        }
        try {
            if ($action -eq 'stop') {
                # Stop and disable
                if ($svc.Status -eq 'Running') {
                    Stop-Service -Name $service -Force -ErrorAction Stop
                }
                Set-Service -Name $service -StartupType Disabled -ErrorAction Stop
                Write-Output "OK:$service disabled"
            } else {
                # Enable (set to Manual for on-demand services)
                # Manual (3) allows the service to start when triggered
                Set-Service -Name $service -StartupType Manual -ErrorAction Stop
                # Try to start, but don't fail if it can't (dependencies, trigger-start, etc.)
                Start-Service -Name $service -ErrorAction SilentlyContinue
                Write-Output "OK:$service enabled"
            }
        } catch {
            Write-Output "ERROR:$service $action failed: $($_.Exception.Message)"
            exit 1
        }
    """,
    # Cleanup actions
    "dism_cleanup": _DISM_RECLAIMABLE_FUNCTION
    + r"""
        $before = Get-DismReclaimableMB
        Dism.exe /online /Cleanup-Image /StartComponentCleanup /ResetBase
        $after = Get-DismReclaimableMB
        if ($null -ne $before -and $null -ne $after) {
            $freed = $before - $after
            Write-Output "DISM cleanup freed: $freed MB (reboot may be required for full reclaim)"
        } else {
            Write-Output 'DISM cleanup completed (reboot may be required for full reclaim)'
        }
    """,
    # Two rules this script exists to keep, both learned from cleanup:prefetch
    # timing out on a real machine (2026-09-02):
    #
    # 1. One Remove-Item, not one per file. Enumerate the *top level* and let
    #    -Recurse take the subtrees: measured here, Temp held 12719 files under
    #    438 top-level entries, so the per-file loop paid a command dispatch
    #    thirty times over for nothing.
    # 2. Report what was freed, not what was found. Temp always holds files a
    #    running process has open, and those survive the delete — the old script
    #    counted them as freed anyway. Sizing before and after makes the number
    #    a measurement (C11). A process writing into Temp between the two passes
    #    can only make the figure conservative, never inflate it.
    "temp_cleanup": """
        # The user temp variable and the one under local app data name the
        # same folder on a stock profile, so without this the walk runs
        # twice for it. Percent-delimited spellings stay out of this comment:
        # that is fpstune's own placeholder syntax, and the renderer would
        # read one here as a placeholder nobody supplies.
        $paths = @($env:TEMP, "$env:LOCALAPPDATA\\Temp", "$env:windir\\Temp") |
            Where-Object { $_ } |
            ForEach-Object { [System.IO.Path]::GetFullPath($_).TrimEnd('\\') } |
            Select-Object -Unique
        function Get-SizeBytes([string]$dir) {
            if (-not (Test-Path -LiteralPath $dir)) { return [int64]0 }
            return [int64](Get-ChildItem -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
        }
        $freed = [int64]0
        foreach ($path in $paths) {
            if (-not (Test-Path -LiteralPath $path)) { continue }
            $before = Get-SizeBytes $path
            Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            $freed += $before - (Get-SizeBytes $path)
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "nvidia_shader_cleanup": """
        $cachePaths = [System.Collections.Generic.List[string]]::new()
        # NVIDIA: LocalAppData root caches
        foreach ($sub in @('DXCache','GLCache')) {
            $p = "$env:LOCALAPPDATA\\NVIDIA\\$sub"
            if (Test-Path $p) { $cachePaths.Add($p) }
        }
        # NVIDIA: PerDriverVersion — root + all per-driver-version subdirs
        $npdBase = "$env:USERPROFILE\\AppData\\LocalLow\\NVIDIA\\PerDriverVersion"
        if (Test-Path $npdBase) {
            foreach ($sub in @('DXCache','GLCache')) {
                $p = Join-Path $npdBase $sub
                if (Test-Path $p) { $cachePaths.Add($p) }
            }
            foreach ($verDir in Get-ChildItem $npdBase -Directory -EA SilentlyContinue) {
                foreach ($sub in @('DXCache','GLCache')) {
                    $p = Join-Path $verDir.FullName $sub
                    if (Test-Path $p) { $cachePaths.Add($p) }
                }
            }
        }
        foreach ($path in $cachePaths) {
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output 'NVIDIA shader caches cleared'
    """,
    "amd_shader_cleanup": """
        $cachePaths = [System.Collections.Generic.List[string]]::new()
        # AMD: root caches + one level deep (AMD organises by feature/driver subdirs)
        $amdBase = "$env:LOCALAPPDATA\\AMD"
        if (Test-Path $amdBase) {
            foreach ($sub in @('DxCache','VkCache','GLCache','DXCache')) {
                $p = Join-Path $amdBase $sub
                if (Test-Path $p) { $cachePaths.Add($p) }
            }
            foreach ($dir in Get-ChildItem $amdBase -Directory -EA SilentlyContinue) {
                foreach ($sub in @('DxCache','VkCache','GLCache','DXCache')) {
                    $p = Join-Path $dir.FullName $sub
                    if (Test-Path $p) { $cachePaths.Add($p) }
                }
            }
        }
        foreach ($path in $cachePaths) {
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output 'AMD shader caches cleared'
    """,
    "intel_shader_cleanup": """
        $cachePaths = [System.Collections.Generic.List[string]]::new()
        # Intel: root + one level deep
        $intelBase = "$env:LOCALAPPDATA\\Intel"
        if (Test-Path $intelBase) {
            $p = Join-Path $intelBase 'ShaderCache'
            if (Test-Path $p) { $cachePaths.Add($p) }
            foreach ($dir in Get-ChildItem $intelBase -Directory -EA SilentlyContinue) {
                $p = Join-Path $dir.FullName 'ShaderCache'
                if (Test-Path $p) { $cachePaths.Add($p) }
            }
        }
        foreach ($path in $cachePaths) {
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output 'Intel shader caches cleared'
    """,
    "directx_shader_cleanup": """
        # Windows D3D shader cache (fixed OS path)
        $d3ds = "$env:LOCALAPPDATA\\D3DSCache"
        if (Test-Path $d3ds) {
            Remove-Item -Path "$d3ds\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output 'DirectX shader cache cleared'
    """,
    # -f only: dangling images, stopped containers, unused networks, build cache.
    # Followed by a vhdx compact so the host actually gets the space back.
    "docker_prune": _DOCKER_RECLAIM_TEMPLATE.replace("__PRUNE_ARGS__", "-f"),
    # -a -f: also removes ALL unused images (not just dangling). No --volumes, so
    # named volumes (persistent data) are preserved. Compacts the vhdx afterwards.
    "docker_prune_all": _DOCKER_RECLAIM_TEMPLATE.replace("__PRUNE_ARGS__", "-a -f"),
    "wsl_compact": r"""
        $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
        if (-not $wsl) { Write-Output 'WSL not installed - nothing to compact'; exit 0 }
        # Collect each WSL2 distro (name + its vhdx files) from the registry. This
        # covers Docker Desktop distros (docker-desktop, docker-desktop-data) too.
        $distros = [System.Collections.Generic.List[object]]::new()
        $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
        if (Test-Path $lxss) {
            foreach ($key in Get-ChildItem $lxss -EA SilentlyContinue) {
                $props = Get-ItemProperty $key.PSPath -EA SilentlyContinue
                $bp = $props.BasePath
                if (-not $bp) { continue }
                $bp = $bp -replace '^\\\\\?\\',''
                $vhdList = @(Get-ChildItem -Path $bp -Filter *.vhdx -EA SilentlyContinue | ForEach-Object { $_.FullName })
                if ($vhdList.Count -gt 0) {
                    $distros.Add([pscustomobject]@{ Name = $props.DistributionName; Vhds = $vhdList })
                }
            }
        }
        if ($distros.Count -eq 0) { Write-Output 'No WSL2 virtual disks found'; exit 0 }
        # Release the vhdx files (closes all distros + Docker Desktop WSL backend).
        & wsl.exe --shutdown 2>&1 | Out-Null
        Start-Sleep -Seconds 3
        $freedTotal = [double]0
        foreach ($d in $distros) {
            $before = [double]0
            foreach ($v in $d.Vhds) { $before += (Get-Item $v -EA SilentlyContinue).Length }
            # Modern, reliable reclaim: mark the disk sparse so Windows shrinks it
            # (auto-shrink going forward + immediate effect on recent WSL builds).
            if ($d.Name) {
                try { & wsl.exe --manage $d.Name --set-sparse true 2>&1 | Out-Null } catch {}
            }
            # Fallback for older WSL builds: explicit diskpart compact.
            foreach ($v in $d.Vhds) {
                $tmp = [System.IO.Path]::GetTempFileName()
                $lines = @("select vdisk file=`"$v`"", 'attach vdisk readonly', 'compact vdisk', 'detach vdisk', 'exit')
                Set-Content -Path $tmp -Value $lines -Encoding ASCII
                & diskpart /s $tmp 2>&1 | Out-Null
                Remove-Item $tmp -Force -EA SilentlyContinue
            }
            Start-Sleep -Seconds 1
            $after = [double]0
            foreach ($v in $d.Vhds) { $after += (Get-Item $v -EA SilentlyContinue).Length }
            if ($before -gt $after) { $freedTotal += ($before - $after) }
        }
        Write-Output "WSL2 disks compacted - reclaimed $([math]::Round($freedTotal/1MB, 0)) MB"
    """,
    "shadow_copy_cleanup": r"""
        $sysDrive = $env:SystemDrive
        $freedTotal = [long]0
        try {
            $stores = Get-CimInstance -ClassName Win32_ShadowStorage -ErrorAction Stop
        } catch {
            Write-Output 'Cleaned 0 MB'
            exit 0
        }
        foreach ($s in $stores) {
            $driveLetter = $null
            $capacity = $null
            try {
                $driveLetter = $s.Volume.DriveLetter
                $capacity = $s.Volume.Capacity
            } catch {}
            if (-not $driveLetter) {
                $devId = $s.Volume.DeviceID
                if ($devId) {
                    $safeId = $devId -replace "'", "''"
                    $volObj = Get-CimInstance -ClassName Win32_Volume -Filter "DeviceID='$safeId'" -ErrorAction SilentlyContinue
                    if ($volObj) { $driveLetter = $volObj.DriveLetter; $capacity = $volObj.Capacity }
                }
            }
            if (-not $driveLetter -or -not $capacity -or $capacity -le 0) { continue }
            if ($driveLetter -eq $sysDrive) { continue }
            $targetMax = [long]([math]::Floor([double]$capacity * 0.10))
            $currentMax = [long]$s.MaxSpace
            $used = [long]$s.UsedSpace
            if ($currentMax -le $targetMax) { continue }
            $letter = $driveLetter.TrimEnd(':')
            & vssadmin.exe resize shadowstorage "/for=${letter}:" "/on=${letter}:" "/maxsize=10%" 2>&1 | Out-Null
            $freedTotal += [math]::Max(0, $used - $targetMax)
        }
        Write-Output "Cleaned $([math]::Round($freedTotal/1MB, 2)) MB"
    """,
    "battlenet_cache_cleanup": """
        $bnetPaths = @(
            "$env:ProgramData\\Blizzard Entertainment\\Battle.net\\Cache",
            "$env:APPDATA\\Battle.net\\Cache"
        )
        $freed = [long]0
        foreach ($path in $bnetPaths) {
            if ([System.IO.Directory]::Exists($path)) {
                foreach ($f in [System.IO.Directory]::EnumerateFiles($path, '*', [System.IO.SearchOption]::AllDirectories)) {
                    try { $freed += [System.IO.FileInfo]::new($f).Length } catch {}
                }
                Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "event_logs_cleanup": """
        $cleared = 0
        Get-WinEvent -ListLog * -ErrorAction SilentlyContinue | Where-Object { $_.RecordCount -gt 0 } | ForEach-Object {
            try {
                [System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.ClearLog($_.LogName)
                $cleared++
            } catch { }
        }
        Write-Output "Cleared $cleared event logs"
    """,
    "wer_cleanup": """
        $paths = @(
            "$env:ALLUSERSPROFILE\\Microsoft\\Windows\\WER\\ReportArchive",
            "$env:ALLUSERSPROFILE\\Microsoft\\Windows\\WER\\ReportQueue",
            "$env:LOCALAPPDATA\\Microsoft\\Windows\\WER\\ReportArchive",
            "$env:LOCALAPPDATA\\Microsoft\\Windows\\WER\\ReportQueue"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "defender_cache_cleanup": """
        $paths = @(
            "$env:ALLUSERSPROFILE\\Microsoft\\Windows Defender\\Scans\\History\\Service",
            "$env:ALLUSERSPROFILE\\Microsoft\\Windows Defender\\Scans\\History\\Store",
            "$env:ALLUSERSPROFILE\\Microsoft\\Windows Defender\\Scans\\MetaStore",
            "$env:ALLUSERSPROFILE\\Microsoft\\Windows Defender\\Scans\\ScanResults"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    # The report that started all of this: this script called Remove-Item once
    # per file, and on a machine with a few thousand .pf entries it ran past the
    # 30 s apply timeout, so the user saw a timeout rather than a refusal and
    # nothing was cleaned. Same two rules as temp_cleanup above — one piped
    # Remove-Item, and a freed figure measured before against after, since
    # Windows keeps some .pf files open and those survive the delete.
    "prefetch_cleanup": """
        $path = "$env:windir\\Prefetch"
        function Get-SizeBytes([string]$dir) {
            if (-not (Test-Path -LiteralPath $dir)) { return [int64]0 }
            return [int64](Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
        }
        $freed = [int64]0
        if (Test-Path -LiteralPath $path) {
            $before = Get-SizeBytes $path
            Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
            $freed = $before - (Get-SizeBytes $path)
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "browser_cache_cleanup": """
        $paths = @(
            "$env:LOCALAPPDATA\\Microsoft\\Edge\\User Data\\Default\\Cache\\Cache_Data",
            "$env:LOCALAPPDATA\\Microsoft\\Edge\\User Data\\Default\\Code Cache",
            "$env:LOCALAPPDATA\\Google\\Chrome\\User Data\\Default\\Cache\\Cache_Data",
            "$env:LOCALAPPDATA\\Google\\Chrome\\User Data\\Default\\Code Cache",
            "$env:LOCALAPPDATA\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Cache\\Cache_Data"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        $ffBase = "$env:APPDATA\\Mozilla\\Firefox\\Profiles"
        if (Test-Path $ffBase) {
            Get-ChildItem -Path $ffBase -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $profile = $_
                @("cache2","startupCache","OfflineCache") | ForEach-Object {
                    $cp = Join-Path $profile.FullName $_
                    if (Test-Path $cp) {
                        $size = (Get-ChildItem -Path $cp -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                        $freed += [int64]$size
                        Remove-Item -Path "$cp\\*" -Recurse -Force -ErrorAction SilentlyContinue
                    }
                }
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "windows_update_cache_cleanup": """
        Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
        $path = "$env:windir\\SoftwareDistribution\\Download"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Start-Service -Name wuauserv -ErrorAction SilentlyContinue
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "delivery_optimization_cleanup": """
        Stop-Service -Name dosvc -Force -ErrorAction SilentlyContinue
        $paths = @(
            "$env:windir\\ServiceProfiles\\NetworkService\\AppData\\Local\\Microsoft\\Windows\\DeliveryOptimization\\Cache",
            "$env:windir\\ServiceProfiles\\NetworkService\\AppData\\Local\\Microsoft\\Windows\\DeliveryOptimization\\Logs"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Service -Name dosvc -ErrorAction SilentlyContinue
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    # Only the cache databases, never the folder: Explorer keeps its own state
    # here. The measured-freed rule matters most on this one — Explorer usually
    # holds these files open, so the old script reported the full cache size as
    # freed on runs that deleted nothing at all.
    "thumbnail_cache_cleanup": """
        $path = "$env:LOCALAPPDATA\\Microsoft\\Windows\\Explorer"
        # -Filter, not a Where-Object name test: the filesystem provider does the
        # matching, so this never becomes text matching on output that could be
        # localized, and the two lists still reach one Remove-Item together.
        function Get-CacheItems([string]$dir) {
            if (-not (Test-Path -LiteralPath $dir)) { return @() }
            return @(Get-ChildItem -LiteralPath $dir -Filter 'thumbcache_*.db' -Force -ErrorAction SilentlyContinue) +
                @(Get-ChildItem -LiteralPath $dir -Filter 'IconCache.db' -Force -ErrorAction SilentlyContinue)
        }
        function Get-CacheBytes([string]$dir) {
            return [int64](Get-CacheItems $dir | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
        }
        $freed = [int64]0
        if (Test-Path -LiteralPath $path) {
            $before = Get-CacheBytes $path
            Get-CacheItems $path | Remove-Item -Force -ErrorAction SilentlyContinue
            $freed = $before - (Get-CacheBytes $path)
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "memory_dumps_cleanup": """
        $freed = 0
        foreach ($dir in @("$env:windir\\Minidump", "$env:windir\\LiveKernelReports", "$env:LOCALAPPDATA\\CrashDumps")) {
            if (Test-Path $dir) {
                $freed += [int64](Get-ChildItem -Path $dir -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                Remove-Item -Path "$dir\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        if (Test-Path "$env:windir\\MEMORY.DMP") {
            try { $freed += [int64](Get-Item "$env:windir\\MEMORY.DMP" -Force).Length; Remove-Item "$env:windir\\MEMORY.DMP" -Force -ErrorAction SilentlyContinue } catch { }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "discord_cache_cleanup": """
        $paths = @(
            "$env:APPDATA\\discord\\Cache\\Cache_Data",
            "$env:APPDATA\\discord\\Code Cache",
            "$env:APPDATA\\discord\\GPUCache"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "epic_cache_cleanup": """
        $paths = @(
            "$env:LOCALAPPDATA\\EpicGamesLauncher\\Saved\\webcache",
            "$env:LOCALAPPDATA\\EpicGamesLauncher\\Saved\\webcache_4147",
            "$env:LOCALAPPDATA\\EpicGamesLauncher\\Saved\\Logs"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "steam_webcache_cleanup": """
        $paths = @(
            "$env:LOCALAPPDATA\\Steam\\htmlcache\\Cache\\Cache_Data",
            "$env:LOCALAPPDATA\\Steam\\htmlcache\\Code Cache"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "pip_cache_cleanup": """
        $path = "$env:LOCALAPPDATA\\pip\\Cache"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "npm_cache_cleanup": """
        $path = "$env:APPDATA\\npm-cache"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "yarn_cache_cleanup": """
        $path = "$env:LOCALAPPDATA\\Yarn\\Cache"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "pnpm_cache_cleanup": """
        $path = "$env:LOCALAPPDATA\\pnpm\\store"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "nuget_cache_cleanup": """
        $path = "$env:USERPROFILE\\.nuget\\packages"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "maven_cache_cleanup": """
        $path = "$env:USERPROFILE\\.m2\\repository"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "gradle_cache_cleanup": """
        $path = "$env:USERPROFILE\\.gradle\\caches"
        $freed = 0
        if (Test-Path $path) {
            $freed = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    "cargo_cache_cleanup": """
        $paths = @(
            "$env:USERPROFILE\\.cargo\\registry\\cache",
            "$env:USERPROFILE\\.cargo\\registry\\src"
        )
        $freed = 0
        foreach ($path in $paths) {
            if (Test-Path $path) {
                $size = (Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                $freed += [int64]$size
                Remove-Item -Path "$path\\*" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    # Maintenance actions
    "sfc_scan": "sfc /scannow",
    "dism_health": "Dism.exe /online /Cleanup-Image /RestoreHealth",
    # Telemetry scheduled tasks toggle
    "telemetry_tasks_toggle": """
        $tasks = @(
            '\\Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator',
            '\\Microsoft\\Windows\\Customer Experience Improvement Program\\KernelCeipTask',
            '\\Microsoft\\Windows\\Customer Experience Improvement Program\\UsbCeip',
            '\\Microsoft\\Windows\\Application Experience\\ProgramDataUpdater',
            '\\Microsoft\\Windows\\Application Experience\\StartupAppTask',
            '\\Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser',
            '\\Microsoft\\Windows\\Autochk\\Proxy',
            '\\Microsoft\\Windows\\DiskDiagnostic\\Microsoft-Windows-DiskDiagnosticDataCollector',
            '\\Microsoft\\Windows\\Device Information\\Device'
        )
        $action = '%value%'
        foreach ($task in $tasks) {
            try {
                if ($action -eq 'disable') {
                    Disable-ScheduledTask -TaskPath ($task -replace '\\\\[^\\\\]*$','') -TaskName ($task -split '\\\\')[-1] -ErrorAction SilentlyContinue | Out-Null
                } else {
                    Enable-ScheduledTask -TaskPath ($task -replace '\\\\[^\\\\]*$','') -TaskName ($task -split '\\\\')[-1] -ErrorAction SilentlyContinue | Out-Null
                }
            } catch { }
        }
        # Also set registry for tailored experiences
        if ($action -eq 'disable') {
            Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Privacy' -Name 'TailoredExperiencesWithDiagnosticDataEnabled' -Value 0 -Type DWord -Force
        } else {
            Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Privacy' -Name 'TailoredExperiencesWithDiagnosticDataEnabled' -Value 1 -Type DWord -Force
        }
        Write-Output "Telemetry tasks $action completed"
    """,
    # Windows Ads & Suggestions toggle (ContentDeliveryManager bundle)
    "windows_ads_toggle": """
        $cdmPath = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager'
        $explorerPath = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced'
        $profilePath = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\UserProfileEngagement'
        $action = '%value%'
        if ($action -eq 'disable') {
            # ContentDeliveryManager settings
            Set-ItemProperty -Path $cdmPath -Name 'SilentInstalledAppsEnabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SoftLandingEnabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338387Enabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338388Enabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338389Enabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338393Enabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-353694Enabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-353696Enabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'RotatingLockScreenEnabled' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'RotatingLockScreenOverlayEnabled' -Value 0 -Type DWord -Force
            # Explorer settings
            Set-ItemProperty -Path $explorerPath -Name 'ShowSyncProviderNotifications' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $explorerPath -Name 'Start_IrisRecommendations' -Value 0 -Type DWord -Force
            # Profile engagement (finish setup nags)
            if (-not (Test-Path $profilePath)) { New-Item -Path $profilePath -Force | Out-Null }
            Set-ItemProperty -Path $profilePath -Name 'ScoobeSystemSettingEnabled' -Value 0 -Type DWord -Force
        } else {
            Set-ItemProperty -Path $cdmPath -Name 'SilentInstalledAppsEnabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SoftLandingEnabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338387Enabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338388Enabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338389Enabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-338393Enabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-353694Enabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'SubscribedContent-353696Enabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'RotatingLockScreenEnabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $cdmPath -Name 'RotatingLockScreenOverlayEnabled' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $explorerPath -Name 'ShowSyncProviderNotifications' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $explorerPath -Name 'Start_IrisRecommendations' -Value 1 -Type DWord -Force
            if (Test-Path $profilePath) { Set-ItemProperty -Path $profilePath -Name 'ScoobeSystemSettingEnabled' -Value 1 -Type DWord -Force }
        }
        Write-Output "Windows ads $action completed"
    """,
    # Accessibility popups disable (Sticky/Filter/Toggle Keys)
    "accessibility_popups_toggle": """
        $stickyPath = 'HKCU:\\Control Panel\\Accessibility\\StickyKeys'
        $filterPath = 'HKCU:\\Control Panel\\Accessibility\\Keyboard Response'
        $togglePath = 'HKCU:\\Control Panel\\Accessibility\\ToggleKeys'
        $action = '%value%'
        if ($action -eq 'disable') {
            Set-ItemProperty -Path $stickyPath -Name 'Flags' -Value '506' -Type String -Force
            Set-ItemProperty -Path $filterPath -Name 'Flags' -Value '122' -Type String -Force
            Set-ItemProperty -Path $togglePath -Name 'Flags' -Value '58' -Type String -Force
        } else {
            Set-ItemProperty -Path $stickyPath -Name 'Flags' -Value '510' -Type String -Force
            Set-ItemProperty -Path $filterPath -Name 'Flags' -Value '126' -Type String -Force
            Set-ItemProperty -Path $togglePath -Name 'Flags' -Value '62' -Type String -Force
        }
        Write-Output "Accessibility popups $action completed"
    """,
    # Mouse acceleration toggle
    "mouse_acceleration_toggle": """
        $mousePath = 'HKCU:\\Control Panel\\Mouse'
        $action = '%value%'
        if ($action -eq 'disable') {
            Set-ItemProperty -Path $mousePath -Name 'MouseSpeed' -Value '0' -Type String -Force
            Set-ItemProperty -Path $mousePath -Name 'MouseThreshold1' -Value '0' -Type String -Force
            Set-ItemProperty -Path $mousePath -Name 'MouseThreshold2' -Value '0' -Type String -Force
        } else {
            Set-ItemProperty -Path $mousePath -Name 'MouseSpeed' -Value '1' -Type String -Force
            Set-ItemProperty -Path $mousePath -Name 'MouseThreshold1' -Value '6' -Type String -Force
            Set-ItemProperty -Path $mousePath -Name 'MouseThreshold2' -Value '10' -Type String -Force
        }
        Write-Output "Mouse acceleration $action completed"
    """,
    # Fast Startup toggle
    "fast_startup_toggle": """
        $powerPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power'
        $action = '%value%'
        if ($action -eq 'disable') {
            Set-ItemProperty -Path $powerPath -Name 'HiberbootEnabled' -Value 0 -Type DWord -Force
        } else {
            Set-ItemProperty -Path $powerPath -Name 'HiberbootEnabled' -Value 1 -Type DWord -Force
        }
        Write-Output "Fast startup $action completed"
    """,
    # AFD Winsock socket buffer sizes - reduces UDP packet drops on fast connections
    "afd_buffers_toggle": r"""
        $afdPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\AFD\Parameters'
        $action = '%value%'
        if ($action -eq 'optimized') {
            if (-not (Test-Path $afdPath)) { New-Item -Path $afdPath -Force | Out-Null }
            Set-ItemProperty -Path $afdPath -Name 'DefaultReceiveWindow' -Value 131072 -Type DWord -Force
            Set-ItemProperty -Path $afdPath -Name 'DefaultSendWindow' -Value 131072 -Type DWord -Force
            Write-Output 'ok'
        } else {
            Remove-ItemProperty -Path $afdPath -Name 'DefaultReceiveWindow' -ErrorAction SilentlyContinue
            Remove-ItemProperty -Path $afdPath -Name 'DefaultSendWindow' -ErrorAction SilentlyContinue
            Write-Output 'ok'
        }
    """,
    # DSCP QoS - enables DSCP marking and creates policies for FPS game executables
    "dscp_qos_toggle": r"""
        $qosPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\QoS'
        $action = '%value%'
        $games = @('cs2.exe', 'ModernWarfare3.exe', 'cod.exe', 'Warzone.exe')
        if ($action -eq 'enabled') {
            if (-not (Test-Path $qosPath)) { New-Item -Path $qosPath -Force | Out-Null }
            Set-ItemProperty -Path $qosPath -Name 'Do not use NLA' -Value 1 -Type DWord -Force
            foreach ($exe in $games) {
                $name = "fpstune-$exe"
                Remove-NetQosPolicy -Name $name -Confirm:$false -ErrorAction SilentlyContinue
                New-NetQosPolicy -Name $name -AppPathNameMatchCondition $exe `
                    -IPProtocolMatchCondition UDP -DSCPAction 46 -ErrorAction SilentlyContinue | Out-Null
            }
            Write-Output 'enabled'
        } else {
            foreach ($exe in $games) {
                Remove-NetQosPolicy -Name "fpstune-$exe" -Confirm:$false -ErrorAction SilentlyContinue
            }
            Remove-ItemProperty -Path $qosPath -Name 'Do not use NLA' -ErrorAction SilentlyContinue
            Write-Output 'disabled'
        }
    """,
    # CS2 generic cvar toggle — writes a single console command (cvar + value)
    # into autoexec.cfg behind unique start/end markers, so any number of
    # parameterized settings can share one apply implementation.
    # Args:  %cvar%        e.g. 'cl_forcepreload'
    #        %cvar_value%  e.g. '1'
    #        %marker%      unique block tag (no spaces) e.g. 'cs2_forcepreload'
    #        %value%       'optimized' (write block) | 'default' (remove block)
    "cs2_cvar_toggle": _CONFIG_IO_HELPERS
    + r"""
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath }
        if (-not $sp) { Write-Output 'not_installed'; exit 0 }
        $libs = @($sp)
        $libVdf = Join-Path $sp 'steamapps\libraryfolders.vdf'
        if (Test-Path $libVdf) {
            $vdf = [System.IO.File]::ReadAllText($libVdf)
            foreach ($_m in [regex]::Matches($vdf, '"path"\s+"([^"]+)"')) {
                $_p = $_m.Groups[1].Value -replace '\\\\','\'
                if ($libs -notcontains $_p) { $libs += $_p }
            }
        }
        $cfgDir = $null
        foreach ($_lib in $libs) {
            $_candidate = Join-Path $_lib 'steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg'
            if (Test-Path $_candidate) { $cfgDir = $_candidate; break }
        }
        if (-not $cfgDir) { Write-Output 'not_installed'; exit 0 }
        $cfgPath = Join-Path $cfgDir 'autoexec.cfg'
        $action = '%value%'
        if ($action -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }
        $cvar = '%cvar%'; $cvarVal = '%cvar_value%'; $marker = '%marker%'
        $ms = "// ===fpstune-${marker}-start==="
        $me = "// ===fpstune-${marker}-end==="
        $block = "$ms`n$cvar $cvarVal`n$me"
        $pat = "(?s)// ===fpstune-${marker}-start===.*?// ===fpstune-${marker}-end===\r?\n?"
        if ($action -eq 'optimized' -or $action -eq 'enabled') {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, $pat, '')
                $content = $existing.TrimEnd() + "`n`n" + $block
            } else { $content = $block }
            Write-ConfigText $cfgPath $content
        } else {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, $pat, '')
                Write-ConfigText $cfgPath $existing.TrimEnd()
            }
        }
        Write-Output 'ok'
    """,
    # CS2 Steam Datagram Relay (SDR) - routes traffic through Valve's network backbone
    "cs2_sdr_toggle": _CONFIG_IO_HELPERS
    + r"""
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath }
        if (-not $sp) { Write-Output 'not_installed'; exit 0 }
        # Search every Steam library (libraryfolders.vdf) — CS2 may live in a
        # secondary library (e.g. D:\SteamLibrary), not the primary path.
        $libs = @($sp)
        $libVdf = Join-Path $sp 'steamapps\libraryfolders.vdf'
        if (Test-Path $libVdf) {
            $vdf = [System.IO.File]::ReadAllText($libVdf)
            foreach ($_m in [regex]::Matches($vdf, '"path"\s+"([^"]+)"')) {
                $_p = $_m.Groups[1].Value -replace '\\\\','\'
                if ($libs -notcontains $_p) { $libs += $_p }
            }
        }
        $cfgDir = $null
        foreach ($_lib in $libs) {
            $_candidate = Join-Path $_lib 'steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg'
            if (Test-Path $_candidate) { $cfgDir = $_candidate; break }
        }
        if (-not $cfgDir) { Write-Output 'not_installed'; exit 0 }
        $cfgPath = Join-Path $cfgDir 'autoexec.cfg'
        $action = '%value%'
        if ($action -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }
        $ms = '// ===fpstune-cs2_sdr-start==='; $me = '// ===fpstune-cs2_sdr-end==='
        $block = "$ms`nnet_client_steamdatagram_enable_override 1`n$me"
        if ($action -eq 'enabled') {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, '(?s)// ===fpstune-cs2_sdr-start===.*?// ===fpstune-cs2_sdr-end===\r?\n?', '')
                $content = $existing.TrimEnd() + "`n`n" + $block
            } else { $content = $block }
            Write-ConfigText $cfgPath $content
        } else {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, '(?s)// ===fpstune-cs2_sdr-start===.*?// ===fpstune-cs2_sdr-end===\r?\n?', '')
                Write-ConfigText $cfgPath $existing.TrimEnd()
            }
        }
        Write-Output 'ok'
    """,
    # CS2 mm_dedicated_search_maxping - skip servers above this ping to reduce unfair matches
    "cs2_maxping_toggle": _CONFIG_IO_HELPERS
    + r"""
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath }
        if (-not $sp) { Write-Output 'not_installed'; exit 0 }
        # Search every Steam library (libraryfolders.vdf) — CS2 may live in a
        # secondary library (e.g. D:\SteamLibrary), not the primary path.
        $libs = @($sp)
        $libVdf = Join-Path $sp 'steamapps\libraryfolders.vdf'
        if (Test-Path $libVdf) {
            $vdf = [System.IO.File]::ReadAllText($libVdf)
            foreach ($_m in [regex]::Matches($vdf, '"path"\s+"([^"]+)"')) {
                $_p = $_m.Groups[1].Value -replace '\\\\','\'
                if ($libs -notcontains $_p) { $libs += $_p }
            }
        }
        $cfgDir = $null
        foreach ($_lib in $libs) {
            $_candidate = Join-Path $_lib 'steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg'
            if (Test-Path $_candidate) { $cfgDir = $_candidate; break }
        }
        if (-not $cfgDir) { Write-Output 'not_installed'; exit 0 }
        $cfgPath = Join-Path $cfgDir 'autoexec.cfg'
        $action = '%value%'
        if ($action -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }
        $ms = '// ===fpstune-cs2_maxping-start==='; $me = '// ===fpstune-cs2_maxping-end==='
        $block = "$ms`nmm_dedicated_search_maxping 50`n$me"
        if ($action -eq '50ms') {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, '(?s)// ===fpstune-cs2_maxping-start===.*?// ===fpstune-cs2_maxping-end===\r?\n?', '')
                $content = $existing.TrimEnd() + "`n`n" + $block
            } else { $content = $block }
            Write-ConfigText $cfgPath $content
        } else {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, '(?s)// ===fpstune-cs2_maxping-start===.*?// ===fpstune-cs2_maxping-end===\r?\n?', '')
                Write-ConfigText $cfgPath $existing.TrimEnd()
            }
        }
        Write-Output 'ok'
    """,
    # MW3 texture streaming config - sets HTTPStreamLimitMBytes to 0 in gamerprofile
    "mw3_texture_toggle": _CONFIG_IO_HELPERS
    + r"""
        $docPath = [System.Environment]::GetFolderPath('MyDocuments')
        $action = '%value%'
        if ($action -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }
        $codPath = Join-Path $docPath 'Call of Duty MWIII\players'
        if (-not (Test-Path $codPath)) { Write-Output 'not_installed'; exit 0 }
        # Match both legacy 'gamerprofile.0.BASE.cst' and current 'gamerprofile.pc.0.BASE.cst'.
        # Pick the most recently modified gamerprofile to handle multi-account installs,
        # but never a copy under mw3fix_backup — writing to a backup changes nothing
        # for the game while reporting success.
        $cfg = Get-ChildItem -Path $codPath -Recurse -Filter 'gamerprofile*.BASE.cst' -EA SilentlyContinue |
               Where-Object { $_.FullName -notmatch 'mw3fix_backup' } |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $cfg) { Write-Output 'not_installed'; exit 0 }
        $cfgFile = $cfg.FullName
        # Clear a read-only lock left by an earlier fpstune release. We never set
        # one again: locking the file stops MW3 saving ANY setting it keeps here,
        # so every in-game change silently reverted on the next launch.
        $attr = (Get-Item $cfgFile).Attributes
        if ($attr -band [System.IO.FileAttributes]::ReadOnly) {
            Set-ItemProperty -Path $cfgFile -Name Attributes -Value ($attr -band (-bnot [System.IO.FileAttributes]::ReadOnly))
        }
        $c = Read-ConfigText $cfgFile
        # MW3 writes gamerprofile in TWO shapes, and which one a machine has
        # depends on the profile, not on the game version: measured on one install,
        # one account's gamerprofile.0.BASE.cst uses `Key@0 = value` for all 60
        # keys while another's gamerprofile.pc.0.BASE.cst uses `Key@ value`.
        # So the separator is captured and written back unchanged rather than
        # chosen. Assuming either shape breaks the other half of the installs —
        # the first pattern here assumed `Key@N = v` and appended a junk key when
        # it missed; its replacement assumed `Key@ v` and simply failed to apply.
        $pattern = '(?m)(^[ \t]*HTTPStreamLimitMBytes@(?:\d*[ \t]*=[ \t]*|[ \t]+))\d+'
        if ($c -notmatch $pattern) { Write-Output 'not_installed'; exit 0 }
        $newVal = if ($action -eq 'minimal') { '0' } else { '1024' }
        $c = [regex]::Replace($c, $pattern, "`${1}$newVal")

        # Named compound: HTTPStreamUsageLimit is the gate. On a profile where it
        # is false the MB cap above is inert, which is the most likely reason this
        # tweak has never had a measurable effect. Written together so the concept
        # is either on or off, never half-applied.
        $gate = '(?m)(^[ \t]*HTTPStreamUsageLimit@(?:\d*[ \t]*=[ \t]*|[ \t]+))\w+'
        if ($c -match $gate) {
            $gateVal = if ($action -eq 'minimal') { 'true' } else { 'false' }
            $c = [regex]::Replace($c, $gate, "`${1}$gateVal")
        }

        Write-ConfigText $cfgFile $c
        Write-Output $action
    """,
    # MW3 NAT firewall rules - opens required ports for Open NAT
    "mw3_nat_firewall_toggle": r"""
        $ruleName = 'fpstune-MW3-NAT'
        $action = '%value%'
        # Always clean up existing rules first
        Get-NetFirewallRule -DisplayName "$ruleName*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        if ($action -eq 'open_nat') {
            New-NetFirewallRule -DisplayName "$ruleName-UDP-In" -Direction Inbound `
                -Protocol UDP -LocalPort @('3074','4380','27000-27036','28950') `
                -Action Allow -Profile Any -EA SilentlyContinue | Out-Null
            New-NetFirewallRule -DisplayName "$ruleName-UDP-Out" -Direction Outbound `
                -Protocol UDP -RemotePort @('3074','4380','27000-27036','28950') `
                -Action Allow -Profile Any -EA SilentlyContinue | Out-Null
            New-NetFirewallRule -DisplayName "$ruleName-TCP-In" -Direction Inbound `
                -Protocol TCP -LocalPort @('3074','3075','27015-27030','27036-27037') `
                -Action Allow -Profile Any -EA SilentlyContinue | Out-Null
            New-NetFirewallRule -DisplayName "$ruleName-TCP-Out" -Direction Outbound `
                -Protocol TCP -RemotePort @('3074','3075','27015-27030','27036-27037') `
                -Action Allow -Profile Any -EA SilentlyContinue | Out-Null
            Write-Output 'open_nat'
        } else {
            Write-Output 'default'
        }
    """,
    # Call of Duty shader/content cache cleanup. Every one of these is rebuilt on
    # the game's next launch, and the install path comes from Battle.net's own
    # record rather than a constant — see `_cod_install_lookup`.
    "mw3_shader_cache_cleanup": _cod_cache_cleanup("cod23", "MW3"),
    "mw4_shader_cache_cleanup": _cod_cache_cleanup("cod26", "MW4"),
    # Crash reports the Call of Duty launcher writes beside the player config.
    # One directory, shared by every COD title on the machine.
    "cod_crash_reports_cleanup": r"""
        $path = Join-Path $env:LOCALAPPDATA 'Activision\Call of Duty\crash_reports'
        $freed = [long]0
        if ([System.IO.Directory]::Exists($path)) {
            foreach ($f in [System.IO.Directory]::EnumerateFiles($path, '*', [System.IO.SearchOption]::AllDirectories)) {
                try { $freed += [System.IO.FileInfo]::new($f).Length } catch {}
            }
            Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    # MW3 crash dump cleanup
    "mw3_crash_cleanup": r"""
        $path = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Call of Duty MWIII\crashes'
        $freed = [long]0
        if ([System.IO.Directory]::Exists($path)) {
            foreach ($f in [System.IO.Directory]::EnumerateFiles($path, '*', [System.IO.SearchOption]::AllDirectories)) {
                try { $freed += [System.IO.FileInfo]::new($f).Length } catch {}
            }
            Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
        }
        Write-Output "Cleaned $([math]::Round($freed/1MB, 2)) MB"
    """,
    # MW3 options.4.cod23.cst toggle - modifies graphics/system options file
    # Key format: "KeyName:version.platform" e.g. "WorldStreamingQuality:0.0"
    # If the key is absent (game has never written it), the toggle APPENDS it
    # so the next launch picks up the recommended value instead of failing.
    "mw3_options_toggle": _CONFIG_IO_HELPERS
    + r"""
        $docPath = [System.Environment]::GetFolderPath('MyDocuments')
        $optPath = Join-Path $docPath 'Call of Duty MWIII\players\options.4.cod23.cst'
        if (-not (Test-Path $optPath)) { Write-Output 'not_installed'; exit 0 }
        $key = '%key%'; $newVal = '%value%'
        if ($newVal -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }

        # Clear a read-only lock left by an earlier fpstune release, and never set
        # one again. Locking options.4.cod23.cst froze the whole file: MW3 could no
        # longer persist ANY graphics setting, so every in-game change reverted on
        # the next launch, and detection read fpstune's own frozen values back and
        # reported "already optimal". Locking the file lowers the ceiling.
        $startAttrs = (Get-Item $optPath).Attributes
        if ($startAttrs -band [System.IO.FileAttributes]::ReadOnly) {
            Set-ItemProperty -Path $optPath -Name Attributes -Value ($startAttrs -band (-bnot [System.IO.FileAttributes]::ReadOnly))
        }

        $c = Read-ConfigText $optPath
        # Strip version suffix (e.g. "DisplayMode:0.0" -> "DisplayMode") so we match
        # any version the game writes (0.0, 1.0, etc.) — avoids spurious appends when
        # the game uses a different version number than our apply_args key.
        $keyName = $key -replace ':[0-9.]+$', ''
        $escapedName = [regex]::Escape($keyName)
        # (?m)^\s* anchors to start-of-line — prevents 'ShadowQuality' from matching
        # the suffix of 'ScreenSpaceShadowQuality'.
        $keyPattern = "(?m)^\s*$escapedName`:[0-9.]+\s*=\s*`"[^`"]*`""
        $resultTag = 'ok'
        if ($c -match $keyPattern) {
            $newContent = [regex]::Replace($c, "(?m)(^\s*$escapedName`:[0-9.]+\s*=\s*`")[^`"]*`"", "`${1}$newVal`"")
            if ($newContent -eq $c) { Write-Output 'unchanged'; exit 0 }
        } else {
            # The file's own line ending, not a literal CRLF: options.4.cod23.cst
            # is pure LF, and appending CRLF left it carrying both conventions.
            $nl = Get-ConfigNewline $c
            $appendBlock = "$nl// fpstune-appended$nl$key = `"$newVal`"$nl"
            $newContent = $c.TrimEnd() + $appendBlock
            $resultTag = 'ok_appended'
        }
        Write-ConfigText $optPath $newContent
        Write-Output $resultTag
    """,
    # Heroes of the Storm Variables.txt - plain key=value, one per line.
    # Two shapes occur in one file and the bracketed index belongs to the game:
    #     vsync=true
    #     GraphicsOptionTextureQuality[2]=0
    # The index is captured and written back untouched. Inventing or dropping one
    # leaves the key the game actually reads in place and adds a dead sibling —
    # the same defect MW3 paid for with its two gamerprofile shapes.
    #
    # The file is never made read-only. MW3's options file was locked by an
    # earlier release and the game then could not persist any setting at all;
    # HotS rewrites Variables.txt on exit the same way, so a lock here would
    # freeze every graphics option the player changes in-game.
    "hots_variable_set": _CONFIG_IO_HELPERS
    + r"""
        $docPath = [System.Environment]::GetFolderPath('MyDocuments')
        $varPath = Join-Path $docPath 'Heroes of the Storm\Variables.txt'
        if (-not (Test-Path $varPath)) { Write-Output 'not_installed'; exit 0 }
        $key = '%key%'; $newVal = '%value%'
        if ($newVal -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }

        # Clear a read-only flag if anything left one; never set one.
        $attrs = (Get-Item $varPath).Attributes
        if ($attrs -band [System.IO.FileAttributes]::ReadOnly) {
            Set-ItemProperty -Path $varPath -Name Attributes -Value ($attrs -band (-bnot [System.IO.FileAttributes]::ReadOnly))
        }

        $c = Read-ConfigText $varPath
        $escapedName = [regex]::Escape($key)
        # ^ anchored so 'shadows' cannot match inside 'localShadows', and the
        # optional [n] is part of the key rather than part of the value.
        $keyPattern = "(?mi)^[ \t]*$escapedName(\[\d+\])?[ \t]*=.*$"
        $resultTag = 'ok'
        if ($c -match $keyPattern) {
            $newContent = [regex]::Replace($c, "(?mi)^([ \t]*$escapedName(?:\[\d+\])?[ \t]*=[ \t]*).*$", "`${1}$newVal")
            if ($newContent -eq $c) { Write-Output 'unchanged'; exit 0 }
        } else {
            $nl = Get-ConfigNewline $c
            $newContent = $c.TrimEnd() + "$nl$key=$newVal$nl"
            $resultTag = 'ok_appended'
        }
        Write-ConfigText $varPath $newContent
        Write-Output $resultTag
    """,
    # MW3 pause-rendering compound - PauseRenderingEnabled and
    # SustainabilityPauseRendering both stop rendering on focus loss, so writing
    # only one leaves the behaviour switched on by the other.
    "mw3_pause_rendering_toggle": _CONFIG_IO_HELPERS
    + r"""
        $docPath = [System.Environment]::GetFolderPath('MyDocuments')
        $optPath = Join-Path $docPath 'Call of Duty MWIII\players\options.4.cod23.cst'
        if (-not (Test-Path $optPath)) { Write-Output 'not_installed'; exit 0 }
        $newVal = '%value%'
        if ($newVal -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }

        # Clear a read-only lock left by an earlier fpstune release; never set one.
        $attrs = (Get-Item $optPath).Attributes
        if ($attrs -band [System.IO.FileAttributes]::ReadOnly) {
            Set-ItemProperty -Path $optPath -Name Attributes -Value ($attrs -band (-bnot [System.IO.FileAttributes]::ReadOnly))
        }

        $c = Read-ConfigText $optPath
        $written = 0
        foreach ($k in @('PauseRenderingEnabled', 'SustainabilityPauseRendering')) {
            $pattern = "(?m)(^\s*$k`:[0-9.]+\s*=\s*`")[^`"]*`""
            if ($c -match $pattern) {
                $c = [regex]::Replace($c, $pattern, "`${1}$newVal`"")
                $written++
            }
        }
        if ($written -eq 0) { Write-Output 'not_installed'; exit 0 }
        Write-ConfigText $optPath $c
        Write-Output $newVal
    """,
    # CS2 fps_max toggle - uncaps frame rate for maximum performance
    "cs2_fps_max_toggle": _CONFIG_IO_HELPERS
    + r"""
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath }
        if (-not $sp) { Write-Output 'not_installed'; exit 0 }
        # Search every Steam library (libraryfolders.vdf) — CS2 may live in a
        # secondary library (e.g. D:\SteamLibrary), not the primary path.
        $libs = @($sp)
        $libVdf = Join-Path $sp 'steamapps\libraryfolders.vdf'
        if (Test-Path $libVdf) {
            $vdf = [System.IO.File]::ReadAllText($libVdf)
            foreach ($_m in [regex]::Matches($vdf, '"path"\s+"([^"]+)"')) {
                $_p = $_m.Groups[1].Value -replace '\\\\','\'
                if ($libs -notcontains $_p) { $libs += $_p }
            }
        }
        $cfgDir = $null
        foreach ($_lib in $libs) {
            $_candidate = Join-Path $_lib 'steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg'
            if (Test-Path $_candidate) { $cfgDir = $_candidate; break }
        }
        if (-not $cfgDir) { Write-Output 'not_installed'; exit 0 }
        $cfgPath = Join-Path $cfgDir 'autoexec.cfg'
        $action = '%value%'
        if ($action -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }
        $marker_start = '// ===fpstune-fps_max-start==='
        $marker_end = '// ===fpstune-fps_max-end==='
        $block = "$marker_start`nfps_max 0`n$marker_end"
        if ($action -eq 'uncapped') {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, '(?s)// ===fpstune-fps_max-start===.*?// ===fpstune-fps_max-end===\r?\n?', '')
                $content = $existing.TrimEnd() + "`n`n" + $block
            } else {
                $content = $block
            }
            Write-ConfigText $cfgPath $content
        } else {
            if (Test-Path $cfgPath) {
                $existing = Read-ConfigText $cfgPath
                $existing = [regex]::Replace($existing, '(?s)// ===fpstune-fps_max-start===.*?// ===fpstune-fps_max-end===\r?\n?', '')
                Write-ConfigText $cfgPath $existing.TrimEnd()
            }
        }
        Write-Output 'ok'
    """,
    # Hibernation toggle - uses powercfg to also delete/create hiberfil.sys
    "hibernation_toggle": """
        $action = '%value%'
        if ($action -eq 'disable') {
            powercfg /h off 2>$null
            Write-Output 'Hibernation disabled'
        } else {
            powercfg /h on 2>$null
            Write-Output 'Hibernation enabled'
        }
    """,
    # Steam config.vdf toggle - modifies global Steam config
    "steam_config_vdf_toggle": _CONFIG_IO_HELPERS
    + r"""
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath }
        if (-not $sp) { Write-Output 'not_installed'; exit 0 }
        $vdfPath = Join-Path $sp 'config\config.vdf'
        if (-not (Test-Path $vdfPath)) { Write-Output 'not_installed'; exit 0 }
        $key = '%key%'; $newVal = '%value%'
        $c = Read-ConfigText $vdfPath
        $escaped = [regex]::Escape($key)
        if ($c -match ('"' + $escaped + '"')) {
            $c = [regex]::Replace($c, '("' + $escaped + '"\s+)"[^"]*"', "`$1`"$newVal`"")
        } else {
            $c = [regex]::Replace($c, '("Steam"\s*\n\s*\{)', "`$1`n`t`t`t`t`"$key`"`t`t`t`"$newVal`"")
        }
        Write-ConfigText $vdfPath $c
        Write-Output 'ok'
    """,
    # Steam localconfig.vdf toggle - modifies per-user Steam config (most-recent user)
    "steam_localconfig_vdf_toggle": _CONFIG_IO_HELPERS
    + r"""
        $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath
        if (-not $sp) { $sp = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name 'InstallPath' -EA SilentlyContinue).InstallPath }
        if (-not $sp) { Write-Output 'not_installed'; exit 0 }
        $lcfg = Get-ChildItem "$sp\userdata\*\config\localconfig.vdf" -EA SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $lcfg) { Write-Output 'not_installed'; exit 0 }
        $key = '%key%'; $newVal = '%value%'
        $c = Read-ConfigText $lcfg.FullName
        $escaped = [regex]::Escape($key)
        if ($c -match ('"' + $escaped + '"')) {
            $c = [regex]::Replace($c, '("' + $escaped + '"\s+)"[^"]*"', "`$1`"$newVal`"")
        } else {
            $c = [regex]::Replace($c, '("system"\s*\n\s*\{)', "`$1`n`t`t`t`"$key`"`t`t`t`"$newVal`"")
        }
        Write-ConfigText $lcfg.FullName $c
        Write-Output 'ok'
    """,
    # Battle.net JSON config toggle - modifies Battle.net.config JSON
    "bnet_json_toggle": r"""
        $bnetCfg = Join-Path $env:APPDATA 'Battle.net\Battle.net.config'
        if (-not (Test-Path $bnetCfg)) { Write-Output 'not_installed'; exit 0 }
        try {
            $json = Get-Content $bnetCfg -Raw | ConvertFrom-Json
            $section = '%section%'; $key = '%key%'; $val = '%value%'
            if ($null -eq $json.$section) {
                $json | Add-Member -NotePropertyName $section -NotePropertyValue ([PSCustomObject]@{}) -Force
            }
            $json.$section | Add-Member -NotePropertyName $key -NotePropertyValue $val -Force
            $json | ConvertTo-Json -Depth 10 | Set-Content $bnetCfg -Encoding UTF8
            Write-Output 'ok'
        } catch { Write-Output "error:$($_.Exception.Message)" }
    """,
    # Steam CEF (browser) GPU compositing toggle - disables GPU in Steam UI for lower overhead
    "steam_cef_toggle": r"""
        $action = '%value%'
        if ($action -eq 'not_installed') { Write-Output 'not_installed'; exit 0 }
        $regPath = 'HKCU:\Software\Valve\Steam'
        if ($action -eq 'disabled') {
            Set-ItemProperty -Path $regPath -Name 'BrowserFlags' -Value '-cef-disable-gpu-compositing -cef-disable-webgl -cef-disable-webgl2' -Type String -Force
        } else {
            Remove-ItemProperty -Path $regPath -Name 'BrowserFlags' -ErrorAction SilentlyContinue
        }
        Write-Output 'ok'
    """,
    # Detection helpers - return size estimates for cleanup actions
    "memory_status": "Write-Output $true",
    # Cleanup size estimation - scans folders and returns estimated bytes to free.
    # Uses DirectoryInfo.EnumerateFiles: the FileInfo objects it yields carry their
    # Length pre-populated from the directory enumeration's Win32 find-data, so summing
    # .Length costs ZERO extra stat calls per file. The previous approach
    # (Directory.EnumerateFiles string paths + new FileInfo(path).Length) did one stat
    # per file — the dominant cost on many-file caches (npm/gradle/maven, 100k+ files).
    # This is locale-independent and exact, unlike robocopy summary parsing (its "Bytes :"
    # label is localized) or COM FileSystemObject.Size (throws on access-denied/long paths).
    "cleanup_status": _CLEANUP_STATUS,
    # Maintenance status - these don't have size estimates
    "maintenance_status": "Write-Output $true",
    # Hyper-V / Virtual Machine Platform toggle
    "hyper_v_only_toggle": """
        $action = '%value%'
        if ($action -eq 'disable') {
            $hv = Get-WindowsOptionalFeature -Online `
                -FeatureName Microsoft-Hyper-V -ErrorAction SilentlyContinue
            if ($hv -and $hv.State -eq 'Enabled') {
                Disable-WindowsOptionalFeature -Online `
                    -FeatureName Microsoft-Hyper-V `
                    -NoRestart -ErrorAction SilentlyContinue | Out-Null
            }
            Write-Output 'disabled'
        } else {
            Enable-WindowsOptionalFeature -Online `
                -FeatureName Microsoft-Hyper-V -All `
                -NoRestart -ErrorAction SilentlyContinue | Out-Null
            Write-Output 'enabled'
        }
    """,
    "vm_platform_toggle": """
        $action = '%value%'
        if ($action -eq 'disable') {
            $vmp = Get-WindowsOptionalFeature -Online `
                -FeatureName VirtualMachinePlatform -ErrorAction SilentlyContinue
            if ($vmp -and $vmp.State -eq 'Enabled') {
                Disable-WindowsOptionalFeature -Online `
                    -FeatureName VirtualMachinePlatform `
                    -NoRestart -ErrorAction SilentlyContinue | Out-Null
            }
            Write-Output 'disabled'
        } else {
            Enable-WindowsOptionalFeature -Online `
                -FeatureName VirtualMachinePlatform -All `
                -NoRestart -ErrorAction SilentlyContinue | Out-Null
            Write-Output 'enabled'
        }
    """,
    # Input personalization toggle (both text + ink collection)
    "input_personalization_toggle": """
        $path = 'HKCU:\\SOFTWARE\\Microsoft\\InputPersonalization'
        $action = '%value%'
        if ($action -eq 'disable') {
            Set-ItemProperty -Path $path -Name 'RestrictImplicitTextCollection' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $path -Name 'RestrictImplicitInkCollection' -Value 1 -Type DWord -Force
        } else {
            Set-ItemProperty -Path $path -Name 'RestrictImplicitTextCollection' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $path -Name 'RestrictImplicitInkCollection' -Value 0 -Type DWord -Force
        }
        Write-Output "Input personalization $action completed"
    """,
    # Feedback reminders toggle (SIUF + Group Policy DoNotShowFeedbackNotifications)
    "feedback_reminders_toggle": """
        $siufPath = 'HKCU:\\SOFTWARE\\Microsoft\\Siuf\\Rules'
        $gpPath = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection'
        $action = '%value%'
        if (-not (Test-Path $siufPath)) { New-Item -Path $siufPath -Force | Out-Null }
        if (-not (Test-Path $gpPath)) { New-Item -Path $gpPath -Force | Out-Null }
        if ($action -eq 'disable') {
            Set-ItemProperty -Path $siufPath -Name 'NumberOfSIUFInPeriod' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $siufPath -Name 'PeriodInNanoSeconds' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $gpPath -Name 'DoNotShowFeedbackNotifications' -Value 1 -Type DWord -Force
        } else {
            Remove-ItemProperty -Path $siufPath -Name 'NumberOfSIUFInPeriod' -ErrorAction SilentlyContinue
            Remove-ItemProperty -Path $siufPath -Name 'PeriodInNanoSeconds' -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $gpPath -Name 'DoNotShowFeedbackNotifications' -Value 0 -Type DWord -Force
        }
        Write-Output "Feedback reminders $action completed"
    """,
    # Application telemetry toggle (AITEnable + DisableUAR + DisableInventory)
    "app_telemetry_toggle": """
        $appCompatPath = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppCompat'
        $action = '%value%'
        if (-not (Test-Path $appCompatPath)) { New-Item -Path $appCompatPath -Force | Out-Null }
        if ($action -eq 'disable') {
            Set-ItemProperty -Path $appCompatPath -Name 'AITEnable' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $appCompatPath -Name 'DisableUAR' -Value 1 -Type DWord -Force
            Set-ItemProperty -Path $appCompatPath -Name 'DisableInventory' -Value 1 -Type DWord -Force
        } else {
            Remove-ItemProperty -Path $appCompatPath -Name 'AITEnable' -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $appCompatPath -Name 'DisableUAR' -Value 0 -Type DWord -Force
            Set-ItemProperty -Path $appCompatPath -Name 'DisableInventory' -Value 0 -Type DWord -Force
        }
        Write-Output "App telemetry $action completed"
    """,
    # Resizable BAR detection (iterates GPU class registry subkeys)
    "rebar_detect": """
        $gpuClass = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class'
        $gpuClass += '\\{4d36e968-e325-11ce-bfc1-08002be10318}'
        $result = 'disabled'
        if (Test-Path $gpuClass) {
            Get-ChildItem -Path $gpuClass -EA SilentlyContinue | ForEach-Object {
                $sub = $_.PSPath
                $val = (Get-ItemProperty -Path $sub `
                    -Name 'LargeBarMapped' -EA SilentlyContinue
                ).LargeBarMapped
                if ($val -eq 1) { $result = 'enabled' }
            }
        }
        Write-Output $result
    """,
}


# =============================================================================
# Cross-thread serialization for action commands that share a target file.
# =============================================================================
# Why: bulk_apply_settings (api/routes/settings.py) runs setting applies in
# parallel via ThreadPoolExecutor. When several settings target the SAME file,
# every thread reads the file, mutates its own line, and writes the whole
# file back — and the LAST writer wins, silently reverting earlier threads'
# changes. A named system mutex serializes the read-modify-write across all
# parallel applies (and across processes), eliminating the race.
#
# How: For each action_command that writes a shared file, we wrap its script
# body in a Mutex acquire/release block (try/finally so failures still
# release the lock). The wrapper preserves the original 'exit 0' semantics
# because PowerShell runs the finally clause even on exit.

_MUTEX_GROUPS: dict[str, list[str]] = {
    # Every CS2 toggle edits the same Counter-Strike Global Offensive autoexec.cfg.
    "Global\\fpstune-cs2-autoexec-cfg": [
        "cs2_cvar_toggle",
        "cs2_sdr_toggle",
        "cs2_maxping_toggle",
        "cs2_fps_max_toggle",
    ],
    # MW3 options.4.cod23.cst — every per-key MW3 graphics setting writes here.
    "Global\\fpstune-mw3-options-cst": [
        "mw3_options_toggle",
    ],
    # Heroes of the Storm Variables.txt — every HotS setting rewrites the whole
    # file, so two concurrent applies would drop one of the two writes.
    "Global\\fpstune-hots-variables-txt": [
        "hots_variable_set",
    ],
    # MW3 gamerprofile.pc.0.BASE.cst — only HTTPStreamLimit today, future settings
    # may target this same file (e.g. FOV, Brightness), so serialize defensively.
    "Global\\fpstune-mw3-gamerprofile-cst": [
        "mw3_texture_toggle",
    ],
    # Steam config.vdf — generic toggle keyed by setting; serialize all writes.
    "Global\\fpstune-steam-config-vdf": [
        "steam_config_vdf_toggle",
    ],
    # Steam localconfig.vdf (per-app launch options).
    "Global\\fpstune-steam-localconfig-vdf": [
        "steam_localconfig_vdf_toggle",
    ],
    # Battle.net Battle.net.config (single JSON file, multiple settings target it).
    "Global\\fpstune-bnet-json": [
        "bnet_json_toggle",
    ],
}


def _wrap_with_mutex(script: str, mutex_name: str) -> str:
    """Wrap a PowerShell script body with a named-mutex acquire/release.

    Serializes parallel apply threads / processes that target the same file.
    """
    return (
        "\n        $_fpstuneMtx = New-Object System.Threading.Mutex($false, "
        f"'{mutex_name}')\n"
        "        $_fpstuneHaveLock = $false\n"
        "        try {\n"
        "            $_fpstuneHaveLock = $_fpstuneMtx.WaitOne(15000)\n"
        "            if (-not $_fpstuneHaveLock) { Write-Output 'lock_timeout'; exit 1 }\n"
        f"{script}"
        "        } finally {\n"
        "            if ($_fpstuneHaveLock) { $_fpstuneMtx.ReleaseMutex() }\n"
        "            $_fpstuneMtx.Dispose()\n"
        "        }\n"
    )


def _wire_mutex_groups(commands: dict[str, str], groups: dict[str, list[str]]) -> None:
    """Wrap every mutex-group member in its named lock, loudly.

    A group entry that no longer matches an ACTION_COMMANDS key is a script
    that MUST be serialized running with no lock at all — the silent
    `if _k in commands` skip this replaces lost the whole-shared-file lock
    invariant on a mere rename. Import fails instead, so a renamed action
    command has to rename its group entry in the same commit.
    """
    unknown = [key for keys in groups.values() for key in keys if key not in commands]
    if unknown:
        raise RuntimeError(
            f"_MUTEX_GROUPS references ACTION_COMMANDS keys that do not exist: {unknown}. "
            "Rename the group entry together with the action command, or its shared "
            "file loses cross-thread locking."
        )
    for mutex_name, keys in groups.items():
        for key in keys:
            commands[key] = _wrap_with_mutex(commands[key], mutex_name)


# Apply the mutex wrapper to every group at import time so callers always get
# the serialized version when they look up a script by key.
_wire_mutex_groups(ACTION_COMMANDS, _MUTEX_GROUPS)


# Action commands whose detect answer is a constant. These describe an operation
# that is always available — running SFC, purging the standby list — not a state
# the machine holds, so their script is the literal `Write-Output $true`.
#
# Starting a PowerShell process to learn a literal costs a process and answers
# nothing: measured, three of the twenty-five a cold scan spawned were exactly
# this. The executor answers them directly and still routes the value through
# `value_map`, so it is the same value by the same route.
#
# Derived from the shipped scripts rather than written out, so a command that
# stops being constant stops being listed here in the same commit that changes
# it — a hand-kept list would go on claiming a constant for a script that had
# started asking the machine something.
CONSTANT_STATUS_ACTIONS: dict[str, str] = {
    key: "True" for key, script in ACTION_COMMANDS.items() if script.strip() == "Write-Output $true"
}
