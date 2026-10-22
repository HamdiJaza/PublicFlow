"""Use the same Ollama BGE-M3 artifact to embed indexed chunks and incoming queries."""

import math

import requests


class OllamaEmbeddings:
    """Only dense embeddings are used; the installed model digest identifies the run."""

    def __init__(self, settings):
        self.settings = settings

    def model_info(self):
        """Fail clearly if BGE-M3 is absent; never silently use another model."""
        response = requests.get(self.settings.ollama_url + "/api/tags", timeout=15)
        response.raise_for_status()
        name = self.settings.embedding_model
        for model in response.json().get("models", []):
            if model["name"] in {name, name + ":latest"}:
                return model
        raise RuntimeError(f"Embedding model {name} is missing. Run: ollama pull {name}")

    def encode(self, text):
        """Reject oversized inputs and normalize the actual returned dense vector."""
        response = requests.post(self.settings.ollama_url + "/api/embed",
                                 json={"model": self.settings.embedding_model, "input": text,
                                       "truncate": False, "keep_alive": "2m"}, timeout=self.settings.timeout)
        response.raise_for_status()
        vector = response.json()["embeddings"][0]
        length = math.sqrt(sum(value * value for value in vector))
        if len(vector) != 1024 or not math.isfinite(length) or length == 0:
            raise ValueError("Expected a finite, nonzero 1024-dimensional BGE-M3 vector.")
        return [value / length for value in vector]
