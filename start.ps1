# fpstune from a source checkout.
#
# Needs only uv (https://docs.astral.sh/uv/): it installs Python 3.12 and, through
# the dev extra, Node.js into this project, then runs fpstune. fpstune asks for
# Administrator itself. Arguments are passed through: .\start.ps1 --dev
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv was not found." -ForegroundColor Red
    Write-Host "Install it with:  winget install --id astral-sh.uv -e" -ForegroundColor Yellow
    Write-Host "then open a new terminal and run this script again."
    Read-Host "Press Enter to close"
    exit 1
}

uv sync --locked --extra dev --python 3.12
if ($LASTEXITCODE -ne 0) {
    Write-Host "uv sync failed (exit code $LASTEXITCODE)." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit $LASTEXITCODE
}

& uv run --locked fpstune serve @args
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host "fpstune exited with code $code." -ForegroundColor Red
    if ($Host.Name -eq "ConsoleHost") { Read-Host "Press Enter to close" }
}
exit $code
