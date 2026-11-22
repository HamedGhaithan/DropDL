@echo off
title DropDL Web (private)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0web\start-private.ps1" %*
echo.
pause
