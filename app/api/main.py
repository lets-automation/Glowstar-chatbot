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

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.artifacts.charts import to_chart
from app.artifacts.excel import to_excel
from app.artifacts.pdf import to_pdf
from app.config import settings
from app.core import auth
from app.core.logging_util import logger
from app.core.rate_limit import enforce_rate_limit
from app.database.runner import run_select

app = FastAPI(
    title="Aastha ERP AI Chatbot API",
    description="Ask questions about the Aastha diamond-manufacturing ERP.",
    version="0.1.0",
)

# --- CORS ---
# React runs on a different origin (e.g. http://localhost:3000), so the
# browser needs CORS permission to call this API. CORS_ORIGINS defaults to "*"
# for local dev; set it to the real deployed frontend origin(s) in .env for
# any real deployment (comma-separated for more than one).
_cors_origins = (
    ["*"] if settings.CORS_ORIGINS.strip() == "*"
    else [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    display_name: str
    expires_in_minutes: int


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    helpful: bool
    session_id: str | None = None


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

    history = sessions.get_history(request.session_id)
    try:
        result = ask(request.question, history=history, attachments=request.attachments)
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
    history = sessions.get_history(request.session_id)

    def on_event(msg: str):
        events.put({"type": "status", "message": msg})

    def run():
        try:
            result = ask(
                request.question,
                history=history,
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

    # Wrap file generation so dirty/unusual data (control chars, non-Latin text,
    # very wide tables) returns a clean 422 instead of an unhandled 500.
    try:
        if req.format == "pdf":
            path = to_pdf(columns, req.rows, "export.pdf", title=req.title)
            return FileResponse(path, media_type="application/pdf", filename="export.pdf")

        if req.format == "chart":
            x_col = req.x_col or columns[0]
            y_col = req.y_col or columns[-1]
            path = to_chart(req.rows, x_col, y_col, "export.png", title=req.title)
            return FileResponse(path, media_type="image/png", filename="export.png")

        path = to_excel(columns, req.rows, "export.xlsx")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="export.xlsx",
        )
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
    import os
    import uuid

    # Basic guardrails: cap size and keep only the extension from the name.
    MAX_BYTES = 15 * 1024 * 1024  # 15 MB
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15 MB).")

    upload_dir = os.path.join("outputs", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_id = uuid.uuid4().hex
    ext = os.path.splitext(file.filename or "")[1][:10]
    path = os.path.join(upload_dir, f"{file_id}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
    }


@app.post("/feedback")
def feedback(req: FeedbackRequest, user: dict = Depends(auth.get_current_user)):
    """
    Store a thumbs up/down on an answer (for improving prompts/tools).
    Appended to logs/feedback.jsonl. Requires a valid login.
    """
    import json
    import os
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
        raise HTTPException(
            status_code=400, detail=f"Query rejected or failed: {result['error']}"
        )

    columns, rows = result["columns"], result["rows"]
    if not rows:
        raise HTTPException(status_code=400, detail="Query returned no rows.")

    try:
        if req.format == "pdf":
            path = to_pdf(columns, rows, "export.pdf", title=req.title)
            return FileResponse(path, media_type="application/pdf", filename="export.pdf")

        if req.format == "chart":
            x_col = req.x_col or columns[0]
            y_col = req.y_col or columns[-1]
            path = to_chart(rows, x_col, y_col, "export.png", title=req.title)
            return FileResponse(path, media_type="image/png", filename="export.png")

        # default: excel
        path = to_excel(columns, rows, "export.xlsx")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="export.xlsx",
        )
    except Exception:
        logger.exception("export failed (format=%s)", req.format)
        raise HTTPException(status_code=422, detail=f"Could not build the {req.format} file from this data.")
