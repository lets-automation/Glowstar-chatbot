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


def _is_id_col(name: str) -> bool:
    """True for a raw internal-id column the client rule forbids showing. Matches
    the ERP's id conventions — a bare "ID", any *_ID, and CamelCase foreign keys
    ending in "ID"/"Id" (KapanID, PacketID, UserID, Emp_ID) — WITHOUT catching
    ordinary words that end in a lowercase "id" (void, paid, grid, valid)."""
    n = (name or "").strip()
    low = n.lower()
    return low == "id" or low.endswith("_id") or n.endswith("ID") or n.endswith("Id")


def sanitize_export(columns: list, rows: list) -> tuple[list, list]:
    """Drop raw internal-id columns from the export snapshot so a downloaded
    report shows names/numbers only (KapanName, PacketNo), never KapanID/PacketID/
    UserID — the client's display rule, enforced deterministically regardless of
    what SQL the model wrote. If EVERY column is an id (rare), keep the originals
    rather than export an empty file."""
    cols = list(columns) if columns else (list(rows[0].keys()) if rows else [])
    keep = [c for c in cols if not _is_id_col(c)]
    if not keep or keep == cols:
        return cols, rows
    trimmed = [{c: r.get(c) for c in keep} for r in rows]
    return keep, trimmed


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


def extract_clarify(answer: str) -> tuple[str, list[str]]:
    """
    Split a trailing 'CLARIFY: option A | option B | option C' line out of the
    answer. When the model asks a follow-up question about which interpretation
    the user meant, it lists the choices here; the UI renders them as clickable
    BUTTONS so a non-technical user just taps one instead of typing "1, 2 or 3".
    Each option is a short, self-contained phrase — tapping it sends that phrase
    back as the next question. Returns (clean_answer, [options]).
    """
    kept, options = [], []
    for line in answer.splitlines():
        if line.strip().upper().startswith("CLARIFY:"):
            payload = line.split(":", 1)[1]
            options = [s.strip() for s in payload.split("|") if s.strip()][:4]
        else:
            kept.append(line)
    return "\n".join(kept).strip(), options


def extract_askdate(answer: str) -> tuple[str, bool]:
    """
    Split a trailing 'ASKDATE:' marker out of the answer. The model emits it when a
    REPORT/date-scoped question arrives with no period ("give me the stock report"),
    instead of silently guessing a range or dumping all history. The UI then shows a
    DATE PICKER (This month / Last month / … + a custom from-to), so a non-technical
    user taps the period rather than typing it. Returns (clean_answer, asked).
    """
    kept, asked = [], False
    for line in answer.splitlines():
        if line.strip().upper().startswith("ASKDATE:"):
            asked = True
        else:
            kept.append(line)
    return "\n".join(kept).strip(), asked


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


