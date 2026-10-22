$ErrorActionPreference = 'Stop'
$knowledgeWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$knowledgePython = Join-Path $knowledgeWorkspace '.runtime\knowledge-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $knowledgePython)) { throw 'Prepare the project Knowledge environment first.' }
& (Join-Path $PSScriptRoot 'Start_Knowledge_Ollama.ps1')
Write-Host 'Starting unchanged native Knowledge API on 8020. Missing resources remain HTTP 503; no paid provider is enabled.'
& $knowledgePython -B -m uvicorn run_agent:app --app-dir $PSScriptRoot --host 0.0.0.0 --port 8020 --workers 1 --no-access-log
if ($LASTEXITCODE -ne 0) { throw 'Knowledge service stopped with an error.' }
