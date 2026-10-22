# Republish only the existing development workflow; no database/container creation.
$ErrorActionPreference = 'Stop'
$recordingProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $recordingProject
$recordingActive = @(Get-ChildItem .runtime\portal\jobs -Filter 'RPT-*.json' | ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
} | Where-Object { $_.state -in @('queued','running') })
if ($recordingActive.Count -ne 0) { throw 'An upload is active; no service stopped.' }
$recordingStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$recordingBackup = Join-Path $recordingProject '.runtime\backups'
[IO.Directory]::CreateDirectory($recordingBackup) | Out-Null
docker exec municipal-n8n-dev n8n export:workflow --id=municipalCompletionDev --output=/tmp/municipal-completion-before-publish.json
if ($LASTEXITCODE -ne 0) { throw 'Existing workflow export failed; nothing stopped.' }
docker cp municipal-n8n-dev:/tmp/municipal-completion-before-publish.json (Join-Path $recordingBackup "completion-$recordingStamp.json")
if ($LASTEXITCODE -ne 0) { throw 'Existing workflow backup failed; nothing stopped.' }
& .\.runtime\nvidia-intake-venv\Scripts\python.exe -B n8n/completion-integration/build_workflow.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed; nothing stopped.' }
$recordingActive = @(Get-ChildItem .runtime\portal\jobs -Filter 'RPT-*.json' | ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
} | Where-Object { $_.state -in @('queued','running') })
if ($recordingActive.Count -ne 0) { throw 'An upload started during backup; no service stopped.' }
docker compose -f n8n/intake-integration/compose.dev.yaml stop n8n
if ($LASTEXITCODE -ne 0) { throw 'Development n8n stop failed.' }
try {
    docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps -v "${recordingProject}/n8n/completion-integration:/completion:ro" n8n import:workflow --input=/completion/municipal-completion-development.json
    if ($LASTEXITCODE -ne 0) { throw 'Development workflow import failed.' }
    docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps n8n publish:workflow --id=municipalCompletionDev
    if ($LASTEXITCODE -ne 0) { throw 'Development workflow publication failed.' }
} finally {
    docker compose -f n8n/intake-integration/compose.dev.yaml up -d n8n
    if ($LASTEXITCODE -ne 0) { throw 'Development n8n restart failed.' }
}
Write-Host 'Development completion workflow published; previous version backed up. No database changes.'
