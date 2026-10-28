param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$portalProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$portalPython = Join-Path $portalProject '.runtime\nvidia-intake-venv\Scripts\python.exe'
$portalLogs = Join-Path $portalProject '.runtime\portal\services'
[IO.Directory]::CreateDirectory($portalLogs) | Out-Null
Set-Location -LiteralPath $portalProject
$portalDbContainer = if ($env:MUNICIPAL_POSTGRES_CONTAINER) { $env:MUNICIPAL_POSTGRES_CONTAINER } else { 'municipal-ticket-postgres-dev' }
$portalN8nContainer = if ($env:MUNICIPAL_N8N_CONTAINER) { $env:MUNICIPAL_N8N_CONTAINER } else { 'municipal-n8n-dev' }

function Test-PortalService {
    param([string]$Url)
    try { $portalResponse = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2; return ($portalResponse.StatusCode -eq 200) }
    catch { return $false }
}
function Start-PortalHelper {
    param([string]$Name, [string]$Script, [string[]]$ExtraArgs = @())
    $portalStamp = [guid]::NewGuid().ToString('N')
    $portalArguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $portalProject $Script) + '"')) + $ExtraArgs
    Start-Process powershell.exe -ArgumentList $portalArguments -WindowStyle Hidden -WorkingDirectory $portalProject `
        -RedirectStandardOutput (Join-Path $portalLogs "$Name-$portalStamp.stdout.log") `
        -RedirectStandardError (Join-Path $portalLogs "$Name-$portalStamp.stderr.log") | Out-Null
}
if (-not (Test-Path -LiteralPath $portalPython)) { throw 'The recovered project Python environment is missing.' }
# Start only the installed ticket database; never create or download infrastructure here.
$portalDatabase = docker inspect $portalDbContainer --format '{{.State.Running}}' 2>$null
if ($LASTEXITCODE -eq 0 -and $portalDatabase -eq 'false') {
    docker start $portalDbContainer
    if ($LASTEXITCODE -ne 0) { Write-Warning 'The installed ticket database could not start.' }
}
if (-not (Test-PortalService 'http://127.0.0.1:5679/healthz')) {
    # Only start the already installed development container: no pull/import/production change.
    docker start $portalN8nContainer
    if ($LASTEXITCODE -ne 0) { Write-Warning 'The existing n8n development container could not start. Check Docker Desktop.' }
}
if (-not (Test-PortalService 'http://127.0.0.1:11435/api/version')) {
    & (Join-Path $portalProject 'integration\knowledge\Start_Knowledge_Ollama.ps1')
}
if (-not (Test-PortalService 'http://127.0.0.1:8013/healthz')) {
    Start-PortalHelper -Name media -Script 'integration\vision\Start_Media_Bridge.ps1'
}
if (-not (Test-PortalService 'http://127.0.0.1:8010/openapi.json')) {
    # Keep Vision on its original Ollama endpoint. The RAG server disables flash
    # attention specifically for BGE-M3; applying that setting to Vision creates
    # a large CPU image-encoder buffer on this workstation.
    Start-PortalHelper -Name vision -Script 'integration\vision\Start_Vision_Dev.ps1'
}
if (-not (Test-PortalService 'http://127.0.0.1:8020/health')) {
    Start-PortalHelper -Name knowledge -Script 'integration\knowledge\Start_Knowledge_Dev.ps1'
}
if (-not (Test-PortalService 'http://127.0.0.1:8021/healthz')) {
    Start-PortalHelper -Name evidence -Script 'integration\knowledge\Start_Evidence_Bridge.ps1'
}
if (-not (Test-PortalService 'http://127.0.0.1:8012/')) {
    . (Join-Path $portalProject 'integration\intake-local\NVIDIA_Credentials.ps1')
    $portalKeyReadable = $false
    try { Invoke-WithProjectNvidiaKey -Action { }; $portalKeyReadable = $true } catch { }
    if ($portalKeyReadable) {
        Start-PortalHelper -Name intake -Script 'intake-agent\Start_NVIDIA_Intake.ps1' -ExtraArgs @('-DockerAccess','-EnableNvidiaApi')
    } else { Write-Host 'Configure the NVIDIA key once in the admin console: http://127.0.0.1:8091/admin. No key is printed.' }
}
# Display-only Vision translation; optional, it needs the same NVIDIA key as Intake.
if (-not (Test-PortalService 'http://127.0.0.1:8014/healthz')) {
    . (Join-Path $portalProject 'integration\intake-local\NVIDIA_Credentials.ps1')
    $portalKeyReadable = $false
    try { Invoke-WithProjectNvidiaKey -Action { }; $portalKeyReadable = $true } catch { }
    if ($portalKeyReadable) { Start-PortalHelper -Name translation -Script 'integration\translation\Start_Translation_Bridge.ps1' }
}
if (-not (Test-PortalService 'http://127.0.0.1:8090/api/session')) {
    $portalStamp = [guid]::NewGuid().ToString('N')
    $portalArguments = @('-B','-m','uvicorn','app:app','--app-dir',('"' + $PSScriptRoot + '"'),
        '--host','127.0.0.1','--port','8090','--workers','1','--no-access-log')
    Start-Process -FilePath $portalPython -ArgumentList $portalArguments -WindowStyle Hidden -WorkingDirectory $portalProject `
        -RedirectStandardOutput (Join-Path $portalLogs "portal-$portalStamp.stdout.log") `
        -RedirectStandardError (Join-Path $portalLogs "portal-$portalStamp.stderr.log") | Out-Null
}
# Staff console (municipalities, STEG, SONEDE and the maintenance admin).
if (-not (Test-PortalService 'http://127.0.0.1:8091/connexion')) {
    $portalStamp = [guid]::NewGuid().ToString('N')
    $staffArguments = @('-B','-m','uvicorn','app:app','--app-dir',('"' + (Join-Path $portalProject 'integration\staff') + '"'),
        '--host','127.0.0.1','--port','8091','--workers','1','--no-access-log')
    Start-Process -FilePath $portalPython -ArgumentList $staffArguments -WindowStyle Hidden -WorkingDirectory $portalProject `
        -RedirectStandardOutput (Join-Path $portalLogs "staff-$portalStamp.stdout.log") `
        -RedirectStandardError (Join-Path $portalLogs "staff-$portalStamp.stderr.log") | Out-Null
}
for ($portalWait=0; $portalWait -lt 30; $portalWait++) {
    if (Test-PortalService 'http://127.0.0.1:8090/api/session') {
        Write-Host 'Upload page: http://127.0.0.1:8090/'
        Write-Host 'Staff console (municipality, STEG, SONEDE, admin): http://127.0.0.1:8091/'
        Write-Host 'One media submission starts n8n automatically. A tracking ID confirms database persistence.'
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8090/' -WindowStyle Hidden }
        return
    }
    Start-Sleep -Milliseconds 500
}
throw 'Portal did not become ready. Inspect .runtime/portal/services.'
