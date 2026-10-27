# Catalogue loader, command invoker and detect classification (D2/D3).
#
# Rows under fixtures/detect act only on a throwaway HKCU key that this file
# creates and removes; its path reaches the fixture commands through
# $env:FPSTUNE_TEST_KEY. No real setting is ever read or written.
BeforeAll {
    . (Join-Path $PSScriptRoot '../Catalogue.ps1')
    . (Join-Path $PSScriptRoot '../Detect.ps1')

    $script:fixtureRoot = Join-Path $PSScriptRoot 'fixtures/detect'
    $script:testKeyParent = 'HKCU:\Software\FpsTuneTest'
    $script:testKey = Join-Path $script:testKeyParent ([guid]::NewGuid().ToString('N'))
    New-Item -Path $script:testKey -Force | Out-Null
    $env:FPSTUNE_TEST_KEY = $script:testKey

    function script:Set-TestValue([string]$Name, $Value) {
        New-ItemProperty -LiteralPath $script:testKey -Name $Name -Value $Value -PropertyType DWord -Force | Out-Null
    }
    function script:Clear-TestValue([string]$Name) {
        Remove-ItemProperty -LiteralPath $script:testKey -Name $Name -ErrorAction SilentlyContinue
    }
    function script:Get-TestState([string]$Name) {
        $catalogue = Get-FpsCatalogue -Root $script:fixtureRoot
        $row = $catalogue | Where-Object { $_.Id -eq "test:$Name" }
        , @(Get-FpsRowState -Row $row)
    }
}

AfterAll {
    Remove-Item -LiteralPath $script:testKey -Recurse -Force -ErrorAction SilentlyContinue
    $left = @(Get-ChildItem -LiteralPath $script:testKeyParent -ErrorAction SilentlyContinue)
    if ($left.Count -eq 0) { Remove-Item -LiteralPath $script:testKeyParent -Force -ErrorAction SilentlyContinue }
    Remove-Item Env:\FPSTUNE_TEST_KEY, Env:\FPSTUNE_TEST_TEXT -ErrorAction SilentlyContinue
}

Describe 'Catalogue loader' {
    It 'derives category:name ids from the path' {
        $ids = @(Get-FpsCatalogue -Root $script:fixtureRoot | ForEach-Object { $_.Id })
        $ids | Should -Contain 'test:value'
        $ids | Should -Contain 'test:manual'
        $ids | Should -Not -Contain 'value'
    }

    It 'exposes the parsed content, category and name' {
        $row = Get-FpsCatalogue -Root $script:fixtureRoot | Where-Object { $_.Id -eq 'test:value' }
        $row.Category | Should -Be 'test'
        $row.Name | Should -Be 'value'
        $row.Data.kind | Should -Be 'tweak'
        $row.Data.title.tr | Should -Be ('Test sat' + [char]0x0131 + 'r' + [char]0x0131 + ' value')  # ASCII-only source
    }

    It 'rejects a file that does not parse and names the file' {
        $dir = Join-Path $TestDrive 'broken/power'
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $dir 'bad_one.json') -Value '{ "kind": ' -Encoding UTF8
        { Get-FpsCatalogue -Root (Join-Path $TestDrive 'broken') } | Should -Throw -ExpectedMessage '*bad_one.json*'
    }

    It 'rejects a file that is not directly under a category folder' {
        $dir = Join-Path $TestDrive 'shallow'
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $dir 'loose.json') -Value '{}' -Encoding UTF8
        { Get-FpsCatalogue -Root $dir } | Should -Throw -ExpectedMessage '*loose.json*'
    }

    It 'fails when the root folder is missing' {
        { Get-FpsCatalogue -Root (Join-Path $TestDrive 'nope') } | Should -Throw
    }
}

