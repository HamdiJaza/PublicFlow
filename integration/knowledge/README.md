# Native Knowledge integration — development

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

The delivered Knowledge implementation is preserved under
`rag-agent/Knowledge_Agent`. All 127 delivered files match its package
inventory and are backed up in ignored `.runtime/backups/knowledge-delivery.zip`.
The integration runs a byte-identical copy under `.runtime/knowledge-agent`.
No delivered model, prompt, corpus file, schema or processing function was edited.

The demonstration scope is the **Commune de Tunis**, explicitly confirmed by the
user, plus the national Tunisian services identified by the selected sources.
This does not fill missing report addresses or coordinates or establish that a
particular road belongs to a particular authority.

The recovered integration selects **qwen2.5:3b**, as confirmed by the user on
2026-10-18. It is the delivered generation model and is already installed on
this PC. The archive's unfinished qwen2.5:latest override is preserved in the
original ZIP and Git history; no replacement generation model was downloaded.
Setup downloads **BGE-M3 only**, plus its public tokenizer for chunking. It refuses
to download a replacement generation model if the installed Qwen tag is missing.

## Verified status

The final running-state and evidence summary is
[knowledge-completion-20261018.json](../../project-docs/integration/knowledge-completion-20261018.json).

* Project-only Python dependencies are installed and pinned in requirements-lock.txt.
* The recovered setup passes 237 offline checks, including 68 Intake tests,
  six media-bridge tests, 81 existing Intake/Vision workflow checks, five native
  Knowledge contract tests, 32 Knowledge integration tests and 45 Knowledge
  workflow checks. These are not model quality measurements.
* Ten archived development n8n engine cases pass. Positive answers/evidence are
  explicitly synthetic fixtures. The missing-index 503 and strict-request 422
  cases call the real native API. Those archived checks made no model calls.
* Before indexing, actual recovered HTTP checks on ports 8020/8021 confirmed native health/configuration,
  missing-index 503 and strict-contract 422 responses. This does not prove retrieval.
* BGE-M3 and the pinned n8n image are downloaded. Ollama verified the model
  digest; its installed manifest digest is
  `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`.
  Fresh embedded Qdrant indexes contain 12 structure chunks and 9 fixed chunks
  from the 9 enabled documents. Original archived vectors were not reused.
* Twenty actual retrieval measurements compare both chunkers on the original
  ten questions. Retained Hit@3 is 5/9 for structure and 6/9 for fixed positive
  questions. Two expected sources are excluded; the original references remain
  unchanged. The negative question still retrieves context, so similarity alone
  does not establish answerability. These results are development measurements.
* Three real native requests and one actual n8n -> RAG -> evidence/Gate 3 request
  completed, recording four local qwen2.5:3b generations and zero cloud calls.
  The water diagnostic question returned an answer with verified indexed sources;
  its paraphrase does not satisfy the conservative verbatim gate. The electrical,
  unsupported repair-deadline and n8n waste-procedure questions returned refusals.
  The actual n8n case returned REVIEW/202 with verified evidence and no ticket.
  Its upstream state was explicitly a fixture, not fresh Intake/Vision execution.
* The published complete development workflow rejected three invalid submissions
  before calling any agent. Evidence is in knowledge-deployment-53e8f733fd.json.
* Nine fresh n8n engine checks passed: synthetic supported answer, refusal,
  paraphrase, invalid schema, missing receipt, invalid evidence, timeout,
  upstream REVIEW, and an actual native contract rejection (422). These tests
  made zero model calls. Results: knowledge-engine-recovered-20261018.json.
* An additional real n8n water-diagnosis request returned a positive answer with
  three actual indexed citations and a verified receipt. Gate 3 correctly kept
  the paraphrase in REVIEW. This is saved separately in
  knowledge-live-water-n8n-20261018.json. Total recorded local generations across
  the two live reports: five; cloud calls: zero.
  That water answer was in English despite a French question; language adherence
  remains a quality limitation alongside the conservative grounding decision.
* Actual indexing, retrieval and model evidence is saved in
  knowledge-index-results.json, knowledge-live-retrieval-results.json and
  knowledge-live-qwen-3b-results.json. Historical reports remain unchanged,
  including knowledge-verification-results.json.

Current offline checks are recorded in
`project-docs/integration/knowledge-verification-recovered-results.json`.
Actual HTTP checks: `project-docs/integration/knowledge-recovered-service-smoke.json`.
Earlier engine evidence remains in knowledge-engine-results.json. Supplied prompt runs and
retrieval metrics are the teammate's separate evidence; they are not new runs on
this machine or measurements of a freshly built index.

## Native API and mapping

Native endpoint: `POST http://127.0.0.1:8020/knowledge`, JSON:

