$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
if (Test-Path "$Root\setup-env.ps1") { . "$Root\setup-env.ps1" }
if (!(Test-Path ".venv")) { py -3 -m venv .venv; if ($LASTEXITCODE) { throw "Install Python 3.11 or later." } }
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt pywebview
if ($LASTEXITCODE) { throw "Dependency installation failed." }
if (!(Test-Path "frontend\dist\index.html")) { throw "Build the frontend first." }
& .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --onedir --windowed --name DropDL-Studio --icon installer\dropdl.ico --add-data "installer\dropdl.ico;installer" --paths backend --add-data "frontend\dist;frontend\dist" --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all webview --collect-all uvicorn backend\desktop.py
if ($LASTEXITCODE) { throw "Desktop build failed." }
Write-Host "Desktop folder: $Root\dist\DropDL-Studio" -ForegroundColor Green
Write-Host "Distribute the whole folder. FFmpeg, ffprobe, Node.js 22+ and WebView2 remain external prerequisites."
