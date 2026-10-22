param([switch]$Rebuild)

$ErrorActionPreference = 'Stop'
$knowledgeRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $knowledgeRoot

# Install dependencies and real models before building either local collection.
& (Join-Path $knowledgeRoot 'scripts\setup_dependencies.ps1')
$knowledgePython = Join-Path $knowledgeRoot '.venv\Scripts\python.exe'
$ingestArguments = @('-B', '-m', 'rag.ingest', '--strategy', 'all')
if ($Rebuild) { $ingestArguments += '--rebuild' }
& $knowledgePython @ingestArguments
if ($LASTEXITCODE -ne 0) { throw 'Indexing failed. Read the error above; no successful setup is claimed.' }

& $knowledgePython -B -m scripts.check_setup
if ($LASTEXITCODE -ne 0) { throw 'Resource checks failed. Resolve the reported issue before starting the API.' }
Write-Host 'Setup finished. Start the service with .\handoff\02_Start_Knowledge.ps1.'
