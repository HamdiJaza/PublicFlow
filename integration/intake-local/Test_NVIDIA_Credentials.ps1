# Fixture-only DPAPI tests; no real credential content read or API calls.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'NVIDIA_Credentials.ps1')
$nvidiaFixtureDir = Join-Path (Split-Path -Parent (Get-ProjectNvidiaCredentialPath)) 'tests'
[IO.Directory]::CreateDirectory($nvidiaFixtureDir) | Out-Null
$nvidiaFixture = Join-Path $nvidiaFixtureDir (([Guid]::NewGuid().ToString('N'))+'.dpapi')
$nvidiaSecureFixture = ConvertTo-SecureString 'OFFLINE-NVIDIA-TEST-ONLY' -AsPlainText -Force
$nvidiaPrior = @{}
foreach ($nvidiaName in @('NVIDIA_API_KEY','INTAKE_NVIDIA_KEY_SOURCE')) {
    $nvidiaPrior[$nvidiaName] = [Environment]::GetEnvironmentVariable($nvidiaName,'Process')
}
try {
    $nvidiaMalformedFixtures = @(
        @{Kind='empty';Value=''}, @{Kind='control';Value=([string][char]22)+'BAD'},
        @{Kind='spaces';Value='KEY WITH SPACES'}, @{Kind='assignment';Value='NVIDIA_API_KEY=TOKEN'},
        @{Kind='URL';Value='https://example.invalid/key'}, @{Kind='quotes';Value='"TOKEN"'}
    )
    foreach ($nvidiaBad in $nvidiaMalformedFixtures) {
        $nvidiaRejected = $false
        try { Assert-ProjectNvidiaKey -Key $nvidiaBad.Value } catch { $nvidiaRejected = $true }
        if (-not $nvidiaRejected) { throw 'Malformed key accepted.' }
    }
    Save-ProjectNvidiaKey -SecureKey $nvidiaSecureFixture -CredentialPath $nvidiaFixture
    if ((Get-Content -LiteralPath $nvidiaFixture -Raw).Contains('OFFLINE-NVIDIA-TEST-ONLY')) { throw 'Fixture stored in plaintext.' }
    $nvidiaOverwriteBlocked = $false
    try { Save-ProjectNvidiaKey -SecureKey $nvidiaSecureFixture -CredentialPath $nvidiaFixture } catch { $nvidiaOverwriteBlocked = $true }
    if (-not $nvidiaOverwriteBlocked) { throw 'Overwrite protection failed.' }
    Invoke-WithProjectNvidiaKey -CredentialPath $nvidiaFixture -Action {
        if ($env:NVIDIA_API_KEY -cne 'OFFLINE-NVIDIA-TEST-ONLY' -or $env:INTAKE_NVIDIA_KEY_SOURCE -cne 'project-dpapi') { throw 'Fixture environment incorrect.' }
    }
    try { Invoke-WithProjectNvidiaKey -CredentialPath $nvidiaFixture -Action { throw 'EXPECTED_NVIDIA_OFFLINE_FAILURE' } }
    catch { if ($_.Exception.Message -ne 'EXPECTED_NVIDIA_OFFLINE_FAILURE') { throw } }
    foreach ($nvidiaName in $nvidiaPrior.Keys) {
        if ([Environment]::GetEnvironmentVariable($nvidiaName,'Process') -cne $nvidiaPrior[$nvidiaName]) { throw 'Process environment not restored.' }
    }
    Write-Host 'PASS fixture encryption, overwrite protection, validation and environment restoration; zero API calls.'
} finally {
    $nvidiaSecureFixture.Dispose()
    Remove-Item -LiteralPath $nvidiaFixture -ErrorAction SilentlyContinue
}
