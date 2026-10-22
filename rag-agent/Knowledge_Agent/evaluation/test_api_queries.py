"""Send development questions through the live HTTP endpoint and save every response."""

import argparse
import json
import time
import unicodedata
from datetime import datetime, timezone

import requests

from api.schema import KnowledgeRequest, KnowledgeResponse
from config import ROOT


def main():
    """These checks cover selected constraints; a human must still check the answer text."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8020")
    args = parser.parse_args()
    cases = json.loads((ROOT / "evaluation/prompt_cases.json").read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        payload = KnowledgeRequest(category=case["category"], description=case["description"]).model_dump()
        result = {"case_id": case["case_id"], "request": payload, "reference": case}
        start = time.monotonic()
        try:
            response = requests.post(args.url.rstrip("/") + "/knowledge", json=payload, timeout=240)
            result.update(http_status=response.status_code, response_text=response.text)
            response.raise_for_status()
            answer = KnowledgeResponse.model_validate(response.json())
            digits = "".join(str(unicodedata.digit(c)) for c in answer.procedure or "" if c.isdigit())
            result["checks"] = {"answerability": answer.answer_found == case["answer_found"],
                                "no_invented_deadline": answer.deadline is None,
                                "required_number": all(number in digits for number in case["required_digits"]),
                                "citations_present_for_answer": bool(answer.sources) if answer.answer_found else not answer.sources}
            result["passed"] = all(result["checks"].values())
        except (requests.RequestException, ValueError) as error:
            result.update(passed=False, error=str(error))
        result["seconds"] = round(time.monotonic() - start, 3)
        results.append(result)
        print(case["case_id"], "passed" if result["passed"] else "failed", flush=True)
    folder = ROOT / "evaluation/http_runs"
    folder.mkdir(exist_ok=True)
    path = folder / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f.json")
    report = {"scope": "Live HTTP, retrieval and generation on five development questions, not an independent factuality benchmark.",
              "endpoint": args.url, "passed": sum(row["passed"] for row in results), "total": len(results), "results": results}
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Saved", path.relative_to(ROOT))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
