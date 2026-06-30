"""
test_semantic.py
----------------
Phase 7 test (OPTIONAL feature). Confirms the semantic-search scaffold
imports cleanly and is correctly OFF when keys are absent. If both keys
are present, it does a tiny index + search round-trip.

Run from the project root with:
    python -m tests.test_semantic
"""

from app.semantic import search


def run_all():
    # The modules must always import without keys.
    print("Semantic modules imported OK.")
    print("Enabled:", search.is_enabled())

    if not search.is_enabled():
        print("SKIPPED - semantic search is OFF (no VOYAGE_API_KEY / PINECONE_API_KEY).")
        print("This is expected. See SEMANTIC.md to enable it if needed.")
        return

    # Keys present -> tiny round-trip.
    sample = [
        {"id": "1", "text": "round brilliant diamond, very white", "metadata": {}},
        {"id": "2", "text": "emerald cut, slightly tinted", "metadata": {}},
    ]
    n = search.index_texts(sample)
    print(f"Indexed {n} sample texts.")
    hits = search.semantic_search("white round stone", top_k=2)
    print("Top match:", hits[0] if hits else "none")
    assert hits, "Expected at least one semantic match."
    print("SUCCESS - semantic search round-trip worked.")


if __name__ == "__main__":
    run_all()
