"""
rate_limit.py
-------------
Per-user rate limiting, backed by Redis, so one account can't hammer the
LLM provider (burning API cost) or the database. Fixed-window counter:
simple, and plenty for this app's traffic level.

Used as a FastAPI dependency AFTER auth (it needs the authenticated username),
on the expensive endpoints: /chat, /chat/stream, /upload.
"""

from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.core.auth import get_current_user
from app.core.logging_util import logger
from app.core.redis_client import get_redis

_WINDOW_SECONDS = 60


def _client_ip(request: Request) -> str:
    """Best-effort caller IP for rate-limit bucketing.

    SECURITY: do NOT trust the client-supplied X-Forwarded-For. Our nginx front
    door sets `X-Forwarded-For $proxy_add_x_forwarded_for`, which APPENDS the
    real socket peer to whatever the caller already sent — so the FIRST XFF entry
    is fully attacker-controlled. Keying the limiter on it let a caller send a
    different fake IP per request and mint unlimited buckets, bypassing the limit
    entirely (the only cost/DoS guard when AUTH is off).

    nginx also sets `X-Real-IP $remote_addr` (the true peer, which the client
    cannot forge THROUGH the proxy, and the backend is only reachable via nginx),
    so prefer that. Fall back to the LAST XFF hop (the address nginx appended),
    then the socket peer for direct/local-dev calls.
    """
    real = request.headers.get("x-real-ip")
    if real and real.strip():
        return real.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.strip():
        return xff.rsplit(",", 1)[-1].strip()  # last hop = nginx-appended, not client-set
    return request.client.host if request.client else "unknown"


def make_rate_limiter(scope: str = "", per_minute: int | None = None):
    """
    Build a FastAPI dependency: allow at most `per_minute` requests per CALLER
    per rolling 60s window (fixed-window bucket keyed by the current minute).
    Raises 429 once the limit is hit. Returns `user` unchanged so it can
    replace get_current_user in a route's Depends() without losing the value.

    `scope` gives an endpoint group its OWN counter (empty = the default shared
    bucket): the cheap /threads history calls must not eat into the same 20/min
    budget as the expensive LLM /chat calls. `per_minute` defaults to
    RATE_LIMIT_PER_MINUTE (read at request time, so .env changes apply).

    The caller identity is the authenticated username when AUTH is on; when AUTH
    is off EVERY user is 'guest', so a single username bucket would be one GLOBAL
    limit shared by all staff (one busy user starves everyone). In that case we
    key on client IP instead, giving each caller their own bucket.
    """

    def _enforce(request: Request, user: dict = Depends(get_current_user)) -> dict:
        import time

        limit = per_minute if per_minute is not None else settings.RATE_LIMIT_PER_MINUTE

        caller = user["username"]
        if caller == "guest":
            caller = f"ip:{_client_ip(request)}"
        if scope:
            caller = f"{scope}:{caller}"

        bucket = int(time.time()) // _WINDOW_SECONDS
        key = f"ratelimit:{caller}:{bucket}"

        # FAIL-OPEN on Redis trouble: the limiter is a cost guard, not a
        # correctness gate. If Redis is momentarily unreachable, allow the
        # request instead of raising an unhandled 500 (which, for /threads, would
        # break the fail-soft history contract; the frontend expects a clean
        # answer or a graceful fallback, not a crash). Logged so an outage is
        # still visible.
        try:
            r = get_redis()
            count = r.incr(key)
            if count == 1:
                r.expire(key, _WINDOW_SECONDS)
        except Exception:
            logger.warning("rate limiter unavailable (Redis) - allowing request", exc_info=True)
            return user

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many requests - limit is {limit} "
                    "per minute. Please wait a moment."
                ),
            )
        return user

    return _enforce


# The default limiter used by the expensive endpoints (/chat, /upload, /export).
enforce_rate_limit = make_rate_limiter()

# History (/threads) is cheap-but-chatty: loading the app lists threads, every
# thread click fetches one, every answered turn saves one. Give it its own,
# roomier bucket so browsing history can never starve /chat (and vice versa).
enforce_history_rate_limit = make_rate_limiter("history", per_minute=120)
