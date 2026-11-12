$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (!(Test-Path ".venv")) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

$backend = Start-Process -PassThru -NoNewWindow -FilePath "$Root\.venv\Scripts\python.exe" -ArgumentList "$Root\backend\run.py"
try {
  Set-Location "$Root\frontend"
  npm install
  npm run dev
} finally {
  if (!$backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
