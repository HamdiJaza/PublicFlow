# Local Intake cleaning benchmark

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

This is a standalone local experiment. No Intake API, n8n workflow, Gemini
timeout, production service, Vision code, prompt or model configuration changed.
The delivered `pipeline.PROMPT` and `masquer_texte` are imported unchanged.
The benchmark sends synthetic text only to loopback Ollama; it cannot pull models
or select cloud endpoints. It uses the installed, digest-checked `qwen3:4b`.

## Actual result

Evidence: `project-docs/integration/intake-qwen3-4b-benchmark-01.json`.
Semantic assessment: `project-docs/integration/intake-qwen3-4b-review-01.json`.

- 13 actual local model calls, zero retries, zero Gemini calls; one additional
  empty-input case used a deterministic bypass and is not a model success.
- All 13 generations completed with valid three-field JSON. Seven met the
  predeclared language, quality, content and masking checks. This is a small
  regression suite, not a measured population accuracy estimate.
- First request: 9.095 seconds including approximately 6.946 seconds loading.
  Subsequent requests: 1.981–3.276 seconds, median 2.424 seconds. Total benchmark:
  39.143 seconds including setup and the final unload request.
- Ollama's post-first-response memory sample reported approximately 3.283 GiB
  loaded size and 2.184 GiB GPU allocation, indicating partial CPU/GPU placement.
  This is one sample, not peak process RAM or peak VRAM measurement.
- Normal French, English, standard Arabic and the single Tunisian dialect report
  preserved the incident text. The French spelling example was corrected.
- Mixed French/Arabic text was translated into French and incorrectly labelled
  VAGUE. The prompt explicitly forbids translation.
- The vague Arabic report was incorrectly marked CLEAR. A clear suspected leak
  with unknown exact location was marked VAGUE; that classification is a more
  conservative error. Missing location and incident intelligibility are separate.
- Fictional French and Arabic person names were left unmasked. `[TELEPHONE]`
  became `[TELE:PHONE]`. Profanity was retained. The deterministic pre-mask did
  remove the fixture email/phone before inference, but did not mask names.
- The prompt-injection fixture did not redirect the response out of its schema
  or remove the actual incident. Its malicious instruction remained in cleaned
  text. That is not proof of downstream prompt-injection protection.

**Decision: do not enable this configuration as an automatic Intake fallback.**
Valid JSON and CLEAR are insufficient to establish safe preparation. The present
Gate 1 does not independently detect the observed unmasked names or altered
placeholders; its existing checks must not be treated as evidence those passed.

The benchmark model was unloaded afterward. All original and agent source files
were hash-identical before and after execution. Original Vision package hashes
are checked separately. These observations do not prove complete anonymization.

## Reproduction

Use the existing project environment and installed Ollama. No additional package
or model installation is needed:

```powershell
intake-agent/.venv/Scripts/python.exe -B integration/intake-local/benchmark_cleaning.py --run
```

The script refuses to overwrite the existing result, accept a different model
digest, or begin while another model is loaded. Inspect the saved result first;
a deliberately new experiment should use a new result filename in a reviewed
benchmark copy. Do not delete evidence to force a repeat.

The configuration was `think:false`, temperature 0, context 4096, max output 2000
tokens, JSON schema constraint and 90-second per-case network deadline. Schema
enforcement is an experiment adapter setting; the system prompt text is exact.
The empty bypass is benchmark-only and does not imply a service change.

## Next correction to evaluate

Before implementation, compare the same fixtures with another installed text
model using the exact same prompt (the installed `qwen2.5:latest` is a 7.6B
candidate, with higher memory requirements). Do not call it better until tested.
If the original prompt remains insufficient, a separately versioned local prompt
or a verified local name-redaction stage needs explicit design review; preserve
the delivered and Gemini prompts.

A future fallback adapter should enforce placeholder preservation, reject
malformed/incomplete responses, record real provider provenance, retain privacy
failure REVIEW and never convert unknown quality into CLEAR. Name masking and
mixed-language fidelity need their own evidence; fixture-name lists are not
production privacy detection. Audio transcription is outside this experiment.

The proposed 150-second Gemini deadline and bounded Gemini-to-local fallback have
not been installed. No paid request was made to validate either.
