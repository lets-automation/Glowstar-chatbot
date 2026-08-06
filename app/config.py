"""
config.py
---------
Central place for all configuration. Reads values from the .env file
once, so the rest of the app never touches os.getenv directly.
"""

import os

from dotenv import load_dotenv

# Load variables from the .env file in the project root.
load_dotenv()


class Settings:
    """All app settings, loaded from environment variables."""

    # --- Database (Aastha ERP - SQL Server) ---
    DB_SERVER: str = os.getenv("DB_SERVER", "localhost")
    DB_NAME: str = os.getenv("DB_NAME", "AasthaErp")
    DB_DRIVER: str = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    # Leave DB_USER empty to use Windows Authentication (local/dev). On the
    # client's live server, set DB_USER + DB_PASSWORD for SQL login auth.
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # --- LLM provider ---
    # Which provider to use: "groq" (now, free-tier testing) or "anthropic"
    # (Claude - switch to this when the Claude key arrives, for best results).
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")

    # Groq (free-tier testing). Reached through Groq's OPENAI-COMPATIBLE endpoint
    # rather than the native groq SDK — see _OPENAI_COMPATIBLE in groq_backend.py.
    # The request/response surface used here (chat.completions.create with tools)
    # is identical on both, and the OpenAI client is the one AgentCost patches, so
    # this is the difference between Groq turns being costed and being invisible.
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # gpt-oss-20b: lighter + separate daily token budget than 120b.
    # TEMPORARY for free-tier. On Claude/paid, prefer gpt-oss-120b or Claude.
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    # Anthropic / Claude (switch to this later for best accuracy).
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # Google Gemini (free-tier FALLBACK for Groq — big per-minute budget).
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # EXTRA keys for automatic failover. The free tier is ~20 requests/DAY per
    # key, which killed mid-demo turns with "the assistant is busy". Set
    # GEMINI_API_KEYS to a comma-separated list (or add GEMINI_API_KEY_2/_3) and
    # a quota-exhausted key is skipped for the rest of the day automatically.
    GEMINI_API_KEYS: str = os.getenv("GEMINI_API_KEYS", "")
    GEMINI_API_KEY_2: str = os.getenv("GEMINI_API_KEY_2", "")
    GEMINI_API_KEY_3: str = os.getenv("GEMINI_API_KEY_3", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # FALLBACK MODELS - the free tier's real escape hatch.
    #
    # The 429 names its own quota id: GenerateRequestsPerMinutePerProjectPerModel
    # (limit 5/min, 20/day). It is scoped PER MODEL, so every model carries its
    # own budget - but it is also per PROJECT, so extra API KEYS in the same
    # project share one pool and rotating them buys nothing. Rotating MODELS
    # does. Verified: gemini-2.5-flash answered in 1.9s while gemini-3-flash was
    # still exhausted.
    #
    # One report question costs ~6 calls against a 5/min limit, so a single model
    # cannot finish one. Three models make it comfortable.
    # Ordered fastest-first (measured: 3.1-flash-lite 1.0s, 2.5-flash 1.9s,
    # 3-flash-preview 19.5s). All three were confirmed to support tool calling -
    # a model without it returns chat text and zero data.
    GEMINI_FALLBACK_MODELS: str = os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-2.5-flash,gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-2.0-flash",
    )

    def gemini_model_chain(self) -> list[str]:
        """The configured model first, then the fallbacks, de-duplicated."""
        chain, seen = [], set()
        for m in [self.GEMINI_MODEL, *self.GEMINI_FALLBACK_MODELS.split(",")]:
            m = m.strip()
            if m and m not in seen:
                seen.add(m)
                chain.append(m)
        return chain

    def gemini_keys(self) -> list[str]:
        """All configured Gemini keys, in priority order, de-duplicated."""
        raw = [self.GEMINI_API_KEY, *self.GEMINI_API_KEYS.split(","),
               self.GEMINI_API_KEY_2, self.GEMINI_API_KEY_3]
        seen, out = set(), []
        for k in (s.strip() for s in raw):
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    # AgentCost (agentcost.tech) — OPTIONAL LLM cost tracking. When both values
    # are set, main.py initializes the SDK, which patches the anthropic/openai/
    # google-genai client libraries and reports per-call metadata (model, token
    # counts, cost, latency — NOT prompt content) to the AgentCost dashboard.
    # Leave empty to disable entirely.
    #
    # EVERY provider is now tracked. It patches by CLIENT LIBRARY, not by
    # provider, so what matters is which library a provider is reached through:
    #   anthropic            -> anthropic client   tracked
    #   gemini               -> google-genai       tracked (needs SDK >= 0.1.4;
    #                                              the old 0.1.3 pin had no
    #                                              Gemini interceptor at all, so
    #                                              nothing was ever recorded)
    #   groq / cerebras / nvidia / ollama / lmstudio -> openai client   tracked
    # Groq used to be the exception because it went through the native groq SDK,
    # which AgentCost does not patch; it now uses Groq's OpenAI-compatible
    # endpoint instead (GROQ_BASE_URL above).
    #
    # A model absent from main.py's _AGENTCOST_PRICING records at $0.00 rather
    # than being refused — keep that table in step with the models in use,
    # including every entry of GEMINI_FALLBACK_MODELS.
    AGENTCOST_API_KEY: str = os.getenv("AGENTCOST_API_KEY", "")
    AGENTCOST_PROJECT_ID: str = os.getenv("AGENTCOST_PROJECT_ID", "")
    AGENTCOST_DEBUG: bool = os.getenv("AGENTCOST_DEBUG", "false").lower() in (
        "1", "true", "yes",
    )

    # Cerebras (free tier, ~1M tokens/day — no daily REQUEST cap, unlike Gemini's
    # ~20/day). OpenAI-compatible, so it routes through the Groq backend just
    # like Ollama does. Set LLM_PROVIDER=cerebras to use it. This account serves
    # gpt-oss-120b, zai-glm-4.7 and gemma-4-31b only (NO llama-3.3-70b).
    CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")
    CEREBRAS_BASE_URL: str = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")
    CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")

    # NVIDIA NIM (build.nvidia.com) — FREE with an NVIDIA Developer account, no
    # card, ~40 req/min. The ONLY free remote tier verified to accept this app's
    # full ~20k-token prompt (Groq caps at 12k TPM, GitHub Models at 8k in).
    # OpenAI-compatible -> reuses this Groq backend. NOTE: many NIM models hang
    # or refuse tool calls; openai/gpt-oss-20b is the verified-good one.
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b")

    # Ollama (LOCAL, offline testing). Runs a model on this machine via Ollama's
    # OpenAI-compatible endpoint — no API key, no internet, no daily quota. Set
    # LLM_PROVIDER=ollama to use it (routed through the Groq backend, which speaks
    # the same tool-calling dialect). Run `ollama pull <model>` first.
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    # LM Studio (LOCAL, offline testing). Same idea as Ollama — an
    # OpenAI-compatible server, so it also routes through the Groq backend. Set
    # LLM_PROVIDER=lmstudio to use it. In LM Studio: load the model, open the
    # Developer/Server tab, Start Server, and copy the model id it shows into
    # LMSTUDIO_MODEL. Two things the model MUST have, or this app cannot work:
    #   * TOOL / function calling  — every answer here comes from run_sql;
    #     a model without tool support returns chat text and zero data.
    #   * a big context length     — the schema prompt is ~20k tokens with
    #     SCHEMA_MAX_COLS=0, and LM Studio defaults new models to ~4k. Raise
    #     the context slider to 32k+ or the prompt is silently truncated.
    # If LM Studio runs on a DIFFERENT machine, point the URL at that machine's
    # IP and enable "Serve on Local Network" in LM Studio's server settings.
    LMSTUDIO_BASE_URL: str = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    LMSTUDIO_MODEL: str = os.getenv("LMSTUDIO_MODEL", "qwen2.5-7b-instruct")

    # Output-token budget per model call.
    #
    # This used to be ONE number (2048) for every non-Anthropic provider, tuned
    # for Groq's tight 12k tokens-per-minute free tier — so Gemini, Cerebras and
    # NVIDIA, which have far more headroom, were throttled to Groq's limit for
    # nothing. 2048 cannot hold the answer format the RULES mandate: a single
    # 30-row x 12-column Markdown table is ~1,200-2,000 tokens on its own, and
    # REASONING models (gpt-oss, Gemma) spend part of the same budget thinking
    # before they write. That is a direct, measurable cause of the "thin answer"
    # and mid-table truncation complaints — the backends even append a "shortened
    # for length" note when it happens.
    #
    # So the budget now follows whichever provider is ACTIVE. This is not a model
    # choice: the provider still rotates with quota exactly as before, each one
    # simply gets its own real headroom instead of Groq's.
    #
    # LLM_MAX_TOKENS in .env still overrides everything, for pinning a value
    # while debugging or when a provider tightens its limits.
    _PROVIDER_MAX_TOKENS = {
        "groq": 2048,       # 12k TPM free tier — the one genuinely tight budget
        "gemini": 8192,     # large free per-minute budget
        "cerebras": 8192,   # ~1M tokens/day, no per-request pressure
        "nvidia": 4096,     # ~40 req/min, generous per request
        "ollama": 4096,     # local: no quota at all
        "lmstudio": 4096,   # local: no quota at all
        "anthropic": 4096,
        "claude": 4096,
    }
    # Floor for any provider: the minimum that fits the mandated answer format
    # (intro + ~30-row preview table + conclusion + download pointer +
    # SUGGESTIONS). An unknown or newly-added provider gets this, never less.
    _MIN_OUTPUT_TOKENS = 2048

    def max_output_tokens(self, provider: str | None = None) -> int:
        """Per-call output budget for the active (or given) provider.

        Reads LLM_MAX_TOKENS LIVE rather than at import. The rest of this class
        must snapshot env into class attributes, but this is a method, and a
        knob that only takes effect if it happened to be set before the module
        was first imported is a knob that will surprise someone at 2am.
        """
        override = os.getenv("LLM_MAX_TOKENS", "").strip()
        if override:
            try:
                return int(override)
            except ValueError:
                pass  # nonsense value -> fall through to the provider default
        key = (provider or self.LLM_PROVIDER or "").lower()
        return self._PROVIDER_MAX_TOKENS.get(key, self._MIN_OUTPUT_TOKENS)

    # Back-compat: some call sites still read this as a plain attribute. It
    # resolves for the provider configured at import time.
    LLM_MAX_TOKENS: int = int(
        os.getenv("LLM_MAX_TOKENS")
        or _PROVIDER_MAX_TOKENS.get(os.getenv("LLM_PROVIDER", "groq").lower(), 2048)
    )

    # Max columns shown per table in the schema context.
    # TEMPORARY token-saving cap for the free tier. Set SCHEMA_MAX_COLS=0
    # (no cap) once on Claude / paid tier for fuller, more accurate context.
    SCHEMA_MAX_COLS: int = int(os.getenv("SCHEMA_MAX_COLS", "30"))

    # How many tables the router may put in the prompt for one question.
    #
    # Was hard-coded to 4 while the router could only ever choose from 29 of the
    # ~239 business tables — so the single most common failure was the answer's
    # table simply not being in the prompt. The router now scores every table
    # (app/schema/router.py) and this is the width of what it may show.
    #
    # It is a QUALITY/COST dial, not a limit to be maxed: each table costs
    # roughly 250-400 tokens, and padding the prompt with weak matches hurts
    # small models. The router already returns fewer than this when the question
    # doesn't warrant more. Lower it if a provider's per-minute budget is tight.
    SCHEMA_MAX_TABLES: int = int(os.getenv("SCHEMA_MAX_TABLES", "10"))

    # --- Semantic search (Phase 7 - OPTIONAL; only if fuzzy search is needed) ---
    VOYAGE_API_KEY: str = os.getenv("VOYAGE_API_KEY", "")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX: str = os.getenv("PINECONE_INDEX", "aastha-semantic")

    # --- Redis (chat sessions, user accounts, rate-limit counters) ---
    # "redis" is the service name inside Docker Compose; "localhost" for local dev.
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Chat-history store (Postgres; cross-device threads) ---
    # SQLAlchemy URL of the history database, e.g.
    #   postgresql+psycopg2://glowstar:<password>@history-db:5432/glowstar_history
    # Compose injects the in-network URL automatically (docker-compose.yml).
    # EMPTY (the default) disables server-side history: the /threads endpoints
    # return 503 and the frontend falls back to per-browser localStorage.
    HISTORY_DB_URL: str = os.getenv("HISTORY_DB_URL", "")

    # --- Authentication master switch ---
    # OFF by default: the chatbot runs standalone with NO login screen and open
    # API access (correct for a localhost/embedded deployment). The client turns
    # this ON (AUTH_ENABLED=true) when they want the built-in username/password
    # login, or when wiring the API's token check into their CRM's SSO. All the
    # auth machinery below stays in place either way.
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() in ("1", "true", "yes")

    # --- Authentication (individual user logins, JWT) ---
    # MUST be overridden in .env for any real deployment - this default is only
    # so local dev doesn't crash before it's set. Generate one long random value
    # (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) and keep
    # it secret - anyone with it can forge valid login tokens.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(12 * 60)))  # 12h workday

    # --- Rate limiting (per authenticated user, Redis-backed) ---
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))

    # --- CORS ---
    # Comma-separated origins allowed to call the API cross-origin, e.g.
    # "https://chat.glowstardiam.com". The Docker deployment serves the frontend
    # AND proxies /api from the SAME origin (nginx :8080), so it needs no CORS at
    # all; CORS only matters for local dev where Vite (:5173) calls the API
    # (:8000) cross-origin. The default is therefore the local dev origins - NOT
    # "*". For a real deployment set this to the exact CRM/frontend origin(s).
    # A wildcard "*" is refused credentials in main.py (a wildcard + credentials
    # would let ANY website read this auth-optional API).
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    )

    # Expose the interactive API docs (/docs, /redoc, /openapi.json)? OFF by
    # default so an internet-reachable backend does not advertise its whole API
    # surface to anonymous callers. Turn on for local development only.
    API_DOCS_ENABLED: bool = os.getenv("API_DOCS_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )


# A single shared settings object the whole app imports.
settings = Settings()
