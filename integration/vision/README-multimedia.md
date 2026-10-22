# Multimedia development workflow

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

The development workflow accepts image + text, image + audio (optional text),
or video (optional text). The native Intake and Vision implementations are
unchanged. Gemini configuration/code remain available; NVIDIA is the selected
preparation provider. RAG and ticket persistence remain unavailable.

Open http://127.0.0.1:5679/workflow/municipalIntakeVisionDev.
Multipart ingress remains `POST /webhook/municipal-intake-vision` on port 5679.
The preserved image/text-only export is
`n8n/vision-integration/backups/image-text-development.json`.

## Contracts

| Citizen multipart fields | Native Intake multipart mapping |
| --- | --- |
| `report_id` | Kept internally; never supplied as an invented Intake field |
| `description` (optional with speech/video) | `texte`, empty when omitted |
| `location` (optional JSON) | Kept internally unchanged after validation |
| `image` + description | `image`, `texte` |
| `image` + `audio`, optionally description | `image`, `audio`, `texte` |
| `video`, optionally description | `video`, `texte` |

Image/video together, separate audio/video together, audio alone, text alone,
duplicate or unknown file fields and unsupported MIME types are rejected before
Intake. The previous single-image binary alias is retained for compatibility.
Location accepts only address, latitude and longitude. Missing location remains
unknown; integration fixtures use explicitly synthetic coordinates.

Intake `/analyser` still returns `intake-preparation-v1`. It reuses its existing
image validation, FFmpeg conversion/extraction, YuNet face processing, masking
and isolated storage tools. NVIDIA-hosted Whisper transcribes speech; Nemotron
normalizes the combined context into French. The native response is retained
internally, including both separate transcript fields. Gemini is not an
automatic fallback.

Gate 1 checks the expected media count/IDs/source, each processing record and
hash, confined paths, common request directory, required audio transcript,
usable normalized text, warnings, errors and optional provider provenance.
NVIDIA speech success must match the submitted audio or returned video speech.
The native API does not expose an independent video-audio-track boolean: for a
silent video Gate 1 relies on checked Intake's READY/errors evidence and usable
text; it does not invent proof that a track existed. No usable text means REVIEW.

All three video frames are processed sequentially through unchanged native
Vision `POST /vision`: one verified PNG, original report_id and cleaned_text as
description per request. Each transfer verifies receipt/hash via the existing
authenticated bridge; original uploads are never substituted on failure.
Every response gets the same Gate 2 validation as an independent image.
Uncertainty or failure stops later frames and requires REVIEW. All three passing
frames must agree on category AND severity before deterministic routing.
There is no vote, averaged confidence or invented merged native response.
The router consumes the first actual native response only after agreement.

`vision_frames` retains the native responses and individual gate/transfer results
inside workflow state. Public `visual_assessment` distinguishes attempted frame
requests, native responses received (`assessed_frames`), and COMPLETE/INCOMPLETE
coverage. A timeout has an attempt but no assessed frame. COMPLETE does not mean
the model is certain or correct. Trace entries identify the current media ID.
Public responses omit transcripts, native host paths and per-frame model bodies.

## Startup

From the repository root, run each service in its own PowerShell terminal:

```powershell
./intake-agent/Start_NVIDIA_Intake.ps1 -DockerAccess -EnableNvidiaApi
./integration/vision/Start_Media_Bridge.ps1
./integration/vision/Start_Vision_Dev.ps1
```

Ollama must already be serving the installed `qwen2.5vl:3b` model on port 11434.
No new dependency or model installation is required for this extension.
Publish only the development workflow:

```powershell
./integration/vision/Deploy_Development.ps1
```

Wait for webhook registration, not only `/healthz`; n8n can answer health checks
before registering workflows. GET the webhook URL: the message “This webhook is
not registered for GET requests. Did you mean to make a POST request?” confirms
the POST route exists without triggering processing.

After the controlled validation has created its local fixtures, examples are:

