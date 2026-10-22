# Native Intake development workflow

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

**Current development:** use `municipal-prepared-intake-development.json`, built
by `build_preparation_workflow.py`, and the preparation-only Intake on port 8012.
Its webhook is `/webhook/municipal-prepared-intake`. See
[the preparation contract and startup instructions](../../intake-agent/README-preparation.md).
Gate 1 now checks safe preparation; Vision owns classification, visual evidence,
severity and image/text consistency. Vision has not been modified.

The remainder of this document records the earlier native workflow and its
historical real Gemini validation. That four-call result is not evidence of a
live Gemini test of the new preparation-only contract.

The real development webhook was verified with the real native Intake and Gemini:
four successful provider calls, Gate 1 PASS, overall REVIEW/202. The actual result
is recorded in `project-docs/integration/live-n8n-intake-result.json`.

The separate running development instance is at **http://127.0.0.1:5679**. The
original `municipal-n8n` container and `n8n_data` volume were not changed.
`compose.dev.yaml` uses container `municipal-n8n-dev` and volume
`municipal_intake_development_data`, with a digest-pinned cached n8n 2.42.6 image.

From VS Code terminals at the repository root:

```powershell
docker compose -f n8n/intake-integration/compose.dev.yaml up -d
./intake-agent/Start_NVIDIA_Intake.ps1 -DockerAccess -EnableNvidiaApi
```

If the service is already running, use it instead of starting a second copy. Open
the development URL and complete first-time owner setup if asked. The imported,
published workflow is `Municipal - Native Intake - DEVELOPMENT ONLY`.

Default Intake startup explicitly sets paid calls OFF. The one approved live test
used a temporary four-call-capped service and has completed; no further paid calls
are authorized. Normal repeat submissions now return REVIEW while provider calls
are disabled. Do not use `-AllowPaidApi` without a separate approved budget.

For a brand-new development volume, import/publish **before** starting n8n:

```powershell
python -B n8n/intake-integration/build_workflow.py
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps n8n import:workflow --input=/integration/municipal-native-intake-development.json
docker compose -f n8n/intake-integration/compose.dev.yaml run --rm --no-deps n8n publish:workflow --id=municipalNativeIntakeDev
docker compose -f n8n/intake-integration/compose.dev.yaml up -d
```

These commands target only the separate development volume. They are unnecessary
for the already initialized instance. Do not import the development ID into the
existing production installation.

Import `municipal-native-intake-development.json` as a **new** workflow. It is
inactive, unpinned and based on the original Phase 5 export, which remains
unchanged. Do not replace or publish an existing production workflow.

The original downstream nodes are preserved but disabled and disconnected. The
only active path is input → native Intake → Gate 1 → response. A Gate 1 PASS goes
through an explicit downstream-unavailable checkpoint and returns overall REVIEW
(202), `ticket:null`, `persisted:false`, `review_queued:false`.

## Exact mapping

| Boundary | Mapping |
| --- | --- |
| Development webhook | POST multipart `/webhook/municipal-intake-integration` |
| Required citizen fields | `report_id`, `description`, one actual binary image |
| Optional location | `location` as JSON text with `address`, `latitude`, `longitude` |
| Native destination | `POST http://host.docker.internal:8011/analyser` |
| Native multipart fields | `image` = preserved n8n binary; `texte` = original description |
| Native response | Complete body retained as `intake_native`, unchanged |
| HTTP evidence | `intake_http.status_code`, body and safe transport-error class |
| Report context | `report_id`, `original.description`, `original.location`; never expected from Intake |
| Normalized text | Read `intake_native.cleaned_text`; do not rename the native field |

Let the HTTP node generate its multipart boundary. Retries are disabled. The
request timeout is 600 seconds and workflow timeout is 660 seconds. A client
timeout does not cancel server work; do not blindly resubmit.

## Gate 1 and traceability

The gate validates native types, text quality, municipal relevance, both human
review flags, multimodal coherence, image status/evaluation, warnings and retained
safe-reference shape. It checks the expected local service's tested privacy
invariant; it does not independently read container-inaccessible files. A path
alone is not proof. Use this export only with the supplied checked local service.

Unknown warnings, uncertainty, missing fields or unavailable privacy processing
produce REVIEW. Only the exact deterministic email/phone masking notice is
informational. Input errors produce REJECT; service errors/timeouts produce REVIEW.
The gate does not choose the final incident category or department.

No missing agent validation/confidence/version fields are invented. Source hash
metadata is deployment provenance, not a returned model version. n8n labels
inference as not independently verified because the native body has no provider
attestation. Other agents/storage remain `not_called`. Audit and citizen output
exclude raw descriptions, locations, media paths, native response and provider
errors. REVIEW is not a claim that a database queue exists.

Successful/error/manual execution-data retention is disabled in the development
export. The full native body remains in execution state while processing; review
it only in the controlled local editor. The service's private receipt is separate.

## Build and check

From repository root:

```powershell
python -B n8n/intake-integration/build_workflow.py
node n8n/intake-integration/tests/test_workflow.mjs
```

Rebuild after moving the repository or changing the local service: the export
contains this host's trusted safe directory and a local-source hash. The builder
never writes the original export. Node checks execute the actual embedded node
code against labelled synthetic and historical notebook cases; they are not real
inference or n8n-engine tests.

## Trigger after local startup and paid-call approval

Use the separate development instance on port 5679. Its published webhook route
is `/webhook/municipal-intake-integration`. Start Intake with
`Start_NVIDIA_Intake.ps1 -DockerAccess -EnableNvidiaApi`; obtain approval before enabling Gemini. Submit:

```powershell
curl.exe -X POST http://127.0.0.1:5679/webhook/municipal-intake-integration --form-string "report_id=RPT-LOCAL-001" --form-string "description=Actual description of your test image" --form "image=@C:/path/to/test-image.png"
```

For location, add `--form "location=<C:/path/to/location.json"` with a JSON file;
curl loads that file as a text form field. Do not upload it as a second binary.
Before paid-call approval, valid submissions should receive REVIEW because the
local service returns 503 with provider calls disabled. Missing media should be
REJECT at ingress and must not call Intake.

## Isolated engine check

`tests/prepare_engine_check.py` obtains a real native ASGI response using generated
media, real YuNet and a labelled model double, then builds an ignored replay under
`.runtime/engine-check`. The engine replay replaces the HTTP node with this saved
offline response and uses a Manual Trigger. It checks actual n8n JavaScript and
branch execution, not real webhook/multipart transport or paid inference.

The cached engine is 2.42.6. Its CLI requires import followed by
`execute --id=municipalIntakeOfflineCheck`; `execute --file` does not execute on
this version. Run only in a disposable container with network disabled and no
production volume. Results and limits are recorded in the integration report.

`tests/run_http_engine_check.py` goes further: it starts a temporary local test
service using real YuNet and a model double, then executes the actual n8n multipart
HTTP Request node. It uses the cached Docker image and no production volume. Its
Docker bridge can reach the temporary host service; no provider credential is
passed to the container and no paid calls occur. The CLI test still substitutes
Manual Trigger/final assertion for webhook registration and response nodes.
