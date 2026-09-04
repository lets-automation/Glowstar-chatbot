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
#
# DAMAGE/penalty money is allowed for the same reason and by the same client
# rule - the damage report legitimately shows an amount deducted for a broken
# stone. It is listed here because the money words below ("ketla paisa katya
# karigar pase thi" - how much money was cut from the karigar) otherwise read
# exactly like a wage question. Real case: cold-case DRS-2, whose ground truth
# is a damage total of -11,536.82.
_ALLOWED_PAY_TOPIC_RE = re.compile(
    r"\b(bonus|bonuses|incentive|incentives|damage|damages|penalty|penalties|"
    r"deduction|deductions|nuksan)\b",
    re.IGNORECASE,
)

# --- bare money words, which mean salary ONLY when a PERSON is the subject ----
#
# "pay" and "paisa" cannot be added to the hard list: the same words carry the
# job-work rate paid to an outside PARTY, which is ordinary business data the
# assistant must answer. Cold-case JP-2 is exactly that - "Party ne galaxy na
# ketla paisa apiye chhiye?" (how much money do we give the party for galaxy) -
# and refusing it would be a regression, not a protection.
#
# So the wage is recognised by its SUBJECT, not by the money word alone:
# money word + a person + no party/process context = salary.
_BARE_MONEY_RE = re.compile(
    r"\b(pay|paisa|paise|rupiya|rupaya|rupees|money|milta|mile|apiye)\b",
    re.IGNORECASE,
)

# The wage belongs to a PERSON. An employee code (M4117, Y111) counts: it is how
# the client's staff actually name someone.
_PERSON_SUBJECT_RE = re.compile(
    r"\b(employee|employees|worker|workers|karigar|karigars|kaarigar|staff|"
    r"mansu|labourer|labourers|laborer|laborers|"
    r"per\s+(?:person|head|employee|worker)|"
    r"[MY]\s?\d{3,5})\b",
    re.IGNORECASE,
)

# ...unless the money is going to an outside party for a process, which is a
# RATE, not a wage. Checked even when a person word is also present, because
# "how much do we pay the party for the polishing process" mentions both.
_PARTY_SUBJECT_RE = re.compile(
    r"\b(party|parties|firm|firms|vendor|vendors|supplier|suppliers|buyer|"
    r"buyers|contractor|contractors|sub-?contractor|jangad|process|rate|rates)\b",
    re.IGNORECASE,
)

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

    # Otherwise, an explicit bonus / incentive / damage topic makes the pay
    # vocabulary mean the ALLOWED figure ("bonus earnings", "damage deduction"),
    # not the wage.
    if _ALLOWED_PAY_TOPIC_RE.search(q):
        return False

    # BARE MONEY WORDS + A PERSON = the wage, however it is phrased.
    #
    # This closes two gaps found on 2026-08-21 by writing adversarial probes:
    # "what is the monthly pay of the Fency department workers" and "kitna paisa
    # milta hai M4117 ko har mahine?" both reached the model, because bare "pay"
    # and the Hinglish phrasing are in neither list above. They were caught only
    # by the RULES - a prose guard - when a code guard was available.
    #
    # The party exclusion is what keeps this safe: the same money words carry
    # the job-work RATE paid to an outside firm, which is ordinary data.
    if (
        _BARE_MONEY_RE.search(q)
        and _PERSON_SUBJECT_RE.search(q)
        and not _PARTY_SUBJECT_RE.search(q)
    ):
        return True

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

def redact_pay_columns(columns: list, rows: list) -> tuple[list, list, list]:
    """Drop salary columns from a RESULT. Returns (columns, rows, dropped).

    WHY THIS EXISTS ALONGSIDE sql_selects_pay_data().
    -------------------------------------------------
    That function reads the SQL TEXT, so it only ever sees column names the
    query spells out. A star projection never spells them, and the guard
    returned False for every one of these (verified 2026-08-25):
        SELECT * FROM tblLabourResult
        SELECT t.* FROM tblLabourResult t
        SELECT SUM(v) FROM (SELECT t.*,1 v FROM tblPointRateLabour t) q
    The first one really does come back carrying LabourAmount and FinalLabour
    with live wage values (0.7, 0.64, 0.6) - straight into the model's preview,
    the rendered table and the user's Excel download. The single instruction the
    client gave about this data - behave as if you cannot see it - was defeated
    by a query the model writes whenever it explores a table.

    Text matching cannot close that: `*` is not a column name, and enumerating
    every alias/CTE/subquery form is exactly the losing game. So this checks
    what actually CAME BACK, where the columns are named no matter how they were
    selected. The text check stays as the first line - it rejects the query
    outright and tells the model why - and this is the backstop for everything
    the text cannot see.

    Never raises: a redaction that crashes the turn would be its own outage.
    """
    try:
        dropped = [c for c in (columns or []) if _SALARY_COLUMNS_RE.search(str(c))]
        if not dropped:
            return columns, rows, []
        keep = [c for c in columns if c not in dropped]
        clean = [{c: r.get(c) for c in keep} for r in (rows or [])]
        return keep, clean, dropped
    except Exception:  # noqa: BLE001 - never let redaction break a turn
        return columns, rows, []


SQL_BLOCKED_MSG = (
    "BLOCKED: that query reads salary columns (FinalLabour/LabourAmount), which "
    "this assistant has no access to. Bonus and incentive figures ARE available "
    "(BonusAmount, BonusPoint, CreditPoints/DebitPoints) — use those, or answer "
    "with counts/weights/dates, or tell the user salary data is not available."
)
