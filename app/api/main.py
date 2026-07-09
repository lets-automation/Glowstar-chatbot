"""
main.py (API layer)
-------------------
Exposes the agent over a REST API so the client's React app can call it.

Endpoints:
  GET  /health  -> simple uptime check (works even with no API key)
  POST /chat    -> ask a question, get an answer

The API is a THIN wrapper: it just calls app.agent.agent.ask().
All the real logic (SQL safety, querying, Claude) lives in the agent.

Run it with:
  & C:\\Glowstar_chatbot\\venv\\Scripts\\python.exe -m uvicorn app.api.main:app --reload
Then open the auto-docs at http://127.0.0.1:8000/docs
"""

import os
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Path, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from app.artifacts.charts import to_chart
from app.artifacts.excel import to_excel
from app.artifacts.pdf import to_pdf
from app.config import settings
from app.core import auth, history
from app.core.logging_util import logger
from app.core.rate_limit import enforce_history_rate_limit, enforce_rate_limit
from app.database.runner import run_select

app = FastAPI(
    title="Aastha ERP AI Chatbot API",
    description="Ask questions about the Aastha diamond-manufacturing ERP.",
    version="0.1.0",
    # Hide the interactive API surface unless explicitly enabled (see config).
    docs_url="/docs" if settings.API_DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.API_DOCS_ENABLED else None,
)

# --- CORS ---
# CORS only matters for cross-origin callers (local dev: Vite :5173 -> API
# :8000). The Docker deployment is same-origin via nginx, so CORS is irrelevant
# there. Set CORS_ORIGINS to the exact frontend/CRM origin(s) for a deployment.
_raw_cors = settings.CORS_ORIGINS.strip()
_wildcard = _raw_cors == "*"
_cors_origins = (
    ["*"] if _wildcard
    else [o.strip() for o in _raw_cors.split(",") if o.strip()]
)
# SECURITY: never pair a wildcard origin with credentials. Starlette would then
# REFLECT the caller's Origin and send Access-Control-Allow-Credentials: true,
# letting ANY website make credentialed cross-origin reads of this (auth-
# optional) API - including /export, which runs arbitrary read-only SQL. Allow
# credentials ONLY for an explicit origin allowlist.
_allow_credentials = not _wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
if _wildcard:
    logger.warning(
        "SECURITY: CORS_ORIGINS='*' lets ANY website call this API cross-origin. "
        "Set CORS_ORIGINS to your exact frontend/CRM origin(s) for deployment."
    )


# --- Request / response shapes (validated by Pydantic) ---
class ChatRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, max_length=1000, description="The user's question."
    )
    session_id: str | None = Field(
        None, description="Optional id to keep conversation memory across turns."
    )
    # Files already uploaded via /upload; referenced by id so the agent can read
    # and analyse them. Just references (no bytes) -> the request stays small.
    attachments: list[dict] = Field(
        default_factory=list,
        description="Uploaded files to analyse: [{file_id, filename}].",
    )


class ChatResponse(BaseModel):
    answer: str
    ok: bool = True
    suggestions: list[str] = []
    citation: str = ""
    export_query: str | None = None
    sql_used: list[str]
    rows_returned: int
    # Inline visuals (HTML/SVG fragments) the model drew via the show_widget tool.
    widgets: list[dict] = []
    # Exact rows behind the answer, so the UI can export a stable snapshot.
    data_columns: list[str] = []
    data_rows: list[dict] = []


class ExportRowsRequest(BaseModel):
    """Export the EXACT rows the chat already showed (no DB re-run)."""
    # Cap the row count so a client can't POST an arbitrarily huge array and
    # force a giant in-memory file build (the SQL path is capped; this wasn't).
    columns: list[str] = []
    rows: list[dict] = Field(..., max_length=5000)
    format: str = Field("excel", pattern="^(excel|pdf|chart)$")
    title: str = "Report"
    x_col: str | None = None
    y_col: str | None = None


