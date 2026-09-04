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


# A pinned recipe (department_report, lab_results_report) reports its call as a
# COMMENT - "-- lab_results_report('2026-05-01', '2026-06-01', '')" - because the
# real work is several queries. _strip_noise removes comments, so constrains_date
# saw an empty string and the scope banner fired on a report that WAS filtered:
# the client was told "not filtered to that period" above correct May figures.
# The recipes take an explicit half-open period, so a marker carrying dates is
# proof of filtering, not the absence of it.
_RECIPE_PERIOD_RE = re.compile(r"^\s*--\s*\w+\(.*\d{4}-\d{2}-\d{2}", re.MULTILINE)


def unfiltered_period(question: str, sql_used: list[str], rows: list | None) -> bool:
    """True when the question names a period but NO query constrained a date."""
    from app.agent import date_gate

    if not rows or not sql_used:
        return False
    # IF WE CANNOT NAME THE PERIOD, WE CANNOT CLAIM THE USER ASKED FOR ONE.
    #
    # period_phrase() falls back to the literal string "that period", and the
    # banner interpolates it: "you asked about **that period**, but this result
    # is not filtered to that period". That is gibberish, and the cold test put
    # it at the top of two client-facing answers (EDA-1, CT-05 on 2026-08-26).
    # A banner we cannot phrase is a banner we have not earned - stay silent and
    # let the pre-execution check in tools.tool_run_sql do the real work.
    if period_phrase(question) == _UNKNOWN_PERIOD:
        return False
    if _GRANULARITY_RE.search(question or "") and not names_bounded_period(question):
        return False
    if not names_bounded_period(question):
        return False
    if date_gate.asks_current_state(question):
        return False
    if any(_RECIPE_PERIOD_RE.search(s or "") for s in sql_used):
        return False
    # A DISAMBIGUATION LOOKUP HAS NO TOTAL TO MIS-SCOPE.
    #
    # "total bonus of employee MAIYANI VIJAYABHAI in June 2026" is answered
    # correctly by asking WHICH of the fifteen people with that name is meant
    # (query_rules.employee_identity forces the code into the query so the
    # ambiguity is visible). That reply reads the roster and returns
    # ID / Code / DepartMentName - no measure at all - and the banner then sat
    # on top of it announcing "treat the totals as all-time" when the answer
    # contains no totals and is not claiming to. Seen live 2026-08-31.
    #
    # Suppressed only where the banner is unearnable: every query is a roster
    # read with no aggregate in it. A COUNT or SUM over tblEmployee is still
    # a figure and still warned about, and the pre-execution date check in
    # tools.tool_run_sql is unaffected.
    if sql_used and all(is_identity_lookup(s) for s in sql_used):
        return False
    return not any(constrains_date(s) for s in sql_used)


# A roster read that computes nothing: "which person did you mean?".
_IDENTITY_LOOKUP_RE = re.compile(
    r"^\s*SELECT\b(?![\s\S]*\b(?:SUM|COUNT|AVG)\s*\()"
    r"[\s\S]*\bFROM\s+tblEmployee\b",
    re.IGNORECASE,
)


def is_identity_lookup(sql: str) -> bool:
    """True for a 'which person did you mean' read - roster, no measure."""
    return bool(_IDENTITY_LOOKUP_RE.search(sql or ""))


# Returned when no period can be named. Callers must treat it as "do not speak".
_UNKNOWN_PERIOD = "that period"


# Phrases the banner must be able to NAME. Tried in order, most specific first.
#
# "may month" and "aa mahine" both named a real period that period_phrase could
# not render, so the banner came out as "you asked about **that period**" - which
# is gibberish, and the cold test put it at the top of two client-facing answers.
# Suppressing the banner instead was tried and lost a legitimate warning
# (test_a_genuinely_unfiltered_query_still_warns), so the phrase is NAMED rather
# than the warning dropped.
_PHRASE_RES = (
    re.compile(rf"\b({_MONTHS})\s+(?:month\s+)?(?:of\s+)?((?:19|20)\d{{2}})\b", re.IGNORECASE),
    re.compile(rf"\b({_MONTHS})\s+month\b", re.IGNORECASE),
    re.compile(r"\b(this|last|past|previous|current|next)\s+"
               r"(month|week|year|quarter|fortnight)\b", re.IGNORECASE),
    re.compile(r"\blast\s+\d+\s+(?:day|days|month|months|week|weeks|year|years)\b", re.IGNORECASE),
    # Gujlish: aa mahine = this month, gaya mahine = last month, aa varsh = this year
    re.compile(r"\b(aa|gaya|gaye|chalu)\s*(mahina|mahine|varsh|varas|varshe)\b", re.IGNORECASE),
    re.compile(rf"\b({_MONTHS})\b", re.IGNORECASE),
    re.compile(r"\b(mtd|ytd|q[1-4])\b", re.IGNORECASE),
)

# MAY IS A MONTH ONLY IN CONTEXT. _MONTHS deliberately omits bare "may" because
# it is also a modal verb ("may I see the stock summary"), so these patterns
# name it only where the context settles it - the same test _MAY_AS_MONTH_RE
# applies for detection.
_MAY_PHRASE_RES = (
    re.compile(r"\bmay\s+(?:month\s+)?((?:19|20)\d{2})\b", re.IGNORECASE),
    re.compile(r"\bmay\s+month\b", re.IGNORECASE),
    re.compile(r"\b(?:in|for|during|of|since|from|till|until|month\s+of)\s+(may)\b",
               re.IGNORECASE),
)

