"""
test_sql_guard_stale_copies.py
------------------------------
The BACKUP/DEMO/EDIT table block, and — just as important — proof that it does
not reject anything that used to work.

WHAT THIS PROTECTS
------------------
tblPacket_BKP holds 71,715 rows against tblPacket's 168,763. tblTimeAttendance_
Demo holds 45,636 rows of fabricated attendance against the real table's 393,882.
A query against either returns a number that looks entirely plausible, so an
answer built on one is confidently wrong in a way no reader can catch.

extractor.is_trap_table() already keeps these out of find_tables() and out of the
schema router, so the model cannot DISCOVER one. Nothing stopped it naming one
from memory: before this guard, run_select("SELECT COUNT(*) FROM
tblLabourResultGIA") returned 121,337 rows quite happily. The RULES block forbids
it in prose — a probabilistic guard costing ~230 tokens on every model call.

THE FALSE-POSITIVE HALF IS THE POINT
------------------------------------
A guard like this is only safe if it can be shown to reject NOTHING that used to
work. The corpus below is every ground-truth query in cold_cases.py (26 queries
hand-written and run against the real database) plus the department-report recipe
plus the app's own fixed queries. When this guard was written it was additionally
checked against 208 distinct SELECT statements recovered from logs/agent.log —
real SQL the model had actually executed — with zero false positives. Those live
in the log rather than the repo, so the in-repo corpus is the permanent lock.

If a future change to _TBL_REF_RE or to _TRAP_TABLE_RE starts rejecting good
SQL, test_no_false_positives_on_known_good_sql fails before it reaches a user.
"""
from __future__ import annotations

import re

import pytest

from app.core.sql_guard import _primary_of, selects_stale_copy, validate_and_prepare
from scripts.cold_cases import COLD_CASES

# Every trap table observed in the 2026-07-27 client backup. Hard-coded rather
# than read from the DB so the test runs without one, and so a table
# disappearing from a future refresh does not silently shrink the coverage.
TRAP_TABLES = [
    "tblKapan_BKP",
    "tblLabourResultEdit",
    "tblLabourResultGIA",
    "tblLabourResultGIAEdit",
    "tblLabourResult_Compare",
    "tblPacketColorAnalysisTemp",
    "tblPacketGenerateTemp",
    "tblPacketPointGIA",
    "tblPacket_BKP",
    "tblPlanMaster_Update",
    "tblPlanReport_BKP",
    "tblTestGXKapanPricePlanMaster",
    "tblTestKapanPricePlanMaster",
    "tblTimeAttendance_Demo",
]


@pytest.mark.parametrize("table", TRAP_TABLES)
def test_every_trap_table_is_blocked(table):
    ok, reason = validate_and_prepare(f"SELECT COUNT(*) AS n FROM {table} WITH (NOLOCK)")
    assert not ok, f"{table} reached the database"
    assert table in reason


@pytest.mark.parametrize(
    "sql",
    [
        # The plain form, and every way a model has been seen to write a table
        # reference. An anchored FROM/JOIN pattern would miss the last three.
        "SELECT * FROM tblPacket_BKP",
        "SELECT * FROM [tblPacket_BKP]",
        "SELECT * FROM dbo.tblPacket_BKP",
        "SELECT * FROM tblpacket_bkp",                       # case-insensitive
        "SELECT p.* FROM tblPacket p JOIN tblPacket_BKP b ON b.ID = p.ID",
        "SELECT * FROM tblKapan k, tblKapan_BKP b WHERE k.ID = b.ID",   # comma join
        "SELECT * FROM tblPacket WHERE ID IN (SELECT ID FROM tblTimeAttendance_Demo)",
        "WITH x AS (SELECT ID FROM tblPlanReport_BKP) SELECT COUNT(*) FROM x",
    ],
)
def test_trap_table_cannot_be_reached_by_any_syntax(sql):
    ok, reason = validate_and_prepare(sql)
    assert not ok, f"leaked: {sql}"
    assert "backup/demo/edit copy" in reason


# --- the false-positive half -------------------------------------------------

def _known_good_sql() -> list[str]:
    """Every query in the repo that is known to be correct and must keep working."""
    out = [c["truthSql"] for c in COLD_CASES if c.get("truthSql")]
    for path in ("app/agent/reports.py", "app/agent/tools.py", "app/api/main.py"):
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        for m in re.finditer(r'"""\s*(SELECT.*?)"""', body, re.S):
            out.append(m.group(1))
        for m in re.finditer(r'f?"(SELECT [^"]{20,400})"', body, re.S):
            out.append(m.group(1))
    return [s for s in out if s.strip()]


def test_no_false_positives_on_known_good_sql():
    """Not one known-good query may be rejected. This is the safety contract."""
    good = _known_good_sql()
    assert len(good) >= 30, "corpus unexpectedly small - did a source file move?"
    rejected = [(s, selects_stale_copy(s)) for s in good if selects_stale_copy(s)]
    assert not rejected, "guard rejects known-good SQL:\n" + "\n".join(
        f"  {r}\n    <- {s[:160]}" for s, r in rejected
    )


@pytest.mark.parametrize(
    "label,sql",
    [
        # The one that matters most: 'GIA' is a legitimate VALUE in RapVer (the
        # lab-certification stage). Only a TABLE name ending in GIA is a copy.
        ("GIA as a value", "SELECT COUNT(*) FROM tblPlanMaster WHERE RapVer IN ('GIA','HRD','IGI')"),
        # A live table whose name merely contains GIA in the middle.
        ("tblEmpGIABonus", "SELECT TOP 5 * FROM tblEmpGIABonus"),
        # is_trap_table() also matches a leading 'temp'; scanning only
        # tbl-prefixed identifiers is what keeps a CTE named temp legal.
        ("CTE named temp", "WITH temp AS (SELECT ID FROM tblKapan) SELECT COUNT(*) FROM temp"),
        ("alias named t", "SELECT t.KapanName FROM tblKapan t WHERE t.IsOnHold = 1"),
        ("live labour table", "SELECT SUM(BonusAmount) FROM tblPointRateLabour"),
        ("live attendance", "SELECT COUNT(*) FROM tblTimeAttendance"),
        ("superseded but REAL", "SELECT COUNT(*) FROM tblLabourResult"),
    ],
)
def test_near_misses_are_still_allowed(label, sql):
    assert not selects_stale_copy(sql), f"{label} was wrongly blocked"


# --- the redirect hint -------------------------------------------------------

def test_hint_names_the_primary_table():
    reason = selects_stale_copy("SELECT * FROM tblPacket_BKP")
    assert "tblPacket'" in reason, "the model needs to be told what to use instead"


def test_hint_never_points_at_another_blocked_table():
    """tblLabourResultGIAEdit carries TWO markers. Stripping only the last one
    suggested tblLabourResultGIA — itself a trap — so the model would fix its
    SQL and be blocked again, burning a correction round for nothing."""
    from app.schema.extractor import is_trap_table

    for table in TRAP_TABLES:
        primary = _primary_of(table)
        assert not (primary and is_trap_table(primary)), (
            f"{table} redirects to {primary}, which is also blocked"
        )


def test_read_only_check_still_runs_first():
    """A write is rejected as a write, not as a stale copy — the messages tell
    an operator two different things and must not be confused."""
    ok, reason = validate_and_prepare("DELETE FROM tblPacket_BKP")
    assert not ok
    assert "Only SELECT" in reason or "Forbidden keyword" in reason
