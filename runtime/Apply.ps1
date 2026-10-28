# Apply and verify (decision D3, unit U6 of #127).
# Requires Catalogue.ps1 (Invoke-FpsCommand), Detect.ps1 (Get-FpsScalar,
# Test-FpsEqual) and Journal.ps1 to be dot-sourced first. Windows PowerShell
# 5.1 compatible; ASCII only; defines functions only; writes no file.
#
# Only will-fix rows are applied. Before the first write a restore point exists
# (a recent one is reused, otherwise one is created and confirmed). Each row is
# applied, then read again with its detect command (= verify). One failing row
# never stops the others.

function Get-FpsApplyLanguage {
    # tr when the UI culture is Turkish, otherwise en (culture object only).
    if ((Get-UICulture).TwoLetterISOLanguageName -eq 'tr') { 'tr' } else { 'en' }
}

function ConvertTo-FpsRestoreTime {
    # Restore point CreationTime is a DMTF string on Windows PowerShell; accept a datetime too.
    param($Value)
    if ($Value -is [datetime]) { return $Value }
    [Management.ManagementDateTimeConverter]::ToDateTime([string]$Value)
}

function Get-FpsNewestRestorePoint {
    # Newest restore point as @{ Sequence; Time }, or $null when there is none.
    $points = @(Get-ComputerRestorePoint -ErrorAction Stop)
    $best = $null
    foreach ($p in $points) {
        if ($null -eq $p) { continue }
        $item = @{ Sequence = [uint32]$p.SequenceNumber; Time = (ConvertTo-FpsRestoreTime $p.CreationTime) }
        if ($null -eq $best -or $item.Time -gt $best.Time -or ($item.Time -eq $best.Time -and $item.Sequence -gt $best.Sequence)) {
            $best = $item
        }
    }
    $best
}

function Confirm-FpsRestorePoint {
    <#
    .SYNOPSIS
      Makes sure a restore point exists. Returns Ok, Reason, Reused, Sequence, Time.
    .DESCRIPTION
      Newest point under 24 h old: reused. Otherwise Checkpoint-Computer runs
      and success counts only when a newer sequence number then appears.
    #>
    [CmdletBinding()]
    param()

    try {
        $newest = Get-FpsNewestRestorePoint
    }
    catch {
        return [pscustomobject]@{ Ok = $false; Reason = 'restore-point-failed'; Reused = $false; Sequence = $null; Time = $null }
    }
    if ($null -ne $newest) {
        $ageHours = ((Get-Date) - $newest.Time).TotalHours
        if ($ageHours -lt 24 -and $ageHours -ge -1) {
            return [pscustomobject]@{ Ok = $true; Reason = $null; Reused = $true; Sequence = $newest.Sequence; Time = $newest.Time }
        }
    }

    try {
        Checkpoint-Computer -Description 'FpsTune' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop -WarningAction SilentlyContinue | Out-Null
    }
    catch {
        return [pscustomobject]@{ Ok = $false; Reason = 'restore-point-failed'; Reused = $false; Sequence = $null; Time = $null }
    }
    $after = $null
    try {
        $after = Get-FpsNewestRestorePoint
    }
    catch {
        $after = $null
    }
    if ($null -eq $after -or ($null -ne $newest -and $after.Sequence -le $newest.Sequence)) {
        return [pscustomobject]@{ Ok = $false; Reason = 'restore-point-unconfirmed'; Reused = $false; Sequence = $null; Time = $null }
    }
    [pscustomobject]@{ Ok = $true; Reason = $null; Reused = $false; Sequence = $after.Sequence; Time = $after.Time }
}

