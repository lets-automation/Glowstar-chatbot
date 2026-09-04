"""
date_gate.py
------------
DETERMINISTIC "which period?" check for report questions.

The client asked that any report/date-related question prompt for a date range
instead of silently answering. A prompt RULE alone is not reliable — the model
answered "give me the damage report of department MFG - 1" with all 484 records
spanning two years. So this gate decides in CODE, before any LLM call:

    report-style question  AND  no period mentioned   ->  ask for the date

Being deterministic also makes it instant and free (no tokens burned), and it
can't regress when a provider changes.

Deliberately conservative: it only fires when the question clearly asks for a
REPORT/listing AND carries no hint of a time period, so ordinary questions
("how many employees do we have", "what is a kapan") flow straight through.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

import re

# Question is asking for a report / listing over some period. Includes the
# Gujlish words the client's staff actually type.
_REPORT_RE = re.compile(
    r"\b("
    r"report|production|output|stock|damage|jangad|earning|earnings|salary|wages|"
    r"incentive|bonus|result|results|certification|gia|hrd|igi|yield|loss|"
    r"repair|rejection|attendance|summary|breakdown|performance|"
    r"utpadan|nuksan|pagar|hisab"          # Gujlish: production/loss/pay/accounts
    r")\b",
    re.IGNORECASE,
)

# "-wise" style asks (kapan wise, employee wise, department wise) are reports too.
_WISE_RE = re.compile(r"\b\w+[\s-]?wise\b", re.IGNORECASE)

# Any hint of a time period. If ANY of these appear we do NOT ask.
_PERIOD_RE = re.compile(
    r"("
    # Month names — spelled out in full or as the standard abbreviation. NOT a
    # loose prefix: "jan[a-z]*" also matched "JANgad" (the trade term) and
    # suppressed the date prompt on every jangad report.
    r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july"
    r"|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b"
    r"|\b(19|20)\d{2}\b"                                            # a year
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"                               # 01/06/2026
    r"|\d{4}-\d{2}-\d{2}"                                           # 2026-06-01
    r"|\b(to|from|between|since|till|until|upto|up to)\b.*\d"       # from 1 to 26
    r"|\btoday|yesterday|tomorrow\b"
    r"|\b(this|last|past|previous|current|next)\s+"
    r"(month|week|year|quarter|day|days|months|weeks|years|fortnight)\b"
    r"|\blast\s+\d+\s+(day|days|month|months|week|weeks|year|years)\b"
    r"|\b(mtd|ytd|q[1-4])\b"
    r"|\b(all\s*time|alltime|overall|ever|till\s*date|to\s*date|so\s*far|lifetime)\b"
    r"|\b(aaje|kaale|aa\s*mahine|gaya\s*mahine|varas|mahina|mahine)\b"  # Gujlish
    r")",
    re.IGNORECASE,
)


# "What is the situation RIGHT NOW" questions. These have no period by nature
# (stock on hand, packets currently out on jangad), so asking for dates would be
# nonsense — answer them directly.
_CURRENT_STATE_RE = re.compile(
    r"\b(currently|right now|at present|as of now|pending|on hold|"
    # WIP is a LIVE snapshot ("what is in each department now"), never a period.
    r"in[\s-]?process|in[\s-]?processing|work[\s-]?in[\s-]?process|wip|"
    # "how many X in stock" is a LIVE snapshot - asking for a date range is
    # nonsense. Found by the cold test: "how many oval diamonds do we have in
    # stock?" was answered with a date picker.
    r"in\s+stock|on\s+hold|stock\s+ma|hold\s+par|atyare|abhi|right\s+now|"
    # "on jangad" is the SAME live snapshot as "in stock" / "on hold": packets
    # still out with a vendor (tblJangadPackets.IsReceived=0). Without it,
    # "how many packets are on jangad" - the default question in
    # scripts/e2e_check.py - was answered with a date picker, and picking a
    # month then answers "sent on jangad in June", which is not what was asked.
    # Added 2026-08-27 after probing the live gate.
    # Bare "jangad" is deliberately NOT here: it is in _REPORT_RE, and
    # "jangad report" with no period must still ask, or it answers over all
    # history. Only the present-tense phrasings are carved out.
    r"on\s+jangad|jangad\s+(par|ma)\b|"
    # "aaje" / "aaj" = TODAY. Missing here, so "Aaje factory ma total ketla
    # mansu chhe?" (how many workers today) was treated as a bounded period
    # and answered with a scope-check banner instead of a headcount.
    # Found by the cold test 2026-08-26 (EDA-1). "atyare"/"abhi" were already
    # here; the Gujarati word for today was not.
    r"\baaje\b|\baaj\b|\baajey\b|\btoday\b|\bcurrent\s+headcount\b|"
    # Gujlish POSSESSIVE forms of the same snapshot. "stock ma" (in stock) was
    # already here; "stock na / stock no / stock nu" (OF the stock) was not, so
    # "our stock na stone no average depth % ketlo che?" got a date picker.
    # Found by the cold test 2026-08-26, exactly like the "in stock" case above.
    r"stock\s+n[aou]\b|stock\s+ni\b|"
    # THE CUT-PURITY CHANGE REPORT IS SCOPED BY KAPAN, NOT BY TIME. A kapan is
    # one batch of rough worked through the factory, so "cut purity change of
    # NI26" is complete as asked; the word "report" in it would otherwise put a
    # date picker in front of the one report that matches their ERP exactly.
    # See recipe_router._CUT_PURITY_RE, which routes the same questions.
    r"cut[\s-]*(and|&|/|vs[.]?|versus)?[\s-]*(purity|clarity)|"
    r"(purity|clarity)[\s-]*(and|&|/|vs[.]?|versus)?[\s-]*cut|"
    # A CHARACTERISTIC of the goods is not a flow through time. Average depth,
    # colour, clarity, shape and size describe what the stones ARE; asking which
    # month to compute them over is nonsense. Deliberately requires the
    # average/percentage word next to the attribute, so "production by colour
    # last month" (a genuine period question) is untouched.
    r"(average|avg|mean)\b.{0,30}\b(depth|table|size|weight|wt|colour|color|"
    r"clarity|purity|shape|carat|cut|polish|symmetry)\b|"
    r"(where|which|what)\b.{0,40}\b(is|are)\b.{0,20}\b(in stock|out|now))\b",
    re.IGNORECASE,
)


# A NAMED KAPAN IS ITS OWN SCOPE - THERE IS NO DATE TO GIVE.
#
# Reported live 2026-09-03. "For kapan OR26, show packets where the MFG grade
# differs from the GIA grade on cut or clarity" was answered with the date
# picker: _REPORT_RE matches the bare word "gia", the question names no month,
# so needs_date fired BEFORE any LLM call and the bot asked for a date range
# for a question that has no time dimension at all.
#
# A kapan is a discrete parcel of rough, not a period. It is opened, worked and
# closed over whatever span it takes; "which month?" is the wrong question, and
# answering one would WRONGLY narrow the result to the plan rows that happen to
# fall inside it. Same argument as _CURRENT_STATE_RE above - the scope is
# already pinned, just not by a date.
#
# "KAPAN WISE" IS THE EXCEPTION AND MUST STILL ASK. "kapan wise production" is
# a real report across all kapans and does need a period, so the pattern
# requires an actual kapan CODE beside the word. Names are 2-4 chars in three
# shapes only (checked over all 865: 'IK', 'IA25', '21WD'), matched as a whole
# token - "wise" cannot satisfy it.
#
# Both word orders occur: "kapan OR26" in English and "OQ26 kapan ma" in the
# Gujlish the client actually types (cold case COLD-07).
def names_a_kapan(question: str) -> bool:
    """True when the question is scoped to a SPECIFIC kapan by name.

    NO NAME-SHAPE PATTERN HERE. The first version matched a hand-written
    "2-4 chars in three shapes" regex, read off the 865 kapans that happened
    to exist the day it was written - a guess that stops working the day the
    client names one differently, and a second place to keep in step with the
    router.

    It asks the router instead, which resolves the token EXACTLY against the
    live tblKapan list. A kapan is a kapan because the database says so.
    "kapan wise" resolves to nothing and still gets the picker, which is
    right: that is a report ACROSS kapans and it does need a period.

    Imported inside the function - recipe_router imports reports, a far
    heavier module than this gate wants to pull in at import time.
    """
    from app.agent.recipe_router import kapan_in

    try:
        name, _ = kapan_in(question or "")
    except Exception:
        # The gate must never take the app down over an unreachable database.
        # Falling back to "no kapan named" just means the picker still shows.
        return False
    return bool(name)


def asks_current_state(question: str) -> bool:
    """True for 'what's the situation now' questions (no period applies)."""
    return bool(_CURRENT_STATE_RE.search(question or ""))


