$ErrorActionPreference = 'Stop'
$bridgeWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$bridgePython = Join-Path $bridgeWorkspace '.runtime\nvidia-intake-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $bridgePython)) {
    $bridgePython = Join-Path $bridgeWorkspace 'intake-agent\.venv\Scripts\python.exe'
}
Write-Host 'Starting authenticated verified-media bridge on 8013; no AI provider calls.'
& $bridgePython -B -m uvicorn media_bridge:app --app-dir $PSScriptRoot --host 0.0.0.0 --port 8013 --no-access-log
if ($LASTEXITCODE -ne 0) { throw 'Media bridge stopped with an error.' }
