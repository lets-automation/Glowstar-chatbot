"""
test_suggest.py
---------------
Entity autocomplete (/suggest): real department/kapan/employee names matching a
typed word, so the user picks a real value instead of misspelling it. This is the
deterministic (no-AI) version of the "fancy -> Fency" fix, so it must:
  - stay injection-safe (the search text is user-supplied),
  - resolve a misspelling phonetically (fancy -> Fency),
  - ignore too-short queries.
Hits the live DB via the safe runner (like test_export).
"""
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _names(resp):
    return [s["name"] for s in resp.json().get("suggestions", [])]


def test_suggest_short_query_is_empty():
    r = client.get("/suggest", params={"q": "a"})
    assert r.status_code == 200
    assert r.json()["suggestions"] == []  # < 2 chars -> no noise


def test_suggest_injection_is_neutralized():
    # A SQL-injection attempt must return a normal 200 with no rows, never error
    # or execute — the text is sanitized and used only as a LIKE literal.
    r = client.get("/suggest", params={"q": "'; DROP TABLE x --"})
    assert r.status_code == 200
    assert r.json()["suggestions"] == []


def test_suggest_phonetic_resolves_misspelling():
    # The client's real case: typing "fanc" must surface the real dept "Fency"
    # (same SOUNDEX), even though it is NOT a substring match.
    r = client.get("/suggest", params={"q": "fanc"})
    assert r.status_code == 200
    assert "Fency" in _names(r)


def test_suggest_exact_substring_match():
    r = client.get("/suggest", params={"q": "fenc"})
    assert r.status_code == 200
    assert "Fency" in _names(r)


def test_suggest_soundex_does_not_match_tiny_codes():
    # Regression: SOUNDEX('giv') == SOUNDEX of the 2-letter kapan codes GB/GF/GP/GV,
    # so a typed word used to surface meaningless short codes. The phonetic arm is
    # now length-guarded (real word-length names only) — no 1-3 char code may leak.
    names = _names(client.get("/suggest", params={"q": "giv"}))
    assert all(len(n) >= 4 for n in names), f"tiny-code noise leaked: {names}"
    # And the useful phonetic rescue must still fire for a real misspelt word.
    assert "Fency" in _names(client.get("/suggest", params={"q": "fanc"}))
