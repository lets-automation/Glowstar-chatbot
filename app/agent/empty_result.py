"""
empty_result.py
---------------
WHY A FILTERED QUERY RETURNED NOTHING - answered with data, not a shrug.

WHY
---
Reported live 2026-08-27. The user asked:

    "from kapan QA26 give me packets that has purity between FL to VVS2 and
     size range from 0.3 to 0.80 for marker 2 department"

The model wrote a reasonable query and filtered the size range on
tblPacket.PolishedWt. It returned 0 rows, and the answer was "0 packets".

The real answer is 1. Measured on the 2026-08-21 backup:

    kapan QA26, 325 packets
      PolishedWt IS NULL or 0 ......... 325  (100%)
      CurrentWt  IS NULL or 0 ......... 0
    QA26 + Purity IN ('FL','IF','VVS1','VVS2') + wt BETWEEN 0.30 AND 0.80
      ... on PolishedWt ............... 0     <- what was answered
      ... on CurrentWt ................ 1     <- the answer
      ... on EstWeight ................ 10

PolishedWt is only written once a stone has been polished, so it is empty for
every packet in a kapan still in process. Nine of the 861 kapans are in that
state. The column is populated on 90% of the table overall, so a blanket "never
use PolishedWt" rule would be wrong for the other 852 kapans - the mistake is
not the column, it is reporting 0 without checking whether the filter COULD
have matched.

WHAT THIS DOES
--------------
When a query with a WHERE clause returns no rows, probe the database once:
hold the equality/IN/LIKE filters (the SCOPE - "which kapan", "which purity")
and drop the range filters (the SUSPECTS - "size between 0.3 and 0.8"). Then
report, per suspect column, how many rows in scope actually carry a value.

A column that is NULL on every row in scope cannot match any range, so it is
the blocker - and that is a fact about the data, not a guess. When the blocker
looks like a weight, sibling weight columns are probed too, so the model is
handed the column that WOULD answer instead of being left to guess again.

Nothing here changes an answer. It adds a note to the tool result so the model
can re-run correctly, and so "0" is never reported as a finding when the filter
was incapable of matching.
"""
from __future__ import annotations

import re

from app.core.logging_util import logger
from app.database.runner import run_select

# A probe is a COUNT over one table with a handful of predicates. It must never
# become the reason a turn is slow, so it is capped hard and failure is silent.
_PROBE_TIMEOUT = 10
_MAX_SUSPECTS = 4
_MAX_ALTERNATIVES = 6

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# FROM tblPacket p  /  JOIN tblEmployee AS e  - alias is optional.
_SOURCE_RE = re.compile(
    rf"\b(?:FROM|JOIN)\s+(?:dbo\.)?({_IDENT})\s*"
    rf"(?:WITH\s*\(\s*NOLOCK\s*\)\s*)?"
    rf"(?:AS\s+)?(?!WITH\b|ON\b|WHERE\b|INNER\b|LEFT\b|RIGHT\b|OUTER\b|JOIN\b|"
    rf"GROUP\b|ORDER\b|HAVING\b|UNION\b|CROSS\b|APPLY\b)({_IDENT})?",
    re.IGNORECASE,
)

# The WHERE clause, stopping at the first clause that ends it.
_WHERE_RE = re.compile(
    r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bUNION\b|$)",
    re.IGNORECASE | re.DOTALL,
)

# alias.Column BETWEEN x AND y   |   alias.Column >= x
_RANGE_RE = re.compile(
    rf"(?:({_IDENT})\s*\.\s*)?({_IDENT})\s*"
    rf"(?:BETWEEN\b|>=|<=|>|<)",
    re.IGNORECASE,
)

# Words that mean "this predicate names WHICH rows", not "how big they are".
_SCOPE_RE = re.compile(r"\b(?:=|IN|LIKE)\b|=", re.IGNORECASE)

_WEIGHTISH = re.compile(r"wt|weight|carat|size|pcs|cts", re.IGNORECASE)


