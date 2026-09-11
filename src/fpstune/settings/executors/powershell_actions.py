"""PowerShell action-command payloads.

Extracted from settings/executors/powershell.py to keep the executor module
focused on detect/apply logic. Each value is a self-contained PowerShell
script that uses %placeholder% substitution at execution time.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from fpstune.settings.cleanup_targets import PATH_SEPARATOR

#: The separator escaped for PowerShell's `-split`, which takes a regex.
_PATH_SPLIT = re.escape(PATH_SEPARATOR)

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
    r"""        # Per-type reclaimable bytes from 'docker system df' as a hashtable
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
    + r"""        # What is left here is what no directory walk can answer: a component
        # store only DISM accounts for, a docker daemon's own bookkeeping, the
        # VSS shadow storage allocation, and the event log service's record
        # counts. Every cleanup whose target is a folder is measured in-process
        # by `settings/cleanup_targets.py` instead - from the same path list its
        # delete command is handed, and without a process start per scan.
        #
        # The dispatch is still a function so the helpers above are parsed once
        # and then asked about each remaining type in the same session.
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
            'event_logs' {
                # Only the logs `ClearLog` will actually clear, which is the ones
                # holding records. Measured here on 2026-09-10: the whole folder
                # was 449 files and 67.3 MB, of which 41 logs holding 35.5 MB had
                # any record in them at all - so sizing the folder promised
                # roughly twice what clearing it can return. A cleared log keeps
                # a small allocation (4 KB was the smallest on disk), which this
                # does not subtract; that is under half a percent of the figure,
                # and it leaves the estimate conservative rather than optimistic.
                #
                # The same criterion is read again afterwards, so a log the
                # service refused to clear stays in the set and the freed figure
                # reports only what actually went.
                $bytes = [long]0
                foreach ($log in Get-WinEvent -ListLog * -ErrorAction SilentlyContinue) {
                    if (-not $log.RecordCount -or $log.RecordCount -le 0) { continue }
                    $file = $log.LogFilePath
                    if (-not $file) { continue }
                    $file = [Environment]::ExpandEnvironmentVariables($file)
                    try { $bytes += [System.IO.FileInfo]::new($file).Length } catch {}
                }
                Write-Output "ready|$([math]::Round($bytes/1MB, 0)) MB"
            }
            'docker_prune' {
                # `docker system prune -f` reclaims build cache + stopped containers +
                # dangling images only - NOT unused tagged images (needs -a) or volumes.
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
"""
)


# Every SSD volume this machine can retrim, as (drive letter, volume path) pairs
# in $ssdVolumes. Shared by the reading and the action on purpose: if the two
# disagreed about which volumes count, a retrim would leave behind a volume the
# reading still calls overdue, and the row would never go green.
#
# The three properties compared here come back as their storage-MOF ValueMap
# names rather than as MUI text - the same enumeration printed `SSD`, `NVMe` and
# `Fixed` verbatim on a Turkish Windows on 2026-09-10 - so this is the C4
# carve-out, not localized-text parsing. `SpindleSpeed` is the second opinion for
# a disk that reports `Unspecified`: Windows documents 0 as solid state.
# `DriveType -ne 'Fixed'` drops an external enclosure, which Optimize Drives does
# not list either.
_SSD_VOLUMES = r"""
    $sep = [char]0x5C
    $solidDisks = @()
    foreach ($pd in Get-PhysicalDisk) {
        $solid = ($pd.MediaType -eq 'SSD') -or
                 (($pd.MediaType -eq 'Unspecified') -and ($pd.SpindleSpeed -eq 0))
        if (-not $solid) { continue }
        foreach ($disk in ($pd | Get-Disk)) { $solidDisks += $disk.Number }
    }
    $ssdVolumes = @()
    foreach ($part in Get-Partition) {
        if (-not $part.DriveLetter) { continue }
        if ($solidDisks -notcontains $part.DiskNumber) { continue }
        $vol = Get-Volume -DriveLetter $part.DriveLetter
        if (-not $vol) { continue }
        if ($vol.DriveType -ne 'Fixed') { continue }
        $volPath = $vol.Path
        if (-not $volPath) { $volPath = $vol.UniqueId }
        $ssdVolumes += ,@($part.DriveLetter, $volPath)
    }
"""

