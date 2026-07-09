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

from app.agent.widget import build_chart_html

# Matches "FROM tblXxx" / "JOIN tblXxx" to discover which tables were read.
_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+(\[?tbl[A-Za-z0-9_]+\]?)", re.IGNORECASE)

# A Markdown table row: "| a | b |". Two or more such lines = a data table.
_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|.*$", re.MULTILINE)

# Honest message shown when the model tried to present data it never queried.
_UNGROUNDED_MSG = (
    "I wasn't able to pull that from the database just now, so I don't have real "
    "figures to show — and I won't show made-up ones. Could you rephrase or add a "
    "little detail (e.g. which kapan, date range, or department) and I'll query it?"
)


def looks_like_data_table(answer: str) -> bool:
    """True if the answer contains a Markdown table (header + at least one row)."""
    return len(_MD_TABLE_ROW.findall(answer or "")) >= 2


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


# "The user asked for a chart" - keyword check on the question.
_CHART_ASKED_RE = re.compile(
    r"\b(chart|graph|plot|visuali[sz]e|bar ?chart|pie ?chart|line ?chart)\b",
    re.IGNORECASE,
)


def _first_label_and_value_cols(columns: list, rows: list) -> tuple[str, str] | None:
    """Pick a text column for labels and a numeric column for values."""
    if not columns or not rows:
        return None
    sample = rows[0]
    label_col = next(
        (c for c in columns if isinstance(sample.get(c), str)), None
    )
    value_col = next(
        (c for c in columns if isinstance(sample.get(c), (int, float))
         and not isinstance(sample.get(c), bool)
         and not c.lower().endswith("id")),
        None,
    )
    if not label_col or not value_col:
        return None
    return label_col, value_col


def fallback_chart(question: str, result: dict) -> dict | None:
    """
    Deterministic backstop: build a chart server-side from the captured rows
    when the model didn't draw one (weak models skip the chart tool). Fires in
    two cases:
      1. the user EXPLICITLY asked for a chart (keyword), or
      2. PROACTIVELY, when the result is a clearly-categorical SUMMARY — a small
         set of rows (2-15) with few columns (<=4), one text label + one number.
    Case 2 means "Show the department-wise summary" (no 'chart' word) still gets
    a chart, instead of relying on the flaky model to call show_chart itself.
    Detail listings (many rows or many columns) are left as tables, not charted.
    """
    if result.get("widgets"):
        return None  # the model already drew something
    rows = result.get("data_rows") or []
    cols = result.get("data_columns") or []
    picked = _first_label_and_value_cols(cols, rows)
    if not picked:
        return None
    asked = bool(_CHART_ASKED_RE.search(question or ""))
    # A FEW-COLUMN result (label + a measure or two) reads as a summary/breakdown
    # worth charting — a wide result is a detail listing, left as a table. No upper
    # row bound: we cap the DISPLAY to the first 25 rows below, so a long sorted
    # breakdown (e.g. ~30 departments, ORDER BY value DESC) still charts its top 25.
    proactive = (len(rows) >= 2) and (0 < len(cols) <= 4)
    if not (asked or proactive):
        return None
    label_col, value_col = picked
    use = rows[:25]  # readable cap: top 25 rows in the query's own order
    q = (question or "").lower()
    chart_type = "pie" if "pie" in q else ("line" if ("line" in q or "trend" in q) else "bar")
    try:
        code = build_chart_html({
            "chart_type": chart_type,
            "title": value_col,
            "labels": [str(r.get(label_col)) for r in use],
            "values": [float(r.get(value_col) or 0) for r in use],
            "series_label": value_col,
        })
    except Exception:
        return None
    return {"title": value_col, "code": code}


def enrich(result: dict, now: datetime | None = None, question: str = "") -> dict:
    """
    Take the backend's raw {answer, sql_used, rows_returned} and return the
    full professional response.
    """
    clean, suggestions = extract_suggestions(result.get("answer", ""))
    sql_used = result.get("sql_used", [])
    rows_returned = result.get("rows_returned", 0)
    ok = result.get("ok", True)
    data_columns = result.get("data_columns", [])
    data_rows = result.get("data_rows", [])

    # ANTI-FABRICATION GUARD (deterministic backstop): if the answer presents a
    # data table but no run_sql actually returned rows, the data is invented.
    # Replace it with an honest message and strip export/widgets/data.
    # EXCEPTION: when the user uploaded a file, the table can legitimately come
    # from that file (not the DB), so a file-grounded answer is NOT fabricated.
    # NOTE: we check `data_rows` too, not just `rows_returned`. rows_returned is
    # the LAST query's count, which a later exploratory/failed query can reset to
    # 0 even after an earlier query returned real rows — `data_rows` holds those
    # captured rows and isn't clobbered by a failing query, so a genuine answer
    # is never wrongly rejected as fabricated.
    grounded = (
        (bool(sql_used) and (rows_returned > 0 or bool(data_rows)))
        or result.get("file_grounded", False)
    )
    if not grounded and looks_like_data_table(clean):
        return {
            "answer": _UNGROUNDED_MSG,
            "suggestions": [],
            "citation": "",
            "export_query": None,
            "sql_used": sql_used,
            "rows_returned": rows_returned,
            "ok": False,
            "widgets": [],
            "data_columns": [],
            "data_rows": [],
        }

    # Drop exact-duplicate widgets (some models call show_chart twice with the
    # same data, rendering two identical charts).
    widgets = []
    seen_codes = set()
    for w in result.get("widgets", []) or []:
        key = w.get("code")
        if key in seen_codes:
            continue
        seen_codes.add(key)
        widgets.append(w)

    # Chart backstop: build one server-side if the model drew none (fires on an
    # explicit chart request OR a clearly-categorical summary — see fallback_chart).
    if ok and not widgets:
        auto = fallback_chart(question, result)
        if auto:
            widgets.append(auto)

    return {
        "answer": clean,
        "suggestions": suggestions,
        "citation": build_citation(sql_used, now),
        # Only offer export on a turn that actually succeeded — otherwise the
        # exported file would contain results the chat couldn't present.
        "export_query": export_query(sql_used) if ok else None,
        "sql_used": sql_used,
        "rows_returned": rows_returned,
        "ok": ok,
        # Inline visuals the model drew via show_widget; rendered in a sandboxed iframe.
        "widgets": widgets,
        # Exact rows behind the answer — exported as a stable snapshot (no re-run).
        "data_columns": data_columns if ok else [],
        "data_rows": data_rows if ok else [],
    }
