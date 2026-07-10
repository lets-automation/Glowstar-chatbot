"""
test_history.py
---------------
Server-side chat-history store (app/core/history.py) + the /threads endpoints.

The real deployment stores threads in the history-db Postgres container; these
tests run the SAME store code against an in-memory sqlite engine (the table
declares JSON with a Postgres-only JSONB variant precisely so this works), so
no database service is needed to run them.

Run from the project root with:
    python -m pytest tests/test_history.py -q
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.api.main as api_main
from app.api.main import app
from app.config import settings
from app.core import history
from app.core.rate_limit import enforce_history_rate_limit

_FAKE_USER = {"username": "tester", "display_name": "Tester"}

client = TestClient(app)

_MSGS = [
    {"id": "u-1", "role": "user", "content": "how many packets today?"},
    {"id": "a-1", "role": "assistant", "content": "There are 42.", "ok": True},
]


@pytest.fixture()
def store(monkeypatch):
    """In-memory sqlite standing in for the history-db Postgres container.
    StaticPool + check_same_thread=False -> every connection (including ones
    TestClient makes from worker threads) sees the SAME in-memory database."""
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    history._metadata.create_all(engine)
    monkeypatch.setattr(history, "_engine", engine)
    monkeypatch.setattr(settings, "HISTORY_DB_URL", "sqlite://")  # enabled() -> True
    # The history endpoints use their own rate limiter (separate bucket from
    # /chat); bypass it like conftest bypasses enforce_rate_limit.
    app.dependency_overrides[enforce_history_rate_limit] = lambda: _FAKE_USER
    yield engine
    app.dependency_overrides.pop(enforce_history_rate_limit, None)


# --- The store itself ---

def test_store_crud_roundtrip(store):
    history.upsert_thread("t-1", _MSGS, title="packets", created_at=1000)

    listed = history.list_threads()
    assert [t["id"] for t in listed] == ["t-1"]
    assert listed[0]["title"] == "packets"
    assert listed[0]["createdAt"] == 1000
    assert "messages" not in listed[0]  # list is metadata-only

    full = history.get_thread("t-1")
    assert full["messages"] == _MSGS

    # Update WITHOUT a title (the mid-turn autosave) keeps the existing title.
    history.upsert_thread("t-1", _MSGS + [{"id": "u-2", "role": "user", "content": "and yesterday?"}])
    full = history.get_thread("t-1")
    assert full["title"] == "packets"
    assert len(full["messages"]) == 3

    assert history.delete_thread("t-1") is True
    assert history.get_thread("t-1") is None
    assert history.delete_thread("t-1") is False  # already gone


def test_soft_delete_is_recoverable(store):
    """Delete tombstones the thread (excluded from list/get) but restore brings
    it back — so a delete in the shared no-auth pool isn't instantly destructive."""
    history.upsert_thread("t-sd", _MSGS, title="soft")
    assert history.delete_thread("t-sd") is True
    assert history.get_thread("t-sd") is None            # hidden from get
    assert [t["id"] for t in history.list_threads()] == []  # and from the list
    assert history.delete_thread("t-sd") is False         # already deleted

    assert history.restore_thread("t-sd") is True         # undo
    assert history.get_thread("t-sd") is not None
    assert [t["id"] for t in history.list_threads()] == ["t-sd"]
    assert history.restore_thread("t-sd") is False        # nothing to restore now


def test_purge_removes_old_tombstones(store, monkeypatch):
    """A soft-deleted thread older than the retention window is hard-purged
    (opportunistically, on the next delete) so tombstones can't accumulate."""
    monkeypatch.setattr(history, "SOFT_DELETE_RETENTION_MS", 1000)  # 1s window
    # Insert a thread and force its tombstone far into the past.
    history.upsert_thread("t-old", _MSGS, title="old")
    engine = history.get_engine()
    with engine.begin() as conn:
        conn.execute(
            history.chat_threads.update()
            .where(history.chat_threads.c.id == "t-old")
            .values(deleted_at=1)  # epoch-ms=1 -> ancient
        )
    # Any later delete triggers the opportunistic purge.
    history.upsert_thread("t-trigger", _MSGS, title="trigger")
    history.delete_thread("t-trigger")
    # The ancient tombstone is gone for good -> not even restorable.
    assert history.restore_thread("t-old") is False


def test_thread_count_cap_refuses_new_threads(store, monkeypatch):
    monkeypatch.setattr(history, "MAX_THREADS", 2)
    history.upsert_thread("t-1", _MSGS, title="1")
    history.upsert_thread("t-2", _MSGS, title="2")
    with pytest.raises(history.ThreadLimitError):
        history.upsert_thread("t-3", _MSGS, title="3")  # over cap -> refused
    # Updating an EXISTING thread must still work at the cap.
    history.upsert_thread("t-1", _MSGS + [{"role": "user", "content": "more"}], title="1")
    # A soft-delete frees a slot -> a new thread fits again.
    history.delete_thread("t-2")
    history.upsert_thread("t-3", _MSGS, title="3")
    assert {t["id"] for t in history.list_threads()} == {"t-1", "t-3"}


