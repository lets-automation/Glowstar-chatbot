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
from app.agent.postprocess import looks_like_data_table
from app.config import settings
from app.core.logging_util import log_interaction, log_provider_error


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


# LM Studio compiles the tool schemas into a sampling grammar and cannot handle
# a UNION type ("type": ["number", "string"]). It answers HTTP 500
#   NotImplemented: map: filter-mapping not implemented
# which surfaces as a 400 and kills the whole turn before a single tool runs —
# show_dashboard has three such unions, so EVERY question failed, not just
# dashboard ones. Remote providers accept unions, so the rewrite below is scoped
# to the engines that need it rather than changing the shared tool specs.
_UNION_INTOLERANT = {"lmstudio"}


def _collapse_union_types(node):
    """Recursively rewrite {"type": [a, b]} to a single type.

    Collapses to "string": any value can be expressed as one, and nothing is
    lost downstream because widget.py coerces on the way in (chart values via
    float(x), labels and tile values via str(x)).
    """
    if isinstance(node, dict):
        return {
            k: ("string" if "string" in v else (v[0] if v else "string"))
            if k == "type" and isinstance(v, list)
            else _collapse_union_types(v)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_collapse_union_types(x) for x in node]
    return node


def _tools_for_provider():
    """The tool specs, adjusted for engines that reject parts of JSON Schema."""
    if settings.LLM_PROVIDER.lower() in _UNION_INTOLERANT:
        return _collapse_union_types(_GROQ_TOOLS)
    return _GROQ_TOOLS


# Providers that speak the OpenAI dialect and therefore reuse this whole
# backend — only the base_url and key differ. They are reached with the real
# OpenAI SDK, NOT the Groq client: the Groq SDK hardcodes Groq's "/openai/v1/…"
# request path and would 404 against them. The OpenAI client honours base_url
# and exposes the identical chat.completions.create surface used below.
#   provider -> (base_url attr, api-key attr, key-name for the error message)
# A blank key-name means no key is needed (local Ollama / LM Studio).
_OPENAI_COMPATIBLE = {
    "ollama":   ("OLLAMA_BASE_URL",   None,                ""),
    "lmstudio": ("LMSTUDIO_BASE_URL", None,                ""),
    "cerebras": ("CEREBRAS_BASE_URL", "CEREBRAS_API_KEY",  "CEREBRAS_API_KEY"),
    "nvidia":   ("NVIDIA_BASE_URL",   "NVIDIA_API_KEY",    "NVIDIA_API_KEY"),
}


def _client():
    provider = settings.LLM_PROVIDER.lower()
    spec = _OPENAI_COMPATIBLE.get(provider)
    if spec:
        from openai import OpenAI

        base_attr, key_attr, key_name = spec
        key = getattr(settings, key_attr) if key_attr else provider
        if key_name and not key:
            raise RuntimeError(f"{key_name} is not set in .env.")
        return OpenAI(api_key=key, base_url=getattr(settings, base_attr))
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

# REPORT = DETAIL ROWS guard (client-flagged bug): the user asked for a
# "report" but the model answered with a GROUP BY aggregate ("Top 10 kapans by
# damage count") instead of the detail listing with joined names the rules
# mandate. Prompt rules alone did not stop weak models, so this is enforced
# deterministically: report-intent question + aggregated final query -> one
# corrective round. Summary-intent words exempt (an explicitly-asked summary
# may aggregate).
REPORT_ASKED_RE = re.compile(r"\breports?\b", re.IGNORECASE)
_SUMMARY_INTENT_RE = re.compile(
    r"\b(summar(y|ies|ise|ize)|total|count|how many|average|avg|trend|"
    r"overview|analytics?|dashboards?|charts?|graphs?)\b",
    re.IGNORECASE,
)

REPORT_DETAIL_NUDGE = (
    "The user asked for a REPORT. In this system a report ALWAYS means the "
    "DETAIL listing - one row per record - NEVER a GROUP BY summary, and never "
    "a 'Top N' ranking they didn't ask for. Your last query AGGREGATED. Re-run "
    "ONE corrected query that lists the individual records with human-readable "
    "columns: JOIN tblEmployee on the numeric emp id for EmployeeName + "
    "DepartMentName where the table has one; show KapanName and PacketNo, "
    "never raw IDs. 'X wise' means ORDER BY that column (kapan wise = ORDER BY "
    "KapanName), NOT GROUP BY. Then present the first ~30 rows as a Markdown "
    "table and tell the user the full data is in the Excel/PDF download. "
    "Aggregate ONLY if the user explicitly asked for totals or a summary."
)


def _all_sql_aggregated(sql_used: list[str]) -> bool:
    """True if EVERY executed query was a GROUP BY aggregate - i.e. the model
    never pulled the detail rows at all. (Checking only the LAST query would
    false-positive on the good pattern 'detail query, then a small total for
    the headline'.)"""
    return bool(sql_used) and all("group by" in s.lower() for s in sql_used)


# How many times, in ONE turn, we force a stalled model to actually run its
# query before giving up. Weak models (e.g. llama-4-scout) sometimes ignore the
# first push, so we allow a second.
_MAX_EXECUTE_NUDGES = 2

# Output budget per model call. 1024 was too small for the mandated answer
# format (intro + ~30-row preview table + conclusion + download pointer +
# SUGGESTIONS) and cut listing answers off mid-table. 2048 fits it while
# staying inside the free tier's tokens-per-minute budget. Overridable via
# LLM_MAX_TOKENS because reasoning models (Gemma 4 in LM Studio) spend part of
# this budget on hidden thinking, leaving too little for the answer itself.
_MAX_TOKENS = settings.LLM_MAX_TOKENS

