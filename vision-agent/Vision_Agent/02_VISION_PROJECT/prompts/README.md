# Prompt library

The Vision component's executable prompts are linked below. Markdown files document them; the runner reads the linked `.txt` or `.json` files. Tested versions are immutable. A runtime or schema change is recorded separately from a prompt change.

| Entry | Role and techniques | Evidence |
| --- | --- | --- |
| [Vision v1](vision/v1.md) | Zero-shot classification, role, fixed labels, JSON, uncertainty rules. | Original baseline and v1/v2 comparison. |
| [Vision v2](vision/v2.md) | Adds direct evidence and cause/uncertainty guardrails. | Before/after review and final zero-shot condition. |
| [Vision v3](vision/v3.md) | Adds three real image/answer demonstrations to exact v2 instructions. | Before/after few-shot results and final paired comparison. |
| [Vision v4 and v5](vision/prompt_library.md) | Checklist revision; then observation/classification prompt chaining. | Failed revisions and runtime corrections retained. |
| [Severity addendum](vision/severity_v1.md) | Shared explicit decision criteria for LOW/MEDIUM/HIGH/null. | Final study; separate from historical prompt versions. |
| [Vision v6](vision/v6.md) | Zero-shot explicit claim/comparison criteria, grounding and uncertainty about text. | Recorded vague-caption failure and controlled v2/v6 comparison. |
| [Vision v7](vision/v7.md) | Contrastive multimodal examples with unchanged v6 instructions. | V6 failure and saved-control comparison on the same six cases. |
| [Vision v8](vision/v8.md) | Text-only contrasting targets and a gloss of the known caption. | Targeted regression check after v7's caption and example-copying failures. |
| [Vision v9](vision/v9.md) | Image-only analysis, then a separate text-comparison prompt. | Targeted chain experiment after the single-call revisions failed. |
| [Vision v10](vision/v10.md) | Gives the caption reviewer the original photo as well as notes. | Addresses v9's false contradiction caused by an omitted visual detail. |
| [Vision v11](vision/v11.md) | Extracts a positive condition and negation, then verifies presence in the photo. | Conditional chain after v9/v10 failed on different caption types. |

[Full library](vision/prompt_library.md) · [PDF](../report/vision_prompt_library.pdf) · [Consolidated results](../evaluation/vision_results.csv)

## Record format for another agent

For each prompt, record its ID/version, system role, exact executable text or file, input fields, output contract and techniques actually used. Explain which instruction implements each technique. State the observed failure with a run ID, the intended correction, and the measured before/after outcome, including regressions. Separate an intended effect from an observed improvement.

For each experiment, record image/document hashes, model/version, decoding settings, schema, reference-label origin, changed variable, exact response/error, elapsed time and review. Compare the same cases; keep failures in the denominator. Describe anything else that changed. Do not label a schema constraint as prompt engineering or claim few-shot prompting without actual demonstrations.

This index covers the Vision files present in this workspace. It does not claim to contain or validate teammates' missing deliverables.
