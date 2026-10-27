# Journal: the in-memory record of one apply run (decision D3).
# Windows PowerShell 5.1 compatible; ASCII only; defines functions only.
#
# Memory only: nothing here writes a file. An entry names what happened and how
# long it took, never a setting value. Reason is a class (apply-error,
# native-exit, not-verified, no-entry, ...), never free text from a command.

function New-FpsJournal {
    <#
    .SYNOPSIS
      Returns an empty journal (a list the entries are added to).
    #>
    , (New-Object 'System.Collections.Generic.List[object]')
}

function Add-FpsJournalEntry {
    <#
    .SYNOPSIS
      Adds one entry: Id, Phase, Outcome, DurationMs, Reason.
    .PARAMETER Phase
      restore-point, apply or verify.
    .PARAMETER Outcome
      ok or failed.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Journal,
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][ValidateSet('restore-point', 'apply', 'verify')][string]$Phase,
        [Parameter(Mandatory)][ValidateSet('ok', 'failed')][string]$Outcome,
        [long]$DurationMs = 0,
        [string]$Reason
    )
    $Journal.Add([pscustomobject]@{
            Id         = $Id
            Phase      = $Phase
            Outcome    = $Outcome
            DurationMs = $DurationMs
            Reason     = if ($Reason) { $Reason } else { $null }
        })
}
