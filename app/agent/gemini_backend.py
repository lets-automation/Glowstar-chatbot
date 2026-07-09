"""
gemini_backend.py
-----------------
Runs the agent using Google Gemini (native function calling).
Used when LLM_PROVIDER=gemini. This is the free-tier FALLBACK for Groq: Gemini's
free tier has a much larger tokens-per-minute budget, so when Groq hits its daily
cap we can keep working by flipping LLM_PROVIDER=gemini in .env.

Same shared logic as the other backends (tools.RULES + schema, tools.run_tool,
anti-fabrication 'ok' flag, row capture for export, temperature 0). Only the
provider-specific call + function-calling format differ.
"""

import base64

from google import genai
from google.genai import types

from app.agent import attachments as attachments_mod
from app.agent import tools, widget
from app.config import settings
from app.core.logging_util import log_interaction


def _client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in .env.")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _to_schema(js: dict) -> types.Schema:
    """Convert our JSON-schema tool spec into a Gemini types.Schema."""
    t = js.get("type") or "string"
    if isinstance(t, list):  # union type like ["number","string"] -> first entry
        t = t[0] if t else "string"
    t = t.upper()
    if t == "OBJECT":
        return types.Schema(
            type="OBJECT",
            properties={k: _to_schema(v) for k, v in js.get("properties", {}).items()},
            required=js.get("required", []),
        )
    if t == "ARRAY":
        return types.Schema(type="ARRAY", items=_to_schema(js.get("items", {})))
    kwargs = {"type": t}
    if "description" in js:
        kwargs["description"] = js["description"]
    if "enum" in js:
        kwargs["enum"] = js["enum"]
    return types.Schema(**kwargs)


# All shared tools + show_widget, as one Gemini Tool (built once).
_GEMINI_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name=spec["name"],
            description=spec["description"],
            parameters=_to_schema(spec["schema"]),
        )
        for spec in (
            *tools.TOOL_SPECS,
            widget.SHOW_WIDGET_TOOL_SPEC,
            widget.SHOW_CHART_TOOL_SPEC,
            widget.SHOW_DASHBOARD_TOOL_SPEC,
        )
    ]
)


def _history_to_contents(history: list[dict] | None) -> list:
    """Turn prior {role, content} turns into Gemini Content objects."""
    out = []
    for m in history or []:
        role = "model" if m.get("role") == "assistant" else "user"
        out.append(types.Content(role=role, parts=[types.Part(text=m.get("content", ""))]))
    return out


def _user_parts(question: str, file_context: dict | None) -> list:
    """First user turn's parts: file text + image parts + the question."""
    if not attachments_mod.has_content(file_context):
        return [types.Part(text=question)]
    parts = [types.Part(text=attachments_mod.build_preamble(file_context))]
    for img in file_context.get("images", []):
        parts.append(
            types.Part.from_bytes(
                data=base64.b64decode(img["data"]), mime_type=img["media_type"]
            )
        )
    parts.append(types.Part(text=question))
    return parts


