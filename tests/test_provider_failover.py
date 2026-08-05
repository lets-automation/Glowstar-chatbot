"""
test_provider_failover.py
-------------------------
Gemini's free tier allows only ~20 requests/DAY per API key. When it ran out the
client saw "the assistant is busy right now" MID-DEMO — the single worst failure
mode for this product, because a correct system looks broken.

Fix: configure several keys (GEMINI_API_KEY + GEMINI_API_KEYS) and fail over
automatically on a quota/permission error, remembering the dead key so later
turns don't retry it. These tests lock that behaviour without calling Gemini.
"""
from unittest.mock import patch

import app.agent.gemini_backend as gb


def test_quota_errors_are_recognised():
    for msg in (
        "429 RESOURCE_EXHAUSTED: quota exceeded",
        "PermissionDenied: 403 forbidden",
        "API key not valid",
        "Rate limit reached",
    ):
        assert gb._is_quota_error(Exception(msg)) is True, msg


def test_real_bugs_are_not_mistaken_for_quota():
    # A genuine error must NOT silently burn every spare key.
    assert gb._is_quota_error(TypeError("Invalid column name 'Foo'")) is False


def test_failover_moves_to_the_next_key():
    tried = []

    def fake(question, model, history, on_event, file_context, api_key):
        tried.append(api_key)
        if len(tried) == 1:
            raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded")
        return {"answer": "ok", "sql_used": ["SELECT 1"], "rows_returned": 1, "ok": True}

    gb._EXHAUSTED_KEYS.clear()
    with patch.object(gb, "_ask_gemini_once", side_effect=fake), \
         patch.object(gb.settings, "GEMINI_API_KEY", "key-one"), \
         patch.object(gb.settings, "GEMINI_API_KEYS", "key-two"):
        out = gb.ask_gemini("q", "gemini-2.5-flash")

    assert out["answer"] == "ok", "the turn must succeed on the backup key"
    assert len(tried) == 2, "it must actually try the second key"
    # Exhaustion is tracked per (MODEL, key): the free-tier quota is per project
    # per model, so a key that ran out on one model still has capacity on the
    # next one. Recording the key alone threw that capacity away.
    assert ("gemini-2.5-flash", "key-one") in gb._EXHAUSTED_KEYS,         "the dead (model, key) pair must be remembered"
    assert "key-one" not in gb._EXHAUSTED_KEYS,         "a bare key must NOT be marked dead for every model"
    gb._EXHAUSTED_KEYS.clear()


def test_all_keys_exhausted_returns_friendly_answer_not_500():
    # Regression: raising here escaped as an HTTP 500 — the client would see a
    # server error instead of "the assistant is busy, try again in a moment".
    def always_quota(*args, **kwargs):
        raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

    gb._EXHAUSTED_KEYS.clear()
    with patch.object(gb, "_ask_gemini_once", side_effect=always_quota),          patch.object(gb.settings, "GEMINI_API_KEY", "key-one"),          patch.object(gb.settings, "GEMINI_API_KEYS", "key-two"):
        out = gb.ask_gemini("q", "gemini-2.5-flash")
    assert isinstance(out, dict) and out["ok"] is False
    assert out["answer"], "must carry a user-facing message, not be empty"
    gb._EXHAUSTED_KEYS.clear()


def test_non_quota_error_tries_only_one_key():
    tried = []

    def boom(*args, **kwargs):
        tried.append(1)
        raise TypeError("real bug")

    gb._EXHAUSTED_KEYS.clear()
    with patch.object(gb, "_ask_gemini_once", side_effect=boom), \
         patch.object(gb.settings, "GEMINI_API_KEY", "key-one"), \
         patch.object(gb.settings, "GEMINI_API_KEYS", "key-two"):
        try:
            gb.ask_gemini("q", "m")
            raise AssertionError("a real bug must propagate, not be swallowed")
        except TypeError:
            pass
    assert len(tried) == 1, "a real bug must not burn the spare keys"
    gb._EXHAUSTED_KEYS.clear()


def test_keys_are_deduplicated_and_ordered():
    with patch.object(gb.settings, "GEMINI_API_KEY", "a"), \
         patch.object(gb.settings, "GEMINI_API_KEYS", "b, a , c"):
        assert gb.settings.gemini_keys() == ["a", "b", "c"]
