"""
vector_store.py
---------------
Wraps Pinecone (stores vectors and finds the nearest matches).

Key-gated: if PINECONE_API_KEY is not set, is_configured() returns False.
voyage-3 produces 1024-dimension vectors, so the index must be created
with dimension=1024 and metric="cosine".
"""

from app.config import settings

VECTOR_DIM = 1024  # voyage-3 embedding size


def is_configured() -> bool:
    """True only if a Pinecone API key is present."""
    return bool(settings.PINECONE_API_KEY)


def _client():
    """Create a Pinecone client (imported lazily)."""
    if not is_configured():
        raise RuntimeError("PINECONE_API_KEY is not set in .env.")
    from pinecone import Pinecone

    return Pinecone(api_key=settings.PINECONE_API_KEY)


def ensure_index():
    """Create the index if it doesn't exist yet (serverless, cosine)."""
    from pinecone import ServerlessSpec

    pc = _client()
    existing = [idx["name"] for idx in pc.list_indexes()]
    if settings.PINECONE_INDEX not in existing:
        pc.create_index(
            name=settings.PINECONE_INDEX,
            dimension=VECTOR_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(settings.PINECONE_INDEX)


def get_index():
    """Return the Pinecone index handle."""
    return _client().Index(settings.PINECONE_INDEX)


def upsert(items: list[dict]):
    """
    Upsert vectors. Each item: {"id": str, "values": [...], "metadata": {...}}.
    """
    get_index().upsert(vectors=items)


def query(vector: list[float], top_k: int = 5) -> list[dict]:
    """Return the top_k nearest matches with their metadata."""
    res = get_index().query(vector=vector, top_k=top_k, include_metadata=True)
    return [
        {"id": m["id"], "score": m["score"], "metadata": m.get("metadata", {})}
        for m in res.get("matches", [])
    ]
