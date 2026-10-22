"""Replay supplied scores or run both chunkers with the API's actual score cutoff."""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone

from config import ROOT, Settings
from rag.corpus_state import fingerprints, source_rows
from rag.policy import select_hits


def score_case(case, hits, threshold):
    """Document retrieval is separate from whether a model can answer the question."""
    retained = select_hits(hits, threshold)
    expected = case["expected_doc"]

    def rank(items):
        return next((i for i, hit in enumerate(items, 1) if hit["doc_id"] == expected), 0)

    return {"query_id": case["query_id"], "expected_doc": expected,
            "raw_rank": rank(hits), "retained_rank": rank(retained),
            "retained_count": len(retained), "threshold": threshold,
            "negative_blocked_by_score": expected == "NO_ANSWER" and not retained,
            "candidates": hits}


def summarize(rows):
    """Keep positive and negative denominators separate; refusal is not Hit@k."""
    output = {}
    for strategy in sorted({row["strategy"] for row in rows}):
        group = [row for row in rows if row["strategy"] == strategy]
        positives = [row for row in group if row["expected_doc"] != "NO_ANSWER"]
        negatives = [row for row in group if row["expected_doc"] == "NO_ANSWER"]
        count = len(positives)
        metrics = {"positive_queries": count, "negative_queries": len(negatives),
                   "positive_queries_with_no_context": sum(not row["retained_count"] for row in positives),
                   "negatives_blocked_by_score": sum(row["negative_blocked_by_score"] for row in negatives)}
        for field, label in (("raw_rank", "raw"), ("retained_rank", "retained")):
            metrics[label] = {"hit_at_1": sum(row[field] == 1 for row in positives) / count if count else None,
                              "hit_at_k": sum(row[field] > 0 for row in positives) / count if count else None,
                              "mrr": sum(1 / row[field] for row in positives if row[field]) / count if count else None}
        output[strategy] = metrics
    return output


def replay(threshold):
    """Recalculate saved original scores; no model or index is loaded."""
    path = ROOT / "evaluation/history/rag_results_original.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        original = list(csv.DictReader(handle))
    rows = []
    for case in original:
        hits = [{"doc_id": case[f"retrieved_{i}"], "score": float(case[f"score_{i}"])}
                for i in range(1, 4) if case[f"retrieved_{i}"] != "NONE"]
        rows.append({"strategy": case["strategy"], **score_case(case, hits, threshold)})
    return rows, {"mode": "historical_score_replay", "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "scope": "Original 12-document corpus and SentenceTransformers BGE-M3 scores supplied in the archive. No fresh retrieval, no Ollama embedding measurement, no generation test. Scores were saved to four decimals."}


def live(settings):
    """Keep original references, including sources now excluded by the audit."""
    from rag.retrieve import KnowledgeRetriever
    cases = json.loads((ROOT / "evaluation/queries.json").read_text(encoding="utf-8"))["cases"]
    active = {row["doc_id"] for row in source_rows() if row["include_in_index"] == "true"}
    retriever = KnowledgeRetriever(settings)
    rows = []
    try:
        for strategy in ("structure", "fixed"):
            for case in cases:
                hits = retriever.retrieve(case["query"], case["category"], settings.top_k, strategy)
                rows.append({"strategy": strategy, "reference_enabled": case["expected_doc"] in active,
                             **score_case(case, hits, settings.score_threshold)})
    finally:
        if retriever.client is not None:
            retriever.client.close()
    return rows, {"mode": "live_ollama_retrieval", "top_k": settings.top_k, "corpus": fingerprints(),
                  "manifests": {s: json.loads((ROOT / f"data/index_{s}.json").read_text()) for s in ("structure", "fixed")},
                  "scope": "Original development references remain unchanged. Disabled expected documents are coverage failures, not relabelled successes. A document hit does not prove a complete procedural answer."}


def main():
    """Save results separately; never overwrite the supplied evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    rows, protocol = live(settings) if args.live else replay(settings.score_threshold)
    report = {**protocol, "created_at": datetime.now(timezone.utc).isoformat(),
              "score_threshold": settings.score_threshold, "metrics": summarize(rows), "results": rows}
    if not args.live:
        other = [{"strategy": row["strategy"], **score_case(row, row["candidates"], 0.50)} for row in rows]
        report["comparison_cutoff_0.50"] = summarize(other)
    folder = ROOT / "evaluation/retrieval"
    folder.mkdir(exist_ok=True)
    name = datetime.now(timezone.utc).strftime("live_%Y%m%dT%H%M%S_%f.json") if args.live else "historical_replay.json"
    (folder / name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    print("Saved", (folder / name).relative_to(ROOT))


if __name__ == "__main__":
    main()
