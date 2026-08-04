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

from app.agent.postprocess import (
    _UNGROUNDED_MSG,
    enrich,
    export_query,
    looks_like_data_table,
)
from app.agent.tools import _is_trap_table
from app.schema import router
from app.schema.context import KEY_TABLES
from app.schema.glossary import (
    DATA_NOTES,
    JOIN_HINTS,
    TABLE_NOTES,
    VALUE_CODES,
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
    # Clone/scratch tables found in the 2026-07-27 client refresh.
    "tblTestKapanPricePlanMaster",
    "tblTestGXKapanPricePlanMaster",
    "tempCross",
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
# VALUE_CODES is included too: the RunningProcess/stage decode lives there and is
# just as load-bearing as a data note (it drives every "where are the stones" answer).
_ALL_NOTES = (
    list(DATA_NOTES)
    + list(JOIN_HINTS)
    + [v["note"] for v in TABLE_NOTES.values()]
    + list(VALUE_CODES.values())
)


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


def test_damage_count_records_and_type_split():
    # Bug (2026-07): "how many damage" returned COUNT(DISTINCT KapanName) (~20/mo)
    # AND merged the two InceDamageTypeName categories into one number. Fix: count
    # RECORDS (rows), and always split DAMAGE vs REPORT so the client's official
    # figure is visible and the answer can't be silently wrong.
    assert _note_has("InceDamageTypeName", "DAMAGE", "REPORT")
    # The guidance must explicitly warn OFF counting distinct kapans.
    assert any(
        "InceDamageTypeName" in n and "DISTINCT" in n and "Kapan" in n
        for n in _ALL_NOTES
    ), "damage-count guidance must say COUNT rows, NOT COUNT(DISTINCT Kapan...)"


def test_clarify_ambiguous_employee_role_guidance():
    # Bug (2026-07, client meeting): "GIA results ... employee wise" was silently
    # grouped by the UPLOAD clerk (tblFinalPacket.UserID) instead of the Fency
    # worker the client meant. Fix: teach the 3 employee roles + tell the model to
    # ASK or DECLARE which role, and never default to the upload clerk.
    assert _note_has("tblFinalPacket.UserID", "upload", "UPLOAD", "clerk")
    assert any(
        "Fency" in n and "employee-wise" in n.lower()
        for n in _ALL_NOTES
    ), "GIA employee-wise ambiguity (3 roles + Fency) must be documented"


def test_count_distinct_guidance_present():
    # Bug: COUNT(*) on transactional tables inflated counts (~34 rows/packet).
    assert any("COUNT(DISTINCT" in n for n in _ALL_NOTES)


def test_export_query_prefers_detail_over_trailing_aggregate():
    # Bug (2026-07): a "Fency production" answer LISTED 305 packets, then ran a
    # COUNT/SUM for its summary line. export_query took the LAST select (the
    # aggregate), so a reopened-thread export re-ran the 1-row summary instead of
    # the 305-packet list — breaking the "full list available to download" promise.
    detail = ("SELECT KapanName, PacketNo AS Packet, Shape FROM tblFinalPacket "
              "WHERE PacketID IN (SELECT Packet_ID FROM tblPointRateLabour "
              "WHERE DepartmentName='Fency') AND CreateDate >= '2026-06-01'")
    summary = ("SELECT COUNT(PacketID) AS n, SUM(CurrentWt) AS ct FROM tblFinalPacket "
               "WHERE CreateDate >= '2026-06-01'")
    # The detail listing must win, regardless of order.
    assert export_query([detail, summary]) == detail
    assert export_query([summary, detail]) == detail
    # A genuine summary-only answer still exports its aggregate (nothing else to use).
    assert export_query([summary]) == summary
    # No SELECT at all -> nothing to export.
    assert export_query(["UPDATE x SET y=1"]) is None


def test_detail_by_default_guidance():
    # Bug (2026-07, client): "Fency department production output" answered with a
    # lone COUNT/SUM ("305 packets, 76.16 ct") and threw away the 305 packet rows
    # the client actually wanted ("which packet"). Fix lives in TWO layers:
    #   (a) an always-on RULES bullet biasing to a DETAIL listing + summary line,
    #   (b) a concrete PRODUCTION note with the packet-list query + dept filter.
    from app.agent.tools import RULES

    assert "DETAIL BY DEFAULT" in RULES, "the always-on detail-listing rule is missing"
    # It must warn OFF answering with a bare aggregate and cover output/results.
    assert "lone COUNT/SUM" in RULES or "bare total" in RULES
    assert all(w in RULES for w in ("OUTPUT", "RESULTS", "PRODUCTION"))

    # The PRODUCTION note must tell it to LIST finished packets and how to scope a
    # department (via tblPointRateLabour), not just how to GROUP BY.
    assert _note_has("PRODUCTION", "LIST", "packet list", "PACKET LIST")
    assert any(
        "tblFinalPacket" in n and "PacketID IN" in n and "tblPointRateLabour" in n
        for n in _ALL_NOTES
    ), "production detail must scope a department by its packets (PacketID IN ...)"


# --- 2026-07-27 DB-refresh sweep: 9 domains, 139 verified facts ---------------
# Each test below locks ONE fact the live DB proved, so a refresh/edit can't
# silently reintroduce the wrong-answer bug it prevents.


def test_planmaster_is_the_stage_pipeline():
    # Bug: tblPlanMaster was described as just "the cutting plan", so the bot
    # answered GIA questions from tblFinalPacket (wrong table, far too thin).
    assert _note_has("RapVer", "one row per packet per STAGE")
    assert _note_has("tblPlanMaster", "CreatDate")


def test_gia_report_is_pls_vs_gia_dual_grade():
    # The client's own report shape: in-house PLS grade next to the lab GIA grade.
    assert _note_has("RapVer='PLS'", "RapVer='GIA'")
    assert _note_has("HasChange", "regrades", "change flag")


def test_gia_stage_is_not_gia_certified():
    # ~34% of RapVer='GIA' rows are LAB='NONE' (graded in-house, never certified).
    assert _note_has("LAB='GIA'", "NONE", "CERTIFIED", "certified")


def test_gia_employee_wise_uses_latest_mfg_maker():
    # G001 entered 150,078/150,080 GIA rows -> grouping there returns ONE name.
    assert _note_has("G001", "150,078")
    assert _note_has("MAX(ID)", "MFG")


def test_fency_workers_are_vendor_firms():
    assert _note_has("Fency", "VENDOR FIRMS", "job-work parties")


def test_approvedate_is_a_date_trap():
    # ApproveDate is NULL on ~96% of GIA rows -> always filter on CreatDate.
    assert _note_has("ApproveDate", "NULL", "CreatDate")


def test_finallabour_is_all_in():
    # FinalLabour ALREADY contains BonusAmount — adding both double-counts pay.
    assert _note_has("FinalLabour", "ALL-IN")


def test_labour_posted_in_arrears():
    assert _note_has("tblPointRateLabour", "ARREARS", "arrears")


def test_data_cutoff_note_present():
    # The DB is a restored backup: "today" can return 0 rows from staleness.
    assert _note_has("RESTORED BACKUP", "cutoff")


def test_attendance_feed_is_dead():
    assert _note_has("tblTimeAttendance", "2025-04-05")


def test_junk_dates_use_createdate_not_issuedate():
    assert any("tblJunk->CreateDate" in n for n in _ALL_NOTES)
    assert not any("tblJunk->IssueDate" in n for n in _ALL_NOTES)


def test_runningprocess_values_corrected():
    # 'MFG - 1' really has spaces; there is no plain 'Marker' value.
    assert _note_has("MFG - 1", "SPACES", "spaces")
    assert _note_has("Marker-2", "NO plain 'Marker'")


def test_kapan_avgsize_is_average_stone_size():
    assert _note_has("AvgSize", "AVERAGE STONE")


def test_jangad_partial_receives():
    # Header Pcs/Carats ~2x overstate what is really out; sum the packet lines.
    assert _note_has("IsReceived", "PARTIAL")


def test_jangad_party_depends_on_direction():
    # GROUP BY ToParty over all rows wrongly makes GLOW STAR the top party.
    assert _note_has("ToParty", "GLOW STAR")


def test_dummy_employees_excluded():
    assert _note_has("EXTRA TRY", "dummy", "DUMMY")


def test_pctchecker_is_partial():
    # A missing tblPctChecker row is normal — not "nobody made it".
    assert _note_has("tblPctChecker", "PARTIAL") or _note_has("PARTIAL", "35-50%")


def test_finalpacket_grades_are_in_house_not_lab():
    assert _note_has("IN-HOUSE", "frozen at entry", "regrades")


def test_stock_report_is_kapan_weight_reconciliation():
    # Client's stock report = kapan-wise weight reconciliation (stock wt, current wt,
    # rwt, tops, rej wt, w loss) — the bot used to dump 30 random packet rows.
    assert _note_has("STOCK", "RECONCILIATION", "reconciliation")
    assert _note_has("IsRejected", "RejectionWt", "rejection")


def test_finalpacket_weight_columns_are_dead():
    # RoughWt/WeightLoss/Tops are 100% NULL on tblFinalPacket -> selecting them
    # renders a report with blank columns. Yield must come from tblPacket.
    assert _note_has("tblFinalPacket", "100% NULL") or _note_has("Tops", "100% NULL")
    assert _note_has("SUM(p.RoughWt)", "k.Weight")


def test_wip_in_process_report_guidance():
    # Client ERP screen: "how many diamonds are manufactured / in process and in
    # WHICH DEPARTMENT". Live snapshot from tblPacket: 'IN Stock' = finished, any
    # other RunningProcess = work in process; department via DepartMentId.
    assert _note_has("WIP", "IN-PROCESS", "in process")
    assert _note_has("DepartMentId", "tblDepartMent")
    assert _note_has("RunningProcess", "TERMINAL", "FINISHED")


def test_location_is_operational_not_geographic():
    # Client asked "where is the diamond now - maybe Mumbai". Verified: the company,
    # every department and all 54 job-work parties are SURAT; 'MUMBAI' exists only as
    # a rough SUPPLIER's city. Packet location is stage/party, never a city.
    assert _note_has("MUMBAI", "SUPPLIER", "supplier")
    assert _note_has("WHERE IS THIS DIAMOND", "not tracked", "NOT tracked")


def test_unknown_question_ladder_present():
    # The systemic fix: never dead-end. Search first, admit the gap in one line,
    # then give the nearest real data.
    from app.agent.tools import RULES

    assert "UNKNOWN / NOT-TRACKED QUESTIONS" in RULES
    assert "NEAREST" in RULES.upper()
    assert "find_tables" in RULES


def test_unanswered_questions_are_logged():
    # Each unanswerable question must land in the log as a to-do, not vanish.
    from app.core.logging_util import log_unanswered

    assert log_unanswered("is it in mumbai", "The system does not record the city.", 0) is True
    assert log_unanswered("june production", "There were 4007 packets.", 4007) is False


def test_maker_fresh_vs_check_issue_guidance():
    # Client ERP screens "maker fresh" / "check issue". Verified: the real log is
    # tblIssuedPacketDetail.IsFresh; CHECK issue stopped 2024-11-19 (0 since), and
    # the header tblIssuedPacket.CheckIssued/PctIssued counters are dead.
    assert _note_has("IsFresh", "FRESH")
    assert _note_has("tblIssuedPacketDetail", "2024-11")
    assert _note_has("tblIssuedPacket", "dead", "never total")


def test_issue_report_supports_both_grains():
    # Must NOT be hardcoded to department-wise: the same table answers
    # department-wise AND employee-wise; the agent picks from the question.
    assert _note_has("tblPacketIssue", "COUNT(DISTINCT Packet_ID)")
    assert _note_has("BOTH grains", "employee-wise")
    assert _note_has("Marker", "MFG-1..6", "karigars")


def test_report_grain_is_chosen_from_the_question():
    # The general rule behind it: never assume one fixed breakdown.
    from app.agent.tools import RULES

    assert "REPORT GRAIN" in RULES
    assert "employee wise" in RULES and "department wise" in RULES
    assert "SHOW BOTH" in RULES


def test_stale_snapshot_examples_removed():
    # Old-backup artifacts must not survive a refresh edit.
    assert not any("2026-05-30" in n for n in _ALL_NOTES)
    assert not any("132 damage records" in n for n in _ALL_NOTES)


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


# ---------------------------------------------------------------------------
# 5. Date picker (ASKDATE): a report question with no period must ASK via the
#    UI picker instead of silently guessing a range or dumping all history.
# ---------------------------------------------------------------------------
def test_askdate_marker_is_extracted_and_stripped():
    from app.agent.postprocess import extract_askdate

    clean, asked = extract_askdate("Which period should I use?\nASKDATE:")
    assert asked is True
    assert "ASKDATE" not in clean  # the marker must never reach the user
    assert clean == "Which period should I use?"

    clean2, asked2 = extract_askdate("Here are the 305 packets.")
    assert asked2 is False and clean2 == "Here are the 305 packets."


def test_enrich_exposes_ask_date_flag():
    out = enrich({"answer": "Which period?\nASKDATE:", "sql_used": [], "rows_returned": 0, "ok": True})
    assert out["ask_date"] is True
    assert "ASKDATE" not in out["answer"]
    # A normal data answer must NOT trigger the picker.
    normal = enrich({"answer": "Total is 305.", "sql_used": ["SELECT 1"], "rows_returned": 1, "ok": True})
    assert normal["ask_date"] is False


def test_date_picker_rule_present_in_rules():
    from app.agent.tools import RULES

    assert "ASKDATE:" in RULES, "the date-picker rule is missing from the always-on RULES"
    assert "DATE PICKER" in RULES


def test_thin_answer_backstop_shows_the_data():
    # THE failure the client kept seeing: the model writes prose ABOUT a table it
    # never printed ("the makers listed above..."), or nothing at all, even though
    # the query returned rows. Deterministic backstop: render the rows ourselves.
    from app.agent.postprocess import ensure_data_shown

    cols = ["Maker", "Packets"]
    rows = [{"Maker": "MAHADEV JEMS", "Packets": 808}]

    # prose with no table -> the real rows get appended
    assert "MAHADEV JEMS" in ensure_data_shown("The makers listed above.", cols, rows, False)
    # empty answer -> still shows the data
    assert "MAHADEV JEMS" in ensure_data_shown("", cols, rows, False)
    # already has a table -> untouched (no duplication)
    already = "| A | B |\n|---|---|\n| 1 | 2 |"
    assert ensure_data_shown(already, cols, rows, False) == already
    # a DASHBOARD carries its own tables -> don't duplicate
    assert ensure_data_shown("See dashboard.", cols, rows, True) == "See dashboard."
    # no rows -> nothing invented
    assert ensure_data_shown("No data.", cols, [], False) == "No data."


def test_report_style_matches_the_client_erp():
    # Learned from the ONE query the client shared: their reports are WIDE
    # (~20 cols), show two gradings SIDE BY SIDE, and carry a derived comparison
    # flag (HasChange). Our old rule capped answers at "~4-8 columns", which is
    # exactly why our output looked thin next to their ERP.
    from app.agent.tools import RULES

    assert "MATCH THEIR REPORT STYLE" in RULES
    assert "10-20" in RULES and "do NOT trim to 4-8" in RULES
    assert "SIDE-BY-SIDE" in RULES
    assert "DERIVED COLUMN" in RULES
    # the old cap must be gone, or the model will keep trimming
    assert "reasonable ~4-8 columns" not in RULES


def test_entity_report_is_a_full_profile():
    # Client asked "past month report of employee M4117" and their ERP shows the
    # whole profile — including how many diamonds he MANUFACTURED. Our answer gave
    # only damage + bonus + incentive. A named-entity report must cover every area.
    from app.agent.tools import RULES

    assert "360 PROFILE" in RULES or "FULL 360" in RULES
    assert "PRODUCTION / MANUFACTURED" in RULES
    assert "PROCESSES HANDLED" in RULES
    assert "BONUS + INCENTIVE" in RULES
    # must not leak salary while doing it
    assert "NEVER salary/FinalLabour" in RULES
    # generalises beyond employees
    assert "KAPAN:" in RULES and "DEPARTMENT:" in RULES


def test_production_report_names_maker_and_department():
    # Client complaint: "report of all diamonds processed" returned packet columns
    # only. Their report also shows WHO made it and WHICH department — and
    # tblFinalPacket has neither column, so it must be joined via the latest
    # MFG-stage row (verified 100% coverage: 4,007/4,007 packets in June 2026).
    assert _note_has("MAKER AND DEPARTMENT", "tblFinalPacket")
    assert _note_has("OUTER APPLY", "RapVer='MFG'")
    assert _note_has("DepartMentName", "Maker")


def test_data_is_shown_even_when_the_writeup_fails():
    # The inconsistency the client saw: the model runs the right query, then
    # writes prose about the data ("production trend shows a surge") with NO
    # table. Worst case is a provider hiccup AFTER a good query — previously the
    # backstop was gated on ok=True and stayed silent exactly then.
    cols = ["ProductionDate", "Packets"]
    rows = [{"ProductionDate": "2026-06-01", "Packets": 84}]

    prose = enrich({"answer": "The production trend shows a mid-month surge.",
                    "sql_used": ["SELECT 1"], "rows_returned": 26, "ok": True,
                    "data_columns": cols, "data_rows": rows})
    assert "2026-06-01" in prose["answer"], "prose-only answer must show the rows"

    failed_writeup = enrich({"answer": "I fetched the data but couldn't write the summary.",
                             "sql_used": ["SELECT 1"], "rows_returned": 26, "ok": False,
                             "data_columns": cols, "data_rows": rows})
    assert "2026-06-01" in failed_writeup["answer"], (
        "a failed write-up after a good query must still show the data"
    )

    # ...but never invent data: no query -> the ungrounded guard still wins.
    ungrounded = enrich({"answer": "| A | B |\n|---|---|\n| 1 | 2 |", "sql_used": [],
                         "rows_returned": 0, "ok": True,
                         "data_columns": [], "data_rows": []})
    assert ungrounded["answer"] == _UNGROUNDED_MSG


def test_superlative_claims_are_checked_against_the_data():
    # COLD-TEST finding (unseen question): asked which colour grade is most
    # common, the model answered "F, closely followed by G" while the data had
    # G first (34,078 vs 28,405). The table was right; the SENTENCE was wrong,
    # and the client reads the sentence.
    from app.agent.postprocess import superlative_mismatch
    from app.agent.tools import RULES

    cols = ["Color", "n"]
    rows = [{"Color": "G", "n": 34078}, {"Color": "F", "n": 28405},
            {"Color": "H", "n": 25982}]

    assert superlative_mismatch("The most common colour is **F**, then G.", cols, rows) == ("F", "G")
    # correct claims, non-claims and unrelated values must NOT be flagged
    assert superlative_mismatch("The most common colour is **G**.", cols, rows) is None
    assert superlative_mismatch("Here is the colour breakdown.", cols, rows) is None
    assert superlative_mismatch("The most common shape is RD.", cols, rows) is None

    # and the model is told to read superlatives off the ordered result
    assert "SUPERLATIVES COME FROM THE DATA" in RULES


def test_gia_defaults_to_all_lab_stage_rows_not_certified_only():
    # Manual client test: "GIA results of Fency employees" returned 120 packets /
    # 4 firms (arithmetically correct: LAB='GIA' certified only). But the CLIENT'S
    # own SQL filters on RapVer IN ('GIA','HRD','IGI') with NO LAB condition, so
    # their report shows 1,024 / 7 firms. A right number that doesn't match their
    # report reads as wrong in a meeting.
    assert _note_has("DEFAULT TO *ALL* LAB-STAGE ROWS", "DO NOT ADD A LAB FILTER")
    assert _note_has("1,024", "120")


def test_empty_quality_attributes_are_flagged():
    # Preparedness for questions never asked yet: tblPlanMaster has ~29 inclusion
    # /finish columns and 22 are effectively EMPTY. "How many milky stones?" must
    # say "not recorded" — reporting 0 would read as a real (wrong) answer.
    assert _note_has("Milky", "EFFECTIVELY EMPTY", "not recorded")
    assert _note_has("EyeClean", "EMPTY", "not recorded")
    # ...and the genuinely usable ones must stay usable
    assert _note_has("CutGrade", "USABLE")
    # the angle columns are TEXT RANGES — averaging them is wrong
    assert _note_has("CrAng", "RANGE", "ranges", "TEXT RANGES")


def test_dead_columns_are_flagged():
    # Proactive sweep (not client-reported): columns with useful-sounding names
    # that are 0-filled across ALL history. Querying one returns 0/blank and reads
    # as a real answer — the same shape as the Tops and CheckIssued bugs.
    #   tblJangad Rej/Loss*  : 0 of 16,498 rows  -> "no loss on jangad" (wrong)
    #   tblPacket.IsRepair   : never set; real register has 4,413 rows
    #   tblKapan.BoilLoss    : ALIVE (801/853) — must stay usable
    assert _note_has("RejCarats", "16,498", "NEVER ANSWER FROM THESE")
    assert _note_has("IsRepair", "4,413")
    assert _note_has("BoilLoss", "801", "populated")
    assert _note_has("SubPcs", "blank", "never count")


# --- 2026-07-31 proactive gap sweep: the five catastrophic traps ------------
# Found by sweeping the DB ourselves (no client input). Each would produce a
# confidently-WRONG number in a meeting; #5 was caused by our OWN guidance.

def test_kapan_value_is_a_per_carat_rate():
    # SUM(RoughValue)=73,230 vs the true SUM(Weight*RoughValue)=9,115,298 (124x).
    assert _note_has("PER-CARAT RATE", "SUM(Weight * RoughValue)", "124x")
    # and the estimate-accuracy trap: EstValue is a copy on 781 of 804 kapans
    assert _note_has("EstValue", "COPY")


def test_kapanvalue_is_a_daily_snapshot():
    # Summing it multiplies by the number of days: 16.9M ct vs 20,407 real.
    assert _note_has("NIGHTLY SNAPSHOT", "16,917,681", "829x")
    assert _note_has("tblKapanValue", "ROW_NUMBER", "latest snapshot")


def test_planmaster_must_not_be_summed_raw():
    # 173,353 rows cover only 27,803 packets -> 9x/6x overstatement.
    assert _note_has("27,803", "173,353")
    assert _note_has("COUNT(DISTINCT Packet_ID)", "RapVer")
    # tblRapVer is an incomplete lookup — joining it drops 12% of rows
    assert _note_has("tblRapVer", "21,027", "MISSING")


def test_jangad_direction_cannot_accuse_a_partner():
    # A naive GROUP BY ToParty reports "97.8% loss" at the client's biggest partner.
    assert _note_has("TransType", "301,427", "99.4%")
    assert _note_has("Issue", "Receive", "FromParty")


def test_depth_and_ratio_are_constants_not_measurements():
    # OUR OWN NOTE called these "USABLE" because they are 100% filled — but every
    # 2026 row holds Depth=60.0 / Ratio=1.0. Fill rate != usefulness.
    assert _note_has("CONSTANTS, NOT", "60.0")
    assert _note_has("tblPacketParameters", "62.93", "DepthPer")
    # the retracted claim must be GONE, or the model still trusts it
    assert not any("Depth (100%), Ratio (100%)" in n for n in _ALL_NOTES)
    # and the generalisable lesson is stated
    assert _note_has("COUNT(DISTINCT", "100% populated does NOT mean")


def test_letter_prefixed_employee_code_is_unambiguous():
    # Live failure (NVIDIA run): asked for "report of employee id M4117" the model
    # replied "do you mean Code M4117 or numeric ID 4117?" — a wasted turn. M4117
    # matches exactly one person and 2,431 of 2,450 codes are letter-prefixed.
    assert _note_has("LETTER PREFIX", "M4117")
    assert _note_has("2,431", "NO ambiguity", "spurious")
