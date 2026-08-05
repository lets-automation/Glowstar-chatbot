"""
loop_policy.py
--------------
Provider-agnostic POLICY for the agent's tool loop: when to push a stalled model
to actually run its query, when an answer is ungrounded, when a "report" came
back as a summary instead of the detail rows.

WHY THIS MODULE EXISTS
----------------------
All of this used to live in groq_backend.py, which made that file two things at
once: the Groq provider AND the shared agent library. The other backends had to
reach into it -

    # anthropic_backend.py
    from app.agent.groq_backend import (
        DASHBOARD_ASKED_RE, DASHBOARD_NUDGE, REPORT_ASKED_RE, REPORT_DETAIL_NUDGE,
        _EXECUTE_NUDGE, _all_sql_aggregated, _MAX_EXECUTE_NUDGES,
        _SUMMARY_INTENT_RE, _has_data_visual, _looks_like_unrun_sql,
    )

- importing six PRIVATE names across module boundaries, and gemini_backend did
the same with function-local imports to dodge a circular import. The practical
cost: to change how a stalled model is nudged you first had to know the logic
lived in the Groq file, and a change there silently altered all three providers.

Nothing here is Groq-specific, so it belongs in one neutral place that every
backend imports. Names are public: they are this module's API, and a leading
underscore on something three other modules import is a lie about its scope.

Policy only - no provider clients, no I/O, no state. That keeps it trivially
testable and keeps the dependency arrow pointing one way (backends -> policy).
"""
from __future__ import annotations

import re

# How many times, in ONE turn, we force a stalled model to actually run its
# query before giving up. Weak models (e.g. llama-4-scout) sometimes ignore the
# first push, so we allow a second.
MAX_EXECUTE_NUDGES = 2

# NOTE: the per-call output budget deliberately does NOT live here. It is a
# per-provider number, not shared policy - Claude uses 4096 while the free-tier
# providers use settings.LLM_MAX_TOKENS to stay inside a tokens-per-minute cap.
# Hoisting it would have quietly given one provider another's budget.

# Shown to the model when it presents data (a table, figures, or written-out
# SQL) without having called run_sql. Generalises the old "you wrote SQL" nudge
# so it ALSO catches a fabricated Markdown table that contains no literal SELECT
# — the exact failure that let "packet report for kapan AA" fall through to the
# canned refusal.
EXECUTE_NUDGE = (
    "You presented data (a table, figures, or a query) but you did NOT call "
    "run_sql, so nothing you showed is real. You MUST call the run_sql tool "
    "NOW to fetch the actual rows from the database, then answer ONLY from the "
    "rows it returns. If you already wrote a SQL query, run that EXACT query "
    "(do not rewrite or simplify it). Never put a data table, chart, or numbers "
    "in your reply without running run_sql first. If the query genuinely "
    "returns no rows, say so plainly."
)

# The user asked for an analytics dashboard/overview. Weak models often answer
# such questions in plain text and skip the show_dashboard tool entirely; when
# this matches and no dashboard was built, we nudge one corrective round.
DASHBOARD_ASKED_RE = re.compile(
    r"\b(dashboards?|analytics?|overview|analysis|analyse|analyze)\b", re.IGNORECASE
)

DASHBOARD_NUDGE = (
    "The user asked for an analytics view, but you have not called the "
    "show_dashboard tool, so they see no dashboard. Do it NOW: if you need "
    "more figures, run 1-3 more quick aggregate run_sql queries (e.g. a "
    "monthly trend, a breakdown by department/category); then call "
    "show_dashboard ONCE with 3-6 KPI tiles and 1-2 sections built ONLY from "
    "numbers your run_sql queries actually returned. Then give a short text "
    "summary."
)

# REPORT = DETAIL ROWS guard (client-flagged bug): the user asked for a
# "report" but the model answered with a GROUP BY aggregate ("Top 10 kapans by
# damage count") instead of the detail listing with joined names the rules
# mandate. Prompt rules alone did not stop weak models, so this is enforced
# deterministically: report-intent question + aggregated final query -> one
# corrective round. Summary-intent words exempt (an explicitly-asked summary
# may aggregate).
REPORT_ASKED_RE = re.compile(r"\breports?\b", re.IGNORECASE)
SUMMARY_INTENT_RE = re.compile(
    r"\b(summar(y|ies|ise|ize)|total|count|how many|average|avg|trend|"
    r"overview|analytics?|dashboards?|charts?|graphs?)\b",
    re.IGNORECASE,
)

REPORT_DETAIL_NUDGE = (
    "The user asked for a REPORT. In this system a report ALWAYS means the "
    "DETAIL listing - one row per record - NEVER a GROUP BY summary, and never "
    "a 'Top N' ranking they didn't ask for. Your last query AGGREGATED. Re-run "
    "ONE corrected query that lists the individual records with human-readable "
    "columns: JOIN tblEmployee on the numeric emp id for EmployeeName + "
    "DepartMentName where the table has one; show KapanName and PacketNo, "
    "never raw IDs. 'X wise' means ORDER BY that column (kapan wise = ORDER BY "
    "KapanName), NOT GROUP BY. Then present the first ~30 rows as a Markdown "
    "table and tell the user the full data is in the Excel/PDF download. "
    "Aggregate ONLY if the user explicitly asked for totals or a summary."
)


def looks_like_unrun_sql(text: str) -> bool:
    """True if the reply EMBEDS a SELECT query — i.e. the model wrote the SQL in
    its answer instead of calling the run_sql tool. Some models (notably
    llama-4-scout) do this on list/ranking questions, so no query runs and the
    user sees no data. Detecting it lets us force an actual execution."""
    if not text:
        return False
    low = text.lower()
    return "select" in low and "from" in low


def all_sql_aggregated(sql_used: list[str]) -> bool:
    """True if EVERY executed query was a GROUP BY aggregate - i.e. the model
    never pulled the detail rows at all. (Checking only the LAST query would
    false-positive on the good pattern 'detail query, then a small total for
    the headline'.)"""
    return bool(sql_used) and all("group by" in s.lower() for s in sql_used)


def has_data_visual(widgets: list[dict]) -> bool:
    """True if a chart/dashboard was emitted — it presents numbers like a table,
    so an ungrounded one is as fabricated as an invented table."""
    return any((w or {}).get("kind") in ("chart", "dashboard") for w in widgets or [])