_GUJLISH_PERIOD = {
    "aa mahina": "this month", "aa mahine": "this month",
    "chalu mahina": "this month", "chalu mahine": "this month",
    "gaya mahina": "last month", "gaya mahine": "last month",
    "gaye mahine": "last month",
    "aa varsh": "this year", "aa varas": "this year", "aa varshe": "this year",
}


def period_phrase(question: str) -> str:
    """The period the user named, rendered for the banner.

    Returns _UNKNOWN_PERIOD only when nothing nameable is present - and callers
    must then stay silent rather than print the placeholder.
    """
    q = question or ""
    # "May" first: its patterns are context-qualified, so a hit is unambiguous.
    for r in _MAY_PHRASE_RES:
        m = r.search(q)
        if m:
            year = m.group(1) if m.lastindex and m.group(1).isdigit() else ""
            return f"May {year}".strip()
    for r in _PHRASE_RES:
        m = r.search(q)
        if not m:
            continue
        text = " ".join(m.group(0).split())
        return _GUJLISH_PERIOD.get(text.lower(), text)
    m = _YEAR_CTX_RE.search(q)
    return m.group(2) if m else _UNKNOWN_PERIOD


def scope_banner(period: str) -> str:
    """Prepended ABOVE the table - a warning under 50 rows is never read."""
    return (
        f"> **Scope check:** you asked about **{period}**, but this result is "
        f"**not filtered to that period** — it covers all available history. "
        f"Treat the totals as all-time, not {period}."
    )


def followup_option(period: str) -> str:
    return f"Show the same report filtered to {period}"


# ---------------------------------------------------------------------------
# PRE-EXECUTION: reject an unfiltered query instead of warning about it after.
#
# The banner above is the backstop, not the fix. By the time it renders, the
# answer already says 179,990 packets for "production in May 2026" - the true
# May figure is 3,227, a 56x inflation - and all the banner can do is tell the
# user the number they are looking at is the wrong one. The code that adds it
# says so: "We cannot fix the SQL from here."
#
# So the same check runs BEFORE execution, at the tool_run_sql choke point where
# query_rules already rejects wrong-SOURCE queries. The model is handed the exact
# column and asked to re-run. The wrong number is never produced.
#
# A WHITELIST, NOT AN INFERENCE. Every column below was read out of
# INFORMATION_SCHEMA against the live database on 2026-08-26, not taken from the
# data notes - the spellings are a minefield and one letter decides it:
# tblFinalPacket has CreateDate, tblPlanMaster has CreatDate. A table that is
# NOT in this map is never rejected, so an unverified table degrades to today's
# behaviour (the banner) instead of blocking a legitimate query.
# ---------------------------------------------------------------------------
_PERIOD_DATE_COLUMN = {
    "tblPacket": "CreDate",
    "tblFinalPacket": "CreateDate",
    "tblPlanMaster": "CreatDate",
    "tblPlanReport": "CreatedDate",
    "tblPointRateLabour": "ProcessDate",   # 928,063 rows, fully populated
    "tblLabourResult": "ProcessDate",      # NOTE: this feed stops in 2023
    "tblIncentiveAmount": "TransactTime",
    "tblTimeAttendance": "Time",
    "tblPacketHistory": "ReciveTime",
    "tblJunk": "CreateDate",               # IssueDate is 99.5% NULL - never use it
    "tblJangad": "JangadDate",
    "tblKapan": "CreatDate",
    "tblRepairCommentVision": "CreatDate",
}

_TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN)\s+\[?(\w+)\]?", re.IGNORECASE)


def dated_tables(sql: str) -> list[str]:
    """Whitelisted tables this query reads, in the order they appear."""
    seen, out = set(), []
    for m in _TABLE_REF_RE.finditer(_strip_noise(sql or "")):
        t = m.group(1)
        key = next((k for k in _PERIOD_DATE_COLUMN if k.lower() == t.lower()), None)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def missing_period_filter(question: str, sql: str) -> str:
    """A rejection message when this query would answer a dated question
    with all-time numbers, or "" when there is nothing to correct.

    Deliberately does NOT compute the date range. Turning "last month" into two
    literals is a date parser, and a wrong range would be a NEW wrong answer -
    the model already has TODAY'S DATE in its prompt and converts a period
    correctly; what it fails at is remembering to filter at all. So this supplies
    the discipline and the column name, and leaves the arithmetic where it works.
    """
    from app.agent import date_gate

    if not sql or not names_bounded_period(question or ""):
        return ""
    if date_gate.asks_current_state(question or ""):
        return ""
    if _RECIPE_PERIOD_RE.search(sql):
        return ""
    if constrains_date(sql):
        return ""
    tables = dated_tables(sql)
    if not tables:
        return ""
    cols = ", ".join(f"{t}.{_PERIOD_DATE_COLUMN[t]}" for t in tables[:3])
    period = period_phrase(question or "")
    return (
        f"BLOCKED: the question asks about {period}, but this query has NO date "
        f"filter - it would return ALL history and the answer would be wrong by "
        f"orders of magnitude. Add the period to the WHERE clause using the "
        f"correct date column for this table: {cols}. Use a half-open range, "
        f"e.g. >= '<start>' AND < '<day after the end>', with the dates for "
        f"{period} worked out from TODAY'S DATE in your instructions. If the "
        f"user genuinely wants all history, say so explicitly in your answer."
    )
