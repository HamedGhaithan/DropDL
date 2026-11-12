@echo off
cd /d "%~dp0"
if exist "%~dp0DropDL.exe" (
  start "" "%~dp0DropDL.exe"
) else (
  wscript.exe "%~dp0Launch-DropDL.vbs"
)
