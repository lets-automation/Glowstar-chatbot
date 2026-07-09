"""
runner.py
---------
Safely runs a single read-only SELECT against AasthaErp and returns the
results in a clean, JSON-friendly form.

Safety layers here:
  - re-validates the SQL is read-only (defense in depth)
  - sets a query timeout so a slow query can't hang forever
  - caps the number of rows actually fetched (backstop to TOP)
  - converts DB types (Decimal, datetime, etc.) to plain values
"""

import datetime
import decimal

from sqlalchemy import text

from app.core.sql_guard import DEFAULT_ROW_CAP, validate_and_prepare
from app.database.connection import get_engine

# How long (seconds) a single query may run before we give up.
DEFAULT_TIMEOUT_SECONDS = 30


def _clean_value(value):
    """Convert DB-specific types into plain JSON-friendly Python values."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat(sep=" ")
    if isinstance(value, bytes):
        return value.hex()
    return value


def run_select(
    sql: str,
    max_rows: int = DEFAULT_ROW_CAP,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """
    Run a validated read-only SELECT.

    Returns a dict:
      {
        "ok": True/False,
        "columns": [...],
        "rows": [ {col: val, ...}, ... ],
        "row_count": <int>,
        "truncated": True/False,   # were there more rows than max_rows?
        "sql": "<the SQL actually run>",
        "error": "<message if ok is False>",
      }
    """
    # 1. Validate read-only + apply row cap.
    ok, prepared = validate_and_prepare(sql, cap=max_rows)
    if not ok:
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "sql": sql,
            "error": prepared,  # the rejection reason
        }

    safe_sql = prepared

    try:
        with get_engine().connect() as conn:
            # Set a query timeout on the RAW pyodbc connection (pyodbc's
            # Connection.timeout = SQL_ATTR_QUERY_TIMEOUT, in seconds). Setting it
            # on SQLAlchemy's connection PROXY (conn.connection) is a no-op - it
            # doesn't forward to pyodbc - so an expensive SELECT would run
            # unbounded. Reach the underlying dbapi connection instead.
            try:
                raw = getattr(conn.connection, "dbapi_connection", None) or conn.connection
                raw.timeout = timeout
            except Exception:
                pass  # not fatal if the driver ignores it

            result = conn.execute(text(safe_sql))
            columns = list(result.keys())

            # Fetch one extra row to detect truncation.
            fetched = result.fetchmany(max_rows + 1)

        truncated = len(fetched) > max_rows
        fetched = fetched[:max_rows]

        rows = [
            {col: _clean_value(val) for col, val in zip(columns, row)}
            for row in fetched
        ]

        return {
            "ok": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "sql": safe_sql,
            "error": "",
        }

    except Exception as exc:
        # Return the DB error text so the agent can correct its SQL.
        return {
            "ok": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "sql": safe_sql,
            "error": f"{type(exc).__name__}: {exc}",
        }


# Quick manual check: `python -m app.database.runner`
if __name__ == "__main__":
    out = run_select("SELECT COUNT(*) AS total FROM tblPacket")
    print("Query :", out["sql"])
    print("OK    :", out["ok"])
    print("Rows  :", out["rows"])
    print("Error :", out["error"])
