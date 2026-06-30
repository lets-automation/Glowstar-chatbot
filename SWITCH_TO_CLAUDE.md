
 Switching to Claude (and reverting the free-tier token savings)

Right now the agent runs on **Groq's free tier**, with two TEMPORARY
token-saving settings. When the **Claude API key** is available, switch to
Claude for better accuracy and undo the savings.

Everything is config-driven — **no code changes needed**, just edit `.env`.

## The temporary free-tier settings (what to undo)

| Setting | Now (free tier) | On Claude (recommended) | Why |
|---|---|---|---|
| `LLM_PROVIDER` | `groq` | `anthropic` | Use Claude for best accuracy |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | — (unused) | Lighter model to fit free limits |
| `SCHEMA_MAX_COLS` | `30` | `0` (no cap) | Send the FULL schema for better answers |
| `ANTHROPIC_API_KEY` | (empty) | `sk-ant-...` | Required for Claude |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | `claude-sonnet-4-6` or `claude-opus-4-8` | opus = most accurate |

## Steps when the Claude key arrives

1. Open `.env` and set:
   ```
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-...your-key...
   ANTHROPIC_MODEL=claude-sonnet-4-6      # or claude-opus-4-8 for top accuracy
   SCHEMA_MAX_COLS=0                       # full schema, no token-saving cap
   ```
2. Restart the API (uvicorn auto-reloads if running with --reload).
3. Verify:
   ```powershell
   & C:\Glowstar_chatbot\venv\Scripts\python.exe -m tests.test_agent
   & C:\Glowstar_chatbot\venv\Scripts\python.exe -m tests.test_accuracy
   ```

That's it. The Claude backend (`app/agent/anthropic_backend.py`) is already
built and uses prompt caching on the schema, so cost stays low even without
the column cap.

## To switch back to Groq later
Set `LLM_PROVIDER=groq` (and `SCHEMA_MAX_COLS=30` if you want the savings).

## Notes
- `claude-opus-4-8` = most accurate (best for tricky questions). `claude-sonnet-4-6`
  = cheaper, still strong. Pick per budget.
- With Claude (pay-as-you-go, no daily token cap), the free-tier limits that
  caused the "rate limit" errors no longer apply.
- The Groq backend stays in the codebase, so you can switch either way anytime.
