"""
test_gemini_model_rotation.py
-----------------------------
The free tier's escape hatch, and why it is MODELS not keys.

The 429 names its own quota id:
    GenerateRequestsPerMinutePerProjectPerModel-FreeTier   (limit 5/min, 20/day)

Two things follow. It is per MODEL, so every model carries its own budget. And
it is per PROJECT, so extra API keys in the same project share ONE pool - which
is why four keys never helped: rotating them stayed inside the same exhausted
bucket.

Measured proof: gemini-2.5-flash answered in 1.9s while gemini-3-flash was still
refusing with 429.

One report question costs ~6 model calls against a 5/min limit, so a single
model cannot finish one. Rotating models is what makes the free tier usable.
"""
from app.agent import gemini_backend as gb
from app.config import settings


def test_the_configured_model_is_tried_first(monkeypatch):
    monkeypatch.setattr(gb, "_EXHAUSTED_KEYS", set())
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "gemini_keys", lambda: ["k1", "k2"])
    first_model = gb._attempts("gemini-2.5-flash")[0][0]
    assert first_model == "gemini-2.5-flash"


def test_every_model_is_paired_with_every_key(monkeypatch):
    monkeypatch.setattr(gb, "_EXHAUSTED_KEYS", set())
    monkeypatch.setattr(settings, "gemini_keys", lambda: ["k1", "k2"])
    monkeypatch.setattr(settings, "gemini_model_chain", lambda: ["mA", "mB"])
    assert gb._attempts("mA") == [("mA", "k1"), ("mA", "k2"),
                                  ("mB", "k1"), ("mB", "k2")]


def test_an_exhausted_pair_is_skipped_but_its_model_survives(monkeypatch):
    """
    Exhaustion is per (model, key). Tracking KEYS alone marked a key dead for
    every model the moment ONE model's bucket ran out - throwing away capacity
    that was still there.
    """
    monkeypatch.setattr(settings, "gemini_keys", lambda: ["k1", "k2"])
    monkeypatch.setattr(settings, "gemini_model_chain", lambda: ["mA", "mB"])
    monkeypatch.setattr(gb, "_EXHAUSTED_KEYS", {("mA", "k1")})

    out = gb._attempts("mA")
    assert ("mA", "k1") not in out
    assert ("mA", "k2") in out, "the key died for ONE model, not for all of them"
    assert ("mB", "k1") in out


def test_all_pairs_spent_still_returns_something_to_try(monkeypatch):
    # The per-MINUTE bucket refills, so "everything is exhausted" is often stale
    # by the next question. Returning nothing would refuse a question the API
    # would now happily answer.
    monkeypatch.setattr(settings, "gemini_keys", lambda: ["k1"])
    monkeypatch.setattr(settings, "gemini_model_chain", lambda: ["mA"])
    monkeypatch.setattr(gb, "_EXHAUSTED_KEYS", {("mA", "k1")})
    assert gb._attempts("mA") == [("mA", "k1")]


def test_the_chain_has_no_duplicates_and_leads_with_the_configured_model():
    monkeypatch_free = settings.gemini_model_chain()
    assert len(monkeypatch_free) == len(set(monkeypatch_free)), "a duplicate wastes an attempt"
    assert monkeypatch_free[0] == settings.GEMINI_MODEL


def test_enough_models_to_finish_one_report():
    """
    A report question costs ~6 calls; the free limit is 5/min per model. With
    fewer than two models a single question cannot complete, which is exactly
    the failure the client hit.
    """
    assert len(settings.gemini_model_chain()) >= 2
