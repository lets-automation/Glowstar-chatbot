"""
test_schema.py
--------------
Phase 2 "Definition of Done": print the generated schema context so we
can eyeball it - key business tables with columns + relationships +
glossary, and NO AspNet*/system tables.

Run from the project root with:
    python -m tests.test_schema
"""

from app.schema import extractor
from app.schema.context import KEY_TABLES, build_schema_context


def test_schema_context():
    # 1. Sanity-check the extractor: only business tables, none excluded.
    tables = extractor.get_tables()
    names = [t["name"] for t in tables]

    assert len(names) > 0, "No business tables found."
    assert all(n.lower().startswith("tbl") for n in names), (
        "A non-business table slipped through the filter."
    )
    assert not any("aspnet" in n.lower() for n in names), "AspNet table not excluded!"

    # 2. Build and print the context the agent will use.
    context = build_schema_context()
    print(context)

    print("\n" + "=" * 60)
    print(f"Total business tables in DB : {len(names)}")
    print(f"Key tables described here   : {len(KEY_TABLES)}")
    print(f"Schema context length       : {len(context):,} characters")
    print("=" * 60)

    assert "AasthaErp" in context
    assert "BUSINESS GLOSSARY" in context


if __name__ == "__main__":
    test_schema_context()
