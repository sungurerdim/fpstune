# Clean Install Script for fpstune frontend
# Removes node_modules and package-lock.json, then reinstalls dependencies

$ErrorActionPreference = "Stop"

Write-Host "Cleaning frontend dependencies..." -ForegroundColor Cyan

# Get script directory and navigate to frontend
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Split-Path -Parent $scriptDir

Push-Location $frontendDir

try {
    # Remove node_modules
    if (Test-Path "node_modules") {
        Write-Host "Removing node_modules..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force "node_modules"
    }

    # Remove package-lock.json
    if (Test-Path "package-lock.json") {
        Write-Host "Removing package-lock.json..." -ForegroundColor Yellow
        Remove-Item -Force "package-lock.json"
    }

    # Clear npm cache (optional but helps with platform-specific issues)
    Write-Host "Clearing npm cache..." -ForegroundColor Yellow
    npm cache clean --force 2>$null

    # Install dependencies
    Write-Host "Installing dependencies..." -ForegroundColor Green
    npm install

    Write-Host "`nDone! Dependencies installed successfully." -ForegroundColor Green
}
catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
