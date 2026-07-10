"""
test_regression_datamodel.py
----------------------------
REGRESSION LOCK for the data-model fixes (the "Layer 1" safety net).

Every audit pass fixed real WRONG-ANSWER bugs by encoding knowledge into the
prompt context (app/schema/glossary.py) and deterministic guards
(app/agent/tools.py, app/agent/postprocess.py). Those fixes are PROVIDER-
INDEPENDENT: Claude, Groq and Gemini all receive the same guidance and run
through the same guards. So this file asserts, WITHOUT calling any LLM, that
each fix is still in place — at the layer it actually operates:

  1. the trap-table filter still blocks stale/fake tables       (pure regex)
  2. the critical guidance is still present in the glossary      (pure text)
  3. the router still surfaces the right tables for a topic      (mocked schema)
  4. the anti-fabrication guard still rejects invented data      (pure logic)

What this PROVES: the mechanism of every fix survives on ANY provider, so these
bugs cannot silently reappear via a glossary/guard edit. What it does NOT prove:
that the model writes perfect SQL from correct guidance (that needs a live model
run). Locking the guidance is most of that battle — the model already produced
correct answers from it on the weaker Groq model.

Run: python -m pytest tests/test_regression_datamodel.py -q
"""

import pytest

from app.agent.postprocess import _UNGROUNDED_MSG, enrich, looks_like_data_table
from app.agent.tools import _is_trap_table
from app.schema import router
from app.schema.context import KEY_TABLES
from app.schema.glossary import (
    DATA_NOTES,
    JOIN_HINTS,
    TABLE_NOTES,
    render_data_notes,
    render_glossary_text,
)


# ---------------------------------------------------------------------------
# 1. Trap-table filter (pure regex — app/agent/tools.py::_is_trap_table)
#    Bug it prevents: querying stale/partial/FAKE variants (e.g. the 45k-row
#    tblTimeAttendance_Demo) instead of the real table.
# ---------------------------------------------------------------------------
TRAP_TABLES = [
    "tblTimeAttendance_Demo",
    "tblPacket_BKP",
    "tblPlanMasterEdit",
    "tblLabourResult_Compare",
    "tblPacket_Update",
    "tblFinalPacket_Temp",
    "tblLabourResultGIA",
]
REAL_TABLES = [
    "tblPacket",
    "tblPointRateLabour",
    "tblFinalPacket",
    "tblEmployee",
    "tblRepairCommentVision",
]


@pytest.mark.parametrize("name", TRAP_TABLES)
def test_trap_tables_are_blocked(name):
    assert _is_trap_table(name) is True, f"{name} should be treated as a trap table"


@pytest.mark.parametrize("name", REAL_TABLES)
def test_real_tables_are_not_blocked(name):
    assert _is_trap_table(name) is False, f"{name} is a real table and must NOT be filtered"


# ---------------------------------------------------------------------------
# 2. Critical guidance present in the glossary (pure text — no DB, no LLM).
#    These notes are always appended to the prompt for EVERY provider, so their
#    presence is what keeps the confident-wrong-answer bugs fixed on Claude too.
# ---------------------------------------------------------------------------
# Every free-text guidance string the agent sees (data notes + tricky joins +
# per-table meanings). We assert a fix's identifier and its meaning co-occur in
# ONE note, so the check is robust to reordering but still catches a deletion.
_ALL_NOTES = list(DATA_NOTES) + list(JOIN_HINTS) + [v["note"] for v in TABLE_NOTES.values()]


def _note_has(token: str, *keywords: str) -> bool:
    """True if some single note contains `token` AND at least one of `keywords`."""
    return any(token in n and any(k in n for k in keywords) for n in _ALL_NOTES)


def test_labour_current_vs_dead_table_guidance():
    # Bug: earnings/labour routed to tblLabourResult (dead ~Feb 2023) -> empty for
    # recent years. Fix: tblPointRateLabour is CURRENT; tblLabourResult is OLD.
    assert _note_has("tblPointRateLabour", "CURRENT")
    assert _note_has("tblLabourResult", "OLD", "HISTORICAL")


def test_repair_is_not_the_crud_log():
    # Bug: "how many repaired" hit tblRepairLog (a DB audit log) -> 7,753 vs the
    # correct 47 from tblRepairCommentVision.
    assert any("tblRepairCommentVision" in n for n in _ALL_NOTES)
    assert _note_has("tblRepairLog", "audit", "log", "NOT")


