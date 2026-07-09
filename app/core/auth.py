"""
auth.py
-------
Individual user logins for the API: bcrypt-hashed passwords, JWT access
tokens, users stored in Redis (NOT in the client's ERP database - this is
app-level access control, unrelated to their business data).

There is deliberately NO public self-registration endpoint. Accounts are
created once via `python -m scripts.create_user` (see that file) by whoever
administers the deployment - an open /auth/register would let anyone on the
network create themselves an account.

Usage:
    - POST /auth/login {username, password} -> {access_token}
    - Every protected endpoint depends on `get_current_user`, which reads the
      "Authorization: Bearer <token>" header, verifies the JWT signature and
      expiry, and confirms the user still exists in Redis (so a deleted user's
      old, still-unexpired token stops working immediately).
"""

import logging
import secrets
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger("aastha")

# Fail SAFE, not open: if no JWT_SECRET is configured, generate a random one
# at startup instead of using a fixed/guessable default. This means restarting
# the process invalidates all existing tokens (acceptable in dev) rather than
# ever shipping a predictable secret. Set JWT_SECRET in .env for real use so
# tokens survive restarts and every backend instance/worker agrees on it.
if not settings.JWT_SECRET:
    logger.warning(
        "JWT_SECRET is not set in .env - using a random one-time secret. "
        "All logins will be invalidated on every restart. Set JWT_SECRET "
        "for any real deployment."
    )
    _EFFECTIVE_JWT_SECRET = secrets.token_hex(32)
else:
    _EFFECTIVE_JWT_SECRET = settings.JWT_SECRET

_USER_KEY = "auth:user:{username}"  # Redis hash: password_hash, display_name, created_at


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False  # malformed hash - never crash on a bad stored value


# ---------------------------------------------------------------------------
# User storage (Redis hash per user - persistent, not a cache)
# ---------------------------------------------------------------------------
def create_user(username: str, password: str, display_name: str = "") -> None:
    """Create a new login. Raises ValueError if the username already exists."""
    r = get_redis()
    key = _USER_KEY.format(username=username)
    if r.exists(key):
        raise ValueError(f"User '{username}' already exists.")
    r.hset(
        key,
        mapping={
            "password_hash": hash_password(password),
            "display_name": display_name or username,
            "created_at": str(int(time.time())),
        },
    )


def set_password(username: str, new_password: str) -> None:
    """Reset an existing user's password."""
    r = get_redis()
    key = _USER_KEY.format(username=username)
    if not r.exists(key):
        raise ValueError(f"User '{username}' does not exist.")
    r.hset(key, "password_hash", hash_password(new_password))


def get_user(username: str) -> dict | None:
    r = get_redis()
    data = r.hgetall(_USER_KEY.format(username=username))
    return data or None


def delete_user(username: str) -> None:
    get_redis().delete(_USER_KEY.format(username=username))


def verify_user_credentials(username: str, password: str) -> dict | None:
    """Return the user dict if username+password are correct, else None."""
    user = get_user(username)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return None
    return user


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------
def create_access_token(username: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + settings.JWT_EXPIRE_MINUTES * 60,
    }
    return jwt.encode(payload, _EFFECTIVE_JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _EFFECTIVE_JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependency - protects an endpoint, injects the current user
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)  # so we control the 401 response ourselves


# Identity used for every request when AUTH_ENABLED is off (no login). Rate
# limiting still keys on this, so cost protection stays even without accounts.
GUEST_USER = {"username": "guest", "display_name": "Guest"}


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency. When AUTH_ENABLED is off (default), every caller is an
    anonymous guest - no login required. When on, it requires a valid
    "Authorization: Bearer <token>" header and returns the user, else 401.
    """
    if not settings.AUTH_ENABLED:
        return GUEST_USER

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not creds:
        raise unauthorized

    payload = decode_access_token(creds.credentials)
    if not payload:
        raise unauthorized

    username = payload.get("sub")
    user = get_user(username) if username else None
    if not user:
        # Token is well-formed but the account no longer exists (deleted) -
        # reject immediately rather than trusting a stale token.
        raise unauthorized

    return {"username": username, "display_name": user.get("display_name", username)}
