# Knowledge Agent handoff

Run n8n in Docker Desktop and run this Python agent plus Ollama on the **same Windows PC**.
The agent uses port **8020**, separate from Vision's 8010. Python 3.11 and Ollama are required.

## 1. Set up once

Extract the ZIP. Open PowerShell in the extracted `Knowledge_Agent` folder.
Start Ollama, then run:

```powershell
& .\handoff\01_Setup_Knowledge.ps1
```

This installs dependencies, downloads real `bge-m3` and `qwen2.5:3b` models, caches
the BGE tokenizer, and builds both audited-corpus Qdrant collections locally.
Model weights and a prebuilt index are not included. Internet is required for setup.
Wait for **Setup finished** before continuing. Errors stop the script.

For an intentional rebuild, stop the API and run the same command with `-Rebuild`.
Moving this folder after indexing also requires a rebuild because manifests record its path.
Optional configuration is in `.env.example`; copy it to `.env` only if you need overrides.

## 2. Start the API

```powershell
& .\handoff\02_Start_Knowledge.ps1
```

Keep the terminal open. It checks installed resources before starting one Uvicorn worker.
API docs: `http://127.0.0.1:8020/docs`. A resource check is not a successful inference test.

In another PowerShell, opened in the same folder:

```powershell
& .\.venv\Scripts\python.exe -B -m scripts.smoke_knowledge
```

The command performs a real POST and saves the result under `evaluation/integration_runs`.
A valid refusal passes the integration contract; it does not demonstrate answer quality.

## 3. Import into n8n

Import `handoff/03_IMPORT_Knowledge_Webhook.json` through n8n's **Import from File**.
It contains Webhook → HTTP Request → Respond to Webhook, with no credentials or pinned outputs.
The HTTP node calls `http://host.docker.internal:8020/knowledge`, the Windows-host API
as reached from n8n's Docker container. Do not change it to container-local `localhost`.

For a test execution, click **Listen for test event**, then run:

```powershell
& .\.venv\Scripts\python.exe -B -m scripts.smoke_knowledge --url http://127.0.0.1:5678/webhook-test/municipal-knowledge
```

For regular use, publish/activate the workflow and use its **Production URL**:
`http://127.0.0.1:5678/webhook/municipal-knowledge` with the default Docker port mapping.
If n8n uses another host port, use the exact URL displayed by your n8n instance.

The workflow preserves the API's JSON body and HTTP status. A transport failure returns
502. It allows 420 seconds for a cold embedding/generation request; this is a timeout,
not a measured response time. Configuration follows the official
[HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/)
and [Respond to Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook/) nodes.

## 4. Connect the team pipeline

The HTTP node accepts either the imported webhook's `body` or a flat item from an upstream agent.
For the main workflow, copy **Call Knowledge API** after your routing/vision step and connect
its output downstream. Keep the full HTTP response so you can branch on `statusCode`.
Process `body` only for HTTP 200; handle other statuses as errors.

| Input | Requirement |
|---|---|
| `category` | `ROAD_DAMAGE`, `STREET_LIGHTING`, `WASTE`, `WATER_LEAK`, or `NONE` |
| `description` | Nonblank citizen question/description, at most 3,000 characters |
| `department` | Optional string or null |
| Prompt | Workflow pins the enabled `v4_grounded` prompt |

Do not forward extra Vision fields into the strict API request. The node explicitly maps
the supported fields. If Vision produces a null category, route that report to review first.
Keep your report ID in the parent workflow and merge it back after the call.

| Response | Meaning |
|---|---|
| `procedure` | Supported answer/contact, or null |
| `deadline` | Documented service deadline, or null |
| `answer_found` | True when an answer is supported; false is a successful refusal |
| `sources` | Selected source chunk IDs, URLs and scores; empty for refusal |
| HTTP 422 | Invalid request or unsupported prompt version |
| HTTP 503 | Missing index/dependencies/model, or busy local agent |
| HTTP 502 | Generation/validation error, or n8n transport failure |

`handoff/04_OPENAPI.json` contains the exported API schema. To inspect the HTTP node's
result in the main workflow, use `$json.statusCode` and `$json.body.answer_found`.
Read returned uncertainty as missing procedural evidence, not as an official municipal decision.

## Deliverables and verification

- `report/rag_report.pdf`: four-page report; editable LaTeX included.
- `prompts/README.md`, `prompts/knowledge/`: versioned prompt library, techniques and failures.
- `evaluation/prompt_*`, `evaluation/prompt_review.csv`: 25 actual model calls and critiques.
- `evaluation/retrieval/historical_replay.json`, `evaluation/queries.json`: historical retrieval comparison.
- `rag/sources.csv`, `rag/source_audit.json`, `rag/corpus/`: corpus, references and inclusion decisions.
- `handoff/VALIDATION_STATUS.json`: packaging checks and unverified steps.

The API uses v4 provisionally; later prompts introduced regressions. The source audit enables
nine entries and excludes three unresolved references. Existing retrieval scores describe the
original corpus. The corrected index must be built on your PC, then evaluated:

```powershell
# Stop the API first: embedded Qdrant is opened by one process at a time.
& .\.venv\Scripts\python.exe -B -m evaluation.evaluate_retrieval --live
```

The exported n8n workflow has not been executed in n8n here. Follow the real HTTP tests above
to verify it on your PC. Original secret settings, virtual environments, local model files,
active indexes, temporary test directories and PDF build files are excluded from the ZIP.
