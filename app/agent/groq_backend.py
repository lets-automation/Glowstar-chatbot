"""
groq_backend.py
---------------
Runs the agent using Groq (OpenAI-compatible tool calling).
Used when LLM_PROVIDER=groq (the free-tier testing setup).
"""

import json
import re

from groq import Groq

from app.agent import attachments as attachments_mod
from app.agent import tools, widget
from app.agent._retry import call_with_retry
from app.config import settings
from app.core.logging_util import log_interaction


def _user_content(question: str, file_context: dict | None):
    """
    Build the first user message. With attachments it's a content-part list
    (OpenAI/Groq multimodal): file text + image_url parts + the question.
    Without attachments it's a plain string.
    """
    if not attachments_mod.has_content(file_context):
        return question
    parts = [{"type": "text", "text": attachments_mod.build_preamble(file_context)}]
    for img in file_context.get("images", []):
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['media_type']};base64,{img['data']}"},
        })
    parts.append({"type": "text", "text": question})
    return parts

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
    for spec in (
        *tools.TOOL_SPECS,
        widget.SHOW_WIDGET_TOOL_SPEC,
        widget.SHOW_CHART_TOOL_SPEC,
        widget.SHOW_DASHBOARD_TOOL_SPEC,
    )
]


def _client():
    # Local Ollama: OpenAI-compatible endpoint on this machine — no key, no
    # internet, no quota. Use the real OpenAI SDK here, NOT the Groq client:
    # the Groq SDK hardcodes Groq's "/openai/v1/…" request path and would 404
    # against Ollama. The OpenAI client honours base_url correctly, and exposes
    # the identical chat.completions.create surface this backend relies on.
    if settings.LLM_PROVIDER.lower() == "ollama":
        from openai import OpenAI
        return OpenAI(api_key="ollama", base_url=settings.OLLAMA_BASE_URL)
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env.")
    return Groq(api_key=settings.GROQ_API_KEY)


def _looks_like_unrun_sql(text: str) -> bool:
    """True if the reply EMBEDS a SELECT query — i.e. the model wrote the SQL in
    its answer instead of calling the run_sql tool. Some Groq models (notably
    llama-4-scout) do this on list/ranking questions, so no query runs and the
    user sees no data. Detecting it lets us force an actual execution."""
    if not text:
        return False
    low = text.lower()
    return "select" in low and "from" in low


# The user asked for an analytics dashboard/overview. Weak models often answer
# such questions in plain text and skip the show_dashboard tool entirely; when
# this matches and no dashboard was built, we nudge one corrective round.
DASHBOARD_ASKED_RE = re.compile(
    r"\b(dashboards?|analytics?|overview|analysis|analyse|analyze)\b", re.IGNORECASE
)

DASHBOARD_NUDGE = (
    "The user asked for an analytics view, but you have not called the "
    "show_dashboard tool, so they see no dashboard. Do it NOW: if you need "
    "more figures, run 1-3 more quick aggregate run_sql queries (e.g. a "
    "monthly trend, a breakdown by department/category); then call "
    "show_dashboard ONCE with 3-6 KPI tiles and 1-2 sections built ONLY from "
    "numbers your run_sql queries actually returned. Then give a short text "
    "summary."
)


