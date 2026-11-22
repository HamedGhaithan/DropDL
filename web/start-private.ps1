<#
  DropDL Web, private mode: runs on THIS PC so your phone can use it, including for YouTube (with your own cookies).

  Easiest: double-click Start-DropDL-Web.bat in the repository folder. Or run:   powershell -File web\start-private.ps1

    -Tunnel     also open a free Cloudflare quick tunnel so it works away from home (needs cloudflared installed)
    -LocalOnly  only this PC can connect (no phone), handy for testing
    -DryRun     show the settings and the addresses, start nothing

  Settings you can override first (as environment variables): ACCESS_CODE, YTDLP_COOKIES_FILE, MAX_HEIGHT, MAX_FILESIZE_MB, ...
  Where things are kept: %LOCALAPPDATA%\DropDLWeb  (access-code.txt, cookies.txt, data\). Set DROPDLWEB_HOME to move it.
#>
param([int]$Port = 7860, [switch]$Tunnel, [switch]$LocalOnly, [switch]$DryRun, [switch]$AssumeYes)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$store = if ($env:DROPDLWEB_HOME) { $env:DROPDLWEB_HOME } else { Join-Path $env:LOCALAPPDATA 'DropDLWeb' }
New-Item -ItemType Directory -Force -Path $store | Out-Null

function Write-Step($text) { Write-Host ">> $text" -ForegroundColor Cyan }
function Set-Default($name, $value) { if (-not [Environment]::GetEnvironmentVariable($name)) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') } }

# 1. A Python that has what the server needs (the installed DropDL app's own Python works)
function Test-Python($exe, $prefix) {
  try { & $exe @prefix -c "import fastapi, uvicorn, yt_dlp" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}
$options = @()
if ($env:DROPDL_PYTHON) { $options += , @($env:DROPDL_PYTHON, @()) }
$installed = Join-Path $env:LOCALAPPDATA 'Programs\DropDLStudio\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $installed) { $options += , @($installed, @()) }
$repoVenv = Join-Path (Split-Path -Parent $here) '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $repoVenv) { $options += , @($repoVenv, @()) }
$options += , @('python', @())
$options += , @('py', @('-3'))
$python = $null
foreach ($option in $options) { if (Test-Python $option[0] $option[1]) { $python = $option; break } }
if (-not $python) {
  Write-Host "Python with fastapi, uvicorn and yt-dlp was not found." -ForegroundColor Red
  Write-Host "Install them with:  python -m pip install -r web\requirements.txt"
  exit 1
}

# 2. The access code (made once, kept in a file so it stays the same)
$codeFile = Join-Path $store 'access-code.txt'
if ($env:ACCESS_CODE) { $code = $env:ACCESS_CODE.Trim() }
elseif (Test-Path -LiteralPath $codeFile) { $code = (Get-Content -LiteralPath $codeFile -Raw).Trim() }
else {
  $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'                     # no 0/O or 1/I to mix up; 32 symbols, so no bias
  $bytes = New-Object byte[] 12
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $code = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
  Set-Content -LiteralPath $codeFile -Value $code -Encoding ascii
}
if ($code.Length -lt 8) { Write-Host 'The access code must be at least 8 characters.' -ForegroundColor Red; exit 1 }

# 3. YouTube cookies: your own, from a file only you can read. The desktop app's saved cookies are reused if you have them.
$desktopData = if ($env:DROPDL_DATA_ROOT) { $env:DROPDL_DATA_ROOT } else { Join-Path $env:LOCALAPPDATA 'DropDL' }
$choices = @($env:YTDLP_COOKIES_FILE, (Join-Path $store 'cookies.txt'), (Join-Path $desktopData 'cookies.txt')) | Where-Object { $_ }
$cookies = $choices | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1

# 3b. A cookies.txt you just exported to Downloads is picked up (and moved out of Downloads) when it is newer than the one in use.
#     Only the cookie NAMES are looked at, to tell whether the file is signed in to YouTube; values are never shown.
function Get-CookieCheck($path) {
  try { $lines = Get-Content -LiteralPath $path -TotalCount 5000 -ErrorAction Stop } catch { return $null }
  if (-not $lines -or $lines[0] -notmatch '^# (Netscape )?HTTP Cookie File') { return $null }
  $yt = @($lines | Where-Object { $_ -match '^(#HttpOnly_)?\.?youtube\.com\t' })
  if (-not $yt) { return $null }
  $names = $yt | ForEach-Object { ($_ -split "`t")[5] }
  [pscustomobject]@{ SignedIn = [bool]($names | Where-Object { $_ -in 'SAPISID', '__Secure-3PSID', '__Secure-1PSID', 'LOGIN_INFO' }) }
}
function Get-DownloadsFolder {
  try {
    $raw = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' -ErrorAction Stop).'{374DE290-123F-4565-9164-39C4925E467B}'
    if ($raw) { return [Environment]::ExpandEnvironmentVariables($raw) }
  } catch { }
  Join-Path $env:USERPROFILE 'Downloads'
}
if (-not $env:YTDLP_COOKIES_FILE) {
  $downloads = if ($env:DROPDLWEB_DOWNLOADS) { $env:DROPDLWEB_DOWNLOADS } else { Get-DownloadsFolder }
  $since = if ($cookies) { (Get-Item -LiteralPath $cookies).LastWriteTime } else { (Get-Date).AddDays(-14) }
  $fresh = Get-ChildItem -LiteralPath $downloads -Filter '*.txt' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt $since -and $_.Length -lt 2MB } | Sort-Object LastWriteTime -Descending |
    Where-Object { Get-CookieCheck $_.FullName } | Select-Object -First 1
  if ($fresh) {
    Write-Host ''
    Write-Host "  Found YouTube cookies you exported: $($fresh.Name) ($($fresh.LastWriteTime))" -ForegroundColor Green
    $answer = if ($AssumeYes) { 'y' } else { Read-Host '  Use them, and move the file out of Downloads so it is not left lying around? [Y/n]' }
    if ($answer -notmatch '^(n|no)$') {
      $target = Join-Path $store 'cookies.txt'
      Copy-Item -LiteralPath $fresh.FullName -Destination $target -Force
      Remove-Item -LiteralPath $fresh.FullName -Force
      $cookies = $target
      Write-Host "  Saved as $target" -ForegroundColor Green
    }
  }
}
if ($cookies) {
  $check = Get-CookieCheck $cookies
  if (-not $check) {
    Write-Host "  $cookies is not a Netscape cookies.txt with YouTube cookies in it, so YouTube stays off." -ForegroundColor Yellow
    $cookies = $null
  } elseif (-not $check.SignedIn) {
    Write-Host '  Warning: those cookies are not signed in to YouTube, so YouTube will probably still ask to confirm you are not a bot.' -ForegroundColor Yellow
    Write-Host '           Sign in on youtube.com first, then export again.' -ForegroundColor Yellow
  }
}

# 4. Settings for a private instance (anything you set beforehand wins)
$env:ACCESS_CODE = $code
$env:PORT = "$Port"
$env:HOST = if ($LocalOnly) { '127.0.0.1' } else { '0.0.0.0' }
Set-Default 'DATA_DIR' (Join-Path $store 'data')
Set-Default 'MAX_FILESIZE_MB' '3000'
Set-Default 'MAX_DURATION_MIN' '300'
Set-Default 'MAX_CLIP_MIN' '120'
Set-Default 'JOB_TTL_MIN' '120'
Set-Default 'DISK_QUOTA_MB' '20000'
Set-Default 'MAX_ACTIVE' '2'
Set-Default 'PER_IP_ACTIVE' '4'
Set-Default 'JOBS_PER_HOUR' '200'
Set-Default 'INFO_PER_MIN' '60'
Set-Default 'TRUSTED_PROXY_HOPS' $(if ($Tunnel) { '1' } else { '0' })
if ($cookies) { $env:YTDLP_COOKIES_FILE = $cookies; $env:YOUTUBE = 'on' }

# 5. Addresses to open on the phone
$lan = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback|VirtualBox|VMware|Tailscale|Bluetooth' } |
  ForEach-Object { $_.IPAddress })