# Shown to the model when it presents data (a table, figures, or written-out
# SQL) without having called run_sql. Generalises the old "you wrote SQL" nudge
# so it ALSO catches a fabricated Markdown table that contains no literal SELECT
# — the exact failure that let "packet report for kapan AA" fall through to the
# canned refusal.
_EXECUTE_NUDGE = (
    "You presented data (a table, figures, or a query) but you did NOT call "
    "run_sql, so nothing you showed is real. You MUST call the run_sql tool "
    "NOW to fetch the actual rows from the database, then answer ONLY from the "
    "rows it returns. If you already wrote a SQL query, run that EXACT query "
    "(do not rewrite or simplify it). Never put a data table, chart, or numbers "
    "in your reply without running run_sql first. If the query genuinely "
    "returns no rows, say so plainly."
)


def _has_data_visual(widgets: list[dict]) -> bool:
    """True if a chart/dashboard was emitted — it presents numbers like a table,
    so an ungrounded one is as fabricated as an invented table."""
    return any((w or {}).get("kind") in ("chart", "dashboard") for w in widgets)


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

    execute_nudges = 0         # how many times we've forced a stalled model to run its SQL
    nudged_report_detail = False  # one corrective round if a "report" came back aggregated
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
                    tools=_tools_for_provider(),
                    tool_choice=choice,
                    temperature=0,  # deterministic: same question -> same SQL, no drift
                    max_tokens=_MAX_TOKENS,
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
            # Classify + log the real cause (dead model / auth / rate-limit /
            # connection) and return the message that points at the RIGHT fix,
            # instead of always blaming the user's phrasing.
            pe = log_provider_error(settings.LLM_PROVIDER, model, exc)
            # ok=False: the turn failed (no real answer), so the UI must not
            # offer export even though some SQL may have run before the failure.
            return {
                "answer": pe.user_message,
                "sql_used": sql_used,
                "rows_returned": last_row_count,
                "ok": False,
            }

        msg = response.choices[0].message

        if not msg.tool_calls:
            answer = msg.content or ""
            # Honesty on output-length truncation: finish_reason "length" means
            # the answer was cut mid-generation - never return a silently
            # sliced table as if it were the whole answer.
            if response.choices[0].finish_reason == "length" and answer:
                answer = answer.rstrip() + (
                    "\n\n_(The written answer was shortened for length - the "
                    "complete data is in the Excel/PDF download below.)_"
                    if data_rows
                    else "\n\n_(The answer was shortened for length - ask a "
                    "narrower question for the rest.)_"
                )
            # Grounding guard: the model returned a data TABLE, a chart/dashboard,
            # or written-out SQL but ran NO query (and this isn't a file-only
            # answer) — so nothing it shows is real. Force an actual run_sql round
            # rather than letting the fabrication fall through to the "ungrounded"
            # refusal the user sees ("I couldn't pull that…"). This catches the
            # common weak-model quirk where it prints a clean Markdown table with
            # no literal SELECT text, which the old SQL-text-only check missed.
            # Fires up to _MAX_EXECUTE_NUDGES times (weak models may need a second
            # push); force_tool makes the next request require a tool call.
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
                # Drop any fabricated widget from this stalled round so it can't
                # be shown; the forced round rebuilds it from real rows.
                widgets = [w for w in widgets if not _has_data_visual([w])]
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": _EXECUTE_NUDGE})
                emit("Running the query…")
                continue
            # Report-detail guard (client-flagged): "…report…" question answered
            # with a GROUP BY aggregate instead of the mandated detail listing
            # with joined names. One corrective round, unless the user actually
            # asked for a summary.
            if (
                not nudged_report_detail
                and not file_grounded
                and _all_sql_aggregated(sql_used)
                and REPORT_ASKED_RE.search(question or "")
                and not _SUMMARY_INTENT_RE.search(question or "")
            ):
                nudged_report_detail = True
                force_tool = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": REPORT_DETAIL_NUDGE})
                emit("Building the detailed report…")
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
                    # Keep the structured args too, so the export can rebuild the
                    # FULL dashboard (all KPIs + every section), not just one table.
                    widgets.append({"title": args.get("title", "dashboard"), "code": code, "kind": "dashboard", "data": args})
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
                # sees a sample) so export is the exact, complete data. The
                # LARGEST result wins: don't let a smaller aggregate/breakdown the
                # model runs AFTERWARDS clobber the detail listing — the download
                # must be the full list (e.g. all 3,200 packets of a kapan
                # report), not the 12-row monthly breakdown or 1-row "summary at
                # a glance" queried after it for the prose/dashboard.
                if (
                    tc.function.name == "run_sql"
                    and rows_full
                    and len(rows_full) > len(data_rows)
                ):
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
            model=model, messages=messages, temperature=0, max_tokens=_MAX_TOKENS
        )
        answer = (final.choices[0].message.content or "").strip()
    except Exception as exc:
        log_interaction(question, sql_used, last_row_count, error=str(exc))
        answer = ""
        synth_ok = False  # couldn't form the final answer -> suppress export

    log_interaction(question, sql_used, last_row_count)
    return {
        # Never claim "no data" while holding rows: when the write-up call fails
        # (e.g. provider quota) AFTER the query succeeded, say so honestly - the
        # UI then renders the captured rows as a table instead of a false denial.
        "answer": answer or (
            "I fetched the data but couldn't write the summary just now - here it is."
            if data_rows else "I don't have that information in the database."
        ),
        "sql_used": sql_used,
        "rows_returned": last_row_count,
        "widgets": widgets,
        "ok": synth_ok,
        "data_columns": data_columns,
        "data_rows": data_rows,
        "file_grounded": file_grounded,
    }
