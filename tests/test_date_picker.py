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
# PERIOD MEMORY across turns.
#
# Regression lock. needs_date() declared `history` and documented it as handling
# follow-ups, but the body never read it and main.py never passed it. So the
# picker re-appeared on EVERY follow-up: the user tapped "June 2026", then
# "now the damage report" put the picker straight back on screen, and again for
# the turn after that. The period they already chose is right there in the
# conversation.
# ---------------------------------------------------------------------------
def _hist(*questions):
    return [{"role": "user", "content": q} for q in questions]


@pytest.mark.parametrize("q,history", [
    ("give me the damage report", _hist("production for June 2026")),
    ("now the damage report", _hist("stock report", "from 1 Jun to 30 Jun 2026")),
    ("kapan wise production", _hist("show me last month's output")),
    ("and the jangad report", _hist("GIA results for 2026-06-01 to 2026-06-30")),
])
def test_period_already_given_in_the_thread_suppresses_the_picker(q, history):
    assert needs_date(q, history) is False, q


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
