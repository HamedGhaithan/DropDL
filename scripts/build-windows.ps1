$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

& "$Root\scripts\build-backend-windows.ps1"
Set-Location "$Root\frontend"
npm install
npm run tauri build