```powershell
$multimediaPhoto = 'vision-agent/Vision_Agent/02_VISION_PROJECT/841248136_1425441186447691_2938885808955356198_n.jpg'
$multimediaReport = 'RPT-AUDIO-' + [guid]::NewGuid().ToString('N').Substring(0,10)
curl.exe --max-time 6500 http://127.0.0.1:5679/webhook/municipal-intake-vision `
  -F "report_id=$multimediaReport" -F "image=@$multimediaPhoto" `
  -F 'audio=@.runtime/nvidia-provider-validation/synthetic-fr-v2.wav'

$multimediaReport = 'RPT-VIDEO-' + [guid]::NewGuid().ToString('N').Substring(0,10)
curl.exe --max-time 6500 http://127.0.0.1:5679/webhook/municipal-intake-vision `
  -F "report_id=$multimediaReport" `
  -F 'video=@.runtime/multimedia-live/synthetic-waste-video.mp4'
```

These commands trigger real provider processing. The constructed video repeats
one existing photo with synthetic French speech; it is not real incident footage.
Existing n8n execution-data saving remains disabled for privacy. Published runs
do not provide stored node payloads for inspection; use the returned safe trace
and controlled test reports. The temporary synthetic engine-check workflow saves
only synthetic execution data and is unpublished after testing.

## Verification

One command runs all four offline suites and checks all 318 original hashes:

```powershell
intake-agent/.venv/Scripts/python.exe -B integration/vision/verify_multimedia_offline.py
```

Individual suites:

```powershell
node n8n/vision-integration/tests/test_workflow.mjs
node n8n/vision-integration/tests/test_multimedia.mjs
.runtime/nvidia-intake-venv/Scripts/python.exe -B -m unittest discover -s intake-agent/tests -p 'test_*.py' -q
intake-agent/.venv/Scripts/python.exe -B -m unittest discover -s integration/vision -p test_media_bridge.py -q
```

`check_multimedia_engine.py` imports a separate, clearly labelled synthetic test
workflow. Its seven cases exercise the real n8n HTTP nodes, multipart transport,
code-node runtime, sequential branches and error paths. It makes no AI calls and
does not prove image decoding, transcription or model accuracy. Diagnostic runs
01–03 record startup-registration failures; runs 04 and 05 record successful
suites, with run 05 additionally checking final per-frame trace identifiers.
Existing reports are preserved rather than overwritten.

The live run in `project-docs/integration/multimedia-live-results.json` completed
both image/audio and constructed-video submissions in 82.04 seconds, with four
successful NVIDIA calls (two Whisper, two Nemotron), zero Gemini calls and no
retries. Both Intake results were READY and Gate 1 PASS. Both real Vision results
were WASTE/MEDIUM with confidence 0.8 and an uncertainty reason; Gate 2 correctly
returned REVIEW. Video stopped after frame 1 and reported 1/3 assessed. Three-frame
continuation and agreement are verified with the labelled synthetic engine suite,
not claimed as a live three-frame AI success. Six local Vision model calls were
recorded in total. Text usage was 918 tokens across two calls; no monetary cost
was returned. These results establish transport and policy behavior, not accuracy.

The bounded live harness is `Run_Multimedia_Validation.ps1`. It requires port 8012
to be free and the other development services ready, loads the saved encrypted
NVIDIA key without displaying it, caps the session at four NVIDIA calls, and
refuses to repeat an existing result. It temporarily serves the normal Intake
processing code with input-hash and call-budget guards; it does not alter agents'
prompts/models. Stop ordinary development Intake before running this harness,
then restart it afterward. Paid Gemini calls remain disabled throughout.

## Limits

* RAG and persistence are unavailable: final response stays REVIEW/202,
  ticket=null, persisted=false and review_queued=false. REVIEW is not a saved queue.
* Face-processing success does not prove removal of all personal information.
  Speech reaches the transcription provider before transcript masking.
* French synthetic speech is a transport test, not an Arabic/Tunisian speech
  benchmark. Mixed-language detection retains its existing conservative REVIEW.
* Native video preparation is limited to 60 seconds; speech conversion supports
  at most 120 seconds. Existing upload and n8n transport size limits still apply;
  this extension does not increase them. Use small clips for the demonstration.
* Native Vision can perform up to three local inference calls per image, hence
  up to nine for three video frames. Early REVIEW stops remaining frames.
* Each Vision HTTP timeout remains 2,000 seconds. Workflow deadline is 6,600
  seconds for bounded sequential processing. Retained media still expires after
  one hour: unusually slow later-frame reads fail closed to REVIEW. No lifetime
  extension or privacy guarantee is fabricated to force completion.