# When Windows last ran Optimize Drives on each SSD volume, and whether that is
# long enough ago to say the schedule has stopped running.
#
# The record is `LastRunTime` under
# HKLM\SOFTWARE\Microsoft\Dfrg\Statistics\Volume{<guid>}: a 16-byte REG_BINARY
# SYSTEMTIME in local time - wYear, wMonth, wDayOfWeek, wDay, wHour, wMinute,
# wSecond, wMilliseconds, each a little-endian word. The subkey name is the
# volume GUID `Get-Volume` reports as its own `Path`, which is why nothing here
# has to name a drive.
#
# Three readings taken on this machine on 2026-09-10 decided that source over the
# event log:
#   1. `ScheduledDefrag`'s task history said 7.09.2026 01:52:24 and the system
#      volume's `LastRunTime` decoded to 2026-09-07 01:52:24 - the same second,
#      so the key is what the scheduled optimization writes.
#   2. The Application log held one record in total and zero Defrag events, so
#      `Get-WinEvent -Id 258` would have answered "never" on a machine that had
#      been retrimmed three days earlier. An event log rolls; this key does not.
#   3. A retrim then moved the key to 2026-09-10 23:00:55 and left
#      `LastRunClustersTrimmed` at 7409270 - so it tracks a retrim, not only a
#      full defragmentation, which keeps its own `LastRunFullDefragTime`.
#
# The threshold is 14 days because Windows' own optimization schedule is weekly:
# one missed week is a machine that was switched off, two is a schedule that is
# not running. It is deliberately not the point at which an SSD suffers - TRIM
# arrears cost sustained write speed gradually - but the point at which the
# arrears mean something is broken.
#
# Which volume the number describes is the one nearest the threshold from its own
# side: `ok` reports the oldest retrim (the volume closest to going overdue) and
# `overdue` reports the newest overdue one (the volume that crossed most
# recently). Both answer "how close to the line is this machine", and neither can
# overstate the case. A volume with no record at all outranks every age, because
# "never" is not a large number of days.
_SSD_TRIM_STATUS = (
    r"""
    $ErrorActionPreference = 'SilentlyContinue'
    $thresholdDays = 14
    $statsRoot = 'HKLM:\SOFTWARE\Microsoft\Dfrg\Statistics'
"""
    + _SSD_VOLUMES
    + r"""
    if ((@(Get-PhysicalDisk)).Count -eq 0) {
        Write-Output 'FPSTUNE_WARN: Get-PhysicalDisk listed no disk; the storage service could not answer'
    }
    $now = Get-Date
    $noRecord = $false
    $ages = @()
    foreach ($entry in $ssdVolumes) {
        $leaf = ''
        if ($entry[1]) { $leaf = $entry[1].TrimEnd($sep).Split($sep)[-1] }
        $stamp = $null
        if ($leaf.StartsWith('Volume{')) {
            $stat = (Get-ItemProperty (Join-Path $statsRoot $leaf)).LastRunTime
            if ($stat -and $stat.Length -ge 16) {
                $year   = $stat[0]  + $stat[1]  * 256
                $month  = $stat[2]  + $stat[3]  * 256
                $day    = $stat[6]  + $stat[7]  * 256
                $hour   = $stat[8]  + $stat[9]  * 256
                $minute = $stat[10] + $stat[11] * 256
                $second = $stat[12] + $stat[13] * 256
                # An all-zero structure is the shape of "this volume has never
                # been optimized", and an impossible date is a corrupt one; both
                # leave $stamp null, which is the same answer.
                if ($year -gt 1900) {
                    $stamp = Get-Date -Year $year -Month $month -Day $day -Hour $hour -Minute $minute -Second $second
                }
            }
        }
        if ($null -eq $stamp) { $noRecord = $true; continue }
        $age = [int][Math]::Floor(($now - $stamp).TotalDays)
        # A clock moved backwards would otherwise report a negative age, which
        # reads as a retrim in the future rather than as a recent one.
        if ($age -lt 0) { $age = 0 }
        $ages += $age
    }
    if ($ssdVolumes.Count -eq 0) {
        Write-Output 'not_available'
    } elseif ($noRecord) {
        Write-Output 'overdue|never'
    } else {
        $late = @($ages | Where-Object { $_ -ge $thresholdDays })
        if ($late.Count -gt 0) {
            Write-Output ('overdue|{0} days' -f ($late | Measure-Object -Minimum).Minimum)
        } else {
            Write-Output ('ok|{0} days' -f ($ages | Measure-Object -Maximum).Maximum)
        }
    }
"""
)

