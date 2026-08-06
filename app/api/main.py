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
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Path, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from app.agent import access_guard, date_gate, smalltalk_gate
from app.artifacts.charts import to_chart
from app.artifacts.excel import to_excel, to_excel_sections
from app.artifacts.pdf import to_pdf
from app.config import settings
from app.core import auth, history
from app.core.logging_util import log_startup, logger
from app.core.rate_limit import enforce_history_rate_limit, enforce_rate_limit
from app.database.runner import run_select

# --- AgentCost (optional cost tracking; agentcost.tech) ---
# Must run BEFORE any LLM client is CREATED: the SDK monkey-patches the
# anthropic / openai / google-genai client libraries so every call reports model,
# token counts, cost and latency (metadata only — no prompt or answer content) to
# the AgentCost dashboard. Best-effort by design: this is a young third-party
# SDK, so a failure here logs a warning and the chatbot runs WITHOUT tracking —
# it must never take the API down.
#
# WHAT IS AND IS NOT COVERED (verify against the startup banner, which names the
# interceptors that actually loaded — that banner is what exposed the bug below):
#   anthropic  yes    gemini  yes (needs SDK >= 0.1.4)
#   openai-compatible (ollama / lmstudio / cerebras / nvidia)  yes
#   groq       NO     the native groq SDK is not patched. See _client() in
#                     groq_backend.py — LLM_PROVIDER=groq is invisible here.
#
# 2026-08-06 BUG: tracking had never worked. The pin was agentcost==0.1.3, which
# shipped only openai_interceptor.py and anthropic_interceptor.py — no Gemini
# interceptor existed in that release — while LLM_PROVIDER=gemini sent every call
# through google.genai. The comment here claimed gemini was covered; the startup
# banner disagreed ("Tracking initialized (LangChain, OpenAI, Anthropic)") and the
# banner was right. Fixed by requirements.txt agentcost==0.1.7.

# Rates in dollars per 1K tokens for every model this app can select. These go
# in via custom_pricing, which the SDK consults FIRST — ahead of its own model
# table. That ordering is the whole point: the SDK's bundled table knows neither
# claude-sonnet-4-6 nor gemini-3-flash-preview, and its 2000-model table is
# fetched from the backend in a BACKGROUND thread, so calls made before that
# fetch lands are silently costed at $0.00. With a free-tier Gemini key capped
# near 20 requests/day, those early calls are most of the traffic — which is why
# every Gemini turn was showing up on the dashboard priced at zero. Listing the
# rates here removes the race entirely.
# Source: AgentCost's own /v1/pricing table, read 2026-08-04. Re-check when
# switching models — a model missing here is recorded at $0.00, not refused.
_AGENTCOST_PRICING = {
    # Gemini — the free tier bills $0; priced here at list rate so the dashboard
    # shows what the traffic WOULD cost on a paid key.
    #
    # EVERY model in the rotation must be listed. gemini_backend rotates through
    # settings.gemini_model_chain() (GEMINI_MODEL + GEMINI_FALLBACK_MODELS) when a
    # per-model quota runs out, so a turn can be answered by any of them — and a
    # model missing here records at $0.00 rather than being refused, which reads
    # on the dashboard as "that traffic was free" instead of "we forgot to price
    # it". Keep this in step with GEMINI_FALLBACK_MODELS in .env.
    "gemini-3-flash-preview": {"input": 0.0005, "output": 0.003},
    "gemini-2.5-flash": {"input": 0.0003, "output": 0.0025},
    "gemini-3.1-flash-lite": {"input": 0.0001, "output": 0.0004},
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    # Anthropic (ANTHROPIC_MODEL)
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    # Groq (GROQ_MODEL) — listed for when the native SDK does get patched.
    "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.00018, "output": 0.00059},
    # Cerebras / NVIDIA (OpenAI-compatible, tracked via the openai lib)
    "gpt-oss-120b": {"input": 0.00022, "output": 0.00059},
    "openai/gpt-oss-20b": {"input": 0.00005, "output": 0.0002},
    "kimi-k2.6": {"input": 0.00095, "output": 0.004},
    # LM Studio / Ollama run locally: no per-token cost. Listed so a local run
    # records $0.00 DELIBERATELY rather than by falling through as unpriced.
    "google/gemma-4-12b-qat": {"input": 0.0, "output": 0.0},
    "qwen/qwen3.6-35b-a3b": {"input": 0.0, "output": 0.0},
    "qwen2.5-7b-instruct": {"input": 0.0, "output": 0.0},
    "qwen2.5:7b": {"input": 0.0, "output": 0.0},
}

