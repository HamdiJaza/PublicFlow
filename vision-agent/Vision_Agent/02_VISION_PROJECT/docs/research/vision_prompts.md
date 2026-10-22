# Vision agent design justifications

## Final study and delivery: 17 October 2026

The [delivery guide](../vision_delivery.md) documents the implemented `POST /vision` interface and commands. The [frozen final study](../../evaluation/vision/final_study/protocol.md) compares two installed models on three identical cases and v2/v3 on eleven fixed conditions. It adds the approved unrelated screenshot, a recorded blur transformation and two authored text conditions. These texts are explicitly evaluation inputs, not citizen reports.

All twelve original photos have [visual reference annotations](../../evaluation/vision/final_study/reviewed_images.csv). They were reviewed by the assistant; no independent validation is claimed. Duplicate scenes and v3 demonstration scenes are excluded from scored query counts. Uncertain cases measure conservative abstention rather than forced category accuracy.

The shared [severity instruction](../../prompts/vision/severity_v1.md) supplies the accepted LOW/MEDIUM/HIGH/null prototype rubric. Its exact text is appended equally to v2 and v3 without editing either historical prompt. The original endpoint used v2 plus this instruction. The current v11 configuration retains that image pass and adds conditional claim extraction/verification; see the delivery guide. The runtime schema is unchanged for this comparison. Historical v4/v5 retain their different null-score policies.

The following sections preserve the original design and experiment history. The final [metrics](../../evaluation/vision/final_study/metrics.json) and [consolidated run table](../../evaluation/vision_results.csv) are the current evaluation artifacts.

The Vision agent converts a citizen photo into a category, visible observations and uncertainty that the municipal workflow can inspect. Our current implementation is a working local experiment script. We chose Qwen2.5-VL with structured JSON as the starting configuration because it returned usable final responses in our tests. We have not established which model is most accurate across the incident categories.

These decisions address the justification requirements in the [exam brief](<../../Advanced DL-Exam.pdf>) and the Vision assignment on page 5 of [the team guide](<../../Municipal_AI_Team_Task_Guide.pdf>). Implementation links below show where each decision appears in the code.

## Role in the planned system

Vision needs AI because identifying waste, damaged paving or a streetlight problem requires interpreting the photograph. File checks, allowed category names and JSON validation are explicit rules, so Python handles them directly.

Vision accepts a photograph and optional citizen description, then returns observations that a municipal workflow can inspect. Keeping visual interpretation in this component lets us compare models and prompts on the same images.

The component provides a command-line runner and a `POST /vision` endpoint. Department routing and ticket submission belong to the surrounding workflow.

The runner reads an inventoried local photo, calls Ollama and saves the experiment record. See [run.py](../../agents/vision/run.py).

## Model and execution choices

We use an existing vision model because we currently have 12 photos with provisional annotations, not a verified training dataset. Training a task-specific classifier would require a separate data collection and training effort before we could compare its results. The pretrained model lets us start testing visual interpretation and prompts with the material we have.

Local Ollama uses the two available installed candidates. The requests in these experiments go to the local machine. This avoids sending the photos to a hosted model for these calls and incurs no hosted inference API charges. Hardware use, electricity and execution time remain costs; we have not measured them all.

| Candidate | Reason to try it | Actual observation | Current decision |
| --- | --- | --- | --- |
| `qwen3-vl:2b` | It was the smaller installed vision candidate. | Two calls with corrected report text returned empty final content, including one with schema enforcement. | Keep it as a comparison candidate and investigate the local runtime behavior before judging its visual quality. |
| `qwen2.5vl:3b` | It was another installed model advertising vision support. | It returned valid final JSON for IMG-01 with report text and later with the image alone. | Use it as the working baseline while collecting broader evaluation results. |

The corresponding records are the [Qwen3-VL structured call](../../evaluation/vision/runs/20261011T203326_249911Z_IMG-01.json), [Qwen2.5-VL call with text](../../evaluation/vision/runs/20261011T203523_215817Z_IMG-01.json), and [Qwen2.5-VL image-only call](../../evaluation/vision/runs/20261011T210914_729938Z_IMG-01.json). An earlier Qwen3-VL call produced valid JSON but used corrupted French text; that [record is retained](../../evaluation/vision/runs/20261011T202811_849636Z_IMG-01.json) and excluded from clean comparisons.

