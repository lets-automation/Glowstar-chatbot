"""
sessions.py
-----------
Conversation memory, keyed by session_id, backed by Redis.

Lets the chatbot remember recent turns so follow-up questions work
("...and break that down by colour?"). We store only the final
question/answer text per turn (not the internal tool calls).

WHY REDIS (not in-memory): the frontend mints a brand-new session_id for
every new chat thread and threads persist indefinitely in the browser's
localStorage, so an in-memory dict of sessions never stops growing - a slow
memory leak on any long-running server. Redis with a TTL fixes both: memory
is bounded (each session expires after SESSION_TTL_SECONDS of inactivity) and
history survives a backend restart, so a mid-conversation redeploy doesn't
wipe follow-up context.
"""

import json

from app.core.redis_client import get_redis

# How many past turns (Q + A pairs) to remember per session.
MAX_TURNS = 6

# Idle sessions expire after this long (refreshed on every new turn).
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24h - comfortably past a workday

_KEY = "chat:session:{session_id}"


def get_history(session_id: str | None) -> list[dict]:
    """Return the remembered messages for a session (oldest first)."""
    if not session_id:
        return []
    raw = get_redis().get(_KEY.format(session_id=session_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []  # corrupt/unexpected value - fail open to no history, not a crash


def add_turn(session_id: str | None, question: str, answer: str) -> None:
    """Record one completed turn (user question + assistant answer)."""
    if not session_id:
        return
    hist = get_history(session_id)
    hist.append({"role": "user", "content": question})
    hist.append({"role": "assistant", "content": answer})
    hist = hist[-(MAX_TURNS * 2):]  # keep only the most recent turns
    get_redis().set(_KEY.format(session_id=session_id), json.dumps(hist), ex=SESSION_TTL_SECONDS)


def clear_session(session_id: str) -> None:
    """Forget a session's history."""
    get_redis().delete(_KEY.format(session_id=session_id))
