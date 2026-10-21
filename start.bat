@echo off
setlocal
:: fpstune from a source checkout: double-click to start. See start.ps1.
chcp 65001 >nul
cd /d "%~dp0"

:: fpstune itself needs Administrator. Ask here, before PowerShell starts, and
:: wait for the elevated copy: the old path let the non-elevated window exit
:: while the user was still looking at the UAC prompt, so a double-click
:: appeared to do nothing.
powershell.exe -NoProfile -Command "if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs -Wait -ErrorAction Stop; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    if errorlevel 1 (
        echo.
        echo Administrator rights are required to run fpstune.
        echo Right-click this file and choose "Run as administrator".
        pause
        exit /b 1
    )
    exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" (
    echo.
    echo fpstune exited with code %CODE%.
    pause
)
exit /b %CODE%
