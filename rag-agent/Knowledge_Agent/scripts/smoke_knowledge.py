"""Send one real HTTP request through the API or the imported n8n webhook."""

import argparse
import json
import time
from datetime import datetime, timezone

import requests

from api.schema import KnowledgeResponse
from config import ROOT


def main():
    """Record success or failure; a valid refusal is an integration result, not an answer-quality pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8020/knowledge")
    args = parser.parse_args()
    case = json.loads((ROOT / "evaluation/prompt_cases.json").read_text(encoding="utf-8"))["cases"][1]
    payload = {"category": case["category"], "description": case["description"]}
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "url": args.url, "request": payload,
              "scope": "Real integration smoke request using authored development case P02. A valid refusal does not count as a quality success."}
    start = time.monotonic()
    try:
        response = requests.post(args.url, json=payload, timeout=430)
        report.update(http_status=response.status_code, response_text=response.text)
        response.raise_for_status()
        result = KnowledgeResponse.model_validate(response.json())
        if result.answer_found and not result.sources:
            raise ValueError("An answer must include at least one source.")
        if not result.answer_found and result.sources:
            raise ValueError("A refusal must have an empty source list.")
        report.update(integration_passed=True, answer_found=result.answer_found)
    except (requests.RequestException, ValueError) as error:
        report.update(integration_passed=False, error=str(error))
    report["seconds"] = round(time.monotonic() - start, 3)
    folder = ROOT / "evaluation/integration_runs"
    folder.mkdir(exist_ok=True)
    output = folder / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Integration smoke check:", "passed" if report["integration_passed"] else "failed")
    print("Saved", output.relative_to(ROOT))
    raise SystemExit(0 if report["integration_passed"] else 1)


if __name__ == "__main__":
    main()