Both installed candidates report Q4_K_M quantization. We used the available versions without comparing quantization settings. The two successful Qwen2.5-VL runs took 70.358 and 62.129 seconds overall. These times include setup and model loading where applicable, use different inputs, and are not a speed benchmark. Our selection establishes a usable configuration on this machine, not superior accuracy or speed.

## Prompt and output choices

The [v1 prompt](../../prompts/vision/v1.txt) uses role prompting, an explicit category list, requested JSON fields and uncertainty instructions. It is a zero-shot baseline: we provide no labeled examples inside the prompt. This gives us a starting point before deciding whether examples improve observed errors.

| Choice | Reason | Limit |
| --- | --- | --- |
| Fixed categories from the team guide | Give the router predictable labels. | Including pavement and kerb damage within ROAD_DAMAGE is a team convention that still needs agreement. |
| Short description and visible evidence | Let a reviewer inspect what supports the classification. | The model can still mention irrelevant or unsupported observations. |
| `NONE` and a null category | Separate a clearly unrelated scene from an image that cannot be classified confidently. | Their reliability needs testing on real negative and ambiguous examples. |
| Null text/image consistency when text is absent | Avoid claiming agreement with a description that was never supplied. | Actual mismatch detection has not yet been evaluated. |
| JSON schema plus Pydantic validation | Give later workflow nodes typed fields and reject invalid outputs before they are used. | Valid structure does not establish that the image interpretation is correct. |

[schema.py](../../agents/vision/schema.py) rejects extra fields and invalid types. It also requires an uncertainty explanation when the category is null, and rejects severity when the category is null or NONE. The runner rejects empty and truncated final responses and does not silently turn them into classifications.

Severity currently uses the LOW, MEDIUM and HIGH labels requested by the team guide. There is no agreed rubric yet, so the emitted level must not determine municipal priority automatically. Likewise, confidence is a model estimate, not a calibrated probability or a justified threshold for a PASS decision.

The original prompt produced a concrete weakness: one response treated the presence of a bin as evidence of a waste problem; another included the absence of a leak or road damage. Those observations do not by themselves establish the reported issue. The [v2 prompt](../../prompts/vision/v2.txt) adds rules for direct observations, uncertainty explanations and unsupported causal claims. The separate [prompt library](../../prompts/vision/prompt_library.md) contains both full versions, techniques, observed failures and intended fixes. The [paired evaluation](vision_prompt_evaluation.md) records what those changes actually improved and what they did not. Schema enforcement and switching models were separate experiments, not prompt revisions.

## Inputs and evaluation data

The [CSV inventory](../../evaluation/vision/image_inventory.csv) is the single list of our 12 supplied photos. CSV is sufficient at this scale and can be reviewed in a spreadsheet. Stable image IDs make discussions easier; hashes detect accidental image replacement. Keeping a second JSON inventory added synchronization work without serving another reader, so it was removed.

Draft labels and review notes are not sent to the model. The current default uses the image alone because no original citizen descriptions were supplied. The optional `--description` argument accepts an actual description. Generated descriptions used in the first experiments were removed from active inputs; their origin remains disclosed in the historical records.

All photos are development data. IMG-04/05 and IMG-07/08 show the same respective scenes, so those pairs must stay together in a future split. Otherwise, seeing one view while designing the prompt could influence evaluation on the other. Twelve files therefore do not represent twelve independent scenes.

The photos' precise locations are unverified. Water on a road does not establish a pipe leak, and visible wiring does not establish a faulty public streetlight. Those cases remain uncertain until the evidence or original description supports a label.

## Code and runtime choices

The runner separates argument parsing, image loading, prompt loading, message assembly, inference and run recording. The comparison script calls the same `run_case()` function and receives the exact result path, avoiding a directory scan that could confuse concurrent runs. Pillow checks images, requests handles HTTP and Pydantic checks output. Dependencies are recorded in [requirements-vision.txt](../../requirements-vision.txt).

The current settings are starting values, not optimized parameters:

| Setting | Reason for the starting value | Evidence or remaining limitation |
| --- | --- | --- |
| Temperature 0 and seed 42 | Reduce sampling variation when comparing runs. | The seed is an arbitrary fixed value; it does not guarantee identical results across runtime or model changes. |
| Context 4096 | Allow room for the image, instructions and a short result. | It worked in the successful examples; longer inputs have not been assessed. |
| Output limit 512 | Bound generation for the short JSON response. | A Qwen3-VL run exhausted this budget. It is not an adequate limit for every configuration. |
| Request timeout 240 seconds | Bound waiting while allowing the observed local calls to finish. | This is an engineering allowance, not a measured service target. |
| Keep model loaded for 2 minutes | Allow nearby experiments to reuse the loaded model. | We have not measured the memory and loading tradeoff. |

