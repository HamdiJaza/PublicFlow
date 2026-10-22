# Vision prompt comparison

## Later caption correction

The actual vague-caption API failure triggered the [v6-v11 records](../../prompts/README.md). On six fixed development conditions, comparison agreement was v2 3/6, v6 3/6, v7 5/6, v8 4/6, v9 5/6, v10 3/6 and v11 6/6. V11 explains both vague requests and retains all six category/severity targets. It is the endpoint configuration. [Metrics](../../evaluation/vision/claim_gate/metrics.json), [reviews](../../evaluation/vision/claim_gate/review.csv), [decision](../../evaluation/vision/claim_gate/decision.json).

V6's rules failed; v7 copied examples; v8 retained vague agreement; v9 treated omitted branches as contradiction; v10 accepted every supplied caption. V11 separates text-only claim extraction from verification of a positive condition against the original image. This changes schemas and call flow and is reported as a configuration study of chaining. These are two development scenes; the known caption occurs in revised examples. Correct flags do not establish complete visual grounding or reliable compound negation. All failed attempts remain in the consolidated CSV.

## Original controlled study: 17 October 2026

All 25 scheduled attempts finished. The [frozen protocol](../../evaluation/vision/final_study/protocol.md), [cases](../../evaluation/vision/final_study/cases.json), [run index](../../evaluation/vision/final_study/runs.jsonl), [metrics](../../evaluation/vision/final_study/metrics.json) and [per-attempt review](../../evaluation/vision/final_study/review.csv) record the inputs and outcomes. Every request hash was reconstructed successfully; frozen files stayed unchanged. The reference annotations are assistant visual judgments on development data.

| Measure | v2 zero-shot + severity rubric | v3 few-shot + same rubric |
| --- | --- | --- |
| Valid output | 11/11 | 11/11 |
| Category agreement on clear visual references | 5/5 | 4/5 |
| NONE rejection on the unrelated screenshot | 1/1 | 0/1 |
| Conservative null on unclear/blurred cases | 0/4 | 3/4 |
| Severity agreement with correct category | 3/4 | 0/4 |
| Matching/mismatching text | 1/2 | 0/2 |
| Category retained on both text conditions | 2/2 | 2/2 |

V3 improved conservative abstention on the frontage, utility and blur cases. Its generated evidence was still unreliable: it invented a facade, window and door in the blurred photo. On the unrelated screenshot it recognized the document but returned null instead of NONE. V2 returned NONE for both the unrelated and blurred inputs; only the former matches the declared policy. Neither version described water on the wet-road query.

V3 returned null severity on all four clear incident cases despite the shared rubric. Its unchanged demonstrations also use null severity. The observed behavior is consistent with example imitation, but this study does not isolate the influence of individual examples. V2 matched three severity references and returned MEDIUM for the local bollard-area defect labelled LOW.

V2 correctly marked the matching text as true, then also marked the directly contradictory text true. V3 returned null on both. Both kept WASTE as the image category. The text test therefore reveals a separate failure even when image classification agrees with its reference. The descriptions were explicitly authored controls, not genuine citizen reports.

The separate three-case model comparison used identical zero-shot instructions, images, query text, schema and decoding settings. Qwen2.5-VL produced 3/3 valid outputs and reference categories. Qwen3-VL returned empty final content on all three cases, so it scored 0/3 usable outputs; this does not measure its visual accuracy under another configuration. Both ran locally with zero hosted-API charges; hardware and electricity costs were not measured. Timing and load duration are recorded separately in the metrics. Empty failed responses must not be presented as fast successful answers.

After this original study, the endpoint retained v2 plus the rubric; the later correction below supersedes its caption handling. The study does not establish a universally best prompt: v2 performs better on the clear-reference, severity and text measures, while v3 abstains more often on the selected ambiguous cases. All earlier v4/v5 configuration experiments below remain part of the failure history. No prompt changed during this frozen study. Later correction studies are separate.

This document preserves the successive Vision development experiments. All use previously inspected images and provisional visual judgments.

## Purpose of the original v1/v2 experiment

Compare the unchanged v1 prompt with v2 on three supplied photos. The target is the evidence field: earlier v1 responses included the mere presence of a bin and the absence of other incident types. Those are insufficient support for a waste classification. A further rule in v2 addresses the unconfirmed origin of water visible in the dataset; this concern comes from reviewing the photos, not from a previously measured model error.

## Fixed conditions

Use `qwen2.5vl:3b`, the same installed model digest, JSON schema enforcement, temperature 0, seed 42, context 4096 and output limit 512. Supply no citizen descriptions and do not send provisional labels or review notes to the model. Run both versions once per photo, retaining every result. Only the system prompt changes within each pair.

Run:

```powershell
python -B -m agents.vision.compare_prompts
```

