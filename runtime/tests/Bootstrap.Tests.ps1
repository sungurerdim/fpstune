# Bundle and bootstrap contract (decision D3, unit U7 of #127). ASCII only.
#
# tools/build.ps1 (dev tool, not shipped; writes its outputs normally)
#   tools/build.ps1 -Out <path> [-TweaksRoot <dir>] [-RunOut <path> -Tag <tag> -BundleUrl <url>]
#   - Writes ONE .ps1: Catalogue, Detect, Summary, Journal, Apply (this fixed
#     order), the strings (en, tr) and the tweak catalogue embedded as data.
#   - LF line endings only, UTF-8 without BOM, parses without errors.
#   - Deterministic: two builds of the same tree have the same SHA-256.
#   - Prints the bundle SHA-256 as 64 upper-case hex characters.
#   - With -RunOut it writes run.ps1 with the three placeholders filled.
# Bundle
#   - param([switch]$NoMain): with -NoMain it only defines its functions and
#     loads the embedded data; the main flow does not start.
#   - Needs no file next to it: Get-FpsStrings -Language <en|tr> returns the
#     embedded strings, Get-FpsCatalogue without -Root returns the embedded
#     rows (Id, Category, Name, Data), Format-FpsSummary works on them.
# run.ps1 (template, ASCII only)
#   - Placeholders: __FPS_RELEASE_TAG__, __FPS_BUNDLE_URL__, __FPS_BUNDLE_SHA256__
#     (upper-case hex).
#   - Enables TLS 1.2.
#   - Test-FpsElevated: WindowsPrincipal.IsInRole([WindowsBuiltInRole]...), a
#     [bool]. When it is $false: Start-Process powershell -Verb RunAs with the
#     same one-liner (... | iex), then exit; nothing is downloaded.
#   - Get-FpsBundleBytes -Url <url>: the only network call, returns byte[].
#   - SHA-256 mismatch: prints a line naming SHA-256, exits non-zero, runs nothing.
#   - Match: decodes the bytes as UTF-8 explicitly and runs them as a scriptblock.
#   - Writes no file.
# All network is mocked; Invoke-RestMethod / Invoke-WebRequest throw if reached.

BeforeAll {
    $script:runtimeRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
    $script:buildPath = Join-Path (Join-Path $script:runtimeRoot 'tools') 'build.ps1'
    $script:runPath = Join-Path $script:runtimeRoot 'run.ps1'
    $script:tweaksRoot = Join-Path $PSScriptRoot 'fixtures/bootstrap/tweaks'
    $script:utf8 = New-Object System.Text.UTF8Encoding($false)
    $script:utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)
    $script:testUrl = 'https://example.invalid/fpstune-bundle.ps1'
    $script:testTag = 'v0.0.0-test'

    # Mock bodies run in the caller's scope (run.ps1 has its own script scope),
    # so served bytes reach them through a closure, never through `$script:.
    # Stand-ins so Pester can mock the commands run.ps1 defines for itself.
    # A mock is an alias, and an alias wins over the function run.ps1 defines.
    function script:Get-FpsBundleBytes { param([string]$Url) throw 'stub: network must be mocked' }
    function script:Test-FpsElevated { throw 'stub: elevation must be mocked' }

    function script:Get-Sha256Hex([byte[]]$Bytes) {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { -join @($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('X2', [Globalization.CultureInfo]::InvariantCulture) }) }
        finally { $sha.Dispose() }
    }

    function script:Invoke-FpsBuild([string]$Out, [string[]]$Extra = @()) {
        if (-not (Test-Path -LiteralPath $script:buildPath)) { throw "runtime/tools/build.ps1 not found: $script:buildPath" }
        $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $script:buildPath -Out $Out -TweaksRoot $script:tweaksRoot @Extra 2>&1
        [pscustomobject]@{ Output = @($output | ForEach-Object { "$_" }); ExitCode = $LASTEXITCODE }
    }

    function script:New-BuiltBundle([string]$Name) {
        $dir = Join-Path $TestDrive $Name
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $out = Join-Path $dir 'fpstune.ps1'
        $r = Invoke-FpsBuild -Out $out
        $r.ExitCode | Should -Be 0 -Because ($r.Output -join "`n")
        $out
    }

    function script:Get-RunTemplate {
        if (-not (Test-Path -LiteralPath $script:runPath)) { throw "runtime/run.ps1 not found: $script:runPath" }
        [IO.File]::ReadAllText($script:runPath, $script:utf8Strict)
    }

    function script:New-FilledRun([string]$Sha256) {
        $text = (Get-RunTemplate).Replace('__FPS_RELEASE_TAG__', $script:testTag).Replace('__FPS_BUNDLE_URL__', $script:testUrl).Replace('__FPS_BUNDLE_SHA256__', $Sha256)
        $path = Join-Path $TestDrive ('run-' + [guid]::NewGuid().ToString('N') + '.ps1')
        [IO.File]::WriteAllText($path, $text, $script:utf8)
        $path
    }

    # Runs a filled run.ps1 from an empty working folder; returns output, exit code, folder.
    function script:Invoke-FilledRun([string]$Path) {
        $cwd = Join-Path $TestDrive ('cwd-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $cwd | Out-Null
        $global:LASTEXITCODE = 0
        Push-Location -LiteralPath $cwd
        try { $out = @(& $Path *>&1 | ForEach-Object { "$_" }) }
        finally { Pop-Location }
        [pscustomobject]@{ Output = $out; ExitCode = $global:LASTEXITCODE; Cwd = $cwd }
    }

    # Turkish text built from code points so this file stays ASCII.
    $script:turkish = 'Bunun i' + [char]0x00E7 + 'in hen' + [char]0x00FC + 'z ad' + [char]0x0131 + 'm yok: ' +
        [char]0x015F + [char]0x011F + [char]0x0130 + [char]0x0131 + [char]0x00F6 + [char]0x00C7
}

