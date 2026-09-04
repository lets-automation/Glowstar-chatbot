"""
postprocess.py
--------------
Turns the agent's raw answer into a richer, professional response:
  - pulls out follow-up SUGGESTIONS the model appended
  - builds a CITATION (source tables + retrieval time) from the SQL it ran
  - finds the EXPORT query (last SELECT) so the UI can offer Excel/PDF export

All of this is deterministic (no extra LLM calls -> no extra tokens).
"""

import json
import re
from datetime import datetime

from app.agent import facts
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


# "|:---|---:|---:|" - alignment/separator only, no data in it.
_MD_SEPARATOR_ROW = re.compile(r"^\s*\|[\s:|-]*\|?\s*$")


def looks_like_data_table(answer: str) -> bool:
    """True if the answer contains a Markdown table with ACTUAL ROWS in it.

    Separator rows do not count. Since the model was told to stop rendering the
    data table, it sometimes still emits the skeleton - a lone "|:---|---:|" line
    under "Here's the breakdown by kapan:" - and counting those as a table made
    ensure_data_shown suppress the real one, so the client got a heading, an
    empty rule, and no data at all. Seen live on 2026-08-24.
    """
    rows = [r for r in _MD_TABLE_ROW.findall(answer or "")
            if not _MD_SEPARATOR_ROW.match(r)]
    return len(rows) >= 2


# A FIGURE ASSERTED IN PROSE IS AS FABRICATED AS ONE IN A TABLE.
#
# The anti-fabrication guard below only fired on a Markdown table, so an answer
# that stated its numbers in a sentence walked straight through.
#
# Caught live 2026-08-31 on Qwen3-30B-A3B, asked "how many oval diamonds do we
# have in stock?":
#     "Total oval diamonds in stock: 7,321 packets
#      Total weight: 1,845.67 carats"
# NO query ran at all (sql_used == []). 7,321 is not a coincidence - it is the
# worked example inside the glossary's shape-normalisation note, measured on an
# OLDER restore. The live answer is 7,591. The model read the number out of its
# own prompt and presented it as data, and the weight was invented outright.
#
# The weaker test model queried the database and got it right, so this failure
# gets MORE likely as the model gets better: a capable model trusts a confident
# prompt over a tool call. That is why it has to be caught in code.
#
# Deliberately narrow - a comma-grouped number, or a number wearing a data unit.
# A clarification ("nine people share this name"), a refusal, or a period
# question carries no such figure, and any answer that DID run a query is
# already grounded and never reaches this check.
_FIGURE_RE = re.compile(
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s*\**\s*(?:\w+\s+){0,2}(?:packets?|carats?|cts?|ct|pcs|pieces?|stones?|"
    r"diamonds?|employees?|workers?|karigars?|kapans?|rows?|records?|nang)\b",
    re.IGNORECASE,
)


def asserts_a_figure(answer: str) -> bool:
    """True if the answer states a data quantity in prose."""
    return bool(_FIGURE_RE.search(answer or ""))


def strip_empty_tables(answer: str) -> str:
    """Drop orphan separator lines left behind by a half-written table."""
    lines = (answer or "").split("\n")
    keep, n = [], len(lines)
    for i, line in enumerate(lines):
        if _MD_SEPARATOR_ROW.match(line) and line.strip():
            prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j].strip()), "")
            nxt = next((lines[j] for j in range(i + 1, n) if lines[j].strip()), "")
            has_neighbour_row = any(
                _MD_TABLE_ROW.match(x) and not _MD_SEPARATOR_ROW.match(x)
                for x in (prev, nxt)
            )
            if not has_neighbour_row:
                continue
        keep.append(line)
    return "\n".join(keep)


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


# show_chart's own payload shape, narrated instead of called (weak-model
# failure mode: same family as loop_policy.looks_like_unrun_sql, but for
# charts the fix is free instead of costing a corrective round-trip - the
# JSON the model wrote IS the tool call, just never sent, so it can be
# rendered directly.
_CHART_TYPES = {"bar", "horizontal_bar", "line", "pie"}
# A fenced ```json {...}``` block, OR a bare {...} sitting in the prose
# (models don't always bother with the fence). Objects here are flat -
# "labels"/"values" are arrays, not nested objects - so a no-inner-brace
# match is enough to capture one without a full JSON parser.
_FENCED_CHART_JSON_RE = re.compile(r"```(?:json)?\s*\n?(\{[^`]*?\})\s*```", re.DOTALL)
_BARE_CHART_JSON_RE = re.compile(r"\{[^{}]*\"chart_type\"[^{}]*\}", re.DOTALL)


