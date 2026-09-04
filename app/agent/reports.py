"""
reports.py
----------
DETERMINISTIC report recipes.

WHY THIS EXISTS
---------------
"Give me a report of department MFG - 1" used to be answered by the model
improvising 7-11 queries of its own. Measured live on 2026-08-20, that produced,
across consecutive runs of the SAME question:

  * a WHERE DepartmentName=... filter against tblPlanMaster - a column that does
    not exist there - so the report came back empty;
  * "9 packets manufactured" when the database holds 381, because the model
    summarised its own 30-row preview sample as if it were the total;
  * two sections one run and five the next, with damage/bonus/incentive silently
    dropped;
  * "That request was too large" once the accumulated rows from nine tool
    rounds overflowed the context window.

None of that is a model defect that a bigger model fixes - it is what happens
when the shape of a report is re-derived from a 19,000-token rulebook on every
turn. The queries here were each RUN against the live database and checked
before being written down, so the numbers are the same every time and the
section list cannot quietly shrink.

The model still writes the prose. It just no longer invents the SQL.

NOT HARDCODED: every recipe takes the department and the period as parameters
and resolves the department against tblEmployee at run time, so a new department
needs no code change.

SALARY REMAINS BLOCKED. tblPointRateLabour carries LabourAmount and FinalLabour;
neither is selected here, and neither may be added. Bonus (BonusAmount,
BonusPoint) and incentive (CreditPoints, DebitPoints) are the figures the rules
permit, and they are the only earnings columns used.
"""
from __future__ import annotations

import re
from app.database.runner import run_select

# One preview table in the model's context is enough for it to describe a
# section; the FULL rows still reach the user through the Excel export. This is
# what stops a nine-round report from overflowing the context window.
_PREVIEW_ROWS = 8

# Detail sections are capped so a busy department cannot produce a 50,000-row
# export that takes minutes to build. The cap is reported honestly when hit.
_DETAIL_CAP = 2000


def _q(value: str) -> str:
    """Escape a value for single-quoted SQL. Department names are model-supplied."""
    return str(value or "").replace("'", "''")


# A report recipe takes an EXPLICIT half-open date range. When the model passes
# something that is not a date, the recipe used to run anyway and return its
# confident header - "the figures below are already computed and reconciled
# against their ERP" - with NO figures under it.
#
# Reported live 2026-08-26: "Provide me GIA results of may month" answered
# "I wasn't able to pull that from the database just now... could you rephrase?"
# The model was right to refuse, but it could not RECOVER: nothing told it that
# the date arguments were the problem, so it asked the user to rephrase a
# question that was already perfectly clear.
#
# So the range is validated like a query_rules violation: a specific, actionable
# rejection the model can fix on the next round.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def invalid_period(from_date: str, to_date: str) -> str:
    """A rejection message for a bad recipe date range, or "" when it is fine."""
    from datetime import date as _date

    a, b = (from_date or "").strip(), (to_date or "").strip()
    if not a or not b:
        return (
            "BLOCKED: this report needs an explicit date range and one was not "
            "supplied. Call it again with from_date and to_date as YYYY-MM-DD, "
            "END-EXCLUSIVE - for the whole of May 2026 that is "
            "from_date='2026-05-01', to_date='2026-06-01'. Work the dates out "
            "from TODAY'S DATE in your instructions; do NOT ask the user to "
            "rephrase, the period they named is enough."
        )
    for label, v in (("from_date", a), ("to_date", b)):
        if not _ISO_DATE_RE.match(v):
            return (
                f"BLOCKED: {label}={v!r} is not a date. Both dates must be "
                "YYYY-MM-DD and the range is END-EXCLUSIVE - for the whole of "
                "May 2026 use from_date='2026-05-01', to_date='2026-06-01'. "
                "Convert the period the user named using TODAY'S DATE from your "
                "instructions and call the tool again; do NOT ask the user to "
                "rephrase."
            )
    try:
        d1 = _date(*(int(x) for x in a.split("-")))
        d2 = _date(*(int(x) for x in b.split("-")))
    except (ValueError, TypeError):
        return (
            f"BLOCKED: {a!r} to {b!r} is not a valid calendar range. Use real "
            "YYYY-MM-DD dates, END-EXCLUSIVE."
        )
    if d2 <= d1:
        return (
            f"BLOCKED: to_date ({b}) must be AFTER from_date ({a}). The range is "
            "END-EXCLUSIVE, so for a single month use the 1st of the NEXT month."
        )
    # THE OFF-BY-ONE THAT SILENTLY LOSES A DAY. from=1st and to=last-day-of-the-
    # same-month reads as "the whole month" but, end-exclusive, drops it: May
    # 2026 as 05-01..05-31 returns 2,495 packets instead of 2,562. Nothing about
    # the answer looks wrong, which is why this must be rejected and not guessed.
    if d1.day == 1:
        nxt = _date(d2.year + (d2.month == 12), (d2.month % 12) + 1, 1)
        if d2.year == d1.year and d2.month == d1.month and (nxt - d2).days == 1:
            return (
                f"BLOCKED: to_date={b} is the LAST DAY of that month, and this "
                f"range is END-EXCLUSIVE - it would silently drop {b}. For the "
                f"whole month use to_date='{nxt:%Y-%m-%d}'."
            )
    return ""


def resolve_department(name: str) -> tuple[str | None, list[str]]:
    """Match a department name to the exact spelling used in tblEmployee.

    Returns (exact_name_or_None, suggestions). The client's staff type "MFG 1",
    "mfg-1" and "MFG - 1" for the same department, and the stored spelling is
    the one with spaces around the dash - an exact-match filter on anything else
    silently returns zero rows, which reads as "no data" rather than "no match".
    """
    like = _q((name or "").replace("-", "").replace(" ", ""))
    r = run_select(
        "SELECT DISTINCT DepartMentName FROM tblEmployee WITH (NOLOCK) "
        "WHERE DepartMentName IS NOT NULL AND DepartMentName <> ''",
        max_rows=500,
    )
    if not r.get("ok"):
        return None, []
    names = [row["DepartMentName"] for row in r["rows"] if row.get("DepartMentName")]
    squash = {n.replace("-", "").replace(" ", "").lower(): n for n in names}
    hit = squash.get(like.lower())
    if hit:
        return hit, []
    close = [n for k, n in squash.items() if like.lower() and like.lower() in k]
    if close:
        return (close[0], []) if len(close) == 1 else (None, sorted(close)[:12])

    # ONE-LETTER TYPOS. The client's own logs spell the Fency department
    # "fancy" ("provide past month gia result for fancy department"), and an
    # exact/substring match misses it by a single vowel - the reply was then a
    # 12-name list of every department, which reads as "we don't have your
    # department". Resolve only an UNAMBIGUOUS near-match: one candidate at high
    # similarity (0.8 - "fancy" vs "fency" scores exactly that). Two
    # plausible ones stay a question for the user, because
    # picking between MFG-2 and MFG-3 for them would be a silent wrong answer.
    import difflib

    keys = difflib.get_close_matches(like.lower(), list(squash), n=3, cutoff=0.8)
    if len(keys) == 1:
        return squash[keys[0]], []
    if keys:
        return None, [squash[k] for k in keys]
    return None, sorted(names)[:12]


def _rows(sql: str, cap: int = _DETAIL_CAP) -> tuple[list[str], list[dict], str | None]:
    """Run one section's query - and LOG it.

    A recipe reports its call to the agent as a single comment marker
    ("-- lab_results_report(...)"), because it runs several queries. That marker
    is what reached agent.log, so the actual SQL behind a report became
    invisible: you could see that a report ran and how many rows came back, but
    not what was executed or which section failed. Every other query in the
    system is logged, and losing that for exactly the queries we most want to
    audit against the client's ERP is the wrong trade.
    """
    from app.core.logging_util import logger

    r = run_select(sql, max_rows=cap)
    one_line = " ".join(sql.split())
    if not r.get("ok"):
        err = str(r.get("error"))[:200]
        logger.error("   RECIPE SQL FAILED: %s | %s", one_line[:400], err)
        return [], [], err
    cols, rows = list(r.get("columns") or []), list(r.get("rows") or [])
    logger.info("   RECIPE SQL (%s rows): %s", len(rows), one_line[:400])
    return cols, rows, None


def _preview(columns: list[str], rows: list[dict], limit: int = _PREVIEW_ROWS) -> str:
    """A small markdown table, so the model can see the shape without the bulk."""
    if not rows:
        return "_(no records in this period)_"
    head = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = [
        "| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in columns) + " |"
        for r in rows[:limit]
    ]
    more = f"\n_({len(rows)} rows total; the full set is in the download.)_" if len(rows) > limit else ""
    return "\n".join([head, rule, *body]) + more


