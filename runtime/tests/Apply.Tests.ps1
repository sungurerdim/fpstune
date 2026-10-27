# Apply, verify, restore point and journal (decision D3, unit U6 of #127).
#
# Contract pinned here:
# - Invoke-FpsApply -Rows <detect results>: each detect state carries Entry,
#   the catalogue entry object Get-FpsCatalogue returns, and row data is read
#   from it (no -Catalogue). A state without Entry fails closed: Status failed,
#   Reason no-entry, nothing applied. Only rows classed will-fix are applied;
#   already-right, manual, not-applicable and unreadable rows never are.
# - Before the first write: a restore point. If the newest restore point is
#   less than 24 h old it is reused and its time is reported; otherwise
#   Checkpoint-Computer runs and success is confirmed by a new sequence number.
#   If creation fails or cannot be confirmed, no apply command runs at all and
#   the result says why (Stopped, StopReason).
# - Per row: apply runs with $Target and $Instance, then detect runs again
#   (= verify). Equal -> Status fixed and the row's fixed sentence in the UI
#   language ((Get-UICulture).TwoLetterISOLanguageName tr -> tr, else en).
#   Not equal -> Status failed, Reason not-verified, Current = the read value.
#   Apply throws -> failed, Reason apply-error; native exit code not 0 ->
#   failed, Reason native-exit. A failure never stops the other rows.
#   A fixed restart=reboot row sets RebootNeeded on the result.
# - "after" is respected: a row runs after the rows it names.
# - Journal (result.Journal): memory only; each entry has Id, Phase, Outcome,
#   DurationMs, Reason and no field holding a previous or current value.
#   Apply/Journal write nothing to disk.
#
# Rows under fixtures/apply act only on a throwaway HKCU key that this file
# creates and removes; its path reaches the fixture commands through
# $env:FPSTUNE_TEST_KEY. Get-ComputerRestorePoint and Checkpoint-Computer are
# always mocked: no real restore point is ever created. This file is ASCII
# only; Turkish text is built from code points.
BeforeAll {
    . (Join-Path $PSScriptRoot '../Catalogue.ps1')
    . (Join-Path $PSScriptRoot '../Detect.ps1')
    . (Join-Path $PSScriptRoot '../Journal.ps1')
    . (Join-Path $PSScriptRoot '../Apply.ps1')

    # Mock needs the commands to exist (they are absent on PowerShell 7).
    if (-not (Get-Command Get-ComputerRestorePoint -ErrorAction SilentlyContinue)) {
        function script:Get-ComputerRestorePoint { param($RestorePoint, [switch]$LastStatus) }
    }
    if (-not (Get-Command Checkpoint-Computer -ErrorAction SilentlyContinue)) {
        function script:Checkpoint-Computer { param($Description, $RestorePointType) }
    }

    $script:repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).ProviderPath
    $script:fixtureRoot = Join-Path $PSScriptRoot 'fixtures/apply'
    $script:catalogue = @(Get-FpsCatalogue -Root $script:fixtureRoot)
    $script:testKeyParent = 'HKCU:\Software\FpsTuneTest'
    $script:testKey = Join-Path $script:testKeyParent ([guid]::NewGuid().ToString('N'))
    $env:FPSTUNE_TEST_KEY = $script:testKey

    function script:Reset-TestKey {
        Remove-Item -LiteralPath $script:testKey -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -Path $script:testKey -Force | Out-Null
        $start = [ordered]@{ Level = 7340; Mismatch = 9876; Thrower = 0; Exiter = 0; Boot = 0; OrdA = 0; OrdB = 0; OrdC = 0; Gate = 1; Guard = 0 }
        foreach ($name in $start.Keys) {
            New-ItemProperty -LiteralPath $script:testKey -Name $name -Value $start[$name] -PropertyType DWord -Force | Out-Null
        }
        New-ItemProperty -LiteralPath $script:testKey -Name Order -Value '' -PropertyType String -Force | Out-Null
        foreach ($i in 'a', 'b') {
            $item = Join-Path (Join-Path $script:testKey 'Items') $i
            New-Item -Path $item -Force | Out-Null
            New-ItemProperty -LiteralPath $item -Name On -Value 0 -PropertyType DWord -Force | Out-Null
        }
    }
    function script:Set-TestValue([string]$Name, $Value) {
        New-ItemProperty -LiteralPath $script:testKey -Name $Name -Value $Value -PropertyType DWord -Force | Out-Null
    }
    function script:Get-TestValue([string]$Name, [string]$Sub) {
        $path = if ($Sub) { Join-Path $script:testKey $Sub } else { $script:testKey }
        $p = Get-ItemProperty -LiteralPath $path -Name $Name -ErrorAction SilentlyContinue
        if ($p) { $p.$Name } else { $null }
    }
    function script:Get-TestRows([string[]]$Names) {
        $states = foreach ($n in $Names) {
            $row = $script:catalogue | Where-Object { $_.Id -eq "test:$n" }
            if (-not $row) { throw "No fixture row test:$n." }
            Get-FpsRowState -Row $row
        }
        , @($states)
    }
    function script:Invoke-TestApply([string[]]$Names) {
        Invoke-FpsApply -Rows (Get-TestRows $Names)
    }
    function script:Get-ResultRow($Result, [string]$RowId) {
        @($Result.Rows) | Where-Object { $_.RowId -eq $RowId }
    }
    function script:Get-FixedText([string]$Name, [string]$Lang) {
        ($script:catalogue | Where-Object { $_.Id -eq "test:$Name" }).Data.fixed.$Lang
    }
    function script:New-TestRestorePoint([int]$Sequence, [datetime]$Time) {
        [pscustomobject]@{
            SequenceNumber   = [uint32]$Sequence
            CreationTime     = [Management.ManagementDateTimeConverter]::ToDmtfDateTime($Time)
            Description      = 'fixture point'
            RestorePointType = 0
            EventType        = 100
        }
    }
    function script:Get-FileSnapshot {
        $set = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $gitDir = Join-Path $script:repoRoot '.git'
        $lists = @(
            @(Get-ChildItem -LiteralPath $script:repoRoot -Recurse -File -Force -ErrorAction SilentlyContinue |
                    Where-Object { -not $_.FullName.StartsWith($gitDir, [StringComparison]::OrdinalIgnoreCase) })
            @(Get-ChildItem -LiteralPath $env:TEMP -Depth 2 -File -Force -ErrorAction SilentlyContinue)
            @(Get-ChildItem -LiteralPath $HOME -Depth 1 -File -Force -ErrorAction SilentlyContinue)
        )
        foreach ($f in $lists) { [void]$set.Add($f.FullName) }
        , $set
    }
}

