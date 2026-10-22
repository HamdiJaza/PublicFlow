"""POST /knowledge: retrieve, apply one source policy, generate and validate JSON."""

import json
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
from typing import Annotated
from uuid import uuid4

import requests
from fastapi import Depends, FastAPI, HTTPException

from api.generation import build_messages, generate, parse_answer
from api.schema import KnowledgeRequest, KnowledgeResponse, SourceItem
from config import ROOT, Settings
from rag.policy import select_hits

app = FastAPI(title="Municipal Knowledge Agent", version="1.1")
request_lock = Lock()


@lru_cache(maxsize=1)
def get_settings():
    """Load one environment configuration per service process."""
    return Settings.from_env()


@lru_cache(maxsize=1)
def get_retriever():
    """Load dependencies and the index lazily, without downloads at import time."""
    from rag.retrieve import KnowledgeRetriever
    return KnowledgeRetriever(get_settings())


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]):
    """Report configuration and index-file presence; this is not a live model test."""
    return {"status": "configured", "generation_provider": settings.generation_provider,
            "generation_model": settings.generation_model, "embedding_model": settings.embedding_model,
            "score_threshold": settings.score_threshold, "default_strategy": settings.strategy,
            "index_manifest_present": (ROOT / f"data/index_{settings.strategy}.json").exists()}


@app.post("/knowledge", response_model=KnowledgeResponse)
def knowledge(request: KnowledgeRequest, settings: Annotated[Settings, Depends(get_settings)]):
    """Keep the context and citation sets identical; failures remain HTTP errors."""
    if not request.description.strip():
        raise HTTPException(422, "description cannot be blank.")
    if request.prompt_version != "v4_grounded":
        raise HTTPException(422, "Only v4_grounded is enabled for the service. Use the experiment runner for other versions.")
    if not request_lock.acquire(blocking=False):
        raise HTTPException(503, "The local knowledge agent is busy.")
    record = {"request": request.model_dump(), "settings": {
        "score_threshold": settings.score_threshold, "top_k": settings.top_k,
        "provider": settings.generation_provider, "model": settings.generation_model}}
    try:
        try:
            retriever = get_retriever()
            hits = retriever.retrieve(request.description, request.category, settings.top_k,
                                      strategy=request.strategy or settings.strategy)
        except (ImportError, RuntimeError, ValueError, OSError, requests.RequestException) as error:
            raise HTTPException(503, str(error)) from error
        selected = select_hits(hits, settings.score_threshold)
        record["retrieved"] = hits
        record["context_sources"] = selected
        if not selected:
            answer = KnowledgeResponse(procedure=None, deadline=None, answer_found=False, sources=[])
        else:
            prompt = build_messages(request.prompt_version, request, selected)
            content, raw, payload = generate(settings, prompt)
            record.update(raw_response=raw, generation_request=payload)
            result = parse_answer(content)
            if result.deadline is not None and not any(result.deadline in hit["text"] for hit in selected):
                raise ValueError("The generated deadline does not occur in the supplied context.")
            sources = [SourceItem(chunk_id=hit["chunk_id"], url=hit["url"], score=round(hit["score"], 4)) for hit in selected]
            answer = KnowledgeResponse(**result.model_dump(), sources=sources if result.answer_found else [])
        record.update(status="completed", response=answer.model_dump())
        return answer
    except HTTPException as error:
        record.update(status="failed", error=str(error.detail))
        raise
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        record.update(status="failed", error=str(error))
        raise HTTPException(502, "Model generation or output validation failed.") from error
    finally:
        request_lock.release()
        save_record(record)


def save_record(record):
    """Keep actual API runs separate from unit fixtures and prompt-only studies."""
    folder = ROOT / "evaluation/api_runs"
    folder.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ_") + uuid4().hex[:8] + ".json"
    (folder / name).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
