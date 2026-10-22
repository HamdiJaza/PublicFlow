"""Dense BGE-M3 retrieval with category filtering and an explicit index-version check."""

import hashlib
import json

from config import ROOT, Settings
from rag.corpus_state import fingerprints
from rag.embeddings import OllamaEmbeddings


class KnowledgeRetriever:
    """The same model artifact must embed chunks and queries; old vectors are not reused."""

    def __init__(self, settings=None):
        self.settings = settings or Settings.from_env()
        self.encoder = OllamaEmbeddings(self.settings)
        self.client = None

    def check_index(self, strategy):
        """Reject missing, stale or differently embedded indexes before searching."""
        if strategy not in {"structure", "fixed"}:
            raise ValueError("Unknown chunking strategy.")
        path = ROOT / f"data/index_{strategy}.json"
        if not path.exists():
            raise RuntimeError("The corrected index is not built. Run: python -m rag.ingest --strategy all")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["files"] != fingerprints():
            raise RuntimeError("The corpus or source ledger changed; rebuild both indexes.")
        chunker_hash = hashlib.sha256((ROOT / "rag/ingest.py").read_bytes()).hexdigest()
        if manifest.get("chunker_sha256") != chunker_hash or manifest.get("qdrant_path") != str(self.settings.qdrant_path.resolve()):
            raise RuntimeError("The chunker or vector-store path changed; rebuild the index.")
        installed = self.encoder.model_info()
        if installed["digest"] != manifest["embedding"]["digest"]:
            raise RuntimeError("The BGE-M3 artifact changed; rebuild the index before querying.")
        if self.client is None:
            from qdrant_client import QdrantClient
            self.client = QdrantClient(path=str(self.settings.qdrant_path))

    def retrieve(self, query, category, top_k=3, strategy="structure"):
        """Return raw ranked candidates; API and evaluation apply the shared score policy."""
        self.check_index(strategy)
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        query_filter = None if category == "NONE" else Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])
        response = self.client.query_points(collection_name="municipal_" + strategy,
                                            query=self.encoder.encode(query), query_filter=query_filter,
                                            limit=top_k, with_payload=True)
        return [{**point.payload, "rank": index, "score": float(point.score)}
                for index, point in enumerate(response.points, 1)]
