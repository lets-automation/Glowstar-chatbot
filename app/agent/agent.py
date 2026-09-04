"""
agent.py
--------
The agent's public entry point: ask(question) -> {answer, sql_used, rows_returned}.

It dispatches to the configured LLM provider:
  - LLM_PROVIDER=groq      -> Groq (free-tier testing)      [groq_backend.py]
  - LLM_PROVIDER=cerebras  -> Cerebras (free, ~1M tok/day)  [groq_backend.py]
  - LLM_PROVIDER=nvidia    -> NVIDIA NIM (free, fits 20k)   [groq_backend.py]
  - LLM_PROVIDER=openrouter-> OpenRouter (Qwen3 trial)       [groq_backend.py]
  - LLM_PROVIDER=lmstudio  -> LM Studio (local, offline)    [groq_backend.py]
  - LLM_PROVIDER=anthropic -> Claude (best accuracy)        [anthropic_backend.py]

Switching providers is a one-line change in .env (LLM_PROVIDER + the key).
The shared rules, schema prompt, and tool handlers live in tools.py.
"""

import time

from app.agent import date_gate, query_rules, recipe_router
from app.agent import (
    anthropic_backend,
    attachments as attachments_mod,
    gemini_backend,
    groq_backend,
    postprocess,
)
from app.config import settings
from app.agent import answer_cache
from app.core import cost_trace
from app.core.logging_util import log_request, log_unanswered, logger


def _resolve_model(provider: str, override: str | None) -> str:
    """The model id this provider will actually use — for logging + dispatch."""
    if override:
        return override
    return {
        "anthropic": settings.ANTHROPIC_MODEL,
        "claude": settings.ANTHROPIC_MODEL,
        "gemini": settings.GEMINI_MODEL,
        "ollama": settings.OLLAMA_MODEL,
        "lmstudio": settings.LMSTUDIO_MODEL,
        "cerebras": settings.CEREBRAS_MODEL,
        "nvidia": settings.NVIDIA_MODEL,
        "openrouter": settings.OPENROUTER_MODEL,
        "kimi": settings.KIMI_MODEL,
    }.get(provider, settings.GROQ_MODEL)


