"""
dimension_guard.py
------------------
ANSWER-COMPLETENESS CHECK: did the result actually cover the dimension the user
asked to break the data down by?

The failure this prevents (seen with the client, twice): they asked for "GIA
results of Fency department EMPLOYEES" and got a correct packet-level table with
NO employee column — the maker was used to FILTER the rows and then never
displayed. The numbers were right; the question wasn't answered.

Deterministic and provider-independent: compare the breakdown the question asked
for against the columns actually returned. No LLM call, so it protects questions
nobody encoded guidance for — the point is that it knows nothing about GIA,
Fency or this ERP, only about "you asked to see it by X, is there an X column?".

Deliberately narrow to avoid nagging:
  * it fires ONLY on an explicit per-X breakdown ("employee wise", "by employee",
    "for each employee", "which employee") — never on a passing mention such as
    "how many employees do we have";
  * it stays silent when a matching column IS present, when there are no rows,
    and when the answer is a single aggregate the user asked for.
"""
from __future__ import annotations

import re

# A dimension the user can ask to break data down BY.
#   key      -> canonical name used in the follow-up text
#   words    -> how a user refers to it (matched in the question)
#   columns  -> substrings that mean "this dimension IS in the result"
DIMENSIONS: list[dict] = [
    {
        "key": "employee",
        "words": ["employee", "employees", "worker", "workers", "karigar", "karigars",
                  "maker", "makers", "staff", "person", "people", "artisan"],
        # NOTE: no bare "name" — "KapanName" contains it and would wrongly look
        # like an employee column, silencing the guard on the exact client case.
        "columns": ["emp", "worker", "maker", "karigar", "firstname", "lastname",
                    "polisher", "checker", "artisan", "party", "firm"],
    },
    {
        "key": "department",
        "words": ["department", "departments", "dept", "depts", "division"],
        "columns": ["department", "dept", "process", "stage"],
    },
    {
        "key": "kapan",
        "words": ["kapan", "kapans", "lot", "lots", "parcel"],
        "columns": ["kapan", "lot"],
    },
    {
        "key": "shape",
        "words": ["shape", "shapes"],
        "columns": ["shape"],
    },
    {
        "key": "colour",
        "words": ["color", "colour", "colors", "colours"],
        "columns": ["color", "colour"],
    },
    {
        "key": "clarity",
        "words": ["clarity", "purity"],
        "columns": ["clarity", "purity"],
    },
    {
        "key": "party",
        "words": ["party", "parties", "vendor", "vendors", "sub-contractor",
                  "subcontractor", "job work", "jobwork"],
        "columns": ["party", "firm", "vendor", "toparty", "fromparty"],
    },
    {
        "key": "date",
        "words": ["day", "daily", "date", "datewise", "month", "monthly", "monthwise"],
        "columns": ["date", "day", "month", "time", "period"],
    },
]

# "Break it down BY x" phrasings. This is what keeps the guard quiet on a
# passing mention: the user must actually be asking for a per-X view.
_BREAKDOWN_PATTERNS = (
    r"\b{w}[\s-]?wise\b",                       # employee wise / employee-wise
    r"\bby\s+(?:each\s+)?{w}\b",                # by employee / by each employee
    r"\bfor\s+each\s+{w}\b",                    # for each employee
    r"\bper\s+{w}\b",                           # per employee
    r"\beach\s+{w}\b",                          # each employee
    r"\bwhich\s+{w}\b",                         # which employee
    r"\bwho\b",                                 # "who made the most" (employee only)
    r"\b{w}\s+(?:wise|breakdown|split|summary)\b",
)

# "<report> OF/FOR ... employees" — the client's actual phrasing: "GIA results of
# Fency department employees". Applied to PLURAL words only, so a single-entity
# question ("report of employee M4117") doesn't trigger a needless follow-up.
# NOTE the doubled braces: this string goes through .format(w=...).
_PLURAL_OF_PATTERN = r"\b(?:of|for)\s+(?:\S+\s+){{0,3}}{w}\b"

# Words that ARE the breakdown on their own — "daily production" needs no
# "day wise" to mean per-day.
_STANDALONE = {
    "date": (r"\bdaily\b", r"\bday[\s-]?wise\b", r"\bdate[\s-]?wise\b",
             r"\bmonthly\b", r"\bmonth[\s-]?wise\b", r"\bweekly\b"),
}

# COUNTING the dimension is not breaking down BY it: "how many employees do we
# have" must stay silent. Checked before any pattern fires.
_COUNT_OF_DIM = (
    r"\bhow\s+many\s+{w}s?\b",
    r"\b(?:number|count|total)\s+of\s+{w}s?\b",
    r"\bhow\s+many\s+\w+\s+{w}s?\s+(?:do|does|are|is)\b",
)

# "who" only implies the EMPLOYEE dimension.
_WHO_ONLY = "employee"


def _asks_breakdown_by(question: str, dim: dict) -> bool:
    q = (question or "").lower()

    # "how many employees" counts the dimension itself — not a per-X breakdown.
    for word in dim["words"]:
        w = re.escape(word)
        for pat in _COUNT_OF_DIM:
            if re.search(pat.format(w=w), q):
                return False

    # Some words imply the breakdown on their own ("daily production").
    for pat in _STANDALONE.get(dim["key"], ()):
        if re.search(pat, q):
            return True

    for word in dim["words"]:
        w = re.escape(word)
        for pat in _BREAKDOWN_PATTERNS:
            if pat == r"\bwho\b" and dim["key"] != _WHO_ONLY:
                continue
            if re.search(pat.format(w=w), q):
                return True
        # "results of ... employees" — plural forms only (see _PLURAL_OF_PATTERN)
        if word.endswith("s") and re.search(_PLURAL_OF_PATTERN.format(w=w), q):
            return True
    return False


def _result_has(dim: dict, columns: list[str]) -> bool:
    cols = " ".join(str(c).lower() for c in (columns or []))
    return any(frag in cols for frag in dim["columns"])


def missing_dimensions(question: str, columns: list[str], rows: list | None = None) -> list[str]:
    """
    Dimensions the question asked to break down by that are ABSENT from the result.

    Returns canonical dimension names (e.g. ["employee"]). Empty when the answer
    is complete, when nothing was returned, or when the user never asked for a
    per-X view.
    """
    if not rows:
        return []                      # nothing was returned; a different problem
    if not question:
        return []
    missing = []
    for dim in DIMENSIONS:
        if _asks_breakdown_by(question, dim) and not _result_has(dim, columns):
            missing.append(dim["key"])
    return missing


def followup_option(dimension: str) -> str:
    """
    The clickable follow-up shown when we could not add the column ourselves.

    Phrased as a complete question because tapping it SENDS this text as the next
    question (same contract as the CLARIFY buttons).
    """
    return f"Show the same report with the {dimension} name included"
