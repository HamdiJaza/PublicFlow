param([switch]$DockerAccess, [switch]$EnableNvidiaApi)
$ErrorActionPreference = 'Stop'
$nvidiaIntakeRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$nvidiaProjectRoot = Split-Path -Parent $nvidiaIntakeRoot
$nvidiaIntakePython = Join-Path $nvidiaProjectRoot '.runtime\nvidia-intake-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nvidiaIntakePython)) { throw 'Create the NVIDIA project environment from requirements-nvidia.txt first.' }
$nvidiaIntakeBind = if ($DockerAccess) { '0.0.0.0' } else { '127.0.0.1' }
Set-Location -LiteralPath $nvidiaIntakeRoot
# Gemini code and encrypted configuration are retained, but calls remain disabled.
$env:INTAKE_ALLOW_PAID_CALLS = '0'
$env:INTAKE_ALLOW_NVIDIA_CALLS = if ($EnableNvidiaApi) { '1' } else { '0' }
Write-Host 'NVIDIA preparation on 8012; French normalized text; Gemini inactive. Existing FFmpeg and face-processing tools are reused.'
if ($EnableNvidiaApi) {
    . (Join-Path $nvidiaProjectRoot 'integration\intake-local\NVIDIA_Credentials.ps1')
    Invoke-WithProjectNvidiaKey -Action {
        & $nvidiaIntakePython -B -m uvicorn local_intake.nvidia_preparation_app:app --host $nvidiaIntakeBind --port 8012 --workers 1 --no-access-log
        if ($LASTEXITCODE -ne 0) { throw 'NVIDIA Intake stopped with an error.' }
    }
} else {
    & $nvidiaIntakePython -B -m uvicorn local_intake.nvidia_preparation_app:app --host $nvidiaIntakeBind --port 8012 --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'NVIDIA Intake stopped with an error.' }
}
