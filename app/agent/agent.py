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

from app.agent import anthropic_backend, groq_backend, postprocess
from app.config import settings


def ask(
    question: str,
    history: list[dict] | None = None,
    model: str | None = None,
    on_event=None,
) -> dict:
    """
    Answer a natural-language question using the configured LLM provider.

    history:  optional prior turns for conversation memory.
    on_event: optional callback(status_str) called as tools run (for live UI).

    Returns the enriched response:
      { answer, suggestions[], citation, export_query, sql_used[], rows_returned }
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "anthropic":
        raw = anthropic_backend.ask_anthropic(
            question, model or settings.ANTHROPIC_MODEL, history, on_event
        )
    else:
        raw = groq_backend.ask_groq(
            question, model or settings.GROQ_MODEL, history, on_event
        )

    # Add suggestions, citation, and export query (deterministic, no LLM cost).
    return postprocess.enrich(raw)


# Quick manual check: `python -m app.agent.agent`
if __name__ == "__main__":
    out = ask("How many packets are on jangad?")
    print("ANSWER:", out["answer"])
