# fpstune from a source checkout.
#
# Needs only uv (https://docs.astral.sh/uv/): it installs Python 3.12 and, through
# the dev extra, Node.js into this project, then runs fpstune. fpstune asks for
# Administrator itself. Arguments are passed through: .\start.ps1 --dev
#
# Everything this script and the fpstune it starts print is appended to
# %TEMP%\fpstune-start.log, so a window that closes too fast still leaves a
# reason behind. start.bat prints the same path when it exits nonzero.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$log = Join-Path $env:TEMP "fpstune-start.log"
function Write-Log([string]$message) {
    try {
        Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message)
    } catch {
        # A log that cannot be written must not stop the launcher.
    }
}

Write-Log "start.ps1 cwd=$PSScriptRoot args=$($args -join ' ')"
Write-Log "user=$env:USERNAME elevated=$(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv was not found." -ForegroundColor Red
    Write-Host "Install it with:  winget install --id astral-sh.uv -e" -ForegroundColor Yellow
    Write-Host "then open a new terminal and run this script again."
    Read-Host "Press Enter to close"
    exit 1
}

# Sync only when the environment is missing or out of date. It used to run on
# every start, which made `uv` spawn and reap a sync child each time and left a
# second interpreter in the tree beside the one that serves — so one double-click
# looked like several fpstune processes with several windows.
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$needsSync = -not (Test-Path $python)
if (-not $needsSync) {
    # A present file is not a working interpreter: .venv is a junction, and a
    # moved or half-repaired target leaves an executable that cannot start. One
    # cheap import decides it, and a broken environment is repaired instead of
    # closing the window on a traceback.
    & $python -c "import sys" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "the environment interpreter does not run (exit $LASTEXITCODE); re-syncing"
        $needsSync = $true
    }
}

if ($needsSync) {
    Write-Log "uv sync --locked --extra dev --python 3.12"
    uv sync --locked --extra dev --python 3.12
    if ($LASTEXITCODE -ne 0) {
        Write-Log "uv sync failed (exit code $LASTEXITCODE)"
        Write-Host "uv sync failed (exit code $LASTEXITCODE)." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit $LASTEXITCODE
    }
}

# Start the environment's own interpreter rather than `uv run`: uv keeps a process
# of its own between this script and fpstune, and a stop request addressed to
# fpstune leaves that parent behind.
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights are required; Windows will ask for permission (UAC)." -ForegroundColor Yellow
    Write-Host "This window closes and the elevated one stays open."
}
Write-Log "starting $python -m fpstune.cli serve $($args -join ' ')"
& $python -m fpstune.cli serve @args 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
Write-Log "fpstune exited with code $code"
if ($code -ne 0) {
    Write-Host "fpstune exited with code $code." -ForegroundColor Red
    Write-Host "Startup log: $log" -ForegroundColor Yellow
    if ($Host.Name -eq "ConsoleHost") { Read-Host "Press Enter to close" }
}
exit $code
