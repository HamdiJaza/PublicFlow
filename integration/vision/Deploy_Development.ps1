$ErrorActionPreference = 'Stop'
$visionWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $visionWorkspace
$visionIntakePython = Join-Path $visionWorkspace 'intake-agent\.venv\Scripts\python.exe'
& $visionIntakePython -B integration/vision/media_bridge.py
if ($LASTEXITCODE -ne 0) { throw 'Bridge credential preparation failed' }
& $visionIntakePython -B n8n/vision-integration/build_workflow.py
if ($LASTEXITCODE -ne 0) { throw 'Workflow build failed' }
docker compose -f n8n/intake-integration/compose.dev.yaml stop n8n
if ($LASTEXITCODE -ne 0) { throw 'Development stop failed' }
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${visionWorkspace}/.runtime/media-bridge:/bridge:ro" n8n import:credentials --input=/bridge/n8n-credential.json
if ($LASTEXITCODE -ne 0) { throw 'Development credential import failed' }
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${visionWorkspace}/n8n/vision-integration:/vision-integration:ro" n8n import:workflow --input=/vision-integration/municipal-intake-vision-development.json
if ($LASTEXITCODE -ne 0) { throw 'Workflow import failed' }
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps n8n publish:workflow --id=municipalIntakeVisionDev
if ($LASTEXITCODE -ne 0) { throw 'Workflow publication failed' }
docker compose -f n8n/intake-integration/compose.dev.yaml up -d n8n
if ($LASTEXITCODE -ne 0) { throw 'Development restart failed' }
