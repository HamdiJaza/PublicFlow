# Native Vision integration

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

The delivered Vision code, prompts, model and native multipart contract are
unchanged. Its pinned requirements are installed in `.runtime/vision-venv`;
`requirements-lock.txt` records the resolved local environment. No system-wide
installation or model download was needed. Ollama already had `qwen2.5vl:3b`.

## Current verified result

Current multimedia workflow and launch/test instructions are in
[README-multimedia.md](README-multimedia.md). Real image/audio and constructed-video
submissions passed Intake/Gate 1; real Qwen uncertainty correctly produced Gate 2
REVIEW, stopping video after frame 1. Three-frame continuation is verified through
the real n8n engine with labelled HTTP doubles. See
`project-docs/integration/multimedia-live-results.json` and
`project-docs/integration/multimedia-engine-results-05.json`.

The earlier image/text development run is a fully fresh n8n -> NVIDIA Intake -> local Qwen
execution, recorded in `project-docs/integration/nvidia-intake-live-validation-01.json`.
Gate 1 passed. Actual Vision returned WASTE/MEDIUM, confidence 0.8 and consistency
true; its uncertainty reason correctly kept Gate 2 at REVIEW. The original
Gemini configuration remains available but is inactive in the running NVIDIA
development service. Native NVIDIA audio/video preparation also passed separately
with corrected synthetic French speech before multimedia webhook support was added.
See `intake-agent/README-nvidia.md` for provider startup.

The following engine/Gemini results are earlier, separately scoped evidence.

The real n8n engine retrieved the retained Intake PNG through an authenticated
bridge, posted it to native `POST /vision`, received actual Qwen inference and
applied Gate 2. The saved real Intake response was replayed explicitly; no fresh
Gemini request was made. A manual trigger replaced webhook ingress in this engine
check. This is not a claim that a fresh complete Intake+Vision webhook run occurred.

The subsequently approved fresh combined attempt is recorded in
`project-docs/integration/preparation-live-validation-combined-01.json`. Its single
Gemini request returned HTTP 503 (model high demand) after 3.559 seconds. The test
stopped without retry or fallback; Gate 1 returned REVIEW/INTAKE_UNAVAILABLE and
Vision was not called. The full fresh pipeline remains unverified. No token usage
or cost was returned. Normal development Intake was restored with paid calls off.

`project-docs/integration/vision-real-vision-result.json` records:

- Actual native Vision HTTP 200, model `qwen2.5vl:3b`, v11, three local model calls.
- Verified processed-image SHA matching Vision's saved run; cleaned text, original
  report ID, description and location preserved.
- Actual output WASTE/MEDIUM, confidence 0.8, text/image consistency true.
- Gate 2 REVIEW because the actual output included an uncertainty reason.
  No uncertainty was erased, and the gate was not weakened to obtain PASS.
- No department assignment on this real REVIEW path; routing PASS behavior was
  checked separately with labelled synthetic fixtures.
- No RAG, database, ticket creation or persisted human-review queue.

The real model's description/evidence are claims to assess, not verified field
facts. Confidence is uncalibrated. This one image is not an accuracy benchmark.

## Local services

Use existing processes when already running. From the repository root, each
startup command needs its own VS Code PowerShell terminal:

```powershell
./intake-agent/Start_NVIDIA_Intake.ps1 -DockerAccess -EnableNvidiaApi
./integration/vision/Start_Media_Bridge.ps1
./integration/vision/Start_Vision_Dev.ps1
```

Intake: 8012; verified-media bridge: 8013; unchanged Vision: 8010; Ollama: 11434;
development n8n: 5679. NVIDIA is explicitly enabled by the command above; Gemini
calls remain disabled. Starting
Vision uses the local installed model, not a Gemini API key.

To recreate the Vision environment (project-only installation):

```powershell
intake-agent/.venv/Scripts/python.exe -m venv .runtime/vision-venv
.runtime/vision-venv/Scripts/python.exe -m pip install -r integration/vision/requirements-lock.txt
```

To build/import/publish the separate development copy and bridge credential:

```powershell
./integration/vision/Deploy_Development.ps1
```