_agentcost_track_costs = None
if settings.AGENTCOST_API_KEY and settings.AGENTCOST_PROJECT_ID:
    try:
        from agentcost import track_costs

        track_costs.init(
            api_key=settings.AGENTCOST_API_KEY,
            project_id=settings.AGENTCOST_PROJECT_ID,
            debug=settings.AGENTCOST_DEBUG,
            custom_pricing=_AGENTCOST_PRICING,
        )
        logger.info(
            "AgentCost tracking enabled (project %s).", settings.AGENTCOST_PROJECT_ID
        )
        _agentcost_track_costs = track_costs
    except Exception as exc:  # noqa: BLE001 - degrade to untracked, never crash
        logger.warning("AgentCost init failed - running WITHOUT cost tracking: %s", exc)

def _log_startup_banner() -> None:
    """Log the active provider + model the moment the backend boots, so a
    misconfiguration (wrong provider, retired model, missing key) is visible
    immediately in the logs instead of only when the first question fails."""
    from app.agent.agent import _resolve_model

    provider = settings.LLM_PROVIDER.lower()
    model = _resolve_model(provider, None)
    key = {
        "groq": settings.GROQ_API_KEY,
        # any configured key counts - GEMINI_API_KEY may be blank while the
        # failover list (GEMINI_API_KEYS) supplies the working keys
        "gemini": (settings.gemini_keys() or [""])[0],
        "anthropic": settings.ANTHROPIC_API_KEY,
        "claude": settings.ANTHROPIC_API_KEY,
        "ollama": "local",  # local model needs no key
        "lmstudio": "local",  # local model needs no key
        "cerebras": settings.CEREBRAS_API_KEY,
        "nvidia": settings.NVIDIA_API_KEY,
    }.get(provider, "")
    log_startup(provider, model, key_present=bool(key))


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Runs once at serve time (not on mere import), so the banner reflects the
    # real running config and the backend import is deferred to boot.
    _log_startup_banner()
    yield
    # FLUSH COST EVENTS ON SHUTDOWN. The SDK batches (batch_size 10, flush every
    # 5s), so whatever is still in the buffer when the process stops is lost —
    # and a container restart or a `docker compose down` is exactly when that
    # happens. Its own atexit hook is not reliable under a SIGTERM'd uvicorn, so
    # drain it here, where the shutdown is graceful and ordered.
    if _agentcost_track_costs is not None:
        try:
            _agentcost_track_costs.shutdown()
            logger.info("AgentCost: flushed pending cost events on shutdown.")
        except Exception as exc:  # noqa: BLE001 - never block shutdown
            logger.warning("AgentCost: flush on shutdown failed: %s", exc)


