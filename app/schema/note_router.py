"""
note_router.py
--------------
Give the model the guidance THIS question needs, instead of all of it.

Every data note, join hint and value code used to be injected on every question:
~10k tokens of notes inside a ~25k-token prompt, 48 competing rules. That is a
known reliability killer — long, mostly-irrelevant context degrades instruction
following ("lost in the middle"), and it showed up as the same question answering
well once and thinly the next time.

So we route the NOTES the same way the schema router already routes TABLES:
score each note against the question, keep the ones that match, and always keep a
small set of ALWAYS-ON notes that protect against wrong answers regardless of
topic (data cutoff, identity/display rules, count inflation).

This is selection, not hard-coding: nothing is tied to a fixed question list. A
note is chosen because its own words match what was asked, so new notes and new
questions work automatically.
"""
from __future__ import annotations

import re

# Notes that must survive routing: they prevent WRONG ANSWERS on any topic, not
# just their own. Matched as substrings against the start of a note.
# Verified against the real note headings — a marker that matches nothing would
# silently stop protecting the answer, so tests assert each one still appears.
_ALWAYS_ON = (
    "DATA CUTOFF",            # backup, not live -> "today" returns 0 rows
    "COUNT DISTINCT",         # COUNT(*) on transactional tables over-counts
    "EMPLOYEE ROSTER",        # active-only default, dummy 'EXTRA' accounts
    "PACKET IDENTITY",        # PacketNo is not unique across kapans
    "DATE COLUMNS",           # each table's real date column
    "KNOWN-EMPTY TABLES",     # don't query dead tables
    "SALARY / PAYROLL",       # restricted data — must never be forgotten
    "Some columns are misspelled",   # Florecent etc. — breaks any query
)

_STOP = {
    "the", "a", "an", "of", "for", "and", "or", "in", "on", "to", "me", "my",
    "give", "show", "get", "list", "what", "which", "how", "many", "much", "is",
    "are", "was", "were", "do", "does", "did", "please", "report", "data", "all",
    "from", "by", "with", "that", "this", "it", "we", "our", "you", "can",
}


def _tokens(text: str) -> set[str]:
    """Lowercase word set, stop-words removed, short words dropped."""
    words = re.findall(r"[a-z0-9_]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _is_always_on(note: str) -> bool:
    head = note[:60].upper()
    return any(k in head for k in _ALWAYS_ON)


def score_note(note: str, q_tokens: set[str]) -> int:
    """
    How relevant is this note to the question?

    Rare, meaningful words carry the signal (a note mentioning 'jangad' when the
    user said 'jangad'), so we simply count shared terms — table names like
    tblJangadPackets tokenise into the same words, which is why an exact-keyword
    approach works well here without embeddings.
    """
    return len(q_tokens & _tokens(note))


def select_notes(
    notes: list[str],
    question: str,
    # min_score MUST stay 1: a note often shares only one distinctive token with
    # the question ("damage" -> the damage note). Raising it to 2 silently dropped
    # the damage and stock-report guidance (caught by test_note_router).
    max_notes: int = 10,
    min_score: int = 1,
) -> list[str]:
    """
    Return the always-on notes plus the best-matching ones for `question`.

    Order is preserved from the source list so the prompt stays stable between
    turns (a stable prefix is also friendlier to prompt caching).
    """
    q = _tokens(question)
    if not q:
        return list(notes)

    keep: list[str] = []
    scored: list[tuple[int, int]] = []          # (score, original index)
    for i, note in enumerate(notes):
        if _is_always_on(note):
            keep.append(note)
        else:
            s = score_note(note, q)
            if s >= min_score:
                scored.append((s, i))

    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen = {i for _, i in scored[:max_notes]}
    picked = [n for i, n in enumerate(notes) if i in chosen]

    # Preserve source order across both groups.
    out, seen = [], set()
    for note in notes:
        if (note in keep or note in picked) and note not in seen:
            seen.add(note)
            out.append(note)
    return out


def select_mapping(
    mapping: dict[str, str],
    question: str,
    max_items: int = 12,
) -> dict[str, str]:
    """Same idea for key->meaning maps (VALUE_CODES, GUJLISH_TERMS)."""
    q = _tokens(question)
    if not q:
        return dict(mapping)
    scored = []
    for k, v in mapping.items():
        s = len(q & _tokens(f"{k} {v}"))
        if s:
            scored.append((s, k))
    scored.sort(key=lambda t: -t[0])
    keys = {k for _, k in scored[:max_items]}
    return {k: v for k, v in mapping.items() if k in keys}
