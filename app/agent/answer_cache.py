"""
answer_cache.py
---------------
Pre-warmed answers, so a demo cannot be killed by provider quota.

The free tier allows ~20 requests/DAY and a question costs ~2 of them — about 10
questions a day, while a client meeting is 15-20. That arithmetic is why demos
kept dying mid-meeting.

This cache lets you WARM the expected questions ahead of time (overnight, or with
the previous day's quota). During the meeting those answers are served instantly
from disk: no provider call, no quota, no "the assistant is busy".

Safe here because the DB is a RESTORED BACKUP - it does not change between the
warm run and the demo, so a cached answer is identical to a fresh one. The key
includes the database name, so restoring a newer backup invalidates everything
automatically. Cached entries record when they were produced.

Off unless ANSWER_CACHE_ENABLED=true. Warm with:
    python -m scripts.demo_rehearsal --warm
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

_LOCK = threading.Lock()
_CACHE_DIR = Path(__file__).resolve().parents[2] / "logs" / "answer_cache"


def enabled() -> bool:
    return os.getenv("ANSWER_CACHE_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _normalise(question: str) -> str:
    """Whitespace/case/punctuation-insensitive form, so trivial rewording hits."""
    q = (question or "").strip().lower()
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def key_for(question: str) -> str:
    """Cache key: the question + the exact data/model it was answered from."""
    basis = "|".join([
        _normalise(question),
        (settings.DB_NAME or "").lower(),
        (settings.LLM_PROVIDER or "").lower(),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def _path(question: str) -> Path:
    return _CACHE_DIR / f"{key_for(question)}.json"


def get(question: str) -> dict | None:
    """Return a cached enriched result, or None. Never raises."""
    if not enabled():
        return None
    try:
        p = _path(question)
        if not p.is_file():
            return None
        with _LOCK:
            payload = json.loads(p.read_text(encoding="utf-8"))
        result = payload.get("result")
        if not isinstance(result, dict) or not result.get("answer"):
            return None
        result["_cached_at"] = payload.get("cached_at")
        return result
    except Exception:
        return None  # a broken cache must never break a turn


def put(question: str, result: dict) -> bool:
    """Store a successful result. Returns True if written."""
    if not enabled() or not isinstance(result, dict):
        return False
    # Only cache real, grounded answers — never an error/quota/empty turn.
    if not result.get("ok", False) or not (result.get("answer") or "").strip():
        return False
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "question": question,
            "db": settings.DB_NAME,
            "provider": settings.LLM_PROVIDER,
            "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "result": {k: v for k, v in result.items() if not k.startswith("_")},
        }
        with _LOCK:
            _path(question).write_text(
                json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8"
            )
        return True
    except Exception:
        return False


def stats() -> dict:
    """How many answers are warmed (for the rehearsal summary)."""
    if not _CACHE_DIR.is_dir():
        return {"entries": 0, "dir": str(_CACHE_DIR)}
    return {
        "entries": len(list(_CACHE_DIR.glob("*.json"))),
        "dir": str(_CACHE_DIR),
    }


def clear() -> int:
    """Drop every cached answer (e.g. after restoring a new DB backup)."""
    if not _CACHE_DIR.is_dir():
        return 0
    n = 0
    for f in _CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except Exception:
            pass
    return n
