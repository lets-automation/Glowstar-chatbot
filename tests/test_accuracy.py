"""
test_accuracy.py
----------------
Phase 5 "Definition of Done": run ~25 real questions through the agent
and AUTO-CHECK the count questions against a direct SQL computation, so
wrong answers are caught automatically.

How auto-check works:
  - We compute the true value with a direct read-only run_select().
  - We then check that the agent's natural-language answer contains that
    number (ignoring comma formatting).
  - COUNT questions are auto-checked (exact integers).
  - SUM/AVG questions are printed with the expected value for manual review
    (the agent may round, so exact matching is unfair).

NEEDS an ANTHROPIC_API_KEY in .env. Without it, this test skips cleanly.

Run from the project root with:
    python -m tests.test_accuracy
"""

from app.config import settings
from app.database.runner import run_select

# Each case: question + a SQL that computes the true scalar.
# auto=True  -> assert the agent's answer contains the number.
# auto=False -> just print expected vs answer for manual review.
CASES = [
    # ---- COUNT questions (auto-checked) ----
    {"q": "How many packets are in tblPacket?",
     "sql": "SELECT COUNT(*) FROM tblPacket", "auto": True},
    {"q": "How many records are in tblPacketHistory?",
     "sql": "SELECT COUNT(*) FROM tblPacketHistory", "auto": True},
    {"q": "How many packet issue records are there?",
     "sql": "SELECT COUNT(*) FROM tblPacketIssue", "auto": True},
    {"q": "How many final packets are there?",
     "sql": "SELECT COUNT(*) FROM tblFinalPacket", "auto": True},
    {"q": "How many jangad packets are there?",
     "sql": "SELECT COUNT(*) FROM tblJangadPackets", "auto": True},
    {"q": "How many junk records are there?",
     "sql": "SELECT COUNT(*) FROM tblJunk", "auto": True},
    {"q": "How many attendance records are in tblTimeAttendance?",
     "sql": "SELECT COUNT(*) FROM tblTimeAttendance", "auto": True},
    {"q": "How many records are in tblLabourResult?",
     "sql": "SELECT COUNT(*) FROM tblLabourResult", "auto": True},
    {"q": "How many records are in tblPlanMaster?",
     "sql": "SELECT COUNT(*) FROM tblPlanMaster", "auto": True},
    {"q": "How many incentive amount records are there?",
     "sql": "SELECT COUNT(*) FROM tblIncentiveAmount", "auto": True},
    {"q": "How many repair log records are in tblRepairLog?",
     "sql": "SELECT COUNT(*) FROM tblRepairLog", "auto": True},
    {"q": "How many records are in tblPacketPoint?",
     "sql": "SELECT COUNT(*) FROM tblPacketPoint", "auto": True},
    {"q": "How many distinct shapes are in tblPacketHistory?",
     "sql": "SELECT COUNT(DISTINCT Shape) FROM tblPacketHistory", "auto": True},
    {"q": "How many distinct employees (by EmpName) are in tblPacketHistory?",
     "sql": "SELECT COUNT(DISTINCT EmpName) FROM tblPacketHistory", "auto": True},
    {"q": "How many distinct Kapan names are in tblPacketHistory?",
     "sql": "SELECT COUNT(DISTINCT KapanName) FROM tblPacketHistory", "auto": True},
    {"q": "How many jangad packets have been received (IsReceived = 1)?",
     "sql": "SELECT COUNT(*) FROM tblJangadPackets WHERE IsReceived = 1", "auto": True},
    {"q": "How many recyclable junk records are there (IsRecyleble = 1)?",
     "sql": "SELECT COUNT(*) FROM tblJunk WHERE IsRecyleble = 1", "auto": True},
    {"q": "How many approved plans are in tblPlanMaster (IsApproved = 1)?",
     "sql": "SELECT COUNT(*) FROM tblPlanMaster WHERE IsApproved = 1", "auto": True},

    # ---- SUM/AVG questions (manual review - agent may round) ----
    {"q": "What is the total Amount in tblFinalPacket?",
     "sql": "SELECT SUM(Amount) FROM tblFinalPacket", "auto": False},
    {"q": "What is the total Weight in tblJunk?",
     "sql": "SELECT SUM(Weight) FROM tblJunk", "auto": False},
    {"q": "What is the total Carat in tblJangadPackets?",
     "sql": "SELECT SUM(Carat) FROM tblJangadPackets", "auto": False},

    # ---- List/exploratory questions (manual review) ----
    {"q": "List 5 distinct shapes found in tblPacketHistory.",
     "sql": None, "auto": False},
    {"q": "Give me the top 5 employees by number of rows in tblPacketHistory.",
     "sql": None, "auto": False},
    {"q": "What does the column 'Weight' represent in tblFinalPacket?",
     "sql": None, "auto": False},
]


def _expected_scalar(sql: str):
    """Run a direct read-only query and return the single scalar value."""
    result = run_select(sql)
    if not result["ok"] or not result["rows"]:
        return None
    first_row = result["rows"][0]
    return list(first_row.values())[0]


def _answer_contains_number(answer: str, number) -> bool:
    """True if the agent's answer contains `number` (ignoring digit separators)."""
    clean = answer
    # Strip common thousands separators: comma, regular/narrow/no-break spaces.
    for ch in (",", " ", " ", " "):
        clean = clean.replace(ch, "")
    return str(int(number)) in clean


def run_all():
    # Make printing UTF-8 safe (agent answers may contain unicode separators).
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not settings.GROQ_API_KEY:
        print("SKIPPED - no GROQ_API_KEY in .env. Add it to run accuracy tests.")
        print(f"({len(CASES)} questions are ready to run once the key is added.)")
        return

    from app.agent.agent import ask

    passed, failed, manual = 0, 0, 0

    for case in CASES:
        print("\n" + "=" * 72)
        print("Q:", case["q"])
        result = ask(case["q"])
        answer = result["answer"]
        for sql in result["sql_used"]:
            print("   agent SQL:", sql)
        print("A:", answer)

        if case["sql"] and case["auto"]:
            expected = _expected_scalar(case["sql"])
            ok = expected is not None and _answer_contains_number(answer, expected)
            print(f"   expected: {expected} -> {'PASS' if ok else 'FAIL'}")
            if ok:
                passed += 1
            else:
                failed += 1
        elif case["sql"]:
            expected = _expected_scalar(case["sql"])
            print(f"   expected (manual review): {expected}")
            manual += 1
        else:
            print("   (manual review - no auto-check)")
            manual += 1

    print("\n" + "=" * 72)
    print(f"AUTO-CHECK: {passed} passed, {failed} failed | {manual} for manual review")
    print("=" * 72)
    assert failed == 0, f"{failed} auto-checked questions returned the wrong number."


if __name__ == "__main__":
    run_all()
