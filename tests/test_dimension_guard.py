"""
test_dimension_guard.py
-----------------------
ANSWER-COMPLETENESS: if the user asked to break the data down by something, that
column must appear in the result.

The client hit this twice: "GIA results of Fency department EMPLOYEES" returned a
correct packet table with NO employee column — the maker was used to FILTER the
rows and then never displayed. Right numbers, wrong answer.

The guard must be TIGHT on real breakdown requests and SILENT on passing
mentions, because nagging would be worse than the original bug.
"""
import pytest

from app.agent.dimension_guard import followup_option, missing_dimensions

ROWS = [{"x": 1}]
GIA_COLS = ["KapanName", "PacketNo", "Shape", "PLS_Color", "GIA_Color", "PLS_Clarity"]


@pytest.mark.parametrize("question,columns,expected", [
    # the exact client question — no maker column in the result
    ("Provide past month GIA results of Fency department employees", GIA_COLS, "employee"),
    ("employee wise earnings for June", ["Total"], "employee"),
    ("show production by employee", ["Packets"], "employee"),
    ("which employee made the most packets", ["Packets"], "employee"),
    ("who made the most packets last month", ["Packets"], "employee"),
    ("department wise production", ["Packets", "Carats"], "department"),
    ("kapan wise yield", ["Yield"], "kapan"),
    ("give me daily production from 1 Jun to 30 Jun", ["Packets"], "date"),
])
def test_fires_when_the_named_dimension_is_missing(question, columns, expected):
    assert expected in missing_dimensions(question, columns, ROWS), question


@pytest.mark.parametrize("question,columns", [
    # counting the dimension is NOT breaking down by it
    ("how many employees do we have", ["Total"]),
    ("how many active employees are there", ["Total"]),
    ("number of employees in Fency", ["Total"]),
    # the column IS present -> nothing to offer
    ("Provide past month GIA results of Fency department employees",
     GIA_COLS + ["Maker", "DepartMentName"]),
    ("employee wise earnings", ["EmployeeName", "Total"]),
    ("department wise production", ["Department", "Packets"]),
    ("daily production", ["ProductionDate", "Packets"]),
    # KapanName must NOT read as an employee column (it contains "name")
    ("kapan wise production", ["KapanName", "Packets"]),
    # no breakdown requested at all
    ("total production for June", ["Packets", "Carats"]),
    ("which packets are in stock", ["KapanName", "PacketNo"]),
    ("what is a kapan", ["Definition"]),
    # a single named entity is not a per-X breakdown
    ("give me past month report of employee id M4117", ["Packets", "Carats"]),
])
def test_stays_silent_when_it_should(question, columns):
    assert missing_dimensions(question, columns, ROWS) == [], question


def test_silent_when_no_rows_were_returned():
    # An empty result is a different problem; don't stack a follow-up on top.
    assert missing_dimensions("employee wise earnings", ["Total"], []) == []
    assert missing_dimensions("employee wise earnings", ["Total"], None) == []


def test_followup_reads_as_a_complete_question():
    # Tapping the chip SENDS this text as the next question, so it must stand alone.
    opt = followup_option("employee")
    assert "employee" in opt.lower() and len(opt.split()) >= 5


def test_enrich_offers_the_followup_and_logs_it():
    from app.agent.postprocess import enrich

    out = enrich(
        # NOTE: the SQL must constrain a date, otherwise period_guard fires first
        # and takes precedence (wrong scope beats a missing column).
        {"answer": "Here are the GIA results.",
         "sql_used": ["SELECT * FROM tblPlanMaster WHERE CreatDate >= '2026-06-01'"],
         "rows_returned": 1024, "ok": True,
         "data_columns": ["KapanName", "PacketNo", "PLS_Color", "GIA_Color"],
         "data_rows": [{"KapanName": "MO26", "PacketNo": 175,
                        "PLS_Color": "D", "GIA_Color": "D"}]},
        question="Provide past month GIA results of Fency department employees",
    )
    assert out["clarify_options"], "a follow-up must be offered"
    assert "employee" in out["clarify_options"][0].lower()

    # and NOT on a question that never asked for a breakdown
    plain = enrich(
        {"answer": "Total is 4,007.",
         "sql_used": ["SELECT COUNT(*) FROM tblEmployee"], "rows_returned": 1,
         "ok": True, "data_columns": ["Total"], "data_rows": [{"Total": 4007}]},
        question="how many employees do we have",
    )
    assert plain["clarify_options"] == []


def test_model_is_told_to_include_the_named_dimension():
    # The follow-up is the FALLBACK; the default is to just include the column.
    from app.agent.tools import RULES

    assert "SHOW THE THING THEY ASKED TO BREAK IT DOWN BY" in RULES
    assert "WHERE clause" in RULES
