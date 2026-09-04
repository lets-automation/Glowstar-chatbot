"""
quick_facts.py
--------------
ONE-LINE FACTS, ANSWERED IN CODE, WITH NO LLM CALL.

WHY THIS EXISTS
---------------
Measured on the recorded cold run (cold_qwen3_v2.txt, 28 questions, qwen3-30b):

    Gujlish business questions   17 asked   6 answered with NO QUERY AT ALL
    English business questions    5 asked   2 (both defensible refusals)
    out-of-scope (poem/webpage)   6 asked   6 refused, correctly

Thirty-five percent of the Gujlish questions ran no SQL whatsoever. The
anti-fabrication guard then correctly refuses to let a number be invented, so
the client sees "I couldn't pull that" for questions this database answers in
one query. The six that failed:

    aa varsh ma ketla planning verify thaya che?
    kapan OQ26 ma total ketla piece hata?
    our stock na stone no average depth % ketlo che?
    Galaxy process no rate su chhe?
    Aapne ketla department chalu chhe?
    Aa mahine ketla nang thaya?

None of these is hard. They are single aggregates over tables whose correct
source is ALREADY settled in query_rules - every rule there carries the figure
it was verified with. The failure is not knowledge, it is that a weak model
under a 21,640-token prompt does not reliably emit a tool call, and Gujlish is
where it breaks first. That is exactly the case for taking the model out of the
loop, the same argument recipe_router already won for reports.

WHAT MAKES THIS SAFE
--------------------
A deterministic wrong answer is worse than a refusal, so:
  * every trigger is NARROW, and a fact that needs a period or a kapan does not
    fire until that scope actually resolves;
  * every SQL below was run against the live database and checked against the
    figure the matching query_rules entry was verified with - planning 2026 =
    31,317, OQ26 = 839 packets / 585 Pcs / 335.446 ct, finished 682 / 310.660,
    active employees = 369;
  * every answer NAMES ITS BASIS, because several of these questions have more
    than one defensible reading and the rules require saying which was used.

Zero prompt cost: the model is never told this exists (no TOOL_SPECS entry -
see tools.TOOL_HANDLERS). recipe_router matches it in code, pre-call.
"""
from __future__ import annotations

import re

# Gujlish "how many / how much". The client's staff type these, not "how many".
_HOWMANY = r"(?:ketla|ketlu|ketlo|ketli|kitne|kitna|how\s+many|how\s+much|total)"


class Fact:
    """A question shape, the query that answers it, and how to say the answer.

    `needs` is "period", "kapan" or "" - the scope the ROUTER must resolve
    before this fact may fire. A fact whose scope does not resolve declines,
    and the normal path runs unchanged.
    """

    def __init__(self, key, trigger, needs, sql, render, unless="", source=None):
        self.key = key
        self.trigger = re.compile(trigger, re.IGNORECASE)
        self.unless = re.compile(unless, re.IGNORECASE) if unless else None
        self.needs = needs
        self.sql = sql
        self.render = render
        # (table, date column) for a period fact - used ONLY to explain a zero.
        self.source = source

    def applies(self, question: str) -> bool:
        q = question or ""
        if self.unless is not None and self.unless.search(q):
            return False
        return bool(self.trigger.search(q))


def _n(v):
    """Render a number the way the rest of the system does - grouped, plain."""
    if v is None:
        return "0"
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return f"{v:,}"


# ---------------------------------------------------------------------------
# THE FACTS
# ---------------------------------------------------------------------------
def _sql_planning(scope):
    f, t = scope
    return f"""
SELECT COUNT(DISTINCT Packet_ID) AS Packets
FROM tblPlanMaster WITH (NOLOCK)
WHERE IsApproved = 1 AND CreatDate >= '{f}' AND CreatDate < '{t}'"""


def _render_planning(rows, scope, label):
    n = rows[0]["Packets"] if rows else 0
    return (f"**{_n(n)} packets** had their planning approved in {label}.",
            "Counted as tblPlanMaster.IsApproved = 1, distinct packets. "
            "IsVerified is a dead flag - it is set on 14 rows in the whole "
            "database - so approval is the real signal.")


def _sql_kapan_pieces(kapan):
    k = str(kapan).replace("'", "''")
    return f"""
SELECT COUNT(*) AS Packets, SUM(ISNULL(p.Pcs, 0)) AS Pieces,
       CAST(SUM(ISNULL(p.PolishedWt, 0)) AS decimal(14,3)) AS PolishedWt,
       (SELECT COUNT(*) FROM tblFinalPacket f WITH (NOLOCK)
        JOIN tblKapan k2 WITH (NOLOCK) ON f.KapanID = k2.ID
        WHERE k2.KapanName = '{k}') AS Finished
FROM tblPacket p WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON p.Kapan_ID = k.ID
WHERE k.KapanName = '{k}'"""


