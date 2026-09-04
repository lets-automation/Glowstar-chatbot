"""
unit_guard.py
-------------
UNIT CHECK: the answer states a CARAT figure that no weight column produced.

The failure this prevents, seen live 2026-08-31 on the cold test:

    Q: "OQ26 kapan ma final point / final polish weight ketlu nikalyu?"
    A: "OQ26 has 6,107.39 points earned in final-polish work and a total of
        6,107.39 carats polished in that kapan."

The same number, presented twice, under two different units. The points figure
was right (SUM(FMFGPoint) = 6,107.39, exactly what query_rules.final_points
requires); the carat figure was that same number wearing a different label. The
true weight is 378.458.

It happened because query_rules.weight_via_points_join correctly REFUSED the
one query that would have produced both - tblPacketPoint covers 398 of the
kapan's 839 packets - and the model, having only a points result in hand,
labelled it as carats rather than running the second query it was told to run.
So this guard is the other half of that rule: the rule stops the wrong weight
being computed, and this stops a weight being asserted that was never computed
at all.

DELIBERATELY NARROW, because a false positive here would put a warning on top
of a correct answer. All three must hold:
  * the answer states a number immediately followed by a carat unit;
  * NO returned column is a weight column (wt / weight / carat / cts);
  * that exact number IS present in the returned data under some other column
    - which is the signature of a figure being re-labelled rather than one
    quoted from memory or from a previous turn.

Deterministic and provider-independent: it reads the answer text and the
returned column names only.
"""
from __future__ import annotations

import re

# Column names that legitimately carry a weight. Substring match, lowercased.
_WEIGHT_COLUMNS = ("wt", "weight", "carat", "cts", "vajan")

# "6,107.39 carats" / "378.458 ct" / "310.66 ct." - a number wearing a carat unit.
_CARAT_CLAIM_RE = re.compile(
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*\**\s*(?:ct|cts|carat|carats)\b",
    re.IGNORECASE,
)


def _is_weight_column(name: str) -> bool:
    low = str(name or "").lower()
    return any(frag in low for frag in _WEIGHT_COLUMNS)


def _numbers_in(rows: list | None, columns: list | None) -> set[str]:
    """Every numeric value in the result, normalised for comparison."""
    out: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for col in columns or []:
            val = row.get(col)
            if isinstance(val, (int, float)):
                out.add(f"{float(val):.10g}")
    return out


def unsourced_carat_claim(answer: str, columns: list | None,
                          rows: list | None) -> str | None:
    """The carat figure the answer states that no weight column produced.

    Returns the offending number as written, or None when the answer is fine -
    which includes every answer that returned a weight column at all.
    """
    if not answer or not columns or not rows:
        return None
    if any(_is_weight_column(c) for c in columns):
        return None                     # a weight WAS queried; not our business

    available = _numbers_in(rows, columns)
    if not available:
        return None

    for match in _CARAT_CLAIM_RE.finditer(answer):
        raw = match.group(1)
        try:
            norm = f"{float(raw.replace(',', '')):.10g}"
        except ValueError:
            continue
        if norm in available:
            # The number came from the result, but from a column that is not a
            # weight - it has been re-labelled, not measured.
            return raw
    return None


def caution(number: str) -> str:
    """Prepended ABOVE the answer - a note underneath a figure is not read."""
    return (
        f"> **Check this figure:** **{number}** is shown here in carats, but no "
        f"weight column was queried for this answer - that number came from a "
        f"different column. Ask for the weight on its own to get a real figure."
    )


def followup_option() -> str:
    """One-tap re-ask, phrased as a complete question because tapping it SENDS
    this text as the next question."""
    return "Show the total weight in carats, queried from the weight column"