def _split_and(where: str) -> list[str]:
    """Top-level AND-separated predicates. OR groups stay whole and are skipped.

    The AND inside `BETWEEN x AND y` binds to the BETWEEN, not to the predicate
    list: splitting on it yielded a dangling "0.80" that read as its own
    predicate. One pending BETWEEN is carried across the next AND.
    """
    parts, depth, buf, i = [], 0, [], 0
    pending_between = False
    while i < len(where):
        ch = where[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and re.match(r"\s+BETWEEN\s", where[i:], re.IGNORECASE):
            pending_between = True
        if depth == 0 and where[i:i + 5].upper() == " AND ":
            if pending_between:
                pending_between = False
            else:
                parts.append("".join(buf))
                buf = []
                i += 5
                continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _sources(sql: str) -> dict[str, str]:
    """alias (and bare table name) -> table name."""
    out: dict[str, str] = {}
    for table, alias in _SOURCE_RE.findall(sql or ""):
        out.setdefault(table.lower(), table)
        if alias and alias.lower() not in ("with", "on"):
            out[alias.lower()] = table
    return out


def _columns_of(table: str) -> dict[str, str]:
    """Real column names of `table`, lowercased -> actual case. {} on any error.

    This is also the whitelist: only identifiers that come back from here are
    ever put into a probe, so nothing parsed out of the model's SQL text can
    reach the database as an identifier.
    """
    res = run_select(
        "SELECT c.name FROM sys.columns c "
        f"WHERE c.object_id = OBJECT_ID('{table}')",
        max_rows=500,
        timeout=_PROBE_TIMEOUT,
    )
    if not res["ok"]:
        return {}
    return {r["name"].lower(): r["name"] for r in res["rows"]}


def _classify(sql: str) -> tuple[str, str, list[str], list[str]] | None:
    """(table, alias, scope predicates, suspect columns) for the first table
    that has both a range filter and real columns.

    The alias comes back because the scope predicates are reused VERBATIM in
    the probe, and they carry `p.`-style prefixes that only bind if the probe
    re-declares the same alias.

    None when nothing is diagnosable."""
    where_m = _WHERE_RE.search(sql or "")
    if not where_m:
        return None
    preds = _split_and(where_m.group(1))
    if not preds:
        return None

    sources = _sources(sql)
    if not sources:
        return None

    # Group predicates by the alias they mention, so each probe stays on ONE
    # table. A predicate touching two aliases (a join condition) belongs to
    # neither and is dropped - dropping it only widens the scope, which keeps
    # the finding conservative.
    by_alias: dict[str, dict[str, list[str]]] = {}
    for pred in preds:
        aliases = {a.lower() for a in re.findall(rf"({_IDENT})\s*\.", pred)}
        if len(aliases) != 1:
            continue
        alias = aliases.pop()
        if alias not in sources:
            continue
        slot = by_alias.setdefault(alias, {"scope": [], "range": []})
        m = _RANGE_RE.search(pred)
        if m and m.group(2):
            slot["range"].append(pred)
        elif _SCOPE_RE.search(pred):
            slot["scope"].append(pred)

    for alias, slot in sorted(by_alias.items()):
        if not slot["range"]:
            continue
        table = sources[alias]
        cols = _columns_of(table)
        if not cols:
            continue
        suspects = []
        for pred in slot["range"]:
            m = _RANGE_RE.search(pred)
            name = (m.group(2) or "").lower() if m else ""
            if name in cols and cols[name] not in suspects:
                suspects.append(cols[name])
        if suspects:
            return table, alias, slot["scope"], suspects[:_MAX_SUSPECTS]
    return None


def _alternatives(table: str, blocked: list[str]) -> list[str]:
    """Columns of the same table that look like the blocked one (weights, sizes)."""
    if not any(_WEIGHTISH.search(b) for b in blocked):
        return []
    cols = _columns_of(table)
    lowered = {b.lower() for b in blocked}
    return [
        actual for low, actual in cols.items()
        if _WEIGHTISH.search(low) and low not in lowered
    ][:_MAX_ALTERNATIVES]


def diagnose(sql: str) -> str:
    """A note explaining an empty result, or "" when there is nothing to add.

    Only ever called when a query returned 0 rows, so the cost lands on a turn
    that has no data to show anyway.
    """
    try:
        parsed = _classify(sql)
        if not parsed:
            return ""
        table, alias, scope, suspects = parsed
        alternatives = _alternatives(table, suspects)

        # The alias is one the model already wrote and every column name came
        # back from sys.columns, so the probe carries no free text.
        ref = alias if re.fullmatch(_IDENT, alias or "") else table
        counts = ", ".join(
            f"COUNT([{ref}].[{c}]) AS [nonnull_{c}]"
            for c in suspects + alternatives
        )
        where = (" WHERE " + " AND ".join(scope)) if scope else ""
        probe = (
            f"SELECT COUNT(*) AS scope_rows, {counts} "
            f"FROM [{table}] AS [{ref}] WITH (NOLOCK){where}"
        )
        res = run_select(probe, max_rows=1, timeout=_PROBE_TIMEOUT)
        if not res["ok"] or not res["rows"]:
            return ""
        row = res["rows"][0]
        in_scope = row.get("scope_rows") or 0

        scope_text = (" matching " + " AND ".join(scope)) if scope else ""
        if in_scope == 0:
            return (
                f"\n(EMPTY-RESULT DIAGNOSIS: there are no rows in {table}"
                f"{scope_text} at all, before the range filter was applied. The "
                "0 is about that filter, not about the size/date range. Say so "
                "plainly - check the spelling of any name the user gave rather "
                "than reporting activity as zero.)"
            )

        dead = [c for c in suspects if not (row.get(f"nonnull_{c}") or 0)]
        if not dead:
            # THE PROBE ONLY SAW ONE TABLE, SO IT CANNOT CLEAR THE WHOLE QUERY.
            #
            # _classify drops every join predicate on purpose - "dropping it
            # only widens the scope, which keeps the finding conservative".
            # That is true of the PROBE and false of the CONCLUSION drawn from
            # it: declaring "0 is the correct answer" is the least conservative
            # thing this module can say, and it is unsupported whenever a join
            # the probe never modelled could be what emptied the result.
            #
            # Measured live 2026-09-03 on the RunPod pod. Asked "from kapan
            # QA26 give me packets that has purity between FL to VVS2 and size
            # range from 0.3 to 0.80 for marker 2 department", the model wrote
            # a query joining tblPlanMaster ON RapVer = 'MKB' and tblEmployee
            # for Marker-2. The probe checked tblPacket ALONE, found 63,555
            # rows with CurrentWt populated, and returned "0 is the correct
            # answer here - report it as a real finding". The true answer is 1:
            # that packet has NO MKB row at all, and Marker-2's work on it sits
            # on the CLV stage. The all-clear was about to turn a wrong number
            # into a stated fact.
            others = sorted({t for a, t in _sources(sql).items()
                             if a != alias and t.lower() != table.lower()})
            if others:
                stage = re.search(r"RapVer\s*=\s*'([A-Za-z]+)'", sql or "")
                pin = (f" The query also pins RapVer = '{stage.group(1)}'; a "
                       f"department's work is not tied to one stage, so that "
                       f"filter is the first thing to drop.") if stage else ""
                return (
                    f"\n(EMPTY-RESULT DIAGNOSIS: {in_scope} rows in {table}"
                    f"{scope_text} carry a value in {', '.join(suspects)}, so "
                    f"the range filter is NOT the cause. The 0 comes from "
                    f"something this check could not see - the join(s) to "
                    f"{', '.join(others)} or their filters.{pin} Do NOT report "
                    f"0 as the answer yet: re-run ONCE with the join filters "
                    f"relaxed to find where the rows disappear.)"
                )
            return (
                f"\n(EMPTY-RESULT DIAGNOSIS: {in_scope} rows in {table}"
                f"{scope_text} carry a value in {', '.join(suspects)}, so the "
                "range filter ran against real data and genuinely matched "
                "nothing. 0 is the correct answer here - report it as a real "
                "finding, not as missing data.)"
            )

        live = [
            f"{c} ({row.get(f'nonnull_{c}')} of {in_scope} rows populated)"
            for c in alternatives if (row.get(f"nonnull_{c}") or 0)
        ]
        note = (
            f"\n(EMPTY-RESULT DIAGNOSIS: this returned 0 rows because "
            f"{', '.join(dead)} is EMPTY (NULL or 0) on ALL {in_scope} rows of "
            f"{table}{scope_text}. A range filter on that column cannot match "
            "anything, so 0 is an artefact of the column choice - it is NOT the "
            "answer, and you must not report it as one."
        )
        if live:
            note += (
                f" The same rows DO carry: {'; '.join(live)}. Re-run ONCE using "
                "whichever of those the user meant"
            )
            if any(_WEIGHTISH.search(c) for c in dead):
                note += (
                    " - a stone's weight is only written to the polished column "
                    "after it is polished, so for packets still in process the "
                    "current/estimated weight is the size the user means"
                )
            note += "."
        else:
            note += (
                " Tell the user this figure is not recorded for these packets "
                "rather than reporting 0."
            )
        note += ")"
        logger.info("EMPTY-RESULT | table=%s | dead=%s | scope_rows=%s",
                    table, ",".join(dead), in_scope)
        return note
    except Exception as exc:  # a diagnosis must never break a turn
        logger.warning("EMPTY-RESULT-DIAG-FAILED | %s", str(exc)[:200])
        return ""
