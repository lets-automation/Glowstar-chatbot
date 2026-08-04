"""
name_guard.py
-------------
PERSON-COLUMN CHECK: the answer has a worker/maker column, but it is showing
employee CODES ("M1332", "Y111", "CL403") instead of people's names.

Why this is worth a guard rather than a prompt rule alone. Measured on the live
database:

    tblPacketIssue.EmpName      = the CODE on 5,642,614 of 5,702,698 rows,
                                  a real name on ZERO
    tblPointRateLabour.EmpName  = the CODE on   880,250 of   902,150 rows,
                                  a real name on ZERO
    tblPlanMaster.EmpName       = a real name ~86% of the time, still the bare
                                  code on ~12%

So any query that reaches for the convenient-looking EmpName column hands the
client "M1332" where they asked for a person. The correct route is always the
id: EmpId / Emp_ID / MfgEmpId / PolishEmpId -> tblEmployee.ID -> FirstName +
LastName. This is NOT one department's quirk: the affected rows span Rough
Estimation, Marker-2/3, Weight Scale, GS Jangad, Galaxy, VL Marker, Vision 360,
Laser, Blocking and the rest of the factory.

Deterministic and provider-independent: it inspects the returned column names
and values only. No LLM call, no schema knowledge, so it also protects questions
nobody encoded guidance for and cannot regress when a provider changes.

DELIBERATELY NARROW, so it never nags:
  * only columns whose NAME means a person (maker/worker/employee/polisher...);
  * a value counts as a code only when it has NO space AND contains a digit --
    real names here are "UNAGAR NIKUNJ", "DIYORA MITULBHAI", "SHRI HARI GEMS";
  * fires only when MOST of the column's values are code-shaped, so one stray
    code among real names stays quiet.
"""
from __future__ import annotations

import re

# Column names that promise a human. Substring match, lowercase.
# "name" alone is excluded on purpose - KapanName/PacketName would match it and
# the guard would fire on every ordinary report.
_PERSON_COLUMNS = (
    "empname", "emp_name", "employee", "maker", "worker", "karigar",
    "polisher", "checker", "artisan", "staff", "person", "operator",
)

# Columns that legitimately hold a code and are LABELLED as such - the answer is
# being honest, so leave it alone.
_CODE_COLUMNS = ("code", "id", "_id")

_HAS_DIGIT = re.compile(r"\d")

# Fire only when at least this share of the values look like codes.
_CODE_SHARE = 0.6
# Below this many values the sample is too small to judge.
_MIN_VALUES = 2


def _is_code_like(value) -> bool:
    """
    A person-name value that is really a code.

    The discriminator is deliberately crude because it is reliable on this data:
    every real name in tblEmployee is either multi-word ("DIYORA MITULBHAI",
    "SHRI HARI GEMS") or has no digits, while every code carries a digit and no
    space ("M1332", "Y111", "CL403", "4P001", "MFGSTK001").
    """
    s = str(value or "").strip()
    if not s or len(s) > 14:
        return False
    if " " in s:
        return False
    return bool(_HAS_DIGIT.search(s))


def code_columns(columns: list[str], rows: list | None) -> list[str]:
    """
    Person-columns in this result that are showing codes instead of names.

    Returns the offending column names (as given). Empty when the answer is
    fine, when nothing was returned, or when there is no person-column at all.
    """
    if not rows or not columns:
        return []

    flagged: list[str] = []
    for col in columns:
        name = str(col).lower()
        if not any(frag in name for frag in _PERSON_COLUMNS):
            continue
        if any(frag in name for frag in _CODE_COLUMNS):
            continue          # an honestly-labelled code column

        values = []
        for row in rows:
            v = row.get(col) if isinstance(row, dict) else None
            if v is not None and str(v).strip():
                values.append(v)
        if len(values) < _MIN_VALUES:
            continue

        coded = sum(1 for v in values if _is_code_like(v))
        if coded / len(values) >= _CODE_SHARE:
            flagged.append(str(col))

    return flagged


def followup_option(column: str) -> str:
    """
    One-tap follow-up, phrased as a complete question because tapping it SENDS
    this text as the next question (same contract as the CLARIFY buttons).
    """
    return f"Show the same report with the full employee name instead of the {column} code"
