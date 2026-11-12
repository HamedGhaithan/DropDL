$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
if (Test-Path "$Root\setup-env.ps1") { . "$Root\setup-env.ps1" }
if (!(Test-Path "frontend\dist\index.html")) { throw "The built interface is missing. Build frontend first with npm run build." }
if (!(Test-Path ".venv")) {
  py -3 -m venv .venv
  if ($LASTEXITCODE) { throw "Install Python 3.11 or later first." }
}
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt pywebview
if ($LASTEXITCODE) { throw "Dependency installation failed. Check your internet connection." }
$env:HOST = "127.0.0.1"
$env:PORT = "17321"
& .\.venv\Scripts\python.exe backend\desktop.py
