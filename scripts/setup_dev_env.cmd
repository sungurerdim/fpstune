@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_dev_env.ps1" %*
exit /b %errorlevel%
