"""
test_date_picker.py
-------------------
The DATE PICKER flow (client request, 2026-07): a report question with NO period
("give me the stock report") must ASK for the date range via a UI picker instead
of silently guessing a range or dumping all history.

Mechanism: the model ends its reply with an `ASKDATE:` marker -> postprocess strips
it and sets ask_date=True -> the API returns that flag -> the frontend renders
DateRangePicker (presets + custom from/to). These tests lock the backend half of
that chain WITHOUT calling an LLM, by injecting the model reply directly.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.api.main as main
from app.agent.postprocess import enrich

client = TestClient(main.app)


def _no_session(monkeypatch):
    """Conversation memory lives in Redis, which isn't reachable from the test
    host (it is internal to the Docker network). These tests are about the
    date-picker flow, not session storage, so stub both sides out."""
    from app.api import sessions

    monkeypatch.setattr(sessions, "get_history", lambda *a, **k: [])
    monkeypatch.setattr(sessions, "add_turn", lambda *a, **k: None)

# What the model returns when it wants the period (no query run on that turn).
_ASKDATE_REPLY = {
    "answer": "Which period should I use for the stock report?\nASKDATE:",
    "sql_used": [],
    "rows_returned": 0,
    "ok": True,
    "widgets": [],
    "data_columns": [],
    "data_rows": [],
}


def test_chat_returns_ask_date_and_hides_the_marker(monkeypatch):
    _no_session(monkeypatch)
    # NOTE: use a question that already names a period, so the deterministic
    # date_gate does NOT short-circuit — this test covers the OTHER path, where
    # the model itself decides to ask and emits the ASKDATE: marker.
    with patch.object(main, "_ask_with_cost_tracking", return_value=enrich(_ASKDATE_REPLY)):
        r = client.post("/chat", json={"question": "damage report for June 2026", "session_id": "dp1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ask_date"] is True, "the UI needs this flag to show the date picker"
    # The marker is an internal protocol token — it must never be shown to a user.
    assert "ASKDATE" not in body["answer"]
    assert body["answer"].strip().endswith("?")


def test_normal_answer_does_not_trigger_the_picker(monkeypatch):
    _no_session(monkeypatch)
    normal = dict(_ASKDATE_REPLY, answer="In June 2026 there were 305 packets.",
                  sql_used=["SELECT 1"], rows_returned=1)
    with patch.object(main, "_ask_with_cost_tracking", return_value=enrich(normal)):
        r = client.post("/chat", json={"question": "june production", "session_id": "dp2"})
    assert r.status_code == 200
    assert r.json()["ask_date"] is False


def test_ungrounded_answer_still_reports_ask_date_false():
    # The anti-fabrication branch returns its own dict — it must carry the key too,
    # or the frontend would read `undefined` and could render a stray picker.
    out = enrich({"answer": "| a | b |\n|---|---|\n| 1 | 2 |", "sql_used": [],
                  "rows_returned": 0, "ok": True})
    assert out["ask_date"] is False


# ---------------------------------------------------------------------------
# The DETERMINISTIC gate. A prompt rule alone was not reliable — the model
# answered "give me the damage report of department MFG - 1" with all 484
# records spanning two years. This decides in code, before any LLM call.
# ---------------------------------------------------------------------------
import pytest

from app.agent.date_gate import needs_date

# Report-style questions with NO period -> must show the picker.
@pytest.mark.parametrize("q", [
    "give me the damage report of department MFG - 1",
    "Give me the stock report",
    "Provide GIA results of Fency department employees",
    "Fency department production",
    "show me jangad report",          # 'jangad' once matched the month 'jan'
    "employee wise earnings",
    "kapan wise production",
])
def test_report_without_period_asks_for_dates(q):
    assert needs_date(q) is True, q


# Anything that already pins a period, or isn't a report, must pass through.
@pytest.mark.parametrize("q", [
    "give me the damage report of department MFG - 1 from 1 Jun 2026 to 30 Jun 2026",
    "Provide past month GIA results of Fency department employees",
    "damage report for June 2026",
    "stock report last month",
    "production this year",
    "all time damage report",
    "how many employees do we have?",
    "what is a kapan?",
    "which packets are in stock",              # current state, no period applies
    "how many packets are currently on jangad",
    "aa mahine ketla nang thaya?",             # Gujlish "this month"
    "hello",
    # WIP is a LIVE snapshot of where stones are NOW — a period makes no sense.
    "how many diamonds are in process and in which department",
    "department wise in process report",
    "work in process report",
    "wip report",
])
def test_no_date_prompt_when_not_needed(q):
    assert needs_date(q) is False, q


def test_stream_returns_the_picker_without_calling_the_model(monkeypatch):
    # The gate must short-circuit BEFORE the LLM: instant, free, and immune to
    # whichever provider/model is configured.
    called = []
    monkeypatch.setattr(main, "_ask_with_cost_tracking",
                        lambda *a, **k: called.append(1) or {})
    r = client.post("/chat/stream",
                    json={"question": "give me the damage report", "session_id": "dg9"})
    assert r.status_code == 200
    assert '"ask_date": true' in r.text.replace("'", '"').lower()
    assert not called, "the date gate must not spend an LLM call"


@pytest.mark.parametrize("q", [
    # COLD-TEST finding: "how many oval diamonds do we have in stock?" was met
    # with a date picker. Stock/hold are LIVE snapshots — a period is nonsense.
    "how many oval diamonds do we have in stock",
    "atyare ketla diamond hold par che",          # Gujlish: how many on hold now
    "how many stones are out on memo right now",
    "how many packets are on hold",
])
def test_current_state_questions_never_ask_for_a_date(q):
    assert needs_date(q) is False, q


# ---------------------------------------------------------------------------
# PERIOD MEMORY across turns - ON (_PERIOD_MEMORY_TURNS = 2), WITH INJECTION.
#
# History: the memory was switched OFF because it only SILENCED the picker and
# then trusted the model to notice the period sitting in the conversation. The
# model did not - measured twice on 2026-08-20, a follow-up widened to ALL
# history and blew the context ("That request was too large"). The note left
# here said the expectations should flip back only alongside the fix it
# prescribed: INJECT the remembered period into the request.
#
# That fix now exists (date_gate.carried_period_directive, injected by
# tools.system_prompt_for), so these expectations are flipped - and the tests
# below assert BOTH halves. Suppressing the picker without the injection is the
# regression that broke it before, so it is tested, not assumed.
#
# The other half of the trade was real too: in the 2026-08-21 client demo the
# user said "may month" and the very next turn asked which month again.
# ---------------------------------------------------------------------------
def _hist(*questions):
    return [{"role": "user", "content": q} for q in questions]


@pytest.mark.parametrize("q,history", [
    ("give me the damage report", _hist("production for June 2026")),
    ("now the damage report", _hist("stock report", "from 1 Jun to 30 Jun 2026")),
    ("kapan wise production", _hist("show me last month's output")),
    ("and the jangad report", _hist("GIA results for 2026-06-01 to 2026-06-30")),
])
def test_a_recent_period_suppresses_the_picker(q, history):
    """A follow-up reuses the period the user already gave."""
    assert needs_date(q, history) is False, q


@pytest.mark.parametrize("q,history", [
    ("give me the damage report", _hist("production for June 2026")),
    ("now the damage report", _hist("stock report", "from 1 Jun to 30 Jun 2026")),
    ("and the jangad report", _hist("GIA results for 2026-06-01 to 2026-06-30")),
])
def test_and_that_period_is_injected_not_merely_remembered(q, history):
    """THE safety condition. Silencing the picker without putting the period in
    the request is what made the model query all of history."""
    from app.agent import date_gate

    with date_gate.carrying_period(history, q):
        directive = date_gate.carried_period_directive()
    assert "PERIOD CARRIED OVER" in directive, q
    assert "Do NOT widen to all history" in directive, q


@pytest.mark.parametrize("q", [
    "give me the damage report for June 2026",
    "kapan wise production from 1 Jul to 31 Jul 2026",
])
def test_a_period_in_the_question_itself_still_suppresses_the_picker(q):
    """The gate only ever needed the period to be in THIS request - and that
    path is unaffected by turning the cross-turn memory off."""
    assert needs_date(q, _hist("something else entirely")) is False, q


@pytest.mark.parametrize("q,history", [
    # No period anywhere -> still ask.
    ("give me the damage report", _hist("hello", "what is a kapan")),
    ("kapan wise production", None),
    ("stock report", []),
    # Too far back: the conversation has moved on, so asking again is right.
    ("stock report", _hist("June 2026 report", "a", "b", "c", "d")),
])
def test_picker_still_appears_when_no_recent_period(q, history):
    assert needs_date(q, history) is True, q


def test_only_user_turns_count_as_the_period_source():
    """An assistant message mentioning a month is not the user choosing one."""
    history = [{"role": "assistant", "content": "In June 2026 there were 305 packets."}]
    assert needs_date("give me the damage report", history) is True


def test_api_passes_history_to_the_gate():
    """main.py must actually hand the conversation to the gate - the whole bug
    was that it never did."""
    import inspect

    import app.api.main as _main

    src = inspect.getsource(_main)
    assert src.count("date_gate.needs_date(request.question, convo_history)") == 2, (
        "both /chat and /chat/stream must pass history to the date gate"
    )


def test_gates_survive_an_unreachable_redis(monkeypatch):
    """The deterministic gates are supposed to need NO infrastructure - no LLM,
    no DB, and no session store. Loading history moved ahead of the date gate so
    the gate can see a period given earlier in the thread; that must not make a
    Redis outage break the reply. Conversation memory is optional CONTEXT."""
    from app.api import sessions

    def _boom(*a, **k):
        raise ConnectionError("Error 10061 connecting to localhost:6379")

    monkeypatch.setattr(sessions, "get_history", _boom)
    monkeypatch.setattr(sessions, "add_turn", lambda *a, **k: None)
    monkeypatch.setattr(main, "_ask_with_cost_tracking",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("the gate must not reach the model")))

    r = client.post("/chat/stream",
                    json={"question": "give me the damage report", "session_id": "redis-down"})
    assert r.status_code == 200
    assert '"ask_date": true' in r.text.replace("'", '"').lower()


# ---------------------------------------------------------------------------
# A NAMED KAPAN IS ITS OWN SCOPE
# ---------------------------------------------------------------------------
# Live 2026-09-03: "For kapan OR26, show packets where the MFG grade differs
# from the GIA grade on cut or clarity" was met with the date picker. _REPORT_RE
# matches the bare word "gia" and the question names no month, so the gate fired
# BEFORE any LLM call and asked for a date range on a question that has no time
# dimension. The bot then reported that as an inability to answer at all.
#
# A kapan is a parcel of rough, not a period; picking a month would narrow the
# result to whichever plan rows happen to fall inside it.


@pytest.mark.parametrize("q", [
    "For kapan OR26, show packets where the MFG grade differs from the GIA "
    "grade on cut or clarity",
    "kapan QA26 ma ketla piece hata?",
    "OQ26 kapan ma final point / final polish weight ketlu nikalyu?",
    "from kapan NS26 list packets with an approved CLV plan but no PLS",
    "kapan OS26 gia results",
    "kapan IK summary",                       # bare two-letter kapan name
])
def test_a_named_kapan_never_asks_for_a_date(q):
    assert needs_date(q, []) is False, q


@pytest.mark.parametrize("q", [
    # "kapan wise" is a report ACROSS kapans and genuinely needs a period.
    "kapan wise production report",
    "give me kapan-wise damage summary",
    "give me kapan wise gia summary",
])
def test_kapan_wise_is_still_a_report_that_needs_a_period(q):
    assert needs_date(q, []) is True, q


def test_a_two_letter_word_before_the_noun_is_not_a_kapan_code():
    """The reverse-order branch ("OQ26 kapan ma") must not fire on ordinary
    English. Before the noun the code has to carry digits, or "give me
    kapan-wise ..." matches on "me kapan" and suppresses the picker."""
    from app.agent.date_gate import names_a_kapan

    assert names_a_kapan("OQ26 kapan ma final polish weight") is True
    for q in ("give me kapan wise report", "in kapan wise terms",
              "of kapan wise damage"):
        assert names_a_kapan(q) is False, q


