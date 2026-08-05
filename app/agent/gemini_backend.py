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
from functools import lru_cache

from google import genai
from google.genai import types

from app.agent import attachments as attachments_mod
from app.agent import loop_policy as policy
from app.agent import result_capture, tools, widget
from app.config import settings
from app.core.logging_util import log_interaction, log_provider_error


# (model, key) pairs the free tier has already rejected today. Skipped on later
# turns so a dead combination can't keep costing every request a failed attempt.
# Cleared on restart — the daily quota resets anyway.
#
# Keyed by MODEL as well as key because the free-tier quota is per model:
# the 429 reports GenerateRequestsPerMinutePerProjectPerModel. Tracking keys
# alone marked a key dead for every model once ONE model ran out.
_EXHAUSTED_KEYS: set[tuple[str, str]] = set()


def _is_quota_error(exc: Exception) -> bool:
    """A 429/quota/permission failure — i.e. try the NEXT key, not a real bug."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(
        s in text
        for s in ("429", "resource_exhausted", "quota", "rate limit",
                  "permission_denied", "403", "api key not valid", "invalid api key")
    )


@lru_cache(maxsize=16)
def _client_for(key: str) -> genai.Client:
    """
    One client per API key, kept alive for the process.

    Cached because mid-turn model rotation builds a client per swap, and the SDK
    shares an underlying HTTP transport between Client objects: when a discarded
    one was garbage-collected it closed that transport for the others, and the
    next call died with "Cannot send a request, as the client has been closed".
    """
    return genai.Client(api_key=key)


def _client(api_key: str | None = None) -> genai.Client:
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env.")
    return _client_for(key)


def _attempts(primary_model: str) -> list[tuple[str, str]]:
    """
    (model, key) pairs to try, in order, skipping combinations already refused.

    MODEL first, key second: the free-tier limit is per project per MODEL, and
    extra keys in the same project share one pool - so moving to the next model
    is what actually recovers capacity. Rotating keys alone was the old
    behaviour and could not finish a single report question.
    """
    fresh, spent = [], []
    for model in settings.gemini_model_chain():
        for key in settings.gemini_keys():
            (spent if (model, key) in _EXHAUSTED_KEYS else fresh).append((model, key))
    # Everything spent -> try again anyway; a per-MINUTE bucket may have refilled.
    return fresh or spent


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
    """
    Answer a question via Gemini, FAILING OVER between configured API keys.

    The free tier allows only ~20 requests/DAY per key, which showed the client
    "the assistant is busy right now" mid-demo. With several keys configured we
    transparently move to the next one on a quota/permission error and remember
    the dead key for the rest of the process, so a demo keeps working.
    """
    attempts = _attempts(model)
    last_exc: Exception | None = None
    for idx, (try_model, key) in enumerate(attempts):
        try:
            return _ask_gemini_once(
                question, try_model, history, on_event, file_context, key
            )
        except Exception as exc:  # noqa: BLE001 - decide by error kind below
            if not _is_quota_error(exc):
                raise  # a real bug: don't burn the other combinations on it
            _EXHAUSTED_KEYS.add((try_model, key))
            last_exc = exc
            log_provider_error("gemini", try_model, exc)
            if idx + 1 < len(attempts) and on_event:
                on_event("Switching to a backup connection…")

    # EVERY key is exhausted. Return the friendly provider message (HTTP 200,
    # ok=False) rather than raising - an escaped exception becomes a 500 and the
    # user sees a server error instead of "try again in a moment".
    pe = log_provider_error("gemini", model, last_exc) if last_exc else None
    return {
        "answer": pe.user_message if pe else "The assistant is unavailable right now.",
        "sql_used": [],
        "rows_returned": 0,
        "ok": False,
    }


def _write_up(contents, system, model, api_key: str | None, on_event=None) -> tuple[str, bool]:
    """
    The final plain-text answer, retried across API keys. Returns (answer, ok).

    Why this is separate from the whole-turn failover in ask_gemini: by the time
    we get here every query has ALREADY run and been paid for. The free tier caps
    requests per MINUTE (limit 5), and one question spends up to MAX_TOOL_ROUNDS
    of them, so the write-up is the call most likely to be the one refused - and
    losing it means the user waited 30 seconds and got a table with no answer,
    which is exactly the failure the client reported on "full report of MFG - 1".

    Re-running the whole turn on a fresh key would re-run every query and spend
    another round-trip budget for a write-up we could get in one call. So rotate
    the key for THIS call only.

    We rotate rather than honour the API's retryDelay (~16s): with several keys a
    rotation is instant, and making a user wait 16 seconds mid-answer is its own
    kind of failure.
    """
    # Start with the model/key that ran the queries (its cache is warm), then
    # fall back across the other MODELS - the per-minute bucket is per model, so
    # a different model is what actually has capacity left.
    tried = [(model, api_key)] if api_key else []
    tried += [pair for pair in _attempts(model) if pair != (model, api_key)]

    for idx, (try_model, key) in enumerate(tried):
        try:
            final = _client(key).models.generate_content(
                model=try_model,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0),
            )
            return (final.text or "").strip(), True
        except Exception as exc:  # noqa: BLE001 - decide by error kind
            log_provider_error("gemini", try_model, exc)
            if not _is_quota_error(exc):
                return "", False        # a real bug: another model won't help
            _EXHAUSTED_KEYS.add((try_model, key))
            if idx + 1 < len(tried) and on_event:
                on_event("Switching to a backup connection…")
    return "", False


def _ask_gemini_once(
    question: str,
    model: str,
    history: list[dict] | None = None,
    on_event=None,
    file_context: dict | None = None,
    api_key: str | None = None,
) -> dict:
    """One attempt with ONE api key (see ask_gemini for the failover wrapper)."""
    client = _client(api_key)
    file_grounded = attachments_mod.grounds_data(file_context)

    def emit(msg):
        if on_event:
            on_event(msg)

    emit("Analyzing your question…")
    routing = tools.routing_text(question, history)
    # ORDER IS BILLING, NOT STYLE. Caching matches a prefix, so every static
    # block goes in front of the per-question schema. The widget prompt used to
    # trail system_prompt_for(), which put 2k of never-changing text behind a
    # per-question boundary where it could never be cached.
    system = (
        widget.WIDGET_SYSTEM_PROMPT
        + "\n\n"
        + tools.system_prompt_for(routing)
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
    data_sections: list[dict] = []  # every result, for a multi-sheet export
    nudged_dashboard = False  # one corrective round if a requested dashboard was skipped
    nudged_report_detail = False  # one corrective round if a "report" came back aggregated
    execute_nudges = 0        # how many times we've forced a stalled model to run its SQL
    dashboard_built = False

    # MID-TURN MODEL ROTATION.
    #
    # The free-tier limit is 5 requests/minute PER MODEL, and one report question
    # spends ~6 model calls - so a single model cannot finish one. Restarting the
    # turn on another model would throw away every query already run (and spend
    # the same budget again), so instead we swap the model/key for the NEXT ROUND
    # and carry the conversation forward untouched: `contents` is just Gemini
    # Content objects, it does not belong to any one model.
    #
    # Rotating models, not keys, is the part that matters: the quota is per
    # project per model, so extra keys in one project share a single pool.
    pairs = [(model, api_key)] + [p for p in _attempts(model) if p != (model, api_key)]
    pair_i = 0
    cur_model, cur_key = pairs[0]

    for _ in range(tools.MAX_TOOL_ROUNDS):
        try:
            # Inner loop so a rotation does NOT consume one of the tool rounds -
            # a swap is a retry of the same step, not a step of its own.
            while True:
                try:
                    resp = client.models.generate_content(
                        model=cur_model, contents=contents, config=config
                    )
                    break
                except Exception as exc:  # noqa: PERF203
                    if not (_is_quota_error(exc) and pair_i + 1 < len(pairs)):
                        raise
                    _EXHAUSTED_KEYS.add((cur_model, cur_key))
                    log_provider_error("gemini", cur_model, exc)
                    pair_i += 1
                    cur_model, cur_key = pairs[pair_i]
                    client = _client(cur_key)
                    emit("Switching to a backup connection…")
        except Exception as exc:
            # Every model/key is spent. Raise only while nothing useful exists,
            # so ask_gemini can report it; mid-answer we keep the partial result
            # rather than redo the work.
            if _is_quota_error(exc) and not sql_used:
                raise
            log_interaction(question, sql_used, last_row_count, error=str(exc))
            # Classify + log the real cause and return the message that points
            # at the right fix (config error vs. transient busy vs. rephrase).
            pe = log_provider_error(settings.LLM_PROVIDER, model, exc)
            return {
                "answer": pe.user_message,
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

            # The model stopped WITHOUT writing anything. Returning here hands
            # back a blank answer and skips the forced write-up below, which only
            # runs when the rounds are exhausted. Same fault, same fix as the
            # groq backend (see the employee-360 case there): with data, break to
            # the write-up; with nothing yet, push it to actually run the query
            # rather than end the turn having queried nothing - that produced
            # "I don't have that information in the database" about an employee
            # who plainly exists.
            if not answer:
                if data_rows:
                    break
                if execute_nudges < policy.MAX_EXECUTE_NUDGES:
                    execute_nudges += 1
                    if cand and cand.content:
                        contents.append(cand.content)
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=policy.EXECUTE_NUDGE)],
                        )
                    )
                    emit("Running the query…")
                    continue
                break
            # Grounding guard (mirrors groq_backend): the model returned a data
            # table, a chart/dashboard, or written-out SQL but ran NO query, so
            # nothing it shows is real. Force a real run_sql round rather than
            # letting the fabrication fall through to the "ungrounded" refusal
            # the user sees. Fires up to policy.MAX_EXECUTE_NUDGES times.
            from app.agent.postprocess import looks_like_data_table
            ungrounded_fabrication = (
                not sql_used
                and not file_grounded
                and (
                    policy.looks_like_unrun_sql(answer)
                    or looks_like_data_table(answer)
                    or policy.has_data_visual(widgets)
                )
            )
            if ungrounded_fabrication and execute_nudges < policy.MAX_EXECUTE_NUDGES:
                execute_nudges += 1
                widgets = [w for w in widgets if not policy.has_data_visual([w])]
                if cand and cand.content:
                    contents.append(cand.content)
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=policy.EXECUTE_NUDGE)],
                    )
                )
                emit("Running the query…")
                continue
            # Report-detail guard (mirrors groq_backend; client-flagged bug):
            # a "…report…" question answered with a GROUP BY aggregate instead
            # of the mandated detail listing with joined names.
            if (
                not nudged_report_detail
                and not file_grounded
                and policy.all_sql_aggregated(sql_used)
                and policy.REPORT_ASKED_RE.search(question or "")
                and not policy.SUMMARY_INTENT_RE.search(question or "")
            ):
                nudged_report_detail = True
                if cand and cand.content:
                    contents.append(cand.content)
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=policy.REPORT_DETAIL_NUDGE)],
                    )
                )
                emit("Building the detailed report…")
                continue
            # Dashboard guard (mirrors groq_backend): the question asked for
            # analytics/overview/dashboard/analysis but no dashboard was built.
            # Nudge one corrective round; requires queried data (sql_used).
            if (
                not dashboard_built
                and not nudged_dashboard
                and sql_used
                and not file_grounded
                and policy.DASHBOARD_ASKED_RE.search(question or "")
            ):
                nudged_dashboard = True
                if cand and cand.content:
                    contents.append(cand.content)
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=policy.DASHBOARD_NUDGE)],
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
        "data_sections": data_sections,
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
                    # Keep the structured args too, so the export can rebuild the
                    # FULL dashboard (all KPIs + every section), not just one table.
                    widgets.append({"title": args.get("title", "dashboard"), "code": code, "kind": "dashboard", "data": args})
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
                # Which result is "the answer"? See result_capture - one rule,
                # shared by every backend, tested against both the bugs it fixes.
                if name == "run_sql" and result_capture.better(
                    cols_full, rows_full, data_columns, data_rows
                ):
                    data_columns, data_rows = cols_full, rows_full
                    result_capture.add_section(data_sections, cols_full, rows_full)
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
                    text=policy.WRITE_UP_PROMPT
                )
            ],
        )
    )
    # cur_model/cur_key, not the originals: if the loop rotated, the original
    # pair is exhausted and starting there would waste an attempt on a dead one.
    answer, synth_ok = _write_up(contents, system, cur_model, cur_key, on_event)
    if not synth_ok:
        log_interaction(question, sql_used, last_row_count,
                        error="write-up call failed on every key")

    log_interaction(question, sql_used, last_row_count)
    return {
        # Never claim "no data" while holding rows: when the write-up call fails
        # (e.g. provider quota) AFTER the query succeeded, say so honestly - the
        # UI then renders the captured rows as a table instead of a false denial.
        # Three situations, three different truths. Saying "I don't have that
        # information in the database" when NO query ever ran is a false denial -
        # it tells the user their data is missing when in fact we never looked.
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