```json
{
  "category": "WASTE",
  "department": "SANITATION_DEPARTMENT",
  "description": "Normalized citizen context from Intake",
  "strategy": "structure",
  "prompt_version": "v4_grounded"
}
```

These are native fields, not a new schema. category supports ROAD_DAMAGE,
STREET_LIGHTING, WASTE, WATER_LEAK and NONE. Integration only calls after Gate 2
PASS on one of the four supported incident categories. Description is nonblank
and at most 3,000 characters. Department is optional natively; n8n supplies its
deterministic internal department code without pretending it is an official
department name from the source ledger. strategy is structure or fixed. Only
v4_grounded is enabled by the service; other prompt versions return 422.

Native HTTP 200 body remains exactly:

```json
{
  "procedure": null,
  "deadline": null,
  "answer_found": false,
  "sources": []
}
```

This example is a schema illustration, not a captured real model answer. A
supported answer has answer_found=true, a nonblank procedure and selected sources
with chunk_id, url and numeric score. deadline is null when unsupported. A refusal
is a successful HTTP result, distinct from HTTP 503 (unready/busy), 502 (generation
or output-validation failure), 422 (invalid contract) or a transport timeout.

n8n sends validated Vision category, Intake cleaned_text, deterministic department,
structure and v4_grounded. Report ID, original description, location, native Intake
and native Vision results stay in parent workflow state. No report_id, confidence,
location or full Vision object is sent into the strict Knowledge API.

## Workflow

New development workflow:
http://127.0.0.1:5679/workflow/municipalKnowledgeIntegrationDev

Name: **Municipal - Intake + Vision + Knowledge - DEVELOPMENT ONLY**.
JSON: `n8n/knowledge-integration/municipal-knowledge-development.json`.
Webhook: `POST http://127.0.0.1:5679/webhook/municipal-full-development`.
Citizen multipart fields and audio/video behavior are unchanged from the
[working multimedia integration](../vision/README-multimedia.md).

The existing Intake/Vision workflow and its webhook remain available as backups.
The original production n8n container on 5678 is not started or modified.

Flow: Intake -> Gate 1 -> sequential Vision/frame checks -> Gate 2 -> frame
agreement -> deterministic department -> native Knowledge -> Gate 3 -> persistence
checkpoint. A REVIEW at an upstream gate prevents Knowledge from running.
The Knowledge HTTP timeout is 420 seconds, no retries/fallback; evidence reads
have a 15-second timeout. Full workflow timeout is 7,200 seconds. Existing media
expiry still applies. Ticket persistence/review queue remain unavailable:
final response is REVIEW/202, ticket=null, persisted=false, review_queued=false.
Passing all three gates does not fabricate a ticket or an operational review queue.

## Evidence and Gate 3

The native source API returns chunk IDs/URLs/scores, not retrieved passage text or
claim-level proof. Its own validator checks strict fields, refusal consistency
and lexical support for a non-null deadline. It does not prove every generated
claim. The corpus contains nine enabled source summaries and three excluded
unresolved references; most sources do not document a full local incident workflow.

An integration wrapper retains native save_record behavior in ignored runtime
storage and adds only X-Knowledge-Receipt and X-Knowledge-Receipt-SHA256 response
headers for completed requests. The public JSON body and OpenAPI contract remain
unchanged. This is service-recorded evidence, not independent verification of
model weights or semantic truth. The wrapper forces the delivered local model
configuration; it does not enable Groq, change prompts or provide a fallback.

New **integration-only** endpoint `POST :8021/evidence/verify` is separate from
the agent. It uses its own generated n8n Header Auth credential. No key is embedded
in workflow JSON. It compares the actual native request/response with an unexpired
receipt, index and corpus fingerprints, exported actual indexed chunk payloads,
the enabled source ledger, category, selected context, URLs and scores. It does
not open the embedded Qdrant store while the API holds its lock. The catalog is
exported only after successful real ingestion; no fake catalog is created in the
development runtime. Receipts expire for verification after one hour; local
debug records are ignored by Git and are not claimed to be automatically deleted.

Gate 3 remains deterministic. A true answer needs actual verified context,
recorded native generation and a procedure occurring verbatim in the selected
source text (Unicode/whitespace/case normalized, minimum 20 characters). A
paraphrase stays REVIEW rather than claiming unmeasured entailment. Source scores
use the agent's 0.40 cutoff as a retrieval rule, not a truth probability. Non-null
service deadlines also require REVIEW because no response/repair commitment has
been certified by this integration. Refusals, missing sources, invalid receipts,
schema failures, timeouts and unavailable resources require REVIEW.

Verbatim support and matching category do not establish question-specific
applicability, currentness of an official page, or correct real-world advice.
These limits remain explicit in gate metadata. Improving semantic validation or
approving deadline-bearing procedures requires separate evidence; changing a
threshold or suppressing a refusal just to get PASS is not acceptable.

## Start existing prepared services