# One retrim per SSD volume, which is one concept rather than one per drive: the
# user asks for "tell the SSDs what is free again", and a machine whose games
# live on a second volume gains nothing from doing only the system one.
#
# `-Verbose` is redirected onto stdout (`4>&1`) because that stream is where
# `Optimize-Volume` reports its progress, and the streamed apply shows the user
# what is happening during a run measured at 8.4 s and 5.3 s for the two volumes
# of a 1 TB NVMe disk on 2026-09-10. The exit code, not the text, decides the
# verdict: a volume that throws is named in English and collected, and a failure
# anywhere exits non-zero, so a partial run is reported failed rather than done.
_SSD_RETRIM = (
    r"""
    $ErrorActionPreference = 'SilentlyContinue'
"""
    + _SSD_VOLUMES
    + r"""
    if ($ssdVolumes.Count -eq 0) {
        Write-Output 'No SSD volume with a drive letter on this machine'
        exit 1
    }
    $failed = @()
    foreach ($entry in $ssdVolumes) {
        $letter = $entry[0]
        Write-Output ('Retrimming volume {0}:' -f $letter)
        try {
            Optimize-Volume -DriveLetter $letter -ReTrim -Verbose -ErrorAction Stop 4>&1 |
                ForEach-Object { Write-Output ('  {0}' -f $_) }
            Write-Output ('Volume {0}: retrim complete' -f $letter)
        } catch {
            $failed += $letter
            Write-Output ('Volume {0}: retrim failed - {1}' -f $letter, $_.Exception.Message)
        }
    }
    if ($failed.Count -gt 0) {
        Write-Output ('Retrim failed on volume(s): ' + ($failed -join ', '))
        exit 1
    }
    Write-Output 'ok'
"""
)

