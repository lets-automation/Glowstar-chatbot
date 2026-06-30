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

    # Max columns shown per table in the schema context.
    # TEMPORARY token-saving cap for the free tier. Set SCHEMA_MAX_COLS=0
    # (no cap) once on Claude / paid tier for fuller, more accurate context.
    SCHEMA_MAX_COLS: int = int(os.getenv("SCHEMA_MAX_COLS", "30"))

    # --- Semantic search (Phase 7 - OPTIONAL; only if fuzzy search is needed) ---
    VOYAGE_API_KEY: str = os.getenv("VOYAGE_API_KEY", "")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX: str = os.getenv("PINECONE_INDEX", "aastha-semantic")


# A single shared settings object the whole app imports.
settings = Settings()
