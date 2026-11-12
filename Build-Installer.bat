@echo off
setlocal
cd /d "%~dp0"
title DropDL Studio - Build installer
echo === DropDL Studio 2.3.0 installer build ===
where makensis >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" (set "PATH=%ProgramFiles(x86)%\NSIS;%PATH%") else if exist "%ProgramFiles%\NSIS\makensis.exe" (set "PATH=%ProgramFiles%\NSIS;%PATH%") else (
    echo NSIS not found - installing it with winget...
    winget install -e --id NSIS.NSIS --silent --accept-package-agreements --accept-source-agreements
    if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set "PATH=%ProgramFiles(x86)%\NSIS;%PATH%"
  )
)
where makensis >nul 2>nul || (echo Could not find NSIS. Install it from https://nsis.sourceforge.io and run this file again. & pause & exit /b 1)
where python >nul 2>nul || (echo Python 3 is required to run the packager. & pause & exit /b 1)
where node >nul 2>nul
if not errorlevel 1 (
  echo Rebuilding the interface with Vite...
  pushd frontend
  if not exist node_modules call npm ci
  call npm run build || echo Vite build failed - using the prebuilt interface in frontend\dist.
  popd
)
python scripts\build-installer.py --output dist\DropDL-Setup.exe
if errorlevel 1 (echo Installer build failed. & pause & exit /b 1)
echo.
echo Done: %~dp0dist\DropDL-Setup.exe
explorer /select,"%~dp0dist\DropDL-Setup.exe"
pause
