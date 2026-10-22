"""Check installed resources and index consistency before starting the API."""

import os

import requests

from config import Settings
from rag.retrieve import KnowledgeRetriever


def check():
    """Inspect actual resources without pretending to execute a successful query."""
    settings = Settings.from_env()
    retriever = KnowledgeRetriever(settings)
    try:
        retriever.check_index(settings.strategy)
        collection = "municipal_" + settings.strategy
        if not retriever.client.collection_exists(collection):
            raise RuntimeError("The configured Qdrant collection is missing; rebuild the indexes.")
        if retriever.client.count(collection, exact=True).count == 0:
            raise RuntimeError("The configured Qdrant collection is empty; rebuild the indexes.")
        if settings.generation_provider == "ollama":
            response = requests.get(settings.ollama_url + "/api/tags", timeout=15)
            response.raise_for_status()
            names = {model["name"] for model in response.json()["models"]}
            if not names.intersection({settings.generation_model, settings.generation_model + ":latest"}):
                raise RuntimeError(f"Generation model missing. Run: ollama pull {settings.generation_model}")
        elif not os.getenv("GROQ_API_KEY") or not settings.generation_model:
            raise RuntimeError("Groq requires GROQ_API_KEY and GROQ_MODEL.")
        print("Resource checks passed. Run a real POST /knowledge request to verify inference.")
    finally:
        if retriever.client is not None:
            retriever.client.close()


if __name__ == "__main__":
    try:
        check()
    except (ImportError, RuntimeError, OSError, ValueError, KeyError, requests.RequestException) as error:
        raise SystemExit("Setup incomplete: " + str(error)) from error
