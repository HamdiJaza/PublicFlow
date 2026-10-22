"""Run the fixed final Vision study and score only its recorded attempts."""

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from statistics import median

import requests

from .compare_prompts import check_pair
from .run import ROOT, load_photo, load_prompt, run_case

FOLDER = ROOT / "evaluation/vision/final_study"
FIRST_MODEL = "qwen2.5vl:3b"
SECOND_MODEL = "qwen3-vl:2b"
MODEL_CASES = ("C01", "C02", "C08")


def read_cases():
    """Read the fixed references; only their description is sent to the model."""
    return json.loads((FOLDER / "cases.json").read_text(encoding="utf-8"))["cases"]


def schedule(cases):
    """Use two model blocks and alternate prompt order within the main block."""
    jobs = [(case, SECOND_MODEL, "v2") for case in cases if case["case_id"] in MODEL_CASES]
    for index, case in enumerate(cases):
        versions = ("v2", "v3") if index % 2 == 0 else ("v3", "v2")
        jobs.extend((case, FIRST_MODEL, version) for version in versions)
    return jobs


def read_runs():
    """Load the append-only run index, including unsuccessful attempts."""
    path = FOLDER / "runs.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def freeze_settings(cases):
    """Reject changed prompts, references or image bytes when resuming the study."""
    paths = ["evaluation/vision/final_study/cases.json", "evaluation/vision/final_study/protocol.md",
             "evaluation/vision/final_study/reviewed_images.csv", "evaluation/vision/final_study/provenance.json",
             "prompts/vision/v2.txt", "prompts/vision/v3.json", "prompts/vision/severity_v1.txt"]
    hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}
    for case in cases:
        photo, _ = load_photo(case["image_id"])
        load_prompt("v3", photo)  # Reject demonstration/query scene overlap before any call.
        hashes[photo["file"]] = photo["sha256"]
    spec = json.loads((ROOT / "prompts/vision/v3.json").read_text(encoding="utf-8"))
    for demo in spec["demonstrations"]:
        photo, _ = load_photo(demo["image_id"])
        hashes[photo["file"]] = photo["sha256"]
    frozen = {
        "input_hashes": hashes,
        "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512},
        "timeout_seconds": 600, "severity_addendum": "severity_v1", "structured": True,
        "schedule": [{"case_id": c["case_id"], "model": m, "prompt_version": v}
                     for c, m, v in schedule(cases)],
    }
    path = FOLDER / "settings.json"
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    tags = requests.get(base + "/api/tags", timeout=15)
    tags.raise_for_status()
    installed = {m["name"]: {key: m[key] for key in ("digest", "size", "details")}
                 for m in tags.json()["models"] if m["name"] in (FIRST_MODEL, SECOND_MODEL)}
    if len(installed) != 2:
        raise ValueError("Both declared vision models must already be installed.")
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["protocol"] != frozen or previous["installed_models"] != installed:
            raise ValueError("The frozen study inputs or installed models changed; do not overwrite this study.")
    else:
        version = requests.get(base + "/api/version", timeout=15)
        version.raise_for_status()
        snapshot = {"frozen_at": datetime.now(timezone.utc).isoformat(), "protocol": frozen,
                    "installed_models": installed, "ollama": version.json(),
                    "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                    for name in ("agents/vision/run.py", "agents/vision/schema.py",
                                                 "agents/vision/experiment.py")}}
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def run_study():
    """Make each planned call once and save its exact result path immediately."""
    cases = read_cases()
    freeze_settings(cases)
    done = {(r["case_id"], r["model"], r["prompt_version"]) for r in read_runs()}
    for number, (case, model, version) in enumerate(schedule(cases), 1):
        key = (case["case_id"], model, version)
        if key in done:
            continue
        print(f"[{number}/25] {case['case_id']} {model} {version}", flush=True)
        args = argparse.Namespace(image_id=case["image_id"], model=model, prompt_version=version,
                                  description=case["description"], structured=True, timeout=600,
                                  context_size=8192, severity_rubric=True)
        result, path = run_case(args)
        row = {"case_id": case["case_id"], "model": model, "prompt_version": version,
               "result_file": path.relative_to(ROOT).as_posix()}
        with (FOLDER / "runs.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(row) + "\n")
        print(f"  {result['status']} | {result['elapsed_seconds']} s | "
              f"{result.get('observation', {}).get('category')} | {path.name}", flush=True)
    summarize()


def syntax_valid(result):
    """Distinguish JSON syntax from schema validity and visual correctness."""
    try:
        return isinstance(json.loads(result.get("raw_response", {}).get("message", {}).get("content", "")), dict)
    except (ValueError, TypeError):
        return False


def score_group(rows, cases, group, model, version):
    """Use all scheduled cases in each denominator; failures score zero."""
    by_case = {row["case_id"]: row["result"] for row in rows}
    rates = {}

    def rate(name, eligible, predicate):
        selected = [c for c in cases if eligible(c)]
        correct = sum(bool(predicate(by_case.get(c["case_id"], {}), c)) for c in selected)
        rates[name] = {"correct": correct, "total": len(selected),
                       "rate": round(correct / len(selected), 4) if selected else None}

    def valid(result):
        return result.get("status") == "completed" and result.get("schema_valid") is True

    def category(result, case):
        return valid(result) and result["observation"]["category"] == case["category"]

    rate("json_syntax", lambda c: True, lambda r, c: syntax_valid(r))
    rate("valid_output", lambda c: True, lambda r, c: valid(r))
    rate("category_accuracy", lambda c: c["kind"] in ("clear", "unrelated"), category)
    rate("correct_rejection", lambda c: c["kind"] == "unrelated", category)
    rate("conservative_abstention", lambda c: c["kind"] in ("uncertain", "blur"), category)
    rate("severity_agreement", lambda c: c["kind"] == "clear",
         lambda r, c: category(r, c) and r["observation"]["severity"] == c["severity"])
    rate("text_image_match", lambda c: c["kind"].startswith("text_"),
         lambda r, c: valid(r) and r["observation"]["text_image_consistent"] is c["match"])
    rate("text_case_category", lambda c: c["kind"].startswith("text_"), category)
    attempts = [r["result"] for r in rows]
    success = [r for r in attempts if valid(r)]
    loads = [r["raw_response"]["load_duration"] / 1e9 for r in attempts
             if "load_duration" in r.get("raw_response", {})]
    return {"comparison": group, "model": model, "prompt_version": version,
            "completed_attempts": len(attempts), "expected_attempts": len(cases), "metrics": rates,
            "median_attempt_seconds": median([r["elapsed_seconds"] for r in attempts]) if attempts else None,
            "median_success_seconds": median([r["elapsed_seconds"] for r in success]) if success else None,
            "median_load_seconds": median(loads) if loads else None}


def summarize():
    """Check matched inputs and write measured rates with explicit denominators."""
    cases = read_cases()
    rows = [{**row, "result": json.loads((ROOT / row["result_file"]).read_text(encoding="utf-8"))}
            for row in read_runs()]
    for case in cases:
        pair = [r["result"] for r in rows if r["case_id"] == case["case_id"] and r["model"] == FIRST_MODEL]
        if len(pair) == 2:
            check_pair(pair, ["v2", "v3"])
    for case_id in MODEL_CASES:
        pair = [r["result"] for r in rows if r["case_id"] == case_id and r["prompt_version"] == "v2"]
        if len(pair) == 2:
            for field in ("image_sha256", "description", "user_message", "options", "prompt_sha256",
                          "format_constraint", "output_schema"):
                if pair[0].get(field) != pair[1].get(field):
                    raise ValueError(f"Model comparison differs on {case_id}: {field}")
    groups = []
    for version in ("v2", "v3"):
        subset = [r for r in rows if r["model"] == FIRST_MODEL and r["prompt_version"] == version]
        groups.append(score_group(subset, cases, "prompt", FIRST_MODEL, version))
    model_cases = [c for c in cases if c["case_id"] in MODEL_CASES]
    for model in (FIRST_MODEL, SECOND_MODEL):
        subset = [r for r in rows if r["model"] == model and r["prompt_version"] == "v2"
                  and r["case_id"] in MODEL_CASES]
        groups.append(score_group(subset, model_cases, "model", model, "v2"))
    output = {"complete": len(rows) == 25, "attempts": len(rows), "groups": groups,
              "limitation": "Small development study with assistant visual reference labels; no independent accuracy claim."}
    (FOLDER / "metrics.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    with (FOLDER / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["comparison", "model", "prompt_version", "metric", "correct", "total", "rate"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for group in groups:
            for name, value in group["metrics"].items():
                writer.writerow({**{key: group[key] for key in fields[:3]}, "metric": name, **value})
    print(f"Scored {len(rows)}/25 recorded attempts; complete={output['complete']}.", flush=True)


def main():
    """Run or resume the frozen study, or summarize it without model calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    summarize() if args.summarize else run_study()


if __name__ == "__main__":
    main()