$tailscale = $null
if (Get-Command tailscale -ErrorAction SilentlyContinue) { try { $tailscale = (& tailscale ip -4 2>$null | Select-Object -First 1) } catch { } }

Write-Host ''
Write-Host '  DropDL Web (private)' -ForegroundColor Green
Write-Host "  Access code : $code"
if ($cookies) { Write-Host "  YouTube     : ON, using the cookies in $cookies" }
else {
  Write-Host '  YouTube     : OFF (no cookies.txt found)' -ForegroundColor Yellow
  Write-Host '                Export cookies.txt from youtube.com into Downloads and start again; it is picked up by itself.'
  Write-Host '                How: web\README.md, "YouTube on your phone".'
}
Write-Host "  On this PC  : http://127.0.0.1:$Port"
if (-not $LocalOnly) {
  foreach ($ip in $lan) { Write-Host "  On your phone, same Wi-Fi : http://${ip}:$Port" }
  if ($tailscale) { Write-Host "  Anywhere, with Tailscale  : http://${tailscale}:$Port" }
  if (-not $lan -and -not $tailscale) { Write-Host '  (no network address found, is this PC connected?)' -ForegroundColor Yellow }
  Write-Host '  If Windows asks about the firewall, allow Python on PRIVATE networks.'
}
Write-Host ''
if ($DryRun) { Write-Host '(dry run: nothing was started)'; exit 0 }

if ($Tunnel) {
  if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    Write-Step 'Opening a Cloudflare tunnel in a new window; its https address appears there.'
    Start-Process cloudflared -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port")
  } else {
    Write-Host 'cloudflared is not installed. Install it with:  winget install Cloudflare.cloudflared   then run again with -Tunnel.' -ForegroundColor Yellow
  }
}

Write-Step 'Starting. Close this window or press Ctrl+C to stop.'
& $python[0] @($python[1]) (Join-Path $here 'serve.py')
