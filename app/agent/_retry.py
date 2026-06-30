"""
_retry.py
---------
Small retry-with-backoff helper for LLM calls.

Retries transient failures (network blips, per-minute rate limits, 5xx).
Does NOT retry hard daily/quota limits - those won't clear by waiting, so
we surface them immediately for a graceful "busy" message.
"""

import time

# Phrases that mean "hard limit - don't bother retrying".
_HARD_LIMIT_HINTS = ("per day", "tpd", "quota", "daily limit")


def call_with_retry(fn, retries: int = 2, base_delay: float = 2.0):
    """Call fn(); retry up to `retries` times with exponential backoff."""
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
            time.sleep(delay)
            delay *= 2
