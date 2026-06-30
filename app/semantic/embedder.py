"""
embedder.py
-----------
Wraps the Voyage AI embedding model (turns text into vectors).

Voyage is Anthropic's recommended embedding partner. This module is
key-gated: if VOYAGE_API_KEY is not set, is_configured() returns False
and nothing tries to call the API.
"""

from app.config import settings

# Voyage model to use. voyage-3 is a strong general-purpose model.
EMBED_MODEL = "voyage-3"


def is_configured() -> bool:
    """True only if a Voyage API key is present."""
    return bool(settings.VOYAGE_API_KEY)


def _client():
    """Create a Voyage client (imported lazily so the package loads w/o the key)."""
    if not is_configured():
        raise RuntimeError("VOYAGE_API_KEY is not set in .env.")
    import voyageai

    return voyageai.Client(api_key=settings.VOYAGE_API_KEY)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents (for indexing)."""
    result = _client().embed(texts, model=EMBED_MODEL, input_type="document")
    return result.embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single search query."""
    result = _client().embed([text], model=EMBED_MODEL, input_type="query")
    return result.embeddings[0]