Describe 'tools/build.ps1 bundle' {
    It 'two builds of the same tree have the same SHA-256 and the build prints it' {
        $a = Join-Path $TestDrive 'det-a.ps1'
        $b = Join-Path $TestDrive 'det-b.ps1'
        $ra = Invoke-FpsBuild -Out $a
        $rb = Invoke-FpsBuild -Out $b
        $ra.ExitCode | Should -Be 0 -Because ($ra.Output -join "`n")
        $rb.ExitCode | Should -Be 0 -Because ($rb.Output -join "`n")
        $ha = (Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash
        $hb = (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash
        $hb | Should -BeExactly $ha
        ($ra.Output -join "`n") -cmatch ('(?<![0-9A-F])' + $ha + '(?![0-9A-F])') | Should -BeTrue -Because 'the build prints the bundle SHA-256'
    }

    It 'has no CR byte, no BOM and is valid UTF-8' {
        $bytes = [IO.File]::ReadAllBytes((New-BuiltBundle 'bytes'))
        $bytes.Length | Should -BeGreaterThan 0
        @($bytes | Where-Object { $_ -eq 13 }).Count | Should -Be 0
        ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) | Should -BeFalse
        { $script:utf8Strict.GetString($bytes) } | Should -Not -Throw
    }

    It 'holds the modules in fixed order and the catalogue as data, and parses' {
        $text = [IO.File]::ReadAllText((New-BuiltBundle 'order'), $script:utf8Strict)
        $marks = 'function Get-FpsCatalogue', 'function Get-FpsRowState', 'function Format-FpsSummary', 'function New-FpsJournal', 'function Invoke-FpsApply'
        $last = -1
        foreach ($m in $marks) {
            $i = $text.IndexOf($m, [StringComparison]::Ordinal)
            $i | Should -BeGreaterThan $last -Because "$m comes after the previous module"
            $last = $i
        }
        $text.Contains('Bundle sample row') | Should -BeTrue -Because 'the catalogue is embedded'
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseInput($text, [ref]$null, [ref]$errors)
        @($errors).Count | Should -Be 0
    }

    It 'runs in a clean process from an empty folder and still finds strings and catalogue' {
        $bundle = New-BuiltBundle 'clean'
        $empty = Join-Path $TestDrive 'empty-cwd'
        New-Item -ItemType Directory -Path $empty | Out-Null

        $child = @'
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$text = $utf8.GetString([IO.File]::ReadAllBytes($env:FPSTUNE_TEST_BUNDLE))
. ([scriptblock]::Create($text)) -NoMain
$s = Get-FpsStrings -Language tr
$rows = @(Get-FpsCatalogue)
$lines = @(Format-FpsSummary -Rows @() -Language tr)
$json = [pscustomobject]@{ NoSteps = $s.manualNoSteps; Ids = @($rows | ForEach-Object { $_.Id }); Title = $rows[0].Data.title.tr; Lines = $lines.Count } | ConvertTo-Json -Compress
[Convert]::ToBase64String($utf8.GetBytes($json))
'@
        $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
        $env:FPSTUNE_TEST_BUNDLE = $bundle
        $prevDir = [Environment]::CurrentDirectory
        Push-Location -LiteralPath $empty
        [Environment]::CurrentDirectory = $empty
        try { $out = @(& powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $enc 2>&1 | ForEach-Object { "$_" }) ; $code = $LASTEXITCODE }
        finally { [Environment]::CurrentDirectory = $prevDir; Pop-Location; Remove-Item Env:\FPSTUNE_TEST_BUNDLE -ErrorAction SilentlyContinue }

        $code | Should -Be 0 -Because ($out -join "`n")
        $result = $script:utf8.GetString([Convert]::FromBase64String($out[-1])) | ConvertFrom-Json
        $trStrings = [IO.File]::ReadAllText((Join-Path $script:runtimeRoot 'strings/tr.json'), $script:utf8) | ConvertFrom-Json
        $fixture = [IO.File]::ReadAllText((Join-Path $script:tweaksRoot 'sample/row.json'), $script:utf8) | ConvertFrom-Json
        $result.NoSteps | Should -BeExactly $trStrings.manualNoSteps
        $result.NoSteps.Contains([string][char]0x0131) | Should -BeTrue
        @($result.Ids) | Should -Be @('sample:row')
        $result.Title | Should -BeExactly $fixture.title.tr
        $result.Lines | Should -BeGreaterThan 0
        @(Get-ChildItem -LiteralPath $empty -Force).Count | Should -Be 0 -Because 'the bundle writes no file'
    }

    It 'with -RunOut fills tag, URL and bundle SHA-256 into an ASCII run.ps1' {
        $dir = Join-Path $TestDrive 'runout'
        New-Item -ItemType Directory -Path $dir | Out-Null
        $out = Join-Path $dir 'fpstune.ps1'
        $runOut = Join-Path $dir 'run'
        $r = Invoke-FpsBuild -Out $out -Extra @('-RunOut', $runOut, '-Tag', $script:testTag, '-BundleUrl', $script:testUrl)
        $r.ExitCode | Should -Be 0 -Because ($r.Output -join "`n")
        $bytes = [IO.File]::ReadAllBytes($runOut)
        @($bytes | Where-Object { $_ -gt 0x7F }).Count | Should -Be 0
        $text = [Text.Encoding]::ASCII.GetString($bytes)
        $text.Contains('__FPS_') | Should -BeFalse
        $text.Contains($script:testTag) | Should -BeTrue
        $text.Contains($script:testUrl) | Should -BeTrue
        $text.Contains((Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash) | Should -BeTrue
    }
}

Describe 'run.ps1 bootstrap' {
    BeforeEach {
        Mock Invoke-RestMethod { throw 'network is mocked' }
        Mock Invoke-WebRequest { throw 'network is mocked' }
        $script:savedProtocol = [Net.ServicePointManager]::SecurityProtocol
    }
    AfterEach {
        [Net.ServicePointManager]::SecurityProtocol = $script:savedProtocol
    }

    It 'contains only ASCII bytes' {
        if (-not (Test-Path -LiteralPath $script:runPath)) { throw "runtime/run.ps1 not found: $script:runPath" }
        $bytes = [IO.File]::ReadAllBytes($script:runPath)
        $bytes.Length | Should -BeGreaterThan 0
        @($bytes | Where-Object { $_ -gt 0x7F }).Count | Should -Be 0
    }

    It 'is a template with the three placeholders, parses and writes no file' {
        $text = Get-RunTemplate
        foreach ($p in '__FPS_RELEASE_TAG__', '__FPS_BUNDLE_URL__', '__FPS_BUNDLE_SHA256__') {
            $text.Contains($p) | Should -BeTrue -Because "$p is filled by tools/build.ps1"
        }
        $errors = $null
        $ast = [Management.Automation.Language.Parser]::ParseInput($text, [ref]$null, [ref]$errors)
        @($errors).Count | Should -Be 0
        $funcs = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | ForEach-Object { $_.Name })
        $funcs -ccontains 'Test-FpsElevated' | Should -BeTrue
        $funcs -ccontains 'Get-FpsBundleBytes' | Should -BeTrue
        $writers = 'Out-File', 'Set-Content', 'Add-Content', 'New-Item', 'Export-Csv', 'Export-Clixml', 'Copy-Item', 'Move-Item', 'Tee-Object', 'Start-BitsTransfer'
        $commands = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($commands | Where-Object { $writers -contains $_ }) | Should -BeNullOrEmpty
        $members = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.MemberExpressionAst] }, $true) | ForEach-Object { $_.Member.Extent.Text })
        @($members | Where-Object { @('DownloadFile', 'WriteAllBytes', 'WriteAllText', 'WriteAllLines', 'AppendAllText') -contains $_ }) | Should -BeNullOrEmpty
        @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.FileRedirectionAst] }, $true)) | Should -BeNullOrEmpty
    }

    It 'Test-FpsElevated uses the WindowsBuiltInRole enum and returns the real elevation as a bool' {
        $ast = [Management.Automation.Language.Parser]::ParseInput((Get-RunTemplate), [ref]$null, [ref]$null)
        $def = $ast.Find({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Test-FpsElevated' }, $true)
        $def | Should -Not -BeNullOrEmpty
        $def.Extent.Text -cmatch 'WindowsBuiltInRole' | Should -BeTrue
        $def.Extent.Text -cmatch 'WindowsPrincipal' | Should -BeTrue
        $actual = & ([scriptblock]::Create($def.Extent.Text + "`nTest-FpsElevated"))
        $expected = (New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $actual | Should -BeOfType [bool]
        $actual | Should -Be $expected
    }

    It 'when not elevated re-launches itself elevated with the one-liner and does nothing else' {
        Mock Test-FpsElevated { $false }
        Mock Start-Process { }
        Mock Get-FpsBundleBytes { throw 'must not download before elevation' }
        $run = New-FilledRun ('0' * 64)
        $r = Invoke-FilledRun $run
        Should -Invoke Start-Process -Times 1 -Exactly -ParameterFilter {
            $Verb -ceq 'RunAs' -and $FilePath -cmatch '(?i)powershell' -and ((@($ArgumentList) -join ' ') -cmatch '\|\s*iex')
        }
        Should -Invoke Get-FpsBundleBytes -Times 0 -Exactly
        Should -Invoke Invoke-RestMethod -Times 0 -Exactly
        Should -Invoke Invoke-WebRequest -Times 0 -Exactly
        @(Get-ChildItem -LiteralPath $r.Cwd -Force).Count | Should -Be 0
    }

    It 'refuses tampered bytes: names SHA-256, exits non-zero, runs nothing' {
        $marker = Join-Path $TestDrive ('marker-' + [guid]::NewGuid().ToString('N') + '.txt')
        $good = "Set-Content -LiteralPath '$marker' -Value 'ran'`n"
        $bad = "Set-Content -LiteralPath '$marker' -Value 'tampered'`n"
        $served = $script:utf8.GetBytes($bad)
        Mock Test-FpsElevated { $true }
        Mock Start-Process { }
        Mock Get-FpsBundleBytes ({ , [byte[]]$served }.GetNewClosure())
        $run = New-FilledRun (Get-Sha256Hex $script:utf8.GetBytes($good))
        $r = Invoke-FilledRun $run
        Should -Invoke Get-FpsBundleBytes -Times 1 -Exactly -ParameterFilter { $Url -ceq $script:testUrl }
        Test-Path -LiteralPath $marker | Should -BeFalse -Because 'nothing runs on a hash mismatch'
        $r.ExitCode | Should -Not -Be 0
        ($r.Output -join "`n") -cmatch 'SHA-256' | Should -BeTrue -Because 'the refusal says why'
        Should -Invoke Start-Process -Times 0 -Exactly
    }

    It 'runs matching bytes as a scriptblock after enabling TLS 1.2 and writes no file' {
        $marker = Join-Path $TestDrive ('marker-' + [guid]::NewGuid().ToString('N') + '.txt')
        $payload = "Set-Content -LiteralPath '$marker' -Value 'ran'`n"
        $served = $script:utf8.GetBytes($payload)
        Mock Test-FpsElevated { $true }
        Mock Get-FpsBundleBytes ({ , [byte[]]$served }.GetNewClosure())
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls11
        $tempBefore = @(Get-ChildItem -LiteralPath $env:TEMP -File -Filter '*.ps1' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
        $run = New-FilledRun (Get-Sha256Hex $served)
        $r = Invoke-FilledRun $run
        $tls12 = [Net.SecurityProtocolType]::Tls12
        ([Net.ServicePointManager]::SecurityProtocol -band $tls12) | Should -Be $tls12
        Test-Path -LiteralPath $marker | Should -BeTrue -Because ($r.Output -join "`n")
        @(Get-ChildItem -LiteralPath $r.Cwd -Force).Count | Should -Be 0
        $tempAfter = @(Get-ChildItem -LiteralPath $env:TEMP -File -Filter '*.ps1' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
        @($tempAfter | Where-Object { $tempBefore -notcontains $_ }) | Should -BeNullOrEmpty
    }

    It 'decodes the bundle as UTF-8 so Turkish text survives download and decode' {
        $global:FpsTestTurkish = $null
        $payload = "`$global:FpsTestTurkish = '" + $script:turkish + "'`n"
        $served = $script:utf8.GetBytes($payload)
        Mock Test-FpsElevated { $true }
        Mock Get-FpsBundleBytes ({ , [byte[]]$served }.GetNewClosure())
        $run = New-FilledRun (Get-Sha256Hex $served)
        try {
            $r = Invoke-FilledRun $run
            $global:FpsTestTurkish | Should -BeExactly $script:turkish -Because ($r.Output -join "`n")
        }
        finally { Remove-Variable -Name FpsTestTurkish -Scope Global -ErrorAction SilentlyContinue }
    }
}
