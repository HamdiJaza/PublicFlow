$ErrorActionPreference = 'Stop'
$ragProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$ragLogRoot = Join-Path $ragProject '.runtime\knowledge-ollama'
$ragEndpoint = 'http://127.0.0.1:11435'
$ragSocket = [Net.Sockets.TcpClient]::new()
try { $ragSocket.Connect('127.0.0.1',11435); $ragListening = $true }
catch { $ragListening = $false }
finally { $ragSocket.Dispose() }
if ($ragListening) {
    $ragOwnerFile = Join-Path $ragLogRoot 'process.json'
    if (-not (Test-Path -LiteralPath $ragOwnerFile)) { throw 'Port 11435 already belongs to an unrecognized service.' }
    $ragOwner = Get-Content -LiteralPath $ragOwnerFile -Raw | ConvertFrom-Json
    $ragProcess = Get-Process -Id $ragOwner.pid -ErrorAction Stop
    if ($ragProcess.ProcessName -ne 'ollama' -or $ragProcess.StartTime.ToUniversalTime().ToString('o') -ne $ragOwner.started_at_utc) {
        throw 'The saved project Ollama process identity no longer matches.'
    }
    Invoke-RestMethod -Uri "$ragEndpoint/api/version" -TimeoutSec 5 | Out-Null
    Write-Host 'Project Ollama is already running on 11435.'
    return
}
[IO.Directory]::CreateDirectory($ragLogRoot) | Out-Null
$ragEnvironment = @{
    OLLAMA_HOST='127.0.0.1:11435'
    OLLAMA_FLASH_ATTENTION='0'
    OLLAMA_NO_CLOUD='1'
    OLLAMA_NOPRUNE='1'
    OLLAMA_MODELS=$(if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { Join-Path $env:USERPROFILE '.ollama\models' })
}
$ragPrevious = @{}
$ragStamp = [guid]::NewGuid().ToString('N')
try {
    foreach ($ragName in $ragEnvironment.Keys) {
        $ragPrevious[$ragName] = [Environment]::GetEnvironmentVariable($ragName,'Process')
        [Environment]::SetEnvironmentVariable($ragName,$ragEnvironment[$ragName],'Process')
    }
    $ragProcess = Start-Process -FilePath (Get-Command ollama -ErrorAction Stop).Source -ArgumentList 'serve' -WindowStyle Hidden -PassThru -WorkingDirectory $ragProject `
        -RedirectStandardOutput (Join-Path $ragLogRoot "$ragStamp.stdout.log") `
        -RedirectStandardError (Join-Path $ragLogRoot "$ragStamp.stderr.log")
    @{pid=$ragProcess.Id;started_at_utc=$ragProcess.StartTime.ToUniversalTime().ToString('o');endpoint=$ragEndpoint;flash_attention=$false;cloud_enabled=$false} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ragLogRoot 'process.json') -Encoding UTF8
} finally {
    foreach ($ragName in $ragPrevious.Keys) { [Environment]::SetEnvironmentVariable($ragName,$ragPrevious[$ragName],'Process') }
}
for ($ragWait=0;$ragWait -lt 60;$ragWait++) {
    if ($ragProcess.HasExited) { throw 'Project Ollama exited; inspect .runtime/knowledge-ollama logs.' }
    try {
        Invoke-RestMethod -Uri "$ragEndpoint/api/version" -TimeoutSec 1 | Out-Null
        Write-Host 'Project Ollama ready on 11435, flash attention disabled; existing shared models reused.'
        return
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'Project Ollama did not become ready; inspect .runtime/knowledge-ollama logs.'
