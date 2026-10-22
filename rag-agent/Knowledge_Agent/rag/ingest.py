"""Build both chunking collections from audited sources with Ollama BGE-M3 vectors."""

import argparse
import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from config import ROOT, Settings
from rag.corpus_state import fingerprints, source_rows
from rag.embeddings import OllamaEmbeddings

STRUCTURE_MAX = 450
STRUCTURE_MIN = 80
OVERLAP = 50
FIXED_SIZE = 512


def split_fixed(text, tokenizer, size=FIXED_SIZE, overlap=OVERLAP):
    """Use actual BGE tokenizer IDs, with overlap only when a window is split."""
    ids = tokenizer.encode(text, add_special_tokens=False)
    for start in range(0, len(ids), size - overlap):
        part = ids[start:start + size]
        yield {"text": tokenizer.decode(part, skip_special_tokens=True).strip(), "token_count": len(part), "section_heading": "Fixed window"}
        if start + size >= len(ids):
            break


def split_structure(text, tokenizer):
    """Respect headings, merge sections below 80 tokens, and cap oversized sections at 450."""
    parts = re.split(r"(?m)^(#{1,3}\s+[^\n]+)", text)
    sections = []
    if parts[0].strip():
        sections.append(("Introduction", parts[0].strip()))
    for index in range(1, len(parts), 2):
        sections.append((parts[index].lstrip("#").strip(), parts[index] + "\n" + parts[index + 1]))
    merged = []
    pending = None
    for heading, content in sections:
        size = len(tokenizer.encode(content, add_special_tokens=False))
        if pending:
            combined = pending[1] + "\n\n" + content
            if len(tokenizer.encode(combined, add_special_tokens=False)) <= STRUCTURE_MAX:
                heading, content = pending[0], combined
                size = len(tokenizer.encode(content, add_special_tokens=False))
                pending = None
            else:
                merged.append(pending)
                pending = None
        if size < STRUCTURE_MIN:
            pending = (heading, content)
        else:
            merged.append((heading, content))
    if pending:
        merged.append(pending)
    for heading, content in merged:
        for chunk in split_fixed(content, tokenizer, STRUCTURE_MAX):
            chunk["section_heading"] = heading
            yield chunk


def ingest(settings, strategies, rebuild=False):
    """Write only a derived index, then record its corpus and embedding fingerprints."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    from transformers import AutoTokenizer

    encoder = OllamaEmbeddings(settings)
    model = encoder.model_info()
    tokenizer = AutoTokenizer.from_pretrained(settings.tokenizer_model, local_files_only=True)
    rows = [row for row in source_rows() if row["include_in_index"] == "true"]
    if not rows:
        raise ValueError("No audited sources are enabled.")
    client = QdrantClient(path=str(settings.qdrant_path))
    try:
        for strategy in strategies:
            collection = "municipal_" + strategy
            manifest_path = ROOT / f"data/index_{strategy}.json"
            if client.collection_exists(collection):
                if not rebuild:
                    raise ValueError("The index exists. Use --rebuild to replace derived vectors.")
                # A failed rebuild must never leave an old success manifest behind.
                manifest_path.unlink(missing_ok=True)
                client.delete_collection(collection)
            else:
                manifest_path.unlink(missing_ok=True)
            client.create_collection(collection, vectors_config=VectorParams(size=1024, distance=Distance.COSINE))
            points = []
            for row in rows:
                text = (ROOT / "rag/corpus" / (row["doc_id"] + ".md")).read_text(encoding="utf-8")
                chunks = split_structure(text, tokenizer) if strategy == "structure" else split_fixed(text, tokenizer)
                for index, chunk in enumerate(chunks, 1):
                    payload = {**row, **chunk, "chunk_id": f"{row['doc_id']}#{index:02d}", "strategy": strategy}
                    points.append(PointStruct(id=str(uuid5(NAMESPACE_URL, f"{collection}:{row['doc_id']}:{index}")),
                                              vector=encoder.encode(chunk["text"]), payload=payload))
            client.upsert(collection, points=points, wait=True)
            counts = [point.payload["token_count"] for point in points]
            manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "files": fingerprints(),
                        "chunker_sha256": hashlib.sha256((ROOT / "rag/ingest.py").read_bytes()).hexdigest(),
                        "qdrant_path": str(settings.qdrant_path.resolve()),
                        "embedding": {"provider": "ollama", "model": model["name"], "digest": model["digest"], "dimension": 1024},
                        "tokenizer": settings.tokenizer_model, "strategy": strategy, "chunks": len(points),
                        "documents": len(rows), "min_tokens": min(counts), "median_tokens": statistics.median(counts),
                        "max_tokens": max(counts), "chunk_parameters": {"structure_max": STRUCTURE_MAX, "structure_min": STRUCTURE_MIN,
                                                                       "fixed_size": FIXED_SIZE, "overlap_on_splits": OVERLAP}}
            (ROOT / "data").mkdir(exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"{strategy}: {len(points)} chunks; token min/median/max={min(counts)}/{statistics.median(counts)}/{max(counts)}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=["structure", "fixed", "all"], default="all")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    ingest(Settings.from_env(), ["structure", "fixed"] if args.strategy == "all" else [args.strategy], args.rebuild)
