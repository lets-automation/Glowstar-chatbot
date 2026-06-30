"""
tools.py
--------
Shared agent logic used by BOTH LLM backends (Groq and Anthropic/Claude):
  - the rules + schema system prompt
  - the tool handlers that actually run our safe DB / artifact code

The provider-specific bits (how the LLM is called and how tool calls are
formatted) live in groq_backend.py and anthropic_backend.py.
"""

import json

from sqlalchemy import text

from app.artifacts.charts import to_chart
from app.artifacts.excel import to_excel
from app.artifacts.pdf import to_pdf
from app.database.connection import get_engine
from app.database.runner import run_select
from app.schema import extractor
from app.schema.context import build_schema_context
from app.schema.router import select_tables

# Max tool-use rounds before we force a final answer. Higher now because the
# agent may need a few steps to discover tables (find_tables -> get_columns ->
# run_sql). Simple questions still use only 1-2 rounds.
MAX_TOOL_ROUNDS = 8

# Rules the model must always follow. The schema context is added separately.
RULES = """You are a careful data analyst for a diamond-manufacturing ERP
called AasthaErp (Microsoft SQL Server). You answer employees' questions by
querying the database with the run_sql tool.

RULES:
- You may ONLY read data. Never attempt to change it.
- Use ONLY the tables and columns listed in the schema below. NEVER invent
  table or column names. If the data isn't in the schema, say you don't have it.
- This is SQL Server (T-SQL): use TOP (not LIMIT) and GETDATE() for "today".
- For big tables, prefer COUNT/SUM/GROUP BY or a small TOP - never dump
  millions of rows.
- Always call run_sql to get real numbers. Do not guess values.
- If a query errors, read the error and fix your SQL, then try again.
- EFFICIENCY (keep tool calls LOW): the schema below ALREADY lists the relevant
  tables AND their columns. In MOST cases, write ONE run_sql query directly from
  it. Do NOT call get_table_columns for a table already shown, and do NOT call
  find_tables when the data is already in a shown table. Fewer steps = faster.
- If a run_sql query succeeds and returns data, ANSWER from it - do NOT re-run
  variations of the same query.
- FALLBACK only: the database has 239 tables. If what you need is genuinely NOT
  in the shown schema (e.g. some employee/party/supplier detail not listed),
  THEN use find_tables("keyword") to locate the table and get_table_columns to
  read its columns, then query. NEVER guess table or column names.
- HONESTY: if after a reasonable search the data isn't in the database, tell the
  user plainly it is not tracked (e.g. "Sales are not recorded in this system").
  NEVER reply that you "couldn't complete" the request.
- PLACEHOLDERS / AMBIGUITY: if the question refers to a specific item by an
  obvious placeholder (e.g. "kapan X", "stone Y", "this packet", "K-123") or by
  a vague term, ASK ONE short clarifying question instead of guessing. NEVER do a
  LIKE '%X%' match on a single letter or placeholder - that returns wrong data.
- NEVER silently DROP a filter or qualifier from the question (e.g. "managers
  only", "in the cutting department", "round stones", "excluding backup"). Apply
  it with the correct column or JOIN (see the relationship hints in the data
  notes). If you truly cannot map a qualifier to the data, say so or ask - do
  NOT return an unfiltered total as if it answered the question.
- Employees may write in BROKEN ENGLISH with typos, short forms, or Hindi/
  Gujarati words. Interpret their intent generously - never refuse over
  spelling. For text searches use LIKE with % wildcards (e.g. City LIKE
  '%surat%') so small spelling/case differences still match.
- For broad questions (e.g. "company info"), find the most relevant table,
  read one row, and summarise the key details - don't get stuck searching.
- Be efficient with your steps: inspect only what you need, then ANSWER.

ANSWER FORMATTING - write like a thoughtful human analyst explaining the result to
a colleague, NEVER a raw database dump. Build a substantive answer in three beats:
- (1) INTRO - open with a short, natural framing line that sets up what you found,
  e.g. "Here's how your jangad stock is looking right now:" or "Good news on the
  workforce side -". Vary it; don't start every reply the same way.
- (2) SUBSTANCE - explain the figures in flowing sentences, using connecting and
  linking words (so, because, while, overall, in total, notably, that said,
  compared with) so it reads like a person talking you through it, not a list of
  values. **Bold** the headline numbers. Present multi-row data (counts by colour/
  city/month, top-N lists, breakdowns) as a Markdown table with clear headers:
        | Colour | Packets |
        | --- | --- |
        | F | 109 |
  Never present multi-column data as a numbered "F - 109" list, and never paste
  raw rows or "Column: value" lines as the whole reply.
- (3) CONCLUSION - close with ONE short takeaway or next step that ties it
  together, e.g. "Net-net, almost all of it is still out on jangad - want me to
  split it by party?".
- Keep it tight and warm, like a helpful colleague who knows the business. For a
  simple one-number answer a single well-phrased sentence is plenty - reserve the
  full intro/table/conclusion for richer, multi-part results. Don't pad or repeat.
- USE MARKDOWN (the chat renders it): tables for multi-row data, **bold** for key
  figures, short "- " bullet lists for a few points, a "## " heading only if the
  reply truly has sections, and `code` style for a specific code/ID/status value.
- ANALYTICS / CHARTS - when the result compares categories, breaks down by group,
  ranks a top-N, or trends over time, ALSO draw a chart with the show_widget tool
  (bar or line) - proactively, even if the user did not ask. The chart sits
  alongside your text + table; the prose still carries the explanation. Skip the
  chart for a single number or a yes/no answer.
- Numbers for people: use thousands separators (Indian numbering where natural,
  e.g. 2,45,000), round sensibly, and include the unit or currency ONLY when you
  actually know it - never invent a currency symbol. Dates as "27 Jun 2026".
- Do NOT mention SQL, raw table names, or column names (say "packets on jangad",
  not "tblJangadPackets").
- LARGE RESULTS: never dump every row. Give the headline (total/count) in a
  sentence, show the top ~10 in a table if a list is needed, and offer to narrow
  or filter.
- AMBIGUOUS MATCHES: if a name/term matches several records (e.g. several
  "Customer A" in different cities), ASK which one and list the options instead
  of guessing.
- FOLLOW-UPS: when it makes sense (NOT for greetings or errors), end your reply
  with ONE final line in EXACTLY this format:
  SUGGESTIONS: <short follow-up 1> | <short follow-up 2> | <short follow-up 3>
  Give 2-3 natural next questions the user might ask. Do not explain them.

DATES (natural language):
- Interpret relative dates in T-SQL: "today" = CAST(GETDATE() AS DATE),
  "yesterday" = the day before, plus "this/last week", "this/last month",
  "this/last year" using GETDATE() date math.
- In India a "financial year" / "FY" runs 1 April to 31 March. "Last financial
  year" = the most recently completed April-March period.
- If a date is genuinely ambiguous (timezone matters, or "the 5th" with no
  month), ask a brief clarifying question.
"""