class ThreadUpsertRequest(BaseModel):
    """Whole-thread save from the frontend (it persists complete threads,
    mirroring the old localStorage model - see frontend/src/lib/chatStore.js)."""
    # None = keep the existing title (the mid-turn autosave doesn't know it).
    title: str | None = Field(None, max_length=300)
    messages: list[dict] = Field(..., max_length=1000)
    # Frontend Date.now() of the thread's creation; only used on first insert.
    createdAt: int | None = Field(None, ge=0)


# Thread ids are client-generated ("t-<ms>-<rand>"); constrain the charset so
# the path segment can't smuggle anything weird into logs or queries.
_THREAD_ID = Path(..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")

# One thread's serialized messages may hold big export snapshots; cap the
# stored size so a single PUT can't bloat the history DB unbounded.
_THREAD_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    display_name: str
    expires_in_minutes: int


class FeedbackRequest(BaseModel):
    # Cap lengths so an unauthenticated caller can't POST huge bodies that grow
    # the feedback log unbounded.
    question: str = Field("", max_length=2000)
    answer: str = Field("", max_length=20000)
    helpful: bool
    session_id: str | None = Field(None, max_length=200)


class ExportRequest(BaseModel):
    query: str = Field(..., description="A read-only SELECT to export.")
    format: str = Field("excel", pattern="^(excel|pdf|chart)$")
    title: str = "Report"
    x_col: str | None = None  # chart only
    y_col: str | None = None  # chart only


# The API key that MUST be present for the currently-selected provider. Used to
# return a clean 503 instead of a raw 500 when the active provider isn't
# configured (e.g. LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is blank).
def _active_provider_key_missing() -> str | None:
    provider = settings.LLM_PROVIDER.lower()
    if provider in ("anthropic", "claude"):
        return "ANTHROPIC_API_KEY" if not settings.ANTHROPIC_API_KEY else None
    if provider == "gemini":
        return "GEMINI_API_KEY" if not settings.GEMINI_API_KEY else None
    return "GROQ_API_KEY" if not settings.GROQ_API_KEY else None


def _load_history(session_id: str | None) -> list[dict]:
    """Follow-up context for a chat turn.

    Prefer the fast Redis session (recent turns, refreshed each turn, 24h TTL).
    If it's empty — the thread was reopened after the session expired/evicted, or
    opened on another day — rebuild the context from the DURABLE thread store so
    the bot doesn't 'forget' a conversation that's still on screen, and warm
    Redis with it so the rest of the session stays fast and keeps accumulating.

    Without this, the chat thread pool (Postgres, durable + cross-device) and the
    LLM memory (Redis, 24h TTL) silently diverge: the user sees a full history
    the model has no recollection of.
    """
    from app.api import sessions

    hist = sessions.get_history(session_id)
    if hist or not session_id or not history.enabled():
        return hist
    try:
        thread = history.get_thread(session_id)
    except Exception:
        logger.exception("history reconstruct failed for session %s", session_id)
        return hist
    if not thread:
        return hist
    rebuilt = sessions.history_from_messages(thread.get("messages") or [])
    if rebuilt:
        sessions.replace_history(session_id, rebuilt)  # warm Redis for the rest of the session
    return rebuilt


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _sweep_old(dir_path: str, max_age_seconds: float) -> None:
    """Best-effort deletion of files older than max_age in a directory, so
    transient dirs (uploads) don't grow without bound. Never raises."""
    import time
    try:
        now = time.time()
        for name in os.listdir(dir_path):
            p = os.path.join(dir_path, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > max_age_seconds:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _download(path: str, media_type: str, download_name: str) -> FileResponse:
    """Serve a generated export file, then delete it once the response is sent.

    Each export is written to a UNIQUE filename (uuid) and removed afterwards, so
    concurrent exports can never collide on a shared name (which previously let
    one request serve another's or a half-written file) and the outputs/ dir does
    not grow without bound.
    """
    return FileResponse(
        path,
        media_type=media_type,
        filename=download_name,
        background=BackgroundTask(_safe_remove, path),
    )


_EXCEL_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- Endpoints ---
@app.get("/health")
def health():
    """Simple check that the API is up. Never touches Claude or the DB. No
    auth required - used for container/load-balancer liveness checks."""
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    Exchange a username + password for a JWT access token. There is no public
    registration endpoint - accounts are created via `scripts/manage_users.py`
    by whoever administers the deployment.
    """
    user = auth.verify_user_credentials(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = auth.create_access_token(request.username)
    return LoginResponse(
        access_token=token,
        display_name=user.get("display_name", request.username),
        expires_in_minutes=settings.JWT_EXPIRE_MINUTES,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Ask the agent a question and return its answer. Requires a valid login
    (Authorization: Bearer <token>) and is rate-limited per user.

    - 503 if the Anthropic API key isn't configured yet.
    - 500 if something unexpected goes wrong while answering.
    """
    # Guard: don't even try to call the LLM without the active provider's key.
    missing = _active_provider_key_missing()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"AI is not configured: {missing} is missing in .env.",
        )

    # Import here so the app still starts/imports fine when the key is absent.
    from app.agent.agent import ask
    from app.api import sessions

    convo_history = _load_history(request.session_id)
    try:
        result = ask(request.question, history=convo_history, attachments=request.attachments)
    except Exception as exc:
        # Log the real error server-side, but never return raw DB/driver text to
        # the client (it can leak table/server names). Give a friendly message.
        logger.exception("chat failed")
        raise HTTPException(
            status_code=500,
            detail="Sorry, something went wrong answering that. Please try again.",
        )

    # Remember this turn for follow-up questions.
    sessions.add_turn(request.session_id, request.question, result["answer"])

    return ChatResponse(
        answer=result["answer"],
        ok=result.get("ok", True),
        suggestions=result.get("suggestions", []),
        citation=result.get("citation", ""),
        export_query=result.get("export_query"),
        sql_used=result["sql_used"],
        rows_returned=result["rows_returned"],
        widgets=result.get("widgets", []),
        data_columns=result.get("data_columns", []),
        data_rows=result.get("data_rows", []),
    )


@app.post("/chat/stream")
def chat_stream(request: ChatRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Same as /chat but streams live status events (Server-Sent Events) so the UI
    can show 'Querying the database…' etc. as the agent works, then the final
    answer. Each line is: data: {json}\\n\\n

    Requires a valid login and is rate-limited per user (same as /chat).
    """
    import json
    import queue
    import threading

    from app.agent.agent import ask
    from app.api import sessions

    events: "queue.Queue" = queue.Queue()
    convo_history = _load_history(request.session_id)

    def on_event(msg: str):
        events.put({"type": "status", "message": msg})

    def run():
        try:
            result = ask(
                request.question,
                history=convo_history,
                on_event=on_event,
                attachments=request.attachments,
            )
            sessions.add_turn(request.session_id, request.question, result["answer"])
            events.put({"type": "result", "data": result})
        except Exception:
            # Never stream raw DB/driver error text to the browser; log it and
            # send a friendly message instead.
            logger.exception("chat/stream failed")
            events.put({
                "type": "error",
                "message": "Sorry, something went wrong answering that. Please try again.",
            })
        finally:
            events.put(None)  # sentinel: stream finished

    threading.Thread(target=run, daemon=True).start()

    def event_stream():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/export_rows")
def export_rows(req: ExportRowsRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Build a downloadable file from rows ALREADY returned to the chat — no query
    re-run. This makes an export a stable snapshot of exactly what was shown
    (fixes 'the Excel changes every download' from re-running unordered SQL).

    Requires a valid login and is rate-limited per user.
    """
    if not req.rows:
        raise HTTPException(status_code=400, detail="No data to export.")
    columns = req.columns or list(req.rows[0].keys())
    uid = uuid.uuid4().hex

    # Wrap file generation so dirty/unusual data (control chars, non-Latin text,
    # very wide tables) returns a clean 422 instead of an unhandled 500.
    try:
        if req.format == "pdf":
            path = to_pdf(columns, req.rows, f"export-{uid}.pdf", title=req.title)
            return _download(path, "application/pdf", "export.pdf")

        if req.format == "chart":
            x_col = req.x_col or columns[0]
            y_col = req.y_col or columns[-1]
            path = to_chart(req.rows, x_col, y_col, f"export-{uid}.png", title=req.title)
            return _download(path, "image/png", "export.png")

        path = to_excel(columns, req.rows, f"export-{uid}.xlsx")
        return _download(path, _EXCEL_MEDIA, "export.xlsx")
    except Exception:
        logger.exception("export_rows failed (format=%s)", req.format)
        raise HTTPException(status_code=422, detail=f"Could not build the {req.format} file from this data.")


@app.post("/upload")
async def upload(file: UploadFile = File(...), user: dict = Depends(enforce_rate_limit)):
    """
    Accept an image or file attachment from the chat composer and store it.

    Saves to outputs/uploads/<file_id><ext> and returns a reference the client
    keeps on the message. The client then sends that {file_id, filename} on the
    next /chat request; the agent reads and analyses the file content there
    (see app/agent/attachments.py: Excel/CSV/PDF text + image vision).

    Requires a valid login and is rate-limited per user.
    """
    # Guardrails: enforce the size cap WHILE streaming (don't buffer the whole
    # file into memory first - that let a huge upload OOM the worker), restrict
    # to expected attachment types, and keep only a sanitized extension.
    MAX_BYTES = 15 * 1024 * 1024  # 15 MB
    ALLOWED_EXT = {
        ".xlsx", ".xls", ".csv", ".pdf",
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt",
    }
    ext = os.path.splitext(file.filename or "")[1].lower()[:10]
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail="Unsupported file type.")

    upload_dir = os.path.join("outputs", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    _sweep_old(upload_dir, 24 * 3600)  # bound disk growth: drop uploads >24h old
    file_id = uuid.uuid4().hex
    path = os.path.join(upload_dir, f"{file_id}{ext}")

    total = 0
    try:
        with open(path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB at a time
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(status_code=413, detail="File too large (max 15 MB).")
                fh.write(chunk)
    except HTTPException:
        _safe_remove(path)  # remove the partial file
        raise
    except Exception:
        _safe_remove(path)
        logger.exception("upload failed")
        raise HTTPException(status_code=400, detail="Could not save the uploaded file.")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": total,
    }


@app.post("/feedback")
def feedback(req: FeedbackRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Store a thumbs up/down on an answer (for improving prompts/tools).
    Appended to logs/feedback.jsonl. Rate-limited (was previously unthrottled).
    """
    import json
    from datetime import datetime

    os.makedirs("logs", exist_ok=True)
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "helpful": req.helpful,
        "question": req.question,
        "answer": req.answer,
        "session_id": req.session_id,
    }
    with open("logs/feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "recorded"}


# --- Chat history (cross-device threads; the history-db Postgres container) ---
# The frontend treats ANY failure here as "use per-browser localStorage
# instead", so these endpoints fail soft: 503 when the store is off/unreachable.

def _history_ready():
    if not history.enabled():
        raise HTTPException(
            status_code=503,
            detail="Chat history storage is not configured (HISTORY_DB_URL).",
        )


def _history_unavailable(action: str) -> HTTPException:
    logger.exception("history %s failed", action)
    return HTTPException(status_code=503, detail="History database is unavailable.")


@app.get("/threads")
def list_threads(user: dict = Depends(enforce_history_rate_limit)):
    """Sidebar list: thread metadata only (no message bodies), newest first."""
    _history_ready()
    try:
        return {"threads": history.list_threads()}
    except Exception:
        raise _history_unavailable("list")


@app.get("/threads/{thread_id}")
def get_thread(
    thread_id: str = _THREAD_ID, user: dict = Depends(enforce_history_rate_limit)
):
    """One full thread, messages included (lazy-loaded when a chat is opened)."""
    _history_ready()
    try:
        thread = history.get_thread(thread_id)
    except Exception:
        raise _history_unavailable("get")
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return thread


@app.put("/threads/{thread_id}")
def put_thread(
    req: ThreadUpsertRequest,
    thread_id: str = _THREAD_ID,
    user: dict = Depends(enforce_history_rate_limit),
):
    """Create or replace a thread (the frontend saves whole threads, debounced)."""
    _history_ready()
    import json

    # Measure the ACTUAL stored size in BYTES, not Unicode characters: Gujarati/
    # Hindi/emoji content is multi-byte in UTF-8, so a character count let a
    # thread store several times the intended cap. Include the title too.
    payload = json.dumps(
        {"title": req.title or "", "messages": req.messages}, ensure_ascii=False
    )
    if len(payload.encode("utf-8")) > _THREAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Thread too large to store - export snapshots exceed the cap.",
        )
    try:
        history.upsert_thread(
            thread_id, req.messages, title=req.title, created_at=req.createdAt
        )
    except Exception:
        raise _history_unavailable("save")
    return {"status": "saved"}


@app.delete("/threads/{thread_id}")
def remove_thread(
    thread_id: str = _THREAD_ID, user: dict = Depends(enforce_history_rate_limit)
):
    """Delete a thread everywhere (all devices see the same shared history)."""
    _history_ready()
    try:
        existed = history.delete_thread(thread_id)
    except Exception:
        raise _history_unavailable("delete")
    # The thread id is ALSO the /chat session id: drop its Redis follow-up memory
    # so a deleted chat leaves nothing behind (and a later thread can't inherit
    # stale context). Best-effort — a Redis hiccup must not fail the delete.
    try:
        from app.api import sessions
        sessions.clear_session(thread_id)
    except Exception:
        logger.warning("could not clear session memory for %s", thread_id, exc_info=True)
    return {"deleted": existed}


@app.post("/export")
def export(req: ExportRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Turn a read-only SELECT into a downloadable file (Excel/PDF/chart).
    No AI key needed - this runs the query directly through the safe runner.
    Returns the file itself for the browser to download. Requires a valid login
    and is rate-limited per user (it runs arbitrary read-only SQL).
    """
    result = run_select(req.query)
    if not result["ok"]:
        # Log the real reason server-side, but do NOT return raw DB/driver error
        # text to the caller (it leaks table/server/schema names on an open API).
        logger.warning("export query rejected/failed: %s", result["error"])
        raise HTTPException(
            status_code=400,
            detail="Query rejected or failed. It must be a valid read-only SELECT.",
        )

    columns, rows = result["columns"], result["rows"]
    if not rows:
        raise HTTPException(status_code=400, detail="Query returned no rows.")

    uid = uuid.uuid4().hex
    try:
        if req.format == "pdf":
            path = to_pdf(columns, rows, f"export-{uid}.pdf", title=req.title)
            return _download(path, "application/pdf", "export.pdf")

        if req.format == "chart":
            x_col = req.x_col or columns[0]
            y_col = req.y_col or columns[-1]
            path = to_chart(rows, x_col, y_col, f"export-{uid}.png", title=req.title)
            return _download(path, "image/png", "export.png")

        # default: excel
        path = to_excel(columns, rows, f"export-{uid}.xlsx")
        return _download(path, _EXCEL_MEDIA, "export.xlsx")
    except Exception:
        logger.exception("export failed (format=%s)", req.format)
        raise HTTPException(status_code=422, detail=f"Could not build the {req.format} file from this data.")
