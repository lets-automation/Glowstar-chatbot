"""
test_department_report.py
-------------------------
The deterministic department-report recipe (app/agent/reports.py).

WHY IT EXISTS AT ALL
--------------------
Measured live on 2026-08-20, the model assembling this report itself produced,
on consecutive runs of the same question: an invalid WHERE DepartmentName=...
against tblPlanMaster; "9 packets" where the database held 381 (it had totalled
its own preview sample); two sections one run and five the next; and a context
overflow from nine rounds of accumulated rows. These tests lock the properties
that made those failures impossible.

No live database: run_select is stubbed, so what is under test is the RECIPE -
which queries it builds and how it presents them - not SQL Server.
"""
import pytest

from app.agent import reports

_DEPTS = ["MFG - 1", "MFG - 2", "Galaxy", "Fency"]


@pytest.fixture
def captured(monkeypatch):
    """Record every SQL the recipe runs, and answer each with one plausible row."""
    seen: list[str] = []

    def fake_run_select(sql, max_rows=None):
        seen.append(sql)
        if "DISTINCT DepartMentName" in sql:
            return {"ok": True, "row_count": len(_DEPTS),
                    "columns": ["DepartMentName"],
                    "rows": [{"DepartMentName": d} for d in _DEPTS]}
        return {"ok": True, "row_count": 1,
                "columns": ["A", "B", "C"], "rows": [{"A": 1, "B": 2, "C": 3}]}

    monkeypatch.setattr(reports, "run_select", fake_run_select)
    return seen


# --- department resolution --------------------------------------------------

@pytest.mark.parametrize("typed", ["MFG - 1", "MFG 1", "mfg-1", "MFG-1", "  mfg 1  "])
def test_department_name_is_matched_loosely(captured, typed):
    """Staff type the dash and spaces differently every time. An exact-match
    filter on the wrong spelling returns zero rows, which reads as 'no data'
    rather than 'no match' - the most misleading failure available."""
    assert reports.resolve_department(typed)[0] == "MFG - 1"


def test_unknown_department_returns_suggestions_not_a_guess(captured):
    name, suggestions = reports.resolve_department("Marketing")
    assert name is None
    assert suggestions, "an unmatched department must offer the real ones"


def test_unknown_department_tells_the_model_to_ask(captured):
    out = reports.department_report("Marketing", "2026-07-01", "2026-08-01")
    assert out["sections"] == []
    assert "do not guess" in out["text"].lower()


# --- section completeness ---------------------------------------------------

def test_every_section_is_present(captured):
    """The section list cannot quietly shrink: that is the whole point of a
    recipe. Hand-built reports dropped damage and bonus silently."""
    out = reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    titles = [s["title"] for s in out["sections"]]
    for expected in ("Workforce", "Headcount", "Production summary",
                     "Production by worker", "Production by kapan",
                     "Damage", "Bonus", "Incentive"):
        assert expected in titles, f"missing section: {expected}"


def test_sections_are_titled_for_the_workbook(captured):
    """Sheet names come from the title; without one the workbook falls back to
    naming tabs after columns ('KapanName-PacketNo')."""
    out = reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    assert all(s.get("title") for s in out["sections"])


# --- the failures this replaces ---------------------------------------------

def test_model_is_told_not_to_total_the_preview(captured):
    """The 9-vs-381 bug: the model summed the rows it could see and presented
    that as the total."""
    out = reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    assert "do not total the preview" in out["text"].lower()


def test_context_stays_small(captured):
    """One tool call replaced nine rounds of accumulating rows. If this grows
    without bound the context overflow comes straight back."""
    out = reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    assert len(out["text"]) < 8000, "the model's context must stay compact"


def test_department_is_never_filtered_on_a_fact_table(captured):
    """tblPlanMaster has no DepartmentName column - it carries EmpId. Filtering
    on the name there is an invalid-column error and an empty report."""
    reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    for sql in captured:
        if "tblPlanMaster" in sql:
            assert "DepartmentName" not in sql, \
                "department must resolve through tblEmployee.EmpId, not a fact table"


def test_period_end_is_exclusive(captured):
    """Half-open ranges avoid the '<= 31 July' bug that drops rows stamped later
    that same day."""
    reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    dated = [s for s in captured if "2026-08-01" in s]
    assert dated, "the period must reach the queries"
    assert all("<= '2026-08-01'" not in s for s in dated)


# --- restricted data --------------------------------------------------------

@pytest.mark.parametrize("blocked", ["FinalLabour", "LabourAmount"])
def test_salary_columns_are_never_selected(captured, blocked):
    """RESTRICTED DATA - SALARY in tools.py: the assistant has no access to wage
    figures. tblPointRateLabour carries them right beside the bonus columns this
    recipe does use, so one careless SELECT * would leak payroll."""
    reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    for sql in captured:
        assert blocked not in sql, f"{blocked} must never be queried"


def test_bonus_and_incentive_are_the_permitted_earnings_columns(captured):
    """The rules allow these explicitly; they are what makes the section useful
    without touching wages."""
    reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    joined = "\n".join(captured)
    assert "BonusAmount" in joined and "BonusPoint" in joined
    assert "CreditPoints" in joined and "DebitPoints" in joined


def test_no_select_star(captured):
    """SELECT * is how a blocked column arrives by accident."""
    reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    assert not any("SELECT *" in s.upper() for s in captured)


# --- honest empties ---------------------------------------------------------

def test_empty_section_is_reported_not_dropped(monkeypatch):
    """MFG - 1 genuinely has no bonus rows after 2026-06-30. Silence would read
    as 'no bonus scheme'; the truth is 'nothing in this period'."""
    def empty_run_select(sql, max_rows=None):
        if "DISTINCT DepartMentName" in sql:
            return {"ok": True, "row_count": 1, "columns": ["DepartMentName"],
                    "rows": [{"DepartMentName": "MFG - 1"}]}
        return {"ok": True, "row_count": 0, "columns": ["A", "B"], "rows": []}

    monkeypatch.setattr(reports, "run_select", empty_run_select)
    out = reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    assert "no records in this period" in out["text"]
    assert out["sections"] == [], "an empty section must not become an empty sheet"


def test_a_failing_query_does_not_kill_the_report(monkeypatch):
    """One bad section must not cost the user the other seven."""
    def flaky(sql, max_rows=None):
        if "DISTINCT DepartMentName" in sql:
            return {"ok": True, "row_count": 1, "columns": ["DepartMentName"],
                    "rows": [{"DepartMentName": "MFG - 1"}]}
        if "tblPlanReport" in sql:
            return {"ok": False, "error": "Invalid object name 'tblPlanReport'"}
        return {"ok": True, "row_count": 1, "columns": ["A", "B"],
                "rows": [{"A": 1, "B": 2}]}

    monkeypatch.setattr(reports, "run_select", flaky)
    out = reports.department_report("MFG - 1", "2026-07-01", "2026-08-01")
    assert "unavailable" in out["text"]
    assert len(out["sections"]) >= 6, "the surviving sections must still be delivered"


# --- SQL injection ----------------------------------------------------------

def test_quotes_in_the_department_name_cannot_break_out(captured):
    """The department name is model-supplied text pasted into SQL."""
    reports.department_report("MFG'; DROP TABLE tblPacket--", "2026-07-01", "2026-08-01")
    for sql in captured:
        assert "DROP TABLE" not in sql.upper() or "''" in sql
