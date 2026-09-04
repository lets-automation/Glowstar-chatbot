"""
groq_backend.py
---------------
Runs the agent using Groq (OpenAI-compatible tool calling).
Used when LLM_PROVIDER=groq (the free-tier testing setup).
"""

import json
import re

from app.agent import attachments as attachments_mod
from app.agent import context_budget
from app.agent import loop_policy as policy
from app.agent import result_capture, tools, widget
from app.agent._retry import call_with_retry
from app.agent.postprocess import asserts_a_figure, looks_like_data_table
from app.config import settings
from app.core import cost_trace
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


# Every provider this backend serves speaks the OpenAI dialect — only the
# base_url and key differ. All of them are reached with the real OpenAI SDK,
# which honours base_url and exposes the chat.completions.create surface used
# below. (The native Groq SDK could not serve the others even if we wanted it
# to: it hardcodes Groq's own "/openai/v1/…" request path and 404s elsewhere.)
#   provider -> (base_url attr, api-key attr, key-name for the error message)
# A blank key-name means no key is needed (local Ollama / LM Studio).
#
# GROQ IS IN THIS MAP TOO, and is reached through Groq's own OpenAI-compatible
# endpoint (https://api.groq.com/openai/v1) rather than the native groq SDK.
#
# Why: cost tracking. AgentCost patches the openai / anthropic / google-genai
# client libraries; NO version of it patches the native groq client, so every
# Groq turn was invisible on the dashboard - the one provider that could never
# be costed. Routing it through the OpenAI client fixes that and deletes a
# special case at the same time.
#
# Verified live before switching (2026-08-06): identical tool-calling behaviour
# through this path - the model returned run_sql with correct SQL, usage came
# back as 566 in / 20 out, and AgentCost recorded and delivered the event. The
# only surface this backend uses is chat.completions.create(tools=...), which
# both clients implement the same way.
_OPENAI_COMPATIBLE = {
    "groq":     ("GROQ_BASE_URL",     "GROQ_API_KEY",      "GROQ_API_KEY"),
    "ollama":   ("OLLAMA_BASE_URL",   None,                ""),
    "lmstudio": ("LMSTUDIO_BASE_URL", None,                ""),
    "cerebras": ("CEREBRAS_BASE_URL", "CEREBRAS_API_KEY",  "CEREBRAS_API_KEY"),
    "nvidia":   ("NVIDIA_BASE_URL",   "NVIDIA_API_KEY",    "NVIDIA_API_KEY"),
    "openrouter": ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
    "kimi":     ("KIMI_BASE_URL",     "KIMI_API_KEY",      "KIMI_API_KEY"),
}


def _client():
    """The OpenAI-dialect client for whichever provider is configured.

    Every provider this backend serves now goes through the OpenAI SDK, so there
    is no longer a native-groq fallback branch. An unknown provider still lands
    here (agent.ask routes anything unrecognised to this backend), so it is
    treated as Groq - which is what the old fallback did.
    """
    from openai import OpenAI

    provider = settings.LLM_PROVIDER.lower()
    base_attr, key_attr, key_name = _OPENAI_COMPATIBLE.get(
        provider, _OPENAI_COMPATIBLE["groq"]
    )
    key = getattr(settings, key_attr) if key_attr else provider
    if key_name and not key:
        raise RuntimeError(f"{key_name} is not set in .env.")
    return OpenAI(api_key=key, base_url=getattr(settings, base_attr))












# Output budget per model call — resolved PER PROVIDER at call time, because
# this one backend serves groq, cerebras, nvidia, ollama and lmstudio, whose
# real budgets differ by 4x. It was a single module-level constant baked from
# LLM_MAX_TOKENS (2048, tuned for Groq's tight 12k TPM tier), so Cerebras and
# NVIDIA were being held to Groq's limit for no reason — and 2048 cannot fit the
# answer format the RULES mandate (a 30-row preview table alone is ~1.2-2k
# tokens), which is a direct cause of answers truncating mid-table. See
# settings.max_output_tokens(). LLM_MAX_TOKENS in .env still overrides.
def _max_tokens() -> int:
    return settings.max_output_tokens()


