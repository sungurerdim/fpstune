@echo off
:: fpstune Launcher - Requires Administrator privileges
:: Auto-elevates to admin if not already running as admin

:: Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ==========================================
    echo   fpstune requires Administrator privileges
    echo  ==========================================
    echo.
    echo  Requesting elevation...
    echo.

    :: Re-run this script with admin privileges
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: We have admin privileges - continue with normal startup
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
start "" powershell -NoExit -ExecutionPolicy Bypass -Command "& '%~dp0start.ps1'"
