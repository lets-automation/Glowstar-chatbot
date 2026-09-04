"""
test_name_as_code_correction.py
-------------------------------
The name-as-code fix, promoted from a log line into a tool-loop correction
(2026-08-21).

WHAT CHANGED AND WHY
--------------------
app/agent/name_guard.py already DETECTED that a person-column was printing
employee codes instead of names. All it did was write a NAME-AS-CODE warning to
the log and offer the user a one-tap follow-up *after the answer was shown*.
Detecting a wrong answer and then showing it anyway is not a guard.

It now feeds tools._enrichment_hint(), which appends a correction to the run_sql
tool result - the same mechanism that already forces the KapanID/PacketID
display rules. The model fixes the query before it writes the answer.

WHY IT MATTERS ON THIS DATABASE (measured):
    tblPacketIssue.EmpName     = the CODE on 5,642,614 of 5,702,698 rows,
                                 a real name on ZERO
    tblPointRateLabour.EmpName = the CODE on   880,250 of   902,150 rows,
                                 a real name on ZERO
So any query reaching for the convenient-looking EmpName column hands the client
"M1332" where they asked for a person.

THE FALSE-POSITIVE HALF
-----------------------
A correction costs one of the MAX_CORRECTION_ROUNDS, so a guard that fires on a
good answer is not free - it spends the budget a real correction would need. The
"must not fire" cases below are therefore the load-bearing half, and they were
each verified against live query results on 2026-08-21:

    properly joined worker names   -> 'UNAGAR NIKUNJ'      no fire
    honestly-labelled Code column  -> 'SW001'              no fire
    department names               -> 'SoftWare Eng'       no fire
    party/firm names               -> 'DIYORA & BHANDERI'  no fire
    ordinary packet report         -> no person column     no fire
"""
from __future__ import annotations

import pytest

from app.agent.tools import _enrichment_hint

_FIRED = "showing employee CODES"


def _hint(columns, rows):
    return _enrichment_hint(columns, rows)


# --- it must fire on the real failure ---------------------------------------

@pytest.mark.parametrize(
    "columns,rows",
    [
        # tblPacketIssue.EmpName - the shape measured live.
        (["EmpName", "PacketNo"],
         [{"EmpName": "VLRC001", "PacketNo": 334},
          {"EmpName": "M1332", "PacketNo": 335},
          {"EmpName": "Y111", "PacketNo": 336}]),
        # tblPointRateLabour.EmpName alongside a department.
        (["EmpName", "DepartmentName"],
         [{"EmpName": "M2008", "DepartmentName": "MFG-2"},
          {"EmpName": "M2139", "DepartmentName": "MFG-2"}]),
        # A column named for the ROLE rather than the table.
        (["Worker", "Packets"],
         [{"Worker": "M4117", "Packets": 12},
          {"Worker": "M4167", "Packets": 9}]),
        (["Maker", "Shape"],
         [{"Maker": "CL403", "Shape": "RD"},
          {"Maker": "CL404", "Shape": "OV"}]),
    ],
)
def test_fires_when_a_person_column_holds_codes(columns, rows):
    assert _FIRED in _hint(columns, rows)


def test_the_correction_names_the_right_fix():
    """The message has to tell the model WHAT to do, not just that it is wrong -
    run_select feeds this straight back into the tool loop."""
    hint = _hint(["EmpName"], [{"EmpName": "M1332"}, {"EmpName": "M2008"}])
    assert "tblEmployee.ID" in hint
    assert "FirstName" in hint
    # It must point at the NUMERIC id, since EmpName is precisely the trap.
    assert "EmpId" in hint or "Emp_ID" in hint


# --- it must NOT fire on a good answer --------------------------------------

@pytest.mark.parametrize(
    "label,columns,rows",
    [
        ("properly joined names",
         ["Worker", "KapanName", "PolishedWt"],
         [{"Worker": "UNAGAR NIKUNJ", "KapanName": "MZ26", "PolishedWt": 0.9},
          {"Worker": "DIYORA MITULBHAI", "KapanName": "MZ26", "PolishedWt": 1.1}]),
        ("honestly-labelled Code column",
         ["Code", "FirstName", "LastName"],
         [{"Code": "SW001", "FirstName": "Jay", "LastName": "Patel"},
          {"Code": "SW002", "FirstName": "Ravi", "LastName": "Shah"}]),
        ("department names are not people",
         ["Name"],
         [{"Name": "SoftWare Eng"}, {"Name": "MFG - 1"}]),
        ("party/firm names",
         ["Party"],
         [{"Party": "DIYORA & BHANDERI CORORATION"},
          {"Party": "SHRI HARI GEMS"}]),
        ("ordinary packet report, no person column",
         ["KapanName", "PacketNo", "Shape", "PolishedWt"],
         [{"KapanName": "MQ26", "PacketNo": 387, "Shape": "RD", "PolishedWt": 0.7},
          {"KapanName": "MQ26", "PacketNo": 388, "Shape": "OV", "PolishedWt": 0.8}]),
        # The department_report Workforce section: a Code column AND a name
        # column side by side is the CORRECT shape, not a violation.
        ("department_report Workforce section",
         ["Code", "Worker"],
         [{"Code": "M1004", "Worker": "CHAVDA AJABSINH "},
          {"Code": "M1005", "Worker": "MAIYANI  VIJAYABHAI "}]),
        # A single stray code among real names must stay quiet - the guard needs
        # a MAJORITY (>=60%) before it spends a correction round.
        ("one stray code among names",
         ["Worker"],
         [{"Worker": "UNAGAR NIKUNJ"}, {"Worker": "DIYORA MITULBHAI"},
          {"Worker": "M1332"}]),
    ],
)
def test_does_not_fire_on_a_correct_answer(label, columns, rows):
    assert _FIRED not in _hint(columns, rows), f"false positive on {label}"


def test_empty_result_is_silent():
    assert _hint(["EmpName"], []) == ""
    assert _hint([], []) == ""


def test_existing_id_rules_still_fire():
    """The name fix is additive - it must not have displaced the display rules
    that shared this function."""
    hint = _hint(["KapanID", "PacketID", "Qty"],
                 [{"KapanID": 1, "PacketID": 2, "Qty": 3}])
    assert "KapanName" in hint
    assert "PacketNo" in hint