The script records results in `evaluation/vision/comparisons/` and checks paired input hashes, user messages, model digests, schema and settings. In the original experiment v1 ran first; the updated runner alternates order. Timings include loading and are not evidence of a prompt speed improvement.

## Cases selected before running

| Photo | Visible content from the inventory | Purpose |
| --- | --- | --- |
| IMG-01 | Branches and scattered rubbish beside a container. | Revisit the image that produced irrelevant supporting evidence. |
| IMG-03 | Broken and uneven road surface. | Check whether evidence remains useful for another incident type. |
| IMG-04 | Water or wet ground across a road; its source is not visible. | Inspect uncertainty and unsupported leak attribution. |

All cases are development examples. The labels are provisional. No general classification accuracy will be calculated from these three cases.

## Review rules decided before running

1. Record whether the final JSON passes the existing schema and input checks.
2. Inspect each evidence item against the photo. It must describe a visible observation relevant to the incident or the reported uncertainty, not only background objects or the absence of other categories.
3. Mark a claimed cause or source as unsupported when it cannot be established from the photo. For IMG-04, a wet road alone does not establish a pipe leak.
4. Check that an uncertainty reason states a real limitation rather than repeating certainty. A null value is acceptable when no specific limitation is identified.
5. Keep regressions and unsuccessful calls in the comparison. This is an assistant review of three photos, not an independently labeled test benchmark.

## Actual results: 2026-10-11

Comparison `20261011T213841Z` completed all six calls. The [run index](../../evaluation/vision/comparisons/20261011T213841Z/runs.csv) links to every raw result. The [review CSV](../../evaluation/vision/comparisons/20261011T213841Z/review.csv) records the assistant's judgments separately from the model outputs. The script's paired-configuration checks passed. All calls used model digest `fb90415cde1ef08aa669ae74b082d49b158729b6db1ab183c941417d507e71a1`.

| Photo | v1 result | v2 result | Review |
| --- | --- | --- | --- |
| IMG-01 | WASTE; valid JSON; 138.181 s. | WASTE; valid JSON; 112.037 s. | V2 removed the irrelevant negative evidence item. Its uncertainty explanation still discusses unrelated categories. |
| IMG-03 | ROAD_DAMAGE; valid JSON; 103.865 s. | ROAD_DAMAGE; valid JSON; 107.008 s. | Both give relevant observations of broken road surface. No category or evidence regression was observed on this case. |
| IMG-04 | ROAD_DAMAGE; valid JSON; 101.341 s. | ROAD_DAMAGE; valid JSON; 105.291 s. | Neither describes the visible water. The main issue and some claimed damage remain uncertain; both require review. |

All six responses had `text_image_consistent: null`, as required when no citizen description is supplied. Both versions returned MEDIUM severity on every photo. The three v1 confidence values were null; the three v2 values were 0.8. Neither severity nor confidence is validated, and a larger confidence value is not evidence of better performance.

### IMG-01: a partial fix

The [paired v1 response](../../evaluation/vision/runs/20261011T213842_982752Z_IMG-01.json) included:

> No visible signs of water leak or road damage

This does not directly support WASTE. In the [paired v2 response](../../evaluation/vision/runs/20261011T214102_399836Z_IMG-01.json), all three evidence items describe the waste or its position:

> A large pile of discarded materials and trash is present on the street.
>
> Plastic bags and other debris are scattered around the pile.
>
> The pile is located near a building and a dumpster.

The final item locates the waste pile; it does not use the dumpster's presence alone as proof. This is an observed improvement in the targeted evidence field on this photo.

However, v2's uncertainty reason was:

> The image does not provide clear evidence of a water leak or road damage.

That is still irrelevant to uncertainty about the waste classification. V1's paired uncertainty reason was mixed: inability to determine the exact waste content is plausible, but its reference to street lighting is unrelated. The intended uncertainty fix is therefore not demonstrated on this case. The prompt has partly shifted the unwanted discussion into another field rather than eliminating it.

### IMG-03: useful behavior retained

The [v1 response](../../evaluation/vision/runs/20261011T214255_343647Z_IMG-03.json) and [v2 response](../../evaluation/vision/runs/20261011T214440_289931Z_IMG-03.json) both identify cracks, missing sections and uneven road surface. These observations are supported by the photo. V1 mentions missing text for comparison, which is a real input limitation but does not assess the visible damage. V2 discusses uncertainty about extent, severity and traffic context. Neither response measures damage depth or establishes a justified municipal priority.

### IMG-04: unresolved visual interpretation

The [v1 response](../../evaluation/vision/runs/20261011T214628_267494Z_IMG-04.json) claims cracks and damaged pavement near the curb. The [v2 response](../../evaluation/vision/runs/20261011T214810_655927Z_IMG-04.json) claims cracks and damaged road patches. Both classify ROAD_DAMAGE, and neither mentions water visible across the street.