function Get-FpsApplyOrder {
    <#
    .SYNOPSIS
      Orders states so each runs after the rows its entry names in "after".
    .DESCRIPTION
      Stable: input order is kept where nothing constrains it. A named row that
      is not being applied is ignored. Returns Ordered and Cyclic (states that
      could never become ready).
    #>
    param([object[]]$States)

    $remaining = New-Object 'System.Collections.Generic.List[object]'
    foreach ($s in $States) { $remaining.Add($s) }
    $ordered = New-Object 'System.Collections.Generic.List[object]'

    while ($remaining.Count -gt 0) {
        $pick = -1
        for ($i = 0; $i -lt $remaining.Count; $i++) {
            $state = $remaining[$i]
            $data = $state.Entry.Data
            $after = @()
            if ($data.PSObject.Properties['after']) { $after = @($data.after) }
            $blocked = $false
            foreach ($other in $remaining) {
                if ($other.Id -eq $state.Id) { continue }
                if ($after -contains $other.Id) { $blocked = $true; break }
            }
            if (-not $blocked) { $pick = $i; break }
        }
        if ($pick -lt 0) { break }
        $ordered.Add($remaining[$pick])
        $remaining.RemoveAt($pick)
    }
    [pscustomobject]@{ Ordered = $ordered.ToArray(); Cyclic = $remaining.ToArray() }
}

function New-FpsApplyRow {
    param([string]$RowId, [string]$Status, [string]$Message, [string]$Reason, $Current)
    [pscustomobject]@{
        RowId   = $RowId
        Status  = $Status
        Message = if ($Message) { $Message } else { $null }
        Reason  = if ($Reason) { $Reason } else { $null }
        Current = $Current
    }
}

function Get-FpsFixedText {
    # The row's fixed sentence in the UI language; falls back to en, then to the title.
    param($Entry, [string]$Language)
    $data = $Entry.Data
    foreach ($name in 'fixed', 'title') {
        if (-not $data.PSObject.Properties[$name]) { continue }
        $pair = $data.$name
        foreach ($lang in @($Language, 'en')) {
            $p = $pair.PSObject.Properties[$lang]
            if ($p -and $p.Value) { return [string]$p.Value }
        }
    }
    $Entry.Id
}

function Invoke-FpsApplyRow {
    # Applies and verifies one will-fix state that has an Entry. Returns the result row.
    param($State, $Journal, [string]$Language)

    $data = $State.Entry.Data
    $clock = [Diagnostics.Stopwatch]::StartNew()

    $reason = $null
    $message = $null
    try {
        if (-not $data.PSObject.Properties['apply'] -or -not $data.apply) { throw 'The row has no apply command.' }
        $null = Invoke-FpsCommand -Command $data.apply -Instance $State.Instance -Target $State.Target
    }
    catch {
        $message = $_.Exception.Message
        # A native exit is the typed FpsNativeExit error of Invoke-FpsCommand, never its message text.
        $reason = if ($_.FullyQualifiedErrorId -ceq 'FpsNativeExit') { 'native-exit' } else { 'apply-error' }
    }
    $clock.Stop()
    if ($reason) {
        Add-FpsJournalEntry -Journal $Journal -Id $State.RowId -Phase apply -Outcome failed -DurationMs $clock.ElapsedMilliseconds -Reason $reason
        return New-FpsApplyRow -RowId $State.RowId -Status failed -Message $message -Reason $reason
    }
    Add-FpsJournalEntry -Journal $Journal -Id $State.RowId -Phase apply -Outcome ok -DurationMs $clock.ElapsedMilliseconds

    $clock = [Diagnostics.Stopwatch]::StartNew()
    $read = $null
    $equal = $false
    try {
        $read = Get-FpsScalar -Command $data.detect -Instance $State.Instance -Target $null
        $equal = Test-FpsEqual $read $State.Target
    }
    catch {
        $message = $_.Exception.Message
    }
    $clock.Stop()
    if (-not $equal) {
        if (-not $message) { $message = 'The value read after applying does not match the target.' }
        Add-FpsJournalEntry -Journal $Journal -Id $State.RowId -Phase verify -Outcome failed -DurationMs $clock.ElapsedMilliseconds -Reason 'not-verified'
        return New-FpsApplyRow -RowId $State.RowId -Status failed -Message $message -Reason 'not-verified' -Current $read
    }
    Add-FpsJournalEntry -Journal $Journal -Id $State.RowId -Phase verify -Outcome ok -DurationMs $clock.ElapsedMilliseconds
    New-FpsApplyRow -RowId $State.RowId -Status fixed -Message (Get-FpsFixedText -Entry $State.Entry -Language $Language) -Current $read
}

