# Create the persistent developer venv and the .venv junction.
#
# The repo path itself breaks CPython's venv launcher on this Windows install:
# every venv created under D:\GitHub\fpstune starts with "No pyvenv.cfg file".
# A venv created outside the repo works, so this script creates one under
# %LOCALAPPDATA%\fpstune\venv and links .venv to it. The link is the only thing
# in the repo; the environment survives a checkout/clean.
#
# Run:  powershell -ExecutionPolicy Bypass -File scripts\setup_dev_env.ps1
#   or: scripts\setup_dev_env.cmd

param(
    [string]$Target = (Join-Path $env:LOCALAPPDATA 'fpstune\venv'),
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo '.venv'

if (Test-Path -LiteralPath $venv) {
    $item = Get-Item -LiteralPath $venv -Force
    if ($item.LinkType -ne 'Junction') {
        throw "$venv exists and is not a junction. Refusing to delete a real environment; remove it yourself if that is intended."
    }
    # Windows PowerShell 5.1 Remove-Item on a junction can throw
    # NullReferenceException; rmdir removes the link and leaves its target.
    & cmd.exe /c rmdir "$venv"
    if (Test-Path -LiteralPath $venv) {
        throw "could not remove the junction at $venv"
    }
}

if ($Recreate -and (Test-Path -LiteralPath $Target)) {
    Remove-Item -LiteralPath $Target -Recurse -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $Target 'Scripts\python.exe'))) {
    $base = (& uv python find 3.12).Trim()
    if (-not $base -or -not (Test-Path -LiteralPath $base)) {
        throw 'uv could not find CPython 3.12; install it with: uv python install 3.12'
    }
    Write-Host "creating $Target from $base"
    & $base -m venv $Target
} else {
    Write-Host "reusing $Target"
}

# uv's bundled CPython writes an `executable` path containing the full version
# (cpython-3.12.13-windows...) that does not exist; the launcher still works but
# the stale path confuses tools that read pyvenv.cfg. Point it at the real one.
$cfg = Join-Path $Target 'pyvenv.cfg'
if (Test-Path -LiteralPath $cfg) {
    $base = (& uv python find 3.12).Trim()
    (Get-Content -LiteralPath $cfg) -replace '^executable = .*', "executable = $base" |
        Set-Content -LiteralPath $cfg -Encoding utf8
}

New-Item -ItemType Junction -Path $venv -Target $Target | Out-Null
Write-Host "junction $venv -> $Target"

Push-Location $repo
try {
    uv sync --locked --extra dev --python 3.12
    uv run --extra dev python -c "import sys, pytest, fpstune; print('python:', sys.executable); print('pytest:', pytest.__version__); print('fpstune:', fpstune.__file__)"
} finally {
    Pop-Location
}
