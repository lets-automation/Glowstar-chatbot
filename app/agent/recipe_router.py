"""
recipe_router.py
----------------
DECIDE THE RECIPE IN CODE, NOT IN THE MODEL.

WHY
---
The curated recipes are correct. Called directly on 2026-08-31 they return
department_report = 8 sections / 20 rows and lab_results = 4 sections / 27
rows, every figure reconciled against the client's own ERP. What fails is the
MODEL CHOOSING to call them:

    "Provide july month report of department MFG - 1"        -> no tool call
    "provide me last month GIA results ... fency department" -> no tool call

and the anti-fabrication guard then correctly refuses to show the prose it
wrote instead, so the user gets "I couldn't pull that" for a question the
system can answer perfectly.

Measured across this session: code-enforced guards score 10/10, curated
recipes score 4/4 WHEN CALLED, and the model choosing what to call scores
about 40%. So the choice is taken away from it - the same pattern as
smalltalk_gate, access_guard and date_gate, none of which has ever produced a
bug the client had to find.

WHAT THIS FIXES
---------------
  * answers the question that was asked, first, in plain language;
  * cannot fabricate - every number comes from the recipe;
  * cannot be defeated by broken English: it matches the words the staff
    actually type (aapo, kadho, nu report, joie, batavo), not fluent phrasing;
  * instant and deterministic - no provider call, so no timeout, no rate
    limit, and the same question always gives the same answer.

DELIBERATELY CONSERVATIVE
-------------------------
Fires ONLY when the recipe, the period, and any named department all resolve.
Anything else returns None and the normal agent path runs unchanged. A router
that half-matches would be worse than none.

A PENDING question IS claimed, but only when it clearly names the lab stage.
Answering "pending" out of the completed-work report is the exact bug that
started this - a GIAAmt reported for packets that had not been graded - so a
pending question routes to pending_lab_results and never to lab_results.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}

_MONTH_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b"
    r"(?:\s*month)?(?:\s*,?\s*((?:19|20)\d{2}|\d{2}))?",
    re.IGNORECASE,
)

# Relative periods, English and the Gujlish the staff actually type.
_LAST_MONTH_RE = re.compile(
    r"\b(last|past|previous|prev)\s+month\b|\bgaya?\s*mahin[aoe]\b"
    r"|\bgai\s*mahin[aoe]\b|\blast\s*mahin[aoe]\b",
    re.IGNORECASE,
)
_THIS_MONTH_RE = re.compile(
    r"\b(this|current|ongoing)\s+month\b|\baa\s*mahin[aoe]\b"
    r"|\bchalu\s*mahin[aoe]\b",
    re.IGNORECASE,
)
_THIS_YEAR_RE = re.compile(
    r"\b(this|current)\s+year\b|\baa\s*varsh\b|\bchalu\s*varsh\b", re.IGNORECASE)
_LAST_YEAR_RE = re.compile(
    r"\b(last|past|previous)\s+year\b|\bgaya?\s*varsh\b", re.IGNORECASE)

_ISO_RANGE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*(?:to|-|till|until|upto|thru|through)\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _month_span(year: int, month: int) -> tuple[str, str]:
    """(from, to) for one calendar month, `to` EXCLUSIVE.

    The recipes document an exclusive end, and an inclusive one silently drops
    the last day - the same 5% loss query_rules.date_range_exclusive exists to
    stop (3,492 against a true 3,692).
    """
    nxt_y, nxt_m = (year + 1, 1) if month == 12 else (year, month + 1)
    return f"{year:04d}-{month:02d}-01", f"{nxt_y:04d}-{nxt_m:02d}-01"


_BARE_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_TODAY_RE = re.compile(r"\btoday\b|\baaje\b|\baajna\b", re.IGNORECASE)
_YESTERDAY_RE = re.compile(r"\byesterday\b|\bkale\b|\bgai kale\b",
                           re.IGNORECASE)


def resolve_period(question: str, today: date | None = None):
    """The period this question names, as (from, to) with `to` EXCLUSIVE.

    Returns None when no period is named. The caller must NOT guess one - an
    unbounded report is the failure date_gate exists to prevent.
    """
    q = question or ""
    today = today or date.today()

    m = _ISO_RANGE_RE.search(q)
    if m:
        return m.group(1), m.group(2)

    if _TODAY_RE.search(q):
        return today.isoformat(), (today + timedelta(days=1)).isoformat()
    if _YESTERDAY_RE.search(q):
        y = today - timedelta(days=1)
        return y.isoformat(), today.isoformat()

    if _LAST_MONTH_RE.search(q):
        y, mo = ((today.year - 1, 12) if today.month == 1
                 else (today.year, today.month - 1))
        return _month_span(y, mo)
    if _THIS_MONTH_RE.search(q):
        return _month_span(today.year, today.month)
    if _LAST_YEAR_RE.search(q):
        return f"{today.year - 1}-01-01", f"{today.year}-01-01"
    if _THIS_YEAR_RE.search(q):
        return f"{today.year}-01-01", f"{today.year + 1}-01-01"

    m = _MONTH_RE.search(q)
    if m:
        month = _MONTHS[m.group(1).lower()]
        raw_year = m.group(2)
        if raw_year:
            year = int(raw_year)
            if year < 100:
                year += 2000
        else:
            # No year: the most recent occurrence, so "july" asked in Aug 2026
            # means Jul 2026 and "december" means Dec 2025.
            year = today.year if month <= today.month else today.year - 1
        return _month_span(year, month)

    # A BARE YEAR, last of all - "production for 2026" means the calendar
    # year. date_gate's _PERIOD_RE already accepts a bare year, so without
    # this the picker stays quiet AND the router declines, and the question
    # falls to free SQL. Same disagreement as "today" had. Last resort on
    # purpose: an explicit month, an ISO range or "this year" all win first,
    # and a year inside one of those has already been consumed.
    m = _BARE_YEAR_RE.search(q)
    if m:
        y = int(m.group(1))
        if 2000 <= y <= today.year + 1:
            return f"{y}-01-01", f"{y + 1}-01-01"
    return None


_REPORT_RE = re.compile(
    r"\breports?\b|\bnu\s+report\b|\bkadho\b|\baapo\b", re.IGNORECASE)
_LAB_RE = re.compile(
    r"\b(gia|hrd|igi)\b|\blab\s*(results?|wise|report)\b", re.IGNORECASE)
_RESULTS_RE = re.compile(r"\bresults?\b|\bparinam\b", re.IGNORECASE)

# "Pending" now HAS a recipe (pending_lab_results), so it is routed rather
# than declined - but only when it is clearly about the LAB. A bare "how many
# were pending" carries no stage, and guessing one is how the completed-work
# report came to answer a pending question in the first place.
#
# BOTH predicates live in lab_gate, not here. The gate decides whether to ask
# which lab and this router decides where to send the answer; if they disagreed
# about what counts as a pending question, one of them would act on a question
# the other had never seen. lab_gate imports nothing but `re`, so there is no
# cycle. Re-exported under the old names so callers and tests read unchanged.
from app.agent.lab_gate import (            # noqa: E402  (after the docstring)
    is_pending_lab_question,
    named_lab,
)

# Words that are never part of a department name. Stripped before resolution
# so "department MFG - 1" becomes "MFG 1", which reports.resolve_department
# does understand. Month names are in here too: "july month report of
# department MFG - 1" must not offer "july" as a candidate department.
_FILLER = frozenset({
    "give", "me", "my", "provide", "show", "get", "please", "want", "need",
    "report", "reports", "reporting", "summary", "detail", "details", "data",
    "of", "for", "the", "a", "an", "in", "on", "at", "to", "from", "and",
    "last", "past", "previous", "prev", "this", "current", "month", "months",
    "year", "years", "week", "day", "days",
    "employee", "employees", "worker", "workers", "karigar", "wise",
    "results", "result", "gia", "hrd", "igi", "lab", "polished", "polish",
    "department", "departments", "dept", "vibhag",
    "nu", "no", "na", "ni", "ma", "aapo", "kadho", "joie", "batavo", "che",
    "chhe", "ketla", "ketlu", "aa", "gaya", "gai", "mahine", "mahina", "varsh",
    "total", "all", "list", "give", "us", "our",
    "jan", "january", "feb", "february", "mar", "march", "apr", "april",
    "may", "jun", "june", "jul", "july", "aug", "august", "sep", "sept",
    "september", "oct", "october", "nov", "november", "dec", "december",
})

# The hint is what makes it worth tokenising at all. It listed the word
# 'department' and three department names - so "packets planned BY Blocking"
# named a department and was not even looked at. The plan_rows recipe asks
# exactly that way, so the authoring phrasings are hints too.
_DEPT_HINT_RE = re.compile(
    r"\bdepartment\b|\bdept\b|\bvibhag\b|\bmfg\b|\bfency\b|\bmarker\b"
    r"|\b(?:planned|created|made|written|done)[ ]+by\b"
    r"|\bplans?[ ]+(?:by|from)\b",
    re.IGNORECASE,
)


def department_in(question: str):
    """(resolved department, a department was NAMED).

    reports.resolve_department needs a CLEAN name - it resolves "MFG-1",
    "mfg 1" and "MFG - 1" but NOT "department MFG - 1", so the question's
    filler has to come off first. Everything that is not plausibly part of a
    department name is stripped, then the remaining 1-3 word windows are tried
    longest-first. Resolution itself stays in reports so the client's spellings
    live in one place.
    """
    from app.agent import reports

    q = question or ""
    if not _DEPT_HINT_RE.search(q):
        return None, False

    # DECIMALS FIRST. Splitting on non-alphanumerics turns "0.80" into the two
    # tokens "0" and "80", which then join a neighbouring word into windows
    # like "0 80 marker" - and that fuzzy-matches the department literally
    # named "Marker". Live 2026-09-03: "...size range from 0.3 to 0.80 for
    # marker 2 department" resolved to Marker instead of Marker-2, a different
    # department with different people. A department name never contains a
    # decimal, so they are removed before tokenising.
    q_clean = re.sub(r"\d+[.]\d+", " ", q)

    words = [w for w in re.split(r"[^A-Za-z0-9]+", q_clean) if w]
    kept = [w for w in words if w.lower() not in _FILLER]

    # A LONGER WINDOW IS NOT A BETTER MATCH. The old loop tried size 3, then 2,
    # then 1, and broke at the first size that matched ANYTHING - so a 3-word
    # window of junk that fuzzy-matched beat the clean 2-word exact match
    # sitting right next to it. Collect every candidate, then prefer an EXACT
    # name over a fuzzy one, and only then prefer the longer window.
    exact, fuzzy = [], []
    for size in (3, 2, 1):
        for i in range(len(kept) - size + 1):
            cand = " ".join(kept[i:i + size])
            if len(cand) < 3:
                continue
            dept, _ = reports.resolve_department(cand)
            if not dept:
                continue
            squash = lambda v: re.sub(r"[^a-z0-9]", "", v.lower())
            (exact if squash(cand) == squash(dept) else fuzzy).append((dept, cand))
    pool = exact or fuzzy
    if not pool:
        return None, True
    best = max(pool, key=lambda dc: len(dc[1]))
    return best[0], True


# CUT-PURITY CHANGE - the one recipe with NO period.
#
# A kapan is one batch of rough worked through the factory, so the kapan IS the
# scope; asking which month to compute it over is the same category error as
# putting a date picker on "how many are in stock". That is why this is matched
# BEFORE resolve_period, which every other recipe requires.
_CUT_PURITY_RE = re.compile(
    # SEPARATORS: 'or' and a bare comma were missing. Live 2026-09-03,
    # "show packets where the MFG grade differs from the GIA grade on cut
    # OR clarity" did not route - 'cut and clarity' did, 'cut or clarity'
    # did not - so the model wrote the comparison free-hand and returned 337
    # rows against a true 288, counting damage plans, superseded MFG rows and
    # 26 stones that were certified at HRD as 'GIA changes'.
    r"\bcut[\s-]*(and|or|&|/|,|vs\.?|versus)?[\s-]*(purity|clarity)\b"
    r"|\b(purity|clarity)[\s-]*(and|or|&|/|,|vs\.?|versus)?[\s-]*cut\b"
    r"|\bcut[\s-]*purity\b|\bhas[\s-]*change\b"
    # THE STAGE-NAMED PHRASING. "the MFG grade differs from the GIA grade"
    # names the two STAGES rather than the two attributes, and matched
    # nothing above. Deliberately narrow: it needs BOTH stage names, the
    # word 'grade', and an explicit difference word. A hit here with no
    # resolvable kapan returns None from match() and skips the lab and
    # pending branches entirely, so a loose pattern would cost those
    # recipes their questions - hence three required tokens, not two.
    r"|^(?=.*\bmfg\b)(?=.*\b(?:gia|hrd|igi)\b)(?=.*\bgrades?\b)"
    r"(?=.*(?:differ|chang|compar|mismatch))"
    ,
    re.IGNORECASE,
)

# A kapan token: two letters and an optional two-digit year (NI26, OS26, BU,
# PL, JE). Uppercase in the client's data; matched case-insensitively here and
# then resolved EXACTLY against tblKapan - never fuzzily, because OS26/OR26 and
# NI26/NS26 all exist and are different stones.
# Kapan names come in three shapes, measured over all 865 in tblKapan:
# 'IK' (629), 'IA25' (220) and '21WD' (16). The third was invisible to the
# old pattern, so sixteen real kapans could never be named at all.
_KAPAN_TOKEN_RE = re.compile(r"\b([A-Za-z]{2}\d{0,2}|\d{2}[A-Za-z]{2})\b")

# Two-letter words that are never kapan names but do match the token shape.
# Without this, "of" and "me" are offered to tblKapan on every question.
_NOT_A_KAPAN = frozenset({
    "of", "me", "my", "in", "on", "at", "to", "is", "it", "do", "we", "us",
    "no", "so", "or", "by", "as", "be", "an", "if", "vs", "up", "go",
    "nu", "na", "ni", "ma", "aa", "ke", "je", "to26",
    "gia", "hrd", "igi", "ex", "vg", "id", "pl",
})


# THIRTY-ONE REAL KAPANS ARE ORDINARY ENGLISH WORDS.
# AA, GO, IN, IS, IT, ME, MY, NO, ON, OR, TO, US, VS ... are all real kapan
# names AND all on the stopword list below, so they could never be resolved
# - 'kapan AA' appears in the client's own logs and was unanswerable.
#
# The stopword list is still right for a BARE token: offering 'of' and 'me'
# to tblKapan on every question is how you end up reporting on the wrong
# batch of diamonds. What distinguishes the two is whether the user SAID
# kapan. 'report of kapan AA' means the kapan; 'report of MFG-1' does not.
# GUJLISH POSTPOSITIONS THAT FOLLOW A NOUN, and are therefore ambiguous
# with a kapan name sitting in the same slot. 'kapan ma' means IN THE
# KAPAN, not kapan MA - and MA, NA, NI, NU, NO are all real kapan names, so
# resolving them here reports on a batch of diamonds nobody asked about.
# Caught by test_quick_facts on 'kapan ma total ketla piece hata?'.
#
# 'aa', 'ke' and 'je' are NOT here: they PRECEDE a noun in Gujarati ('aa
# kapan' = this kapan), so 'kapan AA' is unambiguous and does resolve.
#
# These stay unreachable by name, which is the right failure: the caller
# declines to route and the normal path asks which kapan was meant.
_GUJLISH_POSTPOSITION = frozenset({
    "ma", "na", "ni", "nu", "no", "ne", "thi",
})

_BEFORE_KAPAN_RE = re.compile(r"\bkapan[\s:#-]*$", re.IGNORECASE)
_AFTER_KAPAN_RE = re.compile(r"^[\s]*kapan\b", re.IGNORECASE)


def _explicitly_called_a_kapan(question: str, m) -> bool:
    """True when the word "kapan" sits immediately BEFORE this token.

    ONE DIRECTION ONLY, and deliberately. The mirror form was tried and
    reintroduced the exact bug the stopword list prevents: in "cut purity
    change OF kapan AA" the token 'of' is also immediately before the word
    kapan, so it resolved to the real kapan named OF and would have reported
    on the wrong batch of diamonds.

    'kapan AA' is unambiguous. 'AA kapan' is not - in Gujlish 'aa' means
    THIS, which is why it is on the stopword list at all. A kapan whose name
    is NOT a stopword still resolves in either order, because it never
    reaches this check.
    """
    if (m.group(1) or "").lower() in _GUJLISH_POSTPOSITION:
        return False
    return bool(_BEFORE_KAPAN_RE.search(question[:m.start()]))


# ---------------------------------------------------------------------------
# PLAN-ROW QUESTIONS - kapan-scoped, period-free, matched here rather than
# offered as tools (see the note in tools.py: TOOL_SPECS is re-sent every
# round, and two more specs blew the prompt budget outright).
# ---------------------------------------------------------------------------
_CLARITY = "FL|IF|VVS1|VVS2|VS1|VS2|SI1|SI2|I1|I2|I3"

# "purity between FL to VVS2", "clarity IF to VS2", "purity VS1-VS2"
_CLARITY_RANGE_RE = re.compile(
    r"\b(?:purity|clarity)\b[^A-Za-z0-9]{0,14}(?:between|from|of|range)?"
    r"[^A-Za-z0-9]{0,6}(" + _CLARITY + r")\b"
    r"\s*(?:to|-|–|and|thru|through|upto|up to)\s*"
    r"(" + _CLARITY + r")\b",
    re.IGNORECASE,
)

# "size range from 0.3 to 0.80", "planned weight between 0.50 and 1.00 carat"
_WEIGHT_RANGE_RE = re.compile(
    r"\b(?:size|weight|carat|cts?|wt)\b[^0-9]{0,24}"
    r"([0-9]*[.]?[0-9]+)\s*(?:to|-|–|and|upto|up to)\s*([0-9]*[.]?[0-9]+)",
    re.IGNORECASE,
)

_STAGES = "RST|CLV|ADM|MKB|MFG|PLS|GIA|HRD|IGI|LSO|BLK"

# "an approved CLV plan but no approved PLS plan yet"
# "CLV done but PLS pending"
_STAGE_GAP_RE = re.compile(
    r"\b(" + _STAGES + r")\b[^?]{0,60}?\b(?:but|and|with)?\s*"
    r"(?:no|not|without|never)\b[^?]{0,40}?\b(" + _STAGES + r")\b"
    r"|\b(" + _STAGES + r")\b[^?]{0,30}?\b(?:done|complete[d]?|finished)\b"
    r"[^?]{0,30}?\b(" + _STAGES + r")\b[^?]{0,20}?\bpending\b",
    re.IGNORECASE,
)

# "packets planned by Marker-2", "plans created by Blocking", "what X planned"
_PLANNED_BY_RE = re.compile(
    r"\bplan(?:s|ned|ning)?\b[^?]{0,20}\b(?:by|created by|made by|from)\b"
    r"|\b(?:planned|created)\s+by\b"
    r"|\bplans?\s+(?:created|made|written)\b",
    re.IGNORECASE,
)


_POSITIONAL_WORDING_RE = re.compile(
    r"\bstill\s+(?:sitting|at|on|in)\b|\bhas\s*n[o']?t\s+moved\b"
    r"|\bnot\s+moved\s+on\b|\bstuck\s+at\b|\bcurrently\s+at\b",
    re.IGNORECASE,
)


def clarity_range_in(question: str):
    """(from, to) clarity grades named in the question, or ("", "")."""
    m = _CLARITY_RANGE_RE.search(question or "")
    return (m.group(1).upper(), m.group(2).upper()) if m else ("", "")


def weight_range_in(question: str):
    """(min, max) planned carats named in the question, or (None, None).

    Ordered, so "0.80 to 0.30" still means the same band.
    """
    m = _WEIGHT_RANGE_RE.search(question or "")
    if not m:
        return None, None
    try:
        a, b = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None
    return (a, b) if a <= b else (b, a)


def stage_gap_in(question: str):
    """(done_stage, missing_stage) named in the question, or ("", "")."""
    m = _STAGE_GAP_RE.search(question or "")
    if not m:
        return "", ""
    g = [x for x in m.groups() if x]
    if len(g) < 2:
        return "", ""
    return g[0].upper(), g[1].upper()


def kapan_in(question: str):
    """(resolved kapan, a kapan-shaped token was present).

    Resolution is EXACT - see reports.resolve_kapan. A near miss resolves to
    nothing and the caller declines to route, so the normal path can ask which
    kapan they meant rather than silently reporting on the wrong batch.
    """
    from app.agent import reports

    seen = False
    for m in _KAPAN_TOKEN_RE.finditer(question or ""):
        tok = m.group(1)
        if len(tok) < 2:
            continue
        # A stopword token is skipped UNLESS the user explicitly said kapan.
        if (tok.lower() in _NOT_A_KAPAN
                and not _explicitly_called_a_kapan(question or "", m)):
            continue
        seen = True
        name, _ = reports.resolve_kapan(tok)
        if name:
            return name, True
    return None, seen


# PRODUCTION OVER TIME. Needs a PERIOD, so it is matched after the period
# gate. The BASIS is never guessed: 'made'/'manufactured'/'produced by a
# worker' is the MFG stage, anything else defaults to finished - and the
# recipe states which it used and what the other one gives.
_PRODUCTION_RE = re.compile(
    r"\bproduction\b|\bproduced\b|\bmanufactur"
    r"|\b(?:packets?|stones?|nang|diamonds?)\s+(?:were\s+)?(?:made|finished|completed)\b"
    r"|\bdiamonds?\s+processed\b|\butpadan\b",
    re.IGNORECASE,
)

# 'daily' / 'day wise' / 'date wise' -> one row per day; 'month wise' ->
# per month; otherwise a single total.
_DAILY_RE = re.compile(
    r"\bdaily\b|\bday[\s-]?wise\b|\bdate[\s-]?wise\b"
    r"|\bper\s+day\b|\beach\s+day\b|\bwith\s+date\b",
    re.IGNORECASE,
)
_MONTHLY_RE = re.compile(r"\bmonth[\s-]?wise\b|\bper\s+month\b"
                         r"|\beach\s+month\b|\bmonthly\b",
                         re.IGNORECASE)
# The MAKER's stage, not the finished stone.
_MFG_BASIS_RE = re.compile(r"\bmfg\b|\bmaker\b|\bmanufactur"
                           r"|\bkarigar\b|\bworker\b",
                           re.IGNORECASE)

# KAPAN REPORT - "show me the full packet report for kapan NS26".
# Kapan-scoped and PERIOD-FREE. Narrow on purpose: it wants a report word AND
# the kapan noun, so "how many packets in kapan X" still goes to the
# kapan_pieces fact and a damage or lab question still goes to its own recipe.
_KAPAN_REPORT_RE = re.compile(
    r"(?:packet|kapan|full|finish|estimation|summary)[ \w-]{0,14}report"
    r"|report[ \w-]{0,14}(?:of|for)[ ]+kapan"
    r"|kapan[ ]+(?:finish|estimation|summary)",
    re.IGNORECASE,
)

# EMPLOYEE REPORT - "give me the report of employee M4117 for June 2026".
# Needs a PERIOD, so it is matched after resolve_period, unlike the
# kapan-scoped recipes above. An employee CODE looks like M4117 / CL213 /
# Y126 / RE002 - letters then digits - and the name path is deliberately
# narrow, because a name is not an identity here.
_EMPLOYEE_HINT_RE = re.compile(
    r"\bemployee\b|\bkarigar\b|\bworker\b"
    r"|\bemp[\s_-]?(?:code|id)\b",
    re.IGNORECASE,
)

# An employee CODE is letters then digits: M4117, CL213, Y126, RE002.
_EMP_CODE_RE = re.compile(r"\b([A-Za-z]{1,6}[0-9]{2,4})\b")

# The words right after the noun, for "report of employee patel sureshbhai".
_EMP_NAME_RE = re.compile(r"\bemplo?y?ee\b[\s:]*"
                          r"((?:[A-Za-z]+[\s]+){0,2}[A-Za-z]+)",
                          re.IGNORECASE)

_NOT_A_NAME = frozenset({
    "code", "id", "ids", "name", "names", "wise", "report", "reports",
    "list", "details", "detail", "data", "for", "of", "the", "who",
})


def employee_in(question: str):
    """The employee CODE or name a question names, or "".

    A code is preferred and a name is a last resort - a name is not an
    identity in this database (fifteen rows share one), so the recipe it
    feeds LISTS candidates rather than picking one.
    """
    q = question or ""
    if not _EMPLOYEE_HINT_RE.search(q):
        return ""
    m = _EMP_CODE_RE.search(q)
    if m:
        return m.group(1).upper()
    m = _EMP_NAME_RE.search(q)
    if m:
        cand = m.group(1).strip()
        head = cand.split()[0].lower() if cand.split() else ""
        if head not in _NOT_A_NAME and len(cand) >= 4:
            return cand
    return ""
    m = _EMP_CODE_RE.search(q)
    if m:
        return m.group(1).upper()
    # "report of employee patel sureshbhai" - hand the words after the noun to
    # resolve_employee, which lists candidates rather than picking one.
    m = re.search(r"employee[\s:]*((?:[A-Za-z]+\s+){0,2}[A-Za-z]+)", q,
                  re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        if cand.lower() not in ("code", "id", "name", "wise", "report"):
            return cand
    return ""


def _quick_fact_spec(q: str, today):
    """A one-line fact this question asks for, with its scope resolved.

    Declines unless the scope RESOLVES: a period question with no period, or a
    kapan question with no recognisable kapan, falls through to the normal path
    rather than answering over all of history or the wrong batch of stones.
    """
    from app.agent import quick_facts

    hit = quick_facts.match(q)
    if not hit:
        return None
    needs = hit["needs"]
    if needs == "period":
        period = resolve_period(q, today)
        if not period:
            return None
        return {"recipe": "quick_fact", "fact": hit["fact"],
                "from_date": period[0], "to_date": period[1],
                "label": _period_label(period[0], period[1])}
    if needs == "kapan":
        kapan, _ = kapan_in(q)
        if not kapan:
            return None
        return {"recipe": "quick_fact", "fact": hit["fact"],
                "kapan": kapan, "label": kapan}
    return {"recipe": "quick_fact", "fact": hit["fact"], "label": ""}


def match(question: str, today: date | None = None):
    """The recipe that answers this question, or None to use the normal path."""
    q = question or ""

    # ONE-LINE FACTS FIRST. They are the narrowest match, and they are the
    # questions the model was failing to run any query for at all (35% of the
    # Gujlish corpus). A fact whose scope does not resolve returns None here
    # and the report recipes below still get their chance.
    _fact = _quick_fact_spec(q, today)
    if _fact:
        return _fact

    # NO PERIOD REQUIRED - must be decided before the period gate below.
    if _CUT_PURITY_RE.search(q):
        kapan, _ = kapan_in(q)
        if kapan:
            return {"recipe": "cut_purity_change", "kapan": kapan,
                    "lab": named_lab(q) or "GIA"}
        # Named the report but not a resolvable kapan: let the normal path ask
        # which kapan rather than picking one.
        return None

    # STAGE GAP - "has an approved CLV plan but no approved PLS plan yet".
    # Kapan-scoped and period-free, like cut_purity_change above. PLS -> a lab
    # is deliberately NOT taken here: pending_lab_results answers that better
    # because it also carries the destination lab off the PLS row.
    done, missing = stage_gap_in(q)
    if done and missing and done != missing:
        kapan, _ = kapan_in(q)
        if kapan and not (done == "PLS" and missing in ("GIA", "HRD", "IGI")):
            cf, ct = clarity_range_in(q)
            wmin, wmax = weight_range_in(q)
            return {"recipe": "stage_gap", "kapan": kapan,
                    "done_stage": done, "next_stage": missing,
                    "clarity_from": cf, "clarity_to": ct,
                    "wt_min": wmin, "wt_max": wmax,
                    "positional": bool(_POSITIONAL_WORDING_RE.search(q))}

    # PLANS CREATED BY a department, filtered on the plan row. Needs a kapan
    # AND either a "planned by" phrasing or a clarity/weight filter, so a bare
    # "MFG-1 report for July" still goes to department_report below.
    if _PLANNED_BY_RE.search(q) or clarity_range_in(q)[0]:
        kapan, _ = kapan_in(q)
        dept, named = department_in(q)
        if kapan and not (named and not dept):
            cf, ct = clarity_range_in(q)
            wmin, wmax = weight_range_in(q)
            return {"recipe": "plan_rows", "kapan": kapan,
                    "department": dept or "",
                    "clarity_from": cf, "clarity_to": ct,
                    "wt_min": wmin, "wt_max": wmax}

    # KAPAN REPORT - period-free, so it is decided before the period gate.
    # A damage / lab / grade question about a kapan belongs to its own recipe,
    # so those words disqualify it.
    if (_KAPAN_REPORT_RE.search(q)
            and not re.search(r"damage|junk|repair|gia|hrd|igi|lab|bonus"
                              r"|incentive|labour|cut|purity|clarity|pending",
                              q, re.IGNORECASE)):
        kapan, _ = kapan_in(q)
        if kapan:
            return {"recipe": "kapan_report", "kapan": kapan}

    period = resolve_period(q, today)
    if not period:
        return None

    dept, named = department_in(q)
    if named and not dept:
        # A department was named and could not be resolved - let the normal
        # path ask which one they meant rather than silently widening.
        return None

    # PENDING FIRST - it is the narrower reading, and "GIA pending results"
    # must never fall through to the completed-work report.
    if is_pending_lab_question(q):
        return {"recipe": "pending_lab_results", "from_date": period[0],
                "to_date": period[1], "department": dept or "",
                "lab": named_lab(q)}

    if _LAB_RE.search(q) and _RESULTS_RE.search(q):
        return {"recipe": "lab_results", "from_date": period[0],
                "to_date": period[1], "department": dept or ""}

    # ONE NAMED WORKER beats the department report - "report of employee
    # M4117" is about a person, not their whole department.
    who = employee_in(q)
    if who:
        return {"recipe": "employee_report", "employee": who,
                "from_date": period[0], "to_date": period[1]}

    # PRODUCTION over the period. A DEPARTMENT question stays with
    # department_report, which already breaks production down by worker.
    # A department production question belongs to department_report, which
    # already breaks production down by worker - but the router's _REPORT_RE
    # does not contain the word "production", so "Fency department production
    # for June" matched nothing at all and fell to free SQL.
    if _PRODUCTION_RE.search(q) and dept:
        return {"recipe": "department_report", "from_date": period[0],
                "to_date": period[1], "department": dept}

    if _PRODUCTION_RE.search(q) and not dept:
        bucket = ("day" if _DAILY_RE.search(q)
                  else "month" if _MONTHLY_RE.search(q) else "total")
        return {"recipe": "production_report", "from_date": period[0],
                "to_date": period[1], "bucket": bucket,
                "basis": "mfg" if _MFG_BASIS_RE.search(q) else "finished"}

    if _REPORT_RE.search(q) and dept:
        return {"recipe": "department_report", "from_date": period[0],
                "to_date": period[1], "department": dept}

    return None


# --- rendering --------------------------------------------------------------
# The recipe's own text is addressed to the MODEL ("Present ALL of them to the
# user, in this order..."). Rendering it directly would show the user their own
# instructions, so the preamble is dropped and the computed sections are kept
# exactly as the recipe produced them.
_SECTION_START = "\n## "


def _strip_model_preamble(text: str) -> str:
    i = (text or "").find(_SECTION_START)
    return text[i + 1:] if i >= 0 else (text or "")


def _period_label(from_date: str, to_date: str) -> str:
    """A period a human reads, from an EXCLUSIVE end date."""
    from datetime import date as _d, timedelta

    try:
        f = _d.fromisoformat(from_date)
        t = _d.fromisoformat(to_date) - timedelta(days=1)
    except ValueError:
        return f"{from_date} to {to_date}"
    if f.day == 1 and (t + timedelta(days=1)).day == 1:
        if f.month == t.month and f.year == t.year:
            return f"{f:%B %Y}"
        if f.month == 1 and t.month == 12 and f.year == t.year:
            return f"{f:%Y}"
    return f"{f:%d %b %Y} to {t:%d %b %Y}"


def answer(spec: dict, question: str = "") -> dict:
    """Run the matched recipe and return the backend's raw response shape.

    Returned in the SAME shape groq_backend returns so agent.ask can hand it
    straight to postprocess.enrich - that keeps the citation, the export, the
    scope banners and the anti-fabrication guard all working exactly as they do
    for a model-driven turn. The only thing skipped is the model deciding which
    tool to call, which is the part that was failing.
    """
    from app.agent import tools

    name = spec["recipe"]
    # cut_purity_change is scoped by KAPAN and takes no period at all; every
    # other recipe requires one. Building the period args unconditionally
    # KeyErrors on it.
    if name == "quick_fact":
        args = {"fact": spec["fact"], "label": spec.get("label", ""),
                "from_date": spec.get("from_date"), "to_date": spec.get("to_date"),
                "kapan": spec.get("kapan")}
    elif name == "cut_purity_change":
        args = {"kapan": spec["kapan"], "lab": spec.get("lab") or "GIA"}
    elif name == "kapan_report":
        args = {"kapan": spec["kapan"]}
    elif name == "production_report":
        args = {"from_date": spec["from_date"],
                "to_date": spec["to_date"],
                "basis": spec.get("basis", "finished"),
                "bucket": spec.get("bucket", "total")}
    elif name == "employee_report":
        args = {"employee": spec["employee"], "from_date": spec["from_date"],
                "to_date": spec["to_date"]}
    elif name in ("plan_rows", "stage_gap"):
        # Kapan-scoped and PERIOD-FREE, like cut_purity_change. Passing them
        # through the period branch below would KeyError on from_date.
        args = {k: v for k, v in spec.items()
                if k != "recipe" and v not in (None, "")}
    else:
        args = {"from_date": spec["from_date"], "to_date": spec["to_date"]}
        if spec.get("department"):
            args["department"] = spec["department"]
    # Only pending_lab_results takes a lab; passing it to another recipe would
    # be a silently ignored argument rather than an error.
    if spec.get("lab") and name == "pending_lab_results":
        args["lab"] = spec["lab"]

    text, sql, rows, cols, full, sections = tools.run_tool(name, args)

    if str(text).startswith("ERROR"):
        # The recipe refused (bad period, unknown department). Fall back to the
        # normal path rather than showing the user a tool error.
        return {}

    # ECHO THE KAPAN BACK, always. We have queried the wrong kapan twice on
    # this project (OS26/OR26, NI26/NS26) and both times a number for the wrong
    # batch of stones reached the client.
    if name == "quick_fact":
        # The fact IS the answer - a lead-in sentence in front of a one-line
        # figure just pads it. The basis note is already in the text.
        lead = ""
    elif name == "cut_purity_change":
        lead = (f"Here is the CUT-PURITY CHANGE report for kapan "
                f"**{spec['kapan']}** - the MFG plan against the "
                f"{spec.get('lab') or 'GIA'} grade.")
    elif name == "production_report":
        lead = (f"Here is production for "
                f"{_period_label(spec['from_date'], spec['to_date'])}.")
    elif name == "kapan_report":
        lead = f"Here is the full report for kapan **{spec['kapan']}**."
    elif name == "employee_report":
        lead = (f"Here is the report for employee "
                f"**{spec['employee']}** for "
                f"{_period_label(spec['from_date'], spec['to_date'])}.")
    elif name == "plan_rows":
        _by = f" planned by **{spec['department']}**" if spec.get("department") else ""
        lead = (f"Here are the plans created in kapan "
                f"**{spec['kapan']}**{_by}.")
    elif name == "stage_gap":
        lead = (f"Here are the packets in kapan **{spec['kapan']}** with an "
                f"approved **{spec['done_stage']}** plan and no approved "
                f"**{spec['next_stage']}** plan.")
    else:
        where = f" for {spec['department']}" if spec.get("department") else ""
        _lab = spec.get("lab") or ""
        what = {
            "lab_results": "lab results (GIA/HRD/IGI)",
            "pending_lab_results": (
                f"polished work still waiting for {_lab} certification" if _lab
                else "polished work still waiting for the lab (GIA/HRD/IGI)"),
        }.get(name, "department report")
        lead = (f"Here is the {what}{where} for "
                f"{_period_label(spec['from_date'], spec['to_date'])}.")

    return {
        # A quick fact carries no lead-in, so joining unconditionally would
        # open every one-line answer with two blank lines.
        "answer": (lead + "\n\n" + _strip_model_preamble(text)) if lead
                  else _strip_model_preamble(text),
        "sql_used": [sql] if sql else [],
        "rows_returned": rows,
        "widgets": [],
        "data_columns": cols,
        "data_rows": full,
        "data_sections": sections,
        "file_grounded": False,
    }
