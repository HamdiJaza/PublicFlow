$ErrorActionPreference = 'Stop'
$knowledgeWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $knowledgeWorkspace
$knowledgePython = Join-Path $knowledgeWorkspace '.runtime\knowledge-venv\Scripts\python.exe'
$knowledgeIntakePython = Join-Path $knowledgeWorkspace 'intake-agent\.venv\Scripts\python.exe'
# Check access before changing credentials or stopping any development service.
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker is not accessible. No workflow was imported or stopped.' }
& $knowledgeIntakePython -B integration/vision/media_bridge.py
if ($LASTEXITCODE -ne 0) { throw 'Verified-media credential preparation failed.' }
& $knowledgePython -B integration/knowledge/evidence_bridge.py
if ($LASTEXITCODE -ne 0) { throw 'Evidence credential preparation failed.' }
& $knowledgePython -B n8n/knowledge-integration/build_workflow.py
if ($LASTEXITCODE -ne 0) { throw 'Knowledge development workflow build failed.' }
docker compose -f n8n/intake-integration/compose.dev.yaml stop n8n
if ($LASTEXITCODE -ne 0) { throw 'Development stop failed.' }
try {
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${knowledgeWorkspace}/.runtime/media-bridge:/bridge:ro" n8n import:credentials --input=/bridge/n8n-credential.json
if ($LASTEXITCODE -ne 0) { throw 'Development verified-media credential import failed.' }
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${knowledgeWorkspace}/.runtime/knowledge-bridge:/knowledge-credential:ro" n8n import:credentials --input=/knowledge-credential/n8n-credential.json
if ($LASTEXITCODE -ne 0) { throw 'Development evidence credential import failed.' }
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${knowledgeWorkspace}/n8n/knowledge-integration:/knowledge-integration:ro" n8n import:workflow --input=/knowledge-integration/municipal-knowledge-development.json
if ($LASTEXITCODE -ne 0) { throw 'Development Knowledge workflow import failed.' }
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps n8n publish:workflow --id=municipalKnowledgeIntegrationDev
if ($LASTEXITCODE -ne 0) { throw 'Development Knowledge publication failed.' }
} finally {
docker compose -f n8n/intake-integration/compose.dev.yaml up -d n8n
if ($LASTEXITCODE -ne 0) { throw 'Development restart failed.' }
}
Write-Host 'Imported both bridge credentials and published the separate development workflow. Model inference still requires live validation.'
