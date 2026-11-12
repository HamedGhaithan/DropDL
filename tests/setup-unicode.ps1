# Run on Windows PowerShell 5.1: powershell -File tests/setup-unicode.ps1 -Python python.exe
param([string]$Python = 'python.exe')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$text = [IO.File]::ReadAllText((Join-Path $Root 'Setup-DropDL.bat'))
$parts = $text -split '(?m)^# DROP_DL_POWERSHELL\r?$', 2
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput($parts[1], [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw "Setup PowerShell syntax errors: $errors" }
# Load functions only. Never execute installs or write app settings in this check.
$functions = $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true)
foreach ($function in $functions) { . ([ScriptBlock]::Create($function.Extent.Text)) }
$Python = (Get-Command $Python -CommandType Application).Source
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('DropDL-Unicode-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$oldEncoding = [Console]::OutputEncoding
try {
    # ASCII-only source runs even when this .ps1 is read as ANSI by PowerShell 5.1.
    $names = @(
        (-join ([char[]]@(0x627,0x628,0x648,0x645,0x62c,0x64a,0x62f)))
        ((-join ([char[]]@(0x639,0x644,0x64a))) + ' user')
        ('Fran' + [char]0xe7 + 'ois')
        (-join ([char[]]@(0x4e2d,0x6587)))
        ('user' + [char]0xd83d + [char]0xde00)
        "O'Connor"
        'user & company'
    )
    $code = 'import json,sys; print(json.dumps({''executable'':sys.argv[1]}, ensure_ascii=True))'
    foreach ($codePage in @(437,850,1252,65001)) {
        [Console]::OutputEncoding = [Text.Encoding]::GetEncoding($codePage)
        foreach ($name in $names) {
            $folder = Join-Path $testRoot $name
            New-Item -ItemType Directory -Path $folder -Force | Out-Null
            $path = Join-Path $folder 'python.exe'
            [IO.File]::WriteAllText($path,'fixture')
            $wire = Probe $Python @('-c',$code,$path)
            $decoded = Read-PythonPath $wire
            if ($decoded -cne $path) { throw "Path round-trip failed for code page $codePage" }
        }
    }
    foreach ($invalid in @('', 'garbled executable path', '{"executable":"relative.exe"}', '{"executable":123}', '{"executable":"C:\\does-not-exist\\python.exe"}')) {
        if ($null -ne (Read-PythonPath $invalid)) { throw 'Invalid path was accepted.' }
    }
    Write-Host 'PASS: setup parser, native JSON transport, Unicode literal paths and rejected invalid paths.'
} finally {
    [Console]::OutputEncoding = $oldEncoding
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
