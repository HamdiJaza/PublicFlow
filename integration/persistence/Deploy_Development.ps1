$ErrorActionPreference = 'Stop'
$ticketProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $ticketProject
$ticketPython = Join-Path $ticketProject '.runtime\nvidia-intake-venv\Scripts\python.exe'
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker unavailable; no service changed.' }
docker network inspect municipal-intake-development_default --format '{{.Name}}'
if ($LASTEXITCODE -ne 0) { throw 'Expected existing development network missing.' }
docker image inspect postgres:17-alpine --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw 'Cached PostgreSQL image missing; no automatic download.' }
& $ticketPython -B integration/persistence/setup.py
if ($LASTEXITCODE -ne 0) { throw 'Credential preparation failed.' }
& $ticketPython -B n8n/completion-integration/build_workflow.py
if ($LASTEXITCODE -ne 0) { throw 'Workflow build failed.' }
docker compose -f integration/persistence/compose.dev.yaml up -d --wait --wait-timeout 60
if ($LASTEXITCODE -ne 0) { throw 'Isolated ticket database did not start.' }
& $ticketPython -B integration/persistence/setup.py --initialize
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
docker compose -f n8n/intake-integration/compose.dev.yaml stop n8n
if ($LASTEXITCODE -ne 0) { throw 'Development n8n stop failed.' }
try {
    docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${ticketProject}/.runtime/persistence:/ticket-credentials:ro" n8n import:credentials --input=/ticket-credentials/n8n-credential.json
    if ($LASTEXITCODE -ne 0) { throw 'Ticket credential import failed.' }
    docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${ticketProject}/n8n/completion-integration:/completion:ro" n8n import:workflow --input=/completion/municipal-completion-development.json
    if ($LASTEXITCODE -ne 0) { throw 'Completion workflow import failed.' }
    docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps n8n publish:workflow --id=municipalCompletionDev
    if ($LASTEXITCODE -ne 0) { throw 'Development completion publication failed.' }
} finally {
    docker compose -f n8n/intake-integration/compose.dev.yaml up -d n8n
    if ($LASTEXITCODE -ne 0) { throw 'Development n8n restart failed.' }
}
Write-Host 'Separate completion workflow published. Verify live execution before claiming end-to-end success.'