That script restarts only `municipal-n8n-dev` and uses its separate development
volume. The original production container/volume and all original 318 files stay
untouched. The original Intake-only workflows remain available as references.

## Contracts and gates

New webhook: `POST http://127.0.0.1:5679/webhook/municipal-intake-vision`.
Multipart fields: `report_id`, optional `description` and `location` JSON text,
plus image/text, image/audio (optional text), or video (optional text).
See [multimedia contract and gates](README-multimedia.md#contracts).

1. n8n sends native multipart `texte` with the supplied `image`, `audio` or `video`
   to Intake `/analyser`, using separate HTTP branches for each supported combination.
2. Gate 1 checks preparation, normalized text and face-processing evidence.
3. Bridge `POST /media/resolve` takes JSON `path` and expected `sha256`, requires
   `X-Municipal-Media-Key`, checks confined retained storage, receipt, expiry and
   actual content hash, then returns PNG bytes. Failed/expired transfer is REVIEW.
4. n8n replaces the original upload with those verified bytes. It checks bridge
   status, verification header, hash header and MIME type. The local bridge/HTTP
   channel is trusted; n8n does not independently open host paths.
5. Vision `/vision` receives multipart `image`, original `report_id`, and native
   `cleaned_text` as `description`. Text over 2,000 characters is REVIEW before
   Vision; it is never silently truncated.
6. Gate 2 validates each frame's native fields, report ID, run/media association, supported
   category, severity, evidence, text consistency, confidence type/range and
   `uncertainty_reason`. No mock-only version/uncertainty fields are invented.
   Null/unsupported categories, missing scores or model uncertainty mean REVIEW.
   No confidence cutoff is represented as measured correctness.
7. Image Gate 2 PASS, or three video frame PASS results with unanimous category
   and severity, reaches the original deterministic department mapping.
   RAG and ticket nodes remain disabled; successful routing still returns
   REVIEW/202 with `KNOWLEDGE_AND_PERSISTENCE_NOT_INTEGRATED`.

Native Vision responses are retained internally unchanged. The citizen response
contains decisions and safe trace/provenance, not native host paths or media.
HTTP failures after valid input are REVIEW; invalid citizen input is REJECT/422.
HTTP nodes have no retries. Vision's HTTP timeout is 2,000 seconds and workflow
timeout 6,600 seconds for up to three sequential frames. Each image allows its
existing up-to-three 600-second model stages. One-hour media expiry still applies
and fails closed for unusually slow later-frame transfers.

The bridge credential is generated into ignored `.runtime/media-bridge`, imported
as an n8n Header Auth credential, and absent from workflow JSON/source. It grants
only verified-media reads; there is no arbitrary URL fetch or fallback to raw
uploads. Face-processing evidence does not establish complete PII removal.

## Verification and one fresh combined test

Offline test commands:

```powershell
intake-agent/.venv/Scripts/python.exe -B -m unittest discover -s integration/vision -p test_media_bridge.py -v
node n8n/vision-integration/tests/test_workflow.mjs
```

`vision-offline-test-results.json` records bridge tests, original Vision tests,
workflow checks and original/Intake regressions. The engine transport-double and
real Vision records are separate, accurately labelled files in `project-docs/integration`.
`run_engine_check.py --real-vision` requires the unexpired recorded Intake media;
it refuses to substitute expired media or overwrite an existing result.

Another combined live check requires new explicit approval for **one new Gemini
cleaning call**. After approval, with Vision, bridge and n8n running and port 8012
free for the controlled Intake process:

```powershell
./intake-agent/Run_Preparation_Validation.ps1 -AllowApiCall -WithVision -RunLabel combined-02
```

This uses the user's encrypted project key, the approved waste photo/text,
one Gemini attempt, no retries/fallback, then fresh local Qwen inference. Model
uncertainty may correctly produce Gate 2 REVIEW; that is not a transport failure.
The harness verifies the saved Vision run's report ID, processed-image hash,
model/prompt and completed status. Result labels are single-use; do not overwrite
the failed `combined-01` evidence or repeat provider calls without approval.