The wet surface makes some texture difficult to interpret, and there may also be surface or curb damage. Without an agreed annotation or the original citizen description, this is not a defensible binary classification score. We flag both evidence lists for review and record the omission of water. V1's uncertainty refers to an unspecified description despite the image-only input; v2 gives a generic limit about damage extent but does not address the wet surface.

Neither version claimed WATER_LEAK, so this pair does not show that v2 corrected a false leak attribution. It also does not demonstrate reliable treatment of the ambiguous scene. We must not report the preventive water rule as a measured success.

## Decision and remaining work

We now have a genuine before/after prompt iteration: an unchanged baseline, a revision linked to observed failures, a fixed comparison protocol, actual outputs and a documented partial improvement. The evidence-field defect improved on IMG-01, while IMG-03 retained useful observations. Uncertainty quality and interpretation of IMG-04 remain unresolved.

V1 remains the command's default baseline; v2 is available through `--prompt-version v2`. We have not established a generally superior prompt. Both versions stay unchanged so these runs remain reproducible in intent; even fixed settings do not guarantee identical output from future runtime executions.

The next revision should address irrelevant uncertainty explanations and missed visible water, then be compared on the same development cases plus additional real examples. Team review of the annotations, positive lighting/leak examples, unrelated photos, genuine text/image disagreement cases and a separate final test set are still required. These six calls establish neither general accuracy nor readiness for automatic municipal routing.

## Few-shot comparison: 17 October 2026

Comparison 20261017T104705_090963Z used v2 as the zero-shot baseline and v3 as a three-shot prompt. V3 kept the exact v2 system instructions and added IMG-02, IMG-06 and IMG-10 with assistant-reviewed target JSON. Demonstration scenes were excluded from evaluation. The targets remain pending team validation.

Both versions used Qwen2.5-VL 3B, temperature 0, seed 42, the same JSON schema, 512 output tokens and context 8192. The larger context accommodates four photographs and examples; the older 4096-context v2 calls are not the matched baseline. Order alternated: v2/v3 on IMG-01, v3/v2 on IMG-03, v2/v3 on IMG-04. No model weights were changed.

| Query | V2 category / elapsed time | V3 category / elapsed time | Provisional visual review |
| --- | --- | --- | --- |
| IMG-01 | WASTE / 64.219 s | WASTE / 100.182 s | V3 names vegetation but repeats the waste example's uncertainty. V2 already has relevant uncertainty in this fresh baseline. |
| IMG-03 | ROAD_DAMAGE / 40.277 s | ROAD_DAMAGE / 48.844 s | Both describe visible damage. V3 gives a relevant lack-of-scale limitation. |
| IMG-04 | ROAD_DAMAGE / 43.808 s | WASTE / 51.338 s | Both omit water. V3 invents a pile of plastic bags and other waste not visible in the image. |

All six calls returned valid JSON and null text/image consistency. V3 used 5034-5073 input tokens. Reconstructed complete requests matched all six stored request hashes, including the original image bytes and example order. The model digest matched the earlier Qwen2.5-VL study.

The primary new failure is an unsupported waste interpretation on IMG-04. V3 also repeats the waste demonstration's uncertainty sentence on IMG-01 and IMG-04. Example carryover is a hypothesis, not an established cause. All v3 severity/confidence values are null, matching the demonstration targets; all v2 values are MEDIUM/0.8. This does not establish better calibration.

V3 remains experimental and v1 remains the command's default. The experiment demonstrates neither an overall accuracy improvement nor a fix for omitted water. New scenes and independently reviewed annotations are needed. Separating demonstrations from the query more explicitly or testing prompt chaining would be future experiments, not completed corrections.

The [run table](../../evaluation/vision/comparisons/20261017T104705_090963Z/runs.csv), [settings](../../evaluation/vision/comparisons/20261017T104705_090963Z/settings.json) and [review CSV](../../evaluation/vision/comparisons/20261017T104705_090963Z/review.csv) preserve the evidence. The [prompt library](../../prompts/vision/prompt_library.md) contains the full examples, techniques and comments.


## V4 checklist comparison - 17 October 2026

Comparison [20261017T113125_125125Z](../../evaluation/vision/comparisons/20261017T113125_125125Z/runs.csv) completed twelve real calls, one v2/v4 pair on each of six scenes. Model digest, image bytes, query text, generation options and schema matched within pairs. All twelve responses passed the shared JSON schema and returned null text/image consistency.

