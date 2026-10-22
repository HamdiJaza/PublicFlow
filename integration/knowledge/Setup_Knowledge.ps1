param([switch]$DownloadModels)
$ErrorActionPreference = 'Stop'
$knowledgeWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$knowledgePython = Join-Path $knowledgeWorkspace '.runtime\knowledge-venv\Scripts\python.exe'
Set-Location -LiteralPath $knowledgeWorkspace
if (-not (Test-Path -LiteralPath $knowledgePython)) {
    & python -m venv (Join-Path $knowledgeWorkspace '.runtime\knowledge-venv')
    if ($LASTEXITCODE -ne 0) { throw 'Project-only environment creation failed.' }
}
& $knowledgePython -m pip install --retries 0 -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Project-only dependency installation failed.' }
& $knowledgePython -B (Join-Path $PSScriptRoot 'common.py')
if ($LASTEXITCODE -ne 0) { throw 'RAG delivery/runtime verification failed.' }
if ($DownloadModels) {
    # Explicit opt-in only: downloads BGE-M3. Qwen must already be installed.
    & $knowledgePython -B (Join-Path $PSScriptRoot 'download_models.py') --download
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed; no replacement models will be used.' }
}
& (Join-Path $PSScriptRoot 'Start_Knowledge_Ollama.ps1')
& $knowledgePython -B (Join-Path $PSScriptRoot 'setup_resources.py') --download-tokenizer
if ($LASTEXITCODE -ne 0) { throw 'Knowledge resources are incomplete. Preserve the originals; resolve the reported model/tokenizer/index prerequisite.' }
