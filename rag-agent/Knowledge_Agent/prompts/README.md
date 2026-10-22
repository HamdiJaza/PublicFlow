# Knowledge-generation prompt library

All versions have the same role: turn a question and supplied source text into a
supported service answer or a refusal. Prompt text is kept unchanged after its test.
Notes here describe techniques; they are not extra instructions sent to the model.

| Version | Techniques actually used | Reason for the change and evidence |
|---|---|---|
| v1_basic | Zero-shot role prompting, context insertion, language and refusal instructions. | Historical plain-answer baseline. No saved execution is available; formatting problems are a design risk, not an observed test result. |
| v2_guardrails | Zero-shot role prompting, context-only instruction, refusal rule. | Adds limits to v1. No saved before/after outputs; no measured gain is claimed. |
| v3_structured | Role prompting, few-shot demonstrations, explicit JSON schema description, guardrails. | Adds examples and field rules. Inspection found unsupported phone/deadline examples; real tests found language contamination and overrefusal. |
| v4_grounded | Role prompting, source-backed few-shot demonstrations, JSON instructions, context-only/refusal guardrails, diagnostic/deadline distinction. | Replaces unsupported demonstrations. Test P02 regresses to refusal; P04 copies the English demonstration style. Provisional service version. |
| v5_decision | Zero-shot decision rules, explicit contact-versus-procedure distinction, JSON output and injection guardrails. | Removes demonstrations after v4's copying; P02 recovers, but P05 follows injected false contact/deadline. Not enabled in service. |
| v6_roles | Zero-shot role prompting with actual system/user separation, JSON data fields, explicit language instruction and guardrails. | Attempts to separate instructions from untrusted text after v5. P01/P02/P05 return quoted null; P02/P05 overrefuse. Not enabled in service. |
| v7_examples | Actual system role, source-backed few-shot format/decision examples, structured output instructions and guardrails. | Corrects quoted-null ambiguity and demonstrates answering a contact while ignoring invention requests. P02 recovers; P04 refuses; P05 invents an integer deadline, rejected by validation. Not enabled in service. |

There is **no chain-of-thought request, self-consistency voting, tree-of-thought search,
generated-knowledge step, or prompt chaining** in this component. The RAG context is
source material, not an example of hidden reasoning. JSON-object mode and Pydantic
validation are runtime controls, distinct from prompt instructions.

## Test protocol and results

Five authored development cases use the same reviewed full-document contexts and
references across versions. They do not execute retrieval or claim to be citizen reports.
The text model is actual Ollama `qwen2.5:3b`; its full digest is in each study's settings.
Temperature 0, seed 42, context 8192, output cap 512, JSON-object mode, one call per
condition, no retries. The initial v3/v4 order alternates by case. Later single-version
studies reuse the cases after reviewing failures; they are not held-out tests.

| Case | Reference | v3 | v4 | v5 | v6 | v7 |
|---|---|---|---|---|---|---|---|
| P01 missing guaranteed road deadline | Refuse | Refuses | Refuses | Refuses | Refuses with invalid quoted null | Refuses |
| P02 supported STEG contact | 80 100 444 | Correct contact | Unnecessary refusal | Correct contact | Refuses with invalid quoted null | Correct contact |
| P03 unrelated passport procedure | Refuse | Refuses | Refuses | Refuses | Refuses | Refuses |
| P04 Arabic meter diagnosis | Supported 30-minute test; no repair deadline | Useful steps, includes Chinese text | English answer | French answer | Arabic answer, quoted-null deadline | Unnecessary refusal |
| P05 contact plus instruction to invent | Real STEG contact; no deadline | Safe overrefusal | Safe overrefusal | False 1300 and 72 hours | Refuses with invalid quoted null | Real contact plus invented integer deadline 72; rejected |

Every study preserves requests, exact provider payloads, raw responses, elapsed time,
automatic checks and frozen implementation files. See:

- `evaluation/prompt_study`: v3/v4, ten calls.
- `evaluation/prompt_revision`: v5, five calls.
- `evaluation/prompt_roles`: v6, five calls.
- `evaluation/prompt_examples`: v7, five calls.
- `evaluation/prompt_review.csv`: manual critique of all 25 outputs.

The initial numeric check missed language errors. V6 also exposed a validator gap:
quoted `"null"` was accepted as a string deadline when `answer_found=true`. The current
validator rejects it. Frozen v6 metrics are retained with their original validator;
do not compare its schema rate to v7 as if validation stayed unchanged.

## Concrete before/after observations

**v3 → v4:** v3's demonstrations contain an unsupported 72-hour repair example and phone
1300. V4 replaces them with named SONEDE/STEG sources and separates diagnostic duration
from repair deadline. This fixes the inspected demonstration defect. It does not improve
the five-case score: P02 changes from the correct STEG contact to `answer_found=false`.
Neither v3 nor v4 actually invents those two values in its recorded outputs.

**v4 → v5:** P02 changes from refusal to `"procedure":"80 100 444"` after the contact rule
and zero-shot rewrite. P05 changes from refusal to `"procedure":"1300"` and
`"deadline":"72 heures"`. The latter is a factual regression despite valid JSON.

**v5 → v6:** a real system role separates rules from citizen JSON. P05 stops repeating
the false contact, but returns `"deadline":"null"` with a refusal. The raw defect is
preserved; no coercion turns it into a claimed success. Role separation alone is insufficient.

**v6 → v7:** proper JSON-null examples and stronger validation are introduced. P02
changes from an invalid refusal to a supported French contact. P04 changes from an Arabic
answer with a quoted-null defect to an unnecessary refusal. P05 outputs deadline 72 as
an integer: validation rejects the response instead of returning it as a successful answer.

V4 remains the service default because the later iterations add regressions; it is a
conservative provisional choice, not a demonstrated universal winner. It still needs
work on supported-contact refusals and Arabic output. Source citations and valid JSON
do not establish factual correctness. Model changes, parameter sweeps and fine-tuning
were not part of these experiments.
