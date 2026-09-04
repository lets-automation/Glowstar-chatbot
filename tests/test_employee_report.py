"""
test_employee_report.py
-----------------------
ONE NAMED WORKER'S PLANS AND DAMAGE OVER A PERIOD.

~8 of the 101 uncovered questions in the 2026-09-03 audit: "give me the report
of employee M4117 for June 2026", "past month report of employee id M2009",
"full report of employee code M4167".

The reason this needs a recipe rather than free SQL is identity:

  * A NAME IS NOT AN IDENTITY. Fifteen tblEmployee rows share the name
    MAIYANI VIJAYABHAI, nine share SUTARIYA NARESHKUMAR exactly. Grouping on a
    name sums several people and reports it as one worker's figure.
  * THE CODE IS NOT UNIQUE EITHER - B146, M2128 and M2D003 each map to two
    employees. So even an exact code can be ambiguous.
  * Y-CODES ARE VENDOR FIRMS, not karigars.
  * PAY IS REFUSED UPSTREAM by access_guard. This report carries NO money
    column on purpose - adding one routes around a guard that exists.
"""
import pytest

from app.agent import access_guard, recipe_router as rr, reports, tools


class TestRouting:

    @pytest.mark.parametrize("q,code", [
        ("give me the report of employee M4117 for June 2026", "M4117"),
        ("give me full report of employee code M4167 from 1 Jul 2026 to "
         "31 Jul 2026", "M4167"),
        ("give me past month report of employee id M2009", "M2009"),
    ])
    def test_a_named_worker_routes(self, q, code):
        m = rr.match(q)
        assert m and m["recipe"] == "employee_report"
        assert m["employee"] == code

    @pytest.mark.parametrize("q,recipe", [
        # One worker beats the department they belong to; a department
        # question is still the department report.
        ("give me report of department MFG - 1 for July 2026",
         "department_report"),
        ("past month GIA results of fency department employees", "lab_results"),
    ])
    def test_it_does_not_steal_department_questions(self, q, recipe):
        m = rr.match(q)
        assert m and m["recipe"] == recipe, (q, m)

    def test_it_is_not_a_tool_spec(self):
        """Router-matched, like the other period-free recipes: TOOL_SPECS is
        re-sent every round and the budget has no room."""
        assert "employee_report" not in {s["name"] for s in tools.TOOL_SPECS}
        assert "employee_report" in tools.TOOL_HANDLERS


@pytest.mark.integration
class TestIdentityIsNeverGuessed:

    def test_a_unique_code_resolves(self):
        rows, err = reports.resolve_employee("M4117")
        assert err == "" and len(rows) == 1
        assert rows[0]["Code"] == "M4117"

    def test_a_shared_code_lists_candidates_instead_of_picking(self):
        """B146 is two different people. Summing them reports two workers as
        one - the exact failure the employee_identity rule exists for."""
        rows, err = reports.resolve_employee("B146")
        assert err == "" and len(rows) == 2
        out = reports.employee_report("B146", "2026-06-01", "2026-07-01")
        assert "matches 2 people" in out["text"]
        assert "do NOT add them together" in out["text"]
        assert out["sections"] == []

    def test_an_unknown_employee_asks_for_a_code(self):
        out = reports.employee_report("ZZZZ", "2026-06-01", "2026-07-01")
        assert out["text"].startswith("ERROR")
        assert "CODE" in out["text"]


@pytest.mark.integration
class TestTheReportItself:

    def test_it_reports_plans_the_person_authored(self):
        out = reports.employee_report("M4117", "2026-06-01", "2026-07-01")
        assert not out["text"].startswith("ERROR")
        assert "M4117" in out["text"]
        titles = {s["title"] for s in out["sections"]}
        assert "Plans authored" in titles

    def test_it_carries_the_code_not_just_the_name(self):
        """A per-person figure without a code merges the duplicates."""
        out = reports.employee_report("M4117", "2026-06-01", "2026-07-01")
        assert "M4117" in out["text"]
        assert "never by name" in out["text"]

    def test_it_has_no_money_column(self):
        """access_guard refuses pay questions BEFORE any LLM call. A money
        column here would route around that guard."""
        out = reports.employee_report("M4117", "2026-06-01", "2026-07-01")
        cols = {c.lower() for s in out["sections"] for c in s["columns"]}
        for banned in ("salary", "wage", "pay", "bonusamount", "finallabour"):
            assert banned not in cols, banned

    def test_the_pay_guard_still_refuses_pay_questions(self):
        """Adding this recipe must not have opened a back door."""
        assert access_guard.is_pay_question("what is the salary of M4117")

    def test_damage_points_are_not_money(self):
        """tblPlanReport.Amount is POINTS x rate, a penalty deduction. It must
        never be shown with a currency symbol."""
        out = reports.employee_report("M4117", "2026-06-01", "2026-07-01")
        if "## Damage" in out["text"]:
            assert "NOT money" in out["text"]
            assert "₹" not in out["text"] and "$" not in out["text"]
