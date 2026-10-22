"""Compare recorded prompt revisions on fixed text/image development cases."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from statistics import median

import requests

from .compare_prompts import check_pair
from .run import ROOT, load_photo, load_prompt, run_case

FOLDER = ROOT / "evaluation/vision/text_comparison"
MODEL = "qwen2.5vl:3b"


def read_cases():
    """Load reference labels separately from the model's query inputs."""
    return json.loads((FOLDER / "cases.json").read_text(encoding="utf-8"))["cases"]


def read_runs(folder=FOLDER):
    """Keep failures in the append-only index instead of silently retrying them."""
    path = folder / "runs.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def freeze(cases, folder, versions):
    """Record immutable study inputs and refuse a changed configuration on resume."""
    names = ["evaluation/vision/text_comparison/cases.json", (folder / "protocol.md").relative_to(ROOT).as_posix(),
             "prompts/vision/v6.txt", "prompts/vision/severity_v1.txt",
             "agents/vision/run.py", "agents/vision/schema.py", "agents/vision/text_comparison.py"]
    files = {"v6": ["v2.txt"], "v7": ["v7.json"], "v8": ["v8.txt"],
             "v9": ["v2.txt", "v9_compare.txt"], "v10": ["v2.txt", "v10_compare.txt"],
             "v11": ["v2.txt", "v11_claim.txt", "v11_verify.txt"]}
    names.extend("prompts/vision/" + name for name in files[versions[-1]])
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    for case in cases:
        photo, _ = load_photo(case["image_id"])
        hashes[photo["file"]] = photo["sha256"]
        for version in versions:
            _, _, metadata = load_prompt(version, photo)
            if metadata:
                for demo in metadata["spec"]["demonstrations"]:
                    reference, _ = load_photo(demo["image_id"])
                    hashes[reference["file"]] = reference["sha256"]
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    response = requests.get(base + "/api/tags", timeout=15)
    response.raise_for_status()
    model = next(item for item in response.json()["models"] if item["name"] == MODEL)
    settings = {"input_hashes": hashes, "model": MODEL, "model_digest": model["digest"], "versions": list(versions),
                "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512},
                "timeout_seconds": 600, "schema": "VisionObservation; identical for both versions",
                "validation": "Both versions require a reason for inconclusive supplied-text comparisons.",
                "order": f"Reuse recorded v6 controls; one new {versions[1]} call per case." if versions[0] == "v6" else
                         "Alternate the first prompt by case; one attempt per condition."}
    path = folder / "settings.json"
    if path.exists() and json.loads(path.read_text()) != settings:
        raise ValueError("The frozen text comparison changed; do not overwrite its evidence.")
    if not path.exists():
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def run_study(folder=FOLDER, versions=("v2", "v6")):
    """Make the twelve real requests and preserve exact result paths immediately."""
    cases = read_cases()
    if len(read_runs(folder)) == 12:
        summarize(folder)
        return
    freeze(cases, folder, versions)
    done = {(row["case_id"], row["prompt_version"]) for row in read_runs(folder)}
    if versions[0] == "v6":
        controls = [row for row in read_runs() if row["prompt_version"] == "v6"]
        if len(controls) != 6:
            raise ValueError("Complete all six v6 controls before the contrastive study.")
        for row in controls:
            if (row["case_id"], "v6") not in done:
                reused = {**row, "reused_from": "evaluation/vision/text_comparison/runs.jsonl"}
                with (folder / "runs.jsonl").open("a", encoding="utf-8") as file:
                    file.write(json.dumps(reused) + "\n")
                done.add((row["case_id"], "v6"))
    for index, case in enumerate(cases):
        order = versions if index % 2 == 0 else tuple(reversed(versions))
        for version in order:
            if (case["case_id"], version) in done:
                continue
            print(f"{case['case_id']} {version}: {case['description']!r}", flush=True)
            args = argparse.Namespace(image_id=case["image_id"], model=MODEL, prompt_version=version,
                                      description=case["description"], structured=True, timeout=600,
                                      context_size=8192, severity_rubric=True)
            result, path = run_case(args)
            row = {"case_id": case["case_id"], "prompt_version": version,
                   "result_file": path.relative_to(ROOT).as_posix()}
            with (folder / "runs.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps(row) + "\n")
            observation = result.get("observation", {})
            print(f"  {result['status']} | match={observation.get('text_image_consistent')} | "
                  f"{result['elapsed_seconds']} s | {path.name}", flush=True)
    summarize(folder)


def summarize(folder=FOLDER):
    """Score complete saved outputs and verify matched conditions and frozen hashes."""
    cases = {case["case_id"]: case for case in read_cases()}
    settings = json.loads((folder / "settings.json").read_text())
    versions = settings.get("versions", ["v2", "v6"])
    for name, expected in settings["input_hashes"].items():
        archive = folder / "source" / (Path(name).name + ".txt")
        source = archive if name.endswith(".py") and archive.exists() else ROOT / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen text-comparison input changed: {name}")
    rows = [{**row, "result": json.loads((ROOT / row["result_file"]).read_text(encoding="utf-8"))}
            for row in read_runs(folder)]
    if len({(row["case_id"], row["prompt_version"]) for row in rows}) != len(rows):
        raise ValueError("A condition has more than one recorded attempt.")
    for case_id in cases:
        pair = [row["result"] for row in rows if row["case_id"] == case_id]
        if len(pair) == 2:
            check_pair(pair, versions)
    groups = []
    for version in versions:
        counts = {name: 0 for name in ("valid_output", "text_agreement", "category", "severity", "vague_with_reason")}
        times = []
        for row in rows:
            if row["prompt_version"] != version:
                continue
            result, case = row["result"], cases[row["case_id"]]
            if result.get("model_digest") != settings["model_digest"]:
                raise ValueError("The model digest changed within the comparison.")
            times.append(result["elapsed_seconds"])
            if result["status"] != "completed":
                continue
            observation = result["observation"]
            counts["valid_output"] += 1
            counts["text_agreement"] += observation["text_image_consistent"] is case["match"]
            category_ok = observation["category"] == case["category"]
            counts["category"] += category_ok
            counts["severity"] += category_ok and observation["severity"] == case["severity"]
            if case["reason_required"]:
                counts["vague_with_reason"] += (observation["text_image_consistent"] is None
                                                and bool((observation["uncertainty_reason"] or "").strip()))
        groups.append({"prompt_version": version, "counts": counts,
                       "denominators": {"valid_output": 6, "text_agreement": 6, "category": 6,
                                        "severity": 6, "vague_with_reason": 2},
                       "median_seconds": median(times) if times else None})
    output = {"complete": len(rows) == 12, "attempts": len(rows),
              "new_attempts": sum("reused_from" not in row for row in rows), "groups": groups,
              "new_model_calls": sum(1 + len(row["result"].get("stages", []))
                                     for row in rows if "reused_from" not in row),
              "promotion": "Requires the protocol's numerical gates and a separate visual review.",
              "limitation": "Six development conditions on two scenes; not independent accuracy estimates."}
    (folder / "metrics.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2), flush=True)


def main():
    """Run missing attempts or summarize without inference."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summarize", action="store_true")
    choice = parser.add_mutually_exclusive_group()
    parser.set_defaults(study="text_comparison")
    choice.add_argument("--few-shot", action="store_const", dest="study", const="text_few_shot", help="V6/v7 image examples.")
    choice.add_argument("--text-examples", action="store_const", dest="study", const="text_examples", help="V6/v8 text examples.")
    choice.add_argument("--chain", action="store_const", dest="study", const="text_chain", help="V6/v9 text-only chain.")
    choice.add_argument("--image-review", action="store_const", dest="study", const="image_review", help="V6/v10 image review.")
    choice.add_argument("--claim-gate", action="store_const", dest="study", const="claim_gate", help="V6/v11 claim extraction chain.")
    args = parser.parse_args()
    versions_by_study = {"text_comparison": ("v2", "v6"), "text_few_shot": ("v6", "v7"),
                         "text_examples": ("v6", "v8"), "text_chain": ("v6", "v9"),
                         "image_review": ("v6", "v10"), "claim_gate": ("v6", "v11")}
    folder = ROOT / "evaluation/vision" / args.study
    versions = versions_by_study[args.study]
    summarize(folder) if args.summarize else run_study(folder, versions)


if __name__ == "__main__":
    main()
