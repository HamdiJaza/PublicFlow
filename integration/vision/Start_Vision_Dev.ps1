param([string]$OllamaUrl = 'http://127.0.0.1:11434')
$ErrorActionPreference = 'Stop'
$visionWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$visionPython = Join-Path $visionWorkspace '.runtime\vision-venv\Scripts\python.exe'
$visionProject = Join-Path $visionWorkspace 'vision-agent\Vision_Agent\02_VISION_PROJECT'
if (-not (Test-Path -LiteralPath $visionPython)) { throw 'Prepare the isolated Vision environment first.' }
$env:OLLAMA_BASE_URL = $OllamaUrl
Write-Host 'Starting unchanged Vision API on 8010 with local Ollama.'
& $visionPython -B -m uvicorn agents.vision.api:app --app-dir $visionProject --host 0.0.0.0 --port 8010 --no-access-log
if ($LASTEXITCODE -ne 0) { throw 'Vision service stopped with an error.' }
