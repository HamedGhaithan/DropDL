param(
    [Parameter(Mandatory=$true)][string]$Root,
    [ValidateSet('install','upgrade','repair','uninstall')][string]$Mode = 'install',
    [Parameter(Mandatory=$true)][string]$Release
)
$ErrorActionPreference = 'Stop'
try {
    $Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $state = Join-Path $env:LOCALAPPDATA 'DropDL'
    $versionVerified = $false
    $registration = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DropDLStudio' -ErrorAction SilentlyContinue
    if ($registration -and $registration.InstallLocation) {
        $registeredRoot = [IO.Path]::GetFullPath($registration.InstallLocation).TrimEnd('\')
        if ($registeredRoot -ne $Root) { throw 'The selected directory differs from the registered installation.' }
        if ($Mode -ne 'uninstall' -and $registration.DisplayVersion) {
            $installed = [Version]$registration.DisplayVersion
            $versionVerified = $true
            $target = [Version]$Release
            if ($installed -gt $target) { throw 'An older installer cannot overwrite a newer installation.' }
            if ($installed -lt [Version]'0.5.0') { throw 'This release supports in-place upgrades from desktop 0.5.0 or later. Keep the old installation and export your queue before migrating.' }
            if ($Mode -eq 'repair' -and $installed -ne $target) { throw 'Use the same release to repair, or choose Upgrade.' }
        }
    }
    $versionFile = Join-Path $Root 'backend\app\version.py'
    if ($Mode -ne 'uninstall' -and (Test-Path -LiteralPath $versionFile)) {
        $versionText = Get-Content -LiteralPath $versionFile -Raw
        if ($versionText -match 'VERSION\s*=\s*["'']([0-9]+\.[0-9]+\.[0-9]+)["'']') {
            $actualVersion = [Version]$Matches[1]
            $versionVerified = $true
            if ($actualVersion -gt [Version]$Release) { throw 'App files belong to a newer version. Downgrading is blocked.' }
            if ($actualVersion -lt [Version]'0.5.0') { throw 'In-place upgrades require desktop 0.5.0 or later.' }
        } else { throw 'The installed version could not be verified. Keep the existing installation and use a matching installer.' }
    }
    if ($Mode -in @('upgrade','repair') -and !$versionVerified) {
        throw 'The installed version could not be verified. No files were replaced.'
    }
    # Match exact script paths, never every Python process or a process merely using our port.
    $scripts = @('backend\desktop.py','scripts\launch-installed.ps1','Launch-DropDL.vbs') | ForEach-Object { Join-Path $Root $_ }
    $patterns = $scripts | ForEach-Object { '(?i)(?:"' + [Regex]::Escape($_) + '"|(?<!\S)' + [Regex]::Escape($_) + '(?=\s|$))' }
    $launcher = Join-Path $Root 'DropDL.exe'
    $owned = @(Get-CimInstance Win32_Process | Where-Object {
        $process = $_
        $matched = ($process.ExecutablePath -eq $launcher)
        foreach ($pattern in $patterns) {
            if ($process.CommandLine -match $pattern) { $matched = $true; break }
        }
        $matched -and $process.ProcessId -ne $PID
    })
    foreach ($process in $owned) {
        # Force-stop only an identified DropDL tree; no unrelated applications are stopped.
        Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" -ArgumentList @("/PID",$process.ProcessId,"/T","/F") -Wait -NoNewWindow | Out-Null
    }
    $remaining = @(Get-CimInstance Win32_Process | Where-Object {
        $command = $_.CommandLine
        $matched = ($_.ExecutablePath -eq $launcher)
        foreach ($pattern in $patterns) { if ($command -match $pattern) { $matched = $true; break } }
        $matched -and $_.ProcessId -ne $PID
    })
    if ($remaining.Count) { throw 'DropDL is still running. Close its window and retry setup.' }
    if ($Mode -ne 'uninstall' -and (Test-Path -LiteralPath $Root)) {
        $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
        $backup = Join-Path $state "backups\$stamp"
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        foreach ($name in @('backend','frontend\dist','scripts','installer','DropDL.exe','Uninstall.exe','Setup-DropDL.bat','setup-env.ps1')) {
            $source = Join-Path $Root $name
            if (Test-Path -LiteralPath $source) {
                $destination = Join-Path $backup $name
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
                Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
            }
        }
        foreach ($name in @('settings.json','queue.json','subscriptions.json','presets.json','browser.json','library.sqlite3','library.sqlite3-wal','library.sqlite3-shm')) {
            $source = Join-Path $state $name
            if (Test-Path -LiteralPath $source) {
                $profile = Join-Path $backup 'profile'
                New-Item -ItemType Directory -Force -Path $profile | Out-Null
                Copy-Item -LiteralPath $source -Destination $profile -Force
            }
        }
        Write-Host "App and profile backup: $backup"
        Write-Host 'Python environment and downloaded media are retained in place.'
    }
    Write-Host "Ready for $Mode to $Release"
    exit 0
} catch {
    Write-Host $_.Exception.Message
    exit 1
}