def dynamic_schema_for(question: str) -> str:
    """
    Schema text for THIS question only: the glossary lists every table, but
    detailed columns are included only for the few tables the router picks as
    relevant. This is the key token-saving step.
    """
    relevant = select_tables(question)
    return build_schema_context(relevant)


def system_prompt_for(question: str) -> str:
    """Rules + the question-specific schema, combined (for Groq)."""
    return RULES + "\n\nDATABASE SCHEMA AND GLOSSARY:\n\n" + dynamic_schema_for(question)


def routing_text(question: str, history: list[dict] | None = None) -> str:
    """
    Text used to pick relevant tables. Includes the previous user turn so
    follow-up questions ("...and by colour?") still route correctly.
    """
    history = history or []
    prior_user = [m["content"] for m in history if m.get("role") == "user"]
    last = prior_user[-1] if prior_user else ""
    return f"{last} {question}".strip()


# ---- Tool handlers (provider-agnostic; run our safe DB/artifact code) ----
def tool_run_sql(tool_input: dict) -> tuple[str, str, int]:
    """Execute run_sql. Returns (result_text_for_model, sql, row_count)."""
    query = tool_input.get("query", "")
    result = run_select(query)

    if not result["ok"]:
        return f"ERROR: {result['error']}", result["sql"], 0

    payload = {
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": result["row_count"],
        "truncated": result["truncated"],
    }
    text = json.dumps(payload, default=str)
    if result["truncated"]:
        text += "\n(NOTE: results were capped - add filters or use aggregates.)"

    return text, result["sql"], result["row_count"]


def tool_create_report(tool_input: dict) -> tuple[str, str, int]:
    """Execute create_report. Returns (result_text_for_model, sql, row_count)."""
    query = tool_input.get("query", "")
    fmt = tool_input.get("format", "excel")
    title = tool_input.get("title", "Report")

    result = run_select(query)
    if not result["ok"]:
        return f"ERROR: {result['error']}", result["sql"], 0

    columns, rows = result["columns"], result["rows"]
    if not rows:
        return "No rows to put in the report.", result["sql"], 0

    try:
        if fmt == "pdf":
            path = to_pdf(columns, rows, "report.pdf", title=title)
        elif fmt == "chart":
            x_col = tool_input.get("x_col") or columns[0]
            y_col = tool_input.get("y_col") or columns[-1]
            path = to_chart(rows, x_col, y_col, "chart.png", title=title)
        else:  # excel
            path = to_excel(columns, rows, "report.xlsx")
    except Exception as exc:
        return f"ERROR building {fmt}: {exc}", result["sql"], result["row_count"]

    return (
        f"Created {fmt} report at: {path} ({result['row_count']} rows).",
        result["sql"],
        result["row_count"],
    )


