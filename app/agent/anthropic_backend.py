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
# Shared grounding/nudge machinery (defined once in the groq backend, used by
# gemini too) so ALL providers refuse to present unqueried data — the demo
# provider must not be the only one missing the guard.
from app.agent.groq_backend import (
    DASHBOARD_ASKED_RE,
    DASHBOARD_NUDGE,
    REPORT_ASKED_RE,
    REPORT_DETAIL_NUDGE,
    _EXECUTE_NUDGE,
    _all_sql_aggregated,
    _MAX_EXECUTE_NUDGES,
    _SUMMARY_INTENT_RE,
    _has_data_visual,
    _looks_like_unrun_sql,
)
from app.agent.postprocess import looks_like_data_table
from app.config import settings
from app.core.logging_util import log_interaction

# Output budget per model call. 1024 was too small: the mandated answer format
# (intro + ~30-row Markdown preview table + conclusion + download pointer +
# SUGGESTIONS) routinely exceeds it, which cut answers off mid-table with no
# warning. Tool-selection rounds rarely need this much, but a single generous
# cap is simpler and Claude only bills tokens actually generated.
_MAX_TOKENS = 4096


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
            # Cached too: the schema block is the LARGEST prompt part (~20k+
            # tokens with SCHEMA_MAX_COLS=0) and is identical across the 2-4
            # tool rounds of one question - without this it was re-billed at
            # full price every round. (It varies per question, so cross-question
            # reuse is limited, but within-question reuse is where the money is.)
            "cache_control": {"type": "ephemeral"},
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

    execute_nudges = 0        # forced run-the-query rounds used (grounding guard)
    nudged_report_detail = False  # one corrective round if a "report" came back aggregated
    nudged_dashboard = False  # one corrective round if a requested dashboard was skipped
    force_tool = False        # require a tool call on the NEXT request (set by the nudge)
    dashboard_built = False   # did show_dashboard actually render this turn?

    for _ in range(tools.MAX_TOOL_ROUNDS):
        try:
            choice = {"type": "any"} if force_tool else {"type": "auto"}
            force_tool = False  # one-shot
            response = call_with_retry(
                lambda: client.messages.create(
                    model=model,
                    max_tokens=_MAX_TOKENS,
                    system=system,
                    tools=_ANTHROPIC_TOOLS,
                    tool_choice=choice,
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
            # Grounding guard (parity with groq/gemini): a data table, chart/
            # dashboard, or written-out SQL with NO query behind it is invented.
            # Force an actual run_sql round instead of returning it.
            ungrounded_fabrication = (
                not sql_used
                and not file_grounded
                and (
                    _looks_like_unrun_sql(answer)
                    or looks_like_data_table(answer)
                    or _has_data_visual(widgets)
                )
            )
            if ungrounded_fabrication and execute_nudges < _MAX_EXECUTE_NUDGES:
                execute_nudges += 1
                force_tool = True
                widgets = [w for w in widgets if not _has_data_visual([w])]
                messages.append({"role": "user", "content": _EXECUTE_NUDGE})
                emit("Running the query…")
                continue
            # Report-detail guard (client-flagged): "…report…" answered with a
            # GROUP BY aggregate instead of the detail listing with joined names.
            if (
                not nudged_report_detail
                and not file_grounded
                and _all_sql_aggregated(sql_used)
                and REPORT_ASKED_RE.search(question or "")
                and not _SUMMARY_INTENT_RE.search(question or "")
            ):
                nudged_report_detail = True
                force_tool = True
                messages.append({"role": "user", "content": REPORT_DETAIL_NUDGE})
                emit("Building the detailed report…")
                continue
            # Dashboard guard (parity with groq/gemini): the question asked for
            # analytics/overview but no dashboard was built - one corrective round.
            if (
                not dashboard_built
                and not nudged_dashboard
                and sql_used
                and not file_grounded
                and DASHBOARD_ASKED_RE.search(question or "")
            ):
                nudged_dashboard = True
                messages.append({"role": "user", "content": DASHBOARD_NUDGE})
                emit("Building your dashboard…")
                continue
            # Honesty on output-length truncation: a max_tokens stop means the
            # answer was cut mid-generation. Never return a silently sliced
            # table as if it were the whole answer.
            if response.stop_reason == "max_tokens":
                answer = answer.rstrip() + (
                    "\n\n_(The written answer was shortened for length - the "
                    "complete data is in the Excel/PDF download below.)_"
                    if data_rows
                    else "\n\n_(The answer was shortened for length - ask a "
                    "narrower question for the rest.)_"
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
                    # Keep the structured args too, so the export can rebuild the
                    # FULL dashboard (all KPIs + every section), not just one table.
                    widgets.append(
                        {"title": (block.input or {}).get("title", "dashboard"), "code": code,
                         "kind": "dashboard", "data": block.input or {}}
                    )
                    outcome = "rendered"
                    dashboard_built = True
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
                # LARGEST result wins for the export capture; a smaller
                # aggregate/breakdown run afterwards must not clobber the full
                # detail list (see groq_backend — the kapan-report download bug).
                if (
                    block.name == "run_sql"
                    and rows_full
                    and len(rows_full) > len(data_rows)
                ):
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
            model=model, max_tokens=_MAX_TOKENS, system=system, messages=messages, temperature=0
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
