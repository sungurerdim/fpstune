# fpstune Launcher (PowerShell)
# Run as: .\start.ps1 or right-click > Run with PowerShell

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "fpstune"

# Set UTF-8 encoding and disable colors for clean output
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:NO_COLOR = "1"

# Load user profile if exists (for Conda, nvm, etc.)
if (Test-Path $PROFILE) {
    try { . $PROFILE } catch { }
}

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host "   fpstune - Gaming Performance Optimizer" -ForegroundColor Cyan
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
Set-Location $PSScriptRoot

# Check Python (try python, then py launcher)
$pythonCmd = $null
$pythonVersion = $null

# Try 'python' first
try {
    $pythonVersion = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "python"
    }
} catch {}

# Try 'py' launcher if python failed
if (-not $pythonCmd) {
    try {
        $pythonVersion = & py --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = "py"
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "[ERROR] Python not found!" -ForegroundColor Red
    Write-Host "        Install Python 3.11+ or run from Anaconda Prompt." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Found: $pythonCmd ($pythonVersion)" -ForegroundColor Green

# Check Node (try node, then common paths)
$nodeCmd = $null
$nodeVersion = $null

# Try 'node' in PATH first
try {
    $nodeVersion = & node --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $nodeCmd = "node"
    }
} catch {}

# Try common installation paths
if (-not $nodeCmd) {
    $nodePaths = @(
        "$env:ProgramFiles\nodejs\node.exe",
        "$env:LOCALAPPDATA\Programs\nodejs\node.exe",
        "$env:APPDATA\nvm\current\node.exe"
    )

    foreach ($path in $nodePaths) {
        if (Test-Path $path) {
            $nodeCmd = $path
            $nodeDir = Split-Path $path -Parent
            $env:PATH = "$nodeDir;$env:PATH"
            $nodeVersion = & $nodeCmd --version 2>&1
            break
        }
    }
}

if (-not $nodeCmd) {
    Write-Host "[ERROR] Node.js not found!" -ForegroundColor Red
    Write-Host "        Install Node.js 18+ from https://nodejs.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] Found: node ($nodeVersion)" -ForegroundColor Green

# Install Python package if needed
if (-not (Test-Path "src\fpstune.egg-info")) {
    Write-Host "[*] Installing fpstune package..." -ForegroundColor Yellow
    & $pythonCmd -m pip install -e . -q
}

# Install frontend dependencies if needed (check for vite binary, not just folder)
if (-not (Test-Path "frontend\node_modules\.bin\vite.cmd")) {
    Write-Host "[*] Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location frontend
    # Remove broken node_modules if exists
    if (Test-Path "node_modules") {
        Write-Host "    Cleaning old node_modules..." -ForegroundColor Gray
        Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
    }
    npm install
    Pop-Location
}

Write-Host ""
Write-Host "[*] Starting servers..." -ForegroundColor Green

# Start backend as a background job
$backendJob = Start-Job -ScriptBlock {
    param($pythonCmd, $workDir)
    Set-Location $workDir
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = "utf-8"
    $env:NO_COLOR = "1"
    & $pythonCmd -m uvicorn fpstune.api.main:app --host 127.0.0.1 --port 8000 2>&1
} -ArgumentList $pythonCmd, $PSScriptRoot

# Start frontend as a background job
$frontendJob = Start-Job -ScriptBlock {
    param($workDir)
    Set-Location "$workDir\frontend"
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $env:NO_COLOR = "1"
    $env:FORCE_COLOR = "0"
    npm run dev 2>&1
} -ArgumentList $PSScriptRoot

# Wait for servers to start
Write-Host "[*] Waiting for servers..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Open browser
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "  ========================================" -ForegroundColor Green
Write-Host "   fpstune is running!" -ForegroundColor Green
Write-Host "  ========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Web UI:  " -NoNewline; Write-Host "http://localhost:5173" -ForegroundColor Cyan
Write-Host "   API:     " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Press Ctrl+C to stop..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  ----------------------------------------" -ForegroundColor DarkGray
Write-Host "   Server Logs:" -ForegroundColor DarkGray
Write-Host "  ----------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# Monitor jobs and display output
try {
    while ($true) {
        # Get and display backend output
        $backendOutput = Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
        if ($backendOutput) {
            $backendOutput | ForEach-Object {
                Write-Host "[API] $_" -ForegroundColor DarkCyan
            }
        }

        # Get and display frontend output
        $frontendOutput = Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue
        if ($frontendOutput) {
            $frontendOutput | ForEach-Object {
                Write-Host "[WEB] $_" -ForegroundColor DarkMagenta
            }
        }

        # Check if jobs are still running
        if ($backendJob.State -eq "Failed" -or $frontendJob.State -eq "Failed") {
            Write-Host "[ERROR] A server crashed!" -ForegroundColor Red
            break
        }

        Start-Sleep -Milliseconds 500
    }
}
finally {
    # Cleanup on Ctrl+C or exit
    Write-Host ""
    Write-Host "[*] Stopping servers..." -ForegroundColor Yellow

    Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
    Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue
    Remove-Job -Job $frontendJob -Force -ErrorAction SilentlyContinue

    # Kill any remaining processes on our ports
    $connections = Get-NetTCPConnection -LocalPort 8000,5173 -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[*] Done!" -ForegroundColor Green
}
