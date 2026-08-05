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


# THIN ENTITY REPORT: "report of <entity>" answered with only the WHO row.
#
# The rules already spell out that a report of a named thing (an employee, a
# kapan, a department) means the ERP's all-round profile - who they are, then
# production, processes, damage, bonus - each its own section. Weak models run
# section 1 and stop, so the client asked for a full report of employee M4167
# and got a one-row identity record: name, code, department. The Excel download
# was that single row, which is what they saw as the report.
#
# Prompt text alone did not hold, so this is checked in code, once per turn.
ENTITY_REPORT_NUDGE = (
    "That is NOT the full report the user asked for. You have only identified "
    "WHO/WHAT they named - that is section 1 of several. A report of a named "
    "employee, kapan, department or party means their ALL-ROUND profile, the "
    "same one their ERP prints. Run ONE query per remaining section NOW, using "
    "the id you just resolved: what they PRODUCED (packets and weight), which "
    "PROCESSES they handled, any DAMAGE/repair, and their BONUS/INCENTIVE "
    "points. Skip a section only if the schema genuinely has no such data for "
    "this kind of entity. Then answer with each section as its own small titled "
    "block, led by a 1-2 line summary. Never present the identity row alone as "
    "the report."
)


def thin_entity_report(question: str, sections: list[dict]) -> bool:
    """
    True when a REPORT question came back with essentially one small result.

    Deliberately crude: one section holding a couple of rows is not a profile,
    whatever the entity was. It cannot know which sections a given entity
    supports - that depends on the schema and is the model's job - so it only
    detects that far too little came back.
    """
    q = question or ""
    if not REPORT_ASKED_RE.search(q) or SUMMARY_INTENT_RE.search(q):
        return False
    usable = [s for s in (sections or []) if s.get("rows")]
    if len(usable) > 1:
        return False
    return sum(len(s["rows"]) for s in usable) <= 2


# The final "stop calling tools and write the answer" instruction.
#
# It MUST re-state the SUGGESTIONS contract. The rules block asks every answer to
# end with a `SUGGESTIONS: a | b | c` line, which postprocess turns into the
# follow-up buttons - but this write-up call is a fresh instruction at the end of
# a long conversation, and models follow the last thing they were told. All three
# backends omitted it, so every answer that came through this path (which is most
# of them now) silently lost its follow-ups. Reported by the client: "it doesn't
# give follow up question like if they want any other report".
WRITE_UP_PROMPT = (
    "Give your best final answer now in plain text, based on what you found. "
    "If you could NOT find the requested data, tell the user plainly that this "
    "information is not tracked in the system (e.g. 'Sales are not recorded in "
    "this system'). Do NOT say you couldn't complete the request.\n\n"
    "You MUST end your reply with one line of follow-ups, exactly in this form:\n"
    "SUGGESTIONS: <short follow-up 1> | <short follow-up 2> | <short follow-up 3>\n"
    "Make them the natural NEXT questions for what you just showed - a different "
    "period, a breakdown by employee/kapan/department, or a related report the "
    "same data supports. Keep each under about 8 words."
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
