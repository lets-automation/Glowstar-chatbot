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

    # Groq (free-tier testing).
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # gpt-oss-20b: lighter + separate daily token budget than 120b.
    # TEMPORARY for free-tier. On Claude/paid, prefer gpt-oss-120b or Claude.
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    # Anthropic / Claude (switch to this later for best accuracy).
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # Google Gemini (free-tier FALLBACK for Groq — big per-minute budget).
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # AgentCost (agentcost.tech) — OPTIONAL LLM cost tracking. When both values
    # are set, main.py initializes the SDK, which patches the anthropic/openai
    # client libraries and reports per-call metadata (model, token counts, cost,
    # latency — NOT prompt content) to the AgentCost dashboard. Leave empty to
    # disable entirely. NOTE: it does NOT patch the native groq SDK, so the
    # groq provider path is not tracked (only anthropic, and ollama-via-openai).
    AGENTCOST_API_KEY: str = os.getenv("AGENTCOST_API_KEY", "")
    AGENTCOST_PROJECT_ID: str = os.getenv("AGENTCOST_PROJECT_ID", "")
    AGENTCOST_DEBUG: bool = os.getenv("AGENTCOST_DEBUG", "false").lower() in (
        "1", "true", "yes",
    )

    # Ollama (LOCAL, offline testing). Runs a model on this machine via Ollama's
    # OpenAI-compatible endpoint — no API key, no internet, no daily quota. Set
    # LLM_PROVIDER=ollama to use it (routed through the Groq backend, which speaks
    # the same tool-calling dialect). Run `ollama pull <model>` first.
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    # Max columns shown per table in the schema context.
    # TEMPORARY token-saving cap for the free tier. Set SCHEMA_MAX_COLS=0
    # (no cap) once on Claude / paid tier for fuller, more accurate context.
    SCHEMA_MAX_COLS: int = int(os.getenv("SCHEMA_MAX_COLS", "30"))

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