| Scene | V2 | V4 | Review |
| --- | --- | --- | --- |
| IMG-01, waste | WASTE; general rubbish/bags. | WASTE; adds vegetation. | Clear category retained; uncertainty remains broad. |
| IMG-03, road | ROAD_DAMAGE; cracked surface. | ROAD_DAMAGE; mainly a horizontal crack. | Category retained; wider fragmentation is incompletely described. |
| IMG-04, water | ROAD_DAMAGE; water omitted. | WASTE; possible scattered litter; water omitted. | Failed correction. V4 also copies its uncertainty field instruction into the answer. |
| IMG-09, unclear intent | NONE. | WASTE; treats the colored wall as possibly discarded material. | V4 introduces an unsupported waste interpretation. |
| IMG-10, assembly/cables | WASTE; claims a debris pile. | WASTE; again claims a debris pile. | Both miss the main utility features; the claimed pile is not apparent. |
| IMG-11, red conduits/base | WASTE; suggests a possible leak. | WASTE; calls the conduit discarded and cites graffiti. | Utility function remains unestablished. V4 invents a text/description inconsistency in uncertainty. |

V4 returned LOW severity in all six calls despite requesting null; confidence was null in all six. Schema validity therefore did not imply prompt compliance. Its water-case uncertainty was exactly: "The specific missing information that limits this observation or category, or null when no such limitation is identified." This is copied instruction text, not a limitation observed in the photograph.

**Decision:** do not promote v4. It did not fix missed water or utility recognition and produced new unsupported interpretations. V4 and its raw outputs remain unchanged. The next experiment separates observation from classification and enforces known null fields through the schema. This is a measured failed attempt, not a claim that the checklist corrected every failure. [Review records](../../evaluation/vision/comparisons/20261017T113125_125125Z/review.csv) await team validation.


### Initial v5 trial: two accepted outputs out of six

[20261017T114001_882393Z_v5](../../evaluation/vision/comparisons/20261017T114001_882393Z_v5/runs.csv) made twelve model calls for six pipeline attempts. All observation stages returned structurally valid data. Four final responses compared absent citizen text and were rejected by validation; only IMG-09 and IMG-10 completed successfully. The raw failed responses remain available and are not presented as accepted predictions.

On IMG-04, observation recovered "Uncertain wetness on the road", but classification omitted it, selected WASTE and used irrelevant uncertainty. On IMG-10, the assembly/cables were described, but classification added "The electrical system is intact", which the photograph does not establish. IMG-09 and IMG-11 also received uncertain-wetness observations not established by visual review. Prompt chaining therefore exposed information loss and false observations; it did not eliminate them.

The runtime correction restricts missing-text consistency to null and requests description/evidence before category in the final schema. Both v5 prompt files stay unchanged. This must be reported as a configuration revision, not a new prompt or a successful visual correction by itself. [Initial review](../../evaluation/vision/comparisons/20261017T114001_882393Z_v5/review.csv) remains pending team validation.


### Corrected v5 runtime: valid output, unresolved interpretation

[20261017T114730_539711Z_v5_fixed](../../evaluation/vision/comparisons/20261017T114730_539711Z_v5_fixed/runs.csv) made twelve new model calls for six pipeline attempts. All six completed with validated JSON and null severity, confidence and missing-text consistency. The original v5 trial accepted only two of six final outputs. This is an interface correction from schema constraints, not a measured accuracy gain from prompting.

| Scene | Corrected v5 result | What changed and what remains wrong |
| --- | --- | --- |
| IMG-04, water | WASTE; description/evidence now include wetness. | Previously omitted water is retained. Main-category choice is still poorly supported, and uncertainty discusses unrelated electrical absence. |
| IMG-01, waste | NONE despite describing a waste pile. | Direct contradiction between category and observations. |
| IMG-03, road | ROAD_DAMAGE with cracks/patches. | Supported category retained; uncertainty still mentions unrelated absent incidents. |
| IMG-09, unclear intent | NONE; uncertain wetness. | Stops classifying the wall as waste; wetness is not established by photo review and the intended issue remains unknown. |
| IMG-10, assembly/cables | WASTE despite describing only equipment. | Utility details recovered but category contradicts its own evidence. |
| IMG-11, red conduits/base | WASTE; red pipe, uncertain wetness, no visible conduits. | Utility interpretation remains incomplete/contradictory. Wetness is not established by photo review. |

**Decision:** retain v4 and v5 as experimental versions; v1 remains the CLI baseline. V5 makes intermediate failures inspectable and the corrected configuration enforces known null fields. It does not establish an overall classification improvement or correct every failure. No technique combination has been shown to be best. The successful water mention is a limited result on one development scene, with unresolved category and uncertainty errors.

The [review CSV](../../evaluation/vision/comparisons/20261017T114730_539711Z_v5_fixed/review.csv) records provisional judgments. Both v5 prompt files are unchanged between trials; schema constraints/order changed. New independent scenes, team-reviewed labels and confirmed positive leak/lighting cases remain necessary. No prompt, runtime setting or JSON schema can be presented as a guarantee of visual correctness.
