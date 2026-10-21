@echo off
setlocal
:: fpstune from a source checkout: double-click to start. See start.ps1.
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %errorlevel%