def _render_kapan_pieces(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"Kapan **{label}** holds **{_n(r.get('Packets'))} packets** "
            f"({_n(r.get('PolishedWt'))} ct planned weight).",
            f"'Pieces' has three defensible readings here, so: "
            f"{_n(r.get('Packets'))} packet rows in tblPacket, "
            f"SUM(Pcs) = {_n(r.get('Pieces'))}, and "
            f"{_n(r.get('Finished'))} finished rows in tblFinalPacket. "
            f"The packet count is the usual answer to 'how many pieces are in "
            f"the kapan'.")


def _sql_headcount(scope):
    return """
SELECT COUNT(*) AS Active FROM tblEmployee WITH (NOLOCK) WHERE IsActive = 1"""


def _render_headcount(rows, scope, label):
    n = rows[0]["Active"] if rows else 0
    return (f"**{_n(n)} active employees**.",
            "Counted as tblEmployee.IsActive = 1. The unfiltered roster is a "
            "decade of leavers and about ten times the real size; "
            "tblEmployeeCount is not used - it stopped in July 2021.")


def _sql_departments(scope):
    return """
SELECT COUNT(DISTINCT DepartMentName) AS Departments
FROM tblEmployee WITH (NOLOCK)
WHERE IsActive = 1 AND DepartMentName IS NOT NULL AND DepartMentName <> ''"""


def _render_departments(rows, scope, label):
    n = rows[0]["Departments"] if rows else 0
    return (f"**{_n(n)} departments** currently have active staff.",
            "Counted as distinct tblEmployee.DepartMentName across employees "
            "with IsActive = 1, so it is departments that are actually manned "
            "rather than every department ever created.")


def _sql_finished(scope):
    f, t = scope
    return f"""
SELECT COUNT(*) AS Finished,
       CAST(SUM(ISNULL(CurrentWt, 0)) AS decimal(14,3)) AS Carats
FROM tblFinalPacket WITH (NOLOCK)
WHERE CreateDate >= '{f}' AND CreateDate < '{t}'"""


def _render_finished(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"**{_n(r.get('Finished'))} stones** were finished in {label} "
            f"({_n(r.get('Carats'))} ct).",
            "Counted as stones FINISHED in the period - tblFinalPacket."
            "CreateDate. Production has a second basis, the tblPlanMaster "
            "MFG stage, which is the one to use for a per-worker or "
            "per-department figure; the two disagree by up to 14% in a month.")


def _sql_avg_depth(scope):
    return """
SELECT CAST(AVG(CAST(Depth AS decimal(18,4))) AS decimal(9,2)) AS AvgDepthPct,
       COUNT(*) AS Packets
FROM tblPacket WITH (NOLOCK)
WHERE RunningProcess = 'IN Stock' AND Depth IS NOT NULL AND Depth > 0"""


def _render_avg_depth(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"Average depth is **{_n(r.get('AvgDepthPct'))}%** across "
            f"{_n(r.get('Packets'))} packets in stock.",
            "Counting packets currently flagged RunningProcess = 'IN Stock', "
            "excluding rows with no depth recorded. Stock is not a settled "
            "definition here - the other basis is packets with no "
            "tblFinalPacket row, i.e. the unfinished ones.")


# ---------------------------------------------------------------------------
# LIVE SNAPSHOT FACTS - "what is true right now"
# These take NO period. A date picker on "how many packets are on jangad" is
# the same category error as one on "how many people work here".
# ---------------------------------------------------------------------------
def _sql_kapan_count(scope):
    return """
SELECT COUNT(*) AS Kapans,
       SUM(CASE WHEN ISNULL(IsFinished, 0) = 0 THEN 1 ELSE 0 END) AS OpenKapans
FROM tblKapan WITH (NOLOCK)"""


def _render_kapan_count(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"**{_n(r.get('Kapans'))} kapans** in total, of which "
            f"**{_n(r.get('OpenKapans'))}** are still open.",
            "A kapan is one parcel of rough. 'Open' means it has not been "
            "closed off yet, so it is still being worked.")


def _sql_packet_total(scope):
    return """
SELECT COUNT(*) AS Packets FROM tblPacket WITH (NOLOCK)"""


