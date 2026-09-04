"""
views.py
--------
CURATED VIEWS - the wrong query made inexpressible instead of forbidden.

WHY THIS EXISTS
---------------
query_rules.py grew to 27 rules, every one written AFTER a client found the
bug it prevents. That is whack-a-mole by construction: 264 tables offer an
unbounded supply of plausible-but-wrong queries, and the client keeps finding
the ones nobody has encoded yet.

The industry answer is not more rules, it is fewer tables. The dbt 2026
benchmark measured the SAME text-to-SQL approach at 64.5% on a raw normalised
schema and 84-90% once a small modelled layer sat in front of it. Our own cold
run says the same thing louder: the curated department_report path scores 4/4
and the code-enforced guards 10/10, while free-form SQL over raw tables scores
roughly 9/25.

WHAT A VIEW IS ALLOWED TO DO
----------------------------
Remove AMBIGUITY. It may normalise a dirty dimension, dedupe a snapshot, or
resolve a join the schema does not declare.

WHAT A VIEW MUST NEVER DO
-------------------------
Silently DROP rows. Every join here is a LEFT JOIN and every flag is exposed as
a COLUMN rather than baked into a WHERE clause, because a view that quietly
filters is the same failure as the inner join that lost 46.7% of production
(see query_rules.pct_checker_join). The caller decides what to exclude; the
view only decides what things MEAN.

HOW THEY ARE APPLIED
--------------------
Inlined as derived tables, NOT prepended as CTEs. A leading "WITH" makes
sql_guard.ensure_row_cap return the query untouched (it says so in its own
docstring), so shipping views as CTEs would silently disable the row cap on
every query the model writes. Inlining keeps the statement a plain leading
SELECT, so the cap still gets injected.

VERIFIED 2026-08-31 against the live database - each figure is one the bot has
previously got WRONG:
    v_packet  172,233 rows (= tblPacket, nothing lost)
              oval in stock 7,591   (the bot answered 2,986, then 7,321)
              on hold      11,967   (the bot answered 2)
    v_lab     July 2026     3,692   (the bot answered 2,896, then 3,492)
              COUNT(*) and COUNT(DISTINCT PacketId) AGREE - the wrong query
              cannot be written any more
    v_stage   1,316,677 raw rows -> 1,057,368 deduped, and the distinct packet
              count is unchanged at 171,834
"""
from __future__ import annotations

import re

# Shape variants are SEPARATE stored values, not sub-types: F.OV / S.OV / OVM
# are all oval, and F.OV alone outnumbers plain OV. Mapped EXPLICITLY from the
# 38 stored values rather than by a pattern - "strip a trailing M" would turn
# EM (emerald, 7,059 packets), HM and OM into shapes that do not exist.
_SHAPE_FAMILY = """CASE WHEN p.Shape LIKE 'F.%' THEN SUBSTRING(p.Shape, 3, 20)
              WHEN p.Shape LIKE 'S.%' THEN SUBSTRING(p.Shape, 3, 20)
              WHEN p.Shape = 'OVM'    THEN 'OV'
              WHEN p.Shape = 'PSM'    THEN 'PS'
              ELSE p.Shape END"""

V_PACKET = f"""
SELECT
    p.ID             AS PacketId,
    p.KapanName      AS KapanName,
    p.PacketNo       AS PacketNo,
    p.Shape          AS ShapeCode,
    {_SHAPE_FAMILY}  AS Shape,
    p.Color          AS Color,
    p.Purity         AS Clarity,
    p.CurrentWt      AS Carats,
    p.PolishedWt     AS PolishedCarats,
    p.RunningProcess AS CurrentProcess,
    CASE WHEN p.RunningProcess = 'IN Stock' THEN 1 ELSE 0 END AS IsInStock,
    CASE WHEN ISNULL(k.IsOnHold, 0) = 1     THEN 1 ELSE 0 END AS IsOnHold,
    d.Name           AS CurrentDepartment,
    p.CreDate        AS CreatedOn
FROM tblPacket p
LEFT JOIN tblKapan k      ON p.Kapan_ID     = k.ID
LEFT JOIN tblDepartMent d ON p.DepartMentId = d.ID
"""

V_LAB = """
SELECT
    pm.Packet_ID  AS PacketId,
    pm.KapanId    AS KapanId,
    pm.RapVer     AS LabStage,
    pm.LAB        AS CertifyingLab,
    pm.EmpId      AS EmpId,
    pm.IsApproved AS IsApproved,
    pm.CreatDate  AS SentOn
FROM tblPlanMaster pm
WHERE pm.RapVer IN ('GIA','HRD','IGI')
"""

V_STAGE = """
SELECT x.PacketId, x.KapanId, x.Stage, x.EmpId, x.IsApproved,
       x.IsDamagePlan, x.PolishedCarats, x.StageDate
FROM (
    SELECT pm.Packet_ID   AS PacketId,
           pm.KapanId     AS KapanId,
           pm.RapVer      AS Stage,
           pm.EmpId       AS EmpId,
           pm.IsApproved  AS IsApproved,
           pm.IsDamagePlan AS IsDamagePlan,
           pm.PolishedWt  AS PolishedCarats,
           pm.CreatDate   AS StageDate,
           ROW_NUMBER() OVER (PARTITION BY pm.Packet_ID, pm.RapVer
                              ORDER BY pm.ID DESC) AS rn
    FROM tblPlanMaster pm
) x
WHERE x.rn = 1
"""