def mentions_period(question: str) -> bool:
    """True if the text already pins down a time period (so we must NOT ask)."""
    return bool(_PERIOD_RE.search(question or ""))


def is_report_question(question: str) -> bool:
    """True if the user is asking for a report / listing (not a definition)."""
    q = question or ""
    return bool(_REPORT_RE.search(q) or _WISE_RE.search(q))


# How many recent user turns can still supply the period. The picker sends the
# range back as its own turn, and people then ask two or three follow-ups off it
# ("now damage", "and kapan wise") before moving on. Beyond a few turns the
# conversation has usually moved to a new topic, so asking again is right.
# The period the user already gave is remembered for this many recent USER turns.
#
# It was 3, then 1, and both LEAKED - because remembering only SILENCED the
# picker and then trusted the model to notice the period sitting in the history.
# It did not: "give me report of department MFG - 1 for July 2026" followed by
# "provide report of department MFG - 1" suppressed the picker and the model then
# queried ALL of history and blew the context ("That request was too large").
# Measured twice on 2026-08-20.
#
# So it was switched OFF, and the client hit the other half of the problem in the
# demo: they said "may month", and the very next turn asked them which month
# again. Re-asking for a period that is on screen reads as broken.
#
# What makes it safe now is the fix the old comment prescribed: the remembered
# period is INJECTED into the request (see carried_period() below and its use in
# tools.system_prompt_for), not left for the model to spot. 2 turns is deliberate
# - long enough for "now damage" / "and kapan wise" follow-ups, short enough that
# a genuinely new topic three turns later asks again.
_PERIOD_MEMORY_TURNS = 2


