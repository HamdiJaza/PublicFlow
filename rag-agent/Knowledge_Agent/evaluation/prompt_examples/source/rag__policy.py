"""Select one context set for both generation and returned citations."""


def select_hits(hits, threshold):
    """Keep scored candidates above the shared cutoff; this is not an answerability test."""
    return [hit for hit in hits if hit["score"] >= threshold]


def format_context(hits):
    """Keep source identifiers beside the exact text given to the model."""
    return "\n\n".join(
        f"[{hit['chunk_id']}] {hit['title']}\nSource: {hit['url']}\n{hit['text']}"
        for hit in hits
    )
