"""
redis_client.py
----------------
Shared Redis connection for the whole app: user accounts (auth.py), chat
session history (api/sessions.py), and rate-limit counters (core/rate_limit.py).

Redis is used here for three things, not as a cache:
  1. Persistent user store (username -> password hash) - so login survives a
     backend restart, without adding a login table to the client's ERP database.
  2. Chat session history with a TTL, so old threads expire automatically
     instead of growing forever in memory (see the old app/api/sessions.py).
  3. Per-user rate-limit counters (fixed window).
"""

import redis

from app.config import settings

# decode_responses=True -> get back str, not bytes, everywhere in the app.
_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis() -> redis.Redis:
    """Return the shared Redis client."""
    return _client


def ping() -> bool:
    """True if Redis is reachable right now."""
    try:
        return bool(_client.ping())
    except redis.RedisError:
        return False