def _render_packet_total(rows, scope, label):
    n = rows[0]["Packets"] if rows else 0
    return (f"**{_n(n)} packets** have been created in total.",
            "Every packet created since the system started - NOT what is on "
            "hand today. For the current position ask for stock, or for "
            "packets out on jangad.")


def _sql_on_jangad(scope):
    # tblJangadPackets, never tblJangad: the latter is the MOVEMENT register,
    # one row per Issue or Receive, and counting it overstates by roughly 16x.
    return """
SELECT COUNT(*) AS Packets,
       COUNT(DISTINCT JangadId) AS OpenJangads,
       CAST(SUM(ISNULL(Carat, 0)) AS decimal(14,3)) AS Carats
FROM tblJangadPackets WITH (NOLOCK)
WHERE ISNULL(IsReceived, 0) = 0"""


def _render_on_jangad(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"**{_n(r.get('Packets'))} packets** are out on jangad right now, "
            f"across **{_n(r.get('OpenJangads'))}** open jangads "
            f"({_n(r.get('Carats'))} ct).",
            "Counted as packets issued on a jangad and not yet received back.")


def _sql_on_memo(scope):
    return """
SELECT COUNT(*) AS Packets,
       CAST(SUM(ISNULL(CurrentWt, 0)) AS decimal(14,3)) AS Carats
FROM tblPacket WITH (NOLOCK) WHERE IsOnMemo = 1"""


def _render_on_memo(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"**{_n(r.get('Packets'))} stones** are out on memo right now "
            f"({_n(r.get('Carats'))} ct).",
            "Stones flagged as out on memo, at their current weight. This is the "
            "same goods-out position as packets out on jangad - the two agree "
            "to within a packet, so do not add them together.")


def _sql_on_hold(scope):
    # HOLD IS KAPAN-LEVEL. tblPacket.IsOnHold is set on two rows in the whole
    # table - effectively dead - so counting it reports 2 where the real
    # figure is five digits.
    return """
SELECT COUNT(p.ID) AS Packets,
       COUNT(DISTINCT k.ID) AS Kapans,
       CAST(SUM(ISNULL(p.CurrentWt, 0)) AS decimal(14,3)) AS Carats
FROM tblPacket p WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON k.ID = p.Kapan_ID
WHERE k.IsOnHold = 1"""


def _render_on_hold(rows, scope, label):
    r = rows[0] if rows else {}
    return (f"**{_n(r.get('Packets'))} packets** are on hold, across "
            f"**{_n(r.get('Kapans'))}** held kapans ({_n(r.get('Carats'))} ct).",
            "Hold is applied to a whole kapan, not to individual packets, so "
            "this is every packet belonging to a kapan currently on hold, at "
            "its current weight.")


def _sql_in_stock(scope):
    return """
SELECT COUNT(*) AS InStock,
       (SELECT COUNT(*) FROM tblPacket WITH (NOLOCK)) AS EverCreated
FROM tblPacket WITH (NOLOCK) WHERE RunningProcess = 'IN Stock'"""


def _render_in_stock(rows, scope, label):
    r = rows[0] if rows else {}
    n, ever = r.get("InStock") or 0, r.get("EverCreated") or 0
    pct = (100.0 * n / ever) if ever else 0
    return (f"**{_n(n)} packets** are currently flagged IN Stock.",
            f"Stock does not have one settled definition here, so treat this "
            f"as one reading of it. This flag covers {pct:.0f}% of every "
            f"packet ever created, which is closer to all of history than to "
            f"what is on hand today. The other reading is packets that have "
            f"not been finished yet. Worth confirming which figure your stock "
            f"screen shows.")


