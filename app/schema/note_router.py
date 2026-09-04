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

import math
import re
from functools import lru_cache

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
    # Added 2026-08-20. Both of these describe columns that DO NOT EXIST where a
    # model expects them, so getting them wrong is an invalid-column error and an
    # empty report - not a slightly-worse answer. They were losing the top-10
    # ranking cut to merely-relevant notes: a live "report of department MFG - 1"
    # wrote WHERE DepartmentName=... against tblPlanMaster nine times because
    # this guidance never reached the prompt. Correctness traps must not compete
    # for a slot.
    "SUBSTITUTE THESE COLUMNS",   # IsApproved not IsVerified; kapan-level hold
    "DEPARTMENT IS NOT A COLUMN", # dept resolves via tblEmployee.EmpId only
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
    # UPPER-CASE BOTH SIDES. The head is upper-cased, so a marker that is not
    # itself all-caps can never match it. Every marker was ALL-CAPS except
    # "Some columns are misspelled", so that one note - the one that says an
    # expected column may be stored misspelled (Florecent/Florocent) - was
    # silently NOT always-on. It reached the prompt only when the question
    # already contained a matching word, i.e. it scored in topically; measured
    # 2026-08-25 as absent from all 59 questions of the audit corpus.
    head = note[:60].upper()
    return any(k.upper() in head for k in _ALWAYS_ON)


@lru_cache(maxsize=8)
def _doc_freq(notes: tuple[str, ...]) -> dict[str, int]:
    """How many notes each token appears in. Cached per note corpus."""
    df: dict[str, int] = {}
    for note in notes:
        for tok in _tokens(note):
            df[tok] = df.get(tok, 0) + 1
    return df


def _idf(notes: tuple[str, ...]) -> dict[str, float]:
    """Inverse document frequency: how much evidence one shared token is worth."""
    df = _doc_freq(notes)
    total = len(notes) or 1
    return {tok: math.log(total / n) for tok, n in df.items() if n}


def score_note(note: str, q_tokens: set[str], idf: dict[str, float] | None = None) -> float:
    """
    How relevant is this note to the question?

    RARE WORDS CARRY THE SIGNAL, AND THEY HAVE TO BE WEIGHTED THAT WAY.
    ------------------------------------------------------------------
    This used to be a flat `len(q_tokens & _tokens(note))` — every shared word
    worth one point. That is the same mistake the TABLE router already fixed
    with _WEAK_COLUMN_TOKENS: across 53 notes, a common word matches nearly
    everything and buries the note that actually answers the question.

    Measured on "damage report kapan wise for this year" before this change:
      damage  appears in  2 of 53 notes   (the whole signal)
      kapan   appears in 10 of 53
      year    appears in  5 of 53
    All three scored 1. Nine notes tied at 1, the top-10 cut fell to source
    order, and "DAMAGE IS POINTS, NOT RUPEES — tblPlanReport.Amount = Points x
    Rate" — the ONE note that says a damage amount is not rupees — did not make
    the prompt. The 548-token stock-report note did.

    Weighting by log(N/df) makes 'damage' worth about twice 'kapan' and breaks
    the ties that were being resolved by luck. `idf` is optional so the plain
    count remains available (and so any caller passing two arguments still works).
    """
    shared = q_tokens & _tokens(note)
    if idf is None:
        return float(len(shared))
    return sum(idf.get(tok, 1.0) for tok in shared)


# Drop a note scoring far below the best match rather than padding the list to
# max_notes with noise. Mirrors _RELATIVE_FLOOR in app/schema/router.py, which
# exists for the same reason and against the same failure: long, mostly
# irrelevant context is a known reliability killer on small models.
_RELATIVE_FLOOR = 0.35
# ...but never starve a weak-signal question completely.
_MIN_NOTES = 4


def select_notes(
    notes: list[str],
    question: str,
    # min_score MUST stay >0: a note often shares only one distinctive token with
    # the question ("damage" -> the damage note). Requiring two silently dropped
    # the damage and stock-report guidance (caught by test_note_router). With IDF
    # weighting a single RARE token clears this comfortably while a single common
    # one no longer does - which is the point.
    max_notes: int = 10,
    min_score: float = 0.75,
) -> list[str]:
    """
    Return the always-on notes plus the best-matching ones for `question`.

    Order is preserved from the source list so the prompt stays stable between
    turns (a stable prefix is also friendlier to prompt caching).
    """
    q = _tokens(question)
    if not q:
        # NOTHING RECOGNISABLE IN THE QUESTION. This used to `return list(notes)`
        # - every note, unrouted - and it fires on ordinary phrasing, because
        # _tokens() drops stop-words and any word of two characters or fewer:
        # "give me the report", "show all data", "how many" and "ok give report"
        # all reduce to an empty set. Measured 2026-08-21: those questions were
        # shipping 17,652 tokens of notes against ~7,000 for a specific one, so
        # the vaguest questions - where the model most needs focus - got the
        # LEAST focused prompt, a 46% larger overall prompt, and 48 competing
        # rules. Returning everything is not the conservative choice here; it is
        # the least conservative one. A question with no recognisable content is
        # evidence for no topical note, so send the safety notes and let the
        # model ask or explore.
        # JOIN_HINTS carry no always-on markers, so this returns [] for them -
        # deliberately. A question with no recognisable word cannot be helped by
        # a join hint, and the hints are 3,151 tokens. render_data_notes() skips
        # an empty section, and the model still has the rules and the schema.
        return [n for n in notes if _is_always_on(n)]

    idf = _idf(tuple(notes))
    keep: list[str] = []
    scored: list[tuple[float, int]] = []        # (score, original index)
    for i, note in enumerate(notes):
        if _is_always_on(note):
            keep.append(note)
        else:
            s = score_note(note, q, idf)
            if s >= min_score:
                scored.append((s, i))

    scored.sort(key=lambda t: (-t[0], t[1]))
    if scored:
        cutoff = scored[0][0] * _RELATIVE_FLOOR
        strong = [t for t in scored if t[0] >= cutoff]
        scored = strong if len(strong) >= _MIN_NOTES else scored[:_MIN_NOTES]
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
    """Same idea for key->meaning maps (VALUE_CODES, GUJLISH_TERMS).

    NOTE the two different empty cases, which are NOT the same thing:
      * question is None/"" -> no routing was requested at all (tests, offline
        inspection, render_data_notes() with no argument). Return everything.
      * question has no recognisable tokens ("show all data") -> routing WAS
        requested and found nothing. Return nothing, for the same reason
        select_notes() does: a value code cannot help a question with no
        content, and the two maps are 1,656 tokens.
    """
    if not (question or "").strip():
        return dict(mapping)
    q = _tokens(question)
    if not q:
        return {}
    scored = []
    for k, v in mapping.items():
        s = len(q & _tokens(f"{k} {v}"))
        if s:
            scored.append((s, k))
    scored.sort(key=lambda t: -t[0])
    keys = {k for _, k in scored[:max_items]}
    return {k: v for k, v in mapping.items() if k in keys}