def department_report(department: str, from_date: str, to_date: str) -> dict:
    """Every section of a department report, computed the same way every time.

    `to_date` is EXCLUSIVE - callers pass the first day of the next period, so a
    July report is [2026-07-01, 2026-08-01). Half-open avoids the classic
    "<= 31 July" bug that drops rows timestamped later that day.

    Returns {"text": str, "sections": [{title, columns, rows}], "sql": str}.
    """
    dept, suggestions = resolve_department(department)
    if not dept:
        hint = ("Closest matches: " + ", ".join(suggestions)) if suggestions else ""
        return {
            "text": (
                f"ERROR: no department matching '{department}'. {hint} "
                "Ask the user which one they meant - do not guess."
            ),
            "sections": [],
            "sql": "",
        }

    d, f, t = _q(dept), _q(from_date), _q(to_date)
    emp = (
        f"(SELECT ID FROM tblEmployee WITH (NOLOCK) WHERE DepartMentName = '{d}')"
    )
    # Production is attributed to the MFG-stage worker, which is how the client
    # counts it. Department lives on tblEmployee only - the fact tables carry
    # EmpId - so every production filter goes through the employee subquery.
    in_period = f"p.CreatDate >= '{f}' AND p.CreatDate < '{t}'"

    specs: list[tuple[str, str]] = [
        # ACTIVE ONLY. The unfiltered roster for MFG - 1 is 343 people against 18
        # who actually produced anything in the period - it is a decade of
        # leavers, and listing them makes the department look ten times its real
        # size. Active-only is the documented house default for employee
        # questions; the leaver count is still surfaced, in Headcount below.
        ("Workforce", f"""
SELECT e.Code, e.FirstName + ' ' + e.LastName AS Worker
FROM tblEmployee e WITH (NOLOCK)
WHERE e.DepartMentName = '{d}' AND e.IsActive = 1
ORDER BY e.Code"""),

        ("Headcount", f"""
SELECT SUM(CASE WHEN e.IsActive = 1 THEN 1 ELSE 0 END) AS ActiveEmployees,
       SUM(CASE WHEN e.IsActive = 1 THEN 0 ELSE 1 END) AS FormerEmployees,
       COUNT(*) AS OnRecordEver
FROM tblEmployee e WITH (NOLOCK)
WHERE e.DepartMentName = '{d}'"""),

        ("Production summary", f"""
SELECT COUNT(*) AS PlanRows,
       COUNT(DISTINCT p.Packet_ID) AS Packets,
       COUNT(DISTINCT p.KapanId) AS Kapans,
       COUNT(DISTINCT p.EmpId) AS WorkersWithOutput,
       CAST(SUM(ISNULL(p.RoughWt, 0)) AS decimal(14,3)) AS RoughCarats,
       CAST(SUM(ISNULL(p.PolishedWt, 0)) AS decimal(14,3)) AS PolishedCarats
FROM tblPlanMaster p WITH (NOLOCK)
WHERE p.RapVer = 'MFG' AND p.EmpId IN {emp} AND {in_period}"""),

        ("Production by worker", f"""
SELECT e.Code, e.FirstName + ' ' + e.LastName AS Worker,
       COUNT(DISTINCT p.Packet_ID) AS Packets,
       CAST(SUM(ISNULL(p.RoughWt, 0)) AS decimal(14,3)) AS RoughCarats,
       CAST(SUM(ISNULL(p.PolishedWt, 0)) AS decimal(14,3)) AS PolishedCarats
FROM tblPlanMaster p WITH (NOLOCK)
LEFT JOIN tblEmployee e WITH (NOLOCK) ON p.EmpId = e.ID
WHERE p.RapVer = 'MFG' AND p.EmpId IN {emp} AND {in_period}
GROUP BY e.Code, e.FirstName, e.LastName
ORDER BY Packets DESC"""),

        ("Production by kapan", f"""
SELECT k.KapanName,
       COUNT(DISTINCT p.Packet_ID) AS Packets,
       CAST(SUM(ISNULL(p.PolishedWt, 0)) AS decimal(14,3)) AS PolishedCarats
FROM tblPlanMaster p WITH (NOLOCK)
LEFT JOIN tblKapan k WITH (NOLOCK) ON p.KapanId = k.ID
WHERE p.RapVer = 'MFG' AND p.EmpId IN {emp} AND {in_period}
GROUP BY k.KapanName
ORDER BY Packets DESC"""),

        ("Damage", f"""
SELECT r.KapanName, r.PacketNo,
       e.FirstName + ' ' + e.LastName AS Worker,
       r.Points, r.Amount, r.Description, r.CreatedDate
FROM tblPlanReport r WITH (NOLOCK)
LEFT JOIN tblEmployee e WITH (NOLOCK) ON r.EmpID = e.ID
WHERE r.IsDamageReport = 1 AND r.EmpID IN {emp}
  AND r.CreatedDate >= '{f}' AND r.CreatedDate < '{t}'
ORDER BY r.CreatedDate DESC"""),

        # Bonus is department-stamped on this table, so it does not need the
        # employee subquery. LabourAmount / FinalLabour are deliberately absent.
        ("Bonus", f"""
SELECT COUNT(*) AS BonusRows,
       CAST(SUM(ISNULL(l.BonusPoint, 0)) AS decimal(18,2)) AS BonusPoints,
       CAST(SUM(ISNULL(l.BonusAmount, 0)) AS decimal(18,2)) AS BonusAmount
FROM tblPointRateLabour l WITH (NOLOCK)
WHERE l.DepartmentName = '{d}'
  AND l.ProcessDate >= '{f}' AND l.ProcessDate < '{t}'"""),

        ("Incentive", f"""
SELECT COUNT(*) AS Transactions,
       CAST(SUM(ISNULL(i.CreditPoints, 0)) AS decimal(18,2)) AS CreditPoints,
       CAST(SUM(ISNULL(i.DebitPoints, 0)) AS decimal(18,2)) AS DebitPoints
FROM tblIncentiveAmount i WITH (NOLOCK)
WHERE i.EmpID IN {emp}
  AND i.TransactTime >= '{f}' AND i.TransactTime < '{t}'"""),
    ]

    sections: list[dict] = []
    parts: list[str] = [
        f"DEPARTMENT REPORT - {dept} - {from_date} to {to_date} (end exclusive)",
        "",
        "Every section below is already computed. Present ALL of them to the "
        "user, in this order, with the numbers exactly as given. Do NOT re-run "
        "these queries, and do NOT total the preview rows by hand - a preview is "
        "a sample, the totals are in 'Production summary'.",
    ]

    for title, sql in specs:
        cols, rows, err = _rows(sql.strip())
        if err:
            parts += ["", f"## {title}", f"_(unavailable: {err})_"]
            continue
        # A summary section is a single row: render it as key/value lines, which
        # a model reproduces far more reliably than a one-row wide table.
        if len(rows) == 1 and len(cols) > 2:
            parts += ["", f"## {title}"]
            # SUM over zero rows is NULL, not 0. Printing "BonusAmount: None"
            # invites the model to render "None" to a factory manager, so an
            # empty aggregate is shown as an explicit zero instead.
            parts += [
                f"- {c}: {0 if rows[0].get(c) is None else rows[0].get(c)}"
                for c in cols
            ]
        else:
            parts += ["", f"## {title}", _preview(cols, rows)]
        if rows:
            sections.append({"title": title, "columns": cols, "rows": rows})

    parts += [
        "",
        "If a section says 'no records in this period', SAY SO plainly - that is "
        "a real finding about the data, not a reason to omit the section or to "
        "substitute figures from another period.",
    ]
    return {
        "text": "\n".join(parts),
        "sections": sections,
        "sql": f"-- department_report('{dept}', '{from_date}', '{to_date}')",
    }

# ---------------------------------------------------------------------------
# LAB (GIA / HRD / IGI) RESULTS - the client's own "PLS vs GIA" report
# ---------------------------------------------------------------------------
# VERIFIED 2026-08-24 against a screenshot of the client's ERP for May 2026.
# All 27 kapans and all six columns matched exactly, including the totals row:
#
#     PNo 2,562 | P Wt 1330.930 | PLSAmt 93,904.5200
#               | GIAAmt 97,733.8200 | DiffAmt 3,829.30 | DiffPer 4.08%
#
# The definitions that make it match, none of which are guessable:
#   * the population is tblPlanMaster rows at a LAB-GRADING stage,
#     RapVer IN ('GIA','HRD','IGI') - NOT tblFinalPacket.Lab, which answers
#     "finished stones by certifying lab" and gives 3,227 / 1,723 for the
#     same month. RapVer='GIA' alone gives 2,529 and drops HRD and IGI.
#   * the period sits on CreatDate, half-open [from, to).
#   * PNo is COUNT(DISTINCT Packet_ID). COUNT(*) double-counts stage rows and
#     COUNT(DISTINCT KapanId) grouped by kapan is 1 by construction - a live
#     run made exactly that mistake and reported 49.
#   * PLSAmt is Amount on the LATEST PLS row for the same packet (a packet
#     re-assorted twice would otherwise be counted twice); GIAAmt is Amount on
#     the lab-stage row itself.
#
# The report is the comparison, not the count: it shows where the lab valued
# the goods above or below the in-house assortment.
# Enough to show a normal month whole (27 kapans in May 2026) while still
# capping a multi-year request.
_REPORT_ROWS = 60

_LAB_STAGES = "'GIA','HRD','IGI'"



def _lead_table(specs) -> str:
    """Which breakdown the write-up should lead with.

    THIS WAS HARDCODED TO "by-kapan".
    ---------------------------------
    Reported live 2026-08-26: the user asked for GIA results "employee wise",
    the recipe correctly built a "By employee" section - and then told the model
    to "present the summary and the by-kapan table". The model obeyed, so the
    answer narrated kapans and the employee table it had just computed was never
    mentioned in the prose at all (it was in the Excel, unread).

    The instruction now names the section that was actually built for the
    dimension asked for. A by-employee section only exists when a department was
    given, which is exactly the case where the user asked about people.
    """
    titles = [t for t, _ in specs]
    return "by-employee" if "By employee" in titles else "by-kapan"