def ask_groq(
    question: str,
    model: str,
    history: list[dict] | None = None,
    on_event=None,
    file_context: dict | None = None,
) -> dict:
    """Answer a question via Groq. Returns {answer, sql_used, rows_returned}."""
    client = _client()
    history = history or []
    file_grounded = attachments_mod.grounds_data(file_context)

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
        {"role": "user", "content": _user_content(question, file_context)},
    ]

    sql_used: list[str] = []
    last_row_count = 0
    widgets: list[dict] = []  # visuals emitted via show_widget, shown to the user
    data_columns: list[str] = []  # columns/rows from the LAST successful run_sql,
    data_rows: list[dict] = []    # captured so export uses the exact data shown

    nudged_to_execute = False  # have we already forced a stalled model to run its SQL?
    nudged_dashboard = False   # have we already asked it to build the requested dashboard?
    force_tool = False         # require a tool call on the NEXT request (set by the nudge)
    dashboard_built = False    # did show_dashboard actually render this turn?
    retried_bad_tool_call = False  # one retry when Groq rejects a tool call's arguments

    emit("Analyzing your question…")
    for _ in range(tools.MAX_TOOL_ROUNDS):
        try:
            choice = "required" if force_tool else "auto"
            force_tool = False  # one-shot
            response = call_with_retry(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=_GROQ_TOOLS,
                    tool_choice=choice,
                    temperature=0,  # deterministic: same question -> same SQL, no drift
                    max_tokens=1024,
                )
            )
        except Exception as exc:
            # Don't crash. Give a clear message depending on the cause.
            err = str(exc).lower()
            # A REJECTED TOOL CALL (arguments didn't match the tool's schema,
            # e.g. numbers where strings are required) is recoverable: tell the
            # model exactly what Groq rejected and let it retry once, instead
            # of failing the whole turn.
            if (
                "tool_use_failed" in err or "tool call validation failed" in err
            ) and not retried_bad_tool_call:
                retried_bad_tool_call = True
                messages.append({
                    "role": "user",
                    "content": (
                        "Your last tool call was REJECTED because its arguments "
                        f"did not match the tool's schema: {str(exc)[:600]} ... "
                        "Fix the arguments (label arrays must contain STRINGS; "
                        "value arrays must contain NUMBERS) and make the SAME "
                        "tool call again with the same data."
                    ),
                })
                emit("Retrying…")
                continue
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
            # Model-quirk guard: if the reply EMBEDS a SELECT but no query has
            # actually run (and this isn't a file-only answer), the model wrote
            # SQL instead of calling run_sql. Force one execution round instead
            # of returning a data-less "here's the query" reply to the user.
            if (
                not sql_used
                and not file_grounded
                and not nudged_to_execute
                and _looks_like_unrun_sql(answer)
            ):
                nudged_to_execute = True
                force_tool = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({
                    "role": "user",
                    "content": (
                        "You wrote a SQL query but did not run it, so I have no "
                        "data to show. Call the run_sql tool NOW to execute the "
                        "EXACT query you just wrote above (do not rewrite or "
                        "simplify it), then answer from the actual rows it "
                        "returns. Do not put SQL in your reply."
                    ),
                })
                emit("Running the query…")
                continue
            # Dashboard guard: the question asked for analytics/overview/
            # dashboard/analysis but the model finished without building one
            # (weak models skip optional visual tools). Nudge one corrective
            # round; requires data to have been queried (sql_used) so the
            # dashboard can't be built from invented numbers.
            if (
                not dashboard_built
                and not nudged_dashboard
                and sql_used
                and not file_grounded
                and DASHBOARD_ASKED_RE.search(question or "")
            ):
                nudged_dashboard = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": DASHBOARD_NUDGE})
                emit("Building your dashboard…")
                continue
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
                code = widget.ensure_chart_lib(args.get("widget_code"))
                if code:
                    widgets.append({"title": args.get("title", "widget"), "code": code, "kind": "widget"})
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": "rendered"}
                )
                continue

            if tc.function.name == widget.SHOW_CHART_TOOL_SPEC["name"]:
                # Deterministic chart: the model gives data, we build correct HTML.
                emit("Rendering a chart…")
                try:
                    code = widget.build_chart_html(args)
                    widgets.append({"title": args.get("title", "chart"), "code": code, "kind": "chart"})
                    outcome = "rendered"
                except Exception as exc:
                    outcome = f"ERROR: {exc}"
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": outcome}
                )
                continue

            if tc.function.name == widget.SHOW_DASHBOARD_TOOL_SPEC["name"]:
                # Deterministic dashboard: the model gives data, we build the page.
                emit("Building your dashboard…")
                try:
                    code = widget.build_dashboard_html(args)
                    widgets.append({"title": args.get("title", "dashboard"), "code": code, "kind": "dashboard"})
                    outcome = "rendered"
                    dashboard_built = True
                except Exception as exc:
                    outcome = f"ERROR: {exc}"
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": outcome}
                )
                continue

            emit(tools.friendly_status(tc.function.name))
            result_text, sql, row_count, cols_full, rows_full = tools.run_tool(tc.function.name, args)
            if sql:
                sql_used.append(sql)
                last_row_count = row_count
                # Capture the FULL rows from a successful run_sql (the model only
                # sees a sample) so export is the exact, complete data.
                if tc.function.name == "run_sql" and rows_full:
                    data_columns, data_rows = cols_full, rows_full
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
            model=model, messages=messages, temperature=0, max_tokens=1024
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
        "data_columns": data_columns,
        "data_rows": data_rows,
        "file_grounded": file_grounded,
    }
