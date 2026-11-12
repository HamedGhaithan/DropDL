$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (!(Test-Path ".venv")) {
  py -3 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\.venv\Scripts\pyinstaller.exe --clean --noconfirm dropdl-backend.spec

$Target = "frontend\src-tauri\binaries\dropdl-backend-x86_64-pc-windows-msvc.exe"
New-Item -ItemType Directory -Force "frontend\src-tauri\binaries" | Out-Null
Copy-Item "dist\dropdl-backend.exe" $Target -Force
Write-Host "Backend sidecar staged at $Target" -ForegroundColor Green
