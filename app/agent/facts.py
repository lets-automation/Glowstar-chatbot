"""
facts.py
--------
EXACT numbers for the answer, computed from the data - never by the model.

WHY THIS EXISTS
---------------
Measured on the 2026-08-24 client demo. The question was "kapan wise by lab wise
for may month". The query returned 53 rows totalling 3,227 packets. The model was
shown the first 30 rows (MODEL_ROW_LIMIT), printed those 30, and announced
"In total, 2,403 packets" - a number that matches neither the true total (3,227)
nor even the sum of the rows it had just printed (2,509). The same question on
another provider produced 8,653.

The total was never in the data. It was mental arithmetic over a truncated list,
so every model invented a different one. No prompt wording fixes that: the model
cannot add up rows it was never shown.

So the totals are computed HERE, from the full captured result, and rendered
deterministically. The model is told not to compute them.

WHAT COUNTS AS A TOTAL-ABLE COLUMN
----------------------------------
Only columns the QUERY ITSELF aggregated - `COUNT(...) AS x` / `SUM(...) AS x`.
Summing anything else is a business claim we are not entitled to make: this
schema is full of legitimate row multiplicity (tblPointRateLabour repeats a
packet ~5x, tblPlanMaster once per stage, tblKapanValue once per day), so
"SUM(the column)" across raw rows can be arithmetically right and factually
nonsense. count_guard.py has the same warning for the same reason.

What we DO publish is the figure a user gets by summing that column in the
exported Excel - which is exactly what the client did when they checked us.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# `COUNT(...) AS Packets` / `SUM(x.Wt) AS [Total Wt]` in the OUTER select list.
# The alias is what appears as a column heading, so that is what we can total.
# A CAST'd aggregate must still be recognised, and the TYPE must not be mistaken
# for the alias.
#
# `CAST(SUM(ISNULL(g.PolishedWt,0)) AS decimal(14,3)) AS PWt` - the first `AS`
# the old pattern reached was the type cast, so it captured ('SUM','decimal'):
# the real alias PWt got NO total and a phantom column named 'decimal' was
# declared totalable. Measured live 2026-08-25 on the lab-results query: facts
# returned {PNo: 2,562} and silently dropped PWt = 1,330.93 ct - the carat
# figure the client sums in Excel to check us. The model was then left to add
# the weights up in its head over a 30-row preview, which is the exact
# 2026-08-24 failure this module was written to close.
_CAST_TAIL = (
    r"(?:\s+AS\s+(?:decimal|numeric|float|real|int|bigint|money|smallmoney|"
    r"varchar|nvarchar|char)\s*(?:\([^()]*\))?\s*\))?"
)
_AGG_ALIAS_RE = re.compile(
    r"\b(?P<agg>COUNT|SUM)\s*\((?P<inner>[^()]*(?:\([^()]*\)[^()]*)*)\)"
    + _CAST_TAIL
    + r"\s+AS\s+(?P<alias>\[[^\]]+\]|\"[^\"]+\"|\w+)",
    re.IGNORECASE,
)
# A DISTINCT aggregate is additive across groups ONLY IF each counted entity
# belongs to exactly one group - and whether that holds depends on what the
# query GROUPED BY.
#
#   COUNT(DISTINCT Packet_ID) GROUP BY KapanName   ADDITIVE - a packet belongs
#       to exactly one kapan, so the per-kapan counts sum to the true total.
#       This is the lab-results shape and its total is the figure the client
#       checks against their own ERP. It must keep working.
#
#   COUNT(DISTINCT EmpId)     GROUP BY MONTH(...)  NOT ADDITIVE - an employee
#       who works in March, April and May is counted three times. Measured live
#       2026-08-25: facts published "**Workers: 374**" in bold, labelled EXACT,
#       where the true distinct count over the window is 163.
#
# A TIME BUCKET is the case where recurrence is the norm rather than the
# exception: entities persist across months, kapans and departments do not
# migrate. So DISTINCT totals are withheld only when the grouping is temporal.
# That is narrow on purpose - the alternative, excluding every DISTINCT, was
# tried and deleted the client-facing total above (caught by
# tests/test_answer_numbers.py::test_total_is_summed_over_all_rows_not_the_preview).
#
# A recipe's `| totals:` declaration is never filtered: there an author has
# verified additivity for that specific query.
_DISTINCT_RE = re.compile(r"\bDISTINCT\b", re.IGNORECASE)
_TIME_GROUPING_RE = re.compile(
    r"GROUP\s+BY\b[^)]*?\b(?:MONTH|YEAR|DAY|DATEPART|DATENAME|DATEADD|DATETRUNC|"
    r"FORMAT|CONVERT|EOMONTH)\s*\(|GROUP\s+BY\b[^;]{0,120}?\b\w*Date\w*\b",
    re.IGNORECASE,
)


# A pinned recipe (department_report, lab_results_report) reports its call as a
# COMMENT, because the real work is several queries - so there is no COUNT()/SUM()
# for the parser to find and the totals line silently disappeared. Measured live
# 2026-08-24: the lab report rendered all 27 kapan rows with NO total, which is
# the one figure the client checks against their ERP. A recipe therefore declares
# its own additive columns:  -- lab_results_report(...) | totals: PNo, PWt
# Percentages are deliberately NOT declared: summing DiffPer is nonsense.
_DECLARED_TOTALS_RE = re.compile(r"\|\s*totals:\s*([^\n|]+)", re.IGNORECASE)


def aggregate_columns(sql: str) -> set[str]:
    """Column aliases safe to total: COUNT()/SUM() aliases, or a recipe's own.

    A DISTINCT aggregate is skipped for ad-hoc SQL - see _DISTINCT_RE. Withholding
    a total is always safe; publishing a wrong one in bold is not.
    """
    out = set()
    for m in _AGG_ALIAS_RE.finditer(sql or ""):
        if _DISTINCT_RE.search(m.group("inner") or "") and _TIME_GROUPING_RE.search(sql or ""):
            continue
        out.add(m.group("alias").strip('[]"'))
    for declared in _DECLARED_TOTALS_RE.findall(sql or ""):
        out.update(c.strip() for c in declared.split(",") if c.strip())
    return out


def _num(value):
    """Decimal for anything numeric; None for text/dates/blanks (never raises)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _fmt(value: Decimal) -> str:
    """Thousands-separated; integers without a decimal tail."""
    if value == value.to_integral_value():
        return f"{int(value):,}"
    return f"{value.normalize():,f}".rstrip("0").rstrip(".")


