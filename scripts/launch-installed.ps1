$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root
if (Test-Path -LiteralPath "$Root\setup-env.ps1") { . "$Root\setup-env.ps1" }
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $Python)) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show('Setup is incomplete. Run Setup-DropDL.bat or rerun the installer.', 'DropDL Studio') | Out-Null
    exit 1
}
$env:HOST = '127.0.0.1'
$env:PORT = '17321'
$Data = Join-Path $env:LOCALAPPDATA 'DropDL'
New-Item -ItemType Directory -Force -Path $Data | Out-Null
$env:PYTHONUNBUFFERED = '1'
# Create Python without allocating a console. Drain both pipes concurrently so
# long sessions cannot fill a pipe or accumulate console output in memory.
$Info = New-Object System.Diagnostics.ProcessStartInfo
$Info.FileName = $Python
$Info.Arguments = '-u -X faulthandler "' + (Join-Path $Root 'backend\desktop.py') + '"'
$Info.WorkingDirectory = $Root
$Info.UseShellExecute = $false
$Info.CreateNoWindow = $true
$Info.RedirectStandardOutput = $true
$Info.RedirectStandardError = $true
$OutLog = [IO.File]::Open((Join-Path $Data 'desktop.log'), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
$ErrLog = [IO.File]::Open((Join-Path $Data 'desktop-error.log'), [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
$Process = New-Object System.Diagnostics.Process
$Process.StartInfo = $Info
$ExitCode = 1
try {
    [void]$Process.Start()
    $OutputCopy = $Process.StandardOutput.BaseStream.CopyToAsync($OutLog)
    $ErrorCopy = $Process.StandardError.BaseStream.CopyToAsync($ErrLog)
    $Process.WaitForExit()
    $OutputCopy.GetAwaiter().GetResult()
    $ErrorCopy.GetAwaiter().GetResult()
    $ExitCode = $Process.ExitCode
} finally {
    $OutLog.Dispose()
    $ErrLog.Dispose()
    $Process.Dispose()
}
if ($ExitCode -ne 0) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("DropDL could not start. Close any other DropDL instance, or run Setup-DropDL.bat to repair dependencies. Logs: $Data\diagnostics.log and $Data\backend-console.log", 'DropDL Studio') | Out-Null
}