def period_in_history(history: list[dict] | None) -> bool:
    """True if a recent USER turn already pinned down a period.

    NOTE the explicit 0 check: `list[-0:]` is `list[0:]`, i.e. the WHOLE list,
    so a naive slice would turn "no memory" into "unlimited memory" - the exact
    opposite of what the constant says.
    """
    if _PERIOD_MEMORY_TURNS <= 0:
        return False
    recent = [
        m.get("content", "")
        for m in (history or [])
        if m.get("role") == "user"
    ][-_PERIOD_MEMORY_TURNS:]
    return any(mentions_period(text) for text in recent)


def needs_date(question: str, history: list[dict] | None = None) -> bool:
    """
    Should we show the date picker instead of answering?

    Only when the question reads like a report AND no period is known - from the
    question itself OR from the recent conversation.

    `history` was declared and documented here from the start but never actually
    read, and main.py never passed it. So the picker re-asked on every follow-up:
    the user picked "June 2026", then "now the damage report" put the picker back
    on screen, and again for the next follow-up. The period the user already
    chose is right there in the conversation - use it.
    """
    q = (question or "").strip()
    if not q or len(q) < 3:
        return False
    if mentions_period(q) or asks_current_state(q) or names_a_kapan(q):
        return False
    if period_in_history(history):
        return False
    return is_report_question(q)


def ask_date_response(question: str) -> dict:
    """
    The turn we return INSTEAD of querying: a short question plus the flag the
    UI uses to render the date picker. Shaped like a normal enriched result so
    every caller (both /chat and /chat/stream) can return it unchanged.
    """
    subject = (question or "that report").strip().rstrip("?.")
    return {
        "answer": (
            f"Sure — which period should I cover for “{subject}”?\n\n"
            "Pick a period below, or choose custom dates."
        ),
        "suggestions": [],
        "clarify_options": [],
        "ask_date": True,
        "citation": "",
        "export_query": None,
        "sql_used": [],
        "rows_returned": 0,
        "ok": True,
        "widgets": [],
        "data_columns": [],
        "data_rows": [],
    }

# ---------------------------------------------------------------------------
# CARRYING THE PERIOD INTO THE NEXT TURN
# ---------------------------------------------------------------------------
# Suppressing the picker is only half of it. The period must reach the SQL, or
# the follow-up silently answers over all history - which is worse than asking.
_CARRIED: ContextVar[str] = ContextVar("carried_period", default="")


def remembered_period(history: list[dict] | None) -> str:
    """The period phrase from the most recent user turn that named one."""
    if _PERIOD_MEMORY_TURNS <= 0:
        return ""
    recent = [
        m.get("content", "") or ""
        for m in (history or [])
        if m.get("role") == "user"
    ][-_PERIOD_MEMORY_TURNS:]
    for text in reversed(recent):          # most recent wins
        m = _PERIOD_RE.search(text)
        if m:
            return text.strip()[:120]
    return ""


@contextmanager
def carrying_period(history: list[dict] | None, question: str = ""):
    """Scope the carried period to ONE turn.

    Empty when the question names its own period - an explicit period in the
    current turn always beats a remembered one, or "and what about June?" would
    keep answering for May.
    """
    period = "" if mentions_period(question) else remembered_period(history)
    token = _CARRIED.set(period)
    try:
        yield
    finally:
        _CARRIED.reset(token)


def carried_period() -> str:
    return _CARRIED.get()


def carried_period_directive() -> str:
    """The block injected into the prompt so the period reaches the SQL."""
    period = _CARRIED.get()
    if not period:
        return ""
    return (
        "PERIOD CARRIED OVER FROM THE CONVERSATION: the user already said "
        + repr(period) + ". This question is a follow-up on THAT period - "
        "apply it to every query. Do NOT widen to all history, and do NOT ask "
        "for the period again; they can see it on screen." + "\n\n"
    )