# Compaction POLICY now lives in app/agent/context_budget.py so that every
# backend gets it - it used to live here, which meant it protected Groq and left
# gemini_backend (the production provider) and anthropic_backend with none.
#
# Re-exported under the original names: this module's callers and
# tests/test_context_compaction.py both import them from here.
_CHARS_PER_TOKEN = context_budget.CHARS_PER_TOKEN
_COMPACT_ABOVE_TOKENS = context_budget.COMPACT_ABOVE_TOKENS
_KEEP_FULL_TOOL_RESULTS = context_budget.KEEP_FULL_TOOL_RESULTS
_trimmed_note = context_budget.trimmed_note


def _compact_history(messages: list[dict]) -> None:
    """Shrink old tool results in place so a long report cannot overflow.

    OpenAI dialect: tool results are `role: tool` messages, and every
    tool_call_id must keep a matching reply - so content may shrink, but a
    message may never be removed. The policy (budget, ordering, what is worth
    trimming) is shared - see app/agent/context_budget.py.

    MEASURE THE CONVERSATION, NOT THE SYSTEM PROMPT. messages[0] is the system
    prompt at ~20k tokens; counting it meant the threshold was passed before the
    user's question was appended and compaction ran on every round from the
    first. It is fixed overhead that sits ALONGSIDE the conversation.
    """
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    tool_texts = [str(messages[i].get("content") or "") for i in tool_idx]
    other_chars = sum(
        len(str(m.get("content") or ""))
        for m in messages
        if m.get("role") not in ("system", "tool")
    )
    for k, note in context_budget.plan_trims(tool_texts, other_chars).items():
        messages[tool_idx[k]]["content"] = note


def _extra_body() -> dict:
    """Provider-specific request extras.

    Qwen3.x is a REASONING model: it deliberates before answering and pays for
    that deliberation out of the SAME max_tokens budget. Measured on
    Qwen3.5-9B via vLLM (2026-08-20): one trivial prompt burned 300 completion
    tokens thinking and never produced an answer, versus 30 tokens answering
    correctly with thinking disabled. On a department report the write-up round
    ran out mid-thought, so the user got raw monologue and a dumped table
    instead of a report.

    Qwen's chat template understands enable_thinking=False and vLLM forwards
    chat_template_kwargs to it. Gated behind LLM_DISABLE_THINKING because other
    providers reject unknown request fields outright - a 400 on every call is a
    worse failure than a verbose answer.

    DEFAULT IT OFF. Disabling thinking looked like a clean win (fast, no
    truncation) and was measured to be a REGRESSION on anything multi-step: the
    same MFG-1 department report then summarised its own 9-row preview sample as
    the totals - it reported 9 packets where the database holds 381 - and
    dropped the damage, bonus and incentive sections entirely. Thinking is what
    plans a multi-section report.

    The real fix for truncation is BUDGET, not silence: thinking ON with
    LLM_MAX_TOKENS=16384 produced the correct 381/405 figures, all sections, and
    the same ~34s. Only set LLM_DISABLE_THINKING=true for a provider whose
    context genuinely cannot fit reasoning plus the answer.
    """
    if settings.LLM_DISABLE_THINKING:
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {}


