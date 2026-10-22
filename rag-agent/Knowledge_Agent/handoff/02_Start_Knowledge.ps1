param([int]$Port = 8020)

$ErrorActionPreference = 'Stop'
$knowledgeRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $knowledgeRoot
$knowledgePython = Join-Path $knowledgeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $knowledgePython)) {
    throw 'Run .\handoff\01_Setup_Knowledge.ps1 first.'
}
& $knowledgePython -B -m scripts.check_setup
if ($LASTEXITCODE -ne 0) { throw 'The agent is not configured yet. Resolve the reported setup error first.' }

Write-Host "Knowledge API: http://127.0.0.1:$Port/docs. Keep this terminal open; Ctrl+C stops it."
& $knowledgePython -B -m uvicorn api.knowledge_agent:app --host 0.0.0.0 --port $Port --workers 1
if ($LASTEXITCODE -ne 0) { throw 'The Knowledge API stopped with an error.' }