# ---------------------------------------------------------------------------
# THE GATES vs THE VERIFIED CORPUS
# ---------------------------------------------------------------------------
# Nothing swept the cold-case corpus through the GATES until 2026-09-03, and
# the OR26 kapan bug lived in exactly that blind spot: a gate can refuse a
# question before any LLM call, and no test noticed.
#
# Sweeping it found SEVEN more cases whose ground-truth SQL contains no date
# predicate at all - they are all-time counts, breakdowns, or proofs that a
# column is not recorded - and every one of them is met with the date picker
# instead of its answer.
#
# The list is asserted rather than fixed here because "should 'party wise
# jangad' default to all time or ask for a period?" is a product decision, not
# a bug with one right answer. What must not happen is the list growing
# silently, or a case that works today quietly joining it.


def _gate_blocked_cold_cases():
    from scripts.cold_cases import COLD_CASES
    from app.agent import access_guard, lab_gate

    out = {}
    for c in COLD_CASES:
        q = c.get("question") or ""
        if not q or not c.get("truthSql"):
            continue
        why = []
        if needs_date(q, []):
            why.append("date_picker")
        if lab_gate.needs_lab(q, []):
            why.append("lab_gate")
        if access_guard.is_pay_question(q):
            why.append("pay_guard")
        if why:
            out[c["id"]] = "+".join(why)
    return out


