"""
access_guard.py
---------------
RESTRICTED DATA: salary / wages.

The client instructed that the chatbot must NOT answer salary-related questions —
it is to behave as if it has no access to that data. BONUS and INCENTIVE are
explicitly allowed (client decision): those are the performance figures managers
use day to day; only the wage itself is restricted. Enforced in CODE, not by
asking the model nicely:

  layer 1 (here)      the QUESTION is refused before any LLM call
  layer 2 (RULES)     the model is told it has no access to pay data
  layer 3 (sql_block) queries selecting pay columns are rejected

Deliberately scoped to PAY. Production, damage, stock, jangad, GIA and headcount
questions still work normally — including reports that legitimately show a
damage penalty — so the guard removes the sensitive answer, not the product.
"""
from __future__ import annotations

import re

# UNAMBIGUOUS salary words. These mean the wage itself and nothing else, so they
# are refused even when the question also mentions bonus - the refusal message
# already points the user at the bonus/incentive figures they CAN have.
_HARD_PAY_RE = re.compile(
    r"\b("
    r"salary|salaries|salaried|payroll|pay-?slip|payslip|wage|wages|"
    r"pagar|pagaar|talab|tankha|"                       # Gujarati/Hindi for salary
    r"remuneration|compensation|ctc|take-?home|net\s*pay|gross\s*pay|"
    r"labour\s*(amount|pay|cost|charge)|labor\s*(amount|pay|cost|charge)|"
    r"finallabour|final\s*labour"
    r")\b",
    re.IGNORECASE,
)

# AMBIGUOUS pay words. On their own they mean salary ("total earnings of the
# Fency department"), but paired with bonus or incentive they mean the ALLOWED
# figure ("bonus earnings of M4117"). Splitting these out of the hard list is
# what fixes the false refusals - see is_pay_question.
_SOFT_PAY_RE = re.compile(
    r"\b("
    r"earning|earnings|earned|earner|earners|income|"
    r"paid\s+to|highest\s*paid|top\s*paid|best\s*paid"
    r")\b",
    re.IGNORECASE,
)

# Kept as the union so anything importing it keeps its old meaning.
_PAY_RE = re.compile(
    f"(?:{_HARD_PAY_RE.pattern})|(?:{_SOFT_PAY_RE.pattern})", re.IGNORECASE
)

# BONUS and INCENTIVE are explicitly ALLOWED (client decision): they are the
# performance figures managers use, not the wage. A question about them must not
# be caught by the generic "how much did X get" phrasing below.
_ALLOWED_PAY_TOPIC_RE = re.compile(r"\b(bonus|bonuses|incentive|incentives)\b", re.IGNORECASE)

# "how much does/did <someone> earn|make|get paid" — phrasing without a keyword above.
_PAY_PHRASE_RE = re.compile(
    r"\bhow\s+much\s+(did|does|do|has|have)?\s*\w[\w\s]{0,30}?"
    r"\b(earn|earned|make|made|get|got|receive|received|paid)\b",
    re.IGNORECASE,
)

REFUSAL = (
    "I don't have access to salary or wage information, so I can't answer that.\n\n"
    "I can still show **bonus and incentive** figures, along with production, "
    "packets, kapans, stock, jangad, damage, certification (GIA/HRD/IGI), "
    "employees and attendance. "
    "For salary, please contact the accounts department."
)


def is_pay_question(question: str) -> bool:
    """
    True if the question asks for SALARY / wages / earnings (the wage itself).

    Bonus and incentive are ALLOWED (client decision), so a question about them
    is let through even when it uses pay vocabulary.

    ORDER MATTERS. The bonus/incentive exemption used to be checked ONLY in the
    "how much did X get" branch, while _PAY_RE returned True immediately - and
    _PAY_RE matches "earning|earnings|earned". So every one of these was refused
    despite being explicitly permitted:

        "bonus earnings of employee M4117"
        "total bonus earned by the Fency department"
        "incentive earnings kapan wise"

    That also broke section 7 of the "report of <entity>" profile the RULES
    mandate, which is BONUS + INCENTIVE. The exemption now applies to the whole
    check, not one branch of it.

    The exemption is safe because the actual wage columns are blocked
    independently at execution (sql_selects_pay_data / FinalLabour +
    LabourAmount), so letting a bonus question through cannot reach salary data
    even if it is phrased with pay words.
    """
    q = question or ""

    # An unambiguous salary word is restricted no matter what else is asked. A
    # question about "salary and bonus" still gets the refusal, which names the
    # bonus figures as available.
    if _HARD_PAY_RE.search(q):
        return True

    # Otherwise, an explicit bonus/incentive topic makes the pay vocabulary mean
    # the ALLOWED figure ("bonus earnings", "incentive earned"), not the wage.
    if _ALLOWED_PAY_TOPIC_RE.search(q):
        return False

    # No bonus context: the ambiguous words mean salary.
    return bool(_SOFT_PAY_RE.search(q) or _PAY_PHRASE_RE.search(q))


def refusal_response(question: str = "") -> dict:
    """
    The turn returned INSTEAD of querying. Shaped like a normal enriched result so
    both /chat and /chat/stream can return it unchanged. ok=True because this is a
    deliberate policy answer, not an error/failure.
    """
    return {
        "answer": REFUSAL,
        "suggestions": [],
        "clarify_options": [],
        "ask_date": False,
        "citation": "",
        "export_query": None,
        "sql_used": [],
        "rows_returned": 0,
        "ok": True,
        "widgets": [],
        "data_columns": [],
        "data_rows": [],
    }


# --- layer 3: block the SALARY columns at the SQL level ----------------------
# ONLY the wage itself. FinalLabour is the ALL-IN net pay per process and
# LabourAmount is its wage component — those are the salary. Everything else
# stays readable, including BonusAmount / BonusPoint / CreditPoints /
# DebitPoints (bonus + incentive are allowed) and the damage penalty columns the
# damage report needs. The pay TABLES also stay usable, since tblPointRateLabour
# carries the department/packet attribution the GIA and production reports need.
_SALARY_COLUMNS_RE = re.compile(r"\b(FinalLabour|LabourAmount)\b", re.IGNORECASE)


def sql_selects_pay_data(sql: str) -> bool:
    """True if the SQL reads a SALARY column (the wage). Bonus/incentive are OK."""
    return bool(_SALARY_COLUMNS_RE.search(sql or ""))


SQL_BLOCKED_MSG = (
    "BLOCKED: that query reads salary columns (FinalLabour/LabourAmount), which "
    "this assistant has no access to. Bonus and incentive figures ARE available "
    "(BonusAmount, BonusPoint, CreditPoints/DebitPoints) — use those, or answer "
    "with counts/weights/dates, or tell the user salary data is not available."
)
