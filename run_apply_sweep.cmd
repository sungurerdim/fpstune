@echo off
rem Run the apply sweep without changing the machine's ExecutionPolicy.
rem The sweep itself must be elevated; this wrapper asks for elevation first.
net session >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_apply_sweep.ps1" %*
exit /b %errorlevel%
