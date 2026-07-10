"""
history.py
----------
Server-side store for chat threads, so history is CROSS-DEVICE: any browser
that opens the app sees the same threads (one shared "team" pool - there is
no login in this deployment).

Backed by the `history-db` Postgres container (see docker-compose.yml); the
frontend talks to it through the /threads endpoints in app/api/main.py, and
falls back to per-browser localStorage whenever this store is disabled or
unreachable.

Disabled when HISTORY_DB_URL is empty -> enabled() is False and the endpoints
return 503 (the frontend then quietly stays on localStorage).

Schema note: messages are stored as ONE JSONB document per thread, mirroring
the frontend's "save the whole thread" model (chatStore.js). Timestamps are
epoch milliseconds to round-trip Date.now() values unchanged.
"""

import os
import threading
import time

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    MetaData,
    Table,
    Text,
    and_,
    create_engine,
    delete as sa_delete,
    func,
    insert as sa_insert,
    select as sa_select,
    text as sa_text,
    update as sa_update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from app.config import settings

_metadata = MetaData()

chat_threads = Table(
    "chat_threads",
    _metadata,
    Column("id", Text, primary_key=True),
    # Everything is one shared "team" pool today (no login). A future
    # name-picker or real auth can scope queries by this column without a
    # schema migration.
    Column("user_key", Text, nullable=False, server_default="team"),
    Column("title", Text, nullable=False, server_default="New chat"),
    # JSONB on Postgres; plain JSON elsewhere (lets tests run on sqlite).
    Column("messages", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("created_at", BigInteger, nullable=False),  # epoch ms
    Column("updated_at", BigInteger, nullable=False),  # epoch ms
    # Soft-delete tombstone: NULL = live, epoch-ms = when it was deleted. Because
    # there's no login (one shared team pool), a delete can't be checked for
    # ownership — so instead of destroying a teammate's chat instantly, we mark
    # it and keep it recoverable for a window before purging.
    Column("deleted_at", BigInteger, nullable=True),
)

# Cap the sidebar list so a years-old deployment can't ship an unbounded
# payload to the browser on every page load.
LIST_LIMIT = 200

# Bound total growth so an unauthenticated caller can't fill the history DB
# (disk-fill DoS). Generous — a real team never approaches it; an attacker
# spamming PUTs is stopped. Beyond the cap, NEW threads are refused (existing
# ones still save); the frontend then falls back to localStorage.
MAX_THREADS = int(os.getenv("HISTORY_MAX_THREADS", "10000"))

# How long a soft-deleted thread stays recoverable before it's hard-purged.
SOFT_DELETE_RETENTION_MS = int(os.getenv("HISTORY_SOFT_DELETE_DAYS", "30")) * 24 * 3600 * 1000


class ThreadLimitError(Exception):
    """Raised by upsert_thread when the live-thread cap is reached (see MAX_THREADS)."""


_engine = None
_engine_lock = threading.Lock()


def enabled() -> bool:
    """Is the history store configured at all?"""
    return bool(settings.HISTORY_DB_URL)


def get_engine():
    """Lazily create the engine + table on first use (so the app still starts
    cleanly when Postgres is briefly unavailable or not configured)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                engine = create_engine(
                    settings.HISTORY_DB_URL,
                    # Re-validate pooled connections so a Postgres restart
                    # doesn't surface as a one-off 500 on the next request.
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=5,
                )
                _metadata.create_all(engine)
                _ensure_columns(engine)
                _engine = engine
    return _engine


def _ensure_columns(engine) -> None:
    """Tiny idempotent migration: add columns introduced after a deployment's
    table was first created (create_all only makes MISSING TABLES, not missing
    columns). sqlite test DBs are created fresh from the model, so this is a
    Postgres-only concern."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(sa_text("ALTER TABLE chat_threads ADD COLUMN IF NOT EXISTS deleted_at BIGINT"))


def _now_ms() -> int:
    return int(time.time() * 1000)


def list_threads() -> list[dict]:
    """Sidebar metadata only (no message bodies), newest first. Excludes
    soft-deleted threads. Tiebreak on id so equal updated_at (epoch-ms
    collisions) gives a stable, deterministic order."""
    stmt = (
        sa_select(
            chat_threads.c.id,
            chat_threads.c.title,
            chat_threads.c.created_at,
            chat_threads.c.updated_at,
        )
        .where(chat_threads.c.deleted_at.is_(None))
        .order_by(chat_threads.c.updated_at.desc(), chat_threads.c.id.desc())
        .limit(LIST_LIMIT)
    )
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).all()
    return [
        {"id": r.id, "title": r.title, "createdAt": r.created_at, "updatedAt": r.updated_at}
        for r in rows
    ]


