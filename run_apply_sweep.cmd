@echo off
rem Run the apply sweep without changing the machine's ExecutionPolicy.
rem The sweep itself must be elevated; this wrapper asks for elevation first.
rem -DryRun writes nothing, so it deliberately skips the UAC prompt.
if /I "%~1"=="-DryRun" goto run
powershell.exe -NoProfile -Command "if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { if ('%*' -ne '') { Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs -Wait -ErrorAction Stop } else { Start-Process -FilePath '%~f0' -Verb RunAs -Wait -ErrorAction Stop }; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    if errorlevel 1 (
        echo.
        echo UAC penceresi acilmadi veya iptal edildi.
        echo PowerShell'i "Yonetici olarak calistir" ile acip sunu calistir:
        echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_apply_sweep.ps1"
        pause
        exit /b 1
    )
    exit /b 0
)
:run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_apply_sweep.ps1" %*
exit /b %errorlevel%