def _label_column(columns: list, rows: list) -> str:
    """The column that NAMES each row - the GROUP BY key, in practice.

    Picked as the first column whose values are mostly non-numeric. That is the
    same convention the rendered table already relies on, and it is only ever
    used to LABEL a figure ("highest PNo = 551 (NS26)"), never to compute one -
    so a bad guess costs a wrong label on a correct number, not a wrong number.
    Returns "" when there is no such column, and the label is then omitted.
    """
    for c in [str(x) for x in (columns or [])]:
        vals = [r.get(c) for r in rows[:50] if isinstance(r, dict)]
        vals = [v for v in vals if v is not None]
        if vals and sum(1 for v in vals if _num(v) is None) >= len(vals) * 0.6:
            return c
    return ""


def _derived(rows: list, col: str, total: Decimal, label_col: str) -> dict:
    """Average per row, and the highest/lowest row, for ONE totalable column.

    WHY THESE ARE COMPUTED HERE AND NOT BY THE MODEL
    ------------------------------------------------
    The model sees MODEL_ROW_LIMIT (30) rows. Any average or superlative it
    works out is arithmetic over a sample it mistakes for the whole result.
    Measured live 2026-08-25 on kapan-wise plan counts (861 groups, sorted
    DESC): the true average per kapan is 1,529.24, and the mean of the first 30
    rows is 6,495.93 - the model would overstate it by 325%. Sorted results make
    this worse, not better, because the preview is the top of the distribution.

    Only ADDITIVE columns reach here (see aggregate_columns), which is what makes
    the average sound: total/row_count is the mean of the group values, i.e.
    "average per <group>". A mean of per-group AVG() columns would need weights
    and is deliberately NOT attempted.

    The share is exact for the same reason: highest / total over the complete
    result. It closes the "X accounts for N% of production" claim, which nothing
    computed before.
    """
    n = len(rows)
    out = {}
    if n:
        out["avg"] = _fmt((total / n).quantize(Decimal("0.01")))
    best = worst = None
    for r in rows:
        v = _num(r.get(col) if isinstance(r, dict) else None)
        if v is None:
            continue
        if best is None or v > best[0]:
            best = (v, r)
        if worst is None or v < worst[0]:
            worst = (v, r)

    def _one(hit):
        if hit is None:
            return None
        v, row = hit
        item = {"value": _fmt(v)}
        if label_col:
            lab = row.get(label_col)
            if lab not in (None, ""):
                item["label"] = str(lab)
        return item

    hi, lo = _one(best), _one(worst)
    # Share on the HIGHEST only. It answers "X accounts for N% of production",
    # which is the claim nothing computed before; the minimum's share is almost
    # always 0.0% and is pure noise in the prompt.
    if hi and best and total and total != 0:
        hi["share"] = f"{(best[0] / total * 100):.1f}%"
    if hi:
        out["max"] = hi
    if lo:
        out["min"] = lo
    return out


