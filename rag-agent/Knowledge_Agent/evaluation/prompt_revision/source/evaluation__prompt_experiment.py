"""Compare historical v3 and corrected v4 on the same real source contexts."""

import argparse
import csv
import hashlib
import json
import sys
import time
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.generation import generate, parse_answer, render_prompt
from api.schema import KnowledgeRequest
from config import ROOT, Settings
from rag.corpus_state import source_rows

FOLDER = ROOT / "evaluation/prompt_study"
VERSIONS = ["v3_structured", "v4_grounded"]


def digest(path):
    """Hash the exact case, source or prompt bytes used in an experiment."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize():
    """Score observable output constraints; these scores do not prove factual perfection."""
    rows = []
    for path in sorted((FOLDER / "runs").glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        answer = run.get("answer")
        expected = run["reference"]
        digits = "".join(str(unicodedata.digit(c)) for c in (answer or {}).get("procedure", "") or "" if c.isdigit())
        row = {"case_id": run["case_id"], "prompt_version": run["prompt_version"],
               "valid_json_and_schema": answer is not None,
               "answerability_agreement": answer is not None and answer["answer_found"] == expected["answer_found"],
               "no_invented_deadline": answer is not None and answer["deadline"] is None,
               "required_number_present": answer is not None and all(value in digits for value in expected["required_digits"]),
               "seconds": run["elapsed_seconds"], "result_file": path.relative_to(ROOT).as_posix()}
        row["all_constraints"] = all(row[key] for key in ["valid_json_and_schema", "answerability_agreement", "no_invented_deadline", "required_number_present"])
        rows.append(row)
    if rows:
        with (FOLDER / "results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    metrics = {version: {key: sum(row[key] for row in rows if row["prompt_version"] == version)
                         for key in ["valid_json_and_schema", "answerability_agreement", "no_invented_deadline", "required_number_present", "all_constraints"]}
               for version in VERSIONS}
    result = {"attempts": len(rows), "complete": len(rows) == len(VERSIONS) * 5, "per_version_denominator": 5, "metrics": metrics,
              "scope": "Five dependent development cases with fixed source contexts. Numeric checks and schema checks require separate qualitative review. No retrieval is executed."}
    (FOLDER / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


def run():
    """Freeze inputs, alternate prompt order and preserve all attempts without retries."""
    settings = replace(Settings.from_env(), generation_provider="ollama", generation_model="qwen2.5:3b")
    rows = {row["doc_id"]: row for row in source_rows()}
    cases_file = ROOT / "evaluation/prompt_cases.json"
    cases = json.loads(cases_file.read_text(encoding="utf-8"))["cases"]
    paths = [cases_file, ROOT / "rag/sources.csv", *[ROOT / f"prompts/knowledge/{version}.txt" for version in VERSIONS],
             ROOT / "api/generation.py", ROOT / "api/schema.py", Path(__file__).resolve()]
    paths += [ROOT / f"rag/corpus/{key}.md" for key in sorted({key for case in cases for key in case["documents"]})]
    hashes = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    installed = requests.get(settings.ollama_url + "/api/tags", timeout=15).json()["models"]
    model = next(model for model in installed if model["name"] == settings.generation_model)
    frozen = {"hashes": hashes, "provider": "ollama", "model": model["name"], "model_digest": model["digest"],
              "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}, "format": "json",
              "order": "Alternate first version by case; one attempt per condition; no retries.",
              "context_policy": "Full reviewed document summaries, shared between both prompts; no embedding/retrieval call."}
    (FOLDER / "runs").mkdir(parents=True, exist_ok=True)
    snapshot = FOLDER / "settings.json"
    if snapshot.exists() and json.loads(snapshot.read_text(encoding="utf-8")) != frozen:
        raise ValueError("Frozen prompt-study inputs changed; do not mix different experiments.")
    snapshot.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    for index, case in enumerate(cases):
        hits = [{**rows[key], "chunk_id": key + "#source", "text": (ROOT / f"rag/corpus/{key}.md").read_text(encoding="utf-8")} for key in case["documents"]]
        for version in VERSIONS if index % 2 == 0 else list(reversed(VERSIONS)):
            request = KnowledgeRequest(category=case["category"], description=case["description"], prompt_version=version)
            path = FOLDER / "runs" / f"{case['case_id']}_{version}.json"
            if path.exists():
                continue
            prompt = render_prompt(version, request, hits)
            record = {"case_id": case["case_id"], "prompt_version": version, "request": request.model_dump(),
                      "model_digest": model["digest"], "reference": case,
                      "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                      "started_at": datetime.now(timezone.utc).isoformat()}
            start = time.monotonic()
            try:
                content, raw, payload = generate(settings, prompt)
                record.update(raw_response=raw, generation_request=payload)
                record["answer"] = parse_answer(content).model_dump()
                record["status"] = "completed"
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                record.update(status="failed", error=str(error))
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(case["case_id"], version, record["status"], record["elapsed_seconds"], flush=True)
    summarize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--versions", nargs="+", choices=["v3_structured", "v4_grounded", "v5_decision"], default=VERSIONS)
    parser.add_argument("--output", default="evaluation/prompt_study")
    args = parser.parse_args()
    VERSIONS = args.versions
    FOLDER = (ROOT / args.output).resolve()
    if ROOT not in FOLDER.parents:
        raise SystemExit("Keep experiment output inside the project.")
    summarize() if args.summarize else run()