def get_thread(thread_id: str) -> dict | None:
    """One full thread (messages included), or None if it doesn't exist or was
    soft-deleted."""
    stmt = sa_select(chat_threads).where(
        and_(chat_threads.c.id == thread_id, chat_threads.c.deleted_at.is_(None))
    )
    with get_engine().connect() as conn:
        row = conn.execute(stmt).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "messages": row.messages or [],
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def upsert_thread(
    thread_id: str,
    messages: list,
    title: str | None = None,
    created_at: int | None = None,
) -> None:
    """Create or replace a thread's content (the frontend saves whole threads).

    Update-then-insert instead of dialect-specific ON CONFLICT, so the same
    code runs on Postgres and on sqlite (tests). The insert races only with
    another first-save of the SAME brand-new thread id - if that happens the
    IntegrityError fallback turns it into the update it wanted to be.
    """
    now = _now_ms()
    values = {"messages": messages, "updated_at": now}
    if title is not None:
        values["title"] = title

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            sa_update(chat_threads).where(chat_threads.c.id == thread_id).values(**values)
        )
        if result.rowcount:
            return  # existing thread (incl. a soft-deleted one) updated -> no cap check
        # Brand-new thread: enforce the live-thread cap before inserting so an
        # unauthenticated caller can't grow the DB without bound.
        live = conn.execute(
            sa_select(func.count())
            .select_from(chat_threads)
            .where(chat_threads.c.deleted_at.is_(None))
        ).scalar_one()
        if live >= MAX_THREADS:
            raise ThreadLimitError(f"history at capacity ({MAX_THREADS} threads)")
    try:
        with engine.begin() as conn:
            conn.execute(
                sa_insert(chat_threads).values(
                    id=thread_id,
                    title=title or "New chat",
                    messages=messages,
                    created_at=created_at or now,
                    updated_at=now,
                )
            )
    except IntegrityError:
        with engine.begin() as conn:
            conn.execute(
                sa_update(chat_threads).where(chat_threads.c.id == thread_id).values(**values)
            )


def delete_thread(thread_id: str) -> bool:
    """Soft-delete a thread (recoverable — see restore_thread). Returns whether a
    LIVE thread was deleted. Also opportunistically hard-purges tombstones past
    the retention window, so soft-delete can't accumulate rows without bound
    (there's no background scheduler in this app)."""
    now = _now_ms()
    with get_engine().begin() as conn:
        result = conn.execute(
            sa_update(chat_threads)
            .where(and_(chat_threads.c.id == thread_id, chat_threads.c.deleted_at.is_(None)))
            .values(deleted_at=now)
        )
        conn.execute(
            sa_delete(chat_threads).where(
                and_(
                    chat_threads.c.deleted_at.isnot(None),
                    chat_threads.c.deleted_at < now - SOFT_DELETE_RETENTION_MS,
                )
            )
        )
    return bool(result.rowcount)


def restore_thread(thread_id: str) -> bool:
    """Undo a soft-delete (within the retention window). Returns whether a
    soft-deleted thread was restored."""
    with get_engine().begin() as conn:
        result = conn.execute(
            sa_update(chat_threads)
            .where(and_(chat_threads.c.id == thread_id, chat_threads.c.deleted_at.isnot(None)))
            .values(deleted_at=None)
        )
    return bool(result.rowcount)
