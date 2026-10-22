$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'NVIDIA_Credentials.ps1')
$nvidiaWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$nvidiaPython = Join-Path $nvidiaWorkspace 'intake-agent\.venv\Scripts\python.exe'
$nvidiaBenchmark = Join-Path $PSScriptRoot 'benchmark_nvidia.py'
Write-Host 'NVIDIA free-development-endpoint benchmark: up to 13 synthetic text calls, no retries or provider switches.'
Invoke-WithProjectNvidiaKey -Action {
    & $nvidiaPython -B $nvidiaBenchmark --run
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark stopped. Inspect the sanitized result; do not repeat calls automatically.' }
}