def test_cap_maps_to_507_endpoint(store, monkeypatch):
    monkeypatch.setattr(history, "MAX_THREADS", 1)
    assert client.put("/threads/t-a", json={"messages": _MSGS}).status_code == 200
    assert client.put("/threads/t-b", json={"messages": _MSGS}).status_code == 507


def test_restore_endpoint(store):
    client.put("/threads/t-r", json={"title": "r", "messages": _MSGS})
    client.delete("/threads/t-r")
    assert client.get("/threads/t-r").status_code == 404
    assert client.post("/threads/t-r/restore").json() == {"restored": True}
    assert client.get("/threads/t-r").status_code == 200
    assert client.post("/threads/t-nope/restore").status_code == 404


def test_store_lists_newest_first(store):
    history.upsert_thread("t-old", _MSGS, title="old")
    history.upsert_thread("t-new", _MSGS, title="new")
    history.upsert_thread("t-old", _MSGS, title="old")  # touching bumps updated_at
    assert [t["id"] for t in history.list_threads()] == ["t-old", "t-new"]


# --- The /threads endpoints ---

def test_endpoints_crud_roundtrip(store):
    put = client.put(
        "/threads/t-123-4",
        json={"title": "packets", "messages": _MSGS, "createdAt": 1000},
    )
    assert put.status_code == 200

    listed = client.get("/threads").json()["threads"]
    assert [t["id"] for t in listed] == ["t-123-4"]

    one = client.get("/threads/t-123-4").json()
    assert one["title"] == "packets"
    assert one["messages"] == _MSGS

    assert client.delete("/threads/t-123-4").json() == {"deleted": True}
    assert client.get("/threads/t-123-4").status_code == 404


def test_endpoint_rejects_bad_thread_id(store):
    # Path charset is constrained; anything else must 422, not reach the store.
    assert client.put("/threads/bad id!", json={"messages": []}).status_code == 422


def test_endpoint_rejects_oversized_thread(store, monkeypatch):
    # Shrink the cap so the test doesn't need a real 5 MB body.
    monkeypatch.setattr(api_main, "_THREAD_MAX_BYTES", 100)
    big = [{"id": "a-1", "role": "assistant", "content": "x" * 500}]
    res = client.put("/threads/t-big", json={"messages": big})
    assert res.status_code == 413


def test_size_cap_measured_in_bytes_not_chars(store, monkeypatch):
    # Multi-byte content: 60 Gujarati chars = 60 code points but ~180 UTF-8 bytes.
    # A char-based cap would accept it; the byte-based cap must reject it.
    monkeypatch.setattr(api_main, "_THREAD_MAX_BYTES", 120)
    multibyte = [{"id": "a-1", "role": "assistant", "content": "ગુ" * 30}]  # 60 chars, ~180 bytes
    res = client.put("/threads/t-mb", json={"messages": multibyte})
    assert res.status_code == 413, "byte-based cap should reject multi-byte content a char count would pass"


def test_history_from_messages_rebuilds_clean_turns():
    """The 'bot forgets' fix: reopening a thread whose Redis session expired
    rebuilds follow-up context from the durable thread messages — keeping only
    real user/assistant text, dropping banners/placeholders/empties."""
    from app.api import sessions

    msgs = [
        {"id": "u-1", "role": "user", "content": "how many packets?"},
        {"id": "a-1", "role": "assistant", "content": "164,573.", "ok": True},
        {"id": "a-x", "role": "assistant", "content": "", "ok": True},          # empty -> skip
        {"id": "a-e", "role": "assistant", "content": "⚠️ error", "transient": True},  # banner -> skip
        {"id": "a-s", "role": "assistant", "content": "_Stopped._"},            # placeholder -> skip
        {"id": "u-2", "role": "user", "content": "and by colour?"},
    ]
    rebuilt = sessions.history_from_messages(msgs)
    assert rebuilt == [
        {"role": "user", "content": "how many packets?"},
        {"role": "assistant", "content": "164,573."},
        {"role": "user", "content": "and by colour?"},
    ]


def test_history_from_messages_caps_turns():
    from app.api import sessions

    many = []
    for i in range(40):
        many.append({"role": "user", "content": f"q{i}"})
        many.append({"role": "assistant", "content": f"a{i}"})
    rebuilt = sessions.history_from_messages(many)
    assert len(rebuilt) == sessions.MAX_TURNS * 2  # only the most recent turns kept
    assert rebuilt[-1] == {"role": "assistant", "content": "a39"}


def test_disabled_store_returns_503(monkeypatch):
    # No HISTORY_DB_URL -> clean 503 (frontend then stays on localStorage).
    monkeypatch.setattr(settings, "HISTORY_DB_URL", "")
    app.dependency_overrides[enforce_history_rate_limit] = lambda: _FAKE_USER
    try:
        assert client.get("/threads").status_code == 503
    finally:
        app.dependency_overrides.pop(enforce_history_rate_limit, None)
