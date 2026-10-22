"""Apply reviewed references and summaries; disabled sources remain auditable but unindexed."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Write the source ledger from the documented audit, without creating missing facts."""
    audit = json.loads((ROOT / "rag/source_audit.json").read_text(encoding="utf-8"))
    path = ROOT / "rag/sources.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    reviewed = {entry["doc_id"]: entry for entry in audit["documents"]}
    for row in rows:
        entry = reviewed[row["doc_id"]]
        row.update(title=entry["title"], url=entry["url"], last_update=entry["last_update"],
                   verification_date=audit["review_date"], verification_status=entry["status"],
                   include_in_index=str(entry["include_in_index"]).lower(), source_section=entry["section"],
                   note=entry["removed_claims"])
        if entry["content"] is not None:
            (ROOT / "rag/corpus" / (row["doc_id"] + ".md")).write_text(entry["content"], encoding="utf-8")
        if row["doc_id"] in {"DOC-ROAD-03", "DOC-WASTE-02"}:
            row["source_type"] = "primary"
        if row["doc_id"] == "DOC-WASTE-02":
            row["issuer"] = "Portail des collectivités locales"
            row["municipality"] = "National; pas de procédure propre à Tunis"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated {len(rows)} source records; {sum(row['include_in_index'] == 'true' for row in rows)} enabled.")


if __name__ == "__main__":
    main()
