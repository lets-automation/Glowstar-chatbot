"""
test_period_guard.py
--------------------
SCOPE CHECK: the user named a period but no query filtered on a date, so every
number shown is all-time. Worse than a missing column — nothing on screen is
right, and the figures look entirely plausible.

The guard is only safe if it is silent on the many near-misses, so the silent
cases below outnumber the firing ones. Each was a real false positive during
design.
"""
import pytest

from app.agent.period_guard import (
    constrains_date,
    names_bounded_period,
    unfiltered_period,
)

ROWS = [{"x": 1}]
UNFILTERED = ["SELECT KapanName, COUNT(*) FROM tblFinalPacket GROUP BY KapanName"]


@pytest.mark.parametrize("question", [
    "Fency department production for June 2026",
    "damage report for last month",
    "production in 2026",
    "give me results from 1 to 26 June",
    "stock report for May 2026",
    "GIA results this month",
])
def test_fires_when_period_named_but_sql_unfiltered(question):
    assert unfiltered_period(question, UNFILTERED, ROWS) is True, question


@pytest.mark.parametrize("question,sql", [
    # the filter can live anywhere in the SQL text — subquery, CTE, JOIN ... ON
    ("June 2026 production", ["SELECT * FROM t WHERE CreateDate>='2026-06-01'"]),
    ("June 2026 production",
     ["SELECT * FROM t WHERE PacketID IN (SELECT Packet_ID FROM x WHERE CreatDate>='2026-06-01')"]),
    ("June 2026 production",
     ["WITH m AS (SELECT * FROM x WHERE ProcessDate>='2026-06-01') SELECT * FROM m"]),
    ("June 2026 production",
     ["SELECT * FROM a JOIN b ON b.ReciveTime BETWEEN '2026-06-01' AND '2026-06-30'"]),
    # date FUNCTIONS, where a comma defeats simple comparison matching
    ("last month production", ["SELECT * FROM t WHERE DATEDIFF(MONTH, CreDate, GETDATE()) = 1"]),
    ("June 2026", ["SELECT * FROM t WHERE FORMAT(CreDate,'yyyy-MM')='2026-06'"]),
    ("June 2026", ["SELECT * FROM t WHERE CAST(CreDate AS DATE) BETWEEN '2026-06-01' AND '2026-06-30'"]),
    # a period column that isn't named like a date
    ("salary month 6 2026", ["SELECT * FROM t WHERE SalaryMonth = 6 AND SalaryYear = 2026"]),
    # an early unbounded probe is fine if ANY query was filtered
    ("June 2026 production",
     ["SELECT TOP 1 * FROM tblPacket", "SELECT * FROM t WHERE CreateDate>='2026-06-01'"]),
])
def test_silent_when_some_query_constrains_a_date(question, sql):
    assert unfiltered_period(question, sql, ROWS) is False, question


@pytest.mark.parametrize("question", [
    # explicit ALL-HISTORY: an unfiltered query is CORRECT here
    "total production all time", "overall GIA results",
    "how many packets ever made", "damage till date",
    # current state: no period applies
    "what is in WIP right now", "which packets are currently in process",
    # "may" is a modal verb, not the month
    "may I see the stock summary", "you may show the kapan list",
    # a 4-digit number after an entity word is an ID, not a year
    "show packet 2024 details", "show packet no 2024", "kapan 2019 report",
    # client phrasings a loose from/to range regex would eat
    "damage report of department MFG - 1", "packets from department MFG 1",
    "compare MFG to PLS for 5 packets", "show me the last 5 packets",
    "top 10 kapans by yield",
    # granularity is a BREAKDOWN request (dimension_guard's job), not a bound
    "monthly production", "daily production",
])
def test_silent_on_near_misses(question):
    assert unfiltered_period(question, UNFILTERED, ROWS) is False, question


def test_silent_with_no_rows_or_no_sql():
    assert unfiltered_period("June 2026 production", UNFILTERED, []) is False
    assert unfiltered_period("June 2026 production", [], ROWS) is False


@pytest.mark.parametrize("name,expected", [
    # a naive ".*date.*" match reads these as date columns and silently disables
    # the whole guard on any query that filters one
    ("IsUpdated", False), ("UpdateBy", False), ("Candidate", False),
    ("Validated", False), ("Holiday", False),
    # ...while the ERP's real (inconsistently spelled) date columns must pass
    ("CreDate", True), ("CreatDate", True), ("CreatedDate", True),
    ("ProcessDate", True), ("ReciveTime", True), ("Time", True),
    ("JangadDate", True), ("SalaryMonth", True), ("UpdateDate", True),
])
def test_date_identifier_classification(name, expected):
    sql = f"SELECT * FROM t WHERE {name} = 1"
    assert constrains_date(sql) is expected, name


def test_bounded_period_detection():
    assert names_bounded_period("production for June 2026") is True
    assert names_bounded_period("production all time") is False
    assert names_bounded_period("may I see the summary") is False


def test_enrich_prepends_the_banner_and_keeps_the_data():
    from app.agent.postprocess import enrich

    out = enrich(
        {"answer": "Production was 4,007 packets.", "sql_used": UNFILTERED,
         "rows_returned": 30, "ok": True,
         "data_columns": ["KapanName", "Packets"],
         "data_rows": [{"KapanName": "NI26", "Packets": 84}]},
        question="Fency department production for June 2026",
    )
    # the warning must sit ABOVE the first number, not under a 50-row table
    assert out["answer"].startswith("> **Scope check:**")
    assert out["clarify_options"], "a one-tap re-ask must be offered"
    # the rows are REAL — never strip them (silent-data-loss pattern)
    assert out["data_rows"] and out["export_query"]
