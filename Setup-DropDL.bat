@echo off
setlocal
set "DROP_DL_SETUP_FILE=%~f0"
set "DROP_DL_SETUP_ROOT=%~dp0"
echo.
echo DropDL Studio - Automatic Windows Setup
echo Internet access is required. Installer agreements are accepted automatically.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$text = [IO.File]::ReadAllText($env:DROP_DL_SETUP_FILE); $parts = $text -split '(?m)^# DROP_DL_POWERSHELL\r?$', 2; if ($parts.Count -ne 2) { Write-Error 'Setup file is incomplete'; exit 1 }; & ([ScriptBlock]::Create($parts[1]))"
set "DROP_DL_EXIT=%ERRORLEVEL%"
echo.
if not "%DROP_DL_EXIT%"=="0" echo Setup did not finish. Read Setup-Log.txt for details.
if not defined DROPDL_INSTALLER pause
exit /b %DROP_DL_EXIT%
# DROP_DL_POWERSHELL
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = $env:DROP_DL_SETUP_ROOT
$Log = Join-Path $Root 'Setup-Log.txt'
$Logging = $false

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user;$env:Path;$env:LOCALAPPDATA\Microsoft\WindowsApps"
}
function Executable([string]$Name) {
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return $null
}
function Probe([string]$File, [string[]]$Arguments) {
    if (!$File -or !(Test-Path -LiteralPath $File -PathType Leaf)) { return $null }
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $output = @(& $File @Arguments 2>$null)
        if ($LASTEXITCODE -eq 0 -and $output.Count -gt 0) { return [string]$output[-1] }
    } catch { }
    return $null
}
function Read-PythonPath([string]$Output) {
    # Native stdout decoding differs between Python and Windows PowerShell 5.1.
    # Python sends ASCII JSON; decode Unicode only after it reaches PowerShell.
    if (!$Output) { return $null }
    try {
        $record = ConvertFrom-Json -InputObject $Output -ErrorAction Stop
        $path = $record.executable
        if ($path -isnot [string] -or ![IO.Path]::IsPathRooted($path)) { return $null }
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    } catch { }
    return $null
}
function Find-Python {
    $code = 'import sys, struct, json; sys.exit(3) if not ((3,11) <= sys.version_info[:2] < (3,14) and struct.calcsize(''P'') == 8) else None; print(json.dumps({''executable'': sys.executable}, ensure_ascii=True))'
    $launcher = Executable 'py.exe'
    if ($launcher) {
        foreach ($version in @('-3.12','-3.13','-3.11')) {
            $found = Read-PythonPath (Probe $launcher @($version,'-c',$code))
            if ($found) { return $found }
        }
    }
    $candidates = @()
    $command = Executable 'python.exe'
    if ($command -and $command -notlike '*\WindowsApps\*') { $candidates += $command }
    foreach ($version in @('312','313','311')) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"
        $candidates += Join-Path $env:ProgramFiles "Python$version\python.exe"
    }
    foreach ($candidate in $candidates) {
        $found = Read-PythonPath (Probe $candidate @('-c',$code))
        if ($found) { return $found }
    }
    return $null
}
function Find-Node {
    $candidates = @(Executable 'node.exe')
    $candidates += Join-Path $env:ProgramFiles 'nodejs\node.exe'
    foreach ($packageRoot in @("$env:LOCALAPPDATA\Microsoft\WinGet\Packages","$env:ProgramFiles\WinGet\Packages")) {
        if (Test-Path -LiteralPath $packageRoot) {
            foreach ($package in @(Get-ChildItem -LiteralPath $packageRoot -Directory -Filter 'OpenJS.NodeJS.LTS*')) {
                $candidates += @(Get-ChildItem -LiteralPath $package.FullName -Filter node.exe -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
            }
        }
    }
    foreach ($candidate in $candidates) {
        $version = Probe $candidate @('--version')
        if ($version -match '^v(\d+)\.' -and [int]$Matches[1] -ge 22) { return $candidate }
    }
    return $null
}
function Find-MediaTool([string]$Name) {
    $candidates = @(Executable "$Name.exe")
    if ($env:FFMPEG_LOCATION) {
        $base = $env:FFMPEG_LOCATION
        if (Test-Path -LiteralPath $base -PathType Leaf) { $base = Split-Path -Parent $base }
        $candidates += Join-Path $base "$Name.exe"
    }
    $candidates += Join-Path $Root "bin\$Name.exe"
    foreach ($packageRoot in @("$env:LOCALAPPDATA\Microsoft\WinGet\Packages","$env:ProgramFiles\WinGet\Packages")) {
        if (Test-Path -LiteralPath $packageRoot) {
            foreach ($package in @(Get-ChildItem -LiteralPath $packageRoot -Directory -Filter 'Gyan.FFmpeg*')) {
                $candidates += @(Get-ChildItem -LiteralPath $package.FullName -Filter "$Name.exe" -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
            }
        }
    }
    foreach ($candidate in $candidates) {
        if (Probe $candidate @('-version')) { return $candidate }
    }
    return $null
}
function Has-WebView2 {
    foreach ($key in @('HKCU:\Software\Microsoft\EdgeUpdate\Clients','HKLM:\Software\Microsoft\EdgeUpdate\Clients','HKLM:\Software\WOW6432Node\Microsoft\EdgeUpdate\Clients')) {
        foreach ($client in @(Get-ChildItem -LiteralPath $key -ErrorAction SilentlyContinue)) {
            $properties = Get-ItemProperty -LiteralPath $client.PSPath -ErrorAction SilentlyContinue
            if ($properties.name -like '*WebView2*' -and $properties.pv -and $properties.pv -ne '0.0.0.0') { return $true }
        }
    }
    foreach ($base in @("${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application","$env:ProgramFiles\Microsoft\EdgeWebView\Application","$env:LOCALAPPDATA\Microsoft\EdgeWebView\Application")) {
        if (Test-Path -LiteralPath $base) {
            if (Get-ChildItem -LiteralPath $base -Filter msedgewebview2.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1) { return $true }
        }
    }
    return $false
}
function Install-DropDLPkg([string]$Id) {
    Write-Host "Downloading/installing $Id ..." -ForegroundColor Cyan
    & $script:Winget install --id $Id --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    $code = $LASTEXITCODE
    Refresh-Path
    if ($code -ne 0) { Write-Warning "$Id returned code $code. Checking whether installation completed or a restart is needed." }
}
function Check-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE). See the log and rerun setup after correcting the error." }
}

