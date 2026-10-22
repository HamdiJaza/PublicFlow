# Called by the loopback setup page. Never put the key on a command line.
$ErrorActionPreference = 'Stop'
$portalProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$portalSecure = $null
try {
    . (Join-Path $portalProject 'integration\intake-local\NVIDIA_Credentials.ps1')
    $portalKey = [Console]::In.ReadToEnd()
    $portalSecure = ConvertTo-SecureString -String $portalKey -AsPlainText -Force
    $portalKey = $null
    # A live Intake process cannot safely adopt a different key without restart.
    try { $portalRunning = Invoke-RestMethod 'http://127.0.0.1:8012/' -TimeoutSec 2 } catch { $portalRunning = $null }
    if ($null -ne $portalRunning) { throw 'Intake already running; nothing replaced.' }
    $portalCredential = Get-ProjectNvidiaCredentialPath
    if (Test-Path -LiteralPath $portalCredential) {
        Copy-Item -LiteralPath $portalCredential -Destination ($portalCredential + '.backup-' + [guid]::NewGuid().ToString('N'))
    }
    Save-ProjectNvidiaKey -SecureKey $portalSecure -Replace
    $portalLog = Join-Path $portalProject '.runtime\portal\services'
    [IO.Directory]::CreateDirectory($portalLog) | Out-Null
    $portalStamp = [guid]::NewGuid().ToString('N')
    $portalArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',
        ('"' + (Join-Path $portalProject 'intake-agent\Start_NVIDIA_Intake.ps1') + '"'), '-DockerAccess','-EnableNvidiaApi')
    $portalProcess = Start-Process powershell.exe -ArgumentList $portalArgs -WindowStyle Hidden -PassThru `
        -WorkingDirectory $portalProject -RedirectStandardOutput (Join-Path $portalLog "intake-$portalStamp.stdout.log") `
        -RedirectStandardError (Join-Path $portalLog "intake-$portalStamp.stderr.log")
    for ($portalWait=0; $portalWait -lt 60; $portalWait++) {
        if ($portalProcess.HasExited) { throw 'Intake failed to start.' }
        try {
            $portalHealth = Invoke-RestMethod 'http://127.0.0.1:8012/' -TimeoutSec 1
            if ($portalHealth.version -eq '5.0.0') { Write-Output 'Intake ready.'; exit 0 }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw 'Intake readiness timeout.'
} catch {
    # No exception/provider text, argument values, or credential bytes in output.
    Write-Output 'Local Intake configuration failed.'
    exit 1
} finally {
    $portalKey = $null
    if ($null -ne $portalSecure) { $portalSecure.Dispose() }
}
