# RAG engineering record

## Corpus and purpose

The prototype covers Tunis municipal questions plus relevant national services.
The source ledger contains 12 entries. After review, nine summaries are enabled:
**4,716 bytes, 721 whitespace-separated words**, in UTF-8 Markdown. These are manually
written source summaries, not full website captures or a comprehensive procedural database.
The other three original documents remain for traceability and are excluded by the ledger.

Enabled sources cover the Tunis citizen account, arrondissement directory, municipal
public-lighting maintenance, MEHAT road administration, STEG contacts, SONEDE contacts
and meter diagnosis, and a national waste-collection guide. Titles, direct URLs,
issuing bodies, sections and review dates are in `rag/sources.csv` and `rag/source_audit.json`.
Unknown publication dates are left empty.

These sources fit contact and service-orientation questions. Coverage is limited:
account registration is not a complete pothole-reporting procedure; a national waste
guide does not establish Tunis booking arrangements. The active sources provide no
guaranteed repair deadlines. A diagnostic interval is not a repair commitment.

The 2009 municipal waste regulation, an unrevalidated ONAS page and an unverified legal
reference are excluded. Their exclusion leaves sewage-procedure and legal-coverage gaps.
The prototype must refuse unsupported details rather than fill those gaps from memory.

## Retrieval design and choices

| Choice | Setting and reason | Limitation |
|---|---|---|
| RAG type | Single-stage dense retrieval followed by generation. A small multilingual corpus needs few components to inspect. | No evidence that dense retrieval outperforms lexical or hybrid search here. |
| Embeddings | Ollama `bge-m3`, 1,024-dimensional dense vectors, normalized; cosine search. The original project already selected multilingual BGE-M3. | No local embedding-model comparison; quantized Ollama embeddings are a new artifact, requiring fresh indexes and evaluation. |
| Vector store | Embedded Qdrant with payload metadata and category filtering. It retains the supplied implementation without another server. | One process opens a local store; stop the API before indexing or direct evaluation. |
| Structure chunks | Markdown headings; merge sections below 80 BGE tokens when the combined section fits; cap at 450 tokens. | Short final sections can remain below 80. Structure preference is provisional. |
| Fixed chunks | 512 BGE tokens, 50-token overlap, reset for each document. | Boundaries can cut a section; most short revised summaries may fit one window. |
| Structure overlap | 50 tokens only when a section exceeds the 450-token cap. | Normal section boundaries are not overlapped. None of the original 33 structure chunks required splitting. |
| Retrieval | Top 3; exact category filter, except `NONE`, which searches all categories. No reranker. | Category errors can exclude useful evidence. Three chunks can repeat the same document. |
| Score cutoff | Shared API/evaluation value 0.40. Filter before building both context and citations. | A working default, not a calibrated answerability probability; needs retesting with Ollama. |

The token caps keep a procedure together while limiting context size. The overlap retains
some boundary context in split sections. These are design choices, not experimentally
optimal values. A reranker is omitted because the corpus is small and there is no measured
benefit to justify another model.

## Retrieval evidence: original saved scores

The supplied CSV contains ten authored development queries for each strategy: nine
document references and one unrelated query, in French and Arabic/Derja. The original
indexes contain 33 structure chunks (73/148/346 token min/median/max) and 13 fixed chunks
(81/435/512). These counts describe the original corpus, not the corrected one.

`evaluation/retrieval/historical_replay.json` recalculates the original scores:

| Strategy | Raw Hit@1 | Raw Hit@3 | Raw MRR | Hit@3 after 0.40 | Positive queries with no context |
|---|---:|---:|---:|---:|---:|
| Structure | 6/9 | 9/9 | 0.833 | 9/9 | 0/9 |
| Fixed | 8/9 | 9/9 | 0.926 | 8/9 | 1/9 |

Fixed ranks the expected document first more often. Structure retains more expected
documents at 0.40. Neither result proves better generated answers. For example, the
electrical-cable query ranks the ordinary-lighting document above STEG with structure;
STEG is second. The French meter-diagnosis query retrieves its expected document first.

The unrelated query scores 0.4619 (structure) and 0.4315 (fixed): both pass 0.40.
This is a failure of score filtering, not proof that the final model answers incorrectly.
At the old evaluator's 0.50 cutoff, three structure and four fixed positive queries lose
all context. A single cutoff does not cleanly separate these development cases.

The corrected corpus and embedding provider changed. Its new chunk counts and retrieval
scores are **not measured**: BGE-M3, its tokenizer and Qdrant dependencies could not be
downloaded here. The old vectors are isolated under `evaluation/history` and never opened
by the corrected service. Source, chunker, path and embedding-digest checks reject stale indexes.
The original query references remain unchanged so excluded documents remain visible coverage failures.

## Generation and prompt experiments

The available local `qwen2.5:3b` runs generation. This choice allows real tests without
using the archive's credentials; it is not a demonstrated quality win over the original
unverified Groq model. No training or fine-tuning was performed.

All 25 calls use temperature 0, seed 42, context 8,192, output cap 512 and JSON-object mode.
Temperature 0 reduces sampling variation; seed 42 is an arbitrary fixed control, not an
accuracy improvement. Context 8,192 is a ceiling for these short inputs; 512 permits a
brief structured answer. None of these values was optimized by a parameter sweep.
They do not guarantee deterministic results across different machines or model artifacts.

Five fixed-context development cases isolate prompting from retrieval. They test a
missing road deadline, a STEG contact, an unrelated procedure, Arabic meter diagnosis
and an instruction to invent contact/deadline details. Each version gets one call per
case, without retries. Later versions respond to observed development failures.

| Version | Recorded schema passes | Selected constraints passed | Main observation |
|---|---:|---:|---|
| v3 | 5/5 | 4/5 | Correct STEG contact; mixed Chinese text in Arabic answer; overrefuses injected question. Unsupported examples found by inspection. |
| v4 | 5/5 | 3/5 | Replaces unsupported examples; refuses a supported contact and answers Arabic question in English. |
| v5 | 5/5 | 4/5 | Restores contact; follows injected false phone number and deadline. |
| v6 | 2/5 | 1/5 | System/user separation alone fails; returns quoted `"null"`. |
| v7 | 4/5 | 3/5 | Source-backed examples restore French contact; refuses Arabic diagnosis; produces integer deadline 72 under injection. |

Constraints check schema, expected answerability, null deadline and required digits.
They miss language and factual defects; v5's 4/5 does not make it suitable for service.
After v6, validation was strengthened to reject quoted-null deadlines even with a positive
answer. Historical v6 metrics use its frozen earlier validator; its Arabic output would
also fail the current validator. These are diagnostic iterations, not a clean ranking
under an unchanged validator. There is no independent held-out evaluation.

V4 remains a conservative provisional service default. The later versions are not enabled
in the API. This choice removes v3's unsupported demonstrations without accepting the
later injection regressions; it does not resolve v4's refusals or language errors.
The prompt library provides exact techniques, before/after examples, raw-output paths and
manual critiques. JSON mode is paired with strict validation; lexical deadline checking
rejects a deadline absent from the selected context, but does not prove every claim correct.

## Remaining validation

Five offline contract tests pass for score replay, strict types, data separation, missing
indexes and context/citation consistency with a recorded fixture. They are not live quality
measurements. The corrected index, fresh retrieval evaluation, full HTTP tests and n8n
execution remain to be run after setup succeeds. The project cannot yet claim full RAG
compliance or an end-to-end validated automation from these checks alone.
