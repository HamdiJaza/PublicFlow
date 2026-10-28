$ErrorActionPreference = 'Stop'
$translationWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$translationPython = Join-Path $translationWorkspace '.runtime\nvidia-intake-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $translationPython)) { throw 'The project Python environment is missing.' }
Write-Host 'Starting display-only Vision translation bridge on 8014 (NVIDIA text model, French and Arabic).'
$env:TRANSLATION_ALLOW_NVIDIA_CALLS = '1'
. (Join-Path $translationWorkspace 'integration\intake-local\NVIDIA_Credentials.ps1')
Invoke-WithProjectNvidiaKey -Action {
    # 0.0.0.0 like the other bridges so the n8n container reaches it; header credential required.
    & $translationPython -B -m uvicorn translation_bridge:app --app-dir $PSScriptRoot --host 0.0.0.0 --port 8014 --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Translation bridge stopped with an error.' }
}