def compute(sql: str, columns: list, rows: list, truncated: bool = False) -> dict:
    """
    Exact facts about a result set.

    `rows` must be the FULL captured rows (up to EXPORT_ROW_CAP), not the model's
    preview - the whole point is to know what the model cannot see.

    Returns {row_count, totals: {col: text}, partial: bool}. `partial` means the
    result hit the safety cap, so the totals cover only the captured rows and
    must never be presented as the complete figure.
    """
    rows = rows or []
    facts = {"row_count": len(rows), "totals": {}, "derived": {},
             "partial": bool(truncated)}
    if not rows or not columns:
        return facts

    # Follow the RESULT's column order, not set order: the client reads this line
    # straight across from their ERP's total row, and a shuffled order reads as a
    # different report.
    totalable = aggregate_columns(sql)
    label_col = _label_column(columns, rows)

    # MIN/MAX ARE ALWAYS EXACT; SUM AND AVERAGE ARE NOT.
    #
    # Additivity is what gates a TOTAL - you may not sum a percentage, a rate or
    # a per-group DISTINCT count. But the HIGHEST and LOWEST row of any numeric
    # column is just a scan of the complete result: no arithmetic, no additivity
    # assumption, always right.
    #
    # Reported live 2026-08-26. A Fency lab report said "PJ26 had the largest
    # negative difference at -7.79%". The real lowest DiffPer is NT26 at -10.0%.
    # DiffPer is a PERCENTAGE, so it is deliberately excluded from `totalable`
    # (summing it is nonsense) - which meant no extremes were computed for it at
    # all and the superlative was left to the model. Percentages and rates are
    # exactly the columns a write-up makes superlative claims about.
    for col in [str(c) for c in columns
                if str(c) not in totalable and str(c) != label_col]:
        vals = [_num(r.get(col) if isinstance(r, dict) else None) for r in rows]
        if sum(1 for v in vals if v is not None) < 2:
            continue          # nothing to be superlative about
        d = _derived(rows, col, Decimal(0), label_col)
        d.pop("avg", None)    # not additive - a mean here would be a new claim
        if d:
            facts["derived"][col] = d

    for col in [str(c) for c in columns if str(c) in totalable]:
        total, seen = Decimal(0), False
        for r in rows:
            n = _num(r.get(col) if isinstance(r, dict) else None)
            if n is not None:
                total += n
                seen = True
        if seen:
            facts["totals"][col] = _fmt(total)
            # Average and highest/lowest over the COMPLETE result. Without these
            # the model works them out over a 30-row preview - measured 325% off
            # on an 861-group result. See _derived().
            facts["derived"][col] = _derived(rows, col, total, label_col)
    return facts


def as_model_note(facts: dict) -> str:
    """
    The compact block appended to the tool result.

    Deliberately short - a few dozen tokens - and it REPLACES work the model was
    doing badly, so the net token cost is negative: the model no longer echoes a
    30-row table it was told to render.
    """
    if not facts or not facts.get("row_count"):
        return ""
    bits = [f"rows={facts['row_count']}"]
    derived = facts.get("derived") or {}
    for col, val in facts.get("totals", {}).items():
        bits.append(f"total {col}={val}")
        d = derived.get(col) or {}
        if d.get("avg"):
            bits.append(f"avg {col}/row={d['avg']}")
        # Only the FIRST totalable column gets its extremes named: it is the
        # primary metric a superlative is ever about, and repeating this for
        # every column would cost more tokens than the arithmetic it replaces.
        if col == next(iter(facts.get("totals", {})), None):
            for key, word in (("max", "highest"), ("min", "lowest")):
                hit = d.get(key)
                if not hit:
                    continue
                txt = f"{word} {col}={hit['value']}"
                extra = [x for x in (hit.get("label"), hit.get("share")) if x]
                if extra:
                    txt += " (" + ", ".join(extra) + " of total)" if hit.get("share")                         else " (" + ", ".join(extra) + ")"
                bits.append(txt)
    # Extremes for columns that have NO total (percentages, rates, diffs). These
    # are what a write-up makes superlative claims about - "the largest negative
    # difference" - and nothing computed them before. Capped so a wide result
    # cannot flood the prompt.
    for col, d in list(derived.items()):
        if col in (facts.get("totals") or {}) or "avg" in d:
            continue
        for key, word in (("max", "highest"), ("min", "lowest")):
            hit = d.get(key)
            if not hit:
                continue
            lab = f" ({hit['label']})" if hit.get("label") else ""
            bits.append(f"{word} {col}={hit['value']}{lab}")
        if len(bits) > 22:
            break

    scope = (
        "These cover ONLY the captured rows (the result hit the row cap)"
        if facts.get("partial")
        else "These are EXACT, over the COMPLETE result"
    )
    return (
        f"\n(FACTS — {', '.join(bits)}. {scope}. USE THESE NUMBERS VERBATIM. "
        "Do NOT add up rows yourself and do NOT restate the table: the full "
        "table and these totals are appended to your answer automatically.)"
    )


