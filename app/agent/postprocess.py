"""
postprocess.py
--------------
Turns the agent's raw answer into a richer, professional response:
  - pulls out follow-up SUGGESTIONS the model appended
  - builds a CITATION (source tables + retrieval time) from the SQL it ran
  - finds the EXPORT query (last SELECT) so the UI can offer Excel/PDF export

All of this is deterministic (no extra LLM calls -> no extra tokens).
"""

import re
from datetime import datetime

# Matches "FROM tblXxx" / "JOIN tblXxx" to discover which tables were read.
_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+(\[?tbl[A-Za-z0-9_]+\]?)", re.IGNORECASE)


def extract_suggestions(answer: str) -> tuple[str, list[str]]:
    """
    Split a trailing 'SUGGESTIONS: a | b | c' line out of the answer.
    Returns (clean_answer, [suggestions]).
    """
    kept, suggestions = [], []
    for line in answer.splitlines():
        if line.strip().upper().startswith("SUGGESTIONS:"):
            payload = line.split(":", 1)[1]
            suggestions = [s.strip() for s in payload.split("|") if s.strip()][:3]
        else:
            kept.append(line)
    return "\n".join(kept).strip(), suggestions


def build_citation(sql_used: list[str], now: datetime | None = None) -> str:
    """Build 'Source: tblX, tblY • Retrieved: 27 Jun 2026, 10:45 AM'."""
    if not sql_used:
        return ""
    tables: list[str] = []
    for sql in sql_used:
        for m in _TABLE_RE.findall(sql):
            t = m.strip("[]")
            if t not in tables:
                tables.append(t)
    if not tables:
        return ""
    now = now or datetime.now()
    src = ", ".join(tables[:4])
    if len(tables) > 4:
        src += f", +{len(tables) - 4} more"
    return f"Source: {src} • Retrieved: {now.strftime('%d %b %Y, %I:%M %p')}"


def export_query(sql_used: list[str]) -> str | None:
    """The last successful SELECT/WITH - what the UI exports to Excel/PDF."""
    for sql in reversed(sql_used):
        head = sql.strip().upper()
        if head.startswith("SELECT") or head.startswith("WITH"):
            return sql
    return None


def enrich(result: dict, now: datetime | None = None) -> dict:
    """
    Take the backend's raw {answer, sql_used, rows_returned} and return the
    full professional response.
    """
    clean, suggestions = extract_suggestions(result.get("answer", ""))
    sql_used = result.get("sql_used", [])
    ok = result.get("ok", True)
    return {
        "answer": clean,
        "suggestions": suggestions,
        "citation": build_citation(sql_used, now),
        # Only offer export on a turn that actually succeeded — otherwise the
        # exported file would contain results the chat couldn't present.
        "export_query": export_query(sql_used) if ok else None,
        "sql_used": sql_used,
        "rows_returned": result.get("rows_returned", 0),
        "ok": ok,
        # Inline visuals the model drew via show_widget; rendered in a sandboxed iframe.
        "widgets": result.get("widgets", []),
    }
