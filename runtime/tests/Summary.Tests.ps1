# Console summary: counts, manual steps, optional sections, en/tr strings (D2/D3).
# Pure functions only: nothing here touches the machine.
BeforeAll {
    . (Join-Path $PSScriptRoot '../Summary.ps1')

    $script:stringsRoot = Join-Path $PSScriptRoot '../strings'
    $script:utf8 = New-Object System.Text.UTF8Encoding($false)

    function script:New-Row([string]$Id, [string]$Class, $Instance) {
        $rowId = if ($null -ne $Instance) { "$Id@$Instance" } else { $Id }
        [pscustomobject]@{ RowId = $rowId; Id = $Id; Instance = $Instance; Label = $null; Class = $Class; Current = $null; Target = $null; Error = $null }
    }

    function script:Read-Strings([string]$Name) {
        [IO.File]::ReadAllText((Join-Path $script:stringsRoot "$Name.json"), $script:utf8) | ConvertFrom-Json
    }

    # 2 already right, 3 will fix (one row has two instances), 1 manual, 1 not applicable,
    # 2 unreadable: 9 states in all.
    $script:rows = @(
        (New-Row 'power:a' 'already-right' $null)
        (New-Row 'power:b' 'already-right' $null)
        (New-Row 'power:c' 'will-fix' $null)
        (New-Row 'network:rss' 'will-fix' 'eth0')
        (New-Row 'network:rss' 'will-fix' 'eth1')
        (New-Row 'hardware:xmp' 'manual' $null)
        (New-Row 'power:d' 'not-applicable' $null)
        (New-Row 'power:e' 'unreadable' $null)
        (New-Row 'network:rss' 'unreadable' 'eth2')
    )
    $script:rowsClean = @($script:rows | Where-Object { $_.Class -ne 'unreadable' -and $_.Class -ne 'not-applicable' })

    $trSteps = 'BIOS ay' + [char]0x0131 + 'n' + [char]0x0131 + ' a' + [char]0x00E7 + '. Bellek profilini etkinle' + [char]0x015F + 'tir. Kaydet.'
    $script:catalogue = @(
        [pscustomobject]@{
            Id   = 'hardware:xmp'
            Data = [pscustomobject]@{
                kind  = 'manual'
                title = [pscustomobject]@{ en = 'Turn on the memory profile'; tr = 'Bellek profilini a' + [char]0x00E7 }
                steps = [pscustomobject]@{ en = 'Open the BIOS. Enable the memory profile. Save.'; tr = $trSteps }
            }
        }
    )

    function script:Get-Text($Lines) { (@($Lines) | ForEach-Object { [string]$_ }) -join "`n" }
}

Describe 'Get-FpsLanguage' {
    It 'returns tr for a Turkish UI culture' {
        Mock Get-UICulture { [Globalization.CultureInfo]::GetCultureInfo('tr-TR') }
        Get-FpsLanguage | Should -Be 'tr'
    }
    It 'returns en for a French UI culture' {
        Mock Get-UICulture { [Globalization.CultureInfo]::GetCultureInfo('fr-FR') }
        Get-FpsLanguage | Should -Be 'en'
    }
    It 'returns en for an English UI culture' {
        Mock Get-UICulture { [Globalization.CultureInfo]::GetCultureInfo('en-US') }
        Get-FpsLanguage | Should -Be 'en'
    }
}

Describe 'Strings files' {
    It 'have identical key sets in en and tr' {
        $enKeys = @((Read-Strings 'en').PSObject.Properties.Name | Sort-Object)
        $trKeys = @((Read-Strings 'tr').PSObject.Properties.Name | Sort-Object)
        $enKeys.Count | Should -BeGreaterThan 0
        ($enKeys -join ',') | Should -Be ($trKeys -join ',')
    }
    It 'have no empty value' {
        foreach ($name in 'en', 'tr') {
            foreach ($p in (Read-Strings $name).PSObject.Properties) { [string]$p.Value | Should -Not -BeNullOrEmpty }
        }
    }
    It 'keep Turkish letters only in tr.json' {
        $enText = [IO.File]::ReadAllText((Join-Path $script:stringsRoot 'en.json'), $script:utf8)
        $trText = [IO.File]::ReadAllText((Join-Path $script:stringsRoot 'tr.json'), $script:utf8)
        $turkish = '[' + [char]0x0131 + [char]0x0130 + [char]0x011F + [char]0x011E + [char]0x015F + [char]0x015E + [char]0x00E7 + [char]0x00C7 + [char]0x00F6 + [char]0x00D6 + [char]0x00FC + [char]0x00DC + ']'
        $enText | Should -Not -MatchExactly $turkish
        $trText | Should -MatchExactly $turkish
    }
}