VIEWS: dict[str, str] = {
    "v_packet": V_PACKET,
    "v_lab": V_LAB,
    "v_stage": V_STAGE,
}

# WHICH RULES A VIEW MAKES REDUNDANT.
#
# A query_rules entry exists to stop one wrong way of reading the raw tables.
# When a view already encodes that reading, the rule does not just become
# unnecessary - it becomes WRONG, because it rejects the correct query.
# Verified 2026-08-31: all three of these were rejected before this existed
#     SELECT COUNT(*) FROM v_packet WHERE Shape='OV' AND IsInStock=1
#         -> shape_family: "use Shape IN ('OV','F.OV',...)"   (v_packet already did)
#     SELECT COUNT(*) FROM v_packet WHERE IsOnHold=1
#         -> stock_basis: "hold is KAPAN-level"               (v_packet already did)
#     SELECT COUNT(DISTINCT PacketId) FROM v_lab WHERE ...
#         -> lab_results: "query tblPlanMaster / filter RapVer" (v_lab already did)
#
# Only the rules a view GENUINELY subsumes are listed. Everything else still
# applies to a view query - a BETWEEN on dates or a GROUP BY ROLLUP is just as
# wrong against a view as against a raw table, and those rules keep firing.
# The DIRECTIVES are untouched either way: the model is still told to say which
# stock basis it used, because that is about the prose, not the source.
SUBSUMES: dict[str, frozenset] = {
    "v_packet": frozenset({"shape_family", "stock_basis"}),
    "v_lab": frozenset({"lab_results"}),
    "v_stage": frozenset(),
}


def subsumed_rules(sql: str) -> set:
    """Rule names that must not be applied because a view already encodes them."""
    out: set = set()
    for name in referenced(sql):
        out |= SUBSUMES.get(name, frozenset())
    return out


# Words that follow a table name but are NOT an alias.
_NOT_AN_ALIAS = {
    "where", "join", "inner", "left", "right", "full", "outer", "cross",
    "on", "group", "order", "having", "union", "except", "intersect",
    "with", "for", "option", "as", "and", "or", "pivot", "unpivot",
}

_REF_RE = re.compile(
    r"(?P<kw>(?:FROM|JOIN)\s+)(?P<view>v_[a-z_]+)(?P<tail>\s+(?:AS\s+)?(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)


def referenced(sql: str) -> list[str]:
    """The curated views this SQL reads, in the order they appear."""
    seen: list[str] = []
    for m in _REF_RE.finditer(sql or ""):
        name = m.group("view").lower()
        if name in VIEWS and name not in seen:
            seen.append(name)
    return seen


def inline_views(sql: str) -> str:
    """Replace every v_* reference with its definition as a derived table.

    A derived table MUST carry an alias in T-SQL, so the model's own alias is
    reused when it wrote one and the view name is used when it did not.
    Unknown v_* names are left untouched - the database will reject them with a
    normal invalid-object error, which is a better message than anything this
    could invent.
    """
    if not sql:
        return sql

    def _sub(m: re.Match) -> str:
        name = m.group("view").lower()
        if name not in VIEWS:
            return m.group(0)
        body = VIEWS[name].strip()
        alias = m.group("alias")
        if alias and alias.lower() in _NOT_AN_ALIAS:
            alias = None
        if alias:
            return f"{m.group('kw')}({body}) AS {alias}"
        tail = m.group("tail") or ""
        return f"{m.group('kw')}({body}) AS {name}{tail}"

    return _REF_RE.sub(_sub, sql)

# What the model is told. Deliberately SHORT: it goes in the byte-stable head,
# where every token is paid on every question, and the point of a view is that
# it needs no explaining. Names and grain only - the traps each one removes are
# documented in this file for humans, not re-argued at the model.
_DESCRIPTION = """=== CURATED VIEWS - PREFER THESE OVER THE RAW TABLES ===
Query these exactly like a table. Each is a safe, pre-joined reading that
already handles the traps the raw tables carry, so a straightforward query
against a view is correct. Nothing is filtered out of them - flags are columns,
so you decide what to exclude. The raw tables remain available for anything
these do not cover.

v_packet - ONE ROW PER PACKET.
  PacketId, KapanName, PacketNo, ShapeCode, Shape, Color, Clarity, Carats,
  PolishedCarats, CurrentProcess, IsInStock, IsOnHold, CurrentDepartment,
  CreatedOn
  Shape is NORMALISED: F.OV / S.OV / OVM all read as 'OV', so Shape='OV' is the
  whole oval family. ShapeCode keeps the raw stored value. IsOnHold is resolved
  at KAPAN level.

v_lab - ONE ROW PER PACKET PER LAB STAGE (GIA/HRD/IGI only).
  PacketId, KapanId, LabStage, CertifyingLab, EmpId, IsApproved, SentOn
  Period-filter on SentOn. COUNT(*) is safe here.

v_stage - THE LATEST PLAN ROW PER PACKET PER STAGE (no stage-row inflation).
  PacketId, KapanId, Stage, EmpId, IsApproved, IsDamagePlan, PolishedCarats,
  StageDate
  Count packets with COUNT(DISTINCT PacketId)."""


def describe() -> str:
    """The view catalogue, as the model sees it."""
    return _DESCRIPTION
