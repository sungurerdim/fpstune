@echo off
setlocal
:: fpstune from a source checkout: double-click to start. See start.ps1.
::
:: Elevation has one owner: fpstune itself. start.ps1 starts the project's
:: interpreter and fpstune re-launches itself elevated through ShellExecute. The
:: window this script opened closes a few seconds later and the elevated one
:: stays. The bat used to attempt the UAC step first; on machines where that
:: attempt is cancelled or refused the user got a second prompt and a second
:: window, and a double-click that looked like nothing happened.
chcp 65001 >nul
cd /d "%~dp0"
set "LOG=%TEMP%\fpstune-start.log"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" (
    echo.
    echo fpstune exited with code %CODE%.
    echo Startup log: "%LOG%"
    pause
)
exit /b %CODE%
