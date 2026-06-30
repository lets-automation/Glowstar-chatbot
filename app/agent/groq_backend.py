"""
groq_backend.py
---------------
Runs the agent using Groq (OpenAI-compatible tool calling).
Used when LLM_PROVIDER=groq (the free-tier testing setup).
"""

import json

from groq import Groq

from app.agent import tools, widget
from app.agent._retry import call_with_retry
from app.config import settings
from app.core.logging_util import log_interaction

# Tools in OpenAI/Groq "function" format, built from the shared specs. show_widget
# is appended so the model can draw inline visuals instead of describing them.
_GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": spec["schema"],
        },
    }
    for spec in (*tools.TOOL_SPECS, widget.SHOW_WIDGET_TOOL_SPEC)
]


def _client() -> Groq:
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env.")
    return Groq(api_key=settings.GROQ_API_KEY)


def ask_groq(
    question: str,
    model: str,
    history: list[dict] | None = None,
    on_event=None,
) -> dict:
    """Answer a question via Groq. Returns {answer, sql_used, rows_returned}."""
    client = _client()
    history = history or []

    def emit(msg):
        if on_event:
            on_event(msg)

    # Route on the follow-up context too (last user turn + this question), so
    # "...and by colour?" still pulls the right tables.
    routing_text = tools.routing_text(question, history)
    messages = [
        {
            "role": "system",
            "content": widget.WIDGET_SYSTEM_PROMPT
            + "\n\n"
            + tools.system_prompt_for(routing_text),
        },
        *history,
        {"role": "user", "content": question},
    ]

    sql_used: list[str] = []
    last_row_count = 0
    widgets: list[dict] = []  # visuals emitted via show_widget, shown to the user

    emit("Analyzing your question…")
    for _ in range(tools.MAX_TOOL_ROUNDS):
        try:
            response = call_with_retry(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=_GROQ_TOOLS,
                    tool_choice="auto",
                    temperature=0.3,  # mild warmth for human-sounding prose; SQL stays guarded
                    max_tokens=1024,
                )
            )
        except Exception as exc:
            # Don't crash. Give a clear message depending on the cause.
            err = str(exc).lower()
            log_interaction(question, sql_used, last_row_count, error=str(exc))
            if "rate_limit" in err or "429" in err or "quota" in err:
                answer = (
                    "The assistant is busy right now (usage limit reached). "
                    "Please try again in a minute."
                )
            else:
                answer = (
                    "Sorry, I had trouble forming that query. Please try "
                    "rephrasing the question."
                )
            # ok=False: the turn failed (no real answer), so the UI must not
            # offer export even though some SQL may have run before the failure.
            return {
                "answer": answer,
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "ok": False,
            }

        msg = response.choices[0].message

        if not msg.tool_calls:
            answer = msg.content or ""
            log_interaction(question, sql_used, last_row_count)
            return {
                "answer": answer.strip(),
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "widgets": widgets,
            }

        # Record the assistant turn (with its tool calls).
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # Run each tool call and feed the result back.
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if tc.function.name == widget.SHOW_WIDGET_TOOL_SPEC["name"]:
                # Not a DB tool: the "result" is a UI artifact for the user. Capture
                # it and feed back a minimal tool result so the cycle stays valid.
                emit("Rendering a visual…")
                code = args.get("widget_code")
                if code:
                    widgets.append({"title": args.get("title", "widget"), "code": code})
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": "rendered"}
                )
                continue

            emit(tools.friendly_status(tc.function.name))
            result_text, sql, row_count = tools.run_tool(tc.function.name, args)
            if sql:
                sql_used.append(sql)
                last_row_count = row_count
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result_text}
            )

    # Hit the step limit -> force a final plain-text answer from what we have,
    # WITHOUT tools (so it can't loop further).
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
        final = client.chat.completions.create(
            model=model, messages=messages, temperature=0.3, max_tokens=1024
        )
        answer = (final.choices[0].message.content or "").strip()
    except Exception as exc:
        log_interaction(question, sql_used, last_row_count, error=str(exc))
        answer = ""
        synth_ok = False  # couldn't form the final answer -> suppress export

    log_interaction(question, sql_used, last_row_count)
    return {
        "answer": answer or "I don't have that information in the database.",
        "sql_used": sql_used,
        "rows_returned": last_row_count,
        "widgets": widgets,
        "ok": synth_ok,
    }
