<#
.SYNOPSIS
  Restores the pinned Pester 5 version into runtime/.modules (git-ignored).
.DESCRIPTION
  Dev/CI tooling only. Idempotent: if the pinned version is already present it
  does nothing and exits 0. Fails closed (exit 1) when the gallery is
  unreachable or the downloaded package does not match the pinned hash.
  Runs under Windows PowerShell 5.1 and pwsh. Does not use PowerShellGet.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'pester.pin.ps1')

$runtimeRoot = Split-Path -Parent $PSScriptRoot
$modulesRoot = Join-Path $runtimeRoot '.modules'
$target = Join-Path (Join-Path $modulesRoot 'Pester') $PesterVersion
$manifest = Join-Path $target 'Pester.psd1'

if (Test-Path -LiteralPath $manifest) {
    Write-Host "Pester $PesterVersion is already present: $target"
    exit 0
}

$workDir = Join-Path ([IO.Path]::GetTempPath()) ('pester-restore-' + [Guid]::NewGuid().ToString('N'))
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $workDir | Out-Null
    $package = Join-Path $workDir 'pester.nupkg'
    $url = "https://www.powershellgallery.com/api/v2/package/Pester/$PesterVersion"

    Write-Host "Downloading Pester $PesterVersion from the PowerShell Gallery..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $package -UseBasicParsing
    }
    catch {
        throw "PowerShell Gallery is unreachable or the package is missing ($url): $($_.Exception.Message)"
    }

    $sha = [Security.Cryptography.SHA512]::Create()
    $stream = [IO.File]::OpenRead($package)
    try { $actual = [Convert]::ToBase64String($sha.ComputeHash($stream)) }
    finally { $stream.Dispose(); $sha.Dispose() }
    if ($actual -ne $PesterPackageHash) {
        throw "Pester package hash mismatch. Expected $PesterPackageHash but got $actual."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $extract = Join-Path $workDir 'extract'
    [IO.Compression.ZipFile]::ExtractToDirectory($package, $extract)
    if (-not (Test-Path -LiteralPath (Join-Path $extract 'Pester.psd1'))) {
        throw 'Package layout unexpected: Pester.psd1 not found.'
    }
    # Drop NuGet packaging metadata; keep only the module files.
    foreach ($junk in '_rels', 'package', '[Content_Types].xml') {
        $p = Join-Path $extract $junk
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
    }
    Get-ChildItem -LiteralPath $extract -Filter '*.nuspec' | Remove-Item -Force

    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Move-Item -LiteralPath $extract -Destination $target
    Write-Host "Restored Pester $PesterVersion to $target"
    exit 0
}
catch {
    [Console]::Error.WriteLine("restore.ps1 failed: $($_.Exception.Message)")
    exit 1
}
finally {
    if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue }
}
