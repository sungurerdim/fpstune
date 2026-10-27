# Summary: the console screen after detect (decisions D2/D3).
# Windows PowerShell 5.1 compatible; defines functions only. ASCII only: all
# user text lives in strings/en.json and strings/tr.json (UTF-8, read explicitly).
#
# Format-FpsSummary is pure: it returns lines and prints nothing. It states
# counts and steps only: no percentages and no numeric gain claims (C11).

$script:FpsStringsRoot = Join-Path $PSScriptRoot 'strings'

function Get-FpsLanguage {
    <#
    .SYNOPSIS
      'tr' when the UI culture is Turkish, otherwise 'en'. Culture object only.
    #>
    if ((Get-UICulture).TwoLetterISOLanguageName -eq 'tr') { 'tr' } else { 'en' }
}

function Get-FpsStrings {
    <#
    .SYNOPSIS
      Reads strings/<language>.json as UTF-8 (5.1 would read a BOM-less file as ANSI).
    #>
    param([ValidateSet('en', 'tr')][string]$Language = 'en')
    $path = Join-Path $script:FpsStringsRoot "$Language.json"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::ReadAllText($path, $utf8) | ConvertFrom-Json
}

function Get-FpsLocalText {
    # Picks the {en,tr} text for a language; falls back to en, then to nothing.
    param($Pair, [string]$Language)
    if ($null -eq $Pair) { return $null }
    $p = $Pair.PSObject.Properties[$Language]
    if ($p -and $p.Value) { return [string]$p.Value }
    $p = $Pair.PSObject.Properties['en']
    if ($p -and $p.Value) { return [string]$p.Value }
    $null
}

function Get-FpsEntryField {
    # {en,tr} pair for a state: its own Title / Steps property, else the field on state.Entry.Data.
    param($State, [ValidateSet('title', 'steps')][string]$Name)
    $own = $State.PSObject.Properties[$(if ($Name -eq 'title') { 'Title' } else { 'Steps' })]
    if ($own) { return $own.Value }
    $entry = $State.PSObject.Properties['Entry']
    if ($entry -and $entry.Value -and $entry.Value.Data) {
        $field = $entry.Value.Data.PSObject.Properties[$Name]
        if ($field) { return $field.Value }
    }
    $null
}

function Format-FpsSummary {
    <#
    .SYNOPSIS
      Returns the summary lines for a set of detect results.
    .PARAMETER Rows
      States from Get-FpsRowState / Get-FpsState (Class, RowId, Id, Entry).
      Titles and steps come from state.Entry (the catalogue entry), or from
      Title / Steps properties on the state itself.
    .PARAMETER Language
      en or tr.
    #>
    [CmdletBinding()]
    param(
        [AllowEmptyCollection()][object[]]$Rows = @(),
        [ValidateSet('en', 'tr')][string]$Language = 'en'
    )

    $s = Get-FpsStrings -Language $Language
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $Rows = @($Rows | Where-Object { $null -ne $_ })

    $right = @($Rows | Where-Object { $_.Class -eq 'already-right' })
    $fix = @($Rows | Where-Object { $_.Class -eq 'will-fix' })
    $manual = @($Rows | Where-Object { $_.Class -eq 'manual' })
    $unreadable = @($Rows | Where-Object { $_.Class -eq 'unreadable' })
    $notApplicable = @($Rows | Where-Object { $_.Class -eq 'not-applicable' })

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add([string]::Format($inv, $s.totals, $Rows.Count, $right.Count, $fix.Count, $manual.Count))

    if ($manual.Count -gt 0) {
        $lines.Add('')
        $lines.Add($s.manualHeading)
        foreach ($row in $manual) {
            $title = Get-FpsLocalText -Pair (Get-FpsEntryField -State $row -Name 'title') -Language $Language
            $steps = Get-FpsLocalText -Pair (Get-FpsEntryField -State $row -Name 'steps') -Language $Language

            $name = if ($title) { $title } else { $row.RowId }
            $lines.Add("- $name")
            if ($steps) {
                $lines.Add("  $($s.manualSteps) $steps")
            }
            else {
                $lines.Add("  $($s.manualNoSteps)")
            }
        }
    }

    if ($unreadable.Count -gt 0) {
        $names = @($unreadable | ForEach-Object {
                $title = Get-FpsLocalText -Pair (Get-FpsEntryField -State $_ -Name 'title') -Language $Language
                if ($title) { "$title ($($_.RowId))" } else { [string]$_.RowId }
            }) -join ', '
        $format = if ($unreadable.Count -eq 1) { $s.unreadableOne } else { $s.unreadableMany }
        $lines.Add('')
        $lines.Add([string]::Format($inv, $format, $unreadable.Count, $names))
    }

    if ($notApplicable.Count -gt 0) {
        $format = if ($notApplicable.Count -eq 1) { $s.notApplicableOne } else { $s.notApplicableMany }
        $lines.Add([string]::Format($inv, $format, $notApplicable.Count))
    }

    $lines.ToArray()
}

function Show-FpsSummary {
    <#
    .SYNOPSIS
      Prints the summary lines. The only function here that writes to the host.
    #>
    param(
        [AllowEmptyCollection()][object[]]$Rows = @(),
        [string]$Language
    )
    if (-not $Language) { $Language = Get-FpsLanguage }
    foreach ($line in @(Format-FpsSummary -Rows $Rows -Language $Language)) {
        Write-Host $line
    }
}
