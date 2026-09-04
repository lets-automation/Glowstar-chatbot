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
    # Added 2026-08-21. This one was BROKEN when the test was written: scoring
    # counted shared tokens flat, so "damage" (in 2 of 53 notes - the entire
    # signal) was worth exactly as much as "kapan" (10 of 53) or "year" (5 of
    # 53). Nine notes tied at 1 point, the top-10 cut fell through to source
    # order, and the one note saying a damage Amount is Points x Rate rather
    # than rupees lost its slot to the 548-token stock-report note. Fixed by
    # weighting each shared token by log(N/df); see note_router.score_note.
    ("damage report kapan wise for this year",
     "DAMAGE IS POINTS"),
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


# ---------------------------------------------------------------------------
# The empty-token path (fixed 2026-08-21).
#
# _tokens() drops stop-words and any word of two characters or fewer, so a
# surprising amount of ordinary phrasing reduces to nothing at all. The old
# fallback was `return list(notes)` - EVERY note, unrouted - which meant the
# vaguest questions got the LEAST focused prompt: 17,652 tokens of notes against
# ~7,000 for a specific question, and 48 competing rules on exactly the input
# where the model most needs one clear instruction.
# ---------------------------------------------------------------------------

VAGUE = ["give me the report", "show all data", "how many", "list all",
         "what is that", "ok give report"]


@pytest.mark.parametrize("question", VAGUE)
def test_a_question_with_no_recognisable_word_gets_no_topical_notes(question):
    from app.schema.note_router import _is_always_on, _tokens

    assert not _tokens(question), f"{question!r} should tokenise to nothing"
    picked = select_notes(list(DATA_NOTES), question)
    assert picked, "the safety notes must still be sent"
    assert all(_is_always_on(n) for n in picked), (
        "an unrecognisable question is evidence for no topical note"
    )


@pytest.mark.parametrize("question", VAGUE)
def test_vague_questions_are_no_longer_the_biggest_prompt(question):
    """The regression this guards: a vague question cost MORE than a specific
    one. It must now cost less."""
    specific = len(render_data_notes("how many packets are on jangad"))
    assert len(_rendered(question)) <= specific, (
        f"{question!r} still ships more guidance than a specific question"
    )


def test_no_question_at_all_still_returns_everything():
    """Distinct from the case above: no question means no routing was REQUESTED
    (tests, offline inspection), not that routing found nothing."""
    assert len(render_data_notes()) > len(render_data_notes("show all data"))


# ---------------------------------------------------------------------------
# Rare-token weighting.
# ---------------------------------------------------------------------------

def test_a_rare_token_outscores_a_common_one():
    from app.schema.note_router import _idf

    idf = _idf(tuple(DATA_NOTES))
    # 'damage' appears in 2 of 53 notes; 'kapan' in 10. Flat counting scored
    # them equally, which is how the damage note lost its slot.
    assert idf.get("damage", 0) > idf.get("kapan", 0) * 1.5, (
        "a discriminating word must be worth more than a common one"
    )


def test_the_relative_floor_is_not_tightened_past_the_critical_notes():
    """0.35 was found empirically: at 0.45 the routing drops 'DATE PLACEMENT IS
    CRITICAL' for a production question, for a saving of ~350 tokens. If someone
    tightens this to buy tokens, the CRITICAL cases above fail first - but this
    states the reason so the next person does not have to rediscover it."""
    from app.schema import note_router

    assert note_router._RELATIVE_FLOOR <= 0.35, (
        "tightening the floor drops locked guidance - see the CRITICAL list"
    )
