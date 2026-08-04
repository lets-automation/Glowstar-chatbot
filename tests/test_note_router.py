"""
test_note_router.py
-------------------
The guidance is now ROUTED: each question gets the notes that match it plus the
always-on safety notes, instead of all ~10k tokens of notes every turn (which
buried the relevant guidance and made the same question answer well once and
thinly the next time).

Routing is only safe if it never drops the note a question depends on. These
tests assert exactly that, per real client question — deterministically, with no
LLM and no database.
"""
import pytest

from app.schema.glossary import DATA_NOTES, JOIN_HINTS, render_data_notes
from app.schema.note_router import select_notes

_ALL = list(DATA_NOTES) + list(JOIN_HINTS)


def _rendered(question: str) -> str:
    return render_data_notes(question)


# (question, a distinctive phrase from the note that MUST survive routing)
CRITICAL = [
    ("give me the damage report of department MFG - 1",
     "InceDamageTypeName"),
    ("Provide past month GIA results of Fency department employees",
     "RapVer='PLS'"),
    ("Fency department production for June 2026",
     "DATE PLACEMENT IS CRITICAL"),
    ("Give me the stock report",
     "STOCK / YIELD REPORT"),
    ("how many diamonds are in process and in which department",
     "WIP / IN-PROCESS"),
    ("how many packets are on jangad",
     "IsReceived"),
    ("bonus of the Fency workers",
     "BonusAmount"),
    ("where is packet 131 of kapan NR26 now",
     "WHERE IS THIS DIAMOND"),
    ("maker fresh and check issue report",
     "IsFresh"),
]


@pytest.mark.parametrize("question,must_contain", CRITICAL)
def test_routing_keeps_the_note_the_question_needs(question, must_contain):
    text = _rendered(question)
    assert must_contain in text, (
        f"routing dropped critical guidance for {question!r}: {must_contain!r}"
    )


ALWAYS_ON = [
    "DATA CUTOFF",        # backup, not live -> "today" can return 0 rows
    "COUNT DISTINCT",     # COUNT(*) over-counts on transactional tables
    "SALARY / PAYROLL",   # restricted data must never be routed away
    "KNOWN-EMPTY TABLES", # never query a dead table
]


@pytest.mark.parametrize("marker", ALWAYS_ON)
@pytest.mark.parametrize("question", [
    "how many employees do we have",
    "give me the damage report",
    "bonus of the Fency workers",
])
def test_safety_notes_survive_every_question(marker, question):
    # These prevent wrong answers on ANY topic, so they must never be routed out.
    assert marker in _rendered(question), f"{marker} missing for {question!r}"


def test_routing_actually_reduces_the_prompt():
    full = render_data_notes()
    routed = render_data_notes("how many packets are on jangad")
    assert len(routed) < len(full) * 0.8, (
        "routing should cut a meaningful share of the notes; "
        f"full={len(full)} routed={len(routed)}"
    )


def test_empty_question_returns_everything():
    # Callers with no question (tests, offline inspection) must still see it all.
    assert len(render_data_notes()) >= len(render_data_notes("jangad"))


def test_selection_is_order_stable():
    # A stable prompt prefix keeps behaviour (and prompt caching) predictable.
    q = "give me the damage report of department MFG - 1"
    assert select_notes(_ALL, q) == select_notes(_ALL, q)


def test_suite_does_not_burn_demo_quota():
    """
    Guard: live-LLM tests must stay OPT-IN.

    The free tier is ~20 requests/DAY shared with the client demo. A routine
    `pytest tests/` run used to fire real provider calls, quietly consuming the
    quota the demo then needed. Live tests carry the `live_llm` marker and are
    skipped unless RUN_LIVE_LLM_TESTS=true (see tests/conftest.py).
    """
    import pathlib

    conftest = (pathlib.Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    assert "RUN_LIVE_LLM_TESTS" in conftest
    assert "live_llm" in conftest
    # and the known live test is actually marked
    api = (pathlib.Path(__file__).parent / "test_api.py").read_text(encoding="utf-8")
    assert "@pytest.mark.live_llm" in api