Describe 'Command invoker' {
    It 'passes $Instance and $Target as parameters' {
        $out = @(Invoke-FpsCommand -Command '"$Instance|$Target"' -Instance 'eth0' -Target 5)
        $out | Should -Be 'eth0|5'
    }

    It 'returns nothing for a command with no output' {
        @(Invoke-FpsCommand -Command '$unused = 1').Count | Should -Be 0
    }

    It 'turns a non-terminating error into a failure' {
        { Invoke-FpsCommand -Command 'Get-Item -LiteralPath (Join-Path $env:FPSTUNE_TEST_KEY "missing-item")' } | Should -Throw
    }

    It 'throws when the command does not parse' {
        { Invoke-FpsCommand -Command 'if (' } | Should -Throw
    }

    It 'counts a non-zero native exit code as failure' {
        { Invoke-FpsCommand -Command 'cmd.exe /c exit 3' } | Should -Throw -ExpectedMessage '*3*'
    }

    It 'accepts a native command that exits with zero' {
        { Invoke-FpsCommand -Command 'cmd.exe /c exit 0' } | Should -Not -Throw
    }

    It 'does not reuse an exit code left by an earlier native call' {
        cmd.exe /c exit 7
        { Invoke-FpsCommand -Command '1' } | Should -Not -Throw
    }
}

Describe 'Canonical comparison form' {
    It 'writes <Value> as <Expected>' -ForEach @(
        @{ Value = $true; Expected = 'true' }
        @{ Value = $false; Expected = 'false' }
        @{ Value = 1; Expected = '1' }
        @{ Value = [double]1.5; Expected = '1.5' }
        @{ Value = [decimal]2.50; Expected = '2.5' }
        @{ Value = [long]123456789012; Expected = '123456789012' }
        @{ Value = '  padded  '; Expected = 'padded' }
        @{ Value = 'I'; Expected = 'I' }
    ) {
        ConvertTo-FpsCanonical $Value | Should -BeExactly $Expected
    }

    It 'refuses a value that is not a scalar' {
        { ConvertTo-FpsCanonical @{ a = 1 } } | Should -Throw
        { ConvertTo-FpsCanonical $null } | Should -Throw
    }

    It 'compares ordinally and case-sensitively whatever the thread culture' {
        Test-FpsEqual 'I' 'I' | Should -BeTrue
        Test-FpsEqual 'i' 'I' | Should -BeFalse
        Test-FpsEqual ([string][char]0x0131) 'I' | Should -BeFalse   # dotless i
        Test-FpsEqual ([string][char]0x0130) 'I' | Should -BeFalse   # dotted capital I
        Test-FpsEqual 'TITLE' 'title' | Should -BeFalse
        Test-FpsEqual 'Fix' 'Fix' | Should -BeTrue
    }
}

