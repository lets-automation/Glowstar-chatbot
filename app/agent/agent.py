"""
agent.py
--------
The agent's public entry point: ask(question) -> {answer, sql_used, rows_returned}.

It dispatches to the configured LLM provider:
  - LLM_PROVIDER=groq      -> Groq (free-tier testing)      [groq_backend.py]
  - LLM_PROVIDER=cerebras  -> Cerebras (free, ~1M tok/day)  [groq_backend.py]
  - LLM_PROVIDER=nvidia    -> NVIDIA NIM (free, fits 20k)   [groq_backend.py]
  - LLM_PROVIDER=lmstudio  -> LM Studio (local, offline)    [groq_backend.py]
  - LLM_PROVIDER=anthropic -> Claude (best accuracy)        [anthropic_backend.py]

Switching providers is a one-line change in .env (LLM_PROVIDER + the key).
The shared rules, schema prompt, and tool handlers live in tools.py.
"""

import time

from app.agent import (
    anthropic_backend,
    attachments as attachments_mod,
    gemini_backend,
    groq_backend,
    postprocess,
)
from app.config import settings
from app.agent import answer_cache
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
    provider = settings.LLM_PROVIDER.lower()
    active_model = _resolve_model(provider, model)

    # Pre-warmed answer (ANSWER_CACHE_ENABLED): serve instantly with no provider
    # call, so a demo can't be killed by the ~20-requests/day free-tier limit.
    # Only for plain questions - a turn with attachments or prior context must be
    # answered fresh. Safe because the DB is a static restored backup.
    if not attachments and not history:
        cached = answer_cache.get(question)
        if cached is not None:
            logger.info("CACHE HIT | q=%r (warmed %s)", question[:80],
                        cached.get("_cached_at"))
            if on_event:
                on_event("Answering…")
            return {k: v for k, v in cached.items() if not k.startswith("_")}

    # Read the uploaded files ONCE (into text + image blocks) so every backend
    # receives the same ready-to-use content instead of re-parsing.
    file_context = None
    if attachments:
        if on_event:
            on_event("Reading your file(s)…")
        file_context = attachments_mod.process_attachments(attachments)

    # Time the whole turn and log ONE ops line (provider / model / latency /
    # rows / outcome) regardless of how it ends. Backends catch their own
    # provider errors and return ok=False; an unexpected raise is logged here
    # as a failure and re-raised so the API's own handler still runs.
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
        elif provider in ("ollama", "lmstudio", "cerebras", "nvidia"):
            # OpenAI-compatible endpoints (local Ollama / LM Studio, remote
            # Cerebras / NVIDIA NIM) — all reuse the Groq backend, which speaks the
            # same tool-calling dialect; _client() points at the right base_url
            # (_OPENAI_COMPATIBLE).
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
        raise

    latency_ms = int((time.monotonic() - t0) * 1000)
    log_request(
        question, provider, active_model,
        ok=raw.get("ok", True),
        rows_returned=raw.get("rows_returned", 0),
        latency_ms=latency_ms,
    )

    # Add suggestions, citation, export query, and the chart backstop
    # (deterministic, no LLM cost).
    enriched = postprocess.enrich(raw, question=question)

    # Capture questions the data couldn't answer, so each client surprise becomes
    # a to-do we can encode instead of a repeat bad meeting. Grep: UNANSWERED
    log_unanswered(question, enriched.get("answer", ""), enriched.get("rows_returned", 0))

    # Warm the cache for next time (no-op unless ANSWER_CACHE_ENABLED).
    if not attachments and not history:
        answer_cache.put(question, enriched)

    return enriched


# Quick manual check: `python -m app.agent.agent`
if __name__ == "__main__":
    out = ask("How many packets are on jangad?")
    print("ANSWER:", out["answer"])
