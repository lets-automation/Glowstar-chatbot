"""
lab_gate.py
-----------
DETERMINISTIC "which lab?" check for a PENDING question.

THE CLIENT'S RULE, given 2026-08-31: a pending question counts ALL labs by
default (GIA + HRD + IGI, not GIA alone), and the bot must ASK which lab before
answering rather than assume.

Same family as date_gate, access_guard and smalltalk_gate: decided in CODE,
before any LLM call. That makes it instant, free, and unable to regress when a
provider changes - and a prompt RULE would not do here anyway, because the model
has repeatedly read "GIA pending" as "the lab is GIA" and silently dropped the
other two.

WHY THE QUESTION IS MEANINGFUL AT ALL
-------------------------------------
A pending stone has been to NO lab, so it has no lab stage row to read a lab
off. The destination is recorded on the PLS row instead, in tblPlanMaster.LAB -
see reports.pending_lab_report. Without that column this follow-up would be
unanswerable and asking it would be cruel.

THE LOOP THIS MUST NOT CAUSE
----------------------------
Tapping a clarify chip SENDS ITS TEXT as the next question (see
useGlowstarRuntime.js). So a chip reading "...for all labs" comes straight back
in here, and if "all labs" did not COUNT as an answer the gate would ask the
same question forever. _ALL_LABS_RE is what breaks that cycle, and
test_lab_gate pins it.
"""
from __future__ import annotations

import re

# The three labs this factory grades at. tblPlanMaster.LAB also holds 'NONE',
# which is not a lab - it means the stone is not going to one - so it is never
# offered as a choice.
LABS = ("GIA", "HRD", "IGI")

_NAMED_LAB_RE = re.compile(r"\b(gia|hrd|igi)\b", re.IGNORECASE)

# An explicit "all of them". This is what makes the chip safe to re-send: the
# text comes back, matches here, and the gate stands down instead of re-asking.
# "both" is included because with three labs a user who types it has still
# clearly refused to narrow.
_ALL_LABS_RE = re.compile(
    r"\ball\s+(the\s+)?(labs?|three|3)\b|\ball\s+lab\b|\bevery\s+lab\b|"
    r"\bany\s+lab\b|\bboth\b|"
    r"\bbadha\s+lab\b|\bbadhi\s+lab\b|\bbadha\b.{0,12}\blab\b",  # Gujlish
    re.IGNORECASE,
)

# A pending question. Kept HERE rather than in recipe_router so the router and
# the gate cannot drift apart about what counts as one - the router imports
# these back out (see recipe_router.named_lab / is_pending_lab_question).
_PENDING_RE = re.compile(
    r"\bpending\b|\bbaki\b|\bnot\s+yet\b|\bawait", re.IGNORECASE)

# ...and it must clearly be about the LAB stage. A bare "how many were pending"
# names no stage, and guessing one is how the completed-work report came to
# answer a pending question in the first place.
_PENDING_STAGE_RE = re.compile(
    r"\b(gia|hrd|igi|lab|certification|certificate|pls|polish(ed)?|assort)",
    re.IGNORECASE)


def named_lab(question: str) -> str:
    """The single lab named in the question, or "" for none / more than one.

    Naming two labs deliberately falls back to ALL, which is the safe
    direction: a wider count, not a silently narrower one.
    """
    found = {m.group(1).upper() for m in _NAMED_LAB_RE.finditer(question or "")}
    return found.pop() if len(found) == 1 else ""


def is_pending_lab_question(question: str) -> bool:
    """True for 'polished but still waiting for the lab' in any of its forms."""
    q = question or ""
    return bool(_PENDING_RE.search(q) and _PENDING_STAGE_RE.search(q))


def states_lab_choice(question: str) -> bool:
    """True if the text already settles which lab(s) to count."""
    q = question or ""
    return bool(named_lab(q) or _ALL_LABS_RE.search(q))


# How many recent USER turns can still supply the lab choice. Matches
# date_gate._PERIOD_MEMORY_TURNS and exists for the same reason: after the user
# has answered "GIA", the follow-ups off that answer ("and kapan wise", "now
# for MFG-2") must not each re-ask. Note the explicit <= 0 guard - `list[-0:]`
# is the WHOLE list, so a naive slice turns "no memory" into "unlimited".
_LAB_MEMORY_TURNS = 2


def lab_choice_in_history(history: list[dict] | None) -> bool:
    """True if a recent USER turn already settled which lab(s) to count."""
    if _LAB_MEMORY_TURNS <= 0:
        return False
    recent = [
        m.get("content", "") or ""
        for m in (history or [])
        if m.get("role") == "user"
    ][-_LAB_MEMORY_TURNS:]
    return any(states_lab_choice(text) for text in recent)


def remembered_lab(history: list[dict] | None) -> str:
    """The lab from the most recent user turn that named exactly one.

    "" when the most recent choice was ALL labs, so an explicit "all labs"
    correctly clears an earlier "GIA" instead of being overridden by it.
    """
    if _LAB_MEMORY_TURNS <= 0:
        return ""
    recent = [
        m.get("content", "") or ""
        for m in (history or [])
        if m.get("role") == "user"
    ][-_LAB_MEMORY_TURNS:]
    for text in reversed(recent):          # most recent wins
        if states_lab_choice(text):
            return named_lab(text)
    return ""


def needs_lab(question: str, history: list[dict] | None = None) -> bool:
    """Should we ask which lab instead of answering?

    Only for a pending LAB question that has not already settled the choice,
    itself or in the recent conversation.
    """
    q = (question or "").strip()
    if not q or not is_pending_lab_question(q):
        return False
    if states_lab_choice(q):
        return False
    return not lab_choice_in_history(history)


def ask_lab_response(question: str) -> dict:
    """The turn we return INSTEAD of querying.

    Shaped like a normal enriched result so both /chat and /chat/stream can
    return it unchanged, exactly as they do for date_gate.ask_date_response.

    Each option is a COMPLETE question, because tapping a chip sends its text
    as the next question. The all-labs option is first: it is the client's
    default, and it is the one that must be one tap away.
    """
    subject = (question or "pending work").strip().rstrip("?.")
    return {
        "answer": (
            f"Which lab should I count for “{subject}”?\n\n"
            "By default I count all three — GIA, HRD and IGI."
        ),
        "suggestions": [],
        "clarify_options": [f"{subject} for all labs"]
                           + [f"{subject} for {lab} only" for lab in LABS],
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
