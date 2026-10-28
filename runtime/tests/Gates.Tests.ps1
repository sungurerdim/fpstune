# Catalogue gate runtime/gate.ps1 (decisions D4 and D7 G2/G3).
#
# Contract pinned here:
#   powershell -NoProfile -File runtime/gate.ps1 [-Root <root>]
# <root> holds tweaks/<category>/<name>.json and runtime/*.ps1 (the repository
# root by default). Exit code 0 on a clean root, non-zero on any finding, and
# one line per finding: "<rule-id> <file>: <reason>".
#
# Every case starts from a copy of fixtures/gate/clean in TestDrive and lays
# one rule's overlay folder (fixtures/gate/<rule>) on top, so a red case differs
# from the green catalogue by its one violation only. Turkish letters and the C9
# machine literals never appear in this file or in a committed fixture: they are
# built from code points or from parts at run time and replace a __TOKEN__.
BeforeAll {
    $script:gate = Join-Path (Split-Path -Parent $PSScriptRoot) 'gate.ps1'
    $script:repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $script:fixtures = Join-Path $PSScriptRoot 'fixtures/gate'
    $script:utf8 = New-Object Text.UTF8Encoding($false)

    # The C4 letters, from code points: c-cedilla, g-breve, dotless i, dotted I,
    # o-umlaut, s-cedilla, u-umlaut and the upper-case c, g, o, s, u forms.
    $script:turkishCodes = @(0x00E7, 0x011F, 0x0131, 0x0130, 0x00F6, 0x015F, 0x00FC, 0x00C7, 0x011E, 0x00D6, 0x015E, 0x00DC)
    $script:turkish = -join ($script:turkishCodes | ForEach-Object { [char]$_ })

    function script:Copy-Tree([string]$From, [string]$To) {
        $fromFull = (Resolve-Path -LiteralPath $From).ProviderPath.TrimEnd('\', '/')
        $copied = @()
        foreach ($file in Get-ChildItem -LiteralPath $fromFull -Recurse -File) {
            $relative = $file.FullName.Substring($fromFull.Length + 1)
            $destination = Join-Path $To $relative
            $folder = Split-Path -Parent $destination
            if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
            Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
            $copied += $destination
        }
        $copied
    }

    function script:ConvertTo-JsonText([string]$Value) {
        $Value.Replace('\', '\\').Replace('"', '\"')
    }

    # Clean catalogue + optional overlay, tokens replaced in the overlay files,
    # then extra files written (UTF-8, no BOM) and listed paths removed.
    function script:New-GateRoot {
        param(
            [string]$Overlay,
            [hashtable]$Tokens = @{},
            [hashtable]$Files = @{},
            [string[]]$Remove = @()
        )
        $root = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $root | Out-Null
        Copy-Tree -From (Join-Path $script:fixtures 'clean') -To $root | Out-Null
        if ($Overlay) {
            foreach ($path in (Copy-Tree -From (Join-Path $script:fixtures $Overlay) -To $root)) {
                $text = [IO.File]::ReadAllText($path, $script:utf8)
                foreach ($key in $Tokens.Keys) {
                    $value = [string]$Tokens[$key]
                    if ($path -like '*.json') { $value = ConvertTo-JsonText $value }
                    $text = $text.Replace($key, $value)
                }
                [IO.File]::WriteAllText($path, $text, $script:utf8)
            }
        }
        foreach ($relative in $Files.Keys) {
            $path = Join-Path $root $relative
            $folder = Split-Path -Parent $path
            if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
            $content = $Files[$relative]
            if ($content -is [byte[]]) { [IO.File]::WriteAllBytes($path, $content) }
            else { [IO.File]::WriteAllText($path, [string]$content, $script:utf8) }
        }
        foreach ($relative in $Remove) { Remove-Item -LiteralPath (Join-Path $root $relative) -Force }
        $root
    }

    # Parse one tweak file of a root, let $Edit change it, write it back.
    function script:Edit-GateJson([string]$Root, [string]$Relative, [scriptblock]$Edit) {
        $path = Join-Path $Root $Relative
        $data = [IO.File]::ReadAllText($path, $script:utf8) | ConvertFrom-Json
        & $Edit $data
        [IO.File]::WriteAllText($path, ($data | ConvertTo-Json -Depth 20), $script:utf8)
    }

    function script:Set-Field($Object, [string]$Name, $Value) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
    }

    function script:Invoke-Gate([string]$Root) {
        if (-not (Test-Path -LiteralPath $script:gate)) {
            throw "runtime/gate.ps1 does not exist: the catalogue gate is not implemented yet."
        }
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script:gate)
        if ($Root) { $arguments += @('-Root', $Root) }
        $output = @(& powershell.exe @arguments 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
        $findings = @(foreach ($line in $output) {
                if ($line -cmatch '^(?<rule>[A-Z]+[0-9]+) (?<file>.+?): (?<reason>\S.*)$') {
                    [pscustomobject]@{ Rule = $Matches.rule; File = $Matches.file; Leaf = (Split-Path -Leaf $Matches.file); Line = $line }
                }
            })
        [pscustomobject]@{ ExitCode = $code; Output = $output; Findings = $findings; Text = ($output -join [Environment]::NewLine) }
    }

    # Red: non-zero exit, the rule names the expected file, and no other rule fires.
    function script:Assert-Finding($Result, [string]$Rule, [string]$Leaf) {
        $Result.ExitCode | Should -Not -Be 0 -Because $Result.Text
        @($Result.Findings | Where-Object { $_.Rule -eq $Rule -and $_.Leaf -eq $Leaf }).Count | Should -BeGreaterThan 0 -Because "a '${Rule} ${Leaf}: <reason>' line is expected in:`n$($Result.Text)"
        @($Result.Findings | Where-Object { $_.Rule -ne $Rule }).Count | Should -Be 0 -Because "the fixture breaks $Rule only:`n$($Result.Text)"
    }

    # Green: exit 0 and no finding line at all.
    function script:Assert-Clean($Result) {
        @($Result.Findings).Count | Should -Be 0 -Because $Result.Text
        $Result.ExitCode | Should -Be 0 -Because $Result.Text
    }
}

Describe 'gate.ps1 on the clean catalogue' {
    It 'exits 0 with no finding' {
        Assert-Clean (Invoke-Gate -Root (New-GateRoot))
    }

    It 'C4: allows Turkish letters in tr fields and in runtime/strings/tr.json' {
        $root = New-GateRoot -Overlay 'c4_ok' -Tokens @{ '__TR__' = $script:turkish }
        Assert-Clean (Invoke-Gate -Root $root)
    }

    It 'C8: allows several registry writes when the tweak names a compound' {
        $root = New-GateRoot -Overlay 'c8'
        Edit-GateJson $root 'tweaks/test/two_writes.json' { param($d) Set-Field $d 'compound' 'mouse_acceleration' }
        Assert-Clean (Invoke-Gate -Root $root)
    }
}

Describe 'LN1 native exe output never feeds detect/applicable/target/instances' {
    It 'reports <File> (<Form>)' -ForEach @(
        @{ File = 'assigned.json'; Form = 'assigned in detect' }
        @{ File = 'piped.json'; Form = 'piped in applicable' }
        @{ File = 'expression.json'; Form = 'expression in target.command' }
        @{ File = 'instances.json'; Form = 'piped in instances' }
    ) {
        $root = New-GateRoot -Overlay 'ln1' -Remove @(
            @('assigned.json', 'piped.json', 'expression.json', 'instances.json') |
                Where-Object { $_ -ne $File } | ForEach-Object { "tweaks/test/$_" })
        Assert-Finding (Invoke-Gate -Root $root) 'LN1' $File
    }

    It 'reports detect = <Command>' -ForEach @(
        @{ Command = '$s = & netsh.exe interface teredo show state; [string]$s.Count' }
        @{ Command = '"$(powercfg /getactivescheme)".Length.ToString()' }
    ) {
        $root = New-GateRoot -Overlay 'ln1' -Remove @('tweaks/test/piped.json', 'tweaks/test/expression.json', 'tweaks/test/instances.json')
        Edit-GateJson $root 'tweaks/test/assigned.json' { param($d) Set-Field $d 'detect' $Command }
        Assert-Finding (Invoke-Gate -Root $root) 'LN1' 'assigned.json'
    }
}

Describe 'LN2 human-text properties are never compared or parsed' {
    It 'reports the committed fixture (-clike on InterfaceDescription)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'ln2')) 'LN2' 'text_compare.json'
    }

    It 'reports <Field> = <Command>' -ForEach @(
        @{ Field = 'detect'; Command = '[string]@(Get-PnpDevice -Class Net | Where-Object { $_.FriendlyName -eq ''Ethernet'' }).Count' }
        @{ Field = 'detect'; Command = '[string]((Get-Service -Name Spooler).DisplayName -ne ''Print Spooler'')' }
        @{ Field = 'detect'; Command = '[string]((Get-CimInstance -ClassName Win32_OperatingSystem).Caption -match ''Pro'')' }
        @{ Field = 'detect'; Command = '[string]((Get-NetAdapterAdvancedProperty -Name ''*'').DisplayValue -contains ''Enabled'')' }
        @{ Field = 'detect'; Command = '[string](''Wired'' -in (Get-CimInstance -ClassName Win32_NetworkAdapter).Description)' }
        @{ Field = 'detect'; Command = '((Get-CimInstance -ClassName Win32_VideoController).Caption -split '' '')[0]' }
        @{ Field = 'detect'; Command = '(Get-WinEvent -LogName System -MaxEvents 1).Message -replace ''\s'', ''''' }
        @{ Field = 'detect'; Command = '[string]((Get-WinEvent -LogName System -MaxEvents 1).Message | Select-String -Pattern ''error'' -Quiet)' }
        @{ Field = 'detect'; Command = '[string](Select-String -InputObject (Get-CimInstance -ClassName Win32_OperatingSystem).Caption -Pattern ''Pro'' -Quiet)' }
        @{ Field = 'apply'; Command = '$a = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match ''Realtek'' }; Set-NetAdapterRss -Name $a.Name -Enabled $true' }
    ) {
        $root = New-GateRoot -Overlay 'ln2'
        Edit-GateJson $root 'tweaks/test/text_compare.json' {
            param($d)
            if ($Field -ne 'detect') { Set-Field $d 'detect' '[string](Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value' }
            Set-Field $d $Field $Command
        }
        Assert-Finding (Invoke-Gate -Root $root) 'LN2' 'text_compare.json'
    }
}

Describe 'LN3 every command parses' {
    BeforeAll {
        $script:broken = '[string](Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value).Value)'
        $script:valid = '[string](Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value'
    }

    It 'reports the committed fixture (detect)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'ln3')) 'LN3' 'broken.json'
    }

    It 'reports a broken <Field>' -ForEach @(
        @{ Field = 'applicable' }
        @{ Field = 'instances' }
        @{ Field = 'target.command' }
        @{ Field = 'apply' }
        @{ Field = 'revert' }
        @{ Field = 'detect (unclosed brace)' }
    ) {
        $root = New-GateRoot -Overlay 'ln3'
        Edit-GateJson $root 'tweaks/test/broken.json' {
            param($d)
            Set-Field $d 'detect' $script:valid
            switch ($Field) {
                'target.command' { Set-Field $d 'target' ([pscustomobject]@{ command = $script:broken }) }
                'detect (unclosed brace)' { Set-Field $d 'detect' 'if ($true) { ''1''' }
                default { Set-Field $d $Field $script:broken }
            }
        }
        Assert-Finding (Invoke-Gate -Root $root) 'LN3' 'broken.json'
    }
}