AfterAll {
    if ($script:testKey) { Remove-Item -LiteralPath $script:testKey -Recurse -Force -ErrorAction SilentlyContinue }
    $left = @(Get-ChildItem -LiteralPath 'HKCU:\Software\FpsTuneTest' -ErrorAction SilentlyContinue)
    if ($left.Count -eq 0) { Remove-Item -LiteralPath 'HKCU:\Software\FpsTuneTest' -Force -ErrorAction SilentlyContinue }
    Remove-Item Env:\FPSTUNE_TEST_KEY -ErrorAction SilentlyContinue
}

Describe 'Invoke-FpsApply' {
    BeforeEach {
        Reset-TestKey
        $script:probe = @{ Created = $false; LevelAtCheckpoint = $null }
        $script:rpTime = (Get-Date).AddHours(-2)
        $script:rpList = @(New-TestRestorePoint 41 $script:rpTime)
        Mock Get-ComputerRestorePoint { $script:rpList }
        Mock Checkpoint-Computer { throw 'Checkpoint-Computer must not run in this test.' }
        Mock Get-UICulture { New-Object Globalization.CultureInfo 'en-US' }
    }

    Context 'which rows are applied' {
        It 'applies a will-fix row' {
            (Get-TestRows ok)[0].Class | Should -Be 'will-fix'
            $r = Invoke-TestApply ok
            (Get-ResultRow $r 'test:ok').Status | Should -Be 'fixed'
            Get-TestValue Level | Should -Be 1
        }

        It 'never applies a <Class> row' -ForEach @(
            @{ Class = 'already-right'; Gate = 1; Guard = 1 }
            @{ Class = 'not-applicable'; Gate = 0; Guard = 0 }
            @{ Class = 'unreadable'; Gate = 1; Guard = $null }
        ) {
            Set-TestValue Gate $Gate
            if ($null -eq $Guard) { Remove-ItemProperty -LiteralPath $script:testKey -Name Guard } else { Set-TestValue Guard $Guard }
            (Get-TestRows untouched)[0].Class | Should -Be $Class
            $r = Invoke-TestApply untouched, ok
            Get-TestValue Touched | Should -BeNullOrEmpty
            @(Get-ResultRow $r 'test:untouched' | Where-Object { $_.Status -in 'fixed', 'failed' }).Count | Should -Be 0
            (Get-ResultRow $r 'test:ok').Status | Should -Be 'fixed'
        }

        It 'reads row data from the detect state Entry' {
            $s = (Get-TestRows ok)[0]
            $s.Entry | Should -Not -BeNullOrEmpty
            $s.Entry.Id | Should -Be 'test:ok'
            $s.Entry.Data.apply | Should -Not -BeNullOrEmpty
        }

        It 'fails closed for a will-fix state without Entry' {
            $bare = (Get-TestRows ok)[0] | Select-Object -Property * -ExcludeProperty Entry
            $bare.PSObject.Properties['Entry'] | Should -BeNullOrEmpty
            $bare.Class | Should -Be 'will-fix'
            $r = Invoke-FpsApply -Rows @($bare)
            $row = Get-ResultRow $r 'test:ok'
            $row.Status | Should -Be 'failed'
            $row.Reason | Should -Be 'no-entry'
            Get-TestValue Level | Should -Be 7340
        }

        It 'never applies a manual row' {
            (Get-TestRows manual)[0].Class | Should -Be 'manual'
            $r = Invoke-TestApply manual, ok
            @(Get-ResultRow $r 'test:manual' | Where-Object { $_.Status -in 'fixed', 'failed' }).Count | Should -Be 0
            (Get-ResultRow $r 'test:ok').Status | Should -Be 'fixed'
        }
    }

    Context 'restore point' {
        It 'reuses the newest point when it is less than 24 h old and reports its time' {
            $script:rpList = @(
                New-TestRestorePoint 40 ((Get-Date).AddHours(-30))
                New-TestRestorePoint 41 $script:rpTime
            )
            $r = Invoke-TestApply ok
            Should -Invoke Checkpoint-Computer -Times 0 -Exactly
            $r.Stopped | Should -BeFalse
            $r.RestorePoint.Reused | Should -BeTrue
            [int]$r.RestorePoint.SequenceNumber | Should -Be 41
            $r.RestorePoint.Time | Should -BeOfType [datetime]
            [math]::Abs(($r.RestorePoint.Time - $script:rpTime).TotalSeconds) | Should -BeLessThan 2
            Get-TestValue Level | Should -Be 1
        }

        It 'creates one before the first write when the newest is <Hours> h old, confirmed by a new sequence number' -ForEach @(
            @{ Hours = 25 }
            @{ Hours = 200 }
        ) {
            $script:rpList = @(New-TestRestorePoint 41 ((Get-Date).AddHours(-$Hours)))
            Mock Get-ComputerRestorePoint {
                if ($script:probe.Created) { @($script:rpList) + @(New-TestRestorePoint 42 (Get-Date)) } else { $script:rpList }
            }
            Mock Checkpoint-Computer {
                $script:probe.LevelAtCheckpoint = Get-TestValue Level
                $script:probe.Created = $true
            }
            $r = Invoke-TestApply ok
            Should -Invoke Checkpoint-Computer -Times 1 -Exactly
            $script:probe.LevelAtCheckpoint | Should -Be 7340
            $r.Stopped | Should -BeFalse
            $r.RestorePoint.Reused | Should -BeFalse
            [int]$r.RestorePoint.SequenceNumber | Should -Be 42
            (Get-ResultRow $r 'test:ok').Status | Should -Be 'fixed'
        }

        It 'creates one when there is no restore point at all' {
            Mock Get-ComputerRestorePoint { if ($script:probe.Created) { New-TestRestorePoint 1 (Get-Date) } }
            Mock Checkpoint-Computer { $script:probe.Created = $true }
            $r = Invoke-TestApply ok
            Should -Invoke Checkpoint-Computer -Times 1 -Exactly
            $r.Stopped | Should -BeFalse
            [int]$r.RestorePoint.SequenceNumber | Should -Be 1
            Get-TestValue Level | Should -Be 1
        }

        It 'runs no apply command and says why when creation fails' {
            $script:rpList = @(New-TestRestorePoint 41 ((Get-Date).AddHours(-48)))
            Mock Checkpoint-Computer { throw 'The restore point could not be created.' }
            $r = Invoke-TestApply ok, reboot, order_c, instances
            Should -Invoke Checkpoint-Computer -Times 1 -Exactly
            $r.Stopped | Should -BeTrue
            $r.StopReason | Should -Be 'restore-point-failed'
            Get-TestValue Level | Should -Be 7340
            Get-TestValue Boot | Should -Be 0
            Get-TestValue OrdC | Should -Be 0
            Get-TestValue Order | Should -BeNullOrEmpty
            Get-TestValue On 'Items\a' | Should -Be 0
            @(@($r.Rows) | Where-Object { $_.Status -eq 'fixed' }).Count | Should -Be 0
        }

        It 'runs no apply command and says why when creation cannot be confirmed' {
            $script:rpList = @(New-TestRestorePoint 41 ((Get-Date).AddHours(-48)))
            Mock Checkpoint-Computer { $script:probe.Created = $true }
            $r = Invoke-TestApply ok, reboot
            Should -Invoke Checkpoint-Computer -Times 1 -Exactly
            $r.Stopped | Should -BeTrue
            $r.StopReason | Should -Be 'restore-point-unconfirmed'
            Get-TestValue Level | Should -Be 7340
            Get-TestValue Boot | Should -Be 0
            @(@($r.Rows) | Where-Object { $_.Status -eq 'fixed' }).Count | Should -Be 0
        }

        It 'runs no apply command when the restore points cannot be read' {
            Mock Get-ComputerRestorePoint { throw 'System Restore is turned off.' }
            Mock Checkpoint-Computer { throw 'System Restore is turned off.' }
            $r = Invoke-TestApply ok
            $r.Stopped | Should -BeTrue
            $r.StopReason | Should -Not -BeNullOrEmpty
            Get-TestValue Level | Should -Be 7340
        }
    }

    Context 'apply and verify per row' {
        It 'runs apply with $Target, verifies by detect and reports the en fixed sentence' {
            $r = Invoke-TestApply ok
            $row = Get-ResultRow $r 'test:ok'
            $row.Status | Should -Be 'fixed'
            $row.Message | Should -BeExactly (Get-FixedText ok 'en')
            $row.Reason | Should -BeNullOrEmpty
            Get-TestValue Level | Should -Be 1
        }

        It 'reports the tr fixed sentence when the UI language is Turkish' {
            Mock Get-UICulture { New-Object Globalization.CultureInfo 'tr-TR' }
            $expected = 'Test d' + [char]0x00FC + 'zeyi art' + [char]0x0131 + 'k do' + [char]0x011F + 'ru.'
            (Get-FixedText ok 'tr') | Should -BeExactly $expected
            $r = Invoke-TestApply ok
            (Get-ResultRow $r 'test:ok').Message | Should -BeExactly $expected
        }

        It 'reports the en fixed sentence for UI language <Ui>' -ForEach @(
            @{ Ui = 'en-US' }
            @{ Ui = 'fr-FR' }
            @{ Ui = 'de-DE' }
        ) {
            Mock Get-UICulture { New-Object Globalization.CultureInfo $Ui }
            $r = Invoke-TestApply ok
            (Get-ResultRow $r 'test:ok').Message | Should -BeExactly (Get-FixedText ok 'en')
        }

        It 'runs apply with each $Instance and its own $Target' {
            $r = Invoke-TestApply instances
            (Get-ResultRow $r 'test:instances@a').Status | Should -Be 'fixed'
            (Get-ResultRow $r 'test:instances@b').Status | Should -Be 'fixed'
            Get-TestValue On 'Items\a' | Should -Be 3
            Get-TestValue On 'Items\b' | Should -Be 4
        }

        It 'is failed with reason not-verified and the read value when detect still differs' {
            $r = Invoke-TestApply noverify
            $row = Get-ResultRow $r 'test:noverify'
            $row.Status | Should -Be 'failed'
            $row.Reason | Should -Be 'not-verified'
            $row.Current | Should -Be '4321'
            $row.Message | Should -Not -Be (Get-FixedText noverify 'en')
        }

        It 'is failed with reason apply-error when apply throws' {
            $r = Invoke-TestApply throws
            $row = Get-ResultRow $r 'test:throws'
            $row.Status | Should -Be 'failed'
            $row.Reason | Should -Be 'apply-error'
            Get-TestValue Thrower | Should -Be 0
        }

        It 'is failed with reason native-exit when a native command exits non-zero' {
            $r = Invoke-TestApply exitcode
            $row = Get-ResultRow $r 'test:exitcode'
            $row.Status | Should -Be 'failed'
            $row.Reason | Should -Be 'native-exit'
        }

        It 'keeps applying the other rows after a failure' {
            $r = Invoke-TestApply throws, exitcode, noverify, ok, reboot
            (Get-ResultRow $r 'test:throws').Status | Should -Be 'failed'
            (Get-ResultRow $r 'test:exitcode').Status | Should -Be 'failed'
            (Get-ResultRow $r 'test:noverify').Status | Should -Be 'failed'
            (Get-ResultRow $r 'test:ok').Status | Should -Be 'fixed'
            (Get-ResultRow $r 'test:reboot').Status | Should -Be 'fixed'
            Get-TestValue Level | Should -Be 1
            Get-TestValue Boot | Should -Be 1
        }

        It 'sets RebootNeeded when a restart=reboot row is applied' {
            $r = Invoke-TestApply ok, reboot
            (Get-ResultRow $r 'test:reboot').Status | Should -Be 'fixed'
            $r.RebootNeeded | Should -BeTrue
        }

        It 'leaves RebootNeeded false when no restart=reboot row is applied' {
            $r = Invoke-TestApply ok
            $r.RebootNeeded | Should -BeFalse
        }
    }

    Context 'after ordering' {
        It 'runs each row after the rows it names (input <Names>)' -ForEach @(
            @{ Names = @('order_a', 'order_b', 'order_c') }
            @{ Names = @('order_b', 'order_a', 'order_c') }
        ) {
            $r = Invoke-TestApply $Names
            Get-TestValue Order | Should -BeExactly 'cba'
            foreach ($n in 'a', 'b', 'c') { (Get-ResultRow $r "test:order_$n").Status | Should -Be 'fixed' }
        }

        It 'still runs a row whose named row is not being applied' {
            Set-TestValue OrdB 1
            (Get-TestRows order_b)[0].Class | Should -Be 'already-right'
            $r = Invoke-TestApply order_a, order_b, order_c
            (Get-ResultRow $r 'test:order_a').Status | Should -Be 'fixed'
            (Get-ResultRow $r 'test:order_c').Status | Should -Be 'fixed'
            ((Get-TestValue Order).ToCharArray() | Sort-Object) -join '' | Should -BeExactly 'ac'
        }
    }

    Context 'journal' {
        It 'records the restore point first, then apply and verify per row' {
            $r = Invoke-TestApply ok, noverify
            $entries = @($r.Journal)
            $entries.Count | Should -BeGreaterThan 0
            $entries[0].Phase | Should -Be 'restore-point'
            foreach ($id in 'test:ok', 'test:noverify') {
                @($entries | Where-Object { $_.Id -eq $id -and $_.Phase -eq 'apply' }).Count | Should -Be 1
                @($entries | Where-Object { $_.Id -eq $id -and $_.Phase -eq 'verify' }).Count | Should -Be 1
            }
        }

        It 'gives every entry Id, Phase, Outcome, DurationMs and Reason' {
            $r = Invoke-TestApply ok, throws
            foreach ($e in @($r.Journal)) {
                $names = @($e.PSObject.Properties | ForEach-Object { $_.Name })
                foreach ($required in 'Id', 'Phase', 'Outcome', 'DurationMs', 'Reason') { $names | Should -Contain $required }
                $e.DurationMs | Should -BeOfType [System.ValueType]
                [double]$e.DurationMs | Should -BeGreaterOrEqual 0
            }
        }

        It 'carries the reason class of a failure' {
            $r = Invoke-TestApply ok, noverify, throws, exitcode
            $entries = @($r.Journal)
            ($entries | Where-Object { $_.Id -eq 'test:ok' -and $_.Phase -eq 'verify' }).Outcome | Should -Be 'ok'
            ($entries | Where-Object { $_.Id -eq 'test:noverify' -and $_.Phase -eq 'verify' }).Outcome | Should -Be 'failed'
            ($entries | Where-Object { $_.Id -eq 'test:noverify' -and $_.Phase -eq 'verify' }).Reason | Should -Be 'not-verified'
            ($entries | Where-Object { $_.Id -eq 'test:throws' -and $_.Phase -eq 'apply' }).Reason | Should -Be 'apply-error'
            ($entries | Where-Object { $_.Id -eq 'test:exitcode' -and $_.Phase -eq 'apply' }).Reason | Should -Be 'native-exit'
        }

        It 'holds no previous or current value' {
            $r = Invoke-TestApply ok, noverify
            $entries = @($r.Journal)
            $entries.Count | Should -BeGreaterThan 0
            foreach ($e in $entries) {
                foreach ($p in $e.PSObject.Properties) {
                    $p.Name | Should -Not -Match '(?i)value|previous|prev|old|before|current|target'
                    $text = "$($p.Value)"
                    foreach ($sentinel in '7340', '9876', '4321') { $text | Should -Not -Match $sentinel }
                }
            }
        }

        It 'writes no file to TEMP, the repo or HOME during a run' {
            $before = Get-FileSnapshot
            $r = Invoke-TestApply ok, noverify, throws, reboot, instances
            $after = Get-FileSnapshot
            @($r.Journal).Count | Should -BeGreaterThan 0
            $new = @($after | Where-Object { -not $before.Contains($_) })
            $new | Should -BeNullOrEmpty
        }
    }
}
