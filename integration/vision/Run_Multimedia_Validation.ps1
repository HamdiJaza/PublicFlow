$ErrorActionPreference = 'Stop'
$multimediaProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $multimediaProject 'integration\intake-local\NVIDIA_Credentials.ps1')
Invoke-WithProjectNvidiaKey -Action {
    & (Join-Path $multimediaProject '.runtime\nvidia-intake-venv\Scripts\python.exe') -B (Join-Path $PSScriptRoot 'validate_multimedia_live.py') --run
    if ($LASTEXITCODE -ne 0) { throw 'Controlled multimedia validation stopped. Inspect the result; do not retry automatically.' }
}
