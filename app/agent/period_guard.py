"""
period_guard.py
---------------
SCOPE CHECK: the user named a period, but the query that produced the answer never
filtered on a date — so every number shown is all-time, not the period asked for.

This is worse than a missing column: nothing on screen is right, and the figures
look completely plausible. ("Production for June" that quietly totals five years.)

Deterministic, no LLM. Two halves:
  STEP A  does the QUESTION name a bounded period?
  STEP B  does ANY sql in the turn constrain a date?
Fires only when A is true and B is false for every query.

Design notes that are load-bearing (each was a real false positive while testing):
  * "may" is a modal verb — "may I see the stock summary" is not May 2026.
  * a 4-digit number is often an entity — "show packet 2024 details" is not a year.
  * no loose range regex — "packets from department MFG 1" and "compare MFG to PLS"
    both match a naive \\b(from|to)\\b.*\\d pattern.
  * "all time / overall / ever / till date" means an unfiltered query is CORRECT,
    so it must suppress the guard (the opposite of how date_gate treats it).
  * SQL is scanned as RAW TEXT, so a filter inside a subquery, a CTE or a JOIN ...
    ON clause counts — it is literally present in the string.
"""
from __future__ import annotations

import re

# An explicit request for ALL history: an unfiltered query is then correct.
_ALLTIME_RE = re.compile(
    r"\b(all\s*time|alltime|overall|ever|till\s*date|to\s*date|so\s*far|lifetime|"
    r"since\s+inception|entire\s+history|of\s+all\s+time)\b",
    re.IGNORECASE,
)

# Granularity words ask for a BREAKDOWN, not a bound (dimension_guard's job).
_GRANULARITY_RE = re.compile(r"\b(daily|monthly|weekly|yearly|annually)\b", re.IGNORECASE)

