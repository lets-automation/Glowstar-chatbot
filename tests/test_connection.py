"""
test_connection.py
------------------
Phase 1 "Definition of Done": prove Python can connect to the
Aastha ERP database and read real data.

Run it from the project root with:
    python -m tests.test_connection
"""

from sqlalchemy import text

from app.database.connection import get_engine


def test_connection():
    """Connect to AasthaErp and print 5 real table names."""
    engine = get_engine()

    # 'with' opens the connection and closes it cleanly afterward.
    with engine.connect() as conn:
        # Safe, read-only query: list 5 table names from the system catalog.
        result = conn.execute(
            text("SELECT TOP 5 name FROM sys.tables ORDER BY name")
        )
        rows = result.fetchall()

    print("SUCCESS - connected to AasthaErp.")
    print("Here are 5 tables from the database:")
    for row in rows:
        print("  -", row[0])

    # Basic assertion so this also works under pytest later.
    assert len(rows) > 0, "No tables returned - check the database."


if __name__ == "__main__":
    test_connection()