app = FastAPI(
    title="Aastha ERP AI Chatbot API",
    description="Ask questions about the Aastha diamond-manufacturing ERP.",
    version="0.1.0",
    lifespan=_lifespan,
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
    # Follow-up choices rendered as buttons, and the date-picker request — both
    # already flow through /chat/stream (which emits the enriched dict as-is);
    # declared here so the non-streaming /chat returns them too.
    clarify_options: list[str] = []
    ask_date: bool = False
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
    # Every section of a multi-part report ({columns, rows} each), so a "full
    # report" exports one sheet per section instead of only the biggest result.
    # Optional: older clients and single-result answers just send rows.
    sections: list[dict] = Field(default_factory=list, max_length=20)
    format: str = Field("excel", pattern="^(excel|pdf|chart)$")
    title: str = "Report"
    x_col: str | None = None
    y_col: str | None = None


class ExportDashboardRequest(BaseModel):
    """Export a FULL analytics dashboard (KPI tiles + every chart section + its
    data) that was already shown, as one multi-section file. The `dashboard`
    payload is the show_dashboard data the chat rendered."""
    dashboard: dict
    format: str = Field("pdf", pattern="^(pdf|excel)$")
    title: str = "Report"


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
        # Configured = ANY key (primary or a failover key in GEMINI_API_KEYS).
        return "GEMINI_API_KEY" if not settings.gemini_keys() else None
    if provider == "cerebras":
        return "CEREBRAS_API_KEY" if not settings.CEREBRAS_API_KEY else None
    if provider == "nvidia":
        return "NVIDIA_API_KEY" if not settings.NVIDIA_API_KEY else None
    if provider in ("ollama", "lmstudio"):
        return None  # local model — no key required
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

    # FAIL SOFT. Conversation memory is optional CONTEXT - without it a follow-up
    # loses its earlier turns, which is a worse answer, not a failed request. But
    # sessions.get_history() only guards against corrupt JSON, so an unreachable
    # Redis raised straight out of here and 500'd the whole turn.
    #
    # That became more visible once this moved ahead of the date gate (so the
    # gate can see a period the user gave earlier): a Redis outage started
    # breaking even the gated replies, which are supposed to need no
    # infrastructure at all. Caught here rather than in sessions.get_history so
    # the storage layer keeps reporting real failures to its other callers.
    try:
        hist = sessions.get_history(session_id)
    except Exception:
        logger.warning("session history unavailable for %s - answering without "
                       "follow-up context", session_id, exc_info=True)
        return []
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


def _ask_with_cost_tracking(
    question: str,
    *,
    history: list[dict],
    attachments: list[dict],
    session_id: str | None,
    user: dict,
    on_event=None,
) -> dict:
    """Run one chat turn, tagging every Claude call with its API requester.

    One chat turn can make multiple Claude calls while using tools.  AgentCost's
    Anthropic interceptor records each of them; its context manager gives all
    those events the same safe request identifiers.  The context is entered in
    the worker itself, which is important for /chat/stream because ContextVars
    do not automatically cross a manually-created thread.
    """
    from app.agent.agent import ask

    kwargs = {
        "history": history,
        "attachments": attachments,
        "on_event": on_event,
    }
    if _agentcost_track_costs is None:
        return ask(question, **kwargs)

    # Do not attach the question, response, token, or credentials as metadata.
    # These fields let the dashboard group costs by frontend/API caller.
    with _agentcost_track_costs.agent("aastha-erp-chatbot"), _agentcost_track_costs.metadata(
        source="frontend_api",
        endpoint="chat_stream" if on_event else "chat",
        session_id=session_id or "anonymous",
        user_id=str(user.get("username") or user.get("sub") or "anonymous"),
    ):
        return ask(question, **kwargs)


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

    from app.api import sessions

    # Pure greeting / thanks / "ok" -> canned reply, no LLM call. Checked first
    # because it is the most specific gate (whole-string match) and the cheapest:
    # "hi" was costing a full ~29k-token round trip and 5-10s of latency.
    if smalltalk_gate.is_smalltalk(request.question):
        return ChatResponse(**{
            k: v for k, v in smalltalk_gate.smalltalk_response(request.question).items()
            if k in ChatResponse.model_fields
        })

    # RESTRICTED: salary/pay is off limits (client policy) - refuse before the LLM.
    if access_guard.is_pay_question(request.question):
        return ChatResponse(**{
            k: v for k, v in access_guard.refusal_response(request.question).items()
            if k in ChatResponse.model_fields
        })

    # Report question with no period -> ask for the date range (UI date picker)
    # instead of answering over all history. Decided in code, before any LLM call.
    #
    # History is loaded FIRST so the gate can see a period the user already gave
    # ("June 2026" two turns ago). Without it the picker re-appeared on every
    # follow-up. The smalltalk and salary gates above still short-circuit before
    # this, so a greeting never pays for a history read.
    convo_history = _load_history(request.session_id)
    if date_gate.needs_date(request.question, convo_history):
        return ChatResponse(**{
            k: v for k, v in date_gate.ask_date_response(request.question).items()
            if k in ChatResponse.model_fields
        })

    try:
        result = _ask_with_cost_tracking(
            request.question,
            history=convo_history,
            attachments=request.attachments,
            session_id=request.session_id,
            user=user,
        )
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
        clarify_options=result.get("clarify_options", []),
        ask_date=result.get("ask_date", False),
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

    from app.api import sessions

    # Same guard as /chat: fail fast with a clear 503 when the active provider's
    # API key isn't configured, instead of a mid-stream generic error. This is
    # the endpoint the UI actually uses, so it needs the guard most.
    missing = _active_provider_key_missing()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"AI is not configured: {missing} is missing in .env.",
        )

    # Pure greeting / thanks / "ok" -> stream the canned reply immediately (no
    # LLM call, no DB hit). See the same gate on /chat above.
    if smalltalk_gate.is_smalltalk(request.question):
        _small = smalltalk_gate.smalltalk_response(request.question)

        def _smalltalk_stream():
            yield f"data: {json.dumps({'type': 'result', 'data': _small})}\n\n"

        return StreamingResponse(_smalltalk_stream(), media_type="text/event-stream")

    # RESTRICTED: salary/pay is off limits (client policy) - refuse before the LLM.
    if access_guard.is_pay_question(request.question):
        _refusal = access_guard.refusal_response(request.question)

        def _refusal_stream():
            yield f"data: {json.dumps({'type': 'result', 'data': _refusal})}\n\n"

        return StreamingResponse(_refusal_stream(), media_type="text/event-stream")

    # Report question with no period -> stream back the date-picker turn straight
    # away (no LLM call, no DB hit): the UI renders the period chooser.
    # History first, so a period given earlier in the thread suppresses the
    # picker on follow-ups (see the /chat endpoint above).
    convo_history = _load_history(request.session_id)
    if date_gate.needs_date(request.question, convo_history):
        payload = date_gate.ask_date_response(request.question)

        def _ask_date_stream():
            yield f"data: {json.dumps({'type': 'result', 'data': payload})}\n\n"

        return StreamingResponse(_ask_date_stream(), media_type="text/event-stream")

    events: "queue.Queue" = queue.Queue()

    def on_event(msg: str):
        events.put({"type": "status", "message": msg})

    def run():
        try:
            result = _ask_with_cost_tracking(
                request.question,
                history=convo_history,
                attachments=request.attachments,
                session_id=request.session_id,
                user=user,
                on_event=on_event,
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
    # Client display rule: strip raw internal ids before building the file, even
    # though rows reaching here are normally pre-sanitized by postprocess.enrich.
    from app.agent.postprocess import sanitize_export
    columns, rows = sanitize_export(req.columns or list(req.rows[0].keys()), req.rows)
    uid = uuid.uuid4().hex

    # Wrap file generation so dirty/unusual data (control chars, non-Latin text,
    # very wide tables) returns a clean 422 instead of an unhandled 500.
    try:
        if req.format == "pdf":
            path = to_pdf(columns, rows, f"export-{uid}.pdf", title=req.title)
            return _download(path, "application/pdf", "export.pdf")

        if req.format == "chart":
            x_col = req.x_col or columns[0]
            y_col = req.y_col or columns[-1]
            path = to_chart(rows, x_col, y_col, f"export-{uid}.png", title=req.title)
            return _download(path, "image/png", "export.png")

        # Multi-section report -> one sheet per section. PDF/chart stay
        # single-result: a chart of several unrelated result sets is meaningless.
        if len(req.sections) > 1:
            clean_sections = []
            for sec in req.sections:
                s_rows = sec.get("rows") or []
                if not s_rows:
                    continue
                s_cols, s_rows = sanitize_export(
                    sec.get("columns") or list(s_rows[0].keys()), s_rows
                )
                clean_sections.append({"columns": s_cols, "rows": s_rows})
            if len(clean_sections) > 1:
                path = to_excel_sections(clean_sections, f"export-{uid}.xlsx")
                return _download(path, _EXCEL_MEDIA, "export.xlsx")

        path = to_excel(columns, rows, f"export-{uid}.xlsx")
        return _download(path, _EXCEL_MEDIA, "export.xlsx")
    except Exception:
        logger.exception("export_rows failed (format=%s)", req.format)
        raise HTTPException(status_code=422, detail=f"Could not build the {req.format} file from this data.")


@app.post("/export_dashboard")
def export_dashboard(req: ExportDashboardRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Build a downloadable file that reproduces the WHOLE analytics dashboard the
    chat already showed — headline KPIs plus every chart section and its data
    table — instead of a single summary table. No DB re-run; the dashboard data
    is the snapshot the chat rendered. Requires a valid login; rate-limited.
    """
    d = req.dashboard or {}
    if not (d.get("tiles") or d.get("sections")):
        raise HTTPException(status_code=400, detail="No dashboard data to export.")
    uid = uuid.uuid4().hex
    try:
        if req.format == "excel":
            from app.artifacts.excel import dashboard_to_excel
            path = dashboard_to_excel(d, f"dashboard-{uid}.xlsx")
            return _download(path, _EXCEL_MEDIA, "dashboard.xlsx")
        from app.artifacts.pdf import dashboard_to_pdf
        path = dashboard_to_pdf(d, f"dashboard-{uid}.pdf", title=req.title)
        return _download(path, "application/pdf", "dashboard.pdf")
    except Exception:
        logger.exception("export_dashboard failed (format=%s)", req.format)
        raise HTTPException(status_code=422, detail="Could not build the dashboard file.")


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
    except history.ThreadLimitError:
        # History is full (bounds a disk-fill DoS). The frontend treats any
        # non-2xx as "fall back to localStorage", so the chat isn't lost.
        raise HTTPException(
            status_code=507,
            detail="Chat history is full. Delete old chats to make room.",
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


@app.post("/threads/{thread_id}/restore")
def restore_thread(
    thread_id: str = _THREAD_ID, user: dict = Depends(enforce_history_rate_limit)
):
    """Undo a soft-delete within the retention window (a delete only tombstones
    the thread — see history.delete_thread). Enables an 'undo delete' without a
    schema change; no UI wired to it yet."""
    _history_ready()
    try:
        restored = history.restore_thread(thread_id)
    except Exception:
        raise _history_unavailable("restore")
    if not restored:
        raise HTTPException(status_code=404, detail="No recoverable thread with that id.")
    return {"restored": True}


def _suggest_run(kind: str, sql: str, cap: int) -> list[dict]:
    res = run_select(sql, max_rows=cap)
    if not res.get("ok"):
        return []
    return [{"name": r["name"].strip(), "kind": kind} for r in res["rows"] if r.get("name")]


@app.get("/suggest")
def suggest(q: str = "", user: dict = Depends(enforce_history_rate_limit)):
    """
    Entity autocomplete: return REAL department / kapan / employee names matching
    `q`. Deterministic — a LIKE/SOUNDEX against actual values, NO AI — so a user
    PICKS a real name instead of misspelling it, killing the 'fancy vs Fency'
    class of miss on any provider.

    Precision matters more than recall here (the user is mid-sentence, so a partial
    word must not flood the box):
      - departments & kapans are FEW and curated -> substring + SOUNDEX (a misspelt
        'fanc' still surfaces the real 'Fency'); these rank FIRST.
      - employees are THOUSANDS -> PREFIX match only, min 3 chars, capped at 3, so a
        mid-word coincidence ('ra-FA-liya') never floods out the real answer.

    Uses the lighter history rate-limit bucket (it fires as the user types).
    """
    import re as _re

    # Sanitize to a safe charset so the value is a harmless LIKE literal (no injection).
    safe = _re.sub(r"[^A-Za-z0-9 ._-]", "", q or "").strip()[:40]
    if len(safe) < 2:
        return {"suggestions": []}

    single = " " not in safe and len(safe) >= 3  # SOUNDEX only makes sense per-token

    # Departments are WORDS (Fency, Ghisi, Galaxy) — substring, plus a phonetic
    # fallback so a misspelling ("fanc") still resolves ("Fency"). The SOUNDEX arm
    # is length-guarded to real word-length names close to what was typed: without
    # it, a 3-letter query collides with tiny codes and unrelated long names
    # (e.g. SOUNDEX('giv') == SOUNDEX of the 2-letter kapan codes GB/GF/GP/GV).
    dept = f"Name LIKE '%{safe}%'"
    if single:
        dept = (
            f"({dept} OR (SOUNDEX(Name) = SOUNDEX('{safe}') "
            f"AND LEN(Name) BETWEEN 4 AND {len(safe) + 3}))"
        )
    out = _suggest_run(
        "department",
        f"SELECT DISTINCT TOP 6 Name AS name FROM tblDepartMent "
        f"WHERE ({dept}) AND Name IS NOT NULL AND Name <> '' ORDER BY name",
        6,
    )

    # Kapans are short CODES (GB, GI, 101), not words anyone misspells phonetically,
    # so SOUNDEX here is pure noise — it made "giv" surface GB/GF/GP/GV. Substring only.
    kap = f"KapanName LIKE '%{safe}%'"
    out += _suggest_run(
        "kapan",
        f"SELECT DISTINCT TOP 6 KapanName AS name FROM tblKapan "
        f"WHERE ({kap}) AND KapanName IS NOT NULL AND KapanName <> '' ORDER BY name",
        6,
    )

    # Employees (thousands) — PREFIX only (first OR last name starts with the word),
    # min 3 chars, capped, so they never flood the curated matches above.
    if len(safe) >= 3:
        out += _suggest_run(
            "employee",
            f"SELECT DISTINCT TOP 3 FirstName + ' ' + LastName AS name FROM tblEmployee "
            f"WHERE (FirstName LIKE '{safe}%' OR LastName LIKE '{safe}%') "
            f"AND FirstName IS NOT NULL ORDER BY name",
            3,
        )

    return {"suggestions": out[:8]}


@app.post("/export")
def export(req: ExportRequest, user: dict = Depends(enforce_rate_limit)):
    """
    Turn a read-only SELECT into a downloadable file (Excel/PDF/chart).
    No AI key needed - this runs the query directly through the safe runner.
    Returns the file itself for the browser to download. Requires a valid login
    and is rate-limited per user (it runs arbitrary read-only SQL).

    This is the "re-run for the FULL data" path the UI uses when a reopened
    thread's stored snapshot was trimmed - so it MUST use the same high export
    cap as the chat-time capture, not the 1000-row model default (a mismatch
    here silently shrank downloads on reopened threads).
    """
    from app.agent.tools import EXPORT_ROW_CAP
    result = run_select(req.query, max_rows=EXPORT_ROW_CAP)
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

    # Client display rule: never leak raw internal ids into a downloaded file.
    from app.agent.postprocess import sanitize_export
    columns, rows = sanitize_export(columns, rows)

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
