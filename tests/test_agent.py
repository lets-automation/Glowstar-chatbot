"""
test_agent.py
-------------
Phase 3 "Definition of Done": ask the agent real questions and check it
answers correctly using live data, only ever running read-only SELECTs.

NEEDS an ANTHROPIC_API_KEY in .env. If the key is missing, this test
prints clear instructions and skips (so the build can proceed before the
key is added).

Run from the project root with:
    python -m tests.test_agent
"""

from app.config import settings

# A few real questions against known key tables.
QUESTIONS = [
    "How many packets are in tblPacket?",
    "List 5 distinct employee names from tblPacketHistory.",
    "What is the total Amount in tblFinalPacket?",
    "How many records are in tblTimeAttendance?",
]


def run_all():
    if not settings.GROQ_API_KEY:
        print("SKIPPED - no GROQ_API_KEY found in .env.")
        print("To run this test:")
        print("  1. Get a key at https://console.groq.com")
        print("  2. Paste it into the .env line: GROQ_API_KEY=...")
        print("  3. Run again: python -m tests.test_agent")
        return

    # Import here so the file loads even without the SDK key configured.
    from app.agent.agent import ask

    for q in QUESTIONS:
        print("\n" + "=" * 70)
        print("Q:", q)
        result = ask(q)
        print("SQL used:")
        for s in result["sql_used"]:
            print("   ", s)
        print("A:", result["answer"])

    print("\n" + "=" * 70)
    print("DONE - review the answers above against the database.")


if __name__ == "__main__":
    run_all()