def _narrated_chart_widget(blob: str) -> dict | None:
    """Parse one candidate JSON blob; return a real chart widget or None."""
    try:
        payload = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("chart_type") not in _CHART_TYPES:
        return None
    if not isinstance(payload.get("labels"), list) or not isinstance(payload.get("values"), list):
        return None
    try:
        code = build_chart_html(payload)
    except Exception:
        return None
    return {"title": str(payload.get("title") or ""), "code": code, "kind": "chart"}


def extract_narrated_charts(answer: str) -> tuple[str, list[dict]]:
    """
    Recover show_chart-shaped JSON the model printed as prose instead of
    actually calling the tool, and cut the raw JSON out of the visible text.

    Some models (seen on newly-added candidates during provider bakeoffs)
    narrate the call the same way llama-4-scout used to narrate run_sql: they
    write the exact tool payload as a fenced code block instead of invoking
    show_chart, so the user sees a literal {"chart_type": "bar", ...} card
    instead of a picture. The data in it is real (the model meant to draw
    it), so recover it deterministically rather than just flagging it.
    """
    if not answer or "chart_type" not in answer:
        return answer, []
    widgets: list[dict] = []

    def _sub(pattern: re.Pattern) -> None:
        nonlocal answer
        def repl(m: re.Match) -> str:
            w = _narrated_chart_widget(m.group(1) if m.groups() else m.group(0))
            if w is None:
                return m.group(0)
            widgets.append(w)
            return ""
        answer = pattern.sub(repl, answer)

    _sub(_FENCED_CHART_JSON_RE)
    _sub(_BARE_CHART_JSON_RE)
    clean = re.sub(r"\n{3,}", "\n\n", answer).strip()
    return clean, widgets


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


# Reasoning-mode models (Qwen3.x, DeepSeek-R1 and friends) emit their private
# deliberation before the real answer. vLLM only strips it when the server was
# started with a matching --reasoning-parser; without that flag the whole
# monologue arrives as ordinary content and is shown to the user.
#
# Measured on the 2026-08-18 GPU bakeoff: 18 of 26 answers from Qwen3.5-9B
# leaked reasoning, and one of them printed the ENTIRE SCOPE ruleset back to
# the user verbatim - the system prompt, including which columns are blocked.
# That is an IP leak, not a cosmetic defect.
#
# Stripping here rather than relying on the serving flag is deliberate: this
# runs for EVERY backend and every provider, so a model swap or a forgotten
# server flag cannot re-expose the prompt.
#
# It must also run BEFORE extract_suggestions/extract_clarify/extract_askdate.
# A model reasoning about its own output writes things like "I should use the
# ASKDATE: marker here" INSIDE the monologue; those extractors would match that
# sentence instead of the real marker, which is why the date picker failed to
# render even though the model emitted ASKDATE: correctly.
_THINK_PAIR_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think\s*>", re.IGNORECASE)


def strip_reasoning(answer: str) -> str:
    """Remove chain-of-thought so it never reaches the user.

    Handles both shapes seen in the wild: a well-formed <think>...</think> pair,
    and the far more common one where the opening tag was consumed by the chat
    template so the reply is bare monologue terminated by </think>.

    NEVER returns empty for a non-empty input - if the whole reply was
    reasoning, the original text is kept. A blank bubble is worse than a leak,
    and postprocess already has a separate guard for genuinely empty replies.
    """
    if not answer or "think" not in answer.lower():
        return answer
    cleaned = _THINK_PAIR_RE.sub("", answer)
    # Unpaired close tag: everything up to the LAST one is monologue.
    matches = list(_THINK_CLOSE_RE.finditer(cleaned))
    if matches:
        cleaned = cleaned[matches[-1].end():]
    cleaned = cleaned.strip()
    return cleaned or answer