def ask(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event=None,
    attachments: list[dict] | None = None,
) -> dict:
    """
    Answer a natural-language question using the configured LLM provider.

    history:     optional prior turns for conversation memory.
    on_event:    optional callback(status_str) called as tools run (for live UI).
    attachments: optional uploaded files [{file_id, filename}] to analyse.

    Returns the enriched response:
      { answer, suggestions[], citation, export_query, sql_used[], rows_returned }
    """
    # ONE COST TRACE PER TURN. A single question can spend several provider
    # calls - one per tool round, plus the final write-up, plus any nudge or key
    # rotation - and on the dashboard those arrived as unrelated events, so a
    # cheap question and a stalled one looked the same. Grouping them under one
    # trace (and one step() per round, opened inside each backend) is what makes
    # "this question cost $0.06 across 5 rounds" readable.
    #
    # Opened HERE rather than in the API layer so the CLI, the tests and
    # scripts/e2e_check.py get the same shape. No-op unless AgentCost is
    # configured, and a nested workflow joins the outer trace instead of
    # starting a second one.
    # The SQL tool validates each generated query against the rules for THIS
    # question (query_rules.py), so it needs to know what was asked. Scoped to
    # the turn so a stale question can never judge the next one's query.
    # The period the user gave earlier is carried into THIS turn and injected
    # into the prompt (date_gate.carried_period_directive). Remembering without
    # injecting is what made the model widen to all history and blow the
    # context; re-asking every turn is what the client saw in the demo.
    with cost_trace.workflow("erp-chat-turn"), query_rules.for_question(question),             date_gate.carrying_period(history, question):
        provider = settings.LLM_PROVIDER.lower()
        active_model = _resolve_model(provider, model)

        # Pre-warmed answer (ANSWER_CACHE_ENABLED): serve instantly with no
        # provider call, so a demo can't be killed by the ~20-requests/day
        # free-tier limit. Only for plain questions - a turn with attachments or
        # prior context must be answered fresh. Safe because the DB is a static
        # restored backup.
        if not attachments and not history:
            cached = answer_cache.get(question)
            if cached is not None:
                logger.info("CACHE HIT | q=%r (warmed %s)", question[:80],
                            cached.get("_cached_at"))
                if on_event:
                    on_event("Answering…")
                # No outcome recorded on purpose: a cache hit makes no LLM call,
                # so this trace holds no events and nothing is sent. Reporting
                # it would put free turns on a cost dashboard.
                return {k: v for k, v in cached.items() if not k.startswith("_")}

        # Read the uploaded files ONCE (into text + image blocks) so every
        # backend receives the same ready-to-use content instead of re-parsing.
        file_context = None
        if attachments:
            if on_event:
                on_event("Reading your file(s)…")
            file_context = attachments_mod.process_attachments(attachments)

        # Time the whole turn and log ONE ops line (provider / model / latency /
        # rows / outcome) regardless of how it ends. Backends catch their own
        # provider errors and return ok=False; an unexpected raise is logged
        # here as a failure and re-raised so the API's own handler still runs.
        # CURATED RECIPE, DECIDED IN CODE - NOT BY THE MODEL.
        #
        # The recipes are correct; the model choosing to call them is not.
        # Measured 2026-08-31: called directly, department_report returns 8
        # sections and lab_results 4, every figure reconciled against the
        # client's own ERP - while "Provide july month report of department
        # MFG - 1" and "last month GIA results for fency department" both came
        # back with NO tool call at all, so the anti-fabrication guard refused
        # the prose the model wrote instead and the user saw "I couldn't pull
        # that" for a question the system answers perfectly.
        #
        # Same pattern as smalltalk_gate / access_guard / date_gate above:
        # decided in code before any provider call. Deterministic, instant, and
        # immune to a weak or slow model - and to broken English, because
        # recipe_router matches the words the staff actually type.
        #
        # The result goes through postprocess.enrich exactly like a model turn,
        # so the citation, the export and every guard behave identically.
        # Skipped when files are attached (those need the model to read them)
        # and whenever the router cannot resolve the recipe, the period AND any
        # named department - in which case the normal path runs unchanged.
        if not attachments:
            _spec = recipe_router.match(question)
            if _spec:
                _raw = recipe_router.answer(_spec, question)
                if _raw:
                    # cut_purity_change is scoped by KAPAN and carries no
                    # period; every other recipe carries one. Indexing
                    # from_date/to_date unconditionally KeyErrors on it, which
                    # would take down the live turn for the ONE report the
                    # client checks packet-for-packet.
                    logger.info("RECIPE-ROUTED | %s | dept=%r | %s | q=%r",
                                _spec["recipe"], _spec.get("department", ""),
                                (f"kapan {_spec['kapan']}" if _spec.get("kapan")
                                 else f"{_spec.get('from_date')}..{_spec.get('to_date')}"),
                                question[:80])
                    log_request(question, "recipe", _spec["recipe"], ok=True,
                                rows_returned=_raw.get("rows_returned", 0),
                                latency_ms=0)
                    cost_trace.outcome(True, label="recipe")
                    _enriched = postprocess.enrich(_raw, question=question)
                    if not attachments and not history:
                        answer_cache.put(question, _enriched)
                    return _enriched

        t0 = time.monotonic()
        try:
            if provider in ("anthropic", "claude"):
                raw = anthropic_backend.ask_anthropic(
                    question, active_model, history, on_event, file_context
                )
            elif provider == "gemini":
                raw = gemini_backend.ask_gemini(
                    question, active_model, history, on_event, file_context
                )
            elif provider in ("ollama", "lmstudio", "cerebras", "nvidia",
                              "openrouter", "kimi"):
                # OpenAI-compatible endpoints (local Ollama / LM Studio, remote
                # Cerebras / NVIDIA NIM / OpenRouter) — all reuse the Groq
                # backend, which speaks the same tool-calling dialect; _client()
                # points at the right base_url (_OPENAI_COMPATIBLE).
                raw = groq_backend.ask_groq(
                    question, active_model, history, on_event, file_context
                )
            else:
                raw = groq_backend.ask_groq(
                    question, active_model, history, on_event, file_context
                )
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            log_request(
                question, provider, active_model,
                ok=False, rows_returned=0, latency_ms=latency_ms, error=str(exc),
            )
            # Money was still spent on the rounds that ran before the raise;
            # marking the trace failed is what separates it from a turn that
            # cost the same and actually answered.
            cost_trace.outcome(False, label="exception")
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        answered = bool(raw.get("ok", True))
        log_request(
            question, provider, active_model,
            ok=answered,
            rows_returned=raw.get("rows_returned", 0),
            latency_ms=latency_ms,
        )
        # Backends return ok=False for a provider failure or a failed write-up:
        # rounds were paid for and the user got no answer out of them.
        cost_trace.outcome(answered, label="answered" if answered else "no_answer")

        # Add suggestions, citation, export query, and the chart backstop
        # (deterministic, no LLM cost).
        enriched = postprocess.enrich(raw, question=question)

        # Capture questions the data couldn't answer, so each client surprise
        # becomes a to-do we can encode instead of a repeat bad meeting.
        # Grep: UNANSWERED
        log_unanswered(question, enriched.get("answer", ""), enriched.get("rows_returned", 0))

        # Warm the cache for next time (no-op unless ANSWER_CACHE_ENABLED).
        if not attachments and not history:
            answer_cache.put(question, enriched)

        return enriched


# Quick manual check: `python -m app.agent.agent`
if __name__ == "__main__":
    out = ask("How many packets are on jangad?")
    print("ANSWER:", out["answer"])
