# Vision submission

Scope: photo analysis, the required HTTP interface and prompt/model experiments.

Completed study: 25 planned attempts, all recorded and reviewed; all request hashes reconstructed successfully. Both prompt conditions returned 11/11 valid outputs. Clear-reference category agreement was 5/5 for v2 and 4/5 for v3; conservative abstention was 0/4 and 3/4. Severity and text mismatch failures remain documented. These are small development-case counts, not independent accuracy estimates.

The original HTTP smoke request returned 200 and the expected report ID. Twenty-three focused tests pass. The [main report](../report/vision_report.pdf) and [separate prompt library](../report/vision_prompt_library.pdf) explain the work. The results CSV identifies controlled-study attempts separately from historical and interactive API calls.

## Files to read

| Requirement | File |
| --- | --- |
| Final experiment protocol and scoring | [protocol](../evaluation/vision/final_study/protocol.md) |
| Reviewed visual references for 12 photographs | [reference CSV](../evaluation/vision/final_study/reviewed_images.csv) |
| Eleven fixed conditions and authored text provenance | [cases](../evaluation/vision/final_study/cases.json), [control provenance](../evaluation/vision/final_study/provenance.json) |
| Prompt techniques, failures and corrections | [prompt library](../prompts/vision/prompt_library.md), [version index](../prompts/README.md) |
| Final measured comparison | [metrics](../evaluation/vision/final_study/metrics.json), [metric CSV](../evaluation/vision/final_study/metrics.csv) |
| Every actual attempt, including failures | [consolidated results](../evaluation/vision_results.csv), [raw run folder](../evaluation/vision/runs/) |
| POST /vision implementation | [api.py](../agents/vision/api.py), [original smoke](../evaluation/vision/final_study/api_smoke.json), [v11 HTTP regression](../evaluation/vision/claim_gate/api_smoke.json) |
| Vague-caption correction and failed revisions | [v11 entry](../prompts/vision/v11.md), [metrics](../evaluation/vision/claim_gate/metrics.json), [per-case review](../evaluation/vision/claim_gate/review.csv) |

The engineering report describes the implementation, prompt history and final controlled study. The separate prompt library retains v1-v11 instructions, techniques, comments, measured failures and the severity addendum. The final study compares v2/v3 under that common instruction; historical results are not mixed into its scores. Reference labels are visual judgments by the assistant, not independently verified field annotations.

## Caption correction

V2/v6/v7/v8/v9/v10/v11 matched 3/6, 3/6, 5/6, 4/6, 5/6, 3/6 and 6/6 comparison references respectively. V11 also retained all six category/severity targets and explained both vague requests. The correction studies contain 42 unique pipeline attempts and 60 actual model calls; reused v6 controls are not new inference. [Decision](../evaluation/vision/claim_gate/decision.json), [review](../evaluation/vision/claim_gate/review.csv).

V11 first extracts whether text makes a claim, its condition and negation. Only a concrete claim reaches a visual check of that condition against the original photo. `3awnouna` therefore receives null plus a help-request explanation. The known caption occurs in the examples: this is a development regression correction, not independent language accuracy. On the contradiction case the extractor retained the clear-ground wording rather than normalizing it fully; visual ABSENT still produced the correct false result. Compound negation is not generally validated. The initial visual description still underdescribes branches and may contain irrelevant uncertainty.

## Run the endpoint

Ollama must be running with the already installed `qwen2.5vl:3b` model. From the project directory:

```powershell
python -m pip install -r requirements-vision.txt
python -m uvicorn agents.vision.api:app --host 127.0.0.1 --port 8010
```

In another PowerShell window:

```powershell
curl.exe -X POST "http://127.0.0.1:8010/vision" -F "report_id=VISION-DEMO-01" -F "image=@841248136_1425441186447691_2938885808955356198_n.jpg"
```