# Every one of these has a verified answer that needs no period. CT-04 is the
# pay guard and is deliberate - it refuses before any LLM call, by design.
KNOWN_GATE_BLOCKED = {
    "JP-1": "date_picker",    # "total ketla jangad" - all-time count
    "JP-3": "date_picker",    # party-wise breakdown, no period
    "DRS-3": "date_picker",   # repair reasons, no period
    "EDA-3": "date_picker",   # employee rating ranking, no period
    "CT-02": "date_picker",   # proves tblJunk.Grede is never recorded
    "CT-08": "date_picker",   # proves no yield column exists (metadata probe)
    "CT-09": "date_picker",   # kapan-level boil/chapka loss, no period
    "CT-04": "pay_guard",     # deliberate - refused before any LLM call
}


def test_no_new_cold_case_is_intercepted_by_a_gate():
    """SHRINK THIS LIST, NEVER GROW IT.

    A gate that fires on a question with a verified date-free answer costs
    the user that answer and hands them a picker instead.
    """
    blocked = _gate_blocked_cold_cases()
    new = {k: v for k, v in blocked.items() if k not in KNOWN_GATE_BLOCKED}
    assert not new, f"a gate started intercepting these: {new}"


def test_the_known_list_has_not_silently_changed_reason():
    blocked = _gate_blocked_cold_cases()
    for cid, why in KNOWN_GATE_BLOCKED.items():
        if cid in blocked:
            assert blocked[cid] == why, (
                f"{cid} is now blocked by {blocked[cid]}, was {why}")


def test_a_fixed_case_must_be_removed_from_the_list():
    """The other direction: if a fix unblocks one, the list must shrink so the
    count stays honest."""
    blocked = _gate_blocked_cold_cases()
    stale = [k for k in KNOWN_GATE_BLOCKED if k not in blocked]
    assert not stale, (
        f"these are no longer blocked - delete them from KNOWN_GATE_BLOCKED: {stale}")