def totals_line(facts: dict) -> str:
    """The user-visible total rendered under the table, straight from the data."""
    totals = (facts or {}).get("totals") or {}
    if not totals:
        return ""
    n = facts.get("row_count", 0)
    parts = ", ".join(f"**{col}: {val}**" for col, val in totals.items())

    # A ONE-ROW AGGREGATE IS NOT "ACROSS" ANYTHING.
    #
    # "across all N rows" describes a column summed down a table. When the
    # section IS a single aggregate row - every recipe's Summary - the totals
    # and the row are the same thing, and the clause rendered as
    #     PNo: 2, PWt: 0.67, PLSAmt: 29.74 - across all 1 row.
    # under a figure covering two packets. Reported by the client 2026-09-03
    # on the MFG-1 pending summary: it reads as though the answer rests on one
    # record, which is the doubt these totals exist to remove.
    #
    # The PARTIAL wording is kept whatever the count - "the result hit the row
    # cap" is load-bearing and must never be silently dropped.
    if facts.get("partial"):
        return f"\n\n{parts} — across the captured rows ({n:,})."
    if n <= 1:
        return f"\n\n{parts}"
    return f"\n\n{parts} — across all {n:,} rows."


# ---------------------------------------------------------------------------
# Correcting a total the model stated anyway
# ---------------------------------------------------------------------------
# The model is told to quote FACTS verbatim, and mostly does. When it does not,
# the prose and the totals line disagree in front of the client - the exact
# credibility failure that started all this. So an explicit TOTAL claim is
# checked against the computed figure and rewritten when it is wrong.
#
# ONLY explicit-total wording is touched ("in total", "a total of", "overall"),
# never a bare number: "NS26 had 531 packets" is a row value and must survive.
# count_guard.py stays log-only and untouched - it answers a different question
# (does a row-COUNT claim match?) and its tier-1 contract is deliberate.
#
# THE NUMBER PATTERN MUST MATCH DECIMALS, AND MUST NOT START MID-NUMBER.
#
# `[\d,]+` stops dead at the decimal point. On the model's CORRECT sentence
# "A total of 1,330.93 carats" it captured "1,330", compared that against the
# computed "1330.93", concluded the model was wrong, and spliced the total in
# with str.replace - shipping "A total of 1,330.93.93 carats" to the client.
# Three corruptions reproduced against the live code on 2026-08-25:
#     "A total of 1,330.93 carats."               -> "1,330.93.93"
#     "In total, 76.16 carats were produced."     -> "76.16.16"
#     "The kapan produced 76.16 carats in total." -> "76.76.16"
# The last is the 4th pattern matching the "16" INSIDE "76.16", so it also needs
# a lookbehind. EVERY weight/amount SUM produces a decimal total, and the model
# is told to quote the FACTS figure verbatim - so OBEYING the instruction is
# what triggered the corruption. tests/test_answer_numbers.py had 13 tests and
# every one used an integer total, which is how 851 passing tests sat on top of
# this.
_NUM = r"[\d,]+(?:\.\d+)?"
_TOTAL_CLAIM_RES = (
    re.compile(r"(?P<pre>\bin\s+total[,:]?\s*(?:\*\*)?)(?P<num>" + _NUM + r")", re.IGNORECASE),
    re.compile(r"(?P<pre>\ba?\s*total\s+of\s+(?:\*\*)?)(?P<num>" + _NUM + r")", re.IGNORECASE),
    re.compile(r"(?P<pre>\boverall[,:]?\s+(?:\*\*)?)(?P<num>" + _NUM + r")", re.IGNORECASE),
    re.compile(r"(?<![\d.])(?P<num>" + _NUM + r")(?P<pre>\s+\w+\s+in\s+total\b)", re.IGNORECASE),
)

