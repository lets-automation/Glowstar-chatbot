"""
test_answer_cache.py
--------------------
Pre-warmed answers. The free tier gives ~20 requests/DAY and a question costs ~2,
so a 15-20 question client meeting cannot fit. Warming the expected questions in
advance makes the demo independent of quota.

Safe because the DB is a restored backup (static): a cached answer equals a fresh
one. The key includes the DB name, so a new backup invalidates everything.
"""
import os

import pytest

from app.agent import answer_cache


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("ANSWER_CACHE_ENABLED", "true")
    answer_cache.clear()
    yield
    answer_cache.clear()


GOOD = {"answer": "305 packets in June.", "ok": True, "rows_returned": 305,
        "sql_used": ["SELECT 1"]}


def test_round_trip():
    assert answer_cache.put("Fency production June 2026", GOOD) is True
    got = answer_cache.get("Fency production June 2026")
    assert got and got["answer"] == GOOD["answer"]


def test_lookup_is_insensitive_to_case_space_and_punctuation():
    answer_cache.put("Fency department production for June 2026", GOOD)
    assert answer_cache.get("  fency DEPARTMENT production for June 2026?  ")


def test_miss_returns_none():
    assert answer_cache.get("a question nobody asked") is None


def test_failed_turns_are_never_cached():
    # Caching a quota/error turn would replay the failure forever.
    assert answer_cache.put("q", {"answer": "busy right now", "ok": False}) is False
    assert answer_cache.put("q", {"answer": "", "ok": True}) is False
    assert answer_cache.get("q") is None


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ANSWER_CACHE_ENABLED", raising=False)
    assert answer_cache.enabled() is False
    assert answer_cache.put("q", GOOD) is False
    assert answer_cache.get("q") is None


def test_key_changes_with_the_database(monkeypatch):
    # Restoring a newer backup must invalidate warmed answers automatically.
    k1 = answer_cache.key_for("same question")
    monkeypatch.setattr(answer_cache.settings, "DB_NAME", "AasthaErp_2027")
    assert answer_cache.key_for("same question") != k1
