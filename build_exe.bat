@echo off
setlocal
:: fpstune - build the current tree into dist\fpstune.exe and say where it landed.
:: Double-click to rebuild after a pull. Pass --no-pause when calling from a script.
::
:: The same steps as .github\workflows\release.yml, minus the test suite: Python
:: dependencies from the lockfile (PyInstaller among them), the UI bundle the exe
:: serves from inside itself, then PyInstaller over fpstune.spec. Each step stops
:: the build when it fails, so a stale UI can never be packaged as a new build.

chcp 65001 >nul
cd /d "%~dp0"

where uv >nul 2>&1 || (echo uv was not found on PATH. Install it: https://docs.astral.sh/uv/ & goto :fail)
where npm >nul 2>&1 || (echo npm was not found on PATH. Install Node.js LTS: https://nodejs.org/ & goto :fail)

echo [1/3] Python dependencies (uv sync --frozen --extra dev)
call uv sync --frozen --extra dev || goto :fail

echo [2/3] UI bundle (npm install, npm run build)
pushd frontend
call npm install || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd

echo [3/3] Executable (pyinstaller fpstune.spec)
call uv run pyinstaller fpstune.spec --noconfirm --clean || goto :fail

if not exist "dist\fpstune.exe" (echo PyInstaller finished but dist\fpstune.exe is missing. & goto :fail)

for %%F in ("dist\fpstune.exe") do (set "EXE=%%~fF" & set "SIZE=%%~zF")
for /f "delims=" %%V in ('uv run python -c "from fpstune import __version__; print(__version__)"') do set "VERSION=%%V"
set /a SIZE_MB=%SIZE% / 1048576

echo.
echo   Build complete: fpstune %VERSION%
echo   Executable: %EXE%
echo   Folder:     %~dp0dist
echo   Size:       %SIZE_MB% MB
echo.
if /i not "%~1"=="--no-pause" pause
exit /b 0

:fail
echo.
echo   Build failed. See the messages above.
if /i not "%~1"=="--no-pause" pause
exit /b 1
