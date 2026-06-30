# Production Readiness

What's already production-grade, and what to do before go-live.

## Already built (production-grade)

**Accuracy & intelligence**
- Schema routing: only relevant tables sent per question (token-efficient).
- `find_tables` + `get_table_columns`: the agent reaches any of the 239 tables and never guesses column names.
- Business glossary + VALUE CODES catalog: knows diamond codes (Shape RD/EM, Color D-N, Clarity in the `Purity` column, Fluorescence `Florecent`/`Florocent` NON/FNT/...), so coded/misspelled columns are handled.
- Broken-English handling: interprets typos, uses `LIKE` matching.
- "Don't give up" rule + forced final answer: searches before saying "no data".

**Conversation**
- Session memory (`session_id` on `/chat`): follow-up questions work, with follow-up-aware table routing. Last 6 turns kept per session.

**Performance**
- Schema (tables/columns/FKs) cached after first read: ~150x faster context build, no per-question DB load.

**Safety**
- Read-only enforced (sql_guard blocks writes/commands/comments/multi-statements; runner re-checks).
- Row cap + query timeout on every query.
- System/login tables hidden from the agent.
- Input length capped (1000 chars).

**Reliability & ops**
- Retry-with-backoff on transient LLM errors; graceful "busy" message on hard limits (never crashes).
- Every question + SQL + outcome logged to `logs/agent.log`.
- Provider-switchable (Groq <-> Claude) via `.env`, no code changes.

## Before go-live (checklist)

| Area | Action |
|---|---|
| **LLM** | Switch to Claude (`LLM_PROVIDER=anthropic`, `SCHEMA_MAX_COLS=0`) for best accuracy + no daily cap. See SWITCH_TO_CLAUDE.md. |
| **Security: CORS** | In `app/api/main.py`, replace `allow_origins=["*"]` with the client's real React domain(s). |
| **Security: auth** | Add an API key / JWT check so only the React app can call `/chat` and `/export`. |
| **Security: DB user** | Point `.env` at a SQL login with **SELECT-only** permission (defense in depth on top of the app guard). |
| **Sessions at scale** | The in-memory session store (`app/api/sessions.py`) is per-process. For multiple workers, back it with **Redis** (same get/add interface). |
| **Scale / cost** | Use Groq paid tier or Claude (pay-as-you-go) — the free tier's daily token cap is not enough for many users. |
| **Hosting** | Run uvicorn behind a reverse proxy (nginx/IIS) with HTTPS; set workers; restart policy. |
| **Monitoring** | Ship `logs/agent.log` to a log system; alert on error spikes / rate limits. |
| **UAT** | Run the AI-generated question set (from DATABASE_GUIDE.md) through the agent; fix any wrong answers as glossary/VALUE_CODES additions before launch. |
| **Glossary sign-off** | Have the client confirm the `status: "verify"` items in `glossary.py`. |

## How to extend accuracy (the standard pattern)
When a question returns a wrong/"no data" answer, it's almost always a
coded value or misspelled/misleading column the agent doesn't know yet.
Fix = add a line to `VALUE_CODES` / `TABLE_NOTES` / `DATA_NOTES` in
`app/schema/glossary.py`. No code changes, and it applies to both providers.