The response echoes `report_id`, adds `run_id` and returns category, severity, description, evidence, text/image consistency, confidence and uncertainty. `description` is an optional form field; only send an actual description during normal use. With no text, consistency must be null. The API uses v11: unchanged v2 + `severity_v1` for image-only analysis, then claim extraction and, for a concrete claim, visual verification. It makes one, two or three calls depending on the caption. Each uses context 8192, temperature 0, seed 42 and a 512-token limit. This is the explicit prototype configuration, not a claim that it solves every case.

JPEG and PNG contents are decoded and checked; the limits are 10 MiB and 20 million pixels. Report IDs are not used as file paths. Images are stored locally by SHA-256 in `evaluation/vision/uploads/`. This local teaching prototype runs one inference request at a time. It returns 422 for invalid inputs, 413 for the byte limit, 415 for an unsupported image format, 503 when busy and 502 for a failed model output. A failed inference has a saved run ID; it is not replaced by a guessed answer.

FastAPI accepts the image and fields as multipart form data: [official documentation](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/). Its generated API documentation is at `http://127.0.0.1:8010/docs` while the server is running. Port 8010 was verified locally; Windows refused binding port 8000 in this session.

## Run or inspect the experiments

```powershell
python -B -m agents.vision.experiment
python -B -m agents.vision.experiment --summarize
python -B scripts/verify_vision_study.py
python -B scripts/export_vision_results.py
```

The separate v2/v6 text-comparison study uses:

```powershell
python -B -m agents.vision.text_comparison
python -B -m agents.vision.text_comparison --summarize
python -B -m agents.vision.text_comparison --few-shot --summarize
python -B -m agents.vision.text_comparison --text-examples --summarize
python -B -m agents.vision.text_comparison --chain --summarize
python -B -m agents.vision.text_comparison --image-review --summarize
python -B -m agents.vision.text_comparison --claim-gate --summarize
```

It records twelve attempts across six conditions with the same model, schema, severity rubric and parameters. Both versions use the same rule requiring an explanation for an inconclusive comparison with supplied text. No Python keyword rule decides semantic agreement. Its saved cases and original triggering failure remain separate from the first 25-call study.

The first study's original runner and schema are archived under `evaluation/vision/final_study/source/`. Correction studies likewise retain source snapshots when code changes. Verification checks recorded source/input hashes and reconstructs original and intermediate requests using the current code. New prompt support therefore does not require rewriting old evidence.

The first command resumes only missing scheduled attempts. Once all 25 are recorded, running it again does not repeat inference. Failures are recorded attempts and are not silently retried. The summary/export commands make no model calls. Frozen hashes prevent changing cases or prompts during the study. The controls are already archived; `scripts/prepare_vision_cases.py` records how they were prepared and is not required to rerun inference.

For a single photo using the endpoint's prompt and settings:

```powershell
python -B -m agents.vision.run --image-id IMG-01 --prompt-version v11 --severity-rubric --context-size 8192 --timeout 600
```

The older CLI default remains v1 to preserve the documented baseline. `--severity-rubric` is explicit and supported with v1-v3 and v6-v11. V4/v5 remain historical experiments with different severity policies.

## Verify the interface and scoring

```powershell
python -B -m unittest discover -s tests -p "test_vision*.py" -v
```

Unit tests use real files and replay recorded responses only to test HTTP transport and scoring. They are not counted as experiments. With the server running, `python -B scripts/smoke_vision_api.py` sends one actual HTTP multipart request to port 8010 and makes a real Ollama call. It is a separate integration check and is excluded from scores. Run it after the study to avoid concurrent inference affecting timings.

New smoke-response summaries are saved with unique timestamps under `evaluation/vision/api_smoke/`; the original study summaries are preserved.

## Limits of the evidence

One screenshot tests unrelated-image rejection; one deliberately severe blur tests inability to see detail; two authored descriptions test agreement/contradiction on a single waste scene. There are no confirmed WATER_LEAK or STREET_LIGHTING positives, no HIGH reference severity, no independent annotator and no held-out dataset. Report the measured small-case counts with those limits. The prototype dataset requirement does not establish reliable real-world performance.