def tool_get_table_columns(tool_input: dict) -> tuple[str, str, int]:
    """Return the columns of a specific table (so the agent never guesses)."""
    table = tool_input.get("table", "")
    if not table:
        return "ERROR: no table name given.", "", 0
    if not extractor.is_business_table(table):
        return f"ERROR: '{table}' is not an available table.", "", 0

    cols = extractor.get_columns([table]).get(table)
    if not cols:
        return f"No columns found for table '{table}'.", "", 0

    listed = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
    return f"{table} columns: {listed}", "", 0


def tool_find_tables(tool_input: dict) -> tuple[str, str, int]:
    """
    Search ALL 239 business tables for a keyword in the table name OR any
    column name. Lets the agent discover tables beyond the listed ones
    (e.g. employee/address tables) instead of giving up.
    """
    keyword = (tool_input.get("keyword") or "").strip()
    if not keyword:
        return "ERROR: no keyword given.", "", 0

    sql = text(
        """
        SELECT DISTINCT t.name
        FROM sys.tables t
        LEFT JOIN sys.columns c ON c.object_id = t.object_id
        WHERE t.name LIKE 'tbl%'
          AND (t.name LIKE :kw OR c.name LIKE :kw)
        ORDER BY t.name
        """
    )
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"kw": f"%{keyword}%"}).fetchall()

    names = [r[0] for r in rows][:40]
    if not names:
        return f"No tables found matching '{keyword}'.", "", 0
    more = " (showing first 40)" if len(rows) > 40 else ""
    return f"Tables matching '{keyword}'{more}: " + ", ".join(names), "", 0


TOOL_HANDLERS = {
    "run_sql": tool_run_sql,
    "create_report": tool_create_report,
    "get_table_columns": tool_get_table_columns,
    "find_tables": tool_find_tables,
}


def run_tool(name: str, tool_input: dict) -> tuple[str, str, int]:
    """Dispatch a tool call to its handler."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"ERROR: unknown tool '{name}'.", "", 0
    return handler(tool_input)


def friendly_status(tool_name: str) -> str:
    """A user-facing 'what's happening now' message for a tool call."""
    return {
        "run_sql": "Querying the database…",
        "find_tables": "Searching for the right data…",
        "get_table_columns": "Checking the data structure…",
        "create_report": "Building your report…",
    }.get(tool_name, "Working…")


# Tool descriptions (shared text; each backend wraps these in its own format).
TOOL_SPECS = [
    {
        "name": "run_sql",
        "description": (
            "Run a single READ-ONLY SQL Server SELECT query against AasthaErp "
            "and get the rows back. Only SELECT is allowed."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single T-SQL SELECT statement."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_report",
        "description": (
            "Generate a DOWNLOADABLE FILE (Excel, PDF, or PNG chart image) from "
            "a READ-ONLY SELECT query. Use ONLY when the user explicitly asks to "
            "export or download a report, spreadsheet, or file. Do NOT use this "
            "to show a chart on screen in the chat - for an on-screen, "
            "interactive chart or visual, call show_widget instead. For a PNG "
            "chart file, also give x_col and y_col (column names to plot)."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A T-SQL SELECT statement."},
                "format": {
                    "type": "string",
                    "enum": ["excel", "pdf", "chart"],
                    "description": "The output file type.",
                },
                "title": {"type": "string", "description": "Title for the report/chart."},
                "x_col": {"type": "string", "description": "Chart only: x-axis column."},
                "y_col": {"type": "string", "description": "Chart only: y-axis column."},
            },
            "required": ["query", "format"],
        },
    },
    {
        "name": "get_table_columns",
        "description": (
            "Get the exact column names and types of a specific table. Use "
            "this when you need the columns of a table that isn't already "
            "detailed in the schema, so you never guess column names."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "The table name, e.g. tblJunk."}
            },
            "required": ["table"],
        },
    },
    {
        "name": "find_tables",
        "description": (
            "Search ALL tables in the database for a keyword (matches table "
            "names and column names). Use this to discover tables that aren't "
            "in the listed schema BEFORE saying you don't have the data - e.g. "
            "find_tables('city') or find_tables('employee')."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Word to search for, e.g. 'city'."}
            },
            "required": ["keyword"],
        },
    },
]
