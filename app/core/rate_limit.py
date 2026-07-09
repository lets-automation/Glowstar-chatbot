"""
rate_limit.py
-------------
Per-user rate limiting, backed by Redis, so one account can't hammer the
LLM provider (burning API cost) or the database. Fixed-window counter:
simple, and plenty for this app's traffic level.

Used as a FastAPI dependency AFTER auth (it needs the authenticated username),
on the expensive endpoints: /chat, /chat/stream, /upload.
"""

from fastapi import Depends, HTTPException, status

from app.config import settings
from app.core.auth import get_current_user
from app.core.redis_client import get_redis

_WINDOW_SECONDS = 60


def enforce_rate_limit(user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency: allow at most RATE_LIMIT_PER_MINUTE requests per user
    per rolling 60s window (fixed-window bucket keyed by the current minute).
    Raises 429 once the limit is hit. Returns `user` unchanged so this can
    replace get_current_user in a route's Depends() without losing the value.
    """
    r = get_redis()
    import time

    bucket = int(time.time()) // _WINDOW_SECONDS
    key = f"ratelimit:{user['username']}:{bucket}"

    count = r.incr(key)
    if count == 1:
        r.expire(key, _WINDOW_SECONDS)

    if count > settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many requests - limit is {settings.RATE_LIMIT_PER_MINUTE} "
                "per minute. Please wait a moment."
            ),
        )
    return user
