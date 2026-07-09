"""
test_rate_limit.py
------------------
The make_rate_limiter refactor + the two hardening fixes:
  - _client_ip must NOT trust the spoofable first X-Forwarded-For hop.
  - the limiter must FAIL OPEN (allow) when Redis is unreachable, not 500.
  - normal counting still returns 429 past the limit.

Pure unit tests: the limiter dependency is called directly with a fake Request
and a fake Redis, so no server/Redis is needed.

Run: python -m pytest tests/test_rate_limit.py -q
"""

import pytest
from fastapi import HTTPException

from app.core import rate_limit


class FakeReq:
    def __init__(self, headers=None, peer="10.0.0.9"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": peer})()


class FakeRedis:
    """Counts like the real fixed-window bucket; optionally raises to simulate an outage."""
    def __init__(self, raises=False):
        self.raises = raises
        self.counts = {}

    def incr(self, key):
        if self.raises:
            raise ConnectionError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, ttl):
        if self.raises:
            raise ConnectionError("redis down")


GUEST = {"username": "guest"}


# --- _client_ip anti-spoof (the X-Forwarded-For rate-limit-bypass fix) ---

def test_client_ip_prefers_real_ip_over_spoofed_xff():
    # nginx sets X-Real-IP to the true peer; the first XFF hop is attacker-set.
    req = FakeReq({"x-real-ip": "203.0.113.5", "x-forwarded-for": "6.6.6.6, 203.0.113.5"})
    assert rate_limit._client_ip(req) == "203.0.113.5"


def test_client_ip_uses_last_xff_hop_when_no_real_ip():
    req = FakeReq({"x-forwarded-for": "6.6.6.6, 203.0.113.5"})
    assert rate_limit._client_ip(req) == "203.0.113.5"  # nginx-appended, not client-set


def test_client_ip_rotating_spoof_yields_one_key():
    keys = {
        rate_limit._client_ip(
            FakeReq({"x-real-ip": "203.0.113.5", "x-forwarded-for": f"{i}.{i}.{i}.{i}, 203.0.113.5"})
        )
        for i in range(10)
    }
    assert keys == {"203.0.113.5"}  # spoof no longer mints distinct buckets


# --- fail-open on Redis outage ---

def test_limiter_fails_open_when_redis_down(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: FakeRedis(raises=True))
    limiter = rate_limit.make_rate_limiter("history", per_minute=5)
    # Must ALLOW (return the user), not raise a 500, when Redis is unreachable.
    assert limiter(FakeReq(), user=GUEST) is GUEST


# --- normal counting still enforces the limit ---

def test_limiter_enforces_limit(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: fake)
    limiter = rate_limit.make_rate_limiter("history", per_minute=3)
    req = FakeReq({"x-real-ip": "1.2.3.4"})
    for _ in range(3):
        assert limiter(req, user=GUEST) is GUEST  # first 3 allowed
    with pytest.raises(HTTPException) as exc:
        limiter(req, user=GUEST)  # 4th over the limit
    assert exc.value.status_code == 429


def test_scope_separates_buckets(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: fake)
    req = FakeReq({"x-real-ip": "1.2.3.4"})
    rate_limit.make_rate_limiter("history", per_minute=1)(req, user=GUEST)
    # A different scope for the SAME caller is a different bucket -> still allowed.
    assert rate_limit.make_rate_limiter("", per_minute=1)(req, user=GUEST) is GUEST
    assert any(k.startswith("ratelimit:history:") for k in fake.counts)
    assert any(":history:" not in k for k in fake.counts)
