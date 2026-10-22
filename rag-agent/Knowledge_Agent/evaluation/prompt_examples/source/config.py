"""Shared configuration for ingestion, retrieval, generation and evaluation."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """One explicit configuration; evaluation uses the same score cutoff as the API."""

    top_k: int = 3
    score_threshold: float = 0.40
    strategy: str = "structure"
    qdrant_path: Path = ROOT / "data/qdrant"
    ollama_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    tokenizer_model: str = "BAAI/bge-m3"
    generation_provider: str = "ollama"
    generation_model: str = "qwen2.5:3b"
    timeout: int = 180

    @classmethod
    def from_env(cls):
        """Read optional overrides without loading credentials from the original archive."""
        path = Path(os.getenv("QDRANT_PATH", str(ROOT / "data/qdrant")))
        if not path.is_absolute():
            path = ROOT / path
        provider = os.getenv("GENERATION_PROVIDER", "ollama")
        model = os.getenv("GROQ_MODEL", "") if provider == "groq" else os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        settings = cls(
            top_k=int(os.getenv("TOP_K", "3")),
            score_threshold=float(os.getenv("SCORE_THRESHOLD", "0.40")),
            strategy=os.getenv("CHUNK_STRATEGY", "structure"),
            qdrant_path=path.resolve(),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "bge-m3"),
            generation_provider=provider,
            generation_model=model,
        )
        if settings.strategy not in {"structure", "fixed"}:
            raise ValueError("CHUNK_STRATEGY must be structure or fixed.")
        if not 1 <= settings.top_k <= 10 or not -1 <= settings.score_threshold <= 1:
            raise ValueError("Use TOP_K between 1 and 10 and SCORE_THRESHOLD between -1 and 1.")
        if provider not in {"ollama", "groq"}:
            raise ValueError("GENERATION_PROVIDER must be ollama or groq.")
        return settings