The script records the prompt text and hash, model identity, image hash, settings, response and timing. Failed runs remain available because the teacher requires documented failures and corrections. There are no automatic retries. V1-v4 make one inference request; v5 makes an observation request followed by classification if observation succeeds, preserving both responses.

## Evidence still required for the defence

The [experiment log](../../prompts/vision/experiment_log.csv) supports the decisions above. Together with the paired prompt evaluation, it documents specific observed prompt effects. It does not establish general category accuracy, reliable rejection or mismatch detection.

Next, we need agreed reference labels and a severity rubric, then a comparison of both models on the same real cases, descriptions, prompt and runtime settings. We should record category accuracy on confirmed labels, valid output rate, treatment of ambiguous and unrelated images, mismatch results and execution time. Cold model loading should be reported separately when comparing speed.

The v1/v2 comparison now provides an initial before/after experiment on three development photos; its remaining failures still need work. Real positive lighting and leak examples, unrelated images, genuine descriptions and a separate final test set are still needed. The endpoint and n8n connection are also required before this script can serve as the team's integrated Vision Agent.

## Few-shot extension - 17 October 2026

V3 adds three real image/answer demonstrations to the unchanged v2 system instructions. Its JSON specification records techniques, per-example comments, image hashes and provisional annotation status. Comments are not sent to the model. Query-scene exclusion prevents using an example as its own evaluation input.

The matched v2/v3 experiment uses context 8192 for both versions; single v1/v2 calls retain the 4096 default. V3 defaults to a 600-second timeout and rejects a context smaller than 8192. These settings reserve capacity for the examples, not a claimed optimization. Generation still uses temperature 0, seed 42 and at most 512 output tokens.

The six-call comparison found an unsupported waste claim on the wet-road photo and copied uncertainty text. V3 is therefore an experimental version, not a selected replacement. The [prompt library](../../prompts/vision/prompt_library.md) and [evaluation](vision_prompt_evaluation.md#few-shot-comparison-17-october-2026) record the complete inputs and results. Demonstration labels and evaluation judgments still require team review.


## V4 checklist - 17 October 2026

V4 uses one query image with role prompting, zero-shot instructions, the existing JSON schema, a visual checklist, explicit category criteria, abstention and a final consistency-check instruction. It has no demonstrations, training, extra model call or reasoning transcript. This tests a complete revision, not the isolated effect of each technique.

The checklist covers waste, road, water, electrical/lighting equipment and uncertainty. Visible water must be described even when a leak cannot be established. Electrical/utility observations do not imply a streetlight fault; the team's enum has no general ELECTRICAL label. The prompt requests null severity and confidence because neither has been validated. That request is reviewed separately from schema validity: the shared schema still permits non-null values.

Single v4 calls default to context 4096; the matched v2/v4 comparison uses 8192 for both to match the recent experiment's context. Temperature 0, seed 42 and 512 output tokens remain fixed. None of these values has been optimized in a parameter sweep.

The [pre-run protocol](../../evaluation/vision/v4_protocol.md) defines six development cases and review criteria. Confirmed positive leak and lighting-fault detection cannot be assessed from this collection. The [prompt library](../../prompts/vision/prompt_library.md#v4-one-image-checklist-and-decision-criteria) contains exact instructions and design comments; measured outcomes belong in the [evaluation record](vision_prompt_evaluation.md).


## V5 observation/classification chain - 17 October 2026

V4 still omitted water and misread utility scenes. V5 therefore makes observation a separate call: a photograph produces structured scene/waste/road/water/equipment fields, then a text-only call classifies those observations. This is prompt chaining; both stages remain zero-shot. The classifier cannot see omitted image details and may discard or contradict the observer's claims. The intermediate result is retained to inspect both failure locations.

The first v5 trial rejected four of six final outputs for comparing absent citizen text. The corrected runtime restricts that field to null when text is absent and requests description/evidence before category in the final schema. Severity and confidence are also restricted to null. These deterministic interface constraints are not evidence of factual correctness. Both prompt files stay unchanged, and records distinguish the configuration changes.

The [v5 protocol](../../evaluation/vision/v5_protocol.md) and [evaluation](vision_prompt_evaluation.md) separate both trials and record their limitations. V5 uses two calls with the same local model, so it is not a controlled test of prompt wording alone. No chain-of-thought transcript, majority vote, external knowledge or fine-tuning is used.
