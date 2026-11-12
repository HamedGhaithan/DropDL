# Use an existing trusted code-signing certificate in your Windows certificate store.
# No self-signed certificate is generated, and Windows trust settings are not changed.
param(
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint,
    [Parameter(Mandatory=$true)][string[]]$Files,
    [string]$SignTool = 'signtool.exe',
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'
$CertificateThumbprint = $CertificateThumbprint.Replace(' ', '')
$cert = Get-Item -LiteralPath "Cert:\CurrentUser\My\$CertificateThumbprint"
if (!$cert.HasPrivateKey) { throw 'The certificate must have an accessible private key.' }
if ($cert.NotAfter -lt (Get-Date)) { throw 'The signing certificate is expired.' }
if (!($cert.EnhancedKeyUsageList | Where-Object {$_.ObjectId -eq '1.3.6.1.5.5.7.3.3'})) { throw 'This certificate is not for code signing.' }
foreach ($file in $Files) {
    $path = (Resolve-Path -LiteralPath $file).Path
    & $SignTool sign /sha1 $CertificateThumbprint /s My /fd SHA256 /tr $TimestampUrl /td SHA256 $path
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $path" }
    & $SignTool verify /pa /v $path
    if ($LASTEXITCODE -ne 0) { throw "Windows signature verification failed: $path" }
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    if ($signature.Status -ne 'Valid') { throw "The signature is not trusted: $($signature.Status)" }
    Write-Host "Signed and verified: $path" -ForegroundColor Green
}
