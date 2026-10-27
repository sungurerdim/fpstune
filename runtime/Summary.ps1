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

function Format-FpsSummary {
    <#
    .SYNOPSIS
      Returns the summary lines for a set of detect results.
    .PARAMETER Rows
      States from Get-FpsRowState / Get-FpsState (Class, RowId, Id).
    .PARAMETER Language
      en or tr.
    .PARAMETER Catalogue
      Optional catalogue rows (Get-FpsCatalogue). Manual rows take title and
      steps from here, or from Title / Steps properties on the state itself.
    #>
    [CmdletBinding()]
    param(
        [AllowEmptyCollection()][object[]]$Rows = @(),
        [ValidateSet('en', 'tr')][string]$Language = 'en',
        [object[]]$Catalogue = @()
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
            $entry = $Catalogue | Where-Object { $_.Id -eq $row.Id } | Select-Object -First 1
            $data = if ($entry) { $entry.Data } else { $null }

            $titlePair = if ($row.PSObject.Properties['Title']) { $row.Title } elseif ($data -and $data.PSObject.Properties['title']) { $data.title } else { $null }
            $stepsPair = if ($row.PSObject.Properties['Steps']) { $row.Steps } elseif ($data -and $data.PSObject.Properties['steps']) { $data.steps } else { $null }
            $title = Get-FpsLocalText -Pair $titlePair -Language $Language
            $steps = Get-FpsLocalText -Pair $stepsPair -Language $Language

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
        $ids = @($unreadable | ForEach-Object { $_.RowId }) -join ', '
        $lines.Add('')
        $lines.Add([string]::Format($inv, $s.unreadable, $unreadable.Count, $ids))
    }

    if ($notApplicable.Count -gt 0) {
        $lines.Add([string]::Format($inv, $s.notApplicable, $notApplicable.Count))
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
        [string]$Language,
        [object[]]$Catalogue = @()
    )
    if (-not $Language) { $Language = Get-FpsLanguage }
    foreach ($line in @(Format-FpsSummary -Rows $Rows -Language $Language -Catalogue $Catalogue)) {
        Write-Host $line
    }
}