# A YEAR IS NEVER A TOTAL. "Overall, 2026 production grew." became
# "Overall, 1,022 production grew." - the sentence was CORRECT before the fix.
_YEAR_RE = re.compile(r"^(?:19[89]\d|20[0-4]\d)$")

# NOUNS THAT ARE NEVER WHAT A COUNT/SUM ALIAS TOTALS. "Across a total of 5
# departments" became "a total of 1,022 departments".
#
# Time and structure words ONLY. Anything the query could genuinely be counting
# (packets, stones, kapans, workers, karigars) is deliberately absent: for those
# the value comparison already decides correctly, and excluding them would
# suppress the one correction this function is here to make.
_NOT_THE_TOTAL_NOUN = frozenset("""
    day days week weeks month months year years hour hours minute minutes
    time times department departments section sections stage stages step steps
    category categories type types column columns table tables page pages
    round rounds question questions
""".split())


def correct_total_claims(text: str, facts: dict, question: str = "") -> tuple[str, list]:
    """
    Rewrite explicit total claims that contradict the computed total.

    Returns (text, corrections) where corrections is [(claimed, actual), ...].
    A no-op unless the query produced exactly ONE totalable column: with two,
    which total the sentence meant is a guess, and guessing is what we are
    removing from this system.

    EVERY CHECK BELOW CAN ONLY SUPPRESS A REWRITE, NEVER ADD ONE.
    -------------------------------------------------------------
    That is the safety property this function needs. It edits client-facing
    prose in place, so a wrong rewrite is worse than no rewrite: a total we
    leave alone is still contradicted by the deterministic totals_line rendered
    under the table, but a number we mangle is read aloud in a meeting. Three
    live corruptions (see _TOTAL_CLAIM_RES above and the exclusions below) all
    came from rewriting something that was already correct.

    `question` is optional so any older caller keeps working; without it the
    user-supplied-number check is simply skipped.
    """
    totals = (facts or {}).get("totals") or {}
    if not text or len(totals) != 1 or facts.get("partial"):
        return text, []
    actual = next(iter(totals.values()))
    allowed = {actual.replace(",", ""), str(facts.get("row_count", ""))}
    corrections = []

    # Numbers the USER typed are never the model's arithmetic - they are the
    # question being echoed back ("damage in 2025" -> "2025"). count_guard.py
    # already applies this rule; the corrector did not, which is how a real
    # 2026-08-18 turn had a year adjacent to total-wording.
    q_digits = {d.replace(",", "") for d in re.findall(r"\d[\d,]*(?:\.\d+)?", question or "")}

    def _same(a: str, b: str) -> bool:
        """Numeric equality, so '1330.93' == '1,330.93' and '007' == '7'."""
        try:
            return Decimal(a) == Decimal(b)
        except (InvalidOperation, ValueError):
            return a.lstrip("0") == b.lstrip("0")

    def _fix(m):
        claimed = m.group("num")
        bare = claimed.replace(",", "")

        # (1) The claim is already right - the normal case once the decimal
        #     pattern above actually captures the whole number.
        if any(_same(bare, a) for a in allowed if a):
            return m.group(0)

        # (2) The user supplied this number.
        if bare in q_digits:
            return m.group(0)

        # (3) A year is never a total.
        if _YEAR_RE.match(bare):
            return m.group(0)

        # (4) The noun being counted is not what the query totalled. The word
        #     after the number for the leading patterns; for the trailing
        #     pattern ("5 departments in total") it is inside `pre`.
        tail = (text[m.end():] if m.lastgroup else "") or ""
        after = re.match(r"\s*\*{0,2}([A-Za-z]+)", tail)
        noun = (after.group(1) if after else "")
        if not noun:
            inner = re.match(r"\s+(\w+)\s+in\s+total", m.group("pre") or "")
            noun = inner.group(1) if inner else ""
        if noun.lower() in _NOT_THE_TOTAL_NOUN:
            return m.group(0)

        corrections.append((claimed, actual))
        return m.group(0).replace(claimed, actual)

    for rx in _TOTAL_CLAIM_RES:
        text = rx.sub(_fix, text)
    return text, corrections
