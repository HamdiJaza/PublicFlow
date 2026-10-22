# Municipal Knowledge Agent — corrected RAG prototype

This is a separate RAG component. The original RAR and the Vision deliverables are unchanged.

For the portable n8n handoff, start with [the setup guide](00_START_HERE.md).

The service uses reviewed Tunisian public-service summaries, Ollama BGE-M3 embeddings,
Qdrant local storage, and a local `qwen2.5:3b` text model. It returns a procedure or
contact, a documented deadline if one exists, and source references.

## Verification status

- Nine source entries are enabled. Three unresolved entries are excluded from indexing.
- Historical retrieval scores have been recalculated with the API cutoff, 0.40.
- Twenty-five real local model calls test five prompt versions on five fixed-context development cases.
- Five offline contract tests pass. These use recorded fixtures and do not measure live retrieval.
- The corrected indexes and live retrieval/API evaluation are **not completed**. BGE-M3,
  its tokenizer and Qdrant dependencies are unavailable here; downloads failed through the session proxy.
- No n8n execution of this corrected component has been verified.

Start with [the short engineering record](docs/research/rag.md),
[the prompt library](prompts/README.md), and [the failure log](docs/failure_log.md).
Raw model responses and frozen inputs are under `evaluation/prompt_*`.

## Setup on Windows

Run commands from this folder, with Ollama running:

```powershell
# Open PowerShell in this extracted project folder.
& .\scripts\setup_dependencies.ps1
& .\.venv\Scripts\Activate.ps1
python -m rag.ingest --strategy all
```

The setup script installs Python dependencies, pulls `bge-m3` through Ollama,
downloads **only the BGE-M3 tokenizer** from Hugging Face, then pulls `qwen2.5:3b`.
It does not download Hugging Face model weights. Ingestion builds new indexes;
the archived SentenceTransformers vectors are never used with Ollama queries.
To change defaults, copy `.env.example` to `.env` and edit it. No original credentials are included.

If an index already exists, stop the API and run
`python -m rag.ingest --strategy all --rebuild` to replace derived vectors.
Do this after any corpus, source ledger, chunker or embedding-artifact change.
Qdrant local storage must be opened by only one process at a time.

## Run and test

```powershell
python -m uvicorn api.knowledge_agent:app --host 0.0.0.0 --port 8020
```

Open `http://127.0.0.1:8020/docs`. `POST /knowledge` accepts JSON:

```json
{
  "category": "STREET_LIGHTING",
  "description": "Quel numéro contacter pour signaler un câble électrique tombé au sol ?"
}
```

Labels: `ROAD_DAMAGE`, `STREET_LIGHTING`, `WASTE`, `WATER_LEAK`, `NONE`.
Optional fields: `department`, `strategy` (`structure` or `fixed`),
`prompt_version` (the service enables only `v4_grounded`). Historical and experimental
prompts are available through the experiment runner, not through the service.
`answer_found=false` means no answer was supported; an unavailable index or model is an HTTP error.
`GET /health` reports configuration and manifest presence, not a successful live search.

In another PowerShell with the environment activated:

```powershell
python -m evaluation.test_api_queries
```

This saves all five HTTP results, including errors, under `evaluation/http_runs`.
The API separately saves actual requests, selected contexts and raw model responses
under `evaluation/api_runs`. Review answer wording as well as the numeric checks.

## n8n on the local Docker Desktop

Run Ollama and this API on the local PC. In an n8n **HTTP Request** node use:

| Setting | Value |
|---|---|
| Method | POST |
| URL | `http://host.docker.internal:8020/knowledge` |
| Body | JSON; map `category` and `description` from the preceding agent |
| Timeout | 420000 ms |
| Optional department | Map the routing agent's department |

Use the returned `procedure`, `deadline`, `answer_found` and `sources` downstream.
Handle HTTP errors separately from a successful refusal. This is the integration contract,
not evidence that the group's full automation has run. Port 8020 is separate from Vision's 8010.

## Reproduce evaluations

Stop the API before direct local-Qdrant evaluation:

```powershell
python -m evaluation.evaluate_retrieval
python -m evaluation.evaluate_retrieval --live
python -m unittest discover -s tests -v
```

The first command only replays original saved scores. The second requires both corrected
indexes and preserves the original query references, including two now-excluded documents.
It records those as coverage failures instead of changing the references to improve scores.

To run a new fixed-context prompt comparison without retrieval:

```powershell
python -m evaluation.prompt_experiment --versions v3_structured v4_grounded --output evaluation/new_prompt_comparison
```

Use a new output folder for each changed protocol. Existing studies retain their raw outputs
and exact implementation snapshots. Do not treat these five reused development cases as an independent test set.

Groq remains an optional untested provider: set `GENERATION_PROVIDER=groq`, a currently available
`GROQ_MODEL`, and your own `GROQ_API_KEY` in the environment. Its original model tag and old results
have not been validated here. Local prompt results do not establish Groq performance.
