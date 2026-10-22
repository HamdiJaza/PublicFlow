param([switch]$PrepareOnly, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $appRoot
# Process-scoped only. No PATH, registry, firewall or system Python changes.
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $null
$env:PYTHONHOME = $null
$env:MUNICIPAL_PACKAGE_ROOT = $appRoot
$env:MUNICIPAL_N8N_CONTAINER = 'municipalite-auto-n8n'
$env:MUNICIPAL_POSTGRES_CONTAINER = 'municipalite-auto-postgres'
$appPython = Join-Path $appRoot 'vendor\python\python.exe'
if (-not (Test-Path -LiteralPath $appPython)) { throw 'Extract the entire Windows ZIP first; vendor/python is missing.' }
$appArguments = @('-B', (Join-Path $PSScriptRoot 'prepare.py'))
if ($PrepareOnly) { $appArguments += '--local-only' }
& $appPython @appArguments
if ($LASTEXITCODE -ne 0) { throw 'Setup stopped. The error above identifies the missing prerequisite. Re-run this launcher after correcting it.' }
if ($PrepareOnly) { return }
& (Join-Path $appRoot 'integration\portal\Start_Portal.ps1') -NoBrowser:$NoBrowser
if (-not $NoBrowser) {
    try {
        $appIntake = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8012/' -TimeoutSec 2
    } catch { Start-Process 'http://127.0.0.1:8090/setup' -WindowStyle Hidden }
}