def lab_results_report(from_date: str, to_date: str, kapan: str = "",
                       department: str = "") -> dict:
    """The PLS-vs-GIA lab report, computed the same way every time.

    `to_date` is EXCLUSIVE, as in department_report: May is
    [2026-05-01, 2026-06-01).

    `department` scopes the report to the workers who MADE those stones and adds
    a by-employee section - "past month GIA results of Fency department
    employees" is the single most-asked question in the chat logs (55 times).

    WHO MADE A STONE, and why it is trustworthy here (measured 2026-07):
    the maker is the EmpId on the LATEST tblPlanMaster RapVer='MFG' row for the
    packet. That resolves to a named employee on 100% of July's 3,692 lab-stage
    packets - no coverage loss - and cross-checks at 99.40% against the wholly
    independent tblPacket.MFGEmpId column, with identical totals (3,692) and an
    identical Fency figure (1,643). The ~0.6% that disagree are packets re-issued
    to a different maker after grading: the plan row holds the maker AT THE TIME,
    tblPacket.MFGEmpId holds the current one. The plan row is the right answer
    for "who made the stones we graded in July".
    """
    f, t = _q(from_date), _q(to_date)
    kap_filter = f" AND k.KapanName = '{_q(kapan)}'" if kapan else ""

    dept, dept_suggestions = (resolve_department(department) if department else (None, []))
    if department and not dept:
        hint = ("Closest matches: " + ", ".join(dept_suggestions)) if dept_suggestions else ""
        return {
            "text": (f"ERROR: no department matching '{department}'. {hint}\n"
                     "Ask the user which one they meant - do not guess."),
            "sections": [], "sql": "",
        }
    dept_filter = f" AND e.DepartMentName = '{_q(dept)}'" if dept else ""

    base = f"""
FROM tblPlanMaster g WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON g.KapanId = k.ID
OUTER APPLY (SELECT TOP 1 pm.Amount FROM tblPlanMaster pm WITH (NOLOCK)
             WHERE pm.Packet_ID = g.Packet_ID AND pm.RapVer = 'PLS'
             ORDER BY pm.ID DESC) p
OUTER APPLY (SELECT TOP 1 mm.EmpId FROM tblPlanMaster mm WITH (NOLOCK)
             WHERE mm.Packet_ID = g.Packet_ID AND mm.RapVer = 'MFG'
             ORDER BY mm.ID DESC) m
LEFT JOIN tblEmployee e WITH (NOLOCK) ON e.ID = m.EmpId
WHERE g.RapVer IN ({_LAB_STAGES})
  AND g.CreatDate >= '{f}' AND g.CreatDate < '{t}'{kap_filter}{dept_filter}"""

    specs = [
        ("Summary", f"""
SELECT COUNT(DISTINCT g.Packet_ID) AS PNo,
       COUNT(DISTINCT g.KapanId) AS Kapans,
       CAST(SUM(ISNULL(g.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(p.Amount, 0)) AS decimal(18,4)) AS PLSAmt,
       CAST(SUM(ISNULL(g.Amount, 0)) AS decimal(18,4)) AS GIAAmt,
       CAST(SUM(ISNULL(g.Amount, 0)) - SUM(ISNULL(p.Amount, 0)) AS decimal(18,2)) AS DiffAmt,
       CAST(CASE WHEN SUM(ISNULL(p.Amount, 0)) = 0 THEN 0
            ELSE (SUM(ISNULL(g.Amount, 0)) - SUM(ISNULL(p.Amount, 0)))
                 * 100.0 / SUM(ISNULL(p.Amount, 0)) END AS decimal(9,2)) AS DiffPer{base}"""),

        ("By kapan", f"""
SELECT k.KapanName AS Kapan,
       COUNT(DISTINCT g.Packet_ID) AS PNo,
       CAST(SUM(ISNULL(g.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(p.Amount, 0)) AS decimal(18,4)) AS PLSAmt,
       CAST(SUM(ISNULL(g.Amount, 0)) AS decimal(18,4)) AS GIAAmt,
       CAST(SUM(ISNULL(g.Amount, 0)) - SUM(ISNULL(p.Amount, 0)) AS decimal(18,2)) AS DiffAmt,
       CAST(CASE WHEN SUM(ISNULL(p.Amount, 0)) = 0 THEN 0
            ELSE (SUM(ISNULL(g.Amount, 0)) - SUM(ISNULL(p.Amount, 0)))
                 * 100.0 / SUM(ISNULL(p.Amount, 0)) END AS decimal(9,2)) AS DiffPer{base}
GROUP BY k.KapanName ORDER BY k.KapanName"""),

        # Who made them. Only when a department was named - otherwise this is a
        # 300-row list nobody asked for.
        *([("By employee", f"""
SELECT e.Code, e.FirstName + ' ' + e.LastName AS Worker,
       COUNT(DISTINCT g.Packet_ID) AS PNo,
       CAST(SUM(ISNULL(g.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(p.Amount, 0)) AS decimal(18,4)) AS PLSAmt,
       CAST(SUM(ISNULL(g.Amount, 0)) AS decimal(18,4)) AS GIAAmt,
       CAST(SUM(ISNULL(g.Amount, 0)) - SUM(ISNULL(p.Amount, 0)) AS decimal(18,2)) AS DiffAmt{base}
GROUP BY e.Code, e.FirstName, e.LastName ORDER BY PNo DESC""")] if dept else []),

        # Which lab actually graded them. The client's report carries LAB as a
        # per-packet column; this is the same split, summarised.
        ("By lab", f"""
SELECT g.RapVer AS Lab,
       COUNT(DISTINCT g.Packet_ID) AS PNo,
       CAST(SUM(ISNULL(g.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(g.Amount, 0)) AS decimal(18,4)) AS GIAAmt{base}
GROUP BY g.RapVer ORDER BY PNo DESC"""),
    ]

    scope = ", ".join(filter(None, [
        f"kapan {kapan}" if kapan else "",
        f"department {dept}" if dept else "",
    ])) or "all kapans"
    parts = [
        f"LAB RESULTS (GIA/HRD/IGI) - {from_date} to {to_date} (end exclusive) - {scope}",
        "",
        "This is the client's own PLS-vs-GIA report and the figures below are "
        "already computed and reconciled against their ERP. Present the summary "
        f"and the {_lead_table(specs)} table, with the numbers exactly as given. "
        "Do NOT re-run "
        "these queries and do NOT add up preview rows by hand - the totals are in "
        "'Summary'. PLSAmt is the in-house assortment value, GIAAmt the "
        "lab-graded value, and DiffPer the percentage the lab came out above "
        "(positive) or below (negative) the in-house call.",
    ]
    sections = []
    for title, sql in specs:
        cols, rows, err = _rows(sql.strip())
        if err:
            parts += ["", f"## {title}", f"_(unavailable: {err})_"]
            continue
        if len(rows) == 1 and len(cols) > 2:
            parts += ["", f"## {title}"]
            parts += [f"- {c}: {0 if rows[0].get(c) is None else rows[0].get(c)}"
                      for c in cols]
        else:
            # The client reads this table straight across from their ERP screen,
            # which lists every kapan - a May report is 27 rows. The default
            # 8-row preview made the model render 8 and point at the download,
            # which reads as a different report, not a shorter one.
            parts += ["", f"## {title}", _preview(cols, rows, limit=_REPORT_ROWS)]
        if rows:
            sections.append({"title": title, "columns": cols, "rows": rows})

    return {
        "text": "\n".join(parts),
        "sections": sections,
        # `| totals:` tells facts.py which columns may be summed under the
        # table. DiffPer is excluded - a percentage does not add up.
        "sql": (f"-- lab_results_report('{from_date}', '{to_date}', "
                f"'{kapan}', '{dept or ''}')"
                " | totals: PNo, PWt, PLSAmt, GIAAmt, DiffAmt"),
    }


# A RECIPE FILTER THE USER NEVER ASKED FOR MUST BE DISCLOSED.
#
# Reported live 2026-08-26. The question was "Provide me last month GIA results
# employee wise" - no department named. The model called lab_results with
# department='Fency', because the by-employee section only exists when a
# department is passed (see the `if dept` above) and "Fency department employees"
# is the most-asked shape in the logs. The recipe did exactly as told.
#
# The answer then opened "Overall, 1,643 packets were processed across 27
# kapans" - ONE department's numbers presented as the company's. The true July
# figure is 3,692 packets across 39 kapans, so 56% of the work silently vanished
# and nothing on screen said "Fency".
#
# The recipe's own header DOES say "department Fency". The model dropped it -
# which is what prose does. So the disclosure is added to the ANSWER
# deterministically, where it cannot be dropped.
_DEPT_FILTER_RE = re.compile(r"DepartMentName\s*=\s*'([^']+)'", re.IGNORECASE)
_KAPAN_FILTER_RE = re.compile(r"KapanName\s*=\s*'([^']+)'", re.IGNORECASE)
_RANGE_RE = re.compile(
    r">=\s*'(\d{4}-\d{2}-\d{2})[^']*'.{0,120}?<\s*'(\d{4}-\d{2}-\d{2})[^']*'",
    re.IGNORECASE | re.DOTALL,
)


def _named_in(value: str, question: str) -> bool:
    """Did the user actually name this filter?

    Compared on the distinctive tokens so "MFG 1" in the question still covers a
    resolved "MFG - 1".
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", (value or "").lower()) if len(t) > 1]
    return bool(tokens) and all(t in (question or "").lower() for t in tokens)


def _period_text(sql_used) -> str:
    """The half-open range from the SQL, rendered inclusively for a human.

    The SQL is END-EXCLUSIVE, so '2026-07-01' to '2026-08-01' is July: the line
    must read 31 Jul, not 1 Aug, or it contradicts the report it labels.
    """
    from datetime import date, timedelta

    for sql in (sql_used or []):
        m = _RANGE_RE.search(sql or "")
        if not m:
            continue
        try:
            a = date(*(int(x) for x in m.group(1).split("-")))
            b = date(*(int(x) for x in m.group(2).split("-"))) - timedelta(days=1)
        except (ValueError, TypeError):
            continue
        if b < a:
            continue
        if (a.year, a.month) == (b.year, b.month) and a.day == 1:
            nxt = date(b.year + (b.month == 12), (b.month % 12) + 1, 1)
            if b + timedelta(days=1) == nxt:
                return f"{a:%B %Y}"          # a whole calendar month
        # %-d is glibc-only and raises on Windows, where this runs.
        if a.year == b.year:
            return f"{a.day} {a:%b} - {b.day} {b:%b %Y}"
        return f"{a.day} {a:%b %Y} - {b.day} {b:%b %Y}"
    return ""


def scope_line(question: str, sql_used: list[str] | None) -> str:
    """A one-line scope header for a report narrowed to a department or kapan.

    WHY THIS IS ALWAYS SHOWN, NOT ONLY WHEN THE FILTER WAS UNANNOUNCED.
    ------------------------------------------------------------------
    Reported live 2026-08-26: a Fency-scoped lab report opened "Overall, 1,643
    packets were processed across 27 kapans". The figures were CORRECT for Fency
    - the user had chosen it from a follow-up chip - but the word "Overall" makes
    a one-department result read as the company's, and the word "Fency" appeared
    nowhere in the prose. The recipe's own header did say "department Fency"; the
    model dropped it, which is what prose does.

    It matters because these answers are taken OUT of the chat and sent to the
    client to check against their own ERP. An answer that cannot state its own
    scope cannot be verified by the person reading it.

    So the scope is stated deterministically, whoever chose it. When the user did
    NOT name the filter, a nudge back to the company-wide figure is added too.

    Only ever PREPENDS a sentence - never touches a number, a row or a total - so
    a false positive costs one redundant line and nothing else.
    """
    q = question or ""
    found, unnamed = [], False
    for sql in (sql_used or []):
        for rx, kind in ((_DEPT_FILTER_RE, "department"), (_KAPAN_FILTER_RE, "kapan")):
            for m in rx.finditer(sql or ""):
                val = (m.group(1) or "").strip()
                if not val:
                    continue
                label = f"{kind} **{val}**"
                if label in found:
                    continue
                found.append(label)
                if not _named_in(val, q):
                    unnamed = True
    if not found:
        return ""
    period = _period_text(sql_used)
    bits = ", ".join(found) + (f" · {period}" if period else "")
    tail = (" — not the whole company. Ask again without naming it for the "
            "company-wide total.") if unnamed else "."
    return f"> **Scope:** {bits}{tail}"


# Kept as the narrow predicate the scope wording depends on.
def undisclosed_scope(question: str, sql_used: list[str] | None) -> str:
    """Back-compat: only the WARNING form, when the user never named the filter."""
    line = scope_line(question, sql_used)
    return line if "not the whole company" in line else ""


# The three labs the client grades at. "All labs" means these three - it does
# NOT mean "any value of tblPlanMaster.LAB", because that column's fourth value
# is 'NONE': a stone explicitly marked as never going to a lab. Counting those
# as "pending certification" would report work as waiting that nobody is
# waiting for (248 packets all-time, 246 of them in August 2026 alone).
_LABS = ("GIA", "HRD", "IGI")


def resolve_lab(name: str) -> tuple[str | None, str]:
    """Map a user-supplied lab name to a LAB code, or explain the failure.

    Returns (code, "") on success and (None, message) on failure. An empty
    `name` is not an error - it means ALL labs, which is the client's stated
    default.
    """
    raw = str(name or "").strip()
    if not raw:
        return None, ""
    code = raw.upper()
    if code in _LABS:
        return code, ""
    return None, (f"ERROR: '{raw}' is not a lab this factory grades at. "
                  f"The labs are {', '.join(_LABS)}. Ask the user which one "
                  "they meant, or run without a lab for all three.")


def pending_lab_report(from_date: str, to_date: str, department: str = "",
                       kapan: str = "", lab: str = "") -> dict:
    """POLISHED AND STILL SITTING THERE - not yet sent to a lab.

    `to_date` is EXCLUSIVE, as in the other recipes. `lab` is one of GIA / HRD /
    IGI; EMPTY MEANS ALL THREE, which is the client's stated default.

    WHY THIS EXISTS
    ---------------
    Asked "give me polished GIA pending for mfg-1 department of past month",
    the bot answered it from lab_results_report - the COMPLETED PLS-vs-GIA
    comparison - and reported 379 packets carrying BOTH a PLSAmt (16,248.69)
    and a GIAAmt (16,199.77). A packet pending GIA cannot have a GIA amount, so
    the answer contradicted itself; the follow-up "how many total were pending"
    then said 0 in the same session. Three further attempts to write it as SQL
    produced an inverted anti-join (0 by construction) and a filter on
    tblPacket.DepartMentId, the packet's CURRENT location, which a polished
    stone has long since left (0 again).

    THE DEFINITION THAT WAS HERE BEFORE WAS WRONG, AND A WRONG NUMBER SHIPPED
    ------------------------------------------------------------------------
    It read "has an approved PLS row AND has no approved GIA row" - a plain
    anti-join. That over-counts, because it also catches stones that HAVE moved
    on: graded at a lab other than GIA, or re-planned after grading. Measured
    on the question the client actually challenged - MFG - 1, July 2026 - the
    anti-join says 12 and the client says 2. Twelve is the figure that was
    quoted to them.

    What "pending" means to them is POSITIONAL, not an absence: the packet's
    LATEST approved, non-damage plan row IS its PLS row. The stone is polished
    and has not moved. Expressed that way the same question gives 2, matching
    them exactly. That is the definition below.

    It is written as "no LATER approved row exists" rather than as
    ROW_NUMBER() OVER (PARTITION BY Packet_ID ORDER BY CreatDate DESC, ID DESC)
    = 1. The two are equivalent, but ROW_NUMBER needs a window/CTE that the
    four section queries cannot share the way they share this WHERE fragment,
    and app.schema.views records how CTEs slip past ensure_row_cap.

    WHICH LAB, AND WHY THE QUESTION IS MEANINGFUL
    ---------------------------------------------
    The destination lab is recorded on the PLS row itself, in
    tblPlanMaster.LAB - so a stone that has been to NO lab still knows which
    lab it is waiting for. That is what makes "all labs, or a specific lab?" a
    real question rather than a rephrasing: all-time the pending stones split
    GIA 789 / HRD 27, with a further 248 marked LAB='NONE' that are not pending
    anything. Do NOT try to read the lab off the absent stage row - there is no
    such row, which is the whole point.

    DEPARTMENT IS THE MAKER, NOT THE LOCATION - the department of the worker on
    the packet's latest MFG plan row, exactly as lab_results_report scopes it.

    STILL OPEN: none of this reproduces the 201 the client reads off their own
    screen. That number is unexplained and must not be guessed at - it needs
    their query, or a few of their packet numbers run through
    scripts/packet_trace.py.
    """
    f, t = _q(from_date), _q(to_date)
    kap_filter = f" AND k.KapanName = '{_q(kapan)}'" if kapan else ""

    lab_code, lab_error = resolve_lab(lab)
    if lab_error:
        return {"text": lab_error, "sections": [], "sql": ""}

    dept, dept_suggestions = (resolve_department(department) if department
                              else (None, []))
    if department and not dept:
        hint = ("Closest matches: " + ", ".join(dept_suggestions)) if dept_suggestions else ""
        return {
            "text": (f"ERROR: no department matching '{department}'. {hint}\n"
                     "Ask the user which one they meant - do not guess."),
            "sections": [], "sql": "",
        }
    dept_filter = f" AND e.DepartMentName = '{_q(dept)}'" if dept else ""

    lab_list = ", ".join(f"'{c}'" for c in ((lab_code,) if lab_code else _LABS))
    lab_filter = f"\n  AND LTRIM(RTRIM(pls.LAB)) IN ({lab_list})"

    base = f"""
