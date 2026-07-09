"""
anthropic_backend.py
--------------------
Runs the agent using Anthropic / Claude (native tool use).
Used when LLM_PROVIDER=anthropic. Switch to this once the Claude key is
available for best accuracy. The big schema block is prompt-cached.
"""

import anthropic

from app.agent import attachments as attachments_mod
from app.agent import tools, widget
from app.agent._retry import call_with_retry
from app.config import settings
from app.core.logging_util import log_interaction


def _user_content(question: str, file_context: dict | None):
    """First user message: file text + image blocks + the question (Claude format)."""
    if not attachments_mod.has_content(file_context):
        return question
    blocks = [{"type": "text", "text": attachments_mod.build_preamble(file_context)}]
    for img in file_context.get("images", []):
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["data"],
            },
        })
    blocks.append({"type": "text", "text": question})
    return blocks

# Tools in Anthropic format, built from the shared specs. show_widget is appended
# so the model can draw inline visuals instead of describing them in prose.
_ANTHROPIC_TOOLS = [
    {
        "name": spec["name"],
        "description": spec["description"],
        "input_schema": spec["schema"],
    }
    for spec in (
        *tools.TOOL_SPECS,
        widget.SHOW_WIDGET_TOOL_SPEC,
        widget.SHOW_CHART_TOOL_SPEC,
        widget.SHOW_DASHBOARD_TOOL_SPEC,
    )
]


def _client() -> anthropic.Anthropic:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env.")
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _system_blocks(question: str) -> list[dict]:
    """
    Rules (cached) + the question-specific schema. Only the tables relevant to
    this question are detailed, which keeps tokens low.
    """
    return [
        {
            "type": "text",
            "text": tools.RULES,
            "cache_control": {"type": "ephemeral"},
        },
        {
            # Design-system rules for the show_widget tool. Stable prefix -> cached.
            "type": "text",
            "text": widget.WIDGET_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": "DATABASE SCHEMA AND GLOSSARY:\n\n" + tools.dynamic_schema_for(question),
        },
    ]


def ask_anthropic(
    question: str,
    model: str,
    history: list[dict] | None = None,
    on_event=None,
    file_context: dict | None = None,
) -> dict:
    """Answer a question via Claude. Returns {answer, sql_used, rows_returned}."""
    client = _client()
    history = history or []
    file_grounded = attachments_mod.grounds_data(file_context)

    def emit(msg):
        if on_event:
            on_event(msg)

    emit("Analyzing your question…")
    routing_text = tools.routing_text(question, history)
    system = _system_blocks(routing_text)
    messages = [*history, {"role": "user", "content": _user_content(question, file_context)}]

    sql_used: list[str] = []
    last_row_count = 0
    widgets: list[dict] = []  # visuals emitted via show_widget, shown to the user
    data_columns: list[str] = []  # columns/rows from the LAST successful run_sql,
    data_rows: list[dict] = []    # captured so export uses the exact data shown

    for _ in range(tools.MAX_TOOL_ROUNDS):
        try:
            response = call_with_retry(
                lambda: client.messages.create(
                    model=model,
                    max_tokens=1024,
                    system=system,
                    tools=_ANTHROPIC_TOOLS,
                    messages=messages,
                    temperature=0,
                )
            )
        except Exception as exc:
            err = str(exc).lower()
            log_interaction(question, sql_used, last_row_count, error=str(exc))
            busy = "rate" in err or "429" in err or "quota" in err
            # ok=False: the turn failed, so the UI must not offer export.
            return {
                "answer": (
                    "The assistant is busy right now. Please try again shortly."
                    if busy
                    else "Sorry, I had trouble answering that. Please rephrase."
                ),
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "ok": False,
            }

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            answer = "".join(
                block.text for block in response.content if block.type == "text"
            )
            log_interaction(question, sql_used, last_row_count)
            return {
                "answer": answer.strip(),
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "widgets": widgets,
                "data_columns": data_columns,
                "data_rows": data_rows,
                "file_grounded": file_grounded,
            }

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == widget.SHOW_WIDGET_TOOL_SPEC["name"]:
                # Not a DB tool: the "result" is a UI artifact for the user. Capture
                # it and return a minimal tool_result so the tool cycle stays valid.
                emit("Rendering a visual…")
                code = widget.ensure_chart_lib((block.input or {}).get("widget_code"))
                if code:
                    widgets.append(
                        {"title": (block.input or {}).get("title", "widget"), "code": code, "kind": "widget"}
                    )
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": "rendered"}
                )
                continue

            if block.name == widget.SHOW_CHART_TOOL_SPEC["name"]:
                # Deterministic chart: the model gives data, we build correct HTML.
                emit("Rendering a chart…")
                try:
                    code = widget.build_chart_html(block.input or {})
                    widgets.append(
                        {"title": (block.input or {}).get("title", "chart"), "code": code, "kind": "chart"}
                    )
                    outcome = "rendered"
                except Exception as exc:
                    outcome = f"ERROR: {exc}"
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": outcome}
                )
                continue

            if block.name == widget.SHOW_DASHBOARD_TOOL_SPEC["name"]:
                # Deterministic dashboard: the model gives data, we build the page.
                emit("Building your dashboard…")
                try:
                    code = widget.build_dashboard_html(block.input or {})
                    widgets.append(
                        {"title": (block.input or {}).get("title", "dashboard"), "code": code, "kind": "dashboard"}
                    )
                    outcome = "rendered"
                except Exception as exc:
                    outcome = f"ERROR: {exc}"
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": outcome}
                )
                continue
            emit(tools.friendly_status(block.name))
            result_text, sql, row_count, cols_full, rows_full = tools.run_tool(block.name, block.input)
            if sql:
                sql_used.append(sql)
                last_row_count = row_count
                if block.name == "run_sql" and rows_full:
                    data_columns, data_rows = cols_full, rows_full
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    # Hit the step limit -> force a final plain-text answer (no tools).
    messages.append(
        {
            "role": "user",
            "content": (
                "Give your best final answer now in plain text, based on what you "
                "found. If you could NOT find the requested data, tell the user "
                "plainly that this information is not tracked in the system "
                "(e.g. 'Sales are not recorded in this system'). Do NOT say you "
                "couldn't complete the request."
            ),
        }
    )
    synth_ok = True
    try:
        final = client.messages.create(
            model=model, max_tokens=1024, system=system, messages=messages, temperature=0
        )
        answer = "".join(b.text for b in final.content if b.type == "text").strip()
    except Exception:
        answer = ""
        synth_ok = False

    log_interaction(question, sql_used, last_row_count)
    return {
        "answer": answer or "I don't have that information in the database.",
        "sql_used": sql_used,
        "rows_returned": last_row_count,
        "widgets": widgets,
        "ok": synth_ok,
        "data_columns": data_columns,
        "data_rows": data_rows,
        "file_grounded": file_grounded,
    }