def _is_aggregate_select(sql: str) -> bool:
    """A SELECT whose OUTPUT is a rollup (GROUP BY, or a top-level COUNT/SUM/…)."""
    u = sql.upper()
    return "GROUP BY" in u or bool(re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", u))


def export_query(sql_used: list[str]) -> str | None:
    """
    The SELECT the UI re-runs for a FULL export (used on a reopened thread, whose
    captured rows are no longer in memory).

    Prefer the DETAIL listing over a trailing COUNT/SUM/GROUP BY summary: when an
    answer LISTS rows and then runs an aggregate for its one-line summary, that
    aggregate must NOT become the export - otherwise the download silently shrinks
    to a single summary row, breaking the "full list available to download"
    promise. Fall back to the last SELECT only when EVERY query is an aggregate (a
    genuine summary/GROUP-BY answer, where the aggregate IS the data to export).
    """
    selects = [s for s in sql_used if s.strip().upper().startswith(("SELECT", "WITH"))]
    if not selects:
        return None
    non_aggregate = [s for s in selects if not _is_aggregate_select(s)]
    return (non_aggregate or selects)[-1]


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
    # Label the slice honestly: a chart of 25 of 60 categories presented as
    # "the data" is a silent sample - say "first 25 of 60" in the title.
    title = value_col if len(rows) <= 25 else f"{value_col} (first 25 of {len(rows)})"
    q = (question or "").lower()
    chart_type = "pie" if "pie" in q else ("line" if ("line" in q or "trend" in q) else "bar")
    try:
        code = build_chart_html({
            "chart_type": chart_type,
            "title": title,
            "labels": [str(r.get(label_col)) for r in use],
            "values": [float(r.get(value_col) or 0) for r in use],
            "series_label": value_col,
        })
    except Exception:
        return None
    return {"title": title, "code": code, "kind": "chart"}


_TABLE_PREVIEW_ROWS = 50


def _rows_to_markdown(columns: list, rows: list, limit: int = _TABLE_PREVIEW_ROWS) -> str:
    """Render captured rows as a Markdown table (the exact rows the query returned)."""
    if not columns or not rows:
        return ""
    head = f"| {' | '.join(str(c) for c in columns)} |"
    sep = f"|{'|'.join('---' for _ in columns)}|"
    body = [
        "| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in columns) + " |"
        for r in rows[:limit]
    ]
    out = "\n".join([head, sep, *body])
    if len(rows) > limit:
        out += f"\n\n_Showing {limit} of {len(rows)} rows — the export has every row._"
    return out


def ensure_data_shown(answer: str, columns: list, rows: list, has_visual: bool) -> str:
    """
    DETERMINISTIC anti-thin-answer backstop.

    The model is not consistent: the same report question renders a full table on
    one run and, on the next, only a sentence ABOUT the data ("the makers listed
    above...") or nothing at all — which is what reaches the client as a failure.
    Whenever a query returned rows and the prose contains no table (and no chart
    is carrying the data), append the real rows. The data is already in hand, so
    this never invents anything - it just guarantees the user SEES it.
    """
    # NOTE: a plain CHART does not count as showing the data — the user cannot read
    # numbers off it (chart = extra, table = the answer). Only a DASHBOARD, which
    # carries its own tables, suppresses this.
    if not rows or has_visual or looks_like_data_table(answer):
        return answer
    table = _rows_to_markdown(columns, rows)
    if not table:
        return answer
    prose = (answer or "").strip()
    lead = prose if prose else "Here are the results:"
    return f"{lead}\n\n{table}"


def enrich(result: dict, now: datetime | None = None, question: str = "") -> dict:
    """
    Take the backend's raw {answer, sql_used, rows_returned} and return the
    full professional response.
    """
    clean, suggestions = extract_suggestions(result.get("answer", ""))
    # Clarify-buttons: a trailing 'CLARIFY: a | b | c' line becomes clickable
    # option buttons in the UI (so a non-dev user taps a choice instead of typing).
    clean, clarify_options = extract_clarify(clean)
    # Date picker: an 'ASKDATE:' marker asks the UI to show the period chooser.
    clean, ask_date = extract_askdate(clean)
    sql_used = result.get("sql_used", [])
    rows_returned = result.get("rows_returned", 0)
    ok = result.get("ok", True)
    data_columns = result.get("data_columns", [])
    data_rows = result.get("data_rows", [])

    # BLANK REPLY GUARD. A model can stop with no text at all - a provider blip,
    # a round that returned nothing. The backend's in-loop return passes that
    # straight through, so the user gets an EMPTY chat bubble with ok=True, and
    # the UI offers an export button next to it.
    #
    # Observed live: the same "full report of MFG - 1" question answered fully
    # (2 queries, 317 rows) on one run and returned nothing at all on the next.
    #
    # The wording matters as much as the guard. This must NEVER be reported as
    # "I don't have that information in the database" - that is a FALSE DENIAL,
    # telling the client their data is missing when the truth is that our model
    # call produced nothing. Say what actually happened.
    if not clean.strip():
        if data_rows:
            # The queries DID succeed; only the write-up is missing. Keep ok=True
            # so the rows still render and stay exportable.
            clean = "I fetched the data but couldn't write the summary just now - here it is."
        else:
            clean = (
                "I couldn't complete that just now - please ask again. "
                "If it keeps happening, try rephrasing the question."
            )
            ok = False  # nothing real to show: the UI must not offer an export

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
    # A chart or dashboard presents NUMBERS just like a table does, so a data
    # visual with no run_sql (and no grounding file) behind it is exactly as
    # fabricated as a bare invented table - catch both. (A plain show_widget
    # visual, kind='widget', may legitimately need no DB data, so it isn't a
    # trigger; but it's still stripped in the ungrounded branch below.)
    data_visual = any(
        (w or {}).get("kind") in ("chart", "dashboard")
        for w in (result.get("widgets") or [])
    )
    if not grounded and (looks_like_data_table(clean) or data_visual):
        return {
            "answer": _UNGROUNDED_MSG,
            "suggestions": [],
            "clarify_options": [],
            "ask_date": False,
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

    # Strip raw internal ids from the export snapshot (client display rule) — the
    # download shows KapanName/PacketNo, never KapanID/PacketID/UserID. Only on a
    # successful turn; a failed/ungrounded turn exports nothing.
    export_columns, export_rows = sanitize_export(data_columns, data_rows) if ok else ([], [])

    # Guarantee the user SEES the data. The model intermittently writes prose about
    # a table it never printed (or nothing at all) — on those runs we render the
    # captured rows ourselves so a correct query can never reach the client as a
    # thin answer.
    #
    # Deliberately NOT gated on `ok`: a turn that failed at the write-up step (a
    # provider hiccup AFTER the query succeeded) is exactly when the user is most
    # likely to see prose with no numbers. The rows are real — they came from a
    # successful run_sql in this turn, and the anti-fabrication guard above has
    # already rejected ungrounded answers — so showing them is honest either way.
    shown_columns, shown_rows = sanitize_export(data_columns, data_rows)

    # A "most/highest/top" claim must name the FIRST row of the ordered result.
    # On unseen questions the model has reported the ranking backwards while the
    # table beside it was right — and the client reads the sentence. We can't
    # rewrite prose safely, so we LOG it (grep: SUPERLATIVE-MISMATCH) and let the
    # rendered table carry the truth.
    _mismatch = superlative_mismatch(clean, shown_columns, shown_rows)
    if _mismatch:
        from app.core.logging_util import logger
        logger.warning(
            "SUPERLATIVE-MISMATCH | answer says %r but the top row is %r | q=%r",
            _mismatch[0], _mismatch[1], (question or "")[:100],
        )

    # COUNT CONSISTENCY (LOG ONLY, tier 1): does a prose row-count claim match the
    # data returned? Same family as superlative_mismatch. No user-visible action
    # yet - we measure the real hit rate from the log first, exactly how the
    # superlative guard earned its place. Reads the model's prose only, so it runs
    # before the banner/table are added below. Grep: COUNT-MISMATCH
    if ok:
        from app.agent import count_guard

        _cm = count_guard.count_mismatch(
            clean, shown_rows, rows_returned, question, sql_used,
            file_grounded=bool(result.get("file_grounded")),
        )
        if _cm:
            from app.core.logging_util import logger

            logger.warning(
                "COUNT-MISMATCH | answer claims %s %s but the data gives %s rows | q=%r",
                _cm[0], _cm[1], len(shown_rows), (question or "")[:100],
            )

    # SCOPE CHECK (runs BEFORE the dimension guard and takes precedence over it:
    # a wrong-scope number beats a missing column). The user named a period but no
    # query constrained a date, so every figure shown is all-time. We cannot fix
    # the SQL from here, so we WARN ABOVE the table - a banner under 50 rows is
    # never read - and offer a one-tap re-ask. Rows are left untouched: they are
    # real, and destroying a correct answer on a false positive is the worse bug.
    _period_flagged = False
    if ok:
        from app.agent import period_guard

        if period_guard.unfiltered_period(question, sql_used, shown_rows):
            _period = period_guard.period_phrase(question)
            from app.core.logging_util import logger

            logger.warning("PERIOD-UNFILTERED | period=%r | q=%r", _period,
                           (question or "")[:100])
            clean = period_guard.scope_banner(_period) + "\n\n" + clean
            clarify_options = [period_guard.followup_option(_period)]
            _period_flagged = True

    # ANSWER COMPLETENESS: the user asked to break the data down by something
    # (employee, department, kapan, day...) but that column isn't in the result —
    # e.g. "GIA results of Fency department EMPLOYEES" returned a correct packet
    # table with the maker used only as a FILTER. Offer it as a one-tap follow-up
    # rather than leaving the question half-answered. Logged so we can see whether
    # it helps or nags (grep: DIMENSION-MISSING).
    if ok and not clarify_options and not _period_flagged:
        from app.agent import dimension_guard

        _missing = dimension_guard.missing_dimensions(question, shown_columns, shown_rows)
        if _missing:
            from app.core.logging_util import logger

            logger.warning("DIMENSION-MISSING | %s | q=%r", ",".join(_missing),
                           (question or "")[:100])
            clarify_options = [dimension_guard.followup_option(d) for d in _missing[:2]]

    # PERSON COLUMN SHOWING CODES: the answer has a maker/worker column, but it
    # is printing "M1332" / "Y111" / "CL403" instead of a name. EmpName is the
    # CODE on ~99% of tblPacketIssue and tblPointRateLabour rows (and ~12% of
    # tblPlanMaster), so this is a whole-factory trap, not one department's.
    # The fix is always to resolve EmpId -> tblEmployee. Offer that as a one-tap
    # follow-up. Logged so we can measure it (grep: NAME-AS-CODE).
    if ok and not clarify_options and not _period_flagged:
        from app.agent import name_guard

        _coded = name_guard.code_columns(shown_columns, shown_rows)
        if _coded:
            from app.core.logging_util import logger

            logger.warning("NAME-AS-CODE | %s | q=%r", ",".join(_coded),
                           (question or "")[:100])
            clarify_options = [name_guard.followup_option(c) for c in _coded[:2]]

    clean = ensure_data_shown(
        clean,
        shown_columns,
        shown_rows,
        has_visual=any((w or {}).get("kind") == "dashboard" for w in widgets),
    )

    return {
        "answer": clean,
        "suggestions": suggestions,
        "clarify_options": clarify_options,
        "ask_date": ask_date,
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
        "data_columns": export_columns,
        "data_rows": export_rows,
        # EVERY query result from this turn, one per section, so a multi-part
        # report exports as a multi-sheet workbook. Without this the download
        # carried only the single biggest result: the client asked for a full
        # report, saw production + damage + bonus + GIA in the chat, and got an
        # Excel file containing production alone.
        "data_sections": result.get("data_sections") or [],
    }


# --- superlative claim vs the actual data ------------------------------------
# On an UNSEEN question the model can report the ranking backwards while the
# table beside it is correct ("the most common colour is F" when G leads
# 34,078 to 28,405). The client reads the sentence, not the table. We cannot
# verify prose in general, but a "most/highest/top" claim IS checkable: it must
# name the FIRST row of the ordered result.
_SUPERLATIVE_RE = re.compile(
    r"\b(most common|most|highest|largest|biggest|top|leading|best)\b[^.\n]{0,60}?"
    r"(?:\bis\b|\bwas\b|:)\s*\**\s*([A-Za-z0-9][\w .&/-]{0,40}?)\s*\**",
    re.IGNORECASE,
)


def _first_text_value(columns: list, rows: list) -> str | None:
    """The label of the top row — what a superlative claim must name."""
    if not rows or not columns:
        return None
    for c in columns:
        v = rows[0].get(c)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def superlative_mismatch(answer: str, columns: list, rows: list) -> tuple[str, str] | None:
    """
    Return (claimed, actual_top) when the answer's superlative names something
    OTHER than the top row, and the claimed value appears LOWER in the same
    result. Returns None when there is no claim, no data, or no conflict.

    Deliberately conservative: it only fires when the claimed value is itself
    present in the data (so it is a ranking error, not a different measure).
    """
    top = _first_text_value(columns, rows)
    if not top or len(rows) < 2:
        return None
    m = _SUPERLATIVE_RE.search(answer or "")
    if not m:
        return None
    claimed = (m.group(2) or "").strip().strip(".,:")
    if not claimed or claimed.lower() == top.lower():
        return None
    others = {
        str(r.get(c)).strip().lower()
        for r in rows[1:] for c in columns
        if isinstance(r.get(c), str)
    }
    return (claimed, top) if claimed.lower() in others else None
