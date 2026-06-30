"""
context.py
----------
Turns the raw schema (from extractor.py) + the business glossary
(from glossary.py) into one compact "schema context" text block that
the AI agent reads before writing SQL.

WHY ONLY KEY TABLES:
There are 239 business tables - far too many to feed the LLM at once.
We start with the ~20 most important (largest / most-asked) tables.
Adding more later is as easy as editing KEY_TABLES below.
"""

from app.config import settings
from app.schema import extractor
from app.schema.glossary import render_data_notes, render_glossary_text, table_note

# Cap columns shown per table (token saving). Read from config so it can be
# disabled (SCHEMA_MAX_COLS=0) on Claude/paid tier. The most-used columns
# come first, so the first ~30 cover almost every real question.
MAX_COLS_PER_TABLE = settings.SCHEMA_MAX_COLS

# The key business tables we describe in detail for the agent.
# Easy to extend: just add a table name to this list.
KEY_TABLES = [
    "tblPacket",
    "tblPacketHistory",
    "tblPacketIssue",
    "tblPacketDetail",
    "tblPacketPoint",
    "tblIssuedPacketDetail",
    "tblFinalPacket",
    "tblJangadPackets",
    "tblPlanMaster",
    "tblPlanMasterOptional",
    "tblLabourRate",
    "tblPointRateLabour",
    "tblLabourResult",
    "tblIncentiveAmount",
    "tblBonusRate",
    "tblReportRate",
    "tblRepairLog",
    "tblRepairLogNew",
    "tblTimeAttendance",
    "tblJunk",
    "tblEmployee",
    "tblEmpDetail",
]


def _relationships_for(table: str, foreign_keys: list[dict]) -> list[str]:
    """Return human-readable FK lines involving this table."""
    lines = []
    for fk in foreign_keys:
        if fk["parent_table"] == table:
            lines.append(
                f"{table}.{fk['parent_column']} -> "
                f"{fk['ref_table']}.{fk['ref_column']}"
            )
    return lines


def build_schema_context(table_names: list[str] | None = None) -> str:
    """
    Build the full schema context text for the agent:
      - per key table: row count, business meaning, columns, relationships
      - the business glossary
      - a note that more tables exist
    """
    tables = table_names or KEY_TABLES

    # Pull everything we need once.
    all_tables = extractor.get_tables()
    row_counts = {t["name"]: t["rows"] for t in all_tables}
    columns = extractor.get_columns(tables)
    foreign_keys = extractor.get_foreign_keys()

    parts: list[str] = []
    parts.append("=== DATABASE: AasthaErp (diamond manufacturing ERP) ===")
    parts.append(
        f"This context describes {len(tables)} key business tables "
        f"(out of {len(all_tables)} total). All tables are READ-ONLY."
    )

    parts.append("\n=== KEY TABLES ===")
    for table in tables:
        cols = columns.get(table)
        if not cols:
            # Table name in KEY_TABLES but not found in DB - skip safely.
            continue

        rows = row_counts.get(table, 0)
        note = table_note(table)

        parts.append(f"\nTABLE: {table}  ({rows:,} rows)")
        if note:
            parts.append(f"  meaning: {note}")

        # MAX_COLS_PER_TABLE = 0 means "no cap" (show all columns).
        if MAX_COLS_PER_TABLE and len(cols) > MAX_COLS_PER_TABLE:
            shown_cols = cols[:MAX_COLS_PER_TABLE]
            col_text = ", ".join(f"{c['name']} ({c['type']})" for c in shown_cols)
            col_text += f", ... (+{len(cols) - MAX_COLS_PER_TABLE} more columns)"
        else:
            col_text = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
        parts.append(f"  columns: {col_text}")

        rels = _relationships_for(table, foreign_keys)
        if rels:
            parts.append("  links: " + "; ".join(rels))

    # Append the business glossary (industry terms + table meanings).
    parts.append("\n" + render_glossary_text())

    # Append the data notes (coded values + misspelled columns) - critical
    # for accuracy on things like fluorescence ('Florecent') and colour codes.
    parts.append("\n" + render_data_notes())

    return "\n".join(parts)


# Quick manual check: `python -m app.schema.context`
if __name__ == "__main__":
    print(build_schema_context())
