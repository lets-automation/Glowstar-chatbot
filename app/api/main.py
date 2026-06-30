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

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.artifacts.charts import to_chart
from app.artifacts.excel import to_excel
from app.artifacts.pdf import to_pdf
from app.config import settings
from app.database.runner import run_select

app = FastAPI(
    title="Aastha ERP AI Chatbot API",
    description="Ask questions about the Aastha diamond-manufacturing ERP.",
    version="0.1.0",
)

# --- CORS ---
# React runs on a different origin (e.g. http://localhost:3000), so the
# browser needs CORS permission to call this API.
# NOTE: allow_origins=["*"] is open for development. Before production,
# tighten this to the client's real React domain(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# --- Endpoints ---
@app.get("/health")
def health():
    """Simple check that the API is up. Never touches Claude or the DB."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Ask the agent a question and return its answer.

    - 503 if the Anthropic API key isn't configured yet.
    - 500 if something unexpected goes wrong while answering.
    """
    # Guard: don't even try to call the LLM without a key. Return clean JSON.
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI is not configured: GROQ_API_KEY is missing in .env.",
        )

    # Import here so the app still starts/imports fine when the key is absent.
    from app.agent.agent import ask
    from app.api import sessions

    history = sessions.get_history(request.session_id)
    try:
        result = ask(request.question, history=history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error answering: {exc}")

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
    )


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """
    Same as /chat but streams live status events (Server-Sent Events) so the UI
    can show 'Querying the database…' etc. as the agent works, then the final
    answer. Each line is: data: {json}\\n\\n
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
            result = ask(request.question, history=history, on_event=on_event)
            sessions.add_turn(request.session_id, request.question, result["answer"])
            events.put({"type": "result", "data": result})
        except Exception as exc:
            events.put({"type": "error", "message": str(exc)})
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


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    Accept an image or file attachment from the chat composer and store it.

    Saves to outputs/uploads/<file_id><ext> and returns a reference the client
    keeps on the message. NOTE: this only persists the upload — feeding its
    contents into the agent's reasoning (e.g. OCR a certificate image, or read
    an Excel for extra context) is a deliberate next step, not done here.
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
def feedback(req: FeedbackRequest):
    """
    Store a thumbs up/down on an answer (for improving prompts/tools).
    Appended to logs/feedback.jsonl.
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
def export(req: ExportRequest):
    """
    Turn a read-only SELECT into a downloadable file (Excel/PDF/chart).
    No AI key needed - this runs the query directly through the safe runner.
    Returns the file itself for the browser to download.
    """
    result = run_select(req.query)
    if not result["ok"]:
        raise HTTPException(
            status_code=400, detail=f"Query rejected or failed: {result['error']}"
        )

    columns, rows = result["columns"], result["rows"]
    if not rows:
        raise HTTPException(status_code=400, detail="Query returned no rows.")

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