_MONTHS = (r"january|february|march|april|june|july|august|september|october|"
           r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")

_BOUNDED_RES = (
    re.compile(rf"\b({_MONTHS})\b", re.IGNORECASE),          # month names (NOT bare 'may')
    re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"),            # 01/06/2026
    re.compile(r"\d{4}-\d{2}-\d{2}"),                        # 2026-06-01
    re.compile(r"\b(today|yesterday|tomorrow)\b", re.IGNORECASE),
    re.compile(r"\b(this|last|past|previous|current|next)\s+"
               r"(month|week|year|quarter|day|days|fortnight)\b", re.IGNORECASE),
    re.compile(r"\blast\s+\d+\s+(day|days|month|months|week|weeks|year|years)\b", re.IGNORECASE),
    re.compile(r"\b(mtd|ytd|q[1-4])\b", re.IGNORECASE),
    re.compile(r"\b(aaje|kaale|aa\s*mahine|gaya\s*mahine)\b", re.IGNORECASE),
    # a REAL numeric range: "from 1 to 26", "between 1 and 30"
    re.compile(r"\b(from|between)\s+\d{1,2}(st|nd|rd|th)?\s*(to|-|and)\s*\d{1,2}\b",
               re.IGNORECASE),
)

# "may" only counts as the month when a preposition or a year pins it down.
_MAY_AS_MONTH_RE = re.compile(
    r"\b(?:in|for|during|of|since|from|till|until|month\s+of)\s+may\b"
    r"|\bmay\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

# A 4-digit number preceded by an entity word is an ID, not a year.
_YEAR_CTX_RE = re.compile(
    r"(\w+)?\s*(?:no\.?|number|#)?\s*\b((?:19|20)\d{2})\b", re.IGNORECASE)
_ENTITY_WORDS = {
    "packet", "pkt", "kapan", "lot", "parcel", "rfid", "cert", "certificate",
    "barcode", "no", "number", "id", "emp", "employee", "code",
}


def _has_real_year(question: str) -> bool:
    for m in _YEAR_CTX_RE.finditer(question or ""):
        prev = (m.group(1) or "").lower()
        if prev not in _ENTITY_WORDS:
            return True
    return False


def names_bounded_period(question: str) -> bool:
    """True if the question pins the answer to a specific, bounded period."""
    q = question or ""
    if _ALLTIME_RE.search(q):
        return False
    if any(r.search(q) for r in _BOUNDED_RES):
        return True
    if _MAY_AS_MONTH_RE.search(q):
        return True
    return _has_real_year(q)


# --- STEP B: does the SQL constrain a date? ---------------------------------
_DATE_PARTS = ("date", "time", "month", "year", "period", "quarter", "week",
               "fy", "dob", "doj")
# Words that merely CONTAIN a date part - accepting them silently disables the
# whole guard on any query that filters one ("IsUpdated" contains "date").
_NOT_DATE = {
    "update", "updated", "updateby", "updatedby", "isupdated", "candidate",
    "validate", "validated", "mandate", "consolidate", "holiday", "today",
}
_DATE_FUNCS = r"GETDATE|DATEADD|DATEDIFF|DATEPART|EOMONTH|CONVERT|FORMAT|YEAR|MONTH"
_DATE_LITERAL_RE = re.compile(
    r"'(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{8})", re.IGNORECASE)
_IDENT_RE = re.compile(r"(?:\[?\w+\]?\.)?\[?(\w+)\]?")
_COMPARE_RE = re.compile(r"^\s*(?:AS\s+\w+\s*)?\)*\s*(>=|<=|<>|!=|=|>|<|BETWEEN|IN|IS|LIKE)",
                         re.IGNORECASE)


def _is_date_identifier(name: str) -> bool:
    n = (name or "").strip("[]").lower()
    if not n or n in _NOT_DATE:
        return False
    for part in n.split("_"):
        if part in _NOT_DATE:
            continue
        for d in _DATE_PARTS:
            if part == d or part.startswith(d) or part.endswith(d):
                return True
    return False


def _strip_noise(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s)
    return s


def constrains_date(sql: str) -> bool:
    """True if this SQL text filters on a date ANYWHERE - subquery, CTE or JOIN."""
    s = _strip_noise(sql)
    if not s.strip():
        return False
    if _DATE_LITERAL_RE.search(s):                                   # (a)
        return True
    blanked = re.sub(r"'[^']*'", "''", s)
    for m in _IDENT_RE.finditer(blanked):                            # (b)
        if _is_date_identifier(m.group(1)) and _COMPARE_RE.match(blanked[m.end():]):
            return True
    for m in re.finditer(r"\b(WHERE|HAVING|AND|OR|ON)\b", blanked, re.IGNORECASE):  # (c)
        region = blanked[m.end(): m.end() + 160]
        region = re.split(r"\b(ORDER\s+BY|GROUP\s+BY)\b", region, flags=re.IGNORECASE)[0]
        if re.search(rf"\b({_DATE_FUNCS})\b", region, re.IGNORECASE):
            return True
        if any(_is_date_identifier(t) for t in re.findall(r"\w+", region)):
            return True
    return False


def unfiltered_period(question: str, sql_used: list[str], rows: list | None) -> bool:
    """True when the question names a period but NO query constrained a date."""
    from app.agent import date_gate

    if not rows or not sql_used:
        return False
    if _GRANULARITY_RE.search(question or "") and not names_bounded_period(question):
        return False
    if not names_bounded_period(question):
        return False
    if date_gate.asks_current_state(question):
        return False
    return not any(constrains_date(s) for s in sql_used)


def period_phrase(question: str) -> str:
    """The period the user named, for the banner text."""
    for r in (_BOUNDED_RES[4], _BOUNDED_RES[0], _BOUNDED_RES[3]):
        m = r.search(question or "")
        if m:
            return m.group(0)
    m = _YEAR_CTX_RE.search(question or "")
    return m.group(2) if m else "that period"


def scope_banner(period: str) -> str:
    """Prepended ABOVE the table - a warning under 50 rows is never read."""
    return (
        f"> **Scope check:** you asked about **{period}**, but this result is "
        f"**not filtered to that period** — it covers all available history. "
        f"Treat the totals as all-time, not {period}."
    )


def followup_option(period: str) -> str:
    return f"Show the same report filtered to {period}"