# One delete for every cleanup whose target is a path, and it is handed the path
# list rather than rebuilding it.
#
# The list comes from `settings/cleanup_targets.py`, which is also what sizes the
# target immediately before and immediately after this runs. That is the point:
# the sizer and the deleter cannot disagree about which folders a cleanup covers,
# because there is one list and both are given it. Every defect in the audit's
# mismatch table was a second copy of a path list drifting from the first - a
# folder counted twice and deleted once, a cache deleted and never counted, a
# subdirectory counted and never deleted.
#
# What is gone from here is as important as what arrived. Each of these scripts
# used to walk its own tree with `Get-ChildItem -Recurse | Measure-Object` before
# and sometimes after the delete, to print a `Cleaned N MB` line that nothing
# parses - measured the slowest of the five sizing methods tried, 5.5 to 9 times
# the cost of the walk it was imitating, and paid twice by three of them.
_PATH_CLEANUP = r"""
    $ErrorActionPreference = 'SilentlyContinue'
    # A separator no Windows path may contain, so the whole list stays one
    # placeholder and the substitution layer escapes it as the single literal it
    # lands in. `cleanup_targets.delete_arguments` refuses a path holding one.
    $paths = @('%paths%' -split '__SPLIT__') | Where-Object { $_ }
    $mode = '%mode%'
    $globs = @('%globs%' -split '__SPLIT__') | Where-Object { $_ }
__PROLOGUE__
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        if ($mode -eq 'directory') {
            # The folder itself goes: the caller's target says so, and its
            # `installed` marker is what keeps the row from reading as
            # uninstalled afterwards.
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
        } elseif ($mode -eq 'top_files') {
            # Files directly inside it and nothing else - no -Recurse, so a
            # subdirectory is neither counted nor removed.
            $items = if ($globs.Count -gt 0) {
                @($globs | ForEach-Object {
                    Get-ChildItem -LiteralPath $path -Filter $_ -File -Force -ErrorAction SilentlyContinue
                })
            } else {
                @(Get-ChildItem -LiteralPath $path -File -Force -ErrorAction SilentlyContinue)
            }
            $items | Remove-Item -Force -ErrorAction SilentlyContinue
        } else {
            # One enumeration of the top level and one -Recurse per entry, never
            # one Remove-Item per file: Temp held 12719 files under 438 entries
            # when that difference timed a cleanup out.
            Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
__EPILOGUE__
    Write-Output "Cleanup ran over $($paths.Count) path(s)"
"""


def _path_cleanup(prologue: str = "", epilogue: str = "") -> str:
    """The shared delete, optionally bracketed by a service stop and start.

    Two cleanups have to stop the service that holds their folder open before it
    can be emptied - Windows Update and Delivery Optimization - and both must
    start it again whatever happened in between.
    """
    return (
        _PATH_CLEANUP.replace("__SPLIT__", _PATH_SPLIT)
        .replace("__PROLOGUE__", prologue)
        .replace("__EPILOGUE__", epilogue)
    )


