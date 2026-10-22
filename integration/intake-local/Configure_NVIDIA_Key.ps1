param([switch]$Replace)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'NVIDIA_Credentials.ps1')
$nvidiaFile = Get-ProjectNvidiaCredentialPath
if ((Test-Path -LiteralPath $nvidiaFile) -and -not $Replace) { throw 'A project key exists. Use -Replace only to replace it intentionally.' }
Write-Host 'Generate a key at build.nvidia.com. Paste only the key into this hidden prompt, using terminal right-click Paste.'
$nvidiaSecret = Read-Host 'NVIDIA API key (hidden; do not paste into chat)' -AsSecureString
try {
    Save-ProjectNvidiaKey -SecureKey $nvidiaSecret -CredentialPath $nvidiaFile -Replace:$Replace
    Write-Host 'Saved with Windows account encryption in Git-ignored project storage. No API request was made.'
} finally { $nvidiaSecret.Dispose() }