def ask_gemini(
    question: str,
    model: str,
    history: list[dict] | None = None,
    on_event=None,
    file_context: dict | None = None,
) -> dict:
    """Answer a question via Gemini. Same return shape as the other backends."""
    client = _client()
    file_grounded = attachments_mod.grounds_data(file_context)

    def emit(msg):
        if on_event:
            on_event(msg)

    emit("Analyzing your question…")
    routing = tools.routing_text(question, history)
    system = (
        tools.system_prompt_for(routing)
        + "\n\n"
        + widget.WIDGET_SYSTEM_PROMPT
    )
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[_GEMINI_TOOL],
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents = _history_to_contents(history) + [
        types.Content(role="user", parts=_user_parts(question, file_context))
    ]

    sql_used: list[str] = []
    last_row_count = 0
    widgets: list[dict] = []
    data_columns: list[str] = []
    data_rows: list[dict] = []
    nudged_dashboard = False  # one corrective round if a requested dashboard was skipped
    dashboard_built = False

    for _ in range(tools.MAX_TOOL_ROUNDS):
        try:
            resp = client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            err = str(exc).lower()
            log_interaction(question, sql_used, last_row_count, error=str(exc))
            busy = any(h in err for h in ("rate", "429", "quota", "resource_exhausted", "exhausted"))
            return {
                "answer": (
                    "The assistant is busy right now (usage limit reached). "
                    "Please try again in a minute."
                    if busy
                    else "Sorry, I had trouble answering that. Please rephrase."
                ),
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "ok": False,
            }

        cand = resp.candidates[0] if resp.candidates else None
        parts = list(cand.content.parts) if (cand and cand.content and cand.content.parts) else []
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not calls:
            # No more tool calls -> this is the final answer.
            answer = "".join(p.text for p in parts if getattr(p, "text", None)).strip()
            # Dashboard guard (mirrors groq_backend): the question asked for
            # analytics/overview/dashboard/analysis but no dashboard was built.
            # Nudge one corrective round; requires queried data (sql_used).
            from app.agent.groq_backend import DASHBOARD_ASKED_RE, DASHBOARD_NUDGE
            if (
                not dashboard_built
                and not nudged_dashboard
                and sql_used
                and not file_grounded
                and DASHBOARD_ASKED_RE.search(question or "")
            ):
                nudged_dashboard = True
                if cand and cand.content:
                    contents.append(cand.content)
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=DASHBOARD_NUDGE)],
                    )
                )
                emit("Building your dashboard…")
                continue
            log_interaction(question, sql_used, last_row_count)
            return {
                "answer": answer,
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "widgets": widgets,
                "data_columns": data_columns,
                "data_rows": data_rows,
                "file_grounded": file_grounded,
            }

        # Record the model's tool-call turn, then run each tool.
        contents.append(cand.content)
        responses = []
        for fc in calls:
            name = fc.name
            args = dict(fc.args) if fc.args else {}

            if name == widget.SHOW_WIDGET_TOOL_SPEC["name"]:
                emit("Rendering a visual…")
                code = widget.ensure_chart_lib(args.get("widget_code"))
                if code:
                    widgets.append({"title": args.get("title", "widget"), "code": code, "kind": "widget"})
                responses.append(
                    types.Part.from_function_response(name=name, response={"result": "rendered"})
                )
                continue

            if name == widget.SHOW_CHART_TOOL_SPEC["name"]:
                # Deterministic chart: the model gives data, we build correct HTML.
                emit("Rendering a chart…")
                try:
                    code = widget.build_chart_html(args)
                    widgets.append({"title": args.get("title", "chart"), "code": code, "kind": "chart"})
                    outcome = "rendered"
                except Exception as exc:
                    outcome = f"ERROR: {exc}"
                responses.append(
                    types.Part.from_function_response(name=name, response={"result": outcome})
                )
                continue

            if name == widget.SHOW_DASHBOARD_TOOL_SPEC["name"]:
                # Deterministic dashboard: the model gives data, we build the page.
                emit("Building your dashboard…")
                try:
                    code = widget.build_dashboard_html(args)
                    widgets.append({"title": args.get("title", "dashboard"), "code": code, "kind": "dashboard"})
                    outcome = "rendered"
                    dashboard_built = True
                except Exception as exc:
                    outcome = f"ERROR: {exc}"
                responses.append(
                    types.Part.from_function_response(name=name, response={"result": outcome})
                )
                continue

            emit(tools.friendly_status(name))
            result_text, sql, row_count, cols_full, rows_full = tools.run_tool(name, args)
            if sql:
                sql_used.append(sql)
                last_row_count = row_count
                if name == "run_sql" and rows_full:
                    data_columns, data_rows = cols_full, rows_full
            responses.append(
                types.Part.from_function_response(name=name, response={"result": result_text})
            )
        contents.append(types.Content(role="user", parts=responses))

    # Hit the step limit -> force a final plain-text answer (no tools).
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text=(
                        "Give your best final answer now in plain text, based on what "
                        "you found. If you could NOT find the requested data, tell the "
                        "user plainly that it is not tracked in the system. Do NOT say "
                        "you couldn't complete the request."
                    )
                )
            ],
        )
    )
    synth_ok = True
    try:
        final = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0),
        )
        answer = (final.text or "").strip()
    except Exception as exc:
        log_interaction(question, sql_used, last_row_count, error=str(exc))
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