FACTS: list[Fact] = [
    # ----- LIVE SNAPSHOT: no period, no kapan -----------------------------
    # "how many packets are on jangad?" - the default question in
    # scripts/e2e_check.py, and free SQL for months.
    Fact("on_jangad",
         r"\bjangad\b",
         "", _sql_on_jangad, _render_on_jangad,
         # A jangad REPORT or a party breakdown is not this scalar.
         unless=r"wise|party|process|report|detail|list|which|kaya|history"),

    # "how many stones are out on memo right now?"
    Fact("on_memo",
         r"\bon\s+memo\b|\bmemo\s+(?:par|ma|pe)\b|\bout\s+on\s+memo\b",
         "", _sql_on_memo, _render_on_memo,
         unless=r"wise|report|list|which|detail"),

    # "atyare ketla diamond hold par che?" - HOLD IS KAPAN-LEVEL.
    Fact("on_hold",
         r"\bon\s+hold\b|\bhold\s+(?:par|ma|pe)\b|\bheld\b",
         "", _sql_on_hold, _render_on_hold,
         unless=r"wise|report|list|which|detail|kaya"),

    # "how many packets are in stock right now?" - one basis of several, and
    # the note says so rather than presenting a settled figure.
    Fact("in_stock",
         rf"{_HOWMANY}[\s\w]{{0,16}}\bin\s+stock\b"
         rf"|\bin\s+stock\b[\s\w]{{0,10}}{_HOWMANY}"
         rf"|\bstock\s+ma\b[\s\w]{{0,10}}{_HOWMANY}",
         "", _sql_in_stock, _render_in_stock,
         # A SHAPE or grade in the question makes it a breakdown, not a scalar:
         # "how many oval diamonds do we have in stock" needs the shape family.
         unless=r"wise|oval|pear|marquise|round|shape|colour|color|clarity"
                r"|purity|report|list|which"),

    # "how many kapans do we have?" - AFTER kapan_pieces, which wants a named
    # kapan and a piece count; this is the bare inventory question.
    Fact("kapan_count",
         rf"{_HOWMANY}[\s\w]{{0,8}}\bkapan",
         "", _sql_kapan_count, _render_kapan_count,
         unless=r"piece|pcs|nang|packet|wise|report|weight|loss|junk|damage"),

    # "how many packets are there / how many diamonds do we have" - the whole
    # table. The note keeps it from being read as "on hand".
    Fact("packet_total",
         rf"{_HOWMANY}[\s\w]{{0,10}}(?:packet|diamond|stone|nang)s?\b"
         rf"[\s\w]{{0,14}}(?:do\s+we\s+have|are\s+there|in\s+total|total)"
         rf"|{_HOWMANY}[\s\w]{{0,6}}(?:packet|diamond|stone)s?\s*[?.]?\s*$",
         "", _sql_packet_total, _render_packet_total,
         unless=r"wise|in\s+stock|jangad|memo|hold|kapan|department|process"
                r"|sold|sell|made|produced|month|year|shape|oval|pear|colour"
                r"|color|clarity|purity|report|list|which"),

    # "aa varsh ma ketla planning verify thaya che?"
    Fact("planning_approved",
         rf"planning[\s\w]{{0,12}}(verif|approv)|(verif|approv)[\w\s]{{0,12}}planning"
         rf"|planning\s+{_HOWMANY}",
         "period", _sql_planning, _render_planning,
         source=("tblPlanMaster", "CreatDate")),

    # "kapan OQ26 ma total ketla piece hata?"
    Fact("kapan_pieces",
         rf"kapan[\s\w]{{0,24}}{_HOWMANY}[\s\w]{{0,12}}(piece|pcs|nang|packet)"
         rf"|{_HOWMANY}[\s\w]{{0,12}}(piece|pcs|nang|packet)[\s\w]{{0,18}}kapan",
         "kapan", _sql_kapan_pieces, _render_kapan_pieces),

    # "Aapne ketla department chalu chhe?" - BEFORE headcount, because
    # "how many people in each department" is a different question and the
    # department wording must win over the bare headcount trigger.
    Fact("active_departments",
         rf"{_HOWMANY}[\s\w]{{0,10}}(department|vibhag)"
         rf"|(department|vibhag)[\s\w]{{0,10}}(chalu|active|running)",
         "", _sql_departments, _render_departments,
         unless=r"wise|per\s+department|each\s+department|in\s+\w+\s+department"),

    # "how many employees / mansu / karigar"
    Fact("headcount",
         rf"{_HOWMANY}[\s\w]{{0,10}}(employee|worker|karigar|mansu|staff|people)"
         rf"|headcount|head\s+count",
         "", _sql_headcount, _render_headcount,
         # ANY department wording disqualifies it. "how many employees are in
         # MFG - 1 department" would otherwise be answered with the COMPANY
         # headcount (369) - fast, confident, and about the wrong population.
         # A scoped headcount is a report, not a scalar; let it fall through.
         unless=r"wise|bonus|salary|pagar"
                r"|department|dept|vibhag|mfg|fency|marker|checker"),

    # "Aa mahine ketla nang thaya?"
    Fact("finished_output",
         rf"{_HOWMANY}[\s\w]{{0,10}}(nang|stone|diamond|piece)s?\s*(thaya|thai|made|"
         rf"finish|produced|banya)|production\s+{_HOWMANY}"
         rf"|{_HOWMANY}[\s\w]{{0,6}}(utpadan|production)",
         "period", _sql_finished, _render_finished,
         unless=r"kapan|department|employee|worker|wise",
         source=("tblFinalPacket", "CreateDate")),

    # "our stock na stone no average depth % ketlo che?"
    Fact("stock_avg_depth",
         r"(average|avg|mean)[\s\w]{0,14}depth|depth[\s\w]{0,10}(average|avg|percent)",
         "", _sql_avg_depth, _render_avg_depth),
]