Use separate VS Code PowerShell terminals from the repository root:

```powershell
./integration/knowledge/Start_Knowledge_Dev.ps1
./integration/knowledge/Start_Evidence_Bridge.ps1
```

The API can start before models/indexes are ready: GET /health reports
configuration and index-file presence, while POST /knowledge returns 503.
Do not describe /health status=configured as a successful inference test.

Import/publish the separate development workflow:

```powershell
./integration/knowledge/Deploy_Development.ps1
```

Wait for POST webhook registration, not only n8n /healthz. GET the webhook URL
and check for “Did you mean to make a POST request?” without triggering inference.
Intake, the verified-media bridge, unchanged Vision and Ollama must be running
for a real citizen submission. Their startup commands remain in the multimedia
README. Do not rerun upstream cloud processing merely to test an unavailable RAG.

## Model/index setup — BGE-M3 only

The user approved the BGE-only download and installed-Qwen configuration. Stop
only the development Knowledge API before indexing and use:

```powershell
./integration/knowledge/Setup_Knowledge.ps1 -DownloadModels
```

This installs only the pinned project virtualenv packages, adds the exact bge-m3
model to shared Ollama storage, reuses qwen2.5:3b, downloads only the public BGE-M3
tokenizer into `.runtime/huggingface`, and builds new audited structure/fixed
collections under `.runtime/knowledge-data/qdrant`. It does not install Hugging
Face model weights or use private Hugging Face credentials. No existing models,
archived indexes or original files are deleted. Existing/partial derived indexes
are preserved for inspection; there is no automatic destructive rebuild.

Without -DownloadModels the script never pulls models and fails clearly if a
required resource is missing. After real ingestion,
restart the API, run native real queries and the supplied live retrieval evaluation
in the runtime copy, then test n8n with actual RAG responses. A valid refusal is
not evidence of procedural coverage; do not relax Gate 2 on the waste photo to
force a downstream call. Isolated RAG transport tests must be labelled as such.

## Offline verification

```powershell
.runtime/knowledge-venv/Scripts/python.exe -B -m unittest discover -s integration/knowledge -p 'test_*.py' -v
node n8n/knowledge-integration/tests/test_workflow.mjs
```

The delivered five tests can run with the same interpreter and working directory
`rag-agent/Knowledge_Agent`; use its absolute interpreter path. They mock
record writes and do not change the original files. `check_engine.py` is a bounded
ten-case test that imports a separate clearly labelled temporary workflow,
exercises positive/refusal/error cases with synthetic services plus native 503/422,
and unpublishes that temporary workflow afterward. It refuses to overwrite its
existing report or make a supposedly model-free 503 probe once a real index exists.

For new actual RAG validation after indexing, run validate_live.py. It makes at
most four local generation requests, verifies actual receipts and indexed context,
and preserves its result without automatic retries. Its n8n case explicitly seeds
upstream state: it proves n8n -> real RAG -> Gate 3, not fresh Intake/Vision execution.
The primary workflow's upstream gates remain enforced. evaluate_live_retrieval.py
runs the delivered fixed/structure evaluation with unchanged expected document
references; excluded documents remain coverage failures, not relabelled successes.

## Recovery and Hugging Face download

The Knowledge workflow builder rebinds the media root to this checkout in its
own export. It does not rewrite the preserved Intake/Vision export. The bundled
environments were rebound to this PC with `python -m venv --without-pip` while
retaining their packaged dependencies. Tokenizer cache symlinks were restored as
confined file copies. All 318 earlier original files and 127 RAG delivery files
remain byte-identical to their saved baselines.

Run the aggregate checks from the repository root:

```powershell
.runtime/knowledge-venv/Scripts/python.exe -B integration/knowledge/verify_offline.py
```

On Windows, this runner creates synthetic unit fixtures with inherited project
directory ACLs. Python's private temporary-directory ACL excluded this restricted
session, even inside the workspace. The fixture override is confined to
`.runtime/offline-test-temp`; product storage and original tests are unchanged.