def _service_cleanup(service: str) -> str:
    """The shared delete with `service` stopped around it."""
    return _path_cleanup(
        prologue=f"    Stop-Service -Name {service} -Force -ErrorAction SilentlyContinue",
        epilogue=f"    Start-Service -Name {service} -ErrorAction SilentlyContinue",
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
    # The cleanup, and nothing else. It used to bracket the run with two
    # AnalyzeComponentStore passes to work out how much it had freed, and those
    # passes are what the wait was made of: measured elevated on the reporting
    # machine, 43.0 s before and 34.7 s after, against a run the user timed at
    # about 108 s end to end. Three quarters of it was measuring.
    #
    # The measuring belongs to the app, not to this script. `_apply_and_finalize`
    # sizes this cleanup's target with the shipped `Get-CleanupStatus` script
    # immediately before the command and immediately again after it, and reports
    # the difference as `freed_bytes` — one instrument, one axis, for every
    # cleanup rather than a bespoke pair of passes inside this one. Computing it
    # here as well would pay for the same readings twice.
    "dism_cleanup": r"""
        Dism.exe /online /Cleanup-Image /StartComponentCleanup /ResetBase
        if ($LASTEXITCODE -ne 0) {
            Write-Output "DISM cleanup failed with exit code $LASTEXITCODE"
            exit 1
        }
        Write-Output 'DISM cleanup completed (reboot may be required for full reclaim)'
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
    "temp_cleanup": _path_cleanup(),
    "nvidia_shader_cleanup": _path_cleanup(),
    "amd_shader_cleanup": _path_cleanup(),
    "intel_shader_cleanup": _path_cleanup(),
    "directx_shader_cleanup": _path_cleanup(),
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
    "battlenet_cache_cleanup": _path_cleanup(),
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
    "wer_cleanup": _path_cleanup(),
    "defender_cache_cleanup": _path_cleanup(),
    # The report that started all of this: this script called Remove-Item once
    # per file, and on a machine with a few thousand .pf entries it ran past the
    # 30 s apply timeout, so the user saw a timeout rather than a refusal and
    # nothing was cleaned. Same two rules as temp_cleanup above — one piped
    # Remove-Item, and a freed figure measured before against after, since
    # Windows keeps some .pf files open and those survive the delete.
    "prefetch_cleanup": _path_cleanup(),
    "browser_cache_cleanup": _path_cleanup(),
    "windows_update_cache_cleanup": _service_cleanup("wuauserv"),
    "delivery_optimization_cleanup": _service_cleanup("dosvc"),
    # Only the cache databases, never the folder: Explorer keeps its own state
    # here. The measured-freed rule matters most on this one — Explorer usually
    # holds these files open, so the old script reported the full cache size as
    # freed on runs that deleted nothing at all.
    "thumbnail_cache_cleanup": _path_cleanup(),
    "memory_dumps_cleanup": _path_cleanup(),
    "discord_cache_cleanup": _path_cleanup(),
    "epic_cache_cleanup": _path_cleanup(),
    "steam_webcache_cleanup": _path_cleanup(),
    "pip_cache_cleanup": _path_cleanup(),
    "npm_cache_cleanup": _path_cleanup(),
    "yarn_cache_cleanup": _path_cleanup(),
    "pnpm_cache_cleanup": _path_cleanup(),
    "nuget_cache_cleanup": _path_cleanup(),
    "maven_cache_cleanup": _path_cleanup(),
    "gradle_cache_cleanup": _path_cleanup(),
    "cargo_cache_cleanup": _path_cleanup(),
    # Maintenance actions
    "sfc_scan": "sfc /scannow",
    "dism_health": "Dism.exe /online /Cleanup-Image /RestoreHealth",
    "ssd_retrim": _SSD_RETRIM,
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
    "mw3_shader_cache_cleanup": _path_cleanup(),
    "mw4_shader_cache_cleanup": _path_cleanup(),
    # Crash reports the Call of Duty launcher writes beside the player config.
    # One directory, shared by every COD title on the machine.
    "cod_crash_reports_cleanup": _path_cleanup(),
    # MW3 crash dump cleanup
    "mw3_crash_cleanup": _path_cleanup(),
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
_CONSTANT_TRUE = "Write-Output $true"

# `maintenance_status` is one detect command over several maintenance actions,
# and they do not all read the same thing. SFC and the DISM health check describe
# a repair that is always available, so their reading is a constant; the SSD
# retrim check has to ask the machine when Windows last optimized each SSD
# volume. The `type` arg picks the script, the same way it picks the folder for
# `cleanup_status` — a table rather than a branch inside one PowerShell script,
# because a branch would make every maintenance reading start a process to reach
# its own literal.
MAINTENANCE_STATUS_SCRIPTS: dict[str, str] = {
    "ssd_trim": _SSD_TRIM_STATUS,
}


def detect_script(cmd_key: str, detect_args: Mapping[str, Any]) -> str | None:
    """The script this detect command runs for these args, or None if it names none.

    One resolution for both callers: the constant short-circuit below asks the
    same question the executor asks before spawning PowerShell, so the two cannot
    come to disagree about what a setting actually runs.
    """
    if cmd_key == "maintenance_status":
        override = MAINTENANCE_STATUS_SCRIPTS.get(str(detect_args.get("type", "")))
        if override is not None:
            return override
    return ACTION_COMMANDS.get(cmd_key)


def constant_status_reading(cmd_key: str, detect_args: Mapping[str, Any]) -> str | None:
    """What this detect prints without being run, or None when it must be run.

    Starting a PowerShell process to learn a literal costs a process and answers
    nothing: measured, three of the twenty-five a cold scan spawned were exactly
    this. Derived from the resolved script rather than from a hand-kept list, so
    a command that stops being constant — one type of `maintenance_status` now
    does — stops being answered here in the same commit that changes it.
    """
    script = detect_script(cmd_key, detect_args)
    if script is not None and script.strip() == _CONSTANT_TRUE:
        return "True"
    return None