def _all_zero(rows) -> bool:
    """True when the fact came back with nothing in it."""
    if not rows:
        return True
    return all(v in (0, None) for v in rows[0].values()
               if isinstance(v, (int, float)) or v is None)


def _recency_note(fact, rows, scope) -> str:
    """Explain a ZERO that is really 'the data stops before you asked'.

    THE DATABASE IS A RESTORED BACKUP AND IT ENDS BEFORE TODAY.
    tblFinalPacket stops 2026-08-20, tblPlanMaster 2026-08-21. Asked "Aa mahine
    ketla nang thaya?" on 3 Sep, the honest answer is "0 stones finished in
    September 2026" - correct, and indistinguishable from a broken system. The
    user reads 0 and concludes the bot cannot count.

    So a zero over a period is annotated with where the data actually stops.
    Only ever ADDS a sentence, and only when the count really is zero, so a
    real zero in a period the data covers is still reported as a real zero -
    with the end date shown, which is the information needed to tell them
    apart.
    """
    if fact.needs != "period" or not fact.source or not _all_zero(rows):
        return ""
    if not (isinstance(scope, (tuple, list)) and len(scope) == 2):
        return ""
    table, col = fact.source
    from app.agent.reports import _rows as _run

    _, last, err = _run(f"SELECT MAX({col}) AS Last_ FROM {table} WITH (NOLOCK)")
    if err or not last:
        return ""
    latest = str(last[0].get("Last_") or "")[:10]
    if not latest or latest >= str(scope[0])[:10]:
        return ""
    return (f"**This is zero because the data stops before that period.** The "
            f"most recent record in {table} is {latest}; you asked about "
            f"{str(scope[0])[:10]} onwards. Ask for an earlier period to see "
            f"real figures.")


def match(question: str) -> dict | None:
    """The fact this question asks for, or None.

    Returns {"fact": key, "needs": "period"|"kapan"|""}. The ROUTER resolves
    the scope - keeping period and kapan parsing in one place there rather than
    duplicating it here.
    """
    for fact in FACTS:
        if fact.applies(question or ""):
            return {"fact": fact.key, "needs": fact.needs}
    return None


def get(key: str) -> Fact | None:
    return next((f for f in FACTS if f.key == key), None)


def answer(key: str, scope=None, label: str = "") -> dict:
    """Run the fact and render it. Same envelope shape as a report recipe."""
    from app.agent.reports import _rows

    fact = get(key)
    if fact is None:
        return {"text": f"ERROR: unknown fact '{key}'.", "sections": [], "sql": ""}

    sql = fact.sql(scope) if fact.needs else fact.sql(scope)
    cols, rows, err = _rows(sql.strip())
    if err:
        return {"text": f"ERROR: {err}", "sections": [], "sql": ""}

    headline, basis = fact.render(rows, scope, label)

    note = _recency_note(fact, rows, scope)
    if note:
        basis = f"{note}\n\n{basis}"

    # THE MARKER MUST CARRY THE ISO DATES INSIDE THE PARENTHESES.
    #
    # period_guard exempts a recipe from the "not filtered to that period"
    # banner via _RECIPE_PERIOD_RE = ^\s*--\s*\w+\(.*\d{4}-\d{2}-\d{2} - it
    # looks for the dates in the CALL, because a recipe reports itself as one
    # comment line rather than as the SQL it ran. Written as
    # "-- quick_fact('finished_output') | scope: August 2026" the dates sit
    # outside the parens, the exemption misses, and "Aa mahine ketla nang
    # thaya?" came back correct (3,214 for August) under a banner announcing it
    # "covers all available history". A false banner on a correct number is
    # worse than no banner - it teaches the client to distrust a right answer.
    # Caught live against the RunPod pod, 2026-09-03.
    if isinstance(scope, (tuple, list)) and len(scope) == 2:
        marker = f"-- quick_fact('{key}', '{scope[0]}', '{scope[1]}')"
    elif scope:
        marker = f"-- quick_fact('{key}', '{scope}')"
    else:
        marker = f"-- quick_fact('{key}')"

    return {
        "text": f"{headline}\n\n{basis}",
        # One aggregate row - a table of it adds nothing, and an empty
        # `sections` keeps the Excel export from offering a one-cell workbook.
        "sections": [],
        "sql": marker,
        "columns": cols,
        "rows": rows,
    }
