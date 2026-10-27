# Schema contract for tweaks/<category>/<name>.json.
#
# The schema is validated by pwsh Test-Json (draft 2020-12), which Windows
# PowerShell 5.1 does not have. Each fixture is therefore checked in a child
# `pwsh -NoProfile -Command Test-Json ...` process and the test asserts on its
# boolean. Paths travel in environment variables so no quoting is involved.
# Without pwsh on PATH the tests are skipped (CI always has pwsh).
#
# Every invalid fixture is a copy of a valid one with exactly one defect, and
# the table below names the rule it breaks.
BeforeDiscovery {
    $script:pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    $script:skipReason = -not $script:pwsh
    if ($script:skipReason) {
        Write-Warning 'pwsh not found on PATH: schema checks are skipped (they need PowerShell 7 Test-Json; CI has it).'
    }
    $fixtureRoot = Join-Path $PSScriptRoot 'fixtures/schema'

    $script:validCases = @(Get-ChildItem -LiteralPath (Join-Path $fixtureRoot 'valid') -Filter '*.json' | ForEach-Object {
            @{ Name = $_.BaseName; Path = $_.FullName }
        })

    # fixture file name (without .json) -> rule it must violate
    $rules = [ordered]@{
        'text-title-missing-tr'      = 'tr missing in title'
        'text-why-missing-tr'        = 'tr missing in why'
        'text-fixed-missing-tr'      = 'tr missing in fixed'
        'text-steps-missing-tr'      = 'tr missing in steps'
        'text-risknote-missing-tr'   = 'tr missing in riskNote'
        'why-without-period'         = 'why (en) must end with a period'
        'why-tr-without-period'      = 'why (tr) must end with a period'
        'manual-with-apply'          = 'manual row must not have apply'
        'tweak-without-apply'        = 'tweak requires apply'
        'tweak-without-revert'       = 'tweak requires revert'
        'tweak-without-detect'       = 'tweak requires detect'
        'advanced-without-risknote'  = 'advanced risk requires riskNote'
        'moderate-one-source'        = 'moderate risk requires at least 2 sources'
        'advanced-one-source'        = 'advanced risk requires at least 2 sources'
        'target-value-and-command'   = 'target takes value or command, not both'
        'gain-unknown-kind'          = 'gain only allows the known impact kinds'
        'gain-number-in-list'        = 'gain must not contain numbers'
        'gain-number-map'            = 'gain is a list, not a number map'
        'unknown-top-level-id'       = 'id is derived from the path, not a field'
        'unknown-top-level-scope'    = 'unknown top-level property'
    }
    $script:invalidCases = @(foreach ($key in $rules.Keys) {
            @{ Name = $key; Rule = $rules[$key]; Path = Join-Path $fixtureRoot "invalid/$key.json" }
        })
    $script:schemaPath = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'schema/tweak.schema.json'
}

BeforeAll {
    $script:schemaPath = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'schema/tweak.schema.json'
    $script:pwshExe = (Get-Command pwsh -ErrorAction SilentlyContinue).Source

    # Returns @{ Result = 'True'|'False'|'THROW'; Detail = <messages> }.
    function script:Invoke-SchemaCheck([string]$JsonPath) {
        $env:FPSTUNE_SCHEMA_JSON = $JsonPath
        $env:FPSTUNE_SCHEMA_FILE = $script:schemaPath
        try {
            $command = '$e = $null; try { $r = Test-Json -Path $env:FPSTUNE_SCHEMA_JSON -SchemaFile $env:FPSTUNE_SCHEMA_FILE -ErrorAction SilentlyContinue -ErrorVariable e; Write-Output (''RESULT:'' + $r) } catch { Write-Output (''RESULT:THROW'') ; Write-Output $_.Exception.Message }; $e | ForEach-Object { Write-Output $_.Exception.Message }'
            $lines = @(& $script:pwshExe -NoProfile -NonInteractive -Command $command 2>&1 | ForEach-Object { "$_" })
        }
        finally {
            Remove-Item Env:\FPSTUNE_SCHEMA_JSON, Env:\FPSTUNE_SCHEMA_FILE -ErrorAction SilentlyContinue
        }
        $resultLine = $lines | Where-Object { $_ -like 'RESULT:*' } | Select-Object -First 1
        $result = if ($resultLine) { $resultLine.Substring(7) } else { 'THROW' }
        @{ Result = $result; Detail = ($lines -join ' | ') }
    }
}

Describe 'Tweak schema' {
    It 'exists and loads as a JSON Schema' -Skip:$script:skipReason {
        Test-Path -LiteralPath $script:schemaPath | Should -BeTrue
        $r = Invoke-SchemaCheck (Join-Path $PSScriptRoot 'fixtures/schema/valid/registry.json')
        $r.Result | Should -Not -Be 'THROW' -Because $r.Detail
    }

    It 'accepts valid fixture <Name>' -Skip:$script:skipReason -ForEach $script:validCases {
        $r = Invoke-SchemaCheck $Path
        $r.Result | Should -Be 'True' -Because $r.Detail
    }

    It 'rejects <Name>: <Rule>' -Skip:$script:skipReason -ForEach $script:invalidCases {
        Test-Path -LiteralPath $Path | Should -BeTrue
        $r = Invoke-SchemaCheck $Path
        $r.Result | Should -Be 'False' -Because $r.Detail
    }
}
