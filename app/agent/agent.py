"""
agent.py
--------
The agent's public entry point: ask(question) -> {answer, sql_used, rows_returned}.

It dispatches to the configured LLM provider:
  - LLM_PROVIDER=groq      -> Groq (free-tier testing)      [groq_backend.py]
  - LLM_PROVIDER=anthropic -> Claude (best accuracy)        [anthropic_backend.py]

Switching providers is a one-line change in .env (LLM_PROVIDER + the key).
The shared rules, schema prompt, and tool handlers live in tools.py.
"""

from app.agent import (
    anthropic_backend,
    attachments as attachments_mod,
    gemini_backend,
    groq_backend,
    postprocess,
)
from app.config import settings


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

    # Read the uploaded files ONCE (into text + image blocks) so every backend
    # receives the same ready-to-use content instead of re-parsing.
    file_context = None
    if attachments:
        if on_event:
            on_event("Reading your file(s)…")
        file_context = attachments_mod.process_attachments(attachments)

    if provider in ("anthropic", "claude"):
        raw = anthropic_backend.ask_anthropic(
            question, model or settings.ANTHROPIC_MODEL, history, on_event, file_context
        )
    elif provider == "gemini":
        raw = gemini_backend.ask_gemini(
            question, model or settings.GEMINI_MODEL, history, on_event, file_context
        )
    elif provider == "ollama":
        # Local model via Ollama's OpenAI-compatible API — reuses the Groq
        # backend (same tool-calling dialect); _client() points at Ollama.
        raw = groq_backend.ask_groq(
            question, model or settings.OLLAMA_MODEL, history, on_event, file_context
        )
    else:
        raw = groq_backend.ask_groq(
            question, model or settings.GROQ_MODEL, history, on_event, file_context
        )

    # Add suggestions, citation, export query, and the chart backstop
    # (deterministic, no LLM cost).
    return postprocess.enrich(raw, question=question)


# Quick manual check: `python -m app.agent.agent`
if __name__ == "__main__":
    out = ask("How many packets are on jangad?")
    print("ANSWER:", out["answer"])