def test_sales_data_is_flagged_empty():
    # Bug: fabricating sales figures. Fix: the only sales table is empty -> say so.
    assert _note_has("tblPacketSell", "EMPTY", "NOT tracked", "not tracked")


def test_employee_identity_join_and_group_by():
    # Bug: grouping bonus by NAME merged up to 9 different people. Fix: join the
    # numeric id and GROUP BY it.
    assert _note_has("tblEmployee.ID", "GROUP BY")


def test_attendance_is_flagged_unreliable():
    # Bug: per-employee attendance returned wrong/empty. Fix: EmpId is NULL, so
    # it's not reliably answerable — say so instead of inventing.
    assert _note_has("tblTimeAttendance", "NULL", "not reliabl", "EmpId")


def test_incentive_uses_points_not_dead_amount():
    # Bug: incentive read the Credit/Debit ₹ columns (dead since 2019). Fix: use
    # the CreditPoints ledger.
    assert _note_has("CreditPoints", "POINTS", "points")


def test_count_distinct_guidance_present():
    # Bug: COUNT(*) on transactional tables inflated counts (~34 rows/packet).
    assert any("COUNT(DISTINCT" in n for n in _ALL_NOTES)


def test_glossary_not_gutted():
    # A blunt backstop: the guidance block is ~45k chars. If an edit accidentally
    # truncates it, per-note tests might pass while most guidance vanished.
    combined = render_glossary_text() + render_data_notes()
    assert len(combined) > 30_000, "glossary/data-notes shrank drastically — guidance may have been dropped"


# ---------------------------------------------------------------------------
# 3. Router surfaces the right tables for a topic (app/schema/router.py).
#    DB-free: mock the one call that reads columns from the DB, so scoring runs
#    on the (static) table-name + glossary-note keywords. This guards that a
#    topically-correct table is still REACHABLE (in KEY_TABLES and selected);
#    the current-vs-dead disambiguation itself lives in the notes above, not here.
# ---------------------------------------------------------------------------
@pytest.fixture()
def router_no_db(monkeypatch):
    monkeypatch.setattr(router, "_key_columns", lambda: {t: [] for t in KEY_TABLES})


def test_router_surfaces_packet_table(router_no_db):
    assert "tblPacket" in router.select_tables("how many packets are there in total?", k=6)


def test_router_surfaces_labour_table(router_no_db):
    picked = router.select_tables("total labour paid to workers this year", k=6)
    assert "tblPointRateLabour" in picked


def test_router_surfaces_attendance_table(router_no_db):
    assert "tblTimeAttendance" in router.select_tables("employee attendance and time", k=6)


# ---------------------------------------------------------------------------
# 4. Anti-fabrication guard (app/agent/postprocess.py::enrich). Deterministic
#    backstop: a data table with no run_sql behind it is invented -> replaced
#    with an honest message. Provider-independent by construction.
# ---------------------------------------------------------------------------
_FAKE_TABLE = "Here are the results:\n\n| Name | Bonus |\n| --- | --- |\n| A | 100 |\n| B | 200 |"


def test_guard_rejects_ungrounded_data_table():
    # A markdown table but NO sql/rows behind it -> fabricated -> stripped.
    assert looks_like_data_table(_FAKE_TABLE) is True
    out = enrich({"answer": _FAKE_TABLE, "sql_used": [], "rows_returned": 0, "data_rows": []})
    assert out["ok"] is False
    assert out["answer"] == _UNGROUNDED_MSG
    assert out["data_rows"] == [] and out["export_query"] is None


def test_guard_allows_grounded_data_table():
    # Same table, but a query DID return the rows -> legitimate, pass through.
    out = enrich({
        "answer": _FAKE_TABLE,
        "sql_used": ["SELECT Name, Bonus FROM x"],
        "rows_returned": 2,
        "data_rows": [{"Name": "A", "Bonus": 100}, {"Name": "B", "Bonus": 200}],
        "data_columns": ["Name", "Bonus"],
    })
    assert out["ok"] is True
    assert "| Name | Bonus |" in out["answer"]


def test_guard_allows_file_grounded_answer():
    # A table can legitimately come from an uploaded file (not the DB).
    out = enrich({
        "answer": _FAKE_TABLE,
        "sql_used": [],
        "rows_returned": 0,
        "data_rows": [],
        "file_grounded": True,
    })
    assert out["ok"] is True
