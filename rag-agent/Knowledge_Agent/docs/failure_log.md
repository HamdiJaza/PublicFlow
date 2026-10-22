# Observed failures and corrections

| Evidence | Failure | Correction | Verification and remaining limit |
|---|---|---|---|
| Original config/code/evaluator | API environment used 0.40; evaluator used 0.50 and skipped filtering positive hits. | One Settings value and shared selection function; separate raw and retained metrics. | Historical replay and contract test; no new embedding scores. |
| Original context assembly | Generator saw all candidates; citations contained only candidates above cutoff. | Filter once, use that exact set for context and returned source candidates. | Recorded-output unit fixture confirms excluded text is not sent; citations do not prove every generated claim. |
| Original parser | `bool("false")` evaluates true; no strict output contract. | Strict Pydantic types and refusal consistency; reject quoted-null/empty deadlines. | Contract test rejects string booleans, inconsistent refusals and quoted null. |
| Source review | Broad homepages, unsupported booking/dispatch details, unresolved legal/currentness claims. | Direct references and narrower summaries; exclude three unresolved entries. | Ledger has nine active entries; full procedural coverage is not achieved. |
| Original v3 inspection | Demonstrations introduce unsupported 72-hour repair and phone 1300 details. | Source-backed v4 examples; historical v3 kept unchanged. | This is an inspected prompt defect; the v3 study did not actually output those false values. |
| v4 P02/P04/P05 | Refuses supported STEG contact; English response to Arabic question; injected question overrefused. | v5 states contact answers need no full procedure and removes examples. | P02 contact recovers, but v5 copies false 1300 and 72-hour values in P05; P04 becomes French. |
| v5 P05 | Follows invented phone and deadline instruction. | v6 separates system instructions from question/source JSON. | v6 still overrefuses and emits quoted null; role separation alone is insufficient. |
| v6 raw outputs | Deadline is `"null"`, including in an otherwise useful Arabic answer. | Explicit JSON-null examples in v7 and stronger validator. | v7 restores P02 contact, refuses P04, and emits integer 72 in P05, rejected by schema. |
| Original claims | Claimed structure superiority, zero hallucinations and authentic ground truth without adequate evidence. | Recompute scores and qualify evidence; manual prompt critique accompanies numeric checks. | Fixed has stronger raw first-rank scores; no generated-answer winner or zero-error guarantee established. |
| Changed embedding backend | Old SentenceTransformers vectors could be queried with a different Ollama artifact. | Separate fresh index location; corpus, chunker, path and embedding-digest manifest checks. | Missing-index guard tested; rebuild and live retrieval remain blocked. |
| Setup attempts | CLI and local Ollama pull API failed through a refused registry proxy; HF/PyPI downloads also failed. | Setup now requests Ollama weights plus tokenizer only; no silent model substitution. | Model is still absent. Fresh retrieval and full HTTP/n8n tests are pending. |

Prompt evidence: `evaluation/prompt_study` (v3/v4), `prompt_revision` (v5),
`prompt_roles` (v6), `prompt_examples` (v7). Each contains five actual attempts per
version, raw provider output, configuration and frozen implementation snapshots.
The current service retains v4 provisionally; experimental regressions are not deployed.
