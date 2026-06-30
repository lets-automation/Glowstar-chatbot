# Semantic Search (Phase 7 — Optional)

Semantic search lets the agent answer **fuzzy, meaning-based** questions
("find plans similar to X", "comments about cracks") that exact SQL
filtering can't handle. It is **OFF by default**.

## Do we even need it for Aastha ERP?

Probably not at first. The Aastha ERP is mostly **structured, numeric data**
(weights, rates, counts, dates, IDs) — and the Text-to-SQL agent already
answers those well. Semantic search only adds value if the client asks
**meaning-based questions over free-text columns**, e.g.:
- `tblPlanMaster.Remark`, `tblRepairLogNew.Remark` / `Specification`
- `tblFinalPacket.Comment`, `tblJunk.Remark`

If those free-text questions come up, enable it. Otherwise leave it off —
it adds external cost (Voyage + Pinecone) for little benefit on numeric data.

## How it works

```
text column  -> [Voyage embed] -> vector -> [Pinecone store]
question     -> [Voyage embed] -> vector -> [Pinecone nearest match] -> rows
```

- `app/semantic/embedder.py`   — Voyage embeddings (voyage-3, 1024-dim)
- `app/semantic/vector_store.py` — Pinecone index (cosine, serverless)
- `app/semantic/search.py`     — `index_texts()` and `semantic_search()`

## To enable it

1. Create accounts: **Voyage AI** and **Pinecone**.
2. Put the keys in `.env`:
   ```
   VOYAGE_API_KEY=...
   PINECONE_API_KEY=...
   PINECONE_INDEX=aastha-semantic
   ```
3. Index the free-text data once (example):
   ```python
   from app.database.runner import run_select
   from app.semantic.search import index_texts

   rows = run_select(
       "SELECT ID, Remark FROM tblPlanMaster WHERE Remark IS NOT NULL"
   )["rows"]
   items = [{"id": r["ID"], "text": r["Remark"], "metadata": {"table": "tblPlanMaster"}}
            for r in rows]
   index_texts(items)
   ```
4. Search:
   ```python
   from app.semantic.search import semantic_search
   semantic_search("stones with black inclusions")
   ```
5. (Future) Add a router in the agent so it picks SQL vs semantic per question.

## Status
Scaffold built and key-gated. Not wired into the agent yet — enable only
if a real free-text search need appears.