try {
    if (![Environment]::Is64BitOperatingSystem) { throw 'DropDL setup requires 64-bit Windows 10 or 11.' }
    if ([Environment]::OSVersion.Version.Build -lt 17763) { throw 'Windows 10 version 1809 or newer is required. Update Windows first.' }
    if (!(Test-Path -LiteralPath (Join-Path $Root 'backend\requirements.txt'))) {
        throw 'Place Setup-DropDL.bat inside the extracted DropDL folder, beside Start-Desktop.bat, and run it again.'
    }
    Start-Transcript -Path $Log -Force | Out-Null
    $Logging = $true
    Set-Location -LiteralPath $Root
    Refresh-Path
    Write-Host 'Checking Windows Package Manager...' -ForegroundColor Cyan
    $script:Winget = Executable 'winget.exe'
    if (!$script:Winget -or !(Probe $script:Winget @('--version'))) {
        Write-Host 'Installing/repairing WinGet using the Microsoft WinGet module...'
        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
        Install-Module -Name Microsoft.WinGet.Client -Repository PSGallery -Scope CurrentUser -Force -AllowClobber
        Import-Module Microsoft.WinGet.Client -Force
        Repair-WinGetPackageManager -Force -Latest | Out-Host
        Refresh-Path
        $script:Winget = Executable 'winget.exe'
        if (!$script:Winget -or !(Probe $script:Winget @('--version'))) {
            throw 'WinGet could not be installed. Install/update App Installer from Microsoft Store, then rerun this file.'
        }
    }

    Write-Host '[1/6] Python' -ForegroundColor Cyan
    $Python = Find-Python
    if (!$Python) { Install-DropDLPkg 'Python.Python.3.12'; $Python = Find-Python }
    if (!$Python) { throw 'Compatible 64-bit Python was not found. Restart Windows if requested, then rerun setup.' }

    Write-Host '[2/6] Node.js' -ForegroundColor Cyan
    $Node = Find-Node
    if (!$Node) { Install-DropDLPkg 'OpenJS.NodeJS.LTS'; $Node = Find-Node }
    if (!$Node) { throw 'Node.js 22+ was not found after installation. Check the installer log or restart, then rerun.' }

    Write-Host '[3/6] FFmpeg and ffprobe' -ForegroundColor Cyan
    $FFmpeg = Find-MediaTool 'ffmpeg'; $FFprobe = Find-MediaTool 'ffprobe'
    if (!$FFmpeg -or !$FFprobe) { Install-DropDLPkg 'Gyan.FFmpeg'; $FFmpeg = Find-MediaTool 'ffmpeg'; $FFprobe = Find-MediaTool 'ffprobe' }
    if (!$FFmpeg -or !$FFprobe) { throw 'FFmpeg/ffprobe could not be found after installation.' }

    Write-Host '[4/6] Microsoft WebView2 Runtime' -ForegroundColor Cyan
    if (!(Has-WebView2)) { Install-DropDLPkg 'Microsoft.EdgeWebView2Runtime' }
    if (!(Has-WebView2)) { throw 'WebView2 Runtime was not detected. Restart if requested, then rerun setup.' }

    # Record tool locations for this app, without changing global user settings.
    $toolDirectories = @((Split-Path -Parent $Python),(Split-Path -Parent $Node),(Split-Path -Parent $FFmpeg),(Split-Path -Parent $FFprobe)) | Select-Object -Unique
    $env:Path = ($toolDirectories -join ';') + ';' + $env:Path
    $env:FFMPEG_LOCATION = Split-Path -Parent $FFmpeg
    $quotedPaths = ($toolDirectories -join ';').Replace("'", "''")
    $quotedFFmpeg = $env:FFMPEG_LOCATION.Replace("'", "''")
    $environmentLines = @(
        '# Generated by Setup-DropDL.bat for this computer.',
        ('$env:Path = ''' + $quotedPaths + ';'' + $env:Path'),
        ('$env:FFMPEG_LOCATION = ''' + $quotedFFmpeg + '''')
    )
    Set-Content -LiteralPath (Join-Path $Root 'setup-env.ps1') -Value $environmentLines -Encoding UTF8

    Write-Host '[5/6] App environment and Python libraries' -ForegroundColor Cyan
    $Venv = Join-Path $Root '.venv'
    $VenvPython = Join-Path $Venv 'Scripts\python.exe'
    if (Test-Path -LiteralPath $Venv) {
        $valid = Probe $VenvPython @('-c','import sys; sys.exit(1) if not ((3,11) <= sys.version_info[:2] < (3,14)) else None; print(''ok'')')
        if (!$valid) {
            $backup = '.venv-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
            Rename-Item -LiteralPath $Venv -NewName $backup
            Write-Host "Preserved the incompatible environment as $backup"
        }
    }
    if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'The selected Python executable is unavailable. Rerun setup to rediscover Python.' }
    if (!(Test-Path -LiteralPath $VenvPython)) { & $Python -m venv $Venv; Check-Exit 'Creating the app environment' }
    & $VenvPython -m pip install --upgrade pip
    Check-Exit 'Updating pip'
    $InstallArguments = @('-m','pip','install','--upgrade')
    if ($env:DROPDL_SETUP_MODE -eq 'repair') { $InstallArguments += '--force-reinstall' }
    $InstallArguments += @('-r',(Join-Path $Root 'backend\requirements.txt'))
    & $VenvPython @InstallArguments
    Check-Exit 'Installing app libraries'

    Write-Host '[6/6] Built interface and final checks' -ForegroundColor Cyan
    if (!(Test-Path -LiteralPath (Join-Path $Root 'frontend\dist\index.html'))) {
        $Npm = Join-Path (Split-Path -Parent $Node) 'npm.cmd'
        if (!(Test-Path -LiteralPath $Npm)) { $Npm = Executable 'npm.cmd' }
        if (!$Npm) { throw 'npm was not found. Repair the Node.js installation and rerun setup.' }
        Push-Location -LiteralPath (Join-Path $Root 'frontend')
        try { & $Npm ci; Check-Exit 'Installing interface dependencies'; & $Npm run build; Check-Exit 'Building the interface' }
        finally { Pop-Location }
    }
    & $VenvPython -c 'import yt_dlp, yt_dlp_ejs, fastapi, uvicorn, webview, curl_cffi; print(''App imports OK'')'
    Check-Exit 'Checking app libraries'
    & $Node --version
    Check-Exit 'Checking Node.js'
    if (!(Probe $FFmpeg @('-version')) -or !(Probe $FFprobe @('-version'))) { throw 'FFmpeg verification failed.' }
    Write-Host ''
    Write-Host 'SETUP COMPLETE. Double-click Start-Desktop.bat to launch DropDL Studio.' -ForegroundColor Green
    Write-Host "Setup log: $Log"
    if ($Logging) { Stop-Transcript | Out-Null; $Logging = $false }
    exit 0
} catch {
    Write-Host ''
    Write-Host ('SETUP FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    if ($Logging) { Stop-Transcript | Out-Null }
    exit 1
}
