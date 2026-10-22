param()

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project virtual environment.' }
}

& $pythonPath -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installing the RAG dependencies failed.' }

# Ollama supplies embedding weights. Hugging Face is used only for token counting.
ollama pull bge-m3
if ($LASTEXITCODE -ne 0) { throw 'Ollama could not download BGE-M3. No index was changed.' }
& $pythonPath -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('BAAI/bge-m3')"
if ($LASTEXITCODE -ne 0) { throw 'Downloading the BGE-M3 tokenizer failed.' }
ollama pull qwen2.5:3b
if ($LASTEXITCODE -ne 0) { throw 'Ollama could not download the generation model.' }

Write-Host 'Dependencies, tokenizer and Ollama models are ready. No index was changed.'
