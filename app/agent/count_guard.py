"""
count_guard.py
--------------
Does the prose's COUNT claim match the data actually returned?

Same family as superlative_mismatch: the table beside it can be right while the
sentence is wrong, and the client reads the sentence.

TIER 1 ONLY — LOG, DO NOT ALTER THE ANSWER. This earns its place the way
SUPERLATIVE-MISMATCH did: measure the real hit rate first, then decide whether a
user-visible action is justified. A noisy guard is worse than none.

Deliberately restricted to ROW COUNTS ("a total of 305 packets"). Carat/unit
totals are NOT checked: this schema is full of legitimate reasons a correct total
differs from the naive column sum of the shown rows (tblPointRateLabour's 5.04x
row multiplicity, tblPlanMaster's stage duplication, tblKapanValue's daily
snapshots). A model that correctly de-duplicates would be flagged for being right.
"""
from __future__ import annotations

import re

# Nouns a row count can be counted in. Units (carat/ct/gram) are deliberately absent.
_COUNTED = (
    r"packets?|stones?|diamonds?|rows?|records?|entries|items?|kapans?|"
    r"employees?|workers?|karigars?|makers?|parties|firms?|jangads?|"
    r"reports?|damages?|repairs?|plans?"
)
# "a total of 305 packets" | "305 packets in total" | "305 rows"
_CLAIM_RES = (
    re.compile(rf"\btotal\s+of\s+([\d,]+)\s+({_COUNTED})\b", re.IGNORECASE),
    re.compile(rf"\b([\d,]+)\s+({_COUNTED})\s+in\s+total\b", re.IGNORECASE),
    re.compile(rf"\b([\d,]+)\s+({_COUNTED})\b(?!\s*(?:of|out\s+of))", re.IGNORECASE),
)
# Wording that makes a number an estimate, a subset, or an identifier.
_SKIP_NEAR = re.compile(
    r"\b(approx|approximately|about|around|roughly|nearly|almost|over|under|"
    r"more\s+than|less\s+than|at\s+least|up\s+to|first|top|preview|showing|"
    r"sample|each|per|no\.?|number|id|code|packet\s+no)\b",
    re.IGNORECASE,
)
_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|.*$", re.MULTILINE)
_FENCE = re.compile(r"```.*?```", re.S)
_FOOTER = re.compile(r"_Showing[^_]*_", re.IGNORECASE)
_META_LINE = re.compile(r"^\s*(SUGGESTIONS|CLARIFY|ASKDATE|Source):.*$",
                        re.IGNORECASE | re.MULTILINE)
_PERCENT_OR_MONEY = re.compile(r"[₹$%]")


def _prose_only(answer: str) -> str:
    """The model's own sentences: no rendered table, code, footer or meta lines."""
    s = _FENCE.sub(" ", answer or "")
    s = _MD_TABLE_ROW.sub(" ", s)
    s = _FOOTER.sub(" ", s)
    s = _META_LINE.sub(" ", s)
    return s


def _supported_values(rows: list, rows_returned: int) -> set[float]:
    """Every count the data can legitimately justify."""
    out: set[float] = {float(len(rows))}
    if rows_returned:
        out.add(float(rows_returned))
    if not rows:
        return out
    cols = list(rows[0].keys())
    for c in cols:
        vals = [r.get(c) for r in rows]
        nums = [float(v) for v in vals
                if isinstance(v, (int, float)) and not isinstance(v, bool)]
        out.update(nums)                                   # a cell can BE the count
        if nums:
            out.add(float(sum(nums)))
        out.add(float(len({v for v in vals if v is not None})))   # distinct
        out.add(float(sum(1 for v in vals if v is not None)))     # non-null
    return out


def _matches(claim: float, supported: set[float]) -> bool:
    for v in supported:
        if round(claim) == round(v):
            return True
        if v and abs(claim - v) / abs(v) <= 0.005:         # float noise
            return True
    return False


def count_mismatch(
    answer: str,
    rows: list | None,
    rows_returned: int = 0,
    question: str = "",
    sql_used: list[str] | None = None,
    file_grounded: bool = False,
) -> tuple[int, str] | None:
    """
    Return (claimed_count, noun) when the prose states a row count the data cannot
    support. None when there is no checkable claim — which is the common case.
    """
    from app.agent.tools import EXPORT_ROW_CAP

    if not rows or file_grounded or not sql_used:
        return None
    if len(rows) >= EXPORT_ROW_CAP:      # truncated: the prose may cite the true total
        return None
    # The MODEL's own "SELECT TOP (n)" also truncates: it can correctly report the
    # true total (1,237) while we hold only the capped rows (1,000). Verified live
    # - this fired on a CORRECT answer, which is why the guard is log-only.
    for _sql in sql_used:
        for _n in re.findall(r"TOP\s*\(?\s*(\d+)", _sql or "", re.IGNORECASE):
            if int(_n) == len(rows):
                return None

    prose = _prose_only(answer)
    supported = _supported_values(rows, rows_returned)
    q_digits = set(re.findall(r"\d[\d,]*", question or ""))

    for rx in _CLAIM_RES:
        for m in rx.finditer(prose):
            raw, noun = m.group(1), m.group(2)
            if raw in q_digits:                       # the user supplied this number
                continue
            window = prose[max(0, m.start() - 40): m.end() + 20]
            if _SKIP_NEAR.search(window) or _PERCENT_OR_MONEY.search(window):
                continue
            try:
                claim = float(raw.replace(",", ""))
            except ValueError:
                continue
            if claim <= 1:
                continue
            if not _matches(claim, supported):
                return int(claim), noun
    return None
