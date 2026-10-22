param([switch]$DownloadModels, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$ragProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$ragPython = Join-Path $ragProject '.runtime\knowledge-venv\Scripts\python.exe'
$ragAppDirectory = Join-Path $ragProject 'integration\knowledge'
Set-Location -LiteralPath $ragProject
if (-not (Test-Path -LiteralPath $ragPython)) { throw 'The recovered project Knowledge environment is missing.' }

function Test-RagPort {
    param([int]$Port)
    $ragSocket = [Net.Sockets.TcpClient]::new()
    try { $ragSocket.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $ragSocket.Dispose() }
}

function Stop-OwnedRagService {
    param([int]$Port, [string]$Module)
    if (-not (Test-RagPort -Port $Port)) { return }
    # Never trust a recycled PID or stop a service belonging to another checkout.
    $ragOwners = @(Get-NetTCPConnection -State Listen -LocalPort $Port |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($ragOwners.Count -ne 1) { throw "Cannot identify one development service on port $Port. Stop it in its own terminal first." }
    $ragProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($ragOwners[0])"
    $ragCommand = [string]$ragProcess.CommandLine
    if ($ragProcess.Name -notmatch '^python(w)?\.exe$' -or
        $ragCommand.IndexOf($ragAppDirectory, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
        $ragCommand -notmatch ([regex]::Escape($Module) + '(\s|$)') -or
        $ragCommand -notmatch ('--port\s+' + $Port + '(\s|$)')) {
        throw "Port $Port is occupied by a service that cannot be identified as this checkout's RAG service. Nothing was stopped."
    }
    Stop-Process -Id $ragOwners[0] -ErrorAction Stop
    for ($ragWait = 0; $ragWait -lt 20; $ragWait++) {
        if (-not (Test-RagPort -Port $Port)) { return }
        Start-Sleep -Milliseconds 250
    }
    throw "Development service on port $Port did not stop."
}

function Start-RagService {
    param([string]$Module, [int]$Port, [string]$HealthPath)
    $ragLogRoot = Join-Path $ragProject '.runtime\rag-resume'
    [IO.Directory]::CreateDirectory($ragLogRoot) | Out-Null
    $ragStamp = [guid]::NewGuid().ToString('N')
    $ragArgs = @('-B', '-m', 'uvicorn', $Module, '--app-dir', ('"' + $ragAppDirectory + '"'),
        '--host', '0.0.0.0', '--port', [string]$Port, '--workers', '1', '--no-access-log')
    $ragStarted = Start-Process -FilePath $ragPython -ArgumentList $ragArgs -WorkingDirectory $ragProject -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $ragLogRoot "$Port-$ragStamp.stdout.log") `
        -RedirectStandardError (Join-Path $ragLogRoot "$Port-$ragStamp.stderr.log")
    for ($ragWait = 0; $ragWait -lt 45; $ragWait++) {
        if ($ragStarted.HasExited) { throw "RAG service on $Port exited; inspect .runtime/rag-resume logs." }
        try {
            $ragHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port$HealthPath" -TimeoutSec 1
            if ($Port -eq 8020 -and $ragHealth.index_manifest_present -and $ragHealth.generation_model -eq 'qwen2.5:3b') { return }
            if ($Port -eq 8021 -and $ragHealth.status -eq 'ready' -and $ragHealth.index_present) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "RAG service on $Port did not become configured; inspect .runtime/rag-resume logs."
}

# Read-only prerequisite check; health/configuration is never inference evidence.
$ragProblems = [Collections.Generic.List[string]]::new()
try {
    $ragModels = @((Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5).models.name)
    if ('qwen2.5:3b' -notin $ragModels) { $ragProblems.Add('The selected qwen2.5:3b generation model is missing; no substitute will be downloaded.') }
    if ('bge-m3' -notin $ragModels -and 'bge-m3:latest' -notin $ragModels) {
        Write-Host 'BGE-M3 is missing from Ollama.'
        if (-not $DownloadModels -or $CheckOnly) { $ragProblems.Add('Use -DownloadModels to download the already-approved original BGE-M3 through the native Ollama adapter.') }
    }
} catch { $ragProblems.Add('Ollama is not reachable at 127.0.0.1:11434.') }
try {
    $ragDocker = & docker info --format '{{.ServerVersion}}' 2>&1
    if ($LASTEXITCODE -ne 0) { $ragProblems.Add('Docker API is inaccessible. Run this command in a normal PowerShell terminal with Docker Desktop running.') }
} catch { $ragProblems.Add('Docker API is inaccessible. Run this command in a normal PowerShell terminal with Docker Desktop running.') }
if ($CheckOnly) {
    if ($ragProblems.Count) { throw ($ragProblems -join "`n") }
    Write-Host 'Prerequisites accessible. CheckOnly made no downloads, inference calls or deployment changes.'
    return
}
# Download independently of Docker readiness; do not block model installation on n8n.
if ($DownloadModels -and 'qwen2.5:3b' -in $ragModels) {
    & $ragPython -B integration/knowledge/download_models.py --download
    if ($LASTEXITCODE -ne 0) { throw 'BGE-M3 download failed. No indexes or workflow execution are claimed. No proxy settings were changed.' }
}
if ($ragProblems.Count) { throw ($ragProblems -join "`n") }

# Reuse the exact verified image offline; pull only when it is absent locally.
$ragImageLines = @(Select-String -Path 'n8n/intake-integration/compose.dev.yaml' -Pattern '^\s+image:\s+(.+)$')
if ($ragImageLines.Count -ne 1) { throw 'Cannot identify one pinned development n8n image.' }
$ragImage = $ragImageLines[0].Matches[0].Groups[1].Value.Trim()
$ragImagePresent = & docker image inspect $ragImage --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    docker compose -f n8n/intake-integration/compose.dev.yaml pull n8n
    if ($LASTEXITCODE -ne 0) { throw 'The pinned development n8n image could not be pulled. No development services were stopped.' }
} else { Write-Host 'Reusing the verified pinned n8n image; no registry request needed.' }

# Index/evaluation use embedded Qdrant exclusively before the API is started.
& (Join-Path $ragAppDirectory 'Start_Knowledge_Ollama.ps1')
Stop-OwnedRagService -Port 8020 -Module 'run_agent:app'
Stop-OwnedRagService -Port 8021 -Module 'evidence_bridge:app'
& $ragPython -B integration/knowledge/setup_resources.py
if ($LASTEXITCODE -ne 0) { throw 'Fresh index/resource verification failed. Existing derived data was preserved.' }
$ragRetrievalReport = Join-Path $ragProject 'project-docs\integration\knowledge-live-retrieval-results.json'
if (-not (Test-Path -LiteralPath $ragRetrievalReport)) {
    & $ragPython -B integration/knowledge/evaluate_live_retrieval.py
    if ($LASTEXITCODE -ne 0) { throw 'Real retrieval evaluation failed.' }
} else { Write-Host 'Existing retrieval evidence preserved; no repeated evaluation.' }
& $ragPython -B integration/knowledge/evidence_bridge.py
if ($LASTEXITCODE -ne 0) { throw 'Evidence credential preparation failed.' }
Start-RagService -Module 'run_agent:app' -Port 8020 -HealthPath '/health'
Start-RagService -Module 'evidence_bridge:app' -Port 8021 -HealthPath '/healthz'
& (Join-Path $ragAppDirectory 'Deploy_Development.ps1')
& $ragPython -B integration/knowledge/validate_deployment.py
if ($LASTEXITCODE -ne 0) { throw 'Published full-workflow ingress validation failed. Inspect its saved report before making model calls.' }

$ragLiveReport = Join-Path $ragProject 'project-docs\integration\knowledge-live-qwen-3b-results.json'
if (Test-Path -LiteralPath $ragLiveReport) {
    $ragPrevious = Get-Content -LiteralPath $ragLiveReport -Raw | ConvertFrom-Json
    if ($ragPrevious.errors.Count -or -not $ragPrevious.n8n_case) { throw 'An incomplete live report is preserved. Inspect it before repeating model calls.' }
    Write-Host 'Existing live RAG evidence preserved; no repeated model calls.'
} else {
    & $ragPython -B integration/knowledge/validate_live.py
    if ($LASTEXITCODE -ne 0) { throw 'Live RAG/n8n validation failed. Inspect the preserved report; no automatic retries.' }
}
Write-Host 'Development workflow: http://127.0.0.1:5679/workflow/municipalKnowledgeIntegrationDev'
Write-Host 'RAG validation uses real local models and labelled upstream fixtures. Fresh Intake/Vision execution and ticket persistence are separate pending stages.'