Describe 'LN4 no case-insensitive pattern with an ASCII letter range or an i' {
    # The third locale defect class (after LN1 and LN2): -match, -notmatch,
    # -like, -notlike, -replace, -split (and their i- forms) and Select-String
    # without -CaseSensitive fold case by the thread culture, so under tr-TR
    # 'I' -match '[A-Z]' is False and 'I' -like 'i*' is False. In runtime/*.ps1
    # and in every command field, such a pattern holding an ASCII letter range
    # or the letter i/I is a finding; the c- forms and -CaseSensitive are allowed.
    BeforeAll {
        $script:ln4Valid = '[string](Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value'
        function script:New-Ln4Runtime([string]$Line) {
            "# Gate fixture: one runtime pattern line for LN4.`r`nfunction Test-FixtureName([string]`$Name) {`r`n    $Line`r`n}`r`n"
        }
    }

    It 'reports the committed tweak fixture (-match ''^[A-Z]+$'' in detect)' {
        $root = New-GateRoot -Overlay 'ln4' -Remove @('runtime/Matcher.ps1')
        Assert-Finding (Invoke-Gate -Root $root) 'LN4' 'case_fold.json'
    }

    It 'reports the committed runtime fixture (-like ''id_*'')' {
        $root = New-GateRoot -Overlay 'ln4' -Remove @('tweaks/test/case_fold.json')
        Assert-Finding (Invoke-Gate -Root $root) 'LN4' 'Matcher.ps1'
    }

    It 'reports <Field> = <Command>' -ForEach @(
        @{ Field = 'detect'; Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -notmatch ''[a-f0-9]'')' }
        @{ Field = 'detect'; Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -match "^[A-Z]")' }
        @{ Field = 'detect'; Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -like ''*I*'')' }
        @{ Field = 'detect'; Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -notlike ''min*'')' }
        @{ Field = 'detect'; Command = '(Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -replace ''i'', ''''' }
        @{ Field = 'detect'; Command = '((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -split ''[A-Z]'')[0]' }
        @{ Field = 'detect'; Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -imatch ''min'')' }
        @{ Field = 'detect'; Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value | Select-String -Pattern ''id'' -Quiet)' }
        @{ Field = 'detect'; Command = '[string](Select-String -InputObject (Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value ''[a-z]'' -Quiet)' }
        @{ Field = 'applicable'; Command = '[bool]($env:PROCESSOR_ARCHITECTURE -match ''^[A-Z]'')' }
        @{ Field = 'instances'; Command = 'Get-ChildItem -Path ''HKCU:\Software\FpsTuneFixture'' | Where-Object { $_.PSChildName -like ''Item*'' } | ForEach-Object { [pscustomobject]@{ id = $_.PSChildName; label = $_.PSChildName } }' }
        @{ Field = 'target.command'; Command = '[string](''A1'' -replace ''[A-Z]'', '''')' }
        @{ Field = 'apply'; Command = 'if ($Target -match ''i'') { Set-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -Value $Target }' }
        @{ Field = 'revert'; Command = 'if ($Target -notlike ''*I*'') { Remove-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction SilentlyContinue }' }
    ) {
        $root = New-GateRoot -Overlay 'ln4' -Remove @('runtime/Matcher.ps1')
        Edit-GateJson $root 'tweaks/test/case_fold.json' {
            param($d)
            Set-Field $d 'detect' $script:ln4Valid
            if ($Field -eq 'target.command') { Set-Field $d 'target' ([pscustomobject]@{ command = $Command }) }
            else { Set-Field $d $Field $Command }
        }
        Assert-Finding (Invoke-Gate -Root $root) 'LN4' 'case_fold.json'
    }

    It 'reports the runtime line <Line>' -ForEach @(
        @{ Line = '$Name -match ''^[A-Z]''' }
        @{ Line = '$Name -notmatch ''(?i)\.exe$''' }
        @{ Line = '$Name -notlike ''*I''' }
        @{ Line = '$Name -replace ''[a-z]'', ''''' }
        @{ Line = '$Name -split ''i''' }
        @{ Line = '$Name -imatch ''min''' }
        @{ Line = '$Name | Select-String -Pattern ''id'' -Quiet' }
        @{ Line = 'sls -InputObject $Name -Pattern ''[A-F]'' -Quiet' }
        @{ Line = '$Name -cmatch ''(?i)^abc''' }
        @{ Line = '$Name -cnotmatch ''(?i:abc)''' }
        @{ Line = '$Name -creplace ''(?mi)a'', ''''' }
        @{ Line = '$Name -csplit ''(?i)x''' }
        @{ Line = 'switch -Regex ($Name) { ''^[A-Z]'' { 1 } }' }
        @{ Line = 'switch -Wildcard ($Name) { ''id_*'' { 1 } }' }
        @{ Line = 'switch -Regex -File $Name { ''^[a-f]'' { 1 } }' }
        @{ Line = 'switch -Regex -CaseSensitive ($Name) { ''(?i)^abc'' { 1 } }' }
    ) {
        $root = New-GateRoot -Files @{ 'runtime/Matcher.ps1' = (New-Ln4Runtime $Line) }
        Assert-Finding (Invoke-Gate -Root $root) 'LN4' 'Matcher.ps1'
    }

    It 'allows detect = <Command>' -ForEach @(
        @{ Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -cmatch ''^[A-Z]+$'')' }
        @{ Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -cnotmatch ''[a-f0-9]'')' }
        @{ Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -clike ''*I*'')' }
        @{ Command = '(Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -creplace ''i'', ''''' }
        @{ Command = '((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -csplit ''[A-Z]'')[0]' }
        @{ Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value | Select-String -Pattern ''id'' -CaseSensitive -Quiet)' }
        @{ Command = '[string]((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -match ''^\d+$'')' }
        @{ Command = '((Get-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name Value -ErrorAction Stop).Value -split '','')[0]' }
    ) {
        $root = New-GateRoot -Overlay 'ln4' -Remove @('runtime/Matcher.ps1')
        Edit-GateJson $root 'tweaks/test/case_fold.json' { param($d) Set-Field $d 'detect' $Command }
        Assert-Clean (Invoke-Gate -Root $root)
    }

    It 'allows the runtime line <Line>' -ForEach @(
        @{ Line = '$Name -cmatch ''^[A-Z]''' }
        @{ Line = '$Name -clike ''id_*''' }
        @{ Line = '$Name -creplace ''[a-z]'', ''''' }
        @{ Line = '$Name -csplit ''i''' }
        @{ Line = '$Name | Select-String -Pattern ''id'' -CaseSensitive -Quiet' }
        @{ Line = '$Name -split ''[\\/]''' }
        @{ Line = '$Name -replace ''\s+'', '' ''' }
        @{ Line = '$Name -cmatch ''(?-i)^abc''' }
        @{ Line = '$Name -cmatch ''^[A-Z]+$''' }
        @{ Line = 'switch -Regex -CaseSensitive ($Name) { ''^[A-Z]'' { 1 } }' }
        @{ Line = 'switch -Wildcard -CaseSensitive ($Name) { ''id_*'' { 1 } }' }
        @{ Line = 'switch -Regex ($Name) { ''^\d+$'' { 1 } }' }
        @{ Line = 'switch ($Name) { ''abc'' { 1 } }' }
    ) {
        $root = New-GateRoot -Files @{ 'runtime/Matcher.ps1' = (New-Ln4Runtime $Line) }
        Assert-Clean (Invoke-Gate -Root $root)
    }
}

