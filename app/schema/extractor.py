"""
extractor.py
------------
Reads the STRUCTURE of the Aastha ERP database (not the data itself):
  - which tables exist + how many rows they have
  - each table's columns + data types
  - foreign-key relationships (how tables link together)

This is the raw material the context builder turns into "schema context"
for the AI agent. Everything here is READ-ONLY (it only queries the
SQL Server system catalog).
"""

from functools import lru_cache

from sqlalchemy import text

from app.database.connection import get_engine

# NOTE on caching: the database SCHEMA (tables/columns/relationships) does not
# change while the app runs, so we read it from the DB once and cache it. This
# makes every question faster and avoids hammering the DB. If the schema ever
# changes, restart the app (or call clear_schema_cache()).

# Tables we never show the agent (login/security/system - not business data).
# A table is "business data" if its name starts with "tbl".
_EXCLUDED_PREFIXES = ("aspnet", "__ef", "__migration", "sysdiagrams")


def is_business_table(name: str) -> bool:
    """True only for real business tables (they start with 'tbl')."""
    lower = name.lower()
    if lower.startswith(_EXCLUDED_PREFIXES):
        return False
    return lower.startswith("tbl")


@lru_cache(maxsize=1)
def get_tables() -> list[dict]:
    """
    Return all business tables with their row counts, biggest first.
    Uses sys.partitions (index_id 0/1) for accurate counts - same method
    we used in SSMS. Cached (schema is static at runtime).
    """
    sql = text(
        """
        SELECT t.name AS table_name, SUM(p.rows) AS row_count
        FROM sys.tables t
        JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE p.index_id IN (0, 1)
        GROUP BY t.name
        ORDER BY SUM(p.rows) DESC
        """
    )
    with get_engine().connect() as conn:
        rows = conn.execute(sql).fetchall()

    # Keep only business tables.
    return [
        {"name": r[0], "rows": int(r[1])}
        for r in rows
        if is_business_table(r[0])
    ]


@lru_cache(maxsize=1)
def _all_columns() -> dict[str, tuple]:
    """
    Read ALL business-table columns once and cache them.
    Returns {table_name: ((name, type), ...)} - tuples so the cache is safe.
    """
    sql = text(
        """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
    )
    with get_engine().connect() as conn:
        rows = conn.execute(sql).fetchall()

    out: dict[str, list] = {}
    for table, column, dtype in rows:
        if is_business_table(table):
            out.setdefault(table, []).append((column, dtype))
    return {t: tuple(cols) for t, cols in out.items()}


def get_columns(table_names: list[str] | None = None) -> dict[str, list[dict]]:
    """
    Return {table_name: [{name, type}, ...]} for the given tables (or all).
    Served from the cached column map - no DB hit after the first call.
    """
    all_cols = _all_columns()
    wanted = set(table_names) if table_names else set(all_cols)
    return {
        t: [{"name": n, "type": d} for (n, d) in all_cols[t]]
        for t in all_cols
        if t in wanted
    }


@lru_cache(maxsize=1)
def get_foreign_keys() -> list[dict]:
    """
    Return foreign-key links as a list of:
      {parent_table, parent_column, ref_table, ref_column}
    This tells the agent how to JOIN tables correctly. Cached.
    """
    sql = text(
        """
        SELECT
            tp.name AS parent_table,
            cp.name AS parent_column,
            tr.name AS ref_table,
            cr.name AS ref_column
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc
            ON fk.object_id = fkc.constraint_object_id
        JOIN sys.tables tp ON fkc.parent_object_id = tp.object_id
        JOIN sys.columns cp
            ON fkc.parent_object_id = cp.object_id
            AND fkc.parent_column_id = cp.column_id
        JOIN sys.tables tr ON fkc.referenced_object_id = tr.object_id
        JOIN sys.columns cr
            ON fkc.referenced_object_id = cr.object_id
            AND fkc.referenced_column_id = cr.column_id
        ORDER BY tp.name
        """
    )
    with get_engine().connect() as conn:
        rows = conn.execute(sql).fetchall()

    return [
        {
            "parent_table": r[0],
            "parent_column": r[1],
            "ref_table": r[2],
            "ref_column": r[3],
        }
        for r in rows
        if is_business_table(r[0]) and is_business_table(r[2])
    ]


def clear_schema_cache() -> None:
    """Clear all cached schema reads (call if the DB schema changes)."""
    get_tables.cache_clear()
    _all_columns.cache_clear()
    get_foreign_keys.cache_clear()


# Quick manual check: `python -m app.schema.extractor`
if __name__ == "__main__":
    tables = get_tables()
    print(f"Business tables found: {len(tables)}")
    print("Top 5 by rows:")
    for t in tables[:5]:
        print(f"  {t['name']:<28} {t['rows']:>12,}")

    fks = get_foreign_keys()
    print(f"\nForeign-key links found: {len(fks)}")
