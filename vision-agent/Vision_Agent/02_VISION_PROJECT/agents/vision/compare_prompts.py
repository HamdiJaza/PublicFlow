"""Compare two Vision prompts on the same photos, recording every real call."""

import argparse
import csv
import json
from datetime import datetime, timezone

from .run import ROOT, load_photo, load_prompt, run_case


def check_pair(pair, versions):
    """Check fixed conditions, including identical instructions for v2 versus v3."""
    fields = ["image_sha256", "scene_group", "model_digest", "user_message",
              "description", "options", "format_constraint", "output_schema"]
    if set(versions) & {"v9", "v10", "v11"}:
        # V9 withholds text from the image pass, then uses a caption-only schema.
        # Caption inputs still match; this is explicitly a chain configuration.
        fields.remove("user_message")
    if "v5" in versions:
        # V5 enforces null scores and missing-text consistency. Its comparison is
        # of complete configurations, not an isolated change to prompt wording.
        fields.remove("output_schema")
        schemas = []
        for result in pair:
            schema = json.loads(json.dumps(result["output_schema"]))
            for field in ("title", "description"):
                schema.pop(field, None)
            policy_fields = ["severity", "confidence"]
            if pair[0]["description"] is None and pair[1]["description"] is None:
                policy_fields.append("text_image_consistent")
            for field in policy_fields:
                schema["properties"].pop(field)
            schemas.append(schema)
        if schemas[0] != schemas[1]:
            raise ValueError("Comparison output contracts differ beyond v5's documented null policy.")
    if set(versions) in ({"v2", "v3"}, {"v6", "v7"}):
        fields.append("prompt_sha256")
    for field in fields:
        if field not in pair[0] or field not in pair[1] or pair[0][field] != pair[1][field]:
            raise ValueError(f"Comparison conditions differ or are missing: {field}")


def main():
    """Validate scene separation before inference, then run each matched pair."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-ids", nargs="+", default=["IMG-01", "IMG-03", "IMG-04"])
    parser.add_argument("--versions", nargs=2, choices=["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11"], default=["v1", "v2"])
    parser.add_argument("--model", default="qwen2.5vl:3b")
    parser.add_argument("--context-size", type=int)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    has_image_examples = bool(set(args.versions) & {"v3", "v7"})
    context_size = args.context_size if args.context_size is not None else (8192 if has_image_examples else 4096)
    if (args.versions[0] == args.versions[1] or args.timeout <= 0 or context_size <= 0
            or (has_image_examples and context_size < 8192)):
        parser.error("Choose two different versions, a positive timeout and a sufficient context size.")
    if len(args.image_ids) != len(set(args.image_ids)):
        parser.error("Do not repeat an image ID within one comparison.")
    # Check the whole batch before inference to prevent example/query overlap.
    for image_id in args.image_ids:
        photo, _ = load_photo(image_id)
        for version in args.versions:
            load_prompt(version, photo)

    comparison_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    folder = ROOT / "evaluation/vision/comparisons" / comparison_id
    folder.mkdir(parents=True)
    settings = {
        "versions": args.versions, "image_ids": args.image_ids, "model": args.model,
        "context_size": context_size, "timeout": args.timeout,
        "order": "Alternate the first version between consecutive images.",
        "limitations": "Development scenes, not an independent test set. One call per condition. "
                       "Demonstrations and evaluation judgments require team review. Timings include loading and caching.",
        "v5_changes": "Two calls (visual observations then text classification), observations-first output "
                      "order and schema-enforced null scores/missing-text comparison; a configuration "
                      "comparison, not a prompt-only ablation."
                      if "v5" in args.versions else None,
    }
    (folder / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    rows = []
    for index, image_id in enumerate(args.image_ids):
        pair = []
        versions = args.versions if index % 2 == 0 else list(reversed(args.versions))
        for version in versions:
            options = argparse.Namespace(image_id=image_id, model=args.model, prompt_version=version,
                                         description=None, structured=True, timeout=args.timeout,
                                         context_size=context_size)
            print(f"Running {image_id} with {version}...", flush=True)
            result, result_file = run_case(options)
            pair.append(result)
            observation = result.get("observation", {})
            rows.append({
                "image_id": image_id, "prompt_version": version,
                "status": result["status"], "schema_valid": result["schema_valid"],
                "category": observation.get("category"),
                "evidence": json.dumps(observation.get("evidence"), ensure_ascii=False),
                "uncertainty_reason": observation.get("uncertainty_reason"),
                "elapsed_seconds": result["elapsed_seconds"],
                "prompt_eval_count": result.get("raw_response", {}).get("prompt_eval_count"),
                "error": result.get("error"),
                "result_file": result_file.relative_to(ROOT).as_posix(),
            })
            # Save after every call, including failed model responses.
            with (folder / "runs.csv").open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            print(f"{result['status']} | {result['elapsed_seconds']} s | {result_file.name}", flush=True)
        check_pair(pair, args.versions)
    print(f"Comparison conditions checked. Results: {folder}", flush=True)


if __name__ == "__main__":
    main()
