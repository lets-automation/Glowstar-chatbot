"""
test_lab_picker.py
------------------
THE "WHICH LAB?" FOLLOW-UP, THROUGH THE API.

tests/test_lab_gate.py covers the decision. This covers the WIRING: that both
/chat and /chat/stream actually consult the gate, return its chips, and do so
WITHOUT calling an LLM or touching the database - the same contract
test_date_picker.py holds the date gate to.

The wiring is the half that silently rots. A gate that decides perfectly and is
never called is indistinguishable from no gate at all, and nothing else in the
suite would notice.
"""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.api.main as main

client = TestClient(main.app)

# A pending question that names no lab - exactly what must be asked about.
Q_NO_LAB = "how many packets are pending for the lab last month"
# ...and one that names GIA, which must sail straight through.
Q_WITH_LAB = "gia pending last month"


def _no_session(monkeypatch):
    """Conversation memory lives in Redis, unreachable from the test host."""
    from app.api import sessions

    monkeypatch.setattr(sessions, "get_history", lambda *a, **k: [])
    monkeypatch.setattr(sessions, "add_turn", lambda *a, **k: None)


def _boom(*a, **k):                       # pragma: no cover - must never run
    raise AssertionError("the gate must answer without calling the model")


class TestChatEndpoint:

    def test_it_asks_which_lab_before_answering(self, monkeypatch):
        _no_session(monkeypatch)
        with patch.object(main, "_ask_with_cost_tracking", _boom):
            r = client.post("/chat", json={"question": Q_NO_LAB,
                                           "session_id": "lab1"})
        assert r.status_code == 200
        body = r.json()
        assert "lab" in body["answer"].lower()
        assert len(body["clarify_options"]) == 4
        assert "all labs" in body["clarify_options"][0]

    def test_it_does_not_also_pop_the_date_picker(self, monkeypatch):
        """Two pickers for one question would be unusable. date_gate already
        treats "pending" as a current-state question and stands down."""
        _no_session(monkeypatch)
        with patch.object(main, "_ask_with_cost_tracking", _boom):
            r = client.post("/chat", json={"question": Q_NO_LAB,
                                           "session_id": "lab2"})
        assert r.json()["ask_date"] is False

    def test_a_named_lab_goes_straight_through_to_the_model(self, monkeypatch):
        _no_session(monkeypatch)
        sentinel = {"answer": "answered", "sql_used": [], "rows_returned": 0,
                    "ok": True, "widgets": [], "data_columns": [],
                    "data_rows": [], "clarify_options": [], "ask_date": False,
                    "citation": "", "export_query": None, "suggestions": []}
        with patch.object(main, "_ask_with_cost_tracking", return_value=sentinel):
            r = client.post("/chat", json={"question": Q_WITH_LAB,
                                           "session_id": "lab3"})
        assert r.json()["answer"] == "answered"

    def test_tapping_the_all_labs_chip_answers_instead_of_re_asking(self, monkeypatch):
        """THE LOOP, end to end. The chip's text comes back as the next
        question; if it were not recognised the API would ask again forever."""
        _no_session(monkeypatch)
        with patch.object(main, "_ask_with_cost_tracking", _boom):
            first = client.post("/chat", json={"question": Q_NO_LAB,
                                               "session_id": "lab4"}).json()
        chip = first["clarify_options"][0]

        sentinel = {"answer": "answered", "sql_used": [], "rows_returned": 0,
                    "ok": True, "widgets": [], "data_columns": [],
                    "data_rows": [], "clarify_options": [], "ask_date": False,
                    "citation": "", "export_query": None, "suggestions": []}
        with patch.object(main, "_ask_with_cost_tracking", return_value=sentinel):
            second = client.post("/chat", json={"question": chip,
                                                "session_id": "lab4"}).json()
        assert second["answer"] == "answered", "the all-labs chip re-asked"


class TestStreamEndpoint:

    def test_it_streams_the_same_question(self, monkeypatch):
        _no_session(monkeypatch)
        with patch.object(main, "_ask_with_cost_tracking", _boom):
            r = client.post("/chat/stream", json={"question": Q_NO_LAB,
                                                  "session_id": "lab5"})
        assert r.status_code == 200
        payloads = [json.loads(line[len("data: "):])
                    for line in r.text.splitlines() if line.startswith("data: ")]
        results = [p["data"] for p in payloads if p.get("type") == "result"]
        assert results, "the stream must carry a result event"
        assert len(results[0]["clarify_options"]) == 4
        assert "all labs" in results[0]["clarify_options"][0]
