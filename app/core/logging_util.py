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
import re
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
        return
    logger.info("   rows_returned: %s", rows_returned)
    # A turn that ran NO query and returned NO rows still logged "ok", so a
    # silent no-query answer left no trace at all - seen live 2026-08-25 08:43,
    # where "kapan wise gia results for june month" logged ok/0 rows with no SQL
    # and the same question a minute later returned 37. Flag it: the answer was
    # not grounded in a query, whatever it said.
    if not sql_used and not rows_returned:
        logger.warning("   NO-QUERY TURN | nothing was executed for this question")


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


# AN HTML BODY MEANS A GATEWAY ANSWERED, NOT THE API.
#
# A self-hosted endpoint behind a proxy (RunPod, ngrok, a load balancer) returns
# an HTML error PAGE when the service behind it is down or still loading. That
# page is prose and markup, and matching provider needles against it is
# meaningless - worse, it is actively misleading.
#
# Measured live 2026-09-03. The RunPod pod stopped responding and returned its
# "Waiting for service to respond" page. The page contains the digits "401"
# inside an SVG path coordinate, the bare substring "401" is an `auth` needle,
# and `auth` is ordered BEFORE `connection` - so a dead pod was reported as
# "check LLM_PROVIDER, the model id, and the API key in .env". The config was
# perfect. That sends whoever is on call to the wrong file entirely.
_HTML_RE = re.compile(r"<!doctype html|<html[\s>]", re.IGNORECASE)

# A BARE THREE-DIGIT NEEDLE MATCHES ANY THREE DIGITS ANYWHERE.
# Status codes are only evidence when they read like a status - "401",
# "status: 429", "HTTP 503" - not when they fall out of a coordinate, an id or
# a timestamp. Everything non-numeric stays a plain substring match.
_STATUS_CONTEXT = r"(?:status|code|http|error|response)\D{0,12}"


def _needle_hit(needle: str, text: str) -> bool:
    if not needle.isdigit():
        return needle in text
    return re.search(rf"(?:{_STATUS_CONTEXT}{needle}|\b{needle}\b\s*[:-]|"
                     rf"^\s*{needle}\b)", text, re.MULTILINE) is not None


def classify_provider_error(exc) -> ProviderError:
    """Map a raw provider exception to a (category, user_message)."""
    text = str(exc).lower()
    if _HTML_RE.search(text):
        return ProviderError("unreachable", _MSG_UNREACHABLE)
    for category, needles, message in _ERROR_RULES:
        if any(_needle_hit(n, text) for n in needles):
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
    elif pe.category in ("unreachable", "connection"):
        # Point at the ENDPOINT, not at .env. A self-hosted pod that has
        # stopped, crashed or is still loading its weights looks exactly like
        # this, and the config is usually fine.
        logger.error(
            "   -> ENDPOINT problem: the provider host answered but the model "
            "service behind it did not. Check the pod/server is running and "
            "has finished loading, then retry - .env is probably fine."
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


# Turns that FAILED rather than honestly declined. These never reached the
# UNANSWERED backlog, because the old capture required rows_returned == 0 AND a
# "we don't hold that" phrase - a context overflow or a provider error matches
# neither, so the questions most worth turning into a recipe were the ones the
# backlog could not see. Measured on 2026-08-20: every "That request was too
# large" on a department report was invisible here.
_FAILURE_MARKERS = (
    "too large for the current ai model",
    "trouble answering",
    "busy right now",
    "usage limit",
    "couldn't reach",
    "could not reach",
    "misconfigured",
    "couldn't write the summary",
    "could not write the summary",
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
    low = (answer or "").lower()
    # A FAILURE is worth capturing even when rows came back: "I fetched the data
    # but couldn't write the summary" holds rows and is still a broken turn.
    failed = any(m in low for m in _FAILURE_MARKERS)
    if not failed:
        if rows_returned:
            return False
        if not any(m in low for m in _NO_DATA_MARKERS):
            return False
    logger.warning(
        "UNANSWERED | %s | q=%r | reply=%r",
        "FAILED" if failed else "no-data",
        (question or "").replace("\n", " ").strip()[:160],
        (answer or "").replace("\n", " ").strip()[:160],
    )
    return True
