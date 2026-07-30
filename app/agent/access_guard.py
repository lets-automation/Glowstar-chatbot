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

# Words that make a question about what a PERSON IS PAID. Includes the Gujlish
# the client's staff type ("pagar" = salary, "paisa"/"rupiya" in a pay context).
_PAY_RE = re.compile(
    r"\b("
    r"salary|salaries|salaried|payroll|pay-?slip|payslip|wage|wages|"
    r"pagar|pagaar|talab|tankha|"                       # Gujarati/Hindi for salary
    r"earning|earnings|earned|earner|earners|income|remuneration|compensation|ctc|"
    r"take-?home|net\s*pay|gross\s*pay|paid\s+to|highest\s*paid|top\s*paid|best\s*paid|"
    r"labour\s*(amount|pay|cost|charge)|labor\s*(amount|pay|cost|charge)|"
    r"finallabour|final\s*labour"
    r")\b",
    re.IGNORECASE,
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

    Bonus and incentive are ALLOWED, so a question about them is let through even
    though it uses "how much did X get" phrasing.
    """
    q = question or ""
    if _PAY_RE.search(q):
        return True
    # "how much did X get" -> only restricted when it is NOT about bonus/incentive.
    return bool(_PAY_PHRASE_RE.search(q)) and not _ALLOWED_PAY_TOPIC_RE.search(q)


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