# NOTE: this module used to REASSIGN policy.EXECUTE_NUDGE here at import time,
# with a byte-identical copy of the string already defined in loop_policy.py.
# Harmless in effect, but it was a provider module reaching in and mutating
# shared policy for all three backends — exactly the coupling loop_policy.py was
# extracted to remove, and a trap for anyone who later edited one copy. Removed;
# policy.EXECUTE_NUDGE is used directly below.


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
            # Core visual rules in front (byte-stable, so any prefix cache
            # covers them); the show_widget design system only when this question
            # actually asks for a custom visual, and then DEAD LAST - behind the
            # per-question schema, never in front of it.
            "content": widget.WIDGET_CORE_PROMPT
            + "\n\n"
            + tools.system_prompt_for(routing_text)
            + widget.visual_prompt_for(routing_text),
        },
        *history,
        {"role": "user", "content": _user_content(question, file_context)},
    ]

    sql_used: list[str] = []
    last_row_count = 0
    widgets: list[dict] = []  # visuals emitted via show_widget, shown to the user
    data_columns: list[str] = []  # columns/rows from the LAST successful run_sql,
    data_rows: list[dict] = []
    data_sections: list[dict] = []  # every result, for a multi-sheet export

    execute_nudges = 0         # how many times we've forced a stalled model to run its SQL
    nudged_report_detail = False  # one corrective round if a "report" came back aggregated
    nudged_entity_report = False  # one corrective round if a 'report of X' was just the WHO row
    nudged_dashboard = False   # have we already asked it to build the requested dashboard?
    force_tool = False         # require a tool call on the NEXT request (set by the nudge)
    # THE OUTPUT RESERVATION IS PART OF THE CONTEXT BUDGET, so it has to be able
    # to give ground. Measured live 2026-08-31 on Qwen3-30B-A3B (65,536 ctx):
    # a Gujlish department report reached 49,153 input tokens and the request
    # asked for 16,384 output - 65,537 total, ONE token over, and the whole turn
    # died with "That request was too large". Compaction had already run; the
    # two newest tool results are exempt by design (KEEP_FULL_TOOL_RESULTS) and
    # they were 829-row x 13-column dumps. Halving the reservation would have
    # fitted the same conversation with 8k to spare.
    output_cap = _max_tokens()
    output_squeezes = 0
    writeup_sent = False       # the answer-formatting rules go out WITH the data
    dashboard_built = False    # did show_dashboard actually render this turn?
    retried_bad_tool_call = False  # one retry when Groq rejects a tool call's arguments

    # Two SEPARATE budgets (see tools.MAX_CORRECTION_ROUNDS). tool_rounds counts
    # only rounds that actually ran tools; corrections counts nudges/retries.
    # They used to share one counter, so pushing a stalled model back on track
    # cost it the very rounds it needed to finish the job.
    tool_rounds = 0
    corrections = 0

    emit("Analyzing your question…")
    while (
        tool_rounds < tools.MAX_TOOL_ROUNDS
        and tool_rounds + corrections < tools.MAX_TOTAL_ROUNDS
    ):
        # Before every provider call, not just at the end: the overflow happens
        # ON a call, so trimming afterwards would be too late.
        _compact_history(messages)
        try:
            choice = "required" if force_tool else "auto"
            force_tool = False  # one-shot
            # One "plan" span per round of the loop. Every round is named the
            # same on purpose - the SDK numbers them with step_index, so the
            # dashboard shows five separate planning rounds rather than one
            # merged blob, which is what tells a genuinely multi-query question
            # apart from a model that stalled and had to be nudged. The span
            # covers call_with_retry, so a retried round shows its retries too.
            with cost_trace.step("plan"):
                response = call_with_retry(
                    lambda: client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=_tools_for_provider(),
                        tool_choice=choice,
                        temperature=0,  # deterministic: same question -> same SQL, no drift
                        max_tokens=output_cap,
                        extra_body=_extra_body(),
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
                corrections += 1
                emit("Retrying…")
                continue
            # A CONTEXT OVERFLOW IS RECOVERABLE - give back output room.
            # The reservation is ours to shrink; the conversation is not. Two
            # halvings take 16,384 -> 4,096 and buy 12k of input, which covers
            # the wide-result reports that overflow. If it still does not fit,
            # fall through to the normal provider-error path.
            if ("maximum context length" in err or "context_length_exceeded" in err
                    or "reduce the length" in err) and output_squeezes < 2:
                output_squeezes += 1
                output_cap = max(2048, output_cap // 2)
                from app.core.logging_util import logger

                logger.warning(
                    "CONTEXT-SQUEEZE | output budget -> %s (attempt %s) | q=%r",
                    output_cap, output_squeezes, (question or "")[:80])
                _compact_history(messages)
                corrections += 1
                emit("Trimming the working set…")
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

        # An OpenAI-compatible provider can return an EMPTY choices list. It is
        # a valid HTTP 200, so no exception is raised until choices[0] raises
        # IndexError and kills the whole turn - the user sees a server error
        # after waiting through every query. Seen live on nvidia/gpt-oss-20b.
        # Treat it as a round that produced nothing and let the loop continue:
        # the data gathered so far is preserved, and the end-of-loop write-up
        # still runs.
        if not response.choices:
            log_provider_error(
                settings.LLM_PROVIDER, model,
                RuntimeError("provider returned no choices"),
            )
            # A dead round, not a query round. This is the only correction that
            # can REPEAT (the nudges are one-shot), so it checks the budget
            # itself; break falls through to the write-up, keeping the data.
            corrections += 1
            if corrections >= tools.MAX_CORRECTION_ROUNDS:
                break
            continue

        msg = response.choices[0].message

        if not msg.tool_calls:
            answer = msg.content or ""

            # The model stopped calling tools but wrote NOTHING. Returning here
            # hands back a blank answer, and the forced write-up further down
            # (which asks it plainly for the final text) never runs because that
            # only happens when the loop exhausts its rounds.
            #
            # This is the employee-360 failure: "report of employee M4117 for
            # June 2026" gathered 32 rows across 2 queries and then produced no
            # prose at all, so the user got a bare table under "I fetched the
            # data but couldn't write the summary".
            #
            # WITH data, breaking out is right: the write-up call has material.
            # With NO data it is not - breaking on the very first empty round
            # ended the turn having run zero queries, and the turn then reported
            # "I don't have that information in the database" about an employee
            # who plainly exists. Nudge it to actually run the query instead,
            # bounded by the same counter the fabrication guard uses.
            if not answer.strip():
                if data_rows:
                    break
                if execute_nudges < policy.MAX_EXECUTE_NUDGES:
                    execute_nudges += 1
                    force_tool = True
                    messages.append({"role": "user", "content": policy.EXECUTE_NUDGE})
                    corrections += 1
                    emit("Running the query…")
                    continue
                break

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
            # Fires up to policy.MAX_EXECUTE_NUDGES times (weak models may need a second
            # push); force_tool makes the next request require a tool call.
            ungrounded_fabrication = (
                not sql_used
                and not file_grounded
                and (
                    policy.looks_like_unrun_sql(answer)
                    or looks_like_data_table(answer)
                    or policy.has_data_visual(widgets)
                    # A FIGURE IN PROSE IS AS UNGROUNDED AS ONE IN A TABLE.
                    # Measured 2026-08-31 on Qwen3-30B-A3B via vLLM: given the
                    # real 19,577-token system prompt it returned finish=stop
                    # with NO tool call on every question, and wrote sentences
                    # like "Total packets currently on jangad: 140,276" and
                    # "7,321 packets" - the latter lifted straight out of the
                    # glossary's own worked example, where the live answer is
                    # 7,591. Bisected: the same model tool-calls correctly with
                    # the schema block, the notes block, or a short prompt, and
                    # with tool_choice="required" even at full length - so the
                    # cure is to FORCE the round, which is what this branch
                    # does. Neither of those answers is a Markdown table, so
                    # every trigger above missed them and the turn was lost.
                    or asserts_a_figure(answer)
                )
            )
            if ungrounded_fabrication and execute_nudges < policy.MAX_EXECUTE_NUDGES:
                execute_nudges += 1
                force_tool = True
                # Drop any fabricated widget from this stalled round so it can't
                # be shown; the forced round rebuilds it from real rows.
                widgets = [w for w in widgets if not policy.has_data_visual([w])]
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": policy.EXECUTE_NUDGE})
                corrections += 1
                emit("Running the query…")
                continue
            # Report-detail guard (client-flagged): "…report…" question answered
            # with a GROUP BY aggregate instead of the mandated detail listing
            # with joined names. One corrective round, unless the user actually
            # asked for a summary.
            if (
                not nudged_report_detail
                and not file_grounded
                and policy.all_sql_aggregated(sql_used)
                and policy.REPORT_ASKED_RE.search(question or "")
                and not policy.SUMMARY_INTENT_RE.search(question or "")
            ):
                nudged_report_detail = True
                force_tool = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": policy.REPORT_DETAIL_NUDGE})
                corrections += 1
                emit("Building the detailed report…")
                continue
            # Thin entity report: "report of <entity>" answered with only the
            # WHO row. The client asked for a full report of employee M4167 and
            # got a one-row identity record - name, code, department - which is
            # section 1 of several, and the Excel download was that single row.
            if (
                not nudged_entity_report
                and not file_grounded
                and sql_used
                and policy.thin_entity_report(question, data_sections)
            ):
                nudged_entity_report = True
                force_tool = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": policy.ENTITY_REPORT_NUDGE})
                corrections += 1
                emit("Building the full profile…")
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
                and policy.DASHBOARD_ASKED_RE.search(question or "")
            ):
                nudged_dashboard = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": policy.DASHBOARD_NUDGE})
                corrections += 1
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
        "data_sections": data_sections,
                "file_grounded": file_grounded,
            }

        # This round is REAL WORK: the model asked for tools. Only these
        # count against the query budget (see tools.MAX_CORRECTION_ROUNDS).
        tool_rounds += 1

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
            result_text, sql, row_count, cols_full, rows_full, tool_sections = tools.run_tool(tc.function.name, args)
            if sql:
                sql_used.append(sql)
                last_row_count = row_count
                # Capture the FULL rows from a successful run_sql (the model only
                # sees a sample) so export is the exact, complete data. Which
                # result counts as "the answer" is decided by result_capture -
                # one rule, shared by every backend, tested against both the bugs
                # it fixes (a lookup shown as the report; a summary clobbering a
                # detail listing).
                # Any tool that returned rows, not just run_sql: a report recipe
                # (department_report) also produces the rows behind the answer,
                # and gating on the tool NAME left data_rows empty for it - so
                # the UI's "offer a download" condition never fired and a
                # perfectly good 8-section report came with no Excel at all.
                if cols_full and rows_full and result_capture.better(
                    cols_full, rows_full, data_columns, data_rows
                ):
                    data_columns, data_rows = cols_full, rows_full
                    # Only when the tool did NOT return named sections. A recipe
                    # returns its own titled ones just below, and adding this
                    # untitled copy first made the titled version look like a
                    # duplicate - so the workbook's first sheet lost its name
                    # ("Code-Worker" instead of "Workforce").
                    if not tool_sections:
                        result_capture.add_section(data_sections, cols_full, rows_full)
            # A report recipe returns SEVERAL named results from one call. Each
            # becomes its own titled sheet, so the workbook carries the whole
            # report rather than only its widest table.
            for sec in tool_sections:
                result_capture.add_section(
                    data_sections, sec["columns"], sec["rows"], title=sec.get("title")
                )
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result_text}
            )

        # THE WRITE-UP RULES ARRIVE NOW, WITH THE FIRST REAL RESULT.
        # Held out of the system prompt because they suppress tool calling
        # outright - see tools._split_writeup for the measurements. Sent once,
        # only when a tool has actually returned something, so the model has
        # them in hand before it composes anything and never while it is still
        # deciding whether to fetch.
        if not writeup_sent and sql_used:
            writeup_sent = True
            messages.append({"role": "user", "content": tools.WRITEUP_RULES})

    # Hit the step limit -> force a final plain-text answer from what we have,
    # WITHOUT tools (so it can't loop further).
    messages.append(
        {
            "role": "user",
            "content": policy.WRITE_UP_PROMPT,
        }
    )
    synth_ok = True
    try:
        # The write-up is its own step: it is the single most expensive call of
        # the turn (it renders the row preview) and the one most likely to be
        # refused on a per-minute cap, so it is worth costing separately from
        # the planning rounds rather than averaged in with them.
        with cost_trace.step("write-up"):
            final = client.chat.completions.create(
                model=model, messages=messages, temperature=0,
                max_tokens=_max_tokens(), extra_body=_extra_body(),
            )
        # Same empty-choices guard as the tool loop: a 200 with no choices must
        # not become an IndexError after every query has already run.
        answer = (
            (final.choices[0].message.content or "").strip()
            if final.choices else ""
        )
    except Exception as exc:
        log_interaction(question, sql_used, last_row_count, error=str(exc))
        answer = ""
        synth_ok = False  # couldn't form the final answer -> suppress export

    log_interaction(question, sql_used, last_row_count)
    return {
        # Never claim "no data" while holding rows: when the write-up call fails
        # (e.g. provider quota) AFTER the query succeeded, say so honestly - the
        # UI then renders the captured rows as a table instead of a false denial.
        # Three different situations, three different truths. Saying "I don't
        # have that information in the database" when NO query ever ran is a
        # false denial - it tells the user their data is missing when in fact we
        # never looked. Observed on "report of employee M4117", an employee who
        # plainly exists.
        "answer": answer or (
            "I fetched the data but couldn't write the summary just now - here it is."
            if data_rows
            else "I don't have that information in the database."
            if sql_used  # we DID query and it genuinely came back empty
            else "I couldn't complete that just now - please ask again."
        ),
        "sql_used": sql_used,
        "rows_returned": last_row_count,
        "widgets": widgets,
        "ok": synth_ok,
        "data_columns": data_columns,
        "data_rows": data_rows,
        "data_sections": data_sections,
        "file_grounded": file_grounded,
    }
