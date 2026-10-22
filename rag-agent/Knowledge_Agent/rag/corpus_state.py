"""Read the source ledger and fingerprint files used to build an index."""

import csv
import hashlib

from config import ROOT


def source_rows():
    """Return the audited ledger; an unchecked entry is never silently enabled."""
    with (ROOT / "rag/sources.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if any("include_in_index" not in row for row in rows):
        raise ValueError("The source ledger needs the source-audit fields before indexing.")
    return rows


def fingerprints():
    """Any corpus or source-reference edit requires rebuilding derived vectors."""
    paths = [ROOT / "rag/sources.csv", *sorted((ROOT / "rag/corpus").glob("*.md"))]
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