Describe 'C4 Turkish letters only in tr fields and runtime/strings/tr.json' {
    It 'reports U+<Hex> in a title.en' -ForEach @(
        foreach ($code in @(0x00E7, 0x011F, 0x0131, 0x0130, 0x00F6, 0x015F, 0x00FC, 0x00C7, 0x011E, 0x00D6, 0x015E, 0x00DC)) {
            @{ Code = $code; Hex = $code.ToString('X4') }
        }
    ) {
        $root = New-GateRoot -Overlay 'c4' -Tokens @{ '__TR_JSON__' = "x$([char]$Code)x"; '__TR_CMD__' = 'FpsTuneFixture'; '__TR_PS1__' = 'hello' }
        Assert-Finding (Invoke-Gate -Root $root) 'C4' 'en_text.json'
    }

    It 'reports Turkish letters inside a command' {
        $root = New-GateRoot -Overlay 'c4' -Tokens @{ '__TR_JSON__' = 'Fixture'; '__TR_CMD__' = $script:turkish; '__TR_PS1__' = 'hello' }
        Assert-Finding (Invoke-Gate -Root $root) 'C4' 'en_text.json'
    }

    It 'reports Turkish letters in a runtime .ps1 file' {
        $root = New-GateRoot -Overlay 'c4' -Tokens @{ '__TR_JSON__' = 'Fixture'; '__TR_CMD__' = 'FpsTuneFixture'; '__TR_PS1__' = $script:turkish }
        # Written with a BOM so Windows PowerShell 5.1 itself would read it right.
        $helper = Join-Path $root 'runtime/Helper.ps1'
        [IO.File]::WriteAllText($helper, [IO.File]::ReadAllText($helper, $script:utf8), (New-Object Text.UTF8Encoding($true)))
        Assert-Finding (Invoke-Gate -Root $root) 'C4' 'Helper.ps1'
    }
}

