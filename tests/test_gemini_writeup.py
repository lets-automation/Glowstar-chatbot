"""
test_gemini_writeup.py
----------------------
The final write-up call is the one most likely to be refused: every tool round
has already spent from the same per-minute quota (free tier limit: 5 requests
per minute, and one question can use up to MAX_TOOL_ROUNDS of them).

Client-reported failure this locks: "give me full report of MFG - 1" ran all its
queries successfully, then the write-up hit 429 and was swallowed - so the user
waited 33 seconds and got a bare table with no answer. The retry across keys
never happened because the error never reached the failover wrapper.
"""
import pytest

from app.agent import gemini_backend as gb


class _Boom(Exception):
    """Stands in for a provider error; the code classifies by message text."""


@pytest.fixture(autouse=True)
def _clean_key_state(monkeypatch):
    # _EXHAUSTED_KEYS is process-global; leaking it between tests would make
    # later cases silently skip combinations.
    monkeypatch.setattr(gb, "_EXHAUSTED_KEYS", set())
    # Rotation is over (model, key) pairs now, not keys: the free-tier quota is
    # per project per MODEL, so extra keys in one project share a pool and only
    # a different model recovers capacity.
    monkeypatch.setattr(gb, "_attempts", lambda m: [("m", "k1"), ("m", "k2"), ("m", "k3")])


def _client_that(behaviour):
    """Fake genai client whose generate_content defers to `behaviour(key)`."""
    def factory(key=None):
        class _C:
            class models:
                @staticmethod
                def generate_content(**kwargs):
                    return behaviour(key)
        return _C()
    return factory


def _ok(text):
    return type("R", (), {"text": text})()


def test_write_up_rotates_to_the_next_key_on_quota_error(monkeypatch):
    seen = []

    def behaviour(key):
        seen.append(key)
        if key == "k1":
            raise _Boom("429 RESOURCE_EXHAUSTED: quota exceeded")
        return _ok("In July 2026 MFG - 1 finished 305 packets.")

    monkeypatch.setattr(gb, "_client", _client_that(behaviour))
    answer, ok = gb._write_up([], "sys", "m", "k1")

    assert ok is True
    assert "305 packets" in answer
    assert seen == ["k1", "k2"], "should try the used key first, then rotate"


def test_the_exhausted_key_is_remembered(monkeypatch):
    def behaviour(key):
        if key == "k1":
            raise _Boom("429 RESOURCE_EXHAUSTED")
        return _ok("done")

    monkeypatch.setattr(gb, "_client", _client_that(behaviour))
    gb._write_up([], "sys", "m", "k1")
    assert ("m", "k1") in gb._EXHAUSTED_KEYS, "a dead pair must not be retried all turn"


def test_a_real_bug_does_not_burn_every_key(monkeypatch):
    # A schema/programming error will fail identically on every key. Trying all
    # of them wastes the quota that the NEXT question needs.
    seen = []

    def behaviour(key):
        seen.append(key)
        raise _Boom("400 INVALID_ARGUMENT: bad request")

    monkeypatch.setattr(gb, "_client", _client_that(behaviour))
    answer, ok = gb._write_up([], "sys", "m", "k1")

    assert ok is False and answer == ""
    assert seen == ["k1"], "a non-quota error must stop after the first attempt"


def test_all_keys_exhausted_reports_failure_rather_than_raising(monkeypatch):
    monkeypatch.setattr(
        gb, "_client",
        _client_that(lambda key: (_ for _ in ()).throw(_Boom("429 quota"))),
    )
    answer, ok = gb._write_up([], "sys", "m", "k1")
    # Must return, not raise: an escaped exception becomes an HTTP 500 and the
    # user sees a server error instead of the rows we already fetched.
    assert (answer, ok) == ("", False)