Describe 'Format-FpsSummary totals' {
    It 'counts every class from the rows (en)' {
        $text = Get-Text (Format-FpsSummary -Rows $script:rows -Language en -Catalogue $script:catalogue)
        $text | Should -Match 'Checked 9 '
        $text | Should -Match 'already right 2'
        $text | Should -Match 'will fix 3'
        $text | Should -Match 'manual 1'
    }
    It 'counts every class from the rows (tr)' {
        $tr = Read-Strings 'tr'
        $expected = [string]::Format([Globalization.CultureInfo]::InvariantCulture, $tr.totals, 9, 2, 3, 1)
        $lines = @(Format-FpsSummary -Rows $script:rows -Language tr -Catalogue $script:catalogue)
        $lines | Should -Contain $expected
    }
    It 'derives the counts, not a fixed number' {
        $one = @(New-Row 'power:a' 'will-fix' $null)
        $text = Get-Text (Format-FpsSummary -Rows $one -Language en)
        $text | Should -Match 'Checked 1 '
        $text | Should -Match 'will fix 1'
        $text | Should -Match 'already right 0'
        $text | Should -Match 'manual 0'
    }
    It 'formats numbers the same under a comma-decimal culture' {
        $old = [Threading.Thread]::CurrentThread.CurrentCulture
        try {
            [Threading.Thread]::CurrentThread.CurrentCulture = New-Object Globalization.CultureInfo('fr-FR')
            $text = Get-Text (Format-FpsSummary -Rows $script:rows -Language en -Catalogue $script:catalogue)
            $text | Should -Match 'Checked 9 '
        }
        finally { [Threading.Thread]::CurrentThread.CurrentCulture = $old }
    }
    It 'returns lines and prints nothing' {
        $out = @(Format-FpsSummary -Rows $script:rows -Language en -Catalogue $script:catalogue 6>&1)
        @($out | Where-Object { $_ -is [System.Management.Automation.InformationRecord] }).Count | Should -Be 0
        $out.Count | Should -BeGreaterThan 2
    }
    It 'handles an empty row set' {
        $text = Get-Text (Format-FpsSummary -Rows @() -Language en)
        $text | Should -Match 'Checked 0 '
    }
}

Describe 'Format-FpsSummary manual rows' {
    It 'shows the steps in English' {
        $text = Get-Text (Format-FpsSummary -Rows $script:rows -Language en -Catalogue $script:catalogue)
        $text | Should -Match 'Open the BIOS\. Enable the memory profile\. Save\.'
        $text | Should -Match 'Turn on the memory profile'
    }
    It 'shows the steps in Turkish and not the English text' {
        $text = Get-Text (Format-FpsSummary -Rows $script:rows -Language tr -Catalogue $script:catalogue)
        $text | Should -Match ('Bellek profilini etkinle' + [char]0x015F + 'tir')
        $text | Should -Not -Match 'Open the BIOS'
    }
    It 'takes steps from the row when it carries them' {
        $row = New-Row 'hardware:xmp' 'manual' $null
        $row | Add-Member -NotePropertyName Steps -NotePropertyValue ([pscustomobject]@{ en = 'Do the thing.'; tr = 'Yap.' })
        (Get-Text (Format-FpsSummary -Rows @($row) -Language en)) | Should -Match 'Do the thing\.'
    }
    It 'names the row id when no steps are known' {
        $text = Get-Text (Format-FpsSummary -Rows @(New-Row 'hardware:xmp' 'manual' $null) -Language en)
        $text | Should -Match 'hardware:xmp'
    }
    It 'omits the manual section at 0' {
        $en = Read-Strings 'en'
        $text = Get-Text (Format-FpsSummary -Rows @(New-Row 'power:a' 'will-fix' $null) -Language en)
        $text | Should -Not -Match ([regex]::Escape($en.manualHeading))
    }
}

Describe 'Format-FpsSummary unreadable and not applicable' {
    It 'is absent at 0' {
        $text = Get-Text (Format-FpsSummary -Rows $script:rowsClean -Language en -Catalogue $script:catalogue)
        $text | Should -Not -Match 'could not be read'
        $text | Should -Not -Match 'do not apply'
    }
    It 'is present with the row ids at more than 0' {
        $text = Get-Text (Format-FpsSummary -Rows $script:rows -Language en -Catalogue $script:catalogue)
        $text | Should -Match 'could not be read'
        $text | Should -Match 'power:e'
        $text | Should -Match 'network:rss@eth2'
        $text | Should -Match '1 do not apply'
    }
    It 'is present in Turkish with the row ids' {
        $text = Get-Text (Format-FpsSummary -Rows $script:rows -Language tr -Catalogue $script:catalogue)
        $text | Should -Match 'power:e'
        $text | Should -Match 'network:rss@eth2'
        $text | Should -Not -Match 'could not be read'
    }
}

Describe 'Format-FpsSummary claims' {
    It 'has no line with a number followed by %, ms or fps' {
        foreach ($lang in 'en', 'tr') {
            foreach ($set in @($script:rows, $script:rowsClean)) {
                foreach ($line in @(Format-FpsSummary -Rows $set -Language $lang -Catalogue $script:catalogue)) {
                    [string]$line | Should -Not -Match '\d\s*(%|ms\b|fps\b)'
                }
            }
        }
    }
}
