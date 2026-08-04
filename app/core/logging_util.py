"""
logging_util.py
---------------
Observability for the agent. Records each question, the SQL the agent ran,
how many rows came back, provider latency, and any error — to both the console
and a rotating logfile (logs/agent.log).

This makes both ACCURACY and OPERATIONAL problems debuggable:
  - accuracy: open the log and see exactly which SQL produced an answer.
  - ops: a boot banner shows the active provider/model, every request logs its
    provider + latency + outcome, and provider failures are CLASSIFIED (dead
    model / auth / rate-limit / connection) instead of collapsing into one
    vague "trouble forming that query". A misconfigured model now screams in
    the log instead of hiding behind a generic user message.
"""

import logging
import os
from collections import namedtuple
from logging.handlers import RotatingFileHandler

# Put logs in a "logs" folder next to the project root.
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "agent.log")

# Configure one shared logger named "aastha".
logger = logging.getLogger("aastha")
if not logger.handlers:  # avoid adding handlers twice on re-import
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Rotating so the file can't grow without bound (it used to be a plain
    # FileHandler — a long-running container filled it with repeated tracebacks).
    # ~2 MB x 5 backups = ~10 MB ceiling.
    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)


def log_interaction(
    question: str,
    sql_used: list[str],
    rows_returned: int,
    error: str = "",
) -> None:
    """Record one agent interaction (question + SQL + outcome)."""
    logger.info("Q: %s", question)
    for sql in sql_used:
        logger.info("   SQL: %s", sql)
    if error:
        logger.error("   ERROR: %s", error)
    else:
        logger.info("   rows_returned: %s", rows_returned)


# --------------------------------------------------------------------------- #
# Provider error classification
# --------------------------------------------------------------------------- #
# One place that turns a raw provider exception into (a) a category for the log
# and (b) a user-facing message that points at the RIGHT thing. The big win:
# a dead/renamed model or a bad API key is a CONFIG problem — telling the user
# to "rephrase the question" (the old catch-all) sends everyone down the wrong
# path, exactly what happened when Groq retired the Scout model.

ProviderError = namedtuple("ProviderError", ["category", "user_message"])

# Generic, provider-neutral wording (the user never sees provider names).
_MSG_CONFIG = (
    "The AI service is misconfigured and can't answer right now. "
    "Please contact support — this needs an admin, not a rephrase."
)
_MSG_BUSY = (
    "The assistant is busy right now (usage limit reached). "
    "Please try again in a minute."
)
_MSG_TOO_LARGE = (
    "That request was too large for the current AI model. Please shorten it, "
    "or contact support if it keeps happening."
)
_MSG_UNREACHABLE = (
    "Couldn't reach the AI service just now. Please try again in a moment."
)
_MSG_GENERIC = "Sorry, I had trouble answering that. Please try rephrasing the question."

# Ordered: first matching category wins. Each needle is matched against the
# lower-cased exception text. Order matters — model/auth (config) before the
# broader rate/size buckets so a "model not found" never reads as "busy".
_ERROR_RULES = [
    ("model_not_found",
     ("does not exist", "model_not_found", "model not found", "no such model",
      "decommissioned", "unknown model", "invalid model"),
     _MSG_CONFIG),
    ("auth",
     ("invalid api key", "invalid x-api-key", "incorrect api key", "no api key",
      "authentication", "unauthorized", "401", "permission denied", "forbidden",
      "invalid_api_key"),
     _MSG_CONFIG),
    ("context_too_large",
     ("request too large", "too large", "413", "context length", "context_length",
      "maximum context", "reduce your message", "tokens per minute"),
     _MSG_TOO_LARGE),
    ("rate_limit",
     ("rate limit", "rate_limit", "429", "quota", "resource_exhausted",
      "exhausted", "too many requests", "usage limit"),
     _MSG_BUSY),
    ("connection",
     ("connection", "timed out", "timeout", "unreachable", "refused",
      "getaddrinfo", "temporarily unavailable", "network", "503", "502", "504"),
     _MSG_UNREACHABLE),
]


def classify_provider_error(exc) -> ProviderError:
    """Map a raw provider exception to a (category, user_message)."""
    text = str(exc).lower()
    for category, needles, message in _ERROR_RULES:
        if any(n in text for n in needles):
            return ProviderError(category, message)
    return ProviderError("unknown", _MSG_GENERIC)


def log_provider_error(provider: str, model: str, exc: Exception) -> ProviderError:
    """Classify + LOG a failed provider call clearly, and hand back the
    classification so the backend can return the right user message.

    Logs the category, provider, model and the (truncated) real error — and for
    a config-class failure, an explicit fix hint so it's unmissable in the log.
    """
    pe = classify_provider_error(exc)
    logger.error(
        "PROVIDER CALL FAILED | provider=%s model=%s category=%s | %s",
        provider, model, pe.category, str(exc)[:600],
    )
    if pe.category in ("model_not_found", "auth"):
        logger.error(
            "   -> CONFIG problem: check LLM_PROVIDER, the model id, and the API "
            "key in .env (the model may have been renamed/retired by the provider)."
        )
    return pe


def log_startup(provider: str, model: str, key_present: bool) -> None:
    """Boot banner: what provider/model this process will actually use. Makes a
    misconfiguration (wrong provider, missing key) visible the moment the
    backend starts, instead of only when the first question fails."""
    logger.info(
        "STARTUP | provider=%s | model=%s | api_key=%s",
        provider, model, "set" if key_present else "MISSING",
    )
    if not key_present:
        logger.warning(
            "   -> no API key for provider '%s' — every question will fail until "
            "the key is set in .env.", provider,
        )


def log_request(
    question: str,
    provider: str,
    model: str,
    ok: bool,
    rows_returned: int,
    latency_ms: int,
    error: str = "",
) -> None:
    """One line per chat turn: provider, model, latency, rows, outcome. This is
    the ops view — scan it to see which turns are slow or failing without
    reading the full SQL detail that log_interaction records."""
    short_q = (question or "").replace("\n", " ").strip()[:100]
    status = "ok" if ok else "FAIL"
    if error:
        logger.info(
            "REQUEST | provider=%s model=%s | %s %dms rows=%s | q=%r | err=%s",
            provider, model, status, latency_ms, rows_returned, short_q, str(error)[:200],
        )
    else:
        logger.info(
            "REQUEST | provider=%s model=%s | %s %dms rows=%s | q=%r",
            provider, model, status, latency_ms, rows_returned, short_q,
        )


# Phrases an answer uses when the ERP genuinely has no data for the question.
_NO_DATA_MARKERS = (
    "don't have that information",
    "do not have that information",
    "not tracked",
    "isn't tracked",
    "is not tracked",
    "doesn't record",
    "does not record",
    "not recorded",
    "no access",
)


def log_unanswered(question: str, answer: str, rows_returned: int) -> bool:
    """
    Record a question the assistant could NOT answer from the data.

    The client keeps asking things the ERP was never built for ("which city is
    this packet in?"). Each one that reaches them unanswered is a bad meeting; each
    one CAPTURED here is a to-do we can encode. Grep the log for UNANSWERED to get
    the backlog:  docker logs glowstar_chatbot-backend-1 | grep UNANSWERED

    Returns True when the turn was logged as unanswered.
    """
    if rows_returned:
        return False
    low = (answer or "").lower()
    if not any(m in low for m in _NO_DATA_MARKERS):
        return False
    logger.warning(
        "UNANSWERED | q=%r | reply=%r",
        (question or "").replace("\n", " ").strip()[:160],
        (answer or "").replace("\n", " ").strip()[:160],
    )
    return True
