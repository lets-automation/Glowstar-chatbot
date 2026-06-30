"""
_retry.py
---------
Small retry-with-backoff helper for LLM calls.

Retries transient failures (network blips, per-minute rate limits, 5xx).
Does NOT retry hard daily/quota limits - those won't clear by waiting, so
we surface them immediately for a graceful "busy" message.
"""

import re
import time

# Phrases that mean "hard limit - don't bother retrying".
_HARD_LIMIT_HINTS = ("per day", "tpd", "quota", "daily limit")
# Per-minute throttles (TPM) DO clear by waiting - honour the suggested delay.
_RATE_HINTS = ("per minute", "tpm", "rate limit", "rate_limit", "too many", "429")
# Cap how long we'll wait for a per-minute bucket to refill.
_MAX_RATE_WAIT = 65.0


def _suggested_wait(msg: str) -> float | None:
    """Pull 'try again in 7.3s' out of a rate-limit message, if present."""
    m = re.search(r"try again in\s*([\d.]+)s", msg)
    if m:
        try:
            return float(m.group(1)) + 1.0
        except ValueError:
            return None
    return None


def call_with_retry(fn, retries: int = 4, base_delay: float = 2.0):
    """Call fn(); retry transient failures with backoff.

    Per-minute (TPM) rate limits are waited out using the API's suggested delay
    (capped), since the new Groq free tier throttles to a small tokens/minute
    budget and multi-round questions need to pause between calls.
    """
    delay = base_delay
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:
            msg = str(exc).lower()
            if any(h in msg for h in _HARD_LIMIT_HINTS):
                raise  # hard daily/quota limit - don't retry
            if attempt == retries:
                raise
            if any(h in msg for h in _RATE_HINTS):
                time.sleep(min(_suggested_wait(msg) or 20.0, _MAX_RATE_WAIT))
            else:
                time.sleep(delay)
                delay *= 2