FROM tblPlanMaster pls WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON pls.KapanId = k.ID
OUTER APPLY (SELECT TOP 1 mm.EmpId FROM tblPlanMaster mm WITH (NOLOCK)
             WHERE mm.Packet_ID = pls.Packet_ID AND mm.RapVer = 'MFG'
             ORDER BY mm.ID DESC) m
LEFT JOIN tblEmployee e WITH (NOLOCK) ON e.ID = m.EmpId
WHERE pls.RapVer = 'PLS'
  AND ISNULL(pls.IsDamagePlan, 0) = 0
  AND pls.IsApproved = 1
  AND pls.CreatDate >= '{f}' AND pls.CreatDate < '{t}'{kap_filter}{dept_filter}{lab_filter}
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster nx WITH (NOLOCK)
                  WHERE nx.Packet_ID = pls.Packet_ID
                    AND ISNULL(nx.IsDamagePlan, 0) = 0
                    AND nx.IsApproved = 1
                    AND (nx.CreatDate > pls.CreatDate
                         OR (nx.CreatDate = pls.CreatDate AND nx.ID > pls.ID)))"""

    specs = [
        ("Summary", f"""
SELECT COUNT(DISTINCT pls.Packet_ID) AS PNo,
       COUNT(DISTINCT pls.KapanId) AS Kapans,
       CAST(SUM(ISNULL(pls.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(pls.Amount, 0)) AS decimal(18,4)) AS PLSAmt{base}"""),

        # Only when the user did NOT name a lab - otherwise it is a single row
        # restating the summary. This is the section that answers the
        # "which lab?" follow-up, so it comes before the kapan breakdown.
        *([("By lab", f"""
SELECT LTRIM(RTRIM(pls.LAB)) AS Lab,
       COUNT(DISTINCT pls.Packet_ID) AS PNo,
       CAST(SUM(ISNULL(pls.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(pls.Amount, 0)) AS decimal(18,4)) AS PLSAmt{base}
GROUP BY LTRIM(RTRIM(pls.LAB)) ORDER BY PNo DESC""")] if not lab_code else []),

        ("By kapan", f"""
SELECT k.KapanName AS Kapan,
       COUNT(DISTINCT pls.Packet_ID) AS PNo,
       CAST(SUM(ISNULL(pls.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(pls.Amount, 0)) AS decimal(18,4)) AS PLSAmt{base}
GROUP BY k.KapanName ORDER BY PNo DESC"""),

        # Only when a department was named - otherwise this is a long list
        # nobody asked for, the same trade lab_results_report makes.
        *([("By employee", f"""
SELECT e.Code, e.FirstName + ' ' + e.LastName AS Worker,
       COUNT(DISTINCT pls.Packet_ID) AS PNo,
       CAST(SUM(ISNULL(pls.PolishedWt, 0)) AS decimal(14,3)) AS PWt,
       CAST(SUM(ISNULL(pls.Amount, 0)) AS decimal(18,4)) AS PLSAmt{base}
GROUP BY e.Code, e.FirstName, e.LastName ORDER BY PNo DESC""")] if dept else []),
    ]

    lab_text = lab_code if lab_code else "all labs (" + "/".join(_LABS) + ")"
    scope = ", ".join(filter(None, [
        f"kapan {kapan}" if kapan else "",
        f"department {dept}" if dept else "",
        f"lab {lab_text}",
    ]))
    parts = [
        f"PENDING LAB CERTIFICATION - polished (PLS) and NOT yet sent to a lab - "
        f"{from_date} to {to_date} (end exclusive) - {scope}",
        "",
        "Definition: the packet's LATEST approved, non-damage plan row IS this "
        "PLS row - the stone is polished and has not moved on. This is NOT "
        "'has PLS and no GIA row'; that reading also counts stones that HAVE "
        "moved on, and gave 12 where the client counts 2. The lab shown is the "
        "DESTINATION recorded on the PLS row (tblPlanMaster.LAB), so a stone "
        "that has been to no lab still knows which one it is waiting for; "
        "stones marked LAB='NONE' are not going to a lab and are excluded. "
        "There is deliberately NO GIAAmt column here - a pending packet has "
        "not been graded, so it has no lab value. PLSAmt is the in-house "
        "assortment value of the work waiting. Present the summary and the "
        f"{_lead_table(specs)} table with the numbers exactly as given; do NOT "
        "re-run these queries or total preview rows by hand.",
    ]
    sections = []
    for title, sql in specs:
        cols, rows, err = _rows(sql.strip())
        if err:
            parts += ["", f"## {title}", f"_(unavailable: {err})_"]
            continue
        # A one-row summary reads far more reliably as key/value lines than
        # as one wide table row - the same choice the other recipes make.
        if len(rows) == 1 and len(cols) > 2:
            parts += ["", f"## {title}"]
            parts += [f"- {c}: {0 if rows[0].get(c) is None else rows[0].get(c)}"
                      for c in cols]
        else:
            parts += ["", f"## {title}", _preview(cols, rows, limit=_REPORT_ROWS)]
        if rows:
            sections.append({"title": title, "columns": cols, "rows": rows})

    return {
        "text": "\n".join(parts),
        "sections": sections,
        # `| totals:` tells facts.py which columns may be summed under the
        # table. There is deliberately no GIAAmt - a pending packet has not
        # been graded, so it has no lab value to total.
        "sql": (f"-- pending_lab_report('{from_date}', '{to_date}', "
                f"'{kapan}', '{dept or ''}', '{lab_code or 'ALL'}')"
                " | totals: PNo, PWt, PLSAmt"),
    }


# ---------------------------------------------------------------------------
# CUT-PURITY CHANGE - the client's own screen, reproduced exactly
# ---------------------------------------------------------------------------
# Their report compares the MFG plan against the GIA plan for ONE KAPAN and
# renders TWO separate tables: packets whose CUT changed, and packets whose
# PURITY changed. Verified against their screen for NI26 on 2026-08-31 and
# re-verified from a fresh screenshot on 2026-09-01 - 8 cut changes, 18 purity
# changes, identical packets, identical employee codes.
#
# WHY IT IS A RECIPE NOW. It was answered by the MODEL writing this SQL, and it
# worked - that is the standing evidence that free SQL is fine once the schema
# traps are rules. But it was the only verified report with no code behind it,
# so "it still matches their screen" rested on the model reproducing a
# five-join query with four traps in it, every time, for a report the client
# checks packet-for-packet. The query below is the verified one, byte for byte
# in its semantics; making it a recipe removes the chance of deviation, not the
# query. tests/test_cut_purity_change.py pins the result either way.
#
# THE TRAPS, all of which cost a wrong answer once:
#   * `Purity` IS clarity. There is no clarity column.
#   * ISNULL(IsDamagePlan, 0) = 0 on both sides.
#   * rn = 1 per (Packet_ID, RapVer) - the LATEST plan row for each stage.
#   * The plan row's own EmpCode, NOT a join to tblEmployee: names there are
#     not unique (15 rows share one), and an INNER JOIN silently drops the
#     Y-code Fency vendor firms, which are 3 of NI26's 18 purity changes.
#   * ISNULL(col, '') on BOTH sides of the comparison, so a NULL grade counts
#     as a change instead of vanishing from the result.
#
# The kapan filter sits INSIDE the CTE so the window function partitions over
# one kapan instead of all 1.3M plan rows (half a second warm, minutes cold).
# Safe because no packet's rows ever span two kapans - checked 2026-09-01:
#   SELECT COUNT(*) FROM (SELECT Packet_ID FROM tblPlanMaster
#     GROUP BY Packet_ID HAVING COUNT(DISTINCT KapanId) > 1) x   ->   0
# Both forms were run side by side and returned identical sets.
_CUT_PURITY_SQL = """
WITH s AS (
  SELECT pm.Packet_ID, pm.PacketName, pm.RapVer, pm.Cut, pm.Purity, pm.EmpCode,
         ROW_NUMBER() OVER (PARTITION BY pm.Packet_ID, pm.RapVer
                            ORDER BY pm.ID DESC) rn
  FROM tblPlanMaster pm WITH (NOLOCK)
  JOIN tblKapan k WITH (NOLOCK) ON k.ID = pm.KapanId AND k.KapanName = '{kapan}'
  WHERE ISNULL(pm.IsDamagePlan, 0) = 0)
SELECT a.PacketName AS Pkt, a.EmpCode AS Emp,
       a.{col} AS [MFG{col}], b.{col} AS [GIA{col}]
FROM s a
JOIN s b ON b.Packet_ID = a.Packet_ID AND b.RapVer = '{lab}' AND b.rn = 1
WHERE a.RapVer = 'MFG' AND a.rn = 1
  AND ISNULL(a.{col}, '') <> ISNULL(b.{col}, '')
ORDER BY a.{col}, b.{col}, a.EmpCode, a.PacketName"""


def resolve_kapan(name: str) -> tuple[str | None, list[str]]:
    """Match a kapan name to the exact spelling in tblKapan.

    Returns (exact_name_or_None, suggestions).

    DELIBERATELY EXACT - NO FUZZY MATCH, unlike resolve_department.
    Department names are typed loosely and "fancy" for "Fency" is a typo worth
    resolving. Kapan names are NOT: OS26 and OR26 both exist, NI26 and NS26
    both exist, and one letter apart is a DIFFERENT BATCH OF DIAMONDS, not a
    misspelling. We have already queried the wrong kapan twice on this project
    and quoted the client numbers for stones they were not asking about.
    So a near miss returns candidates and resolves nothing - the caller must
    ask which one they meant.
    """
    raw = (name or "").strip()
    if not raw:
        return None, []
    r = run_select(
        "SELECT DISTINCT KapanName FROM tblKapan WITH (NOLOCK) "
        "WHERE KapanName IS NOT NULL AND KapanName <> ''",
        max_rows=2000,
    )
    if not r.get("ok"):
        return None, []
    names = [row["KapanName"].strip() for row in r["rows"] if row.get("KapanName")]
    exact = {n.upper(): n for n in names}
    hit = exact.get(raw.upper())
    if hit:
        return hit, []
    # Same length, one character different: the exact trap above. Offer them.
    close = sorted(n for n in names
                   if len(n) == len(raw)
                   and sum(a != b for a, b in zip(n.upper(), raw.upper())) == 1)
    if close:
        return None, close[:12]
    return None, sorted(n for n in names if raw.upper() in n.upper())[:12]


def cut_purity_report(kapan: str, lab: str = "GIA") -> dict:
    """The CUT-PURITY CHANGE report for one kapan - MFG plan vs GIA plan.

    Takes NO period. The kapan IS the scope: a kapan is one batch of rough
    worked through the factory, so asking which month to compute it over is the
    same category error as asking for a date range on "how many are in stock".
    """
    # THE LAB WAS HARDCODED TO GIA. Measured 2026-09-03: 175 packets are
    # graded at HRD and 6 at IGI, and "MFG vs HRD cut grade" matched no recipe
    # at all - it fell through to free SQL, the unguarded path that returned
    # 337 rows against a true 288 for the GIA version of the same question.
    lab_code, lab_error = resolve_lab(lab)
    if lab_error:
        return {"text": lab_error, "sections": [], "sql": ""}
    lab_code = lab_code or "GIA"

    name, suggestions = resolve_kapan(kapan)
    if not name:
        hint = ("Did you mean: " + ", ".join(suggestions)) if suggestions else ""
        return {
            "text": (f"ERROR: no kapan named '{kapan}'. {hint}\n"
                     "Ask the user which kapan they meant - do NOT pick the "
                     "closest one. OS26 and OR26 both exist, NI26 and NS26 "
                     "both exist, and they are different batches of stones."),
            "sections": [], "sql": "",
        }

    specs = [("Cut changes", "Cut"), ("Purity changes", "Purity")]
    parts = [
        f"CUT-PURITY CHANGE - kapan {name} - the MFG plan against the "
        f"{lab_code} grade, as TWO separate tables.",
        "",
        f"State the kapan name ({name}) in the answer. Cut and purity are "
        "SEPARATE questions and must stay two tables - a packet can change "
        "purity without changing cut, and merging them into one 'changed' "
        "list is a different report from the one the client checks. Purity IS "
        "clarity. The Emp column is the plan row's own code; Y-codes are "
        "Fency job-work firms, not individual karigars. Present the counts and "
        "rows exactly as given; do NOT re-run these queries.",
    ]
    sections = []
    for title, col in specs:
        sql = _CUT_PURITY_SQL.format(kapan=_q(name), col=col, lab=lab_code)
        cols, rows, err = _rows(sql.strip())
        if err:
            parts += ["", f"## {title}", f"_(unavailable: {err})_"]
            continue
        parts += ["", f"## {title} ({len(rows)})",
                  _preview(cols, rows, limit=_REPORT_ROWS)]
        if rows:
            sections.append({"title": title, "columns": cols, "rows": rows})

    return {
        "text": "\n".join(parts),
        "sections": sections,
        # No `| totals:` - every column here is a grade or a code. Summing a
        # packet number would be meaningless, and facts.py must not offer to.
        "sql": f"-- cut_purity_report('{name}', '{lab_code}')",
    }


# ---------------------------------------------------------------------------
# PLAN-ROW REPORTS - the question shapes that had no recipe
#
# Audit 2026-09-03: of the eight shapes asked in a working session, three fell
# through to free SQL every time - and free SQL produced EVERY wrong answer of
# that session: 337 rows against a true 288, 1 packet against 4, 12 pending
# against 2. query_rules can reject a known-bad shape; it cannot make the model
# reconstruct sibling-plan handling or a positional stage test.
#
# So those shapes get recipes, with the lessons built in rather than hoped for:
#   1. NO latest-row dedupe. One rough packet is planned into SEVERAL stones
#      and those rows are SIBLINGS, not supersessions. NS26 packet 3 carries
#      three approved CLV rows written the same day; keeping only the newest
#      dropped the one that qualified and lost the packet entirely.
#   2. Attributes come off the PLAN ROW. tblPacket.Purity is the stone's
#      CURRENT grade and tblPacket.CurrentWt its present (often ROUGH) weight -
#      on QA26 the two readings returned almost disjoint sets.
#   3. The department is the PLAN'S AUTHOR, never tblPacket.DepartMentId,
#      which is where the stone is sitting today.
#   4. tblPacket is joined for PacketNo ONLY - tblPlanMaster.PacketName is
#      NULL on 13.4% of rows and on 96% of QA26's marking rows.
# ---------------------------------------------------------------------------

# Best first. These eleven are every value stored in tblPlanMaster.Purity.
# SI3 is in the trade ladder but not in this database, so it is not offered.
CLARITY_LADDER = ("FL", "IF", "VVS1", "VVS2", "VS1", "VS2",
                  "SI1", "SI2", "I1", "I2", "I3")


def resolve_clarity_range(lo, hi):
    """Expand "IF to VS2" into every grade between, inclusive.

    Returns (codes, "") or ([], message). Order is not assumed: "VS2 to IF"
    means the same span, because people read the ladder in both directions.
    """
    a = (lo or "").strip().upper()
    b = (hi or "").strip().upper()
    if not a and not b:
        return list(CLARITY_LADDER), ""
    for v in (a, b):
        if v and v not in CLARITY_LADDER:
            return [], ("ERROR: '" + v + "' is not a clarity grade in this "
                        "database. The grades are "
                        + ", ".join(CLARITY_LADDER)
                        + ". Ask which one was meant - do not guess.")
    i = CLARITY_LADDER.index(a) if a else 0
    j = CLARITY_LADDER.index(b) if b else len(CLARITY_LADDER) - 1
    if i > j:
        i, j = j, i
    return list(CLARITY_LADDER[i:j + 1]), ""


def _plan_filters(clarity_from, clarity_to, wt_min, wt_max):
    """Shared WHERE fragment plus a human description of what it narrowed."""
    codes, err = resolve_clarity_range(clarity_from, clarity_to)
    if err:
        return None, None, err
    bits, said = [], []
    if clarity_from or clarity_to:
        bits.append("  AND pm.Purity IN ("
                    + ", ".join("'" + c + "'" for c in codes) + ")")
        said.append("clarity " + "/".join(codes))
    if wt_min is not None:
        bits.append("  AND pm.PolishedWt >= " + str(float(wt_min)))
    if wt_max is not None:
        bits.append("  AND pm.PolishedWt <= " + str(float(wt_max)))
    if wt_min is not None or wt_max is not None:
        said.append("planned weight "
                    + (str(wt_min) if wt_min is not None else "-") + " to "
                    + (str(wt_max) if wt_max is not None else "-")
                    + " ct (inclusive)")
    return "\n".join(bits), ", ".join(said), None


_PLAN_COLS = """
SELECT k.KapanName AS Kapan,
       ISNULL(pk.PacketNo, pm.PacketName) AS PacketNo,
       pm.ID AS PlanId, pm.RapVer AS Stage,
       pm.Purity AS Clarity, pm.Color AS Colour, pm.Shape,
       pm.Cut, pm.Polish, pm.Symmetry,
       CAST(pm.PolishedWt AS decimal(10,3)) AS PlannedWt,
       CAST(pm.RoughWt AS decimal(10,3)) AS RoughWt,
       CAST(pm.Amount AS decimal(18,2)) AS PlanAmt,
       pm.IsApproved, ISNULL(pm.IsDamagePlan, 0) AS IsDamagePlan,
       e.Code AS EmpCode,
       LTRIM(RTRIM(e.FirstName + ' ' + ISNULL(e.LastName, ''))) AS EmpName,
       e.DepartMentName AS Department,
       CONVERT(char(10), pm.CreatDate, 120) AS PlanCreated
FROM tblPlanMaster pm WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON k.ID = pm.KapanId
{emp_join} tblEmployee e WITH (NOLOCK) ON e.ID = pm.EmpId
LEFT JOIN tblPacket pk WITH (NOLOCK) ON pk.ID = pm.Packet_ID
WHERE k.KapanName = '{kapan}'
{filters}
ORDER BY PlannedWt, pm.CreatDate, pm.ID"""


def _resolve_scope(kapan, department):
    """(name, dept, error_dict). Kapan is EXACT; a near miss never resolves."""
    name, suggestions = resolve_kapan(kapan)
    if not name:
        hint = ("Did you mean: " + ", ".join(suggestions)) if suggestions else ""
        return None, None, {
            "text": ("ERROR: no kapan named '" + str(kapan) + "'. " + hint
                     + "\nAsk which kapan was meant - do NOT pick the closest "
                       "one. OS26 and OR26 both exist, NI26 and NS26 both "
                       "exist, and they are different batches of stones."),
            "sections": [], "sql": ""}
    dept = None
    if department:
        dept, sugg = resolve_department(department)
        if not dept:
            hint = ("Closest matches: " + ", ".join(sugg)) if sugg else ""
            return None, None, {
                "text": ("ERROR: no department matching '" + str(department)
                         + "'. " + hint + "\nAsk which one - do not guess."),
                "sections": [], "sql": ""}
    return name, dept, None


def plan_rows_report(kapan, department="", stage="", clarity_from="",
                     clarity_to="", wt_min=None, wt_max=None,
                     approved_only=False):
    """PLANS CREATED by a department in one kapan, filtered on the plan row.

    `approved_only` defaults FALSE: an unapproved plan is still a plan someone
    created, and on QA26 half of Marker-2's were unapproved. IsApproved is a
    COLUMN so the caller can split on it instead of losing those rows silently.
    """
    name, dept, err = _resolve_scope(kapan, department)
    if err:
        return err
    filters, said, ferr = _plan_filters(clarity_from, clarity_to, wt_min, wt_max)
    if ferr:
        return {"text": ferr, "sections": [], "sql": ""}

    extra = []
    if dept:
        extra.append("  AND REPLACE(e.DepartMentName, ' ', '') = REPLACE('"
                     + _q(dept) + "', ' ', '')")
    if stage:
        extra.append("  AND pm.RapVer = '" + _q(str(stage).upper()) + "'")
    if approved_only:
        extra.append("  AND pm.IsApproved = 1 AND ISNULL(pm.IsDamagePlan, 0) = 0")

    sql = _PLAN_COLS.format(
        kapan=_q(name),
        # INNER only when a department was named - otherwise a plan whose author
        # row is missing would vanish without a word.
        emp_join="JOIN" if dept else "LEFT JOIN",
        filters="\n".join([f for f in [filters] + extra if f]))
    cols, rows, rerr = _rows(sql.strip())
    if rerr:
        return {"text": "ERROR running the plan query: " + str(rerr),
                "sections": [], "sql": sql}

    pkts = len({r.get("PacketNo") for r in rows})
    unappr = sum(1 for r in rows if not r.get("IsApproved"))
    scope = ", ".join([x for x in [
        "kapan " + name,
        "planned by " + dept if dept else "",
        "stage " + str(stage).upper() if stage else "",
        said] if x])
    parts = [
        "PLANS CREATED - " + scope,
        "",
        str(len(rows)) + " plan row(s) across " + str(pkts) + " packet(s)."
        + ((" " + str(unappr) + " of them are NOT approved.") if unappr else ""),
        "",
        "The unit is the PLAN, not the packet: one rough packet can be planned "
        "into several stones and each is a row here. Clarity, colour, shape and "
        "weight are the PLANNED values off the plan row - not the packet's "
        "current grade, and not its rough weight. The department is the plan's "
        "AUTHOR, not where the stone sits now. Present the rows exactly as "
        "given and do NOT re-run this query.",
        "",
        _preview(cols, rows, limit=_REPORT_ROWS),
    ]
    return {"text": "\n".join(parts),
            "sections": ([{"title": "Plans", "columns": cols, "rows": rows}]
                         if rows else []),
            "sql": "-- plan_rows_report('" + name + "', '"
                   + (dept or "") + "')"}


# ---------------------------------------------------------------------------
# STAGE GAP - "has an approved X plan but no approved Y plan yet"
#
# TWO READINGS, AND THEY DISAGREE. Measured on NS26 (CLV -> PLS, clarity
# IF..VS2, 0.50-1.00 ct): the anti-join says 1 packet and the positional
# reading says 0, because the one packet HAS moved on - to ADM - it simply
# never reached PLS. For MFG-1's GIA question the same split was 12 against 2.
#
# Neither is wrong; they answer different questions. So this report computes
# BOTH, returns the one asked for, and always states the other alongside it -
# the failure that cost trust was never the arithmetic, it was reporting one
# reading as if it were the only one.
# ---------------------------------------------------------------------------

_STAGE_GAP_SQL = """
SELECT k.KapanName AS Kapan,
       ISNULL(pk.PacketNo, pm.PacketName) AS PacketNo,
       pm.ID AS PlanId,
       pm.Purity AS Clarity, pm.Color AS Colour, pm.Shape,
       CAST(pm.PolishedWt AS decimal(10,3)) AS PlannedWt,
       CAST(pm.Amount AS decimal(18,2)) AS PlanAmt,
       e.Code AS EmpCode,
       LTRIM(RTRIM(e.FirstName + ' ' + ISNULL(e.LastName, ''))) AS EmpName,
       e.DepartMentName AS Department,
       CONVERT(char(10), pm.CreatDate, 120) AS PlanCreated,
       stand.RapVer AS LatestApprovedStage,
       COUNT(*) OVER (PARTITION BY pm.Packet_ID) AS QualifyingPlansOnThisPacket
FROM tblPlanMaster pm WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON k.ID = pm.KapanId
LEFT JOIN tblEmployee e WITH (NOLOCK) ON e.ID = pm.EmpId
LEFT JOIN tblPacket pk WITH (NOLOCK) ON pk.ID = pm.Packet_ID
CROSS APPLY (SELECT TOP 1 nx.RapVer
             FROM tblPlanMaster nx WITH (NOLOCK)
             WHERE nx.Packet_ID = pm.Packet_ID
               AND nx.IsApproved = 1
               AND ISNULL(nx.IsDamagePlan, 0) = 0
             ORDER BY nx.CreatDate DESC, nx.ID DESC) stand
WHERE k.KapanName = '{kapan}'
  AND pm.RapVer = '{done}'
  AND pm.IsApproved = 1
  AND ISNULL(pm.IsDamagePlan, 0) = 0
{filters}
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster x WITH (NOLOCK)
                  WHERE x.Packet_ID = pm.Packet_ID
                    AND x.RapVer = '{nxt}'
                    AND x.IsApproved = 1
                    AND ISNULL(x.IsDamagePlan, 0) = 0)
{positional}
ORDER BY PlannedWt, PacketNo"""

# "nothing came after this row" - the positional reading, as in dbo.GetPLSSUM.
_POSITIONAL = """  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster nx2 WITH (NOLOCK)
                  WHERE nx2.Packet_ID = pm.Packet_ID
                    AND nx2.IsApproved = 1
                    AND ISNULL(nx2.IsDamagePlan, 0) = 0
                    AND (nx2.CreatDate > pm.CreatDate
                         OR (nx2.CreatDate = pm.CreatDate
                             AND nx2.ID > pm.ID)))"""

# RST -> CLV -> ADM -> MKB -> MFG -> PLS -> GIA/HRD/IGI, plus the side stages.
STAGE_CODES = ("RST", "CLV", "ADM", "MKB", "MFG", "PLS",
               "GIA", "HRD", "IGI", "LSO", "BLK")


def stage_gap_report(kapan, done_stage, next_stage, clarity_from="",
                     clarity_to="", wt_min=None, wt_max=None,
                     positional=False):
    """Packets with an approved <done_stage> plan and no approved <next_stage>.

    `positional=False` (default) is the literal anti-join the question usually
    spells out. `positional=True` narrows to stones that have not moved at all -
    their <done_stage> row is still the packet's latest approved plan row.
    BOTH counts are always reported, whichever is asked for.
    """
    name, _dept, err = _resolve_scope(kapan, "")
    if err:
        return err
    done = str(done_stage or "").strip().upper()
    nxt = str(next_stage or "").strip().upper()
    for v, label in ((done, "done"), (nxt, "pending")):
        if v not in STAGE_CODES:
            return {"text": ("ERROR: '" + str(v) + "' is not a stage in this "
                             "database. The stages are "
                             + ", ".join(STAGE_CODES)
                             + " (RST -> CLV -> ADM -> MKB -> MFG -> PLS -> "
                               "GIA/HRD/IGI). Ask which was meant."),
                    "sections": [], "sql": ""}
    filters, said, ferr = _plan_filters(clarity_from, clarity_to, wt_min, wt_max)
    if ferr:
        return {"text": ferr, "sections": [], "sql": ""}

    out = {}
    for mode in ("anti", "positional"):
        sql = _STAGE_GAP_SQL.format(
            kapan=_q(name), done=_q(done), nxt=_q(nxt),
            filters=filters or "",
            positional=_POSITIONAL if mode == "positional" else "")
        cols, rows, rerr = _rows(sql.strip())
        if rerr:
            return {"text": "ERROR running the stage-gap query: " + str(rerr),
                    "sections": [], "sql": sql}
        out[mode] = (cols, rows)

    chosen = "positional" if positional else "anti"
    cols, rows = out[chosen]
    other = "anti" if positional else "positional"
    other_pkts = len({r.get("PacketNo") for r in out[other][1]})
    pkts = len({r.get("PacketNo") for r in rows})

    reading = ("STILL AT " + done + " - the " + done + " row is the packet's "
               "LATEST approved plan row, so the stone has not moved at all"
               if positional else
               "HAS " + done + ", HAS NO " + nxt + " - counted whether or not "
               "the stone moved on to some other stage")
    counter = ("the anti-join reading (has " + done + ", no " + nxt + ")"
               if positional else
               "the positional reading (still sitting at " + done + ")")
    scope = ", ".join([x for x in ["kapan " + name, said] if x])

    parts = [
        done + " done, " + nxt + " not yet - " + scope,
        "",
        "Reading used: " + reading + ".",
        str(len(rows)) + " plan row(s) across " + str(pkts) + " packet(s). "
        "For comparison, " + counter + " gives " + str(other_pkts) + " packet(s).",
        "",
        "STATE WHICH READING YOU USED. The two answer different questions and "
        "they disagree; reporting one as if it were the only one is how a "
        "figure gets challenged. LatestApprovedStage shows where each stone "
        "actually stands, so a packet that HAS moved on is visible rather than "
        "hidden in the WHERE clause. Clarity, colour and weight are the PLANNED "
        "values off the plan row. Present the rows as given; do NOT re-run this.",
        "",
        _preview(cols, rows, limit=_REPORT_ROWS),
    ]
    return {"text": "\n".join(parts),
            "sections": ([{"title": done + " without " + nxt,
                           "columns": cols, "rows": rows}] if rows else []),
            "sql": ("-- stage_gap_report('" + name + "', '" + done + "', '"
                    + nxt + "', positional=" + str(positional) + ")")}


# ---------------------------------------------------------------------------
# EMPLOYEE REPORT - "give me the report of employee M4117 for June 2026"
#
# ~8 of the 101 uncovered questions in the 2026-09-03 audit. The traps:
#
#   1. A NAME IS NOT AN IDENTITY. Fifteen tblEmployee rows share the name
#      MAIYANI VIJAYABHAI and nine share SUTARIYA NARESHKUMAR exactly.
#      Grouping on a name sums several people into one figure and reports it
#      as one worker's.
#   2. THE CODE IS NOT UNIQUE EITHER - B146, M2128 and M2D003 each map to two
#      employees. So even an exact code can be ambiguous, and when it is this
#      LISTS the candidates instead of picking one.
#   3. Y-CODES ARE VENDOR FIRMS, not karigars (MAHADEV JEMS, TRITH DIAMOND).
#      Ranking a firm beside an individual compares a company to a person.
#   4. PAY IS REFUSED UPSTREAM by access_guard.is_pay_question, before any LLM
#      call. This report deliberately carries NO money column - adding one
#      would route around a guard that exists on purpose.
# ---------------------------------------------------------------------------

def resolve_employee(who):
    """(rows, error). One row = resolved. Several = ambiguous, ASK.

    Matches an exact Code first, then an exact full name, then a substring.
    Never picks one when several match - see trap 1 and 2 above.
    """
    raw = (who or "").strip()
    if not raw:
        return [], "ERROR: no employee named. Ask for a code (e.g. M4117)."
    esc = _q(raw)
    r = run_select(
        "SELECT ID, Code, "
        "LTRIM(RTRIM(FirstName + ' ' + ISNULL(LastName, ''))) AS Name, "
        "DepartMentName, IsActive FROM tblEmployee WITH (NOLOCK) "
        f"WHERE Code = '{esc}' "
        f"   OR LTRIM(RTRIM(FirstName + ' ' + ISNULL(LastName,''))) = '{esc}' "
        f"   OR LTRIM(RTRIM(FirstName + ' ' + ISNULL(LastName,''))) LIKE '%{esc}%' "
        "ORDER BY CASE WHEN Code = '" + esc + "' THEN 0 ELSE 1 END, IsActive DESC, Code",
        max_rows=60)
    if not r.get("ok"):
        return [], "ERROR: could not read tblEmployee: " + str(r.get("error"))
    rows = r["rows"]
    if not rows:
        return [], (f"ERROR: no employee matching '{raw}'. Ask for the employee "
                    "CODE (like M4117 or CL213) - names are not unique here.")
    exact = [x for x in rows if (x.get("Code") or "").upper() == raw.upper()]
    if exact:
        rows = exact
    return rows, ""


_EMP_PLANS_SQL = """
SELECT pm.RapVer AS Stage,
       COUNT(*) AS Plans,
       COUNT(DISTINCT pm.Packet_ID) AS Packets,
       COUNT(DISTINCT pm.KapanId) AS Kapans,
       CAST(SUM(ISNULL(pm.PolishedWt, 0)) AS decimal(14,3)) AS PlannedWt,
       SUM(CASE WHEN pm.IsApproved = 1 THEN 1 ELSE 0 END) AS Approved
FROM tblPlanMaster pm WITH (NOLOCK)
WHERE pm.EmpId = {emp}
  AND pm.CreatDate >= '{f}' AND pm.CreatDate < '{t}'
GROUP BY pm.RapVer
ORDER BY COUNT(*) DESC"""

# tblPlanReport is the DAMAGE REGISTER. Amount there is POINTS x rate - a
# penalty-point deduction, NOT money - so it never carries a currency symbol.
_EMP_DAMAGE_SQL = """
SELECT COUNT(*) AS DamageReports,
       CAST(SUM(ISNULL(r.Points, 0)) AS decimal(12,2)) AS Points,
       CAST(SUM(ISNULL(r.Amount, 0)) AS decimal(12,2)) AS PointValue
FROM tblPlanReport r WITH (NOLOCK)
WHERE r.EmpID = {emp}
  AND r.IsDamageReport = 1
  AND r.CreatedDate >= '{f}' AND r.CreatedDate < '{t}'"""


def employee_report(who, from_date, to_date):
    """One worker's plans and damage over a period. NO money column - see 4."""
    rows, err = resolve_employee(who)
    if err:
        return {"text": err, "sections": [], "sql": ""}
    if len(rows) > 1:
        listing = "\n".join(
            f"  - {x['Code']} - {x['Name']} ({x['DepartMentName']}"
            + (", active" if x.get("IsActive") else ", left") + ")"
            for x in rows[:12])
        return {"text": (f"'{who}' matches {len(rows)} people. Ask which one - "
                         "do NOT add them together, that reports several "
                         "workers as one:\n" + listing),
                "sections": [], "sql": ""}

    emp = rows[0]
    eid, code, name = emp["ID"], emp["Code"], emp["Name"]
    dept = emp.get("DepartMentName") or "-"
    f, t = _q(from_date), _q(to_date)

    pcols, prows, perr = _rows(
        _EMP_PLANS_SQL.format(emp=int(eid), f=f, t=t).strip())
    dcols, drows, derr = _rows(
        _EMP_DAMAGE_SQL.format(emp=int(eid), f=f, t=t).strip())
    if perr or derr:
        return {"text": "ERROR running the employee report: "
                        + str(perr or derr), "sections": [], "sql": ""}

    total_plans = sum(r.get("Plans") or 0 for r in prows)
    total_pkts = sum(r.get("Packets") or 0 for r in prows)
    dmg = (drows[0] if drows else {}) or {}
    is_vendor = str(code or "").upper().startswith("Y")

    parts = [
        f"EMPLOYEE REPORT - {code} {name} ({dept}) - {from_date} to {to_date} "
        "(end exclusive)",
        "",
        f"{total_plans} plan row(s) across {total_pkts} packet(s), and "
        f"{dmg.get('DamageReports') or 0} damage report(s).",
        "",
        "IDENTIFY THE PERSON BY CODE, never by name: fifteen employees share "
        "one name in this database and even a code can map to two people. "
        "The figures below are PLANS THIS PERSON AUTHORED, by stage. There is "
        "deliberately NO pay, bonus or salary column here.",
    ]
    if is_vendor:
        parts.append(
            "NOTE: a Y-code is a Fency job-work FIRM, not an individual "
            "karigar - do not present it beside individuals as a person.")
    parts += ["", "## Plans authored", _preview(pcols, prows, limit=_REPORT_ROWS)]
    if dmg.get("DamageReports"):
        parts += [
            "",
            "## Damage",
            f"{dmg.get('DamageReports')} report(s), "
            f"{dmg.get('Points')} points, value {dmg.get('PointValue')}.",
            "tblPlanReport.Amount is POINTS x rate - a penalty-point "
            "deduction, NOT money. Never show it with a currency symbol.",
        ]

    sections = []
    if prows:
        sections.append({"title": "Plans authored", "columns": pcols,
                         "rows": prows})
    if drows and dmg.get("DamageReports"):
        sections.append({"title": "Damage", "columns": dcols, "rows": drows})
    return {"text": "\n".join(parts), "sections": sections,
            "sql": f"-- employee_report('{code}', '{from_date}', '{to_date}')"}


# ---------------------------------------------------------------------------
# KAPAN REPORT - "show me the full packet report for kapan NS26"
#
# ~7 of the 101 uncovered questions in the 2026-09-03 audit: "packet report for
# kapan AA", "Kapan Finish Report for NS26", "kapan Estimation report".
#
# THE TRAPS:
#   1. PIECES HAS THREE DEFENSIBLE ANSWERS and they disagree. NS26: 792 packet
#      rows, SUM(Pcs) 404, 768 finished rows. This gives all three and names
#      the one to prefer, rather than picking one silently.
#   2. tblKapanValue is a DAILY SNAPSHOT - the same kapan repeats once per
#      active day. SUM it and you are 77x out. Kapan totals come from tblKapan.
#   3. ChapkaLoss is populated on ONE kapan in the whole database. Reporting an
#      empty column as if it were a measurement is worse than saying it is not
#      tracked.
#   4. `Weight` is AMBIGUOUS - tblJunk and tblKapan both have one. Qualify it
#      or the query dies at runtime (it did, while this was being written).
#   5. tblFinalPacket.Amount is the finished value; tblKapan.RoughValue is the
#      rough. They are not comparable as "profit" - there is no cost data.
# ---------------------------------------------------------------------------

_KAPAN_HEADER_SQL = """
SELECT k.KapanName AS Kapan,
       k.Article, k.Mine, k.Size,
       CAST(k.Weight AS decimal(12,3)) AS RoughWt,
       k.TotalPcs AS DeclaredPcs,
       CASE WHEN ISNULL(k.IsFinished, 0) = 1 THEN 'finished' ELSE 'open' END AS Status,
       CONVERT(char(10), k.CreatDate, 120) AS Started,
       CONVERT(char(10), k.FinishDate, 120) AS Finished,
       CAST(k.BoilLoss AS decimal(10,3)) AS BoilLoss,
       CAST(k.RoughValue AS decimal(14,2)) AS RoughValue
FROM tblKapan k WITH (NOLOCK)
WHERE k.KapanName = '{kapan}'"""

# All three piece counts, and all three weights, in one pass. They disagree by
# design - see trap 1 - so the answer shows them side by side.
# NOTE: j.Weight is qualified on purpose - tblKapan has a Weight column
# too and an unqualified reference dies with 'Ambiguous column name'.
# The note lives here, not in the SQL: sql_guard rejects '--' comments
# in a query outright, which is how this recipe failed on first run.
_KAPAN_BODY_SQL = """
SELECT (SELECT COUNT(*) FROM tblPacket p WITH (NOLOCK)
        WHERE p.Kapan_ID = k.ID)                        AS PacketRows,
       (SELECT SUM(ISNULL(p.Pcs, 0)) FROM tblPacket p WITH (NOLOCK)
        WHERE p.Kapan_ID = k.ID)                        AS SumOfPcs,
       (SELECT COUNT(*) FROM tblFinalPacket f WITH (NOLOCK)
        WHERE f.KapanID = k.ID)                         AS FinishedRows,
       (SELECT CAST(SUM(ISNULL(p.RoughWt, 0)) AS decimal(12,3))
        FROM tblPacket p WITH (NOLOCK) WHERE p.Kapan_ID = k.ID) AS PacketRoughWt,
       (SELECT CAST(SUM(ISNULL(p.CurrentWt, 0)) AS decimal(12,3))
        FROM tblPacket p WITH (NOLOCK) WHERE p.Kapan_ID = k.ID) AS CurrentWt,
       (SELECT CAST(SUM(ISNULL(f.CurrentWt, 0)) AS decimal(12,3))
        FROM tblFinalPacket f WITH (NOLOCK) WHERE f.KapanID = k.ID) AS FinishedWt,
       (SELECT CAST(SUM(ISNULL(f.Amount, 0)) AS decimal(14,2))
        FROM tblFinalPacket f WITH (NOLOCK) WHERE f.KapanID = k.ID) AS FinishedValue,
       (SELECT CAST(SUM(ISNULL(j.Weight, 0)) AS decimal(12,3))
        FROM tblJunk j WITH (NOLOCK) WHERE j.Kapan_ID = k.ID)  AS JunkWt,
       (SELECT COUNT(*) FROM tblPlanReport r WITH (NOLOCK)
        WHERE r.KapanID = k.ID AND r.IsDamageReport = 1)       AS DamageReports,
       (SELECT COUNT(*) FROM tblJangadPackets jp WITH (NOLOCK)
        JOIN tblPacket p2 WITH (NOLOCK) ON p2.ID = jp.PacketId
        WHERE p2.Kapan_ID = k.ID AND ISNULL(jp.IsReceived, 0) = 0) AS OutOnJangad
FROM tblKapan k WITH (NOLOCK)
WHERE k.KapanName = '{kapan}'"""

_KAPAN_STAGES_SQL = """
SELECT pm.RapVer AS Stage,
       COUNT(DISTINCT pm.Packet_ID) AS Packets,
       CAST(SUM(ISNULL(pm.PolishedWt, 0)) AS decimal(12,3)) AS PlannedWt
FROM tblPlanMaster pm WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON k.ID = pm.KapanId
WHERE k.KapanName = '{kapan}'
  AND pm.IsApproved = 1
  AND ISNULL(pm.IsDamagePlan, 0) = 0
GROUP BY pm.RapVer
ORDER BY COUNT(DISTINCT pm.Packet_ID) DESC"""


def kapan_report(kapan):
    """Everything about one kapan: header, the three piece counts, the stage
    ladder, losses and damage. Takes NO period - the kapan IS the scope."""
    name, suggestions = resolve_kapan(kapan)
    if not name:
        hint = ("Did you mean: " + ", ".join(suggestions)) if suggestions else ""
        return {"text": ("ERROR: no kapan named '" + str(kapan) + "'. " + hint
                         + "\nAsk which kapan was meant - do NOT pick the "
                           "closest one. OS26 and OR26 both exist, NI26 and "
                           "NS26 both exist, and they are different stones."),
                "sections": [], "sql": ""}

    esc = _q(name)
    hcols, hrows, herr = _rows(_KAPAN_HEADER_SQL.format(kapan=esc).strip())
    bcols, brows, berr = _rows(_KAPAN_BODY_SQL.format(kapan=esc).strip())
    scols, srows, serr = _rows(_KAPAN_STAGES_SQL.format(kapan=esc).strip())
    if herr or berr or serr:
        return {"text": "ERROR running the kapan report: "
                        + str(herr or berr or serr), "sections": [], "sql": ""}

    h = (hrows[0] if hrows else {}) or {}
    b = (brows[0] if brows else {}) or {}

    parts = [
        "KAPAN REPORT - " + name
        + (" (" + str(h.get("Article")) + ")" if h.get("Article") else "")
        + " - " + str(h.get("Status") or "?"),
        "",
        "PIECES HAS THREE DEFENSIBLE ANSWERS AND THEY DISAGREE - say which one "
        "you used. " + str(b.get("PacketRows")) + " packet rows in tblPacket, "
        "SUM(Pcs) = " + str(b.get("SumOfPcs")) + ", and "
        + str(b.get("FinishedRows")) + " finished rows in tblFinalPacket. "
        "PREFER the tblPacket row count for 'how many packets/pieces are in "
        "this kapan' and say so.",
        "",
        "Weights likewise: RoughWt is the parcel as received, CurrentWt the "
        "packets as they stand, FinishedWt only the stones that completed. "
        "Do NOT subtract FinishedValue from RoughValue and call it profit - "
        "there is no cost data in this database.",
    ]
    if h.get("BoilLoss"):
        parts.append("")
        parts.append("Boil loss " + str(h.get("BoilLoss")) + " ct. Chapka loss "
                     "is NOT tracked - the column is populated on one kapan in "
                     "the whole database, so it is omitted rather than shown "
                     "as zero.")

    parts += ["", "## Kapan", _preview(hcols, hrows, limit=_REPORT_ROWS),
              "", "## Totals", _preview(bcols, brows, limit=_REPORT_ROWS),
              "", "## Stage ladder (approved, non-damage)",
              _preview(scols, srows, limit=_REPORT_ROWS)]

    sections = []
    if hrows:
        sections.append({"title": "Kapan", "columns": hcols, "rows": hrows})
    if brows:
        sections.append({"title": "Totals", "columns": bcols, "rows": brows})
    if srows:
        sections.append({"title": "Stage ladder", "columns": scols,
                         "rows": srows})
    return {"text": "\n".join(parts), "sections": sections,
            "sql": "-- kapan_report('" + name + "')"}


# ---------------------------------------------------------------------------
# PRODUCTION OVER TIME - "daily production 1-30 Jun", "packets made in June"
#
# ~6 of the 101 uncovered questions in the 2026-09-03 audit.
#
# PRODUCTION HAS TWO DEFENSIBLE BASES AND THEY DISAGREE. Measured on the
# 2026-08-21 backup:
#
#     May 2026   finished 3,227   MFG stage 2,777   -13.9%
#     Jun 2026   finished 4,007   MFG stage 3,993    -0.3%
#     Jul 2026   finished 4,476   MFG stage 4,517    +0.9%
#
# They count different EVENTS, not the same thing twice - only about
# three-quarters of each month's sets overlap. An unlabelled number that moves
# 14% between two reasonable readings is exactly how trust was lost here, so
# this recipe computes BOTH and always states which one it used.
#
#   FINISHED  tblFinalPacket.CreateDate - the stone was completed.
#   MFG       the maker's stage row. tblFinalPacket has no department, so any
#             per-worker or per-department question MUST use this basis.
# ---------------------------------------------------------------------------

_PROD_FINISHED_SQL = """
SELECT {bucket} AS Period,
       COUNT(*) AS Packets,
       COUNT(DISTINCT f.KapanID) AS Kapans,
       CAST(SUM(ISNULL(f.CurrentWt, 0)) AS decimal(14,3)) AS Carats
FROM tblFinalPacket f WITH (NOLOCK)
WHERE f.CreateDate >= '{f_}' AND f.CreateDate < '{t}'
{groupby}"""

_PROD_MFG_SQL = """
SELECT {bucket} AS Period,
       COUNT(DISTINCT pm.Packet_ID) AS Packets,
       COUNT(DISTINCT pm.KapanId) AS Kapans,
       CAST(SUM(ISNULL(pm.PolishedWt, 0)) AS decimal(14,3)) AS Carats
FROM tblPlanMaster pm WITH (NOLOCK)
WHERE pm.RapVer = 'MFG'
  AND pm.IsApproved = 1
  AND ISNULL(pm.IsDamagePlan, 0) = 0
  AND pm.CreatDate >= '{f_}' AND pm.CreatDate < '{t}'
{groupby}"""

_BUCKETS = {
    "day":   ("CONVERT(char(10), {c}, 120)", "day"),
    "month": ("CONVERT(char(7), {c}, 120)", "month"),
    "total": (None, "the whole period"),
}


def production_report(from_date, to_date, basis="finished", bucket="day"):
    """Production over a period, on a NAMED basis, with the other reported too.

    `basis` is "finished" (tblFinalPacket) or "mfg" (the maker's stage row).
    Anything per-worker or per-department must use "mfg" - tblFinalPacket
    carries no department at all.
    """
    b = (basis or "finished").strip().lower()
    if b not in ("finished", "mfg"):
        return {"text": ("ERROR: basis must be 'finished' (the stone was "
                         "completed) or 'mfg' (the maker's stage row). They "
                         "disagree by up to 14% in a month, so it has to be "
                         "chosen, not guessed."),
                "sections": [], "sql": ""}
    bk = (bucket or "day").strip().lower()
    if bk not in _BUCKETS:
        bk = "day"

    f_, t = _q(from_date), _q(to_date)
    datecol = "f.CreateDate" if b == "finished" else "pm.CreatDate"
    expr, bucket_word = _BUCKETS[bk]
    tmpl = _PROD_FINISHED_SQL if b == "finished" else _PROD_MFG_SQL
    if expr is None:
        period_sel, groupby = "'" + _q(from_date) + " to " + _q(to_date) + "'", ""
    else:
        period_sel = expr.format(c=datecol)
        groupby = "GROUP BY " + period_sel + "\nORDER BY 1"

    cols, rows, err = _rows(
        tmpl.format(bucket=period_sel, groupby=groupby, f_=f_, t=t).strip())
    if err:
        return {"text": "ERROR running the production query: " + str(err),
                "sections": [], "sql": ""}

    # The OTHER basis, as one total, so the answer can state the gap honestly.
    other = "mfg" if b == "finished" else "finished"
    other_tmpl = _PROD_MFG_SQL if other == "mfg" else _PROD_FINISHED_SQL
    other_col = "pm.CreatDate" if other == "mfg" else "f.CreateDate"
    _oc, orows, _oe = _rows(other_tmpl.format(
        bucket="'total'", groupby="", f_=f_, t=t).strip())
    other_n = (orows[0].get("Packets") if orows else None)

    total = sum(r.get("Packets") or 0 for r in rows)
    carats = sum(float(r.get("Carats") or 0) for r in rows)
    basis_word = ("stones FINISHED (tblFinalPacket.CreateDate)" if b == "finished"
                  else "stones at the MFG stage - the MAKER (tblPlanMaster "
                       "RapVer='MFG')")

    parts = [
        "PRODUCTION - " + from_date + " to " + to_date + " (end exclusive), by "
        + bucket_word,
        "",
        "Basis: " + basis_word + ". "
        + str(total) + " packets, " + f"{carats:,.3f}" + " ct.",
    ]
    if other_n is not None:
        gap = (100.0 * (other_n - total) / total) if total else 0
        parts.append(
            "The other basis (" + other + ") gives " + str(other_n)
            + f" packets over the same period, {gap:+.1f}%.")
    parts += [
        "",
        "SAY WHICH BASIS YOU USED, in one short clause - e.g. 'counted as "
        "stones finished in July'. The two count different EVENTS and only "
        "about three-quarters of each set overlaps; an unlabelled number that "
        "moves between them is how a figure gets challenged. Anything "
        "per-worker or per-department MUST use the MFG basis, because "
        "tblFinalPacket carries no department. Do NOT mix the two in one "
        "table. Present the rows as given; do NOT re-run this query.",
        "",
        _preview(cols, rows, limit=_REPORT_ROWS),
    ]
    return {"text": "\n".join(parts),
            "sections": ([{"title": "Production (" + b + ")",
                           "columns": cols, "rows": rows}] if rows else []),
            "sql": ("-- production_report('" + from_date + "', '" + to_date
                    + "', basis='" + b + "', bucket='" + bk + "')")}
