"""
date_gate.py
------------
DETERMINISTIC "which period?" check for report questions.

The client asked that any report/date-related question prompt for a date range
instead of silently answering. A prompt RULE alone is not reliable — the model
answered "give me the damage report of department MFG - 1" with all 484 records
spanning two years. So this gate decides in CODE, before any LLM call:

    report-style question  AND  no period mentioned   ->  ask for the date

Being deterministic also makes it instant and free (no tokens burned), and it
can't regress when a provider changes.

Deliberately conservative: it only fires when the question clearly asks for a
REPORT/listing AND carries no hint of a time period, so ordinary questions
("how many employees do we have", "what is a kapan") flow straight through.
"""
from __future__ import annotations

import re

# Question is asking for a report / listing over some period. Includes the
# Gujlish words the client's staff actually type.
_REPORT_RE = re.compile(
    r"\b("
    r"report|production|output|stock|damage|jangad|earning|earnings|salary|wages|"
    r"incentive|bonus|result|results|certification|gia|hrd|igi|yield|loss|"
    r"repair|rejection|attendance|summary|breakdown|performance|"
    r"utpadan|nuksan|pagar|hisab"          # Gujlish: production/loss/pay/accounts
    r")\b",
    re.IGNORECASE,
)

# "-wise" style asks (kapan wise, employee wise, department wise) are reports too.
_WISE_RE = re.compile(r"\b\w+[\s-]?wise\b", re.IGNORECASE)

# Any hint of a time period. If ANY of these appear we do NOT ask.
_PERIOD_RE = re.compile(
    r"("
    # Month names — spelled out in full or as the standard abbreviation. NOT a
    # loose prefix: "jan[a-z]*" also matched "JANgad" (the trade term) and
    # suppressed the date prompt on every jangad report.
    r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july"
    r"|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b"
    r"|\b(19|20)\d{2}\b"                                            # a year
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"                               # 01/06/2026
    r"|\d{4}-\d{2}-\d{2}"                                           # 2026-06-01
    r"|\b(to|from|between|since|till|until|upto|up to)\b.*\d"       # from 1 to 26
    r"|\btoday|yesterday|tomorrow\b"
    r"|\b(this|last|past|previous|current|next)\s+"
    r"(month|week|year|quarter|day|days|months|weeks|years|fortnight)\b"
    r"|\blast\s+\d+\s+(day|days|month|months|week|weeks|year|years)\b"
    r"|\b(mtd|ytd|q[1-4])\b"
    r"|\b(all\s*time|alltime|overall|ever|till\s*date|to\s*date|so\s*far|lifetime)\b"
    r"|\b(aaje|kaale|aa\s*mahine|gaya\s*mahine|varas|mahina|mahine)\b"  # Gujlish
    r")",
    re.IGNORECASE,
)


# "What is the situation RIGHT NOW" questions. These have no period by nature
# (stock on hand, packets currently out on jangad), so asking for dates would be
# nonsense — answer them directly.
_CURRENT_STATE_RE = re.compile(
    r"\b(currently|right now|at present|as of now|pending|on hold|"
    # WIP is a LIVE snapshot ("what is in each department now"), never a period.
    r"in[\s-]?process|in[\s-]?processing|work[\s-]?in[\s-]?process|wip|"
    # "how many X in stock" is a LIVE snapshot - asking for a date range is
    # nonsense. Found by the cold test: "how many oval diamonds do we have in
    # stock?" was answered with a date picker.
    r"in\s+stock|on\s+hold|stock\s+ma|hold\s+par|atyare|abhi|right\s+now|"
    r"(where|which|what)\b.{0,40}\b(is|are)\b.{0,20}\b(in stock|out|now))\b",
    re.IGNORECASE,
)


def asks_current_state(question: str) -> bool:
    """True for 'what's the situation now' questions (no period applies)."""
    return bool(_CURRENT_STATE_RE.search(question or ""))


def mentions_period(question: str) -> bool:
    """True if the text already pins down a time period (so we must NOT ask)."""
    return bool(_PERIOD_RE.search(question or ""))


def is_report_question(question: str) -> bool:
    """True if the user is asking for a report / listing (not a definition)."""
    q = question or ""
    return bool(_REPORT_RE.search(q) or _WISE_RE.search(q))


def needs_date(question: str, history: list[dict] | None = None) -> bool:
    """
    Should we show the date picker instead of answering?

    Only when the question reads like a report AND names no period. A follow-up
    that already carries dates (what the picker sends back) passes straight
    through, as does any non-report question.
    """
    q = (question or "").strip()
    if not q or len(q) < 3:
        return False
    if mentions_period(q) or asks_current_state(q):
        return False
    return is_report_question(q)


def ask_date_response(question: str) -> dict:
    """
    The turn we return INSTEAD of querying: a short question plus the flag the
    UI uses to render the date picker. Shaped like a normal enriched result so
    every caller (both /chat and /chat/stream) can return it unchanged.
    """
    subject = (question or "that report").strip().rstrip("?.")
    return {
        "answer": (
            f"Sure — which period should I cover for “{subject}”?\n\n"
            "Pick a period below, or choose custom dates."
        ),
        "suggestions": [],
        "clarify_options": [],
        "ask_date": True,
        "citation": "",
        "export_query": None,
        "sql_used": [],
        "rows_returned": 0,
        "ok": True,
        "widgets": [],
        "data_columns": [],
        "data_rows": [],
    }
