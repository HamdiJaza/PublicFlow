"""Render versioned prompts and call a configured text model without hidden fallbacks."""

import json
import os
import re

import requests

from api.schema import ModelAnswer
from config import ROOT
from rag.policy import format_context

PROMPTS = {"v1_basic", "v2_guardrails", "v3_structured", "v4_grounded", "v5_decision", "v6_roles", "v7_examples"}


def build_messages(version, request, hits):
    """Separate system instructions from citizen/source data in the role-based versions."""
    if version not in {"v6_roles", "v7_examples"}:
        return [{"role": "user", "content": render_prompt(version, request, hits)}]
    language = "Arabic" if re.search(r"[\u0600-\u06ff]", request.description) else "French"
    instructions = (ROOT / "prompts/knowledge" / (version + ".txt")).read_text(encoding="utf-8")
    data = {"response_language": language, "category": request.category,
            "department": request.department, "question": request.description,
            "source_context": format_context(hits)}
    return [{"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]


def render_prompt(version, request, hits):
    """Replace template fields once so braces inside supplied text stay unchanged."""
    if version not in PROMPTS:
        raise ValueError("Unknown prompt version.")
    template = (ROOT / "prompts/knowledge" / (version + ".txt")).read_text(encoding="utf-8")
    values = {"context": format_context(hits), "category": request.category,
              "department": request.department or "Non précisé", "description": request.description}
    return re.sub(r"\{(context|category|department|description)\}", lambda match: values[match[1]], template)


def generate(settings, prompt, structured=True):
    """Return raw provider output for recording; credentials never enter saved payloads."""
    payload = {"model": settings.generation_model,
               "messages": prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]}
    if settings.generation_provider == "ollama":
        payload.update(stream=False, options={"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}, keep_alive="2m")
        if structured:
            payload["format"] = "json"
        response = requests.post(settings.ollama_url + "/api/chat", json=payload, timeout=settings.timeout)
        response.raise_for_status()
        raw = response.json()
        content = raw.get("message", {}).get("content", "")
        if raw.get("done_reason") == "length":
            raise ValueError("Model output reached the token limit.")
    else:
        key = os.getenv("GROQ_API_KEY")
        if not key or not settings.generation_model:
            raise ValueError("Groq requires GROQ_API_KEY and an available GROQ_MODEL.")
        payload["temperature"] = 0
        if structured:
            payload["response_format"] = {"type": "json_object"}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload,
                                 headers={"Authorization": "Bearer " + key}, timeout=settings.timeout)
        response.raise_for_status()
        raw = response.json()
        content = raw["choices"][0]["message"]["content"]
        if raw["choices"][0].get("finish_reason") == "length":
            raise ValueError("Model output reached the token limit.")
    if not content.strip():
        raise ValueError("Model returned empty final content.")
    return content, raw, payload


def parse_answer(content):
    """Reject invalid JSON and wrong field types rather than coercing string booleans."""
    return ModelAnswer.model_validate(json.loads(content))
