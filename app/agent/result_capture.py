"""
result_capture.py
-----------------
Picks WHICH query result is "the answer" when a turn ran several queries.

A single question often costs several queries: the model looks up how a value is
spelled, then runs the real report. Only one of those is the answer - it is the
one shown as a table when the write-up call fails, and the one the user's Excel
download is built from. Picking the wrong one is not a cosmetic bug: the user is
handed a table that is not what they asked for.

THE RULE
--------
A single-column result is a LOOKUP, not an answer. Discard it - unless it is all
we have. Among what remains, the largest result wins.

Both halves are load-bearing, and each one is a bug we already shipped:

1. "give me full report of MFG - 1" ran a lookup
   (SELECT DISTINCT DepartmentName ... LIKE '%MFG%' -> 10 rows, ONE column) and
   then the real 8-column report. The old rule was "largest wins", so 10 > 1 and
   the user was shown a list of department names captioned as their report.
   Dropping single-column results fixes it: a report question is never answered
   by one bare column.

2. A kapan detail list (hundreds of rows) followed by a one-row summary the
   model ran "for the prose". Taking the LAST result would clobber the detail
   and the download would hold a single summary row. Largest-wins fixes it.

Kept deliberately dumb. This used to be three copies of an inline `if` in the
gemini/groq/anthropic backends, drifting apart with three different comments -
so a fix had to be found and applied three times. One rule, one place, tested.
"""
from __future__ import annotations


def is_lookup(columns: list[str]) -> bool:
    """A one-column result is the model checking how something is spelled."""
    return len(columns or []) <= 1


def add_section(sections: list[dict], columns: list[str], rows: list) -> None:
    """
    Record one query result as an exportable SECTION.

    A "full report" runs several queries - production, damage, bonus, GIA - and
    the chat answer narrates all of them. Only ONE of them used to survive into
    the Excel file, because the export was built from the single `better()`
    winner: the client downloaded a 318-row production sheet with the bonus, GIA
    and damage sections missing entirely.

    Every non-empty, non-lookup result is kept so the workbook can carry one
    sheet per section. Exact duplicates are dropped - models re-run the same
    query after a nudge, and a duplicated sheet reads as a mistake.
    """
    if not rows or is_lookup(columns):
        return
    for existing in sections:
        if existing["columns"] == columns and len(existing["rows"]) == len(rows):
            return
    sections.append({"columns": list(columns), "rows": rows})


def better(new_cols: list[str], new_rows: list, cur_cols: list[str], cur_rows: list) -> bool:
    """
    Should the new result replace the one held so far?

    Answers beat lookups; between two of the same kind, more rows wins. Kept as a
    predicate (rather than sorting at the end) so the backends can keep streaming
    results in and holding just the winner.
    """
    if not new_rows:
        return False
    if not cur_rows:
        return True

    new_is_lookup, cur_is_lookup = is_lookup(new_cols), is_lookup(cur_cols)
    if new_is_lookup != cur_is_lookup:
        return cur_is_lookup          # a real result always displaces a lookup
    return len(new_rows) > len(cur_rows)
