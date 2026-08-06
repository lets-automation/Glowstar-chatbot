"""
test_access_guard.py
--------------------
RESTRICTED DATA: salary / pay.

The client instructed that the chatbot must not answer salary-related questions —
it should behave as if it has no access to that data. This is a POLICY control,
so it is enforced in code at three layers and locked here:

  layer 1  the question is refused before any LLM call      (is_pay_question)
  layer 2  RULES tell the model it has no access            (prompt text)
  layer 3  queries reading pay columns are rejected         (sql_selects_pay_data)

The guard must be tight on pay and loose on everything else: production, damage,
stock, jangad and GIA reports still have to work, including per-employee piece
counts (which are not pay).
"""
import pytest

from app.agent.access_guard import (
    REFUSAL,
    is_pay_question,
    refusal_response,
    sql_selects_pay_data,
)


@pytest.mark.parametrize("q", [
    "what is the salary of employee M2139",
    "show me top earners last month",
    "who is the highest paid worker",
    "how much did BHADANI LAVJIBHAI earn in June",
    "employee wise earnings",
    "payroll for June 2026",
    "pagar batavo",                       # Gujlish: "show me the salary"
    "total labour amount paid last month",
    "who earned the most?",
])
def test_pay_questions_are_refused(q):
    assert is_pay_question(q) is True, f"pay question leaked through: {q}"


@pytest.mark.parametrize("q", [
    "give me the damage report of department MFG - 1",
    "Give me the stock report",
    "GIA results of Fency department employees",
    "how many packets did M2139 make last month",   # piece count is NOT pay
    "how many employees do we have",
    "production for June 2026",
    "which packets are in stock",
    "kapan wise production",
    "how many packets are on jangad",
    "top 10 workers by production",                 # ranking by output, not pay
    # BONUS + INCENTIVE are explicitly allowed (client decision).
    "bonus of the Fency workers",
    "incentive report",
    "how much bonus did M2139 get last month",
    "employee wise bonus for June 2026",
])
def test_normal_business_questions_still_work(q):
    assert is_pay_question(q) is False, f"guard is over-blocking: {q}"


def test_refusal_is_polite_and_actionable():
    out = refusal_response("what is the salary of M2139")
    assert out["ok"] is True          # a policy answer, not an error
    assert out["sql_used"] == [] and out["rows_returned"] == 0
    assert out["export_query"] is None and out["data_rows"] == []
    assert "salary" in REFUSAL.lower()
    # the refusal must advertise what IS available, incl. bonus/incentive
    assert "bonus" in REFUSAL.lower() and "incentive" in REFUSAL.lower()
    assert "accounts" in REFUSAL.lower(), "tell the user where pay data DOES live"


@pytest.mark.parametrize("sql", [
    "SELECT SUM(FinalLabour) FROM tblPointRateLabour",
    "SELECT LabourAmount FROM tblPointRateLabour",
])
def test_sql_reading_pay_columns_is_blocked(sql):
    assert sql_selects_pay_data(sql) is True, f"pay column reachable via SQL: {sql}"


@pytest.mark.parametrize("sql", [
    # The pay TABLES stay usable — they carry the department/packet attribution
    # the GIA and production reports depend on. Only the money columns are barred.
    "SELECT COUNT(*) FROM tblPointRateLabour WHERE DepartmentName='Fency'",
    "SELECT KapanName, PacketNo FROM tblFinalPacket",
    "SELECT DepartmentName, COUNT(DISTINCT Packet_ID) FROM tblPointRateLabour GROUP BY DepartmentName",
    # bonus + incentive columns are ALLOWED
    "SELECT EmpName, BonusAmount FROM tblPointRateLabour",
    "SELECT CreditPoints, DebitPoints FROM tblIncentiveAmount",
])
def test_non_pay_queries_are_allowed(sql):
    assert sql_selects_pay_data(sql) is False, f"guard is over-blocking SQL: {sql}"


def test_rules_tell_the_model_it_has_no_pay_access():
    from app.agent.tools import RULES

    assert "RESTRICTED DATA - SALARY" in RULES
    assert "BONUS and INCENTIVE ARE" in RULES, "bonus/incentive must stay allowed"
    assert "NO ACCESS" in RULES


# ---------------------------------------------------------------------------
# BONUS / INCENTIVE ARE ALLOWED — even when phrased with pay vocabulary.
#
# Regression lock. _PAY_RE matches "earning|earnings|earned", and is_pay_question
# used to return True on it IMMEDIATELY, consulting the bonus/incentive exemption
# only in the separate "how much did X get" branch. So every one of these was
# refused despite the client explicitly permitting bonus and incentive — and it
# broke section 7 (BONUS + INCENTIVE) of the "report of <entity>" profile the
# RULES mandate.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", [
    "bonus earnings of employee M4117",
    "total bonus earned by the Fency department",
    "incentive earnings kapan wise",
    "how much incentive did M2139 earn last month",
    "top employees by bonus",
    "which karigar earned the most incentive points",
])
def test_bonus_and_incentive_questions_are_not_refused(q):
    assert is_pay_question(q) is False, f"bonus/incentive must be allowed: {q}"


@pytest.mark.parametrize("q", [
    # An UNAMBIGUOUS salary word stays refused even alongside bonus: the refusal
    # message already points the user at the bonus figures they can have.
    "salary and bonus of M4117",
    "payroll and incentive report",
    "pagar ane bonus batavo",
    # ...and the ambiguous words still mean salary with no bonus context.
    "total earnings of the Fency department",
    "highest paid employees",
    "how much did M4117 earn",
])
def test_salary_is_still_refused(q):
    assert is_pay_question(q) is True, f"salary must stay restricted: {q}"
