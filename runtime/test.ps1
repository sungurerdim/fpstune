<#
.SYNOPSIS
  The one test entry for the runtime tree. Exit code = number of failed tests.
.PARAMETER Path
  File or folder of Pester tests. Default: runtime/tests.
.PARAMETER Tag
  Run only tests with these tags.
.PARAMETER ExcludeTag
  Skip tests with these tags.
.PARAMETER Culture
  Culture name (e.g. fr-FR, tr-TR) applied to the thread CurrentCulture and
  CurrentUICulture for the whole run.
.DESCRIPTION
  Imports Pester only from the folder restored by tools/restore.ps1 and never
  the inbox 3.4.0. Fails closed when the pinned version is missing.
#>
[CmdletBinding()]
param(
    [string[]]$Path,
    [string[]]$Tag,
    [string[]]$ExcludeTag,
    [string]$Culture
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot is not reliable inside param() defaults on Windows PowerShell 5.1.
if (-not $Path) { $Path = @(Join-Path $PSScriptRoot 'tests') }

function Stop-Run([string]$Message) {
    [Console]::Error.WriteLine($Message)
    Write-Host 'Failed: 1'
    exit 1
}

. (Join-Path (Join-Path $PSScriptRoot 'tools') 'pester.pin.ps1')

$manifest = Join-Path (Join-Path (Join-Path (Join-Path $PSScriptRoot '.modules') 'Pester') $PesterVersion) 'Pester.psd1'
if (-not (Test-Path -LiteralPath $manifest)) {
    Stop-Run "Pester $PesterVersion is not restored. Run: powershell -NoProfile -ExecutionPolicy Bypass -File runtime/tools/restore.ps1"
}

if ($Culture) {
    try { $ci = New-Object Globalization.CultureInfo($Culture) }
    catch { Stop-Run "Invalid -Culture '$Culture'." }
    if ($ci.Name -ne $Culture) { Stop-Run "Unknown culture '$Culture'." }
    [Threading.Thread]::CurrentThread.CurrentCulture = $ci
    [Threading.Thread]::CurrentThread.CurrentUICulture = $ci
    [Globalization.CultureInfo]::DefaultThreadCurrentCulture = $ci
    [Globalization.CultureInfo]::DefaultThreadCurrentUICulture = $ci
    # Lets tests assert that the switch took effect.
    $env:FPSTUNE_TEST_CULTURE = $ci.Name
}
else {
    Remove-Item Env:\FPSTUNE_TEST_CULTURE -ErrorAction SilentlyContinue
}

foreach ($p in $Path) {
    if (-not (Test-Path -LiteralPath $p)) { Stop-Run "Test path not found: $p" }
}

# Drop any already-loaded Pester (e.g. inbox 3.4.0) before importing the pinned one.
Get-Module Pester | Remove-Module -Force
Import-Module $manifest -Force
$loaded = Get-Module Pester
if (-not $loaded -or $loaded.Version.ToString() -ne $PesterVersion) {
    Stop-Run "Loaded Pester is not the pinned $PesterVersion."
}

$config = New-PesterConfiguration
$config.Run.Path = $Path
$config.Run.PassThru = $true
$config.Output.Verbosity = 'Normal'
if ($Tag) { $config.Filter.Tag = $Tag }
if ($ExcludeTag) { $config.Filter.ExcludeTag = $ExcludeTag }

$result = Invoke-Pester -Configuration $config

# Failed tests plus failed blocks/containers (discovery or setup errors) so a
# broken test file can never read as green.
$failed = [int]$result.FailedCount + [int]$result.FailedBlocksCount + [int]$result.FailedContainersCount
Write-Host "Failed: $failed"
exit $failed
