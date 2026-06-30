"""
sessions.py
-----------
Simple in-memory conversation memory, keyed by session_id.

Lets the chatbot remember recent turns so follow-up questions work
("...and break that down by colour?"). We store only the final
question/answer text per turn (not the internal tool calls).

PRODUCTION NOTE: this is in-memory, so history is lost on restart and is
NOT shared across multiple server workers/processes. For a multi-worker
production deployment, back this with Redis (same get/add interface).
"""

from collections import deque

# How many past turns (Q + A pairs) to remember per session.
MAX_TURNS = 6

# session_id -> deque of {"role": "user"|"assistant", "content": str}
_SESSIONS: dict[str, deque] = {}


def get_history(session_id: str | None) -> list[dict]:
    """Return the remembered messages for a session (oldest first)."""
    if not session_id:
        return []
    return list(_SESSIONS.get(session_id, []))


def add_turn(session_id: str | None, question: str, answer: str) -> None:
    """Record one completed turn (user question + assistant answer)."""
    if not session_id:
        return
    hist = _SESSIONS.setdefault(session_id, deque(maxlen=MAX_TURNS * 2))
    hist.append({"role": "user", "content": question})
    hist.append({"role": "assistant", "content": answer})


def clear_session(session_id: str) -> None:
    """Forget a session's history."""
    _SESSIONS.pop(session_id, None)