The user requested the official [BAAI/bge-m3 repository](https://huggingface.co/BAAI/bge-m3).
Its pinned PyTorch checkpoint can be downloaded with:

```powershell
.runtime/knowledge-venv/Scripts/python.exe -B integration/knowledge/download_huggingface.py --download --label hf-02
```

This uses revision `5617a9f61b028005a4858fdac845db406aefb181`, downloads dense
model/tokenizer files only, and verifies the published checkpoint SHA-256. It
uses the default session networking without bypassing proxies or TLS. The failed
`hf-01` evidence is preserved; use a new label for an authorized retry. Interrupted
or mismatched files remain `.partial` and are never claimed as verified weights.

Downloading this checkpoint does not register an Ollama model. The native agent
currently embeds through Ollama, so Hugging Face weights still require a verified
compatible conversion/import before the unchanged native adapter can use them.
No conversion, embedding-provider change or real retrieval is claimed. Fresh
indexes must be built for the actual embedding artifact; old vectors are not reused.

The live validator now distinguishes a correct no-context refusal (retrieval
completed, generation not called) from a generated refusal. It never counts a
missing, incomplete or different-model response as completed generation.

To repeat a bounded test while preserving the earlier evidence, use a new label:

```powershell
.runtime/knowledge-venv/Scripts/python.exe -B integration/knowledge/validate_live.py --n8n-only-water --label water-repeat-01
.runtime/knowledge-venv/Scripts/python.exe -B integration/knowledge/check_engine.py --skip-missing-index-case --label engine-repeat-01
```

The first command makes one real local generation; the second makes zero model
calls. Both use separate temporary workflows with labelled upstream fixtures,
then unpublish them and restore development n8n. They refuse existing report labels.

## Local GPU runtime recovery

The downloaded BGE artifact initially failed on this PC's GTX 1050: the shared
Ollama CUDA runner crashed in flash-attention initialization and returned HTTP
500. `Start_Knowledge_Ollama.ps1` starts a project-only Ollama process on
`127.0.0.1:11435` with `OLLAMA_FLASH_ATTENTION=0`, `OLLAMA_NO_CLOUD=1` and
`OLLAMA_NOPRUNE=1`, reusing the existing model store. This follows the documented
[Ollama flash-attention setting](https://github.com/ollama/ollama/blob/main/docs/faq.mdx).
Environment changes apply only to the child process and are restored in the
launcher. Shared Ollama on 11434 and the native member implementation remain
unchanged. The integration configuration points Knowledge at the project process.

A real embedding probe returned 1,024 finite components with normalized length
1.0, then both native indexes and all four recorded generations succeeded.
The incomplete first index is preserved under `.runtime/knowledge-data/qdrant-failed-cuda-*`.
The evidence exporter now explicitly closes its Qdrant client; the installed
client does not implement Python's context-manager protocol. Completed vectors
were preserved while correcting that integration-only export bug.

The normal Knowledge startup, setup and resume commands start/reuse this project
Ollama process. Its logs and process identity are stored in
`.runtime/knowledge-ollama`; model downloads still use the shared store.

Ticket persistence, durable review, tracking and deterministic priority still need
implementation after real RAG validation. Frontend work is deferred by the user.

## Resume download and development n8n validation

From a normal PowerShell terminal with Ollama and Docker Desktop running:

```powershell
cd C:\Municipal\MunicipaliteAuto
./integration/knowledge/Resume_RAG_Development.ps1 -DownloadModels
```

`-CheckOnly` inspects prerequisites without downloading, stopping services,
calling models or deploying. The resumable command uses the native Ollama BGE-M3
distribution, reuses the pinned local n8n image (pulling it only if missing) before stopping
services, reuses the installed Qwen 3B and recovered tokenizer, builds both
indexes, runs the real retrieval evaluation, starts Knowledge/evidence services,
imports both media and Knowledge credentials into development n8n, and runs the
bounded real RAG validator. It makes no hosted Intake calls. Positive or refusal
RAG results remain real; its seeded upstream state is explicitly a fixture.
This does not prove fresh Intake/Vision execution or ticket persistence.
Before real RAG requests, validate_deployment.py executes three deliberately
invalid submissions against the published full workflow and verifies REJECT,
unchanged report identifiers, all agent stages not called, and no persistence
claims. These are actual n8n ingress checks, not AI-quality measurements.

Before indexing, only a listening Python process whose command identifies this
checkout's absolute Knowledge app directory, expected module and expected port
may be stopped. Unrecognized services are left alone. The script preserves
existing indexes and reports; it stops on an incomplete live report for inspection
instead of silently repeating model calls. Logs go to ignored `.runtime/rag-resume`.

Deployment now imports the verified-media credential as well as the Knowledge
evidence credential, so a fresh development n8n volume does not depend on an
earlier Vision deployment. Docker access is checked before deployment changes.
The live validator checks Docker before inference and restarts development n8n
even when temporary-workflow import or cleanup fails. No production container
or workflow is addressed. These deployment changes have offline failure-path
tests and the actual n8n execution reports listed above.

The archived NVIDIA Intake key cannot be decrypted on this Windows account.
Fresh hosted Intake testing needs a key saved locally using
`integration/intake-local/Configure_NVIDIA_Key.ps1 -Replace` and explicit
authorization for the intended provider calls. Keep keys out of chat and logs.
No cloud calls are made by the RAG resume command.

The recovered development n8n editor is available at http://127.0.0.1:5679.
A fresh volume asks for local owner-account setup; the final recovery check
reported setup complete on this instance. CLI publication and the tested webhooks
work. No owner password or API key is embedded here.
