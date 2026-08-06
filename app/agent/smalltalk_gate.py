"""
smalltalk_gate.py
-----------------
DETERMINISTIC greeting / thanks / acknowledgement short-circuit.

The problem this fixes: "hi" took 5-10 seconds and burned a full turn. Every
message — including a one-word greeting — was shipping the ~29k-token system
prompt (RULES + full schema + glossary) and the whole tool-definition block to
the provider, then waiting on the tool loop. For "hi" that is a round trip and
a five-figure token count to say "hello".

Same family as date_gate and access_guard: decided in CODE, before any LLM call.
Instant, free, and it cannot regress when a provider changes.

DELIBERATELY PARANOID — it fires only when the ENTIRE message is smalltalk:
  * the whole normalised string must be in _SMALLTALK, not merely start with it,
    so "hi, how many packets are on jangad?" goes to the model untouched;
  * a length cap on top of that, so a long sentence can never match by accident;
  * nothing here is a substring/regex search over the question. A greeting gate
    that eats a real question is far worse than one that misses a "hii".

Anything not matched falls through completely unchanged.
"""
from __future__ import annotations

import re

# Longest real smalltalk phrase we accept ("jai shree krishna" = 17). Anything
# longer is a sentence, and a sentence is a question until proven otherwise.
_MAX_LEN = 24

# The whole message must equal one of these once normalised. Gujlish included:
# the client's staff greet in transliterated Gujarati as often as in English.
_SMALLTALK: frozenset[str] = frozenset({
    # --- greetings (en) ---
    "hi", "hii", "hiii", "hey", "heyy", "hello", "helo", "hallo", "yo",
    "good morning", "good afternoon", "good evening", "gm", "gud morning",
    # --- greetings (gujlish / hinglish) ---
    "namaste", "namaskar", "kem cho", "kemcho", "kem chho", "jai shree krishna",
    "jay shree krishna", "ram ram", "salaam", "aadab",
    # --- thanks ---
    "thanks", "thank you", "thank u", "thanku", "thx", "tnx", "ty",
    "thanks a lot", "many thanks", "dhanyavad", "aabhar", "abhar",
    # --- acknowledgement / closing ---
    "ok", "okay", "k", "kk", "fine", "good", "nice", "great", "cool", "perfect",
    "done", "got it", "gotit", "understood", "noted", "sure", "alright",
    "bye", "goodbye", "good bye", "see you", "see ya", "ok bye", "tata",
    "good night", "gn",
})

# Which canned reply to send. Kept separate from matching so the reply can be
# tuned without touching the (safety-critical) match set.
_THANKS = frozenset({
    "thanks", "thank you", "thank u", "thanku", "thx", "tnx", "ty",
    "thanks a lot", "many thanks", "dhanyavad", "aabhar", "abhar",
})
_BYE = frozenset({
    "bye", "goodbye", "good bye", "see you", "see ya", "ok bye", "tata",
    "good night", "gn",
})
_ACK = frozenset({
    "ok", "okay", "k", "kk", "fine", "good", "nice", "great", "cool",
    "perfect", "done", "got it", "gotit", "understood", "noted", "sure",
    "alright",
})

# The greeting reply doubles as the scope statement: it tells a first-time user
# what this assistant is for, which is the moment they are most likely to ask
# it for something out of scope (see the SCOPE rule in tools.py).
_GREETING_REPLY = (
    "Hello! I'm the GlowStar assistant — I answer questions about your "
    "factory data: production, packets and kapans, planning and GIA results, "
    "jangad, stock, damage and departments.\n\n"
    "What would you like to look at?"
)
_THANKS_REPLY = "Happy to help! Anything else you'd like me to pull up?"
_BYE_REPLY = "Goodbye! I'm here whenever you need the factory numbers."
_ACK_REPLY = "Got it. What would you like to check next?"

_SUGGESTIONS = [
    "How many packets are on jangad?",
    "Show this month's GIA results",
    "Department wise production summary",
]


def _normalise(question: str) -> str:
    """Lowercase, strip punctuation/emoji-ish trailing chars, squeeze spaces."""
    q = (question or "").strip().lower()
    # Drop leading/trailing punctuation only — never inner characters, so an
    # inner "?" (i.e. a real question) survives and fails the equality test.
    q = re.sub(r"^[\s!.,\-–—]+|[\s!.,\-–—?]+$", "", q)
    return re.sub(r"\s+", " ", q)


def is_smalltalk(question: str) -> bool:
    """True only when the WHOLE message is a greeting / thanks / acknowledgement."""
    q = _normalise(question)
    if not q or len(q) > _MAX_LEN:
        return False
    return q in _SMALLTALK


def smalltalk_response(question: str) -> dict:
    """
    The turn we return INSTEAD of calling the model. Shaped exactly like
    date_gate.ask_date_response so every caller (/chat and /chat/stream) can
    return it unchanged.
    """
    q = _normalise(question)
    if q in _THANKS:
        answer = _THANKS_REPLY
    elif q in _BYE:
        answer = _BYE_REPLY
    elif q in _ACK:
        answer = _ACK_REPLY
    else:
        answer = _GREETING_REPLY

    return {
        "answer": answer,
        # Only offer starters on an opening greeting — after "thanks" or "bye"
        # the user is finishing, and three prompts would be nagging.
        "suggestions": _SUGGESTIONS if answer == _GREETING_REPLY else [],
        "clarify_options": [],
        "ask_date": False,
        "citation": "",
        "export_query": None,
        "sql_used": [],
        "rows_returned": 0,
        "ok": True,
        "widgets": [],
        "data_columns": [],
        "data_rows": [],
    }