function Invoke-FpsApply {
    <#
    .SYNOPSIS
      Applies the will-fix rows among detect states, then verifies each.
    .PARAMETER Rows
      States from Get-FpsRowState / Get-FpsState (each carries Entry).
    .OUTPUTS
      Stopped, StopReason, RestorePoint {Reused, SequenceNumber, Time},
      RebootNeeded, Rows {RowId, Status, Message, Reason, Current}, Journal.
    #>
    [CmdletBinding()]
    param([AllowEmptyCollection()][object[]]$Rows = @())

    $language = Get-FpsApplyLanguage
    $journal = New-FpsJournal
    $results = New-Object 'System.Collections.Generic.List[object]'
    $reboot = $false
    $stopped = $false
    $stopReason = $null
    $restore = $null

    $fix = @($Rows | Where-Object { $null -ne $_ -and $_.Class -eq 'will-fix' })
    $runnable = New-Object 'System.Collections.Generic.List[object]'
    foreach ($state in $fix) {
        $hasEntry = $state.PSObject.Properties['Entry'] -and $null -ne $state.Entry -and $null -ne $state.Entry.Data
        if ($hasEntry) {
            $runnable.Add($state)
        }
        else {
            Add-FpsJournalEntry -Journal $journal -Id $state.RowId -Phase apply -Outcome failed -Reason 'no-entry'
            $results.Add((New-FpsApplyRow -RowId $state.RowId -Status failed -Message 'The row has no catalogue entry, so nothing was applied.' -Reason 'no-entry'))
        }
    }

    $order = Get-FpsApplyOrder -States $runnable.ToArray()

    if ($runnable.Count -gt 0) {
        $clock = [Diagnostics.Stopwatch]::StartNew()
        $point = Confirm-FpsRestorePoint
        $clock.Stop()
        if ($point.Ok) {
            Add-FpsJournalEntry -Journal $journal -Id 'restore-point' -Phase restore-point -Outcome ok -DurationMs $clock.ElapsedMilliseconds
            $restore = [pscustomobject]@{ Reused = $point.Reused; SequenceNumber = $point.Sequence; Time = $point.Time }
        }
        else {
            Add-FpsJournalEntry -Journal $journal -Id 'restore-point' -Phase restore-point -Outcome failed -DurationMs $clock.ElapsedMilliseconds -Reason $point.Reason
            $stopped = $true
            $stopReason = $point.Reason
        }
    }

    if ($stopped) {
        foreach ($state in $runnable) {
            $results.Add((New-FpsApplyRow -RowId $state.RowId -Status skipped -Message 'Nothing was applied because no restore point could be made.' -Reason $stopReason))
        }
    }
    else {
        foreach ($state in $order.Ordered) {
            $row = Invoke-FpsApplyRow -State $state -Journal $journal -Language $language
            $results.Add($row)
            if ($row.Status -eq 'fixed' -and $state.Entry.Data.PSObject.Properties['restart'] -and $state.Entry.Data.restart -eq 'reboot') {
                $reboot = $true
            }
        }
        foreach ($state in $order.Cyclic) {
            Add-FpsJournalEntry -Journal $journal -Id $state.RowId -Phase apply -Outcome failed -Reason 'after-cycle'
            $results.Add((New-FpsApplyRow -RowId $state.RowId -Status failed -Message 'The "after" order of this row can never be satisfied.' -Reason 'after-cycle'))
        }
    }

    [pscustomobject]@{
        Stopped      = $stopped
        StopReason   = $stopReason
        RestorePoint = $restore
        RebootNeeded = $reboot
        Rows         = $results.ToArray()
        Journal      = $journal.ToArray()
    }
}