Describe 'Detect classification' {
    Context 'registry value row' {
        It 'is already-right when the value matches the target' {
            Set-TestValue Level 1
            $s = Get-TestState value
            $s.Count | Should -Be 1
            $s[0].Class | Should -Be 'already-right'
            $s[0].RowId | Should -Be 'test:value'
            $s[0].Current | Should -Be '1'
            $s[0].Target | Should -Be '1'
        }

        It 'is will-fix when the value differs' {
            Set-TestValue Level 0
            (Get-TestState value)[0].Class | Should -Be 'will-fix'
        }

        It 'is unreadable, never already-right, when detect throws' {
            Clear-TestValue Level
            $s = (Get-TestState value)[0]
            $s.Class | Should -Be 'unreadable'
            $s.Class | Should -Not -Be 'already-right'
            $s.Error | Should -Not -BeNullOrEmpty
        }
    }

    Context 'manual row' {
        It 'is manual and runs no command' {
            $s = Get-TestState manual
            $s.Count | Should -Be 1
            $s[0].Class | Should -Be 'manual'
            $s[0].RowId | Should -Be 'test:manual'
        }
    }

    Context 'applicable gate' {
        It 'is not-applicable when applicable returns false' {
            Set-TestValue Gate 0
            Set-TestValue Level 0
            (Get-TestState gated)[0].Class | Should -Be 'not-applicable'
        }

        It 'continues to detect when applicable returns true' {
            Set-TestValue Gate 1
            Set-TestValue Level 0
            (Get-TestState gated)[0].Class | Should -Be 'will-fix'
            Set-TestValue Level 1
            (Get-TestState gated)[0].Class | Should -Be 'already-right'
        }

        It 'is unreadable when applicable throws' {
            Clear-TestValue Gate
            (Get-TestState gated)[0].Class | Should -Be 'unreadable'
        }
    }

    Context 'per-instance row' {
        BeforeAll {
            $items = Join-Path $script:testKey 'Items'
            foreach ($i in 'a', 'b', 'c') { New-Item -Path (Join-Path $items $i) -Force | Out-Null }
            New-ItemProperty -LiteralPath (Join-Path $items 'a') -Name On -Value 1 -PropertyType DWord | Out-Null
            New-ItemProperty -LiteralPath (Join-Path $items 'b') -Name On -Value 1 -PropertyType DWord | Out-Null
            # instance c has no On value: unreadable
        }

        It 'returns one state per instance with ids <id>@<instance>' {
            $s = Get-TestState instances
            $s.Count | Should -Be 3
            ($s | ForEach-Object { $_.RowId } | Sort-Object) | Should -Be @('test:instances@a', 'test:instances@b', 'test:instances@c')
        }

        It 'classifies each instance on its own, with a per-instance target' {
            $s = Get-TestState instances
            ($s | Where-Object { $_.Instance -eq 'a' }).Class | Should -Be 'already-right'
            ($s | Where-Object { $_.Instance -eq 'b' }).Class | Should -Be 'will-fix'
            ($s | Where-Object { $_.Instance -eq 'c' }).Class | Should -Be 'unreadable'
            ($s | Where-Object { $_.Instance -eq 'b' }).Target | Should -Be '2'
        }

        It 'carries the instance label' {
            ((Get-TestState instances) | Where-Object { $_.Instance -eq 'a' }).Label | Should -Be 'Item a'
        }

        It 'is a single not-applicable row when there are no instances' {
            Remove-Item -LiteralPath (Join-Path $script:testKey 'Items') -Recurse -Force
            New-Item -Path (Join-Path $script:testKey 'Items') -Force | Out-Null
            $s = Get-TestState instances
            $s.Count | Should -Be 1
            $s[0].Class | Should -Be 'not-applicable'
            $s[0].RowId | Should -Be 'test:instances'
        }

        It 'is a single unreadable row when the instances command throws' {
            Remove-Item -LiteralPath (Join-Path $script:testKey 'Items') -Recurse -Force
            $s = Get-TestState instances
            $s.Count | Should -Be 1
            $s[0].Class | Should -Be 'unreadable'
        }
    }

    Context 'unreadable target and detect shapes' {
        It 'is unreadable when the target command throws' {
            (Get-TestState target_throws)[0].Class | Should -Be 'unreadable'
        }

        It 'is unreadable when detect returns nothing' {
            (Get-TestState detect_empty)[0].Class | Should -Be 'unreadable'
        }

        It 'is unreadable when detect returns more than one value' {
            (Get-TestState detect_many)[0].Class | Should -Be 'unreadable'
        }
    }

    Context 'invariant, ordinal comparison under the thread culture' {
        It 'treats a double detect value and a string target as equal' {
            (Get-TestState decimal_num)[0].Class | Should -Be 'already-right'
        }

        It 'treats a string detect value and a numeric target as equal' {
            (Get-TestState decimal_str)[0].Class | Should -Be 'already-right'
        }

        It 'treats a boolean detect value and a boolean target as equal' {
            (Get-TestState bool)[0].Class | Should -Be 'already-right'
        }

        It 'compares text <Text> against I as <Class>' -ForEach @(
            @{ Text = 'I'; Class = 'already-right' }
            @{ Text = ' I '; Class = 'already-right' }
            @{ Text = 'i'; Class = 'will-fix' }
            @{ Text = ([string][char]0x0131); Class = 'will-fix' }
            @{ Text = ([string][char]0x0130); Class = 'will-fix' }
        ) {
            $env:FPSTUNE_TEST_TEXT = $Text
            (Get-TestState text)[0].Class | Should -Be $Class
        }
    }

    Context 'whole catalogue' {
        It 'classifies every fixture row without throwing' {
            Set-TestValue Gate 1
            Set-TestValue Level 1
            $rows = @(Get-FpsState -Root $script:fixtureRoot)
            $rows.Count | Should -BeGreaterThan 8
            foreach ($r in $rows) {
                $r.Class | Should -BeIn @('already-right', 'will-fix', 'manual', 'not-applicable', 'unreadable')
            }
        }
    }
}
