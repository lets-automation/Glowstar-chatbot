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
    # Comma-separated origins allowed to call the API, e.g.
    # "https://chat.glowstardiam.com,http://localhost:5173". Defaults to "*"
    # for local dev only - set this explicitly for any real deployment.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")


# A single shared settings object the whole app imports.
settings = Settings()
