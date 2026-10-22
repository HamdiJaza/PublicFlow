# Severity instruction v1

**Executable text:** [severity_v1.txt](severity_v1.txt). **Role:** define the requested LOW/MEDIUM/HIGH/null field for the prototype.

**Technique:** explicit decision criteria with a guardrail against inferring hidden hazards. This is an instruction addendum, not a trained severity model or an official municipal priority policy. The user accepted the rubric on 17 October 2026.

**Earlier failure:** original v1/v2 runs returned MEDIUM without an agreed rubric; v4 requested null but returned LOW; v5 enforced null and therefore could not provide the required severity levels.

**Correction:** append the same criteria to v2 and v3 in the final study. Preserve their seven-field schema and every historical prompt file. The endpoint uses v2 with this addendum. Labels are visual reference judgments; HIGH has no positive test case.

**Evidence:** [frozen protocol](../../evaluation/vision/final_study/protocol.md), [references](../../evaluation/vision/final_study/reviewed_images.csv), [measured severity agreement](../../evaluation/vision/final_study/metrics.json).

**Observed outcome:** v2 matched 3/4 severity references with a correct category; v3 matched 0/4 and returned null on all four clear incident cases. V2 called the small bollard-area defect MEDIUM instead of LOW. The common instruction therefore provides a defined policy but does not guarantee compliance.

The final study evaluates the combined instructions. It does not isolate the causal effect of adding the rubric, because there is no paired rubric-on/rubric-off experiment. No success is inferred merely from adding the definitions.