def enrich(result: dict, now: datetime | None = None, question: str = "") -> dict:
    """
    Take the backend's raw {answer, sql_used, rows_returned} and return the
    full professional response.
    """
    # Strip chain-of-thought FIRST - see strip_reasoning(). The marker
    # extractors below must never see the model's monologue.
    clean, suggestions = extract_suggestions(strip_reasoning(result.get("answer", "")))
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

    # NARRATED CHART GUARD: recover show_chart JSON the model printed as text
    # instead of calling the tool (see extract_narrated_charts) BEFORE the
    # grounding check below, so an ungrounded narrated chart is still treated
    # as a data visual and caught like any other fabricated one.
    clean, _narrated = extract_narrated_charts(clean)
    if _narrated:
        result = dict(result, widgets=[*(result.get("widgets") or []), *_narrated])

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
    if not grounded and (looks_like_data_table(clean) or data_visual
                         or asserts_a_figure(clean)):
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
            # Every query's rows, not just the captured winner - see count_guard.
            sections=result.get("data_sections") or [],
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
    # STATE THE SCOPE OF A NARROWED REPORT, whoever chose the filter.
    #
    # These answers are taken OUT of the chat and sent to the client to check
    # against their own ERP, so an answer that cannot state its own scope cannot
    # be verified by the person reading it. A live Fency report opened "Overall,
    # 1,643 packets across 27 kapans" - correct for Fency, but the word "Fency"
    # was nowhere in the prose. Runs before the period banner: a subset read as
    # the whole company is the bigger misstatement.
    if ok:
        from app.agent import reports as _reports

        _scope = _reports.scope_line(question, sql_used)
        if _scope:
            from app.core.logging_util import logger

            logger.warning("UNDISCLOSED-SCOPE | %s | q=%r",
                           _scope[:80], (question or "")[:100])
            clean = _scope + "\n\n" + clean

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

        # A MULTI-SECTION RECIPE ANSWERS THE BREAKDOWN IN A SECTION, NOT IN
        # the top-level columns - those are only the widest single result. The
        # lab-results recipe returns a "By employee" section of 15 rows, and
        # asking "GIA results EMPLOYEE WISE" still offered "show it by
        # employee" as a follow-up because the guard never saw it. Every
        # section's columns count as shown.
        _sec_cols = list(shown_columns or [])
        for _sec in (result.get("data_sections") or []):
            _sec_cols.extend(_sec.get("columns") or [])
        _missing = dimension_guard.missing_dimensions(question, _sec_cols, shown_rows)
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

    # A CARAT FIGURE THAT NO WEIGHT COLUMN PRODUCED.
    # Seen live 2026-08-31: "OQ26 has 6,107.39 points ... and a total of
    # 6,107.39 carats polished" - the same number twice, under two units. The
    # points half was right; the carat half was that number re-labelled, where
    # the true weight is 378.458. query_rules.weight_via_points_join had
    # correctly refused the one query that computes both, and the model
    # labelled what it had rather than running the second query.
    #
    # Warned ABOVE the answer rather than rewritten: the points figure is real
    # and destroying a half-correct answer on a false positive is the worse
    # bug - the same trade the period banner makes. (grep: UNSOURCED-CARAT)
    if ok:
        from app.agent import unit_guard

        _bad_ct = unit_guard.unsourced_carat_claim(clean, shown_columns, shown_rows)
        if _bad_ct:
            from app.core.logging_util import logger

            logger.warning("UNSOURCED-CARAT | %s stated as carats with no "
                           "weight column | q=%r", _bad_ct, (question or "")[:100])
            clean = unit_guard.caution(_bad_ct) + "\n\n" + clean
            if not clarify_options:
                clarify_options = [unit_guard.followup_option()]

    # THE NUMBERS COME FROM THE DATA, NOT THE MODEL. The model is shown only a
    # preview (MODEL_ROW_LIMIT rows), so any total it works out itself is
    # addition over rows it never saw: the 2026-08-24 client demo announced
    # "2,403 packets" for a result that totalled 3,227, and a second provider
    # said 8,653. These facts are derived from the COMPLETE captured result.
    _facts = facts.compute("\n".join(sql_used or []), shown_columns,
                           shown_rows, truncated=bool(result.get("truncated")))

    # Correct an explicit total the model stated anyway, BEFORE the table is
    # appended - prose and table disagreeing is what the client actually saw.
    clean, _fixed = facts.correct_total_claims(clean, _facts, question or "")
    if _fixed:
        from app.core.logging_util import logger

        for _claimed, _actual in _fixed:
            logger.warning("TOTAL-CORRECTED | model said %s, data says %s | q=%r",
                           _claimed, _actual, (question or "")[:100])

    clean = strip_empty_tables(clean)
    clean = ensure_data_shown(
        clean,
        shown_columns,
        shown_rows,
        has_visual=any((w or {}).get("kind") == "dashboard" for w in widgets),
    )
    clean += facts.totals_line(_facts)

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
