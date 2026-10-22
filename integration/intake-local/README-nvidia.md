# NVIDIA Intake cleaning experiment

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

The real benchmark completed on 2026-10-18. It was a standalone text experiment;
NVIDIA had not yet been connected to Intake, n8n or Vision in that experiment. No original agent code,
Gemini prompt/model/timeout, production service or workflow was changed.

The subsequent integration now uses a separately versioned NVIDIA French
normalization prompt, as approved by the user. See
[the current Intake instructions](../../intake-agent/README-nvidia.md) and
`project-docs/integration/nvidia-intake-live-validation-01.json`. The failures below
remain evidence about the earlier, unchanged no-translation prompt experiment.

## Observed endpoint availability

The official catalog listed `nvidia/nemotron-3-super-120b-a12b` (replaced on 2026-10-22 by `nvidia/nemotron-3.5-lightning-30b-a3b`, because Nemotron 3 Super is not reachable from recent free NVIDIA accounts; same prompt and request format) with **Free Endpoint:
Available**. Its API returned the same model identifier for all 13 requests.
Sources checked on the experiment date:

- [Nemotron 3 Super catalog and hosted request example](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b)
- [Model card, including reasoning-off configuration](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
- [NVIDIA API catalog quickstart](https://docs.api.nvidia.com/nim/re/docs/api-quickstart)

The checked [Qwen3.5 397B](https://build.nvidia.com/qwen/qwen3.5-397b-a17b)
and [Qwen3-Next Instruct](https://build.nvidia.com/qwen/qwen3-next-80b-a3b-instruct)
catalog pages marked their free endpoints **Deprecated**. Neither was called.
Catalog listings can change; do not silently substitute a paid partner endpoint.

## Actual result

Captured outputs: `project-docs/integration/intake-nvidia-nemotron-benchmark-01.json`.
Comparison/assessment: `project-docs/integration/intake-nvidia-nemotron-review-01.json`.

- 13 actual NVIDIA requests; no retries, API errors, Gemini requests or model
  fallback. One additional empty-input case used a deterministic bypass.
- All 13 generations completed with valid native cleaning fields.
- 10 of 13 met the same predeclared checks; local Qwen3 4B met 7 of 13.
  This is a small fixture comparison, not general accuracy evidence.
- HTTP response times: median 1.365 seconds, range 0.913–3.041 seconds. Total
  controlled session: 21.03 seconds. These are single-run latency observations.
- Reported usage: 4,327 prompt tokens + 461 completion tokens = 4,788 total.
  No monetary cost was returned. Public free availability and user-confirmed
  account setup do not provide access to an actual billing ledger.
- Both synthetic personal names were masked. `[EMAIL]` and `[TELEPHONE]` were
  preserved; profanity was masked. These few fixtures do not prove general PII
  detection or establish a privacy guarantee.
- The vague Arabic report was correctly VAGUE. The injection fixture retained
  the incident and removed the malicious instruction; downstream injection
  resistance was not tested.
- The mixed French/Arabic case was translated into French, violating the
  original no-translation instruction, despite being labelled `mixed`.
- Arabic text containing a replaced name was labelled `mixed` instead of the
  expected `ar`. The suspected leak with unknown location was VAGUE instead of
  expected CLEAR. The latter is a conservative quality-label disagreement;
  uncertainty was retained, not invented or erased.

**Do not enable automatic fallback on the basis of JSON validity alone.** The
mixed-language translation needs a conservative preservation check before
integration, and the language/clarity expectations need documented treatment.
Current Gate 1 would not independently catch this translation. Do not weaken it
or change expected fixture results retroactively to manufacture a pass.

## Secure setup and run

From the repository root in VS Code PowerShell:

```powershell
./integration/intake-local/Configure_NVIDIA_Key.ps1
./integration/intake-local/Run_NVIDIA_Benchmark.ps1
```

Create the key in NVIDIA Build and enter it only at the hidden local prompt. Use
terminal right-click Paste; never paste it into chat, shell command arguments,
source files or tracked `.env` files. Storage is Windows DPAPI encrypted at
Git-ignored `.runtime/credentials/nvidia.dpapi`. The wrapper temporarily sets
`NVIDIA_API_KEY`, records explicit project provenance and restores the prior
process environment, including when execution fails. No system environment
variables are modified. `-Replace` is available only on the configuration script.

These exact run commands now refuse to repeat the completed experiment: both a
result file and an ignored single-use marker prevent accidental duplicate calls.
Prepare a separately labelled experiment if another run is deliberately needed;
preserve the existing evidence.

The runner pins the original fixture hash, native prompt, exact model and HTTPS
endpoint. Only synthetic text is sent, with fixture email/phone masking applied
before transmission. It does not upload media or inspect real reports. It caps
requests at 13, sets a 150-second HTTP timeout (not a global hard wall deadline),
uses zero transport retries and refuses redirects. Authentication, rate-limit,
server, timeout and malformed-output failures stop the experiment. Provider error
bodies and credential headers are never written to results. Response content is
also filtered for the exact credential and NVIDIA-key patterns before writing.

NVIDIA uses temperature 1/top_p 0.95 as recommended for this model, thinking off,
max output 2000 and JSON-object mode with strict client checks. Qwen used
temperature 0 and server JSON-schema constraints. Prompt and fixtures are equal;
serving configuration, weights and infrastructure are different. The plan inside
the captured report is the pre-execution plan snapshot, not the result status.

## Offline checks

```powershell
intake-agent/.venv/Scripts/python.exe -B -m unittest discover -s integration/intake-local -p test_nvidia_benchmark.py -v
./integration/intake-local/Test_NVIDIA_Credentials.ps1
```

Nine transport/budget/credential tests passed with fixtures. Windows DPAPI tests
passed for encryption, overwrite protection, malformed-input rejection and
environment restoration. All 318 original fingerprints and the delivered Vision
manifest remained unchanged after the live benchmark. Keys stay Git-ignored.

Audio transcription and image interpretation are outside this experiment. The
existing Vision implementation stays unchanged on Ollama.
