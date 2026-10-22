$ErrorActionPreference = 'Stop'
$knowledgeWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$knowledgePython = Join-Path $knowledgeWorkspace '.runtime\knowledge-venv\Scripts\python.exe'
Write-Host 'Starting separate authenticated Knowledge evidence bridge on 8021; no model calls.'
& $knowledgePython -B -m uvicorn evidence_bridge:app --app-dir $PSScriptRoot --host 0.0.0.0 --port 8021 --workers 1 --no-access-log
if ($LASTEXITCODE -ne 0) { throw 'Knowledge evidence service stopped with an error.' }