Describe 'C8 one registry write per tweak unless it names a compound' {
    It 'reports the committed fixture (Set-ItemProperty + New-ItemProperty)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'c8')) 'C8' 'two_writes.json'
    }

    It 'reports apply = <Apply>' -ForEach @(
        @{ Apply = 'reg add HKCU\Software\FpsTuneFixture /v A /t REG_DWORD /d 1 /f; reg add HKCU\Software\FpsTuneFixture /v B /t REG_DWORD /d 1 /f' }
        @{ Apply = 'Set-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name A -Value $Target; Set-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name B -Value $Target' }
        @{ Apply = 'Set-ItemProperty -Path ''HKCU:\Software\FpsTuneFixture'' -Name A -Value $Target; reg add HKCU\Software\FpsTuneFixture /v B /t REG_DWORD /d 1 /f' }
    ) {
        $root = New-GateRoot -Overlay 'c8'
        Edit-GateJson $root 'tweaks/test/two_writes.json' { param($d) Set-Field $d 'apply' $Apply }
        Assert-Finding (Invoke-Gate -Root $root) 'C8' 'two_writes.json'
    }
}

Describe 'C9 no machine literal in any command' {
    # Each literal is joined from parts here so this file never contains it.
    It 'reports the <Name> literal' -ForEach @(
        @{ Name = 'monitor model'; Parts = @('Q25G4', 'S') }
        @{ Name = 'account id'; Parts = @('41613607', '3') }
        @{ Name = 'user library folder'; Parts = @('Oyunla', 'r') }
        @{ Name = 'GPU model'; Parts = @('RTX 307', '0') }
        @{ Name = 'CPU model'; Parts = @('i7-11800', 'H') }
        @{ Name = 'user profile path'; Parts = @('C:\', 'Users', '\', 'alice\AppData\Local') }
        @{ Name = 'drive-letter Steam library'; Parts = @('D:\', 'SteamLibrary\steamapps\common\Game') }
        @{ Name = 'drive-letter game library'; Parts = @('E:\', 'Games\Battle.net') }
    ) {
        $root = New-GateRoot -Overlay 'c9' -Tokens @{ '__C9__' = (-join $Parts) }
        Assert-Finding (Invoke-Gate -Root $root) 'C9' 'machine.json'
    }
}

Describe 'C11 no number with %, ms or fps in why or fixed' {
    It 'reports the committed fixture (why.en with %)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'c11')) 'C11' 'claim.json'
    }

    It 'reports <Field>.<Lang> = <Text>' -ForEach @(
        @{ Field = 'why'; Lang = 'en'; Text = 'Games run about 10 % faster.' }
        @{ Field = 'why'; Lang = 'en'; Text = 'Input reaches the game 5 ms sooner.' }
        @{ Field = 'why'; Lang = 'en'; Text = 'Input reaches the game 5ms sooner.' }
        @{ Field = 'why'; Lang = 'en'; Text = 'Frames arrive 2.5 ms sooner.' }
        @{ Field = 'why'; Lang = 'en'; Text = 'Games gain about 30 fps.' }
        @{ Field = 'why'; Lang = 'tr'; Text = 'Oyun %10 daha hizli calisir.' }
        @{ Field = 'fixed'; Lang = 'en'; Text = 'Input now arrives 20 ms sooner.' }
        @{ Field = 'fixed'; Lang = 'tr'; Text = 'Oyun artik 30 fps daha hizli.' }
    ) {
        $root = New-GateRoot -Overlay 'c11'
        Edit-GateJson $root 'tweaks/test/claim.json' {
            param($d)
            $d.why.en = 'C11 fixture: the copy claims no number.'
            Set-Field $d.$Field $Lang $Text
        }
        Assert-Finding (Invoke-Gate -Root $root) 'C11' 'claim.json'
    }
}

Describe 'ID1 the path forms a valid id' {
    It 'reports the committed fixture (upper case name)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'id1')) 'ID1' 'CpuBoost.json'
    }

    It 'reports <Relative>' -ForEach @(
        @{ Relative = 'tweaks/power/cpu boost.json' }
        @{ Relative = 'tweaks/power/cpu-boost.json' }
        @{ Relative = 'tweaks/Display/refresh_rate.json' }
        @{ Relative = 'tweaks/my power/cpu_boost.json' }
    ) {
        $content = [IO.File]::ReadAllText((Join-Path $script:fixtures 'id1/tweaks/power/CpuBoost.json'), $script:utf8)
        $root = New-GateRoot -Files @{ $Relative = $content }
        Assert-Finding (Invoke-Gate -Root $root) 'ID1' (Split-Path -Leaf $Relative)
    }
}

Describe 'FS1 the runtime writes no file' {
    It 'reports the committed fixture (Set-Content)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'fs1')) 'FS1' 'Writer.ps1'
    }

    It 'reports <Write>' -ForEach @(
        @{ Write = '''x'' | Out-File -FilePath (Join-Path $env:TEMP ''fpstune-note.txt'')' }
        @{ Write = 'Add-Content -Path (Join-Path $env:TEMP ''fpstune-note.txt'') -Value ''x''' }
        @{ Write = 'New-Item -ItemType File -Path (Join-Path $env:TEMP ''fpstune-note.txt'') | Out-Null' }
        @{ Write = '[IO.File]::WriteAllText((Join-Path $env:TEMP ''fpstune-note.txt''), ''x'')' }
        @{ Write = '[System.IO.File]::WriteAllBytes((Join-Path $env:TEMP ''fpstune-note.txt''), [byte[]](1))' }
        @{ Write = '[IO.File]::WriteAllLines((Join-Path $env:TEMP ''fpstune-note.txt''), [string[]]@(''x''))' }
        @{ Write = '[System.IO.File]::AppendAllText((Join-Path $env:TEMP ''fpstune-note.txt''), ''x'')' }
        @{ Write = '$fileApi = [IO.File]; $fileApi::WriteAllBytes((Join-Path $env:TEMP ''fpstune-note.bin''), [byte[]](1))' }
        @{ Write = '$fileApi = [type]''System.IO.File''; $fileApi::AppendAllLines((Join-Path $env:TEMP ''fpstune-note.txt''), [string[]]@(''x''))' }
        @{ Write = '([IO.File])::WriteAllText((Join-Path $env:TEMP ''fpstune-note.txt''), ''x'')' }
        @{ Write = '[IO.File]::Create((Join-Path $env:TEMP ''fpstune-note.txt'')).Dispose()' }
        @{ Write = '[IO.File]::OpenWrite((Join-Path $env:TEMP ''fpstune-note.txt'')).Dispose()' }
        @{ Write = '$w = [IO.StreamWriter]::new((Join-Path $env:TEMP ''fpstune-note.txt'')); $w.Dispose()' }
        @{ Write = '$writerType = [IO.StreamWriter]; $w = $writerType::new((Join-Path $env:TEMP ''fpstune-note.txt'')); $w.Dispose()' }
        @{ Write = '$w = New-Object IO.StreamWriter (Join-Path $env:TEMP ''fpstune-note.txt''); $w.Dispose()' }
        @{ Write = '$w = New-Object -TypeName System.IO.StreamWriter -ArgumentList (Join-Path $env:TEMP ''fpstune-note.txt''); $w.Dispose()' }
        @{ Write = '$s = [IO.FileStream]::new((Join-Path $env:TEMP ''fpstune-note.txt''), [IO.FileMode]::Create); $s.Dispose()' }
        @{ Write = '$s = New-Object IO.FileStream (Join-Path $env:TEMP ''fpstune-note.txt''), ''OpenOrCreate'', ''Write''; $s.Dispose()' }
        @{ Write = '$doc = New-Object Xml.XmlDocument; $doc.LoadXml(''<a/>''); $doc.Save((Join-Path $env:TEMP ''fpstune-note.xml''))' }
        @{ Write = 'Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $env:TEMP ''fpstune-copy.ps1'')' }
        @{ Write = 'Move-Item -LiteralPath (Join-Path $env:TEMP ''a.txt'') -Destination (Join-Path $env:TEMP ''b.txt'')' }
    ) {
        $text = "# Gate fixture: a runtime file that writes a file.`r`nfunction Save-FixtureNote {`r`n    $Write`r`n}`r`n"
        $root = New-GateRoot -Files @{ 'runtime/Writer.ps1' = $text }
        Assert-Finding (Invoke-Gate -Root $root) 'FS1' 'Writer.ps1'
    }

    It 'reports the committed receiver fixture ($fileApi = [IO.File]; $fileApi::WriteAllBytes)' {
        Assert-Finding (Invoke-Gate -Root (New-GateRoot -Overlay 'fs1_receiver')) 'FS1' 'Writer.ps1'
    }

    It 'allows the read-only <Read>' -ForEach @(
        @{ Read = '$s = [IO.File]::OpenRead($PSCommandPath); $s.Dispose()' }
        @{ Read = '$s = [IO.FileStream]::new($PSCommandPath, [IO.FileMode]::Open, [IO.FileAccess]::Read); $s.Dispose()' }
        @{ Read = '$s = New-Object IO.FileStream $PSCommandPath, ''Open'', ''Read''; $s.Dispose()' }
        @{ Read = '$doc = New-Object Xml.XmlDocument; $doc.LoadXml(''<a/>''); $doc.OuterXml' }
    ) {
        $text = "# Gate fixture: a runtime file that only reads.`r`nfunction Read-FixtureNote {`r`n    $Read`r`n}`r`n"
        $root = New-GateRoot -Files @{ 'runtime/Reader.ps1' = $text }
        Assert-Clean (Invoke-Gate -Root $root)
    }

    # Scope: FS1 binds the shipped runtime modules runtime/*.ps1. The dev files
    # runtime/gate.ps1 and runtime/test.ps1 stay at runtime/ by their contract
    # and are exempt by name; runtime/tools/** and runtime/tests/** are not scanned.
    It 'does not report the dev file runtime/<Leaf> writing a file' -ForEach @(
        @{ Leaf = 'gate.ps1' }
        @{ Leaf = 'test.ps1' }
        @{ Leaf = 'tools/build.ps1' }
    ) {
        $root = New-GateRoot -Overlay 'fs1_scope' -Remove @(
            @('gate.ps1', 'test.ps1', 'tools/build.ps1') | Where-Object { $_ -ne $Leaf } | ForEach-Object { "runtime/$_" })
        Assert-Clean (Invoke-Gate -Root $root)
    }

    It 'reports runtime/Apply.ps1 making the write runtime/tools/build.ps1 makes' {
        $text = [IO.File]::ReadAllText((Join-Path $script:fixtures 'fs1_scope/runtime/tools/build.ps1'), $script:utf8)
        $root = New-GateRoot -Files @{ 'runtime/Apply.ps1' = $text }
        Assert-Finding (Invoke-Gate -Root $root) 'FS1' 'Apply.ps1'
    }
}

Describe 'AS1 runtime/run.ps1 is ASCII only' {
    It 'reports a non-ASCII character in run.ps1' {
        $root = New-GateRoot -Overlay 'as1' -Tokens @{ '__NONASCII__' = [string][char]0x00E9 }
        Assert-Finding (Invoke-Gate -Root $root) 'AS1' 'run.ps1'
    }

    It 'reports a byte order mark in run.ps1' {
        $bytes = [byte[]](@(0xEF, 0xBB, 0xBF) + [Text.Encoding]::ASCII.GetBytes("Write-Host 'run'`r`n"))
        $root = New-GateRoot -Files @{ 'runtime/run.ps1' = $bytes }
        Assert-Finding (Invoke-Gate -Root $root) 'AS1' 'run.ps1'
    }

    It 'finds no AS1 in the real runtime/run.ps1' {
        if (-not (Test-Path -LiteralPath (Join-Path $script:repoRoot 'runtime/run.ps1'))) {
            Set-ItResult -Skipped -Because 'runtime/run.ps1 does not exist yet (U7)'
            return
        }
        $result = Invoke-Gate -Root $script:repoRoot
        @($result.Findings | Where-Object { $_.Rule -eq 'AS1' }).Count | Should -Be 0 -Because $result.Text
    }
}
