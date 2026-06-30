"""
search.py
---------
Ties the embedder (Voyage) and the vector store (Pinecone) together into
two operations:

  index_texts(items)  -> embed text + store it (one-time / when data changes)
  semantic_search(q)  -> embed the question + find the closest stored texts

Both are OFF unless VOYAGE_API_KEY and PINECONE_API_KEY are set. Use
is_enabled() to check before calling.
"""

from app.semantic import embedder, vector_store


def is_enabled() -> bool:
    """Semantic search works only when BOTH services are configured."""
    return embedder.is_configured() and vector_store.is_configured()


def index_texts(items: list[dict], batch_size: int = 100) -> int:
    """
    Index a list of {"id": str, "text": str, "metadata": {...}} items.
    Embeds the text and upserts into Pinecone. Returns how many were indexed.
    """
    if not is_enabled():
        raise RuntimeError("Semantic search is not configured (missing keys).")

    vector_store.ensure_index()
    total = 0
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        vectors = embedder.embed_documents([it["text"] for it in batch])
        vector_store.upsert(
            [
                {
                    "id": str(it["id"]),
                    "values": vec,
                    "metadata": {**it.get("metadata", {}), "text": it["text"]},
                }
                for it, vec in zip(batch, vectors)
            ]
        )
        total += len(batch)
    return total


def semantic_search(question: str, top_k: int = 5) -> list[dict]:
    """Find the stored texts most similar in meaning to the question."""
    if not is_enabled():
        raise RuntimeError("Semantic search is not configured (missing keys).")

    vector = embedder.embed_query(question)
    return vector_store.query(vector, top_k=top_k)
