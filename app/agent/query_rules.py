"""
query_rules.py
--------------
WHICH TABLE ANSWERS THIS QUESTION - decided by rule, not by the model.

WHY
---
Measured on the client demo, 2026-08-21 vs 2026-08-24. The SAME question -
"provide total number of kapan wise by lab wise for may month" - produced:

    21 Aug   FROM tblPlanMaster  ... COUNT(DISTINCT pm.Packet_ID)   -> 89 rows
    22 Aug   FROM tblFinalPacket ... COUNT(PacketID)                -> 53 rows
    24 Aug   FROM tblFinalPacket ... COUNT(*)                       -> 53 rows

Neither matched the client's ERP (2,562). The router had handed the model BOTH
tables plus eight more and ~11,900 tokens of guidance, and nothing chose between
them - so each run chose differently, and the client saw a different answer every
time they asked.

The knowledge was already in glossary.py (see the LAB/GIA note): RapVer is the
STAGE a plan row came from and the LAB column is which lab certified. Prose in a
12k-token prompt did not make the model apply it. A rule that is injected as a
directive AND enforced against the generated SQL does.

HOW
---
Each rule is: when the question looks like X, the SQL MUST satisfy Y.
  - directive()  puts the requirement in the prompt (steer before generation)
  - violations() checks the SQL against it (catch after generation)
tool_run_sql refuses a violating query and tells the model exactly what to fix,
so a wrong table can never reach the user - the model gets one corrected round.

ADDING A RULE
-------------
Only add one whose number has been checked against the client's own report. An
unverified rule is the same guess as before, just harder to see. Every entry
below carries the query and figure it was verified with.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar

# The question being answered, so the SQL tool can check the SQL against it.
# Set once per turn by agent.ask(); tools run inside that same context.
_QUESTION: ContextVar[str] = ContextVar("current_question", default="")


def set_question(question: str) -> None:
    _QUESTION.set(question or "")


@contextmanager
def for_question(question: str):
    """
    Scope the question to ONE turn.

    Without the reset, the previous turn's question stays visible and its rules
    are applied to the next query - a lab rule could reject a perfectly good
    jangad query because the turn before it asked about GIA. Caught by the test
    suite, where a directly-called tool inherited an earlier test's question.
    """
    token = _QUESTION.set(question or "")
    try:
        yield
    finally:
        _QUESTION.reset(token)


def current_question() -> str:
    return _QUESTION.get()


class Rule:
    """A question shape, the SQL it demands, and how to say so."""

    def __init__(self, name, trigger, directive, require_all=(), forbid=(),
                 unless="", verified=""):
        self.name = name
        self.trigger = re.compile(trigger, re.IGNORECASE)
        # Wording that means the rule does NOT apply. "GIA certified" asks which
        # lab issued the certificate - that IS the LAB column, and forcing the
        # RapVer stage there would be a new wrong answer, not a fix.
        self.unless = re.compile(unless, re.IGNORECASE) if unless else None
        self.directive = directive
        self.require_all = require_all      # (regex, human explanation) pairs
        self.forbid = forbid                # (regex, human explanation) pairs
        self.verified = verified

    def applies(self, question: str) -> bool:
        q = question or ""
        if self.unless is not None and self.unless.search(q):
            return False
        return bool(self.trigger.search(q))

    def check(self, sql: str) -> list[str]:
        problems = []
        for rx, why in self.require_all:
            if not re.search(rx, sql or "", re.IGNORECASE):
                problems.append(why)
        for rx, why in self.forbid:
            # A forbid may be a CALLABLE instead of a regex. Some checks
            # cannot honestly be written as a pattern: "is this column read
            # off tblPacket" depends on which alias the query BOUND to
            # tblPacket, which a regex cannot know. Guessing it from the
            # alias's LENGTH was the hardcoded version - see
            # reads_grade_off_the_packet below.
            hit = rx(sql or "") if callable(rx) else re.search(
                rx, sql or "", re.IGNORECASE)
            if hit:
                problems.append(why)
        return problems


RULES: list[Rule] = [
    # -----------------------------------------------------------------------
    # LAB / GIA RESULTS
    # VERIFIED 2026-08-24 against the client's ERP figure of 2,562 for May 2026:
    #   SELECT COUNT(DISTINCT Packet_ID) FROM tblPlanMaster
    #   WHERE RapVer IN ('GIA','HRD','IGI')
    #     AND CreatDate >= '2026-05-01' AND CreatDate < '2026-06-01'   -> 2,562
    # (GIA 2,529 + HRD 31 + IGI 2, across 27 kapans.)
    # tblFinalPacket.Lab gives 3,227 / 1,723 for the same month - the wrong
    # question. RapVer='GIA' alone gives 2,529 and misses HRD and IGI, which is
    # what the client challenged us on in the meeting.
    # -----------------------------------------------------------------------
    Rule(
        name="lab_results",
        trigger=r"\b(gia|igi|hrd)\b|\blab\s*(wise|results?|report)|\blab\s+ma\b|\bsend\s+to\s+lab",
        directive=(
            "LAB / GIA RESULTS - USE THE lab_results TOOL. It returns the "
            "client's own PLS-vs-GIA report (summary, by kapan, by lab), "
            "reconciled against their ERP. Pass the period with to_date "
            "EXCLUSIVE. If you write SQL instead, it MUST use tblPlanMaster "
            "with RapVer IN ('GIA','HRD','IGI') and COUNT(DISTINCT Packet_ID), "
            "with the period on CreatDate: RapVer is the STAGE the plan row "
            "came from, while the LAB column says which lab certified and is "
            "NOT the filter. Never answer lab results from tblFinalPacket.Lab."
        ),
        require_all=(
            (r"\btblPlanMaster\b",
             "query tblPlanMaster (the lab-grading stage lives there), not "
             "tblFinalPacket"),
            (r"RapVer\s*(=|IN)",
             "filter on RapVer - RapVer IN ('GIA','HRD','IGI') for lab results "
             "generally, or a single stage if the user named one lab"),
            # THE COUNTED UNIT. Live run 2026-08-24: the model got the table and
            # the filter right, then wrote COUNT(DISTINCT KapanId) GROUP BY
            # KapanName - which is 1 for every row by construction - and
             # reported "49" where the client's ERP says 2,562.
            # A LIST IS NOT A COUNT, AND DEMANDING ONE REFUSES THE QUESTION.
            #
            # Reported live 2026-09-03. "For kapan OR26, show packets where the
            # MFG grade differs from the GIA grade on cut or clarity" is a
            # per-packet LISTING - it cannot contain COUNT(DISTINCT Packet_ID)
            # because it returns one row per packet. This requirement rejected
            # it, and the model, unable to satisfy a rule that contradicts the
            # question, REFUSED outright and offered lab_results instead. The
            # query it refused is the one that reproduces the client's own
            # CUT-PURITY CHANGE screen packet-for-packet.
            #
            # The requirement exists to stop a HOW-MANY question being answered
            # in the wrong unit (COUNT(DISTINCT KapanId) grouped by kapan is 1
            # by construction, and reported 49 where their ERP says 2,562). A
            # query with NO aggregate at all has no unit to get wrong, so it is
            # exempt. Anything that does aggregate must still count packets.
            #
            # NO BACKSLASHES - see the _ENFORCEMENT header. (?s) has to lead the
            # whole pattern; Python rejects a global flag mid-expression.
            (r"(?s)COUNT[ ]*[(][ ]*DISTINCT[ ]+[A-Za-z_]*[.]?Packet_ID"
             r"|^(?!.*(?:COUNT|SUM|AVG)[ ]*[(])",
             "count PACKETS with COUNT(DISTINCT Packet_ID) - the figure is how "
             "many packets each kapan sent to the lab. COUNT(DISTINCT KapanId) "
             "grouped by kapan is always 1 and COUNT(*) double-counts stage "
             "rows. A per-packet LISTING with no aggregate at all is fine as "
             "it is - this applies only when you are reporting a total"),
        ),
        forbid=(
            (r"\btblFinalPacket\b\s*(?:\w+\s*)?(?:WITH\s*\(NOLOCK\)\s*)?(?![^;]*\btblPlanMaster\b)",
             "tblFinalPacket.Lab is a different question (finished stones by "
             "certifying lab) and gives a different number - use tblPlanMaster"),
        ),
        unless=r"certif",   # "GIA certified" = the LAB column, a different question
        verified="May 2026 = 2,562 packets (GIA 2,529 + HRD 31 + IGI 2)",
    ),

    # -----------------------------------------------------------------------
    # PLANNING "VERIFIED" / APPROVED
    # MEASURED 2026-08-24 on the refreshed DB:
    #   tblPlanMaster.IsVerified = 1 -> 14 rows in the WHOLE database
    #   tblPlanMaster.IsApproved = 1 -> 1,080,036 rows / 31,317 packets in 2026
    # The client asks "aa varsh ma ketla planning verify thaya che?" (27 times in
    # the logs). The column whose NAME matches the word they used is a dead flag;
    # answering from it reports 14 for a year in which 31,317 packets were signed
    # off. Approval is also what carries a date (ApproveDate).
    # -----------------------------------------------------------------------
    Rule(
        name="planning_verified",
        trigger=r"verif(y|ied|ication)|approv(e|ed|al)|verify thaya|sign(ed)?.off",
        # NO FIGURES IN THIS DIRECTIVE. It used to read "IsVerified is set
        # on 14 rows in the entire database, while IsApproved covers 31,317
        # packets in 2026" - and on 2026-09-03 the model answered "14" to
        # "aa varsh ma ketla planning verify thaya che?", TWICE, reciting
        # the dead flag's row count as the year's sign-off total. A
        # directive is injected BEFORE the model queries, so any number in
        # one is an answer it can give without running SQL.
        #
        # The measured figures live in the comment above and in the
        # rejection message below - the model sees neither until it has
        # already written the wrong query.
        directive=(
            "PLANNING VERIFIED/APPROVED - use tblPlanMaster.IsApproved = 1 "
            "(and ApproveDate for when). IsVerified is a DEAD flag, set on "
            "a negligible handful of rows in the whole database, while "
            "IsApproved is what actually carries sign-off. Count packets "
            "with COUNT(DISTINCT Packet_ID). Do NOT state any total you "
            "have not just read out of a query result."
        ),
        forbid=(
            (r"IsVerified",
             "use IsApproved, not IsVerified - IsVerified is set on only 14 rows "
             "in the whole database and reports a year of sign-offs as 14"),
        ),
        verified="IsApproved 2026 = 31,317 packets; IsVerified all-time = 14 rows",
    ),

    # -----------------------------------------------------------------------
    # REPAIRS
    # MEASURED 2026-08-24: for calendar 2025, tblRepairLogNew returns 150,706
    # (it is a generic CRUD audit trail) against a TRUE 3,302 in
    # tblRepairCommentVision - 46x inflated. tblRepairLog is a UI click log,
    # dead since 2022-02-19. July 2026: 41 real repairs vs 9,494 from the decoy.
    # tblRepairCommentVision starts 2025-04-08, so earlier trends do not exist.
    # -----------------------------------------------------------------------
    Rule(
        name="repairs",
        trigger=r"repair|repairing",
        directive=(
            "REPAIRS - the ONLY repair register is tblRepairCommentVision, and "
            "its data STARTS 2025-04-08, so there is no earlier repair history "
            "to trend. tblRepairLogNew is a generic audit trail (46x inflated: "
            "150,706 rows for 2025 against a true 3,302) and tblRepairLog is a "
            "dead UI click log. The reason for a repair is RepairComment, not "
            "the blank Reason column."
        ),
        forbid=(
            # matches tblRepairLog AND tblRepairLogNew - both are wrong here
            (r"tblRepairLog",
             "use tblRepairCommentVision - tblRepairLog is a dead UI click log "
             "and tblRepairLogNew is a CRUD audit trail that inflates repair "
             "counts about 46x"),
        ),
        verified="2025 repairs = 3,302 (decoy gives 150,706); July 2026 = 41",
    ),

    # -----------------------------------------------------------------------
    # ATTENDANCE - not answerable, and saying so is the correct answer.
    # tblTimeAttendance stops 2025-04-05 and its EmpId is NULL on all 393,882
    # rows, so a punch can never be tied to a named person. tblTimeAttendance_Demo
    # is seeded test data (2021) and tblEmployeeTimeAttandance a 2017 gate-pass
    # register. There is no live attendance feed in this database.
    # -----------------------------------------------------------------------
    Rule(
        name="attendance",
        trigger=r"attendance|punch|haajri|hajri|present today|kitne.*present",
        directive=(
            "ATTENDANCE IS NOT ANSWERABLE from this database and you must say so "
            "plainly instead of returning a number. tblTimeAttendance stopped on "
            "2025-04-05 and its EmpId is NULL on all 393,882 rows, so punches can "
            "never be attributed to a named employee; tblTimeAttendance_Demo is "
            "seeded test data and tblEmployeeTimeAttandance a 2017 gate-pass log. "
            "Say the attendance feed stopped in April 2025 and offer headcount "
            "(tblEmployee.IsActive = 1) instead."
        ),
        verified="tblTimeAttendance ends 2025-04-05; EmpId NULL on all 393,882 rows",
    ),

    # -----------------------------------------------------------------------
    # MATCH PAIR + ORDER LINKAGE - shipped in the 2026-08-21 backup, NOT YET USED
    # MEASURED 2026-08-24:
    #   tblMatchPairCriteria            664 rows  (catalogued CERTIFIED STONES,
    #                                   one row per stone: StoneNo, Lab, ReportNo,
    #                                   4Cs, measurements - NOT pairs)
    #   tblMatchPairTolerance             1 row   (the matching tolerance profile)
    #   tblAllowMatchPair*Permission      0 rows
    #   tblPlanMaster.IsMatchPair = 1     0 rows   MatchPairId: all NULL
    #   tblPlanMaster.OrderDetailId     182 of 1,316,677 (0.01%), GUIDs, first
    #                                   written 2026-08-21; tblPacket 16 of 172,233
    #   and there is NO populated order table for those GUIDs to point at.
    # Both risks are real: "how many match pairs do we have?" reads 664 off the
    # criteria table and calls them pairs, or reads IsMatchPair, gets 0, and
    # reports "no match pairs" as if the pairing had failed.
    # -----------------------------------------------------------------------
    Rule(
        name="match_pair_and_orders",
        trigger=r"match.?pair|matched pair|order.?detail|order.?wise|order linkage",
        directive=(
            "MATCH PAIR / ORDER LINKAGE ARE NEW AND NOT YET IN USE - say that "
            "rather than reporting a number. tblPlanMaster.IsMatchPair is 1 on "
            "ZERO rows and every MatchPairId is NULL, so no stone has been "
            "match-paired yet. tblMatchPairCriteria is a catalogue of candidate "
            "CERTIFIED STONES - ONE ROW PER STONE, NOT PER PAIR - so never "
            "report its row count as a number of pairs; tblMatchPairTolerance "
            "is just the tolerance profile. OrderDetailId is populated on a "
            "negligible fraction of rows and there is no populated order table "
            "to join it to. The honest answer is that the feature is configured "
            "but carries no production data yet. Count it if you must quote a "
            "figure - never quote one from this rule."
        ),
        verified="IsMatchPair=1 on 0 rows; criteria 664 stones; OrderDetailId 182/1,316,677",
    ),

    # -----------------------------------------------------------------------
    # PRODUCTION - two defensible definitions that do NOT agree.
    # MEASURED 2026-08-24 (packets):
    #     period     tblFinalPacket   MFG-stage   divergence
    #     May 2026            3,227       2,783      -13.8%
    #     Jun 2026            4,007       4,001       -0.1%
    #     Jul 2026            4,476       4,555       +1.8%
    # Only 3,358 packets appear in BOTH July sets, so about a quarter of each is
    # absent from the other - they count different EVENTS (a stone was finished
    # vs a maker's plan row was created), not the same thing measured twice.
    #
    # NOT ERP-VERIFIED: which one the client's production screen shows is still
    # an open question. So this rule does not force a table - it forces the
    # answer to SAY which basis it used. An unlabelled number that moves 13.8%
    # between two reasonable readings is exactly how trust was lost.
    # -----------------------------------------------------------------------
    Rule(
        name="production_basis",
        trigger=r"production|produced|output|nang thaya|manufactur",
        directive=(
            "PRODUCTION HAS TWO BASES AND THEY DISAGREE (by up to 14% in a "
            "month), so NAME the one you used in the answer. Finished output = "
            "tblFinalPacket.CreateDate (the stone was completed). Output "
            "attributed to a worker or department = the tblPlanMaster "
            "RapVer='MFG' row, because tblFinalPacket has no department. Use "
            "FINISHED output for 'how much did we produce', and the MFG stage "
            "whenever the question is per-worker or per-department - then say "
            "so in one short clause, e.g. 'counted as stones finished in July'. "
            "Do not mix the two bases in one table."
        ),
        verified="May 3,227 vs 2,783; Jun 4,007 vs 4,001; Jul 4,476 vs 4,555",
    ),

    # -----------------------------------------------------------------------
    # GOODS OUT: JANGAD / MEMO
    # MEASURED 2026-08-24, three independent paths agreeing exactly:
    #   tblJangadPackets.IsReceived = 0                          -> 1,072
    #   ...with the parent jangad TransType = 'Issue'            -> 1,072
    #   ...with the parent jangad also unreceived                -> 1,072
    #   tblPacket.IsOnMemo = 1                                   -> 1,073
    # and 1,072 of the on-memo packets ARE the out-on-jangad ones: memo and
    # jangad are the SAME physical state recorded twice, differing by a single
    # packet. tblJangad itself is the MOVEMENT register (17,220 Issue/Receive
    # rows) - counting it answers "how many jangad movements ever", not "how
    # many packets are out", which is off by a factor of 16.
    # -----------------------------------------------------------------------
    Rule(
        name="jangad_memo",
        trigger=r"jangad|on memo|out on memo|memo right now|memo par",
        directive=(
            "PACKETS OUT ON JANGAD / MEMO: count PACKET rows in "
            "tblJangadPackets WHERE ISNULL(IsReceived,0) = 0 (join tblJangad "
            "only for the party/date). tblJangad itself is the movement "
            "register - one row per Issue or Receive - so counting it answers a "
            "different question and overstates by roughly 16x. 'On memo' "
            "(tblPacket.IsOnMemo = 1) is the SAME goods-out state recorded "
            "separately and agrees to within one packet, so do not present the "
            "two as different populations."
        ),
        require_all=(
            (r"tblJangadPackets",
             "count packets from tblJangadPackets, not tblJangad - tblJangad is "
             "the movement register (one row per Issue/Receive), not a packet list"),
        ),
        unless=r"party|gst|process|water\s*jet|branch|firm",
        verified="1,072 packets out (3 independent paths agree); IsOnMemo=1 gives 1,073",
    ),

    # -----------------------------------------------------------------------
    # HEADCOUNT
    # tblEmployeeCount is dead since 2021-07-23 and its last value is 420
    # against 369 real actives today - the most attractive table name for the
    # question and wrong by 14%.
    # -----------------------------------------------------------------------
    Rule(
        name="headcount",
        trigger=r"how many (employees|workers|karigar|staff)|total (employees|workers|karigar)|"
                r"ketla (mansu|karigar)|kitne (employee|log|karigar)|headcount|workforce",
        directive=(
            "HEADCOUNT: count tblEmployee WHERE IsActive = 1 (369 today). The "
            "unfiltered roster is a decade of leavers and roughly ten times the "
            "real size, so always say the figure is ACTIVE employees. Never use "
            "tblEmployeeCount - it stopped in July 2021 and its last value (420) "
            "is 14% above the truth."
        ),
        forbid=(
            (r"tblEmployeeCount",
             "use tblEmployee WHERE IsActive = 1 - tblEmployeeCount died in 2021 "
             "and its last value is 420 against 369 real actives"),
        ),
        verified="tblEmployee IsActive=1 = 369; tblEmployeeCount dead 2021-07-23, last 420",
    ),

    # -----------------------------------------------------------------------
    # STOCK - genuinely ambiguous, so the answer must SAY what it counted.
    # MEASURED 2026-08-24: tblPacket holds 172,233 packets EVER created.
    #   RunningProcess = 'IN Stock'                 -> 155,841  (90% of all time)
    #   no tblFinalPacket row yet (unfinished/WIP)  ->  16,924
    #   IsRejected = 1                              ->  10,740
    # 155,841 of 172,233 cannot mean "in stock right now", and nothing in the
    # schema settles which figure the client's stock screen shows. Unlike the
    # lab report there is no ERP screenshot to check against, so this rule does
    # not pick - it forces the basis to be stated and the alternative offered.
    # -----------------------------------------------------------------------
    Rule(
        name="stock_basis",
        trigger=r"in stock|stock report|stock right now|stock ma|hold par|on hold|"
                r"hold ma|how many .*(do we have|in hand)",
        directive=(
            "STOCK IS NOT A SETTLED DEFINITION HERE - say which basis you used "
            "and offer the other. tblPacket holds every packet ever created. "
            "RunningProcess = 'IN Stock' covers most of them, which is all of "
            "history and so cannot mean 'right now'; packets with no "
            "tblFinalPacket row are the unfinished ones. State plainly what you "
            "counted, e.g. 'counting packets currently flagged IN Stock', and "
            "add one line offering the other basis. Do NOT present a stock "
            "number as settled fact. HOLD IS KAPAN-LEVEL, NOT PACKET-LEVEL: "
            "tblPacket.IsOnHold is effectively dead and must never be counted. "
            "Packets on hold = the packets of HELD KAPANS: JOIN tblKapan k ON "
            "p.Kapan_ID = k.ID WHERE k.IsOnHold = 1. Query it; never quote a "
            "figure from these rules as the answer."
        ),
        verified="172,233 packets ever; 155,841 IN Stock; 16,924 unfinished; hold = 34 kapans / 11,967 packets (tblPacket.IsOnHold dead at 2)",
    ),

    # -----------------------------------------------------------------------
    # DAMAGE - two near-identical paths; prefer the register, note the gap.
    # MEASURED 2026-08-24: tblPlanReport.IsDamageReport = 133 / 159 / 179 for
    # May / Jun / Jul 2026, vs tblPlanMaster.IsDamagePlan = 137 / 157 / 175.
    # Close but never equal; the register is the reporting artefact the client
    # works from, and damage is POINTS, not rupees.
    # -----------------------------------------------------------------------
    Rule(
        name="damage",
        trigger=r"damage|damaged|nuksan|bhangar.*damage",
        directive=(
            "DAMAGE: use tblPlanReport WHERE IsDamageReport = 1 (the damage "
            "register), dated on CreatedDate. tblPlanMaster.IsDamagePlan is a "
            "flag on the plan row and gives a slightly different count (175 vs "
            "179 for July 2026) - do not mix them in one answer. "
            "tblPlanReport.Amount is POINTS x rate, a penalty-POINT deduction, "
            "NOT money: never present it with a currency symbol."
        ),
        # ENFORCED, not advised. The directive above ALREADY fired on
        # "2025 ma damage na ketla paisa katya karigar pase thi?" (verified
        # 2026-08-26) and the answer still came back -14,816.33 where the
        # register gives -11,536.82. A rule with no require_all/forbid is a
        # suggestion, and a suggestion is what the model had just ignored.
        require_all=(
            (r"tblPlanReport", "a damage figure must come from tblPlanReport "
                               "(the damage register), not another table"),
            (r"IsDamageReport", "filter the damage register with "
                                "IsDamageReport = 1"),
        ),
        forbid=(
            (r"IsDamagePlan", "IsDamagePlan is the PLAN-row flag and gives a "
                              "different count - use tblPlanReport."
                              "IsDamageReport for a damage total"),
        ),
        verified="IsDamageReport May/Jun/Jul 2026 = 133/159/179; IsDamagePlan = 137/157/175; "
                 "2025 total = -11,536.82",
    ),

    # -----------------------------------------------------------------------
    # EMPLOYEE BONUS / LABOUR EARNINGS
    # MEASURED 2026-08-24 for June 2026 (a COMPLETE month for this feed):
    #   tblPointRateLabour  26,790 rows | tblLabourResult  0 rows  (dead 2023)
    #   SUM(BonusAmount)   =    653.10   <- the bonus
    #   SUM(FinalLabour)   = 80,763.23   <- total earnings, 123x larger
    #   top-5 by bonus vs top-5 by earnings share only 1 of 5 PEOPLE
    #   4,446 rows carry a NEGATIVE BonusAmount (a deduction, not an award)
    #   3.09 rows per packet, so COUNT(*) and naive joins inflate
    #   EmpName is a CODE ('M3073') on every row - never a person's name
    # Getting the column wrong does not just move a number, it names the WRONG
    # PEOPLE in front of the client.
    # -----------------------------------------------------------------------
    Rule(
        name="bonus_earnings",
        trigger=r"bonus|incentive|labour amount|earning|kamai|payout|"
                r"ketla rupiya|highest paid",
        directive=(
            "BONUS vs EARNINGS ARE DIFFERENT COLUMNS on tblPointRateLabour and "
            "mixing them names the wrong people: BonusAmount is the bonus "
            "(653.10 across June 2026), FinalLabour is total earnings (80,763.23 "
            "- 123x larger), and the top-5 lists overlap by only one person. Use "
            "BonusAmount for 'bonus', FinalLabour for 'earnings/labour/how much "
            "did they make'. BonusAmount can be NEGATIVE (a deduction) - keep the "
            "sign and say so. Get names by joining Emp_ID to tblEmployee.ID: "
            "EmpName on this table is a CODE like 'M3073'. The feed is posted in "
            "arrears, so the most recent weeks are incomplete, not a drop."
        ),
        forbid=(
            (r"tblLabourResult(?!GIA)",
             "use tblPointRateLabour - tblLabourResult stopped in 2023 and "
             "returns 0 rows for any 2026 month, which reads as 'no bonus paid'"),
        ),
        verified="June 2026: BonusAmount 653.10 vs FinalLabour 80,763.23; "
                 "top-5 lists overlap 1 of 5; tblLabourResult 0 rows",
    ),

    # -----------------------------------------------------------------------
    # SALES / REVENUE - NOT IN THIS DATABASE AT ALL.
    # MEASURED 2026-08-24: no tblSales, tblSalesMaster, tblSalesDetail,
    # tblInvoice or tblBuyer exists; tblParty holds 59 rows of party MASTER data
    # only. tblJangad.Amount (51,769,806.75) is the value of goods MOVED on
    # jangad, and tblPacket.PAmount (8,254,627.23) is a packet valuation -
    # presenting either as sales revenue would invent a number the business
    # never recorded here.
    # -----------------------------------------------------------------------
    Rule(
        name="sales_not_recorded",
        trigger=r"\bsales?\b|revenue|turnover|vechya|buyer.?wise|sold|invoice|"
                r"dollar aavya|profit margin",
        directive=(
            "NO SALES HAVE BEEN RECORDED - but do NOT say the tables do not "
            "exist. The ERP DOES support selling: tblPacketSell (SellDollar, "
            "SellDate, SellDisc, RapPrice) and tblBuyerName both exist - "
            "tblPacketSell is simply EMPTY and tblBuyerName holds only master "
            "rows. Say the feature exists but no sales data has been posted "
            "yet; telling the client their ERP has no sales table is wrong and "
            "they will know it. tblParty is party master data. tblJangad.Amount "
            "is the VALUE OF GOODS MOVED on jangad and tblPacket.PAmount is a "
            "packet valuation - neither is sales revenue, so never present them "
            "as money earned. Offer what does exist: goods movement by party, "
            "or packet valuations."
        ),
        verified="tblPacketSell EXISTS but is empty (0 rows); tblBuyerName = 8 rows; tblParty = 59 master rows",
    ),

    # -----------------------------------------------------------------------
    # JUNK - weight and pieces are real, GRADE is not.
    # MEASURED 2026-08-24: tblJunk holds 215,158 rows and 76,887.352 total
    # weight, but Grede (yes, misspelled) is NULL on ALL 215,158 of them. The
    # client asks for junk "grade-wise", so this must be said, not returned as a
    # single blank row. Also misspelled: IsIssed (issued), IsRecyleble.
    # -----------------------------------------------------------------------
    Rule(
        name="junk",
        trigger=r"junk|scrap|bhangar",
        directive=(
            "JUNK: tblJunk has real Weight and Pcs (215,158 rows, 76,887.352 "
            "total weight) but its grade column - spelled Grede - is NULL on "
            "EVERY row, so a grade-wise junk report cannot be produced. Say that "
            "grade is not recorded rather than returning one blank group. Note "
            "the misspellings: Grede, IsIssed, IsRecyleble. Break junk down by "
            "kapan or by month instead, which both work."
        ),
        verified="tblJunk 215,158 rows, Grede NULL on all of them",
    ),

    # -----------------------------------------------------------------------
    # KAPAN LOSS - boil is recorded, chapka is not.
    # MEASURED 2026-08-24 over 865 kapans: BoilLoss populated on 812 (total
    # 478.710), ChapkaLoss on exactly 1 (19.250), DifferWeight on 60 (0.833).
    # The client asks for boil and chapka "alag alag" (separately), so a chapka
    # column would be an empty promise.
    # -----------------------------------------------------------------------
    Rule(
        name="kapan_loss",
        trigger=r"\bloss\b|boil|chapka|yield|ghat|weight loss",
        directive=(
            "KAPAN LOSS: BoilLoss is real and populated on nearly every kapan. "
            "ChapkaLoss is populated on a single kapan and DifferWeight on a "
            "handful, so chapka loss is effectively NOT RECORDED: if the user "
            "asks for boil and chapka separately, give boil and say chapka is "
            "not tracked rather than showing an empty column. Packet-level loss "
            "lives on tblPacket (WeightLoss, JunkLoss)."
        ),
        verified="BoilLoss 812/865 kapans; ChapkaLoss 1/865; DifferWeight 60/865",
    ),

    # -----------------------------------------------------------------------
    # KAPAN PIECES / WEIGHT / POINTS
    # MEASURED 2026-08-24 on kapan OQ26 - three defensible "how many pieces":
    #   tblPacket rows          839   (packets cut from the kapan)
    #   SUM(tblPacket.Pcs)      585   (the Pcs column, sparsely filled)
    #   tblFinalPacket rows     682   (finished stones)
    # and two weights: tblPacket.PolishedWt 335.446 vs tblFinalPacket.CurrentWt
    # 310.660. "Final point" is a real thing and lives in tblPacketPoint, whose
    # F-prefixed columns are the FINAL values (FMFGPoint, FMarkerPoint,
    # FScopePoint, FHLMPoint, FMKBPoint) - the unprefixed ones are pre-final.
    # -----------------------------------------------------------------------
    Rule(
        name="kapan_pieces_points",
        trigger=r"ketla piece|how many piece|final point|polish weight|"
                r"final polish|nikalyu|rough weight|top \d+ kapan",
        directive=(
            "KAPAN PIECES HAS THREE DEFENSIBLE ANSWERS - name the one you used: "
            "the COUNT of tblPacket rows, SUM(tblPacket.Pcs), and the count of "
            "tblFinalPacket rows. They do not agree. Prefer COUNT of tblPacket "
            "rows for 'how many packets/pieces are in the kapan' and say so. "
            "Weight likewise: tblPacket.PolishedWt is the plan/polish weight, "
            "tblFinalPacket.CurrentWt the finished weight. Run the query - "
            "never quote a figure from this rule as the answer."
        ),
        verified="OQ26: 839 packets / 585 Pcs / 682 finished; PolishedWt 335.446 vs CurrentWt 310.660",
    ),

    # -----------------------------------------------------------------------
    # 4C BREAKDOWNS - the fluorescence column is spelled DIFFERENTLY per table.
    # MEASURED 2026-08-24: tblPacket.Florecent (100% populated, 172,233) but
    # tblFinalPacket.Florocent (179,990). Same concept, two spellings, and
    # neither matches the English word - a query written from the dictionary
    # spelling ("Fluorescent") fails outright.
    # -----------------------------------------------------------------------
    Rule(
        name="four_c_breakdown",
        trigger=r"fluorescen|florecent|florocent|by colour|by color|"
                r"breakdown of packets|cut, polish|clarity",
        directive=(
            "4C COLUMN SPELLINGS ARE INCONSISTENT AND NON-STANDARD: it is "
            "Florecent on tblPacket and Florocent on tblFinalPacket - never "
            "'Fluorescent', which exists on neither and fails. Both are fully "
            "populated. 'NON' means no fluorescence, so exclude it when the user "
            "asks for FLUORESCENT stones. Roll fancy/special SHAPE variants into "
            "the base shape before grouping (OV + F.OV + S.OV), or oval "
            "under-reports by more than half."
        ),
        verified="tblPacket.Florecent 172,233/172,233; tblFinalPacket.Florocent 179,990/179,990",
    ),

    # -----------------------------------------------------------------------
    # "STAGE X DONE BUT STAGE Y PENDING" - POSITIONAL, NOT AN ABSENCE
    #
    # Reported live 2026-08-27. The same question, asked twice:
    #   "polished GIA pending for mfg-1 department of past month"      -> 201
    #   "polish planned is already done but gia certification is
    #    pending for MFG-1 department for july month"                  -> "2 kapan"
    # Two different numbers, in two different UNITS, for one question.
    #
    # THIS RULE USED TO TEACH A PLAIN ANTI-JOIN, AND THAT WAS WRONG.
    # It said: pending = has an X row, has no Y row. The shape came from the
    # client's own dbo.GetPLSSUM, so it looked unimpeachable:
    #
    #   RapVer='PLS' AND IsDamagePlan=0 AND IsApproved=1
    #   AND Packet_ID NOT IN (SELECT Packet_ID FROM tblPlanMaster
    #                         WHERE RapVer='GIA' AND IsDamagePlan=0
    #                           AND IsApproved=1)
    #
    # It over-counts. "No GIA row" also catches stones that HAVE moved on -
    # graded at HRD or IGI instead, or re-planned after grading. Measured on
    # the one question the client checked against their own screen, MFG - 1
    # July 2026, the anti-join gives 12 and the client counts 2. The 12 was
    # quoted to them.
    #
    # What they mean is POSITIONAL: the packet's LATEST approved, non-damage
    # plan row IS its X row - the stone is at X and has not moved. Measured
    # 2026-09-01, that gives 2 for MFG - 1 July 2026, matching them exactly.
    #
    # WHICH LAB a pending stone is waiting for is NOT derivable from the
    # missing stage row - there isn't one. It is tblPlanMaster.LAB, carried on
    # the PLS row itself (GIA / HRD / IGI / NONE). LAB='NONE' means the stone
    # is not going to a lab at all: 248 packets all-time that are pending
    # nothing. See reports.pending_lab_report, which is the recipe for this.
    # -----------------------------------------------------------------------
    Rule(
        name="stage_pending",
        trigger=r"\bpending\b|\bremain(ing|s)?\b|\bbaki\b|\bnot yet\b|"
                r"\byet to\b|\bawait(ing)?\b|\bstill to\b|\boutstanding\b",
        directive=(
            "PENDING IS POSITIONAL, NOT AN ABSENCE. 'X is done but Y is "
            "pending' means the packet's LATEST approved, non-damage plan row "
            "in tblPlanMaster IS its X-stage row - the stone is at X and has "
            "not moved on. Write that as ROW_NUMBER() OVER (PARTITION BY "
            "Packet_ID ORDER BY CreatDate DESC, ID DESC) = 1 with RapVer = "
            "'<X>', or as NOT EXISTS (a LATER approved row for the same "
            "packet). Do NOT write it as 'has X, has no Y' - that also counts "
            "stones which HAVE moved on, to a different lab or a re-plan, and "
            "it over-reported this exact question to this exact user. Both "
            "sides carry ISNULL(IsDamagePlan, 0) = 0 AND IsApproved = 1, as in "
            "their own dbo.GetPLSSUM. Stage codes are RapVer: RST -> CLV -> "
            "ADM -> MKB -> MFG (the maker) -> PLS (the in-house grade, what "
            "'polish planned/assorted' means) -> GIA/HRD/IGI (the lab). WHICH "
            "LAB a pending stone is waiting for is tblPlanMaster.LAB on the "
            "PLS row, NOT a stage row - and LAB = 'NONE' means it is not going "
            "to a lab at all, so exclude it. ANSWER IN PACKETS - "
            "COUNT(DISTINCT Packet_ID) - unless the user asked for kapans; "
            "reporting a kapan count for a packet question gave the same user "
            "two different numbers in two different units for one question. "
            "State the unit in the answer."
        ),
        require_all=(
            # A query with none of these cannot express "has no later row".
            # A status column (RunningProcess) is a legitimate alternative
            # reading, so it is accepted rather than rejected.
            # The latest-row IDIOMS are listed alongside the absence ones. The
            # directive now teaches the positional reading, and a model that
            # writes it as "p.ID = (SELECT MAX(ID) ...)" or "TOP 1 ... ORDER BY
            # CreatDate DESC, ID DESC" is CORRECT - rejecting it for not
            # spelling ROW_NUMBER would be the rule punishing a query for
            # obeying it.
            (r"ROW_NUMBER|NOT\s+EXISTS|NOT\s+IN|IS\s+NULL|RunningProcess"
             r"|MAX\s*\(\s*[A-Za-z_]*[.]?(?:ID|CreatDate)\s*\)"
             r"|TOP\s+1[\s\S]{0,300}?ORDER\s+BY[\s\S]{0,160}?DESC",
             "establish that the done-stage row is the packet's LATEST "
             "approved one - ROW_NUMBER() OVER (PARTITION BY Packet_ID ORDER "
             "BY CreatDate DESC, ID DESC) = 1, or NOT EXISTS (SELECT 1 FROM "
             "tblPlanMaster nx WHERE nx.Packet_ID = ... AND nx.IsApproved = 1 "
             "AND (nx.CreatDate > ... OR (nx.CreatDate = ... AND nx.ID > "
             "...))). Filtering the done-stage rows alone counts work that IS "
             "finished, which is the opposite of what was asked"),

            # THE ANTI-JOIN SATISFIES THE RULE ABOVE AND IS STILL WRONG.
            # "NOT EXISTS a GIA row" passes the first check, and it is exactly
            # the query that answered 12 where the client counts 2. So the
            # POSITIONAL evidence is required separately: something in the SQL
            # must establish "nothing came after", not merely "that stage is
            # absent".
            #
            # The column-vs-column shape is what distinguishes it. A plain date
            # filter - CreatDate >= '2026-07-01' - is not evidence of anything
            # positional, so the comparison only counts when the right-hand
            # side starts with a LETTER (another column) rather than a quote or
            # a digit, and >= is excluded by the lookahead.
            #
            # TRADE-OFF, taken deliberately: a question that genuinely means
            # "never reached that stage at all" is now also pushed to the
            # positional form. That reading differs from the client's by ~1% of
            # packets (1,051 vs 1,064 all-time) and it is NOT what they mean by
            # pending, so being strict costs a rare rephrase and buys back the
            # wrong number that actually reached them.
            (r"ROW_NUMBER"
             r"|RunningProcess"
             r"|CreatDate\s*>(?!=)\s*[A-Za-z_\[]"
             r"|[.]ID\s*>(?!=)\s*[A-Za-z_\[]"
             r"|MAX\s*\(\s*[A-Za-z_]*[.]?(?:ID|CreatDate)\s*\)"
             r"|TOP\s+1[\s\S]{0,300}?ORDER\s+BY[\s\S]{0,160}?DESC",
             "prove the stone has NOT MOVED ON, not merely that the later "
             "stage row is missing. 'Has PLS and has no GIA row' also counts "
             "stones graded at another lab or re-planned after grading - it "
             "answered 12 for a question the client counts as 2. Add the "
             "positional test: ROW_NUMBER() OVER (PARTITION BY Packet_ID ORDER "
             "BY CreatDate DESC, ID DESC) = 1, or NOT EXISTS (SELECT 1 FROM "
             "tblPlanMaster nx WHERE nx.Packet_ID = p.Packet_ID AND "
             "ISNULL(nx.IsDamagePlan,0) = 0 AND nx.IsApproved = 1 AND "
             "(nx.CreatDate > p.CreatDate OR (nx.CreatDate = p.CreatDate AND "
             "nx.ID > p.ID)))"),
        ),
        # ROW_NUMBER is accepted because the directive now TEACHES it; without
        # it here, a model that followed the directive exactly would be
        # rejected by the rule that told it what to write.
        verified="MFG - 1, July 2026, measured 2026-09-01: latest-approved-row "
                 "IS PLS = 2 packets, matching the client. The old anti-join "
                 "reading (has PLS, no GIA) gives 12 - the figure we quoted "
                 "them by mistake",
    ),

    # -----------------------------------------------------------------------
    # "FOR <DEPARTMENT>" - WHOSE DEPARTMENT, AND WHEN?
    #
    # Reported live 2026-08-27, in the QA26 question. tblPacket.DepartMentId is
    # where the packet is SITTING NOW; it is not who worked on it. Traced on
    # kapan QA26 packet 301, the one stone that answers that question:
    #
    #   tblPacket.DepartMentId ...... 16 = "Laser"     (where it is today)
    #   tblPlanMaster CLV row ....... CL205 JIGNESHBHAI KANAVYA, "Marker-2"
    #
    # So "for marker 2 department" is answered by the CLV/marker plan row, and a
    # query that filtered tblPacket.DepartMentId would have returned 0 for a
    # packet that IS a Marker-2 packet. Both columns are legitimate - they
    # answer different questions - so this steers rather than rejects.
    # -----------------------------------------------------------------------
    Rule(
        name="stage_department",
        trigger=r"\bdepartment\b|\bdept\b|\bmfg\s*-?\s*\d|\bmarker\s*-?\s*\d|"
                r"\bfency\b|\bvibhag\b",
        directive=(
            "'FOR <DEPARTMENT>' IS AMBIGUOUS AND THE TWO READINGS GIVE "
            "DIFFERENT ANSWERS. tblPacket.DepartMentId is where the packet is "
            "SITTING NOW, not who worked it. The department that DID the work "
            "is the department of the worker on the tblPlanMaster row: JOIN "
            "tblEmployee e ON e.ID = pm.EmpId, then e.DepartMentName. For work "
            "done ('made by', 'MFG-1 results') use the plan row - the LATEST "
            "per packet (TOP 1 ... ORDER BY ID DESC), because a re-issued "
            "packet has more than one. Use tblPacket.DepartMentId only for "
            "'where is it now' questions. Department names carry spaces and "
            "hyphens exactly as stored ('MFG - 1', 'Marker-2') - match them. "
            "NEVER PIN A RapVer THE USER DID NOT NAME: 'Marker-2' reads like "
            "the MKB stage but its work can sit on the CLV row, so filter on "
            "the department alone and the packet survives."
        ),
        verified="QA26 packet 301: tblPacket.DepartMentId = Laser (current), "
                 "CLV plan row worker CL205 = Marker-2 (who planned it); "
                 "live 2026-08-31 the location filter answered 0 vs a true 12",
    ),

    # -----------------------------------------------------------------------
    # SHAPE FAMILIES - THE BASE CODE IS NOT THE SHAPE
    # MEASURED 2026-08-31 on tblPacket (38 stored shapes, whole table):
    #   OV family 8,207 packets, plain 'OV' 3,265 ......... 40% of the family
    #   PS family 6,652 packets, plain 'PS' 6,585 ......... 99%
    #   MQ family 1,837 packets, plain 'MQ' 1,817 ......... 99%
    # The F./S./M forms are SEPARATE stored values, not sub-types of the base,
    # so a base-code equality silently answers for part of the family.
    #
    # Cold case COLD-08, "how many oval diamonds do we have in stock?": answered
    # 2,986 (Shape='OV') against a true 7,591 - a 61% under-count, and F.OV
    # alone (4,542) is BIGGER than plain OV. The glossary note that explains
    # this WAS routed into the prompt for that question and was ignored anyway,
    # which is precisely why it is enforced against the SQL instead of asked
    # for in prose. Only OV is catastrophic; PS and MQ are listed because a 1%
    # wrong number is still a wrong number.
    # -----------------------------------------------------------------------
    Rule(
        name="shape_family",
        trigger=r"\b(oval|pear|marquise|marquis)\b",
        directive=(
            "SHAPE ASKED BY NAME MEANS THE WHOLE FAMILY, not the base code. "
            "The F./S./M forms are separate stored values: "
            "oval = ('OV','F.OV','S.OV','OVM'), "
            "pear = ('PS','F.PS','S.PS','PSM'), "
            "marquise = ('MQ','S.MQ'). Shape='OV' returns under half the oval "
            "packets - F.OV alone is bigger than plain OV. Use Shape IN (...) "
            "listing every variant, and say which codes you rolled up."
        ),
        verified="tblPacket: OV family 8,207, plain OV 3,265 (40%); "
                 "oval in stock = 7,591 not 2,986",
    ),

    # -----------------------------------------------------------------------
    # DATE RANGES ARE END-EXCLUSIVE
    # Every date column here is smalldatetime (verified 2026-08-31 across
    # tblPlanMaster, tblFinalPacket, tblPacket, tblPlanReport, tblPacketHistory,
    # tblJunk), so a bare '2026-07-31' literal means 2026-07-31 00:00:00 and
    # BETWEEN drops every row timestamped later that day.
    #
    # MEASURED on tblPlanMaster for cold case COLD-01 ("last month ketla stone
    # lab ma send karya?"):
    #   CreatDate >= '2026-07-01' AND CreatDate < '2026-08-01' ..... 3,692
    #   CreatDate BETWEEN '2026-07-01' AND '2026-07-31' ............ 3,492
    # 200 packets - 5.4% - lost at the boundary, with nothing in the answer to
    # show it. reports.py already refuses an inclusive end on the TOOL path;
    # this closes the same hole on the SQL the model writes by hand.
    # -----------------------------------------------------------------------
    Rule(
        name="date_range_exclusive",
        trigger=r"\b(19|20)\d{2}\b|"
                r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|sep(t|tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b|"
                r"\b(month|year|quarter|week|today|yesterday|daily|monthly)\b|"
                r"\b(mahin[aoe]|varsh|aaje|aajkal|gai|chalu)\b",
        # DELIBERATELY TERSE. This rule fires on most dated questions, so every
        # character is paid on nearly every turn; the measured numbers and the
        # worked example live in the rejection message instead, where they cost
        # nothing until the model has actually got it wrong. Keeping the full
        # prose here pushed a lab question to 424 tokens of directives and
        # tripped test_a_rule_is_cheap_and_conditional.
        directive=(
            "DATE RANGES ARE END-EXCLUSIVE: use "
            "col >= 'START' AND col < 'NEXT_PERIOD_START'. Never BETWEEN with a "
            "date literal - these are smalldatetime columns, so it silently "
            "drops the last day."
        ),
        verified="tblPlanMaster GIA/HRD/IGI July 2026: exclusive 3,692 vs "
                 "BETWEEN-inclusive 3,492 - 200 packets lost",
    ),

    # -----------------------------------------------------------------------
    # "FINAL POINT" MEANS THE F-PREFIXED COLUMN
    # tblPacketPoint carries both a pre-final and a final value for every point
    # type, and only an F distinguishes them. MEASURED 2026-08-31 on kapan OQ26
    # (398 rows): FMFGPoint 6,107.39 against MFGPoint 5,965.98, FMarkerPoint
    # 6,183.70, FMKBPoint 5,290.93.
    #
    # kapan_pieces_points already SAYS this and is deliberately left advisory,
    # because "how many pieces" has three defensible answers and none of them is
    # wrong. "Final point" is not that: the unprefixed column is the pre-final
    # value, so reading it is not a different reading of the question, it is the
    # wrong number. Split into its own rule so the ambiguous half stays advisory
    # and only the unambiguous half is enforced.
    # -----------------------------------------------------------------------
    Rule(
        name="final_points",
        trigger=r"\bfinal\s*points?\b|\bfinal\s*pt\b",
        directive=(
            "'FINAL POINT' = the F-PREFIXED columns on tblPacketPoint "
            "(FMFGPoint, FMarkerPoint, FScopePoint, FHLMPoint, FMKBPoint). The "
            "unprefixed ones are pre-final and give a different number."
        ),
        verified="OQ26: FMFGPoint 6,107.39 vs MFGPoint 5,965.98",
    ),

    # -----------------------------------------------------------------------
    # A WEIGHT SUMMED THROUGH tblPacketPoint COVERS HALF THE KAPAN
    # tblPacketPoint is a POINTS table and carries no weight column of its own,
    # so any weight in a query that joins it comes from tblPacket - restricted
    # to the packets that happen to have a points row.
    #
    # MEASURED 2026-08-31 on kapan OQ26:
    #   packets in tblPacket ....................... 839
    #   distinct packets in tblPacketPoint ......... 398   (47%)
    #   SUM(CurrentWt) across the kapan ............ 378.458
    #   SUM(CurrentWt) through the points join ..... 197.661   <- 48% short
    #
    # Observed live on 2026-08-31: asked for OQ26's final point AND final polish
    # weight, the model wrote ONE query joining both and answered 6,107.39
    # points (right) with 197.66 carats (the join artefact). The points half was
    # correct, which is what makes this dangerous - the answer looks sourced.
    # -----------------------------------------------------------------------
    Rule(
        name="weight_via_points_join",
        trigger=r"\bweights?\b|\bwt\b|\bcarats?\b|\bvajan\b|\bnikalyu\b",
        directive=(
            "WEIGHT COMES FROM tblPacket, never through a tblPacketPoint join - "
            "that table holds under half the packets, so the sum silently drops "
            "the rest. Query points and weight as SEPARATE queries."
        ),
        verified="OQ26: 197.661 via the points join (398 rows) vs 378.458 "
                 "across all 839 packets",
    ),

    # -----------------------------------------------------------------------
    # ROLLUP MIXES GRANULARITIES AND EVERY TOTAL READ OFF IT IS INFLATED
    # GROUP BY ROLLUP(a, b, c) emits a subtotal row at each level. When b and c
    # are functionally dependent on a - e.ID, the employee's name, the
    # employee's department - those levels are the SAME number repeated, so the
    # result carries each employee's figure several times over and there is
    # nothing in the rows themselves to say which are detail and which are
    # subtotals.
    #
    # MEASURED 2026-08-31, from a live NVIDIA run of DRS-2:
    #   GROUP BY ROLLUP(e.ID, name, dept) ... 976 rows
    #   sum of every returned row .......... -43,309.04   <- what was answered
    #   its own grand-total row ............ -10,827.26
    #   the plain ungrouped truth .......... -11,536.82
    # The model reported -43,309.04: 3.75x the real figure, from a query whose
    # table, flag and date range were all correct.
    # -----------------------------------------------------------------------
    Rule(
        name="no_rollup_totals",
        trigger=r"\btotals?\b|\bsum\b|\bkul\b|\bketla\b|\bkitna\b|\bhow many\b|"
                r"\bbreakdown\b|\bwise\b|\breport\b|\bavg\b|\baverage\b",
        # TERSE BY NECESSITY: this fires on nearly every aggregate question,
        # so its length is paid on almost every turn. The measurements live in
        # the rejection message, which costs nothing until the model has
        # actually written a ROLLUP.
        directive=(
            "Never GROUP BY ROLLUP / CUBE / GROUPING SETS - the subtotal rows "
            "repeat figures and inflate any total. Use a plain GROUP BY."
        ),
        verified="DRS-2 ROLLUP: 976 rows summing to -43,309.04 against a true "
                 "-11,536.82",
    ),

    # -----------------------------------------------------------------------
    # AN EMPLOYEE NAME IS NOT AN IDENTITY
    # MEASURED 2026-08-31 on tblEmployee: NINE separate employee rows are called
    # "MAIYANI  VIJAYABHAI", and nine more "SUTARIYA NARESHKUMAR". A per-person
    # figure filtered or grouped on the name silently sums all nine into one
    # number and attributes it to a single worker.
    #
    # Cold case ADV-08 - "total bonus of employee MAIYANI VIJAYABHAI in June
    # 2026" - is graded on whether the bot ASKS WHICH PERSON rather than
    # answering. It cannot ask if it never sees that the name is ambiguous, and
    # it only sees that if the code is in the result, so the query is what has
    # to carry it.
    # -----------------------------------------------------------------------
    Rule(
        name="employee_identity",
        trigger=r"\b(of|for)\s+employee\b|\bemployee[\s-]?wise\b|"
                r"\bkarigar[\s-]?wise\b|\b(per|by|each)\s+employee\b|"
                r"\bkaya\s+karigar\b",
        directive=(
            "AN EMPLOYEE NAME IS NOT UNIQUE - fifteen rows match MAIYANI "
            "VIJAYABHAI (codes M2001, V001, Y001, G001, IGI001, HRD001, "
            "MFGAD003/5/7 ...) across MFG-2, Vision 360, Fency, GIA, IGI, HRD "
            "and Administrator. Carry tblEmployee.Code - the column is Code, "
            "NOT EmpCode - in any per-person figure, and never group or filter "
            "on the name alone. When the name matches more than one code, list "
            "the codes with their departments and ask which person is meant "
            "instead of summing them into one number."
        ),
        verified="tblEmployee: 15 rows match MAIYANI VIJAYABHAI across 11 "
                 "departments; SUTARIYA NARESHKUMAR = 9 exact duplicates",
    ),

    # -----------------------------------------------------------------------
    # tblKapanValue IS A DAILY SNAPSHOT, NOT A LEDGER
    # It re-writes every active kapan's figures once a day, so a kapan that ran
    # for two months appears sixty times carrying the same weight.
    # MEASURED 2026-08-31: 61,221 rows covering 1,050 kapans (~58 each).
    #   SUM(RoughWt) over tblKapanValue ...... 17,469,238.68
    #   SUM(Weight)  over tblKapan ...........    226,631.26
    # A 77x inflation, and the inflated figure reads perfectly plausibly as a
    # lifetime intake. The glossary says this in prose; the oval case settled
    # what prose is worth inside a 20k-token prompt.
    # -----------------------------------------------------------------------
    Rule(
        name="kapan_value_snapshot",
        trigger=r"\bkapan\b|\brough\b|\bintake\b|\bparcel\b",
        directive=(
            "tblKapanValue is a DAILY SNAPSHOT - the same kapan repeats once "
            "per active day (61,221 rows for 1,050 kapans). Never SUM it raw: "
            "kapan totals come from tblKapan."
        ),
        verified="tblKapanValue SUM(RoughWt) 17,469,238.68 vs tblKapan "
                 "SUM(Weight) 226,631.26 - 77x",
    ),

    # -----------------------------------------------------------------------
    # tblPctChecker COVERS HALF THE FINISHED PACKETS
    # It is the polisher/maker attribution register and it is INCOMPLETE.
    # MEASURED 2026-08-31 against tblFinalPacket:
    #   LEFT JOIN  ... 180,066 rows
    #   INNER JOIN ...  95,920 rows    <- 46.7% of the production disappears
    # An employee-production report built on the inner join looks complete and
    # under-states the factory by nearly half. Same failure as the damage
    # inner-join guarded above, on a much bigger table.
    # -----------------------------------------------------------------------
    Rule(
        name="pct_checker_join",
        # BARE "polish" WAS A FALSE FIRE. "final polish weight ketlu
        # nikalyu" asks for a WEIGHT, not for who polished anything, and
        # this directive rode along on every such question - 43 tokens on
        # a question it has nothing to say about, which is what pushed the
        # OQ26 question over the prompt ceiling. Attribution needs a
        # PERSON in the phrasing, so the bare participle is gone.
        trigger=r"\bpolisher\b|\bwho\s+(made|polished)\b|\bmaker\b|"
                r"\battribution\b|\bkarigar\b|"
                r"\b(employee|worker)[\s-]?wise\b",
        directive=(
            "tblPctChecker (who made / who polished) covers only about half of "
            "the finished packets - always LEFT JOIN to it, never an inner "
            "join, or half the production vanishes silently."
        ),
        verified="tblFinalPacket x tblPctChecker: LEFT 180,066 vs INNER 95,920",
    ),

    # -----------------------------------------------------------------------
    # THE RATE TABLES ARE PRICE LISTS, NOT PAYMENTS
    # tblLabourRate (3,379,566 rows), tblReportRate and tblBonusRate (1,535,720
    # each) are rate CARDS: one row per shape/colour/clarity/weight combination
    # saying what that combination pays. Nothing in them was paid to anybody.
    # MEASURED 2026-08-31:
    #   SUM(Amount) over tblLabourRate .......... 64,311,533.58
    #   SUM(FinalLabour) over tblPointRateLabour   3,884,709.83  <- actually paid
    # 16.6x, and denominated in rupees either way, so nothing about the wrong
    # figure looks wrong.
    # -----------------------------------------------------------------------
    Rule(
        name="rate_card_not_money",
        trigger=r"\brates?\b|\blabour\b|\blabor\b|\bwage\b|\bbonus\b|"
                r"\bincentive\b|\bpaid\b|\bpayment\b",
        # Trimmed for the same reason: "bonus" is in this trigger AND in
        # bonus_earnings', so both fire on every bonus question and together
        # they pushed that question's directives to 422 tokens, over the 400
        # budget test_a_rule_is_cheap_and_conditional sets.
        directive=(
            "tblLabourRate / tblReportRate / tblBonusRate are PRICE LISTS, not "
            "payments - never SUM them. Money paid is in tblPointRateLabour."
        ),
        verified="SUM(Amount) tblLabourRate 64,311,533.58 vs real "
                 "tblPointRateLabour 3,884,709.83 - 16.6x",
    ),

    # -----------------------------------------------------------------------
    # AN ANTI-JOIN POINTED THE WRONG WAY ALWAYS RETURNS (NEARLY) ZERO
    # stage_pending already demands NOT EXISTS, and gets it - but it never
    # checked WHICH WAY ROUND. Seen live 2026-08-31 on "polished GIA pending
    # for mfg-1 last month", answered 0:
    #     FROM tblPlanMaster p WHERE p.RapVer = 'GIA' ... AND NOT EXISTS (...)
    # "GIA pending" is a statement about the PLS row: it is the packet's latest
    # approved plan row, so the stone is still sitting at polish. Starting FROM
    # the GIA rows selects exactly the packets that are NOT pending, so the
    # answer is 0 by construction - and 0 reads as "all caught up", which is
    # the most reassuring possible way to be wrong.
    # The query must be anchored on RapVer='PLS' either way.
    # -----------------------------------------------------------------------
    Rule(
        name="lab_pending_direction",
        trigger=r"(gia|hrd|igi|lab)[^.]{0,24}pending|pending[^.]{0,24}(gia|hrd|igi|lab)",
        directive=(
            "'GIA PENDING' IS A STATEMENT ABOUT THE PLS ROW: select FROM "
            "RapVer='PLS' and require that it is the packet's LATEST approved "
            "plan row. Never select FROM RapVer='GIA' and exclude - those are "
            "the packets that are NOT pending, so it gives 0 every time. To "
            "narrow to one lab, filter tblPlanMaster.LAB on the PLS row; do "
            "not look for a lab stage row, because a pending packet has none."
        ),
        verified="live 2026-08-31: GIA-outer anti-join returned 0 for MFG-1 July",
    ),

    # -----------------------------------------------------------------------
    # ENFORCEMENT ONLY - stage_department already carries the explanation.
    #
    # That rule is ADVISORY on purpose: "packets for marker 2 department" is
    # genuinely ambiguous between "worked on by" and "sitting in", both columns
    # are legitimate, and rejecting either reading costs a correct answer.
    # This one fires ONLY where the question is unambiguously about work DONE -
    # pending / made / polished / produced / results / output - and there
    # tblPacket.DepartMentId cannot be right, because the stone has moved on.
    #
    # Live 2026-08-31: "polished GIA pending for mfg-1 department last month"
    # filtered on the CURRENT location and answered 0, where the ERP's own
    # definition gives 12.
    #
    # Its directive is EMPTY, so it costs nothing in the prompt - the guidance
    # is already in stage_department, which fires on the same questions.
    # directive() skips empty entries.
    # -----------------------------------------------------------------------
    Rule(
        name="department_did_the_work",
        trigger=r"\b(pending|made|planned|produced|polish(ed)?|output|results?)\b"
                r"[^?]{0,44}\bdepartment\b"
                r"|\bdepartment\b[^?]{0,44}"
                r"\b(pending|made|planned|produced|polish(ed)?|output|results?)\b",
        unless=r"where is|where are|lying|sitting|currently in|right now|"
               r"location|kya che|atyare kya",
        directive="",
        verified="live 2026-08-31: DepartMentId filter answered 0 for MFG-1 "
                 "GIA-pending where the maker-based answer is 12",
    ),    # -----------------------------------------------------------------------
    # A PLAN'S ATTRIBUTES LIVE ON THE PLAN ROW, NOT ON THE PACKET
    #
    # Reported live 2026-09-03. "from kapan QA26 give me packets that has
    # purity between FL to VVS2 and size range from 0.3 to 0.80 for marker 2
    # department" was answered with
    #     p.Purity IN ('FL','IF','VVS1','VVS2') AND p.CurrentWt BETWEEN 0.3 AND 0.80
    # read off tblPacket, and returned ONE packet (301) where the plans
    # Marker-2 actually created give FOUR.
    #
    # Packet 301's Marker-2 plan proposes PolishedWt 0.200 - OUTSIDE the band
    # that was asked for. It matched only because tblPacket.CurrentWt reads
    # 0.464, and in QA26 that is the ROUGH weight: tblPacket.PolishedWt is NULL
    # on every one of its 325 packets, because nothing in the kapan has been
    # cut yet. A rough weight was reported to the user as the stone's size.
    #
    # BOTH columns matter. Measured on that exact question 2026-09-03:
    #     packet purity + packet weight ..... 1   <- what shipped
    #     packet purity + plan weight ....... 7
    #     plan purity   + packet weight ..... 1
    #     plan purity   + plan weight ....... 4   <- correct
    # so correcting either column alone still reports a wrong number, which is
    # why both are forbidden rather than just the weight.
    #
    # The purity columns genuinely disagree: QA26 packets 220 and 232 read SI1
    # and VS1 on tblPacket where the Marker-2 plan for each says VVS2.
    #
    # tblPacket stays LEGITIMATE FOR IDENTITY - PacketNo - because
    # tblPlanMaster.PacketName is NULL on 96% of QA26's marking rows. That is
    # why this forbids the ATTRIBUTE PREDICATES and not the table itself.
    # -----------------------------------------------------------------------
    Rule(
        name="plan_attributes_from_the_plan_row",
        # NO BACKSLASHES IN THESE PATTERNS. A literal backslash in this
        # file has been eaten before now - the first draft of this rule
        # shipped with every [b] turned into a 0x08 BACKSPACE byte,
        # silently killing all six word boundaries. [0-9] and (?<![a-z])
        # say the same thing and cannot rot that way.
        #
        # THE FIRST DRAFT WAS FITTED TO THE QUESTION THAT REPORTED IT.
        # It fired on "marker <n>" and on the exact phrase "plan(s)
        # created/made" - so Marker-2/3/4 were covered and Blocking,
        # Sarin, Dilate, Galaxy and MFG-6 were not, though the trap is
        # identical for every one of them. Measured 2026-09-03: 12 of 18
        # department/kapan combinations let the wrong SQL through. The
        # shapes below are about the QUESTION ("planned by X", "for X
        # department", "who planned"), never about which department.
        trigger=r"marker[ ]*-?[ ]*[0-9]"
                r"|(?<![a-z])(?:plan|plans|planned|planning)[ ]+"
                r"(?:created|made|written|by)(?![a-z])"
                r"|(?<![a-z])who[ ]+planned(?![a-z])"
                r"|(?<![a-z])(?:for|by)[ ]+[A-Za-z][A-Za-z0-9 .-]{0,24}?"
                r"[ ]*department(?![a-z])",
        unless=r"current(ly)?|right now|atyare|in stock"
               r"|where is|lying|final[ ]+(point|polish)",
        directive=(
            "A PLAN'S ATTRIBUTES ARE ON THE PLAN ROW. When the question is "
            "about what a marker or planning department PLANNED, read purity, "
            "shape, colour and size from tblPlanMaster - Purity and "
            "PolishedWt on the plan row the worker authored - never from "
            "tblPacket. tblPacket.Purity is the stone's CURRENT grade and "
            "tblPacket.CurrentWt is its present weight, which on a kapan that "
            "has not been cut yet is the ROUGH weight, so the two readings "
            "return almost disjoint sets. Join tblPacket only for PacketNo, "
            "because tblPlanMaster.PacketName is frequently NULL. Attribute "
            "the plan to its AUTHOR (tblPlanMaster.EmpId -> tblEmployee, then "
            "DepartMentName) and do NOT filter that employee list on IsActive "
            "- a leaver's plan is still a plan they created. Do not guess a "
            "RapVer list either; the author's department already decides which "
            "stage rows are theirs."
        ),
        verified="QA26 / Marker-2 / FL-VVS2 / 0.30-0.80 measured 2026-09-03: "
                 "the plan columns give 4 packets, the tblPacket columns that "
                 "shipped give 1, and packet 301 matched only on a rough "
                 "weight while the plan it belongs to proposes 0.200",
    ),
]




# ---------------------------------------------------------------------------
# IS THIS GRADE COLUMN READ OFF tblPacket? - RESOLVED, NOT GUESSED
#
# The first version matched "[ (,][a-z][0-9]?[.]Purity": any alias of one
# letter plus an optional digit. That encodes an ASSUMPTION - short aliases
# mean tblPacket, longer ones mean tblPlanMaster - true of the queries we
# happened to look at and of nothing else. It MISSES "pkt.Purity" bound to
# tblPacket and FALSELY REJECTS "m.Purity" bound to tblPlanMaster.
#
# So read the binding out of the SQL. Whatever identifier follows tblPacket is
# tblPacket's alias, whatever it is called, and only that alias's grade
# PREDICATES are forbidden - selecting the column is fine, it is the WHERE
# clause that changes the answer.
# ---------------------------------------------------------------------------
_PACKET_ALIAS_RE = re.compile(
    r"tblPacket[ ]*(?:WITH[ ]*[(][^)]*[)])?[ ]*(?:AS[ ]+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# Words that can legally follow a table name and are NOT an alias.
_NOT_AN_ALIAS = frozenset({
    "on", "where", "join", "inner", "left", "right", "full", "cross", "outer",
    "group", "order", "having", "union", "with", "as", "and", "or", "select",
    "apply", "set", "values", "when", "then", "else", "end", "using",
})

_GRADE_COLS = "(?:Purity|Shape|Color|Colour|Cut|Polish|Symmetry)"
_GRADE_PREDICATE = "[ ]*(?:=|<>|!=|IN[ ]*[(]|LIKE|BETWEEN)"


def packet_alias_names(sql: str) -> set:
    """Every alias this query binds to tblPacket, plus the bare table name."""
    out = {"tblPacket"}
    for m in _PACKET_ALIAS_RE.finditer(sql or ""):
        alias = m.group(1)
        if alias.lower() not in _NOT_AN_ALIAS:
            out.add(alias)
    return out


def reads_grade_off_the_packet(sql: str) -> bool:
    """True if a grade column is FILTERED on a tblPacket-bound alias."""
    sql = sql or ""
    for alias in packet_alias_names(sql):
        if re.search(re.escape(alias) + "[.]" + _GRADE_COLS + _GRADE_PREDICATE,
                     sql, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# ENFORCEMENT FOR RULES THAT WERE ADVISORY ONLY
#
# A Rule with no require_all/forbid is a SUGGESTION. Verified end-to-end on
# 2026-08-26: the `damage` directive FIRED on "2025 ma damage na ketla paisa
# katya karigar pase thi?" and the answer still came back -14,816.33 where the
# register gives -11,536.82. Of the sixteen rules, the seven with enforcement
# produced correct answers in that run and two of the nine advisory ones
# produced wrong numbers. Firing is not enforcing.
#
# Applied here as a table rather than edited into sixteen Rule(...) literals, so
# the whole enforcement surface is reviewable in one place.
#
# EVERY PATTERN BELOW FORBIDS SOMETHING VERIFIED DEAD OR VERIFIED WRONG - never
# a merely-discouraged shape. A require_all that rejects a legitimate query
# costs a working answer, which is worse than the bug. The suite asserts zero
# rejections across all 40 scripts/cold_cases.py ground-truth SQLs.
#
# `[.]` is used instead of a backslash-escaped dot on purpose: a literal
# backslash in these patterns has already been eaten once in this file (the
# \b in the sales/loss triggers became a 0x08 BACKSPACE byte, silently killing
# both), so the patterns here avoid backslashes entirely.
# ---------------------------------------------------------------------------
_ENFORCEMENT: dict[str, dict] = {
    # ONLY WHAT IS ACTIVELY WRONG - NOT WHAT IS MERELY EMPTY.
    #
    # The first draft of this table also forbade tblPacketSell, tblJunk.Grede,
    # ChapkaLoss, IsMatchPair and tblTimeAttendance - every one of them verified
    # dead. Replaying the 40 cold-case ground-truth SQLs rejected SIX of them,
    # and reading those six showed the flaw: they are PROOF queries. The correct
    # answer to "junk grade-wise report" is "grade is not recorded", and the way
    # you establish that is
    #     SELECT COUNT(DISTINCT Grede) FROM tblJunk WHERE Grede IS NOT NULL
    # Forbidding the dead column forbids PROVING it is dead.
    #
    # So a forbid must only fire where the query would return a WRONG number,
    # never merely an empty one. An empty result is self-describing; a wrong one
    # is not.
    "stock_basis": {"forbid": (
        # A BARE IsOnHold ESCAPED BOTH PATTERNS BELOW.
        # They only match a table-qualified or p-aliased column, but the most
        # natural way to write the wrong query is
        #     SELECT COUNT(*) FROM tblPacket WHERE IsOnHold = 1
        # with no prefix at all, and that walked straight through - the exact
        # 6,000x error (2 against a true 11,967) this rule exists to stop.
        # Found 2026-08-31 while de-numbering the directive.
        # Keyed on the ABSENCE of tblKapan: the only correct reading of hold is
        # k.IsOnHold on the kapan, so an IsOnHold in a query that never mentions
        # tblKapan can only be tblPacket's dead flag.
        ("(?s)^(?!.*tblKapan)(?=.*IsOnHold)",
         "hold is KAPAN-level: tblPacket.IsOnHold is set on 2 rows in the whole "
         "table and is dead. Join the kapan - JOIN tblKapan k ON p.Kapan_ID = "
         "k.ID WHERE k.IsOnHold = 1 - and count the packets of held kapans"),
        ("tblPacket[.]IsOnHold|[ (,]p[.]IsOnHold",
         "tblPacket.IsOnHold is set on only 2 of 172,233 rows and is effectively "
         "dead - it returns 2 where the true answer is 11,967. Hold is "
         "KAPAN-level: JOIN tblKapan k ON p.Kapan_ID = k.ID WHERE k.IsOnHold = 1 "
         "(34 kapans / 11,967 packets)"),
    )},

    # A LOSS QUESTION MUST BE ANSWERED FROM A LOSS COLUMN.
    #
    # Cold test COLD-02, 2026-08-26: "June ma manufacturing ma ketlu value loss
    # thayu?" - the true answer is 1,382.894 carats (tblPacketHistory.WightLoss).
    # The model instead differenced two money columns and answered "manufacturing
    # ADDED value - Rs 108,394.66 higher", which is the wrong metric, the wrong
    # sign, and a currency symbol on a figure that is not money.
    #
    # kapan_loss fires on the question but only describes BoilLoss/ChapkaLoss at
    # KAPAN level, so nothing told the model where MANUFACTURING loss lives.
    # Enforced rather than explained: the rejection message carries the column
    # list, so it costs ZERO prompt tokens and only appears when the model has
    # already gone wrong.
    #
    # Every loss column in the schema contains "Loss" except tblKapan.DifferWeight,
    # hence the alternation. Note the misspelling: it is WightLoss (no 'e') on
    # tblPacketHistory, WeightLoss on tblPacket/tblFinalPacket.
    "kapan_loss": {"require_all": (
        ("Loss|DifferWeight",
         "a LOSS question must read a loss column, not a money or weight total. "
         "Manufacturing loss = tblPacketHistory.WightLoss (misspelled, no 'e') "
         "or tblPacket.WeightLoss; kapan loss = tblKapan.BoilLoss "
         "(ChapkaLoss is populated on 1 of 865 kapans, so it is not tracked); "
         "jangad loss = tblJangad.LossCarats. Never difference two value columns "
         "and call it loss, and never put a currency symbol on a carat figure"),
    )},

    # Not "empty" - the query ERRORS. There is no Fluorescent column on either
    # table, so this costs a whole round to an invalid-column failure.
    "four_c_breakdown": {"forbid": (
        ("Fluorescen",
         "there is no 'Fluorescent' column on either table and this query will "
         "FAIL with an invalid column error: it is spelled Florecent on "
         "tblPacket and Florocent on tblFinalPacket. Both are fully populated"),
    )},

    # THE BASE SHAPE CODE IS A MINORITY OF ITS OWN FAMILY.
    # Measured 2026-08-31: Shape='OV' is 3,265 of 8,207 oval packets, and F.OV
    # (4,542 in stock) is BIGGER than plain OV (2,986). Cold case COLD-08
    # answered 2,986 against a true 7,591 with the explaining note already in
    # its prompt - prose lost, so this rejects the query instead.
    # Only the base-code EQUALITY is forbidden: Shape IN ('OV','F.OV',...) and
    # LIKE '%OV%' both pass untouched, and a single-element IN is the same bug
    # spelled differently.
    "shape_family": {"forbid": (
        ("Shape[ ]*=[ ]*'(OV|PS|MQ)'",
         "a shape asked for by name means the whole family - use "
         "Shape IN ('OV','F.OV','S.OV','OVM') for oval, "
         "('PS','F.PS','S.PS','PSM') for pear, ('MQ','S.MQ') for marquise. "
         "Shape='OV' reports 3,265 of 8,207 oval packets because the F./S./M "
         "forms are separate stored values, and F.OV alone is bigger than OV"),
        ("Shape[ ]*IN[ ]*[(][ ]*'(OV|PS|MQ)'[ ]*[)]",
         "that IN list holds only the base code, which is the same under-count "
         "as an equality - list every variant of the family"),
    )},

    # BETWEEN ON A smalldatetime SILENTLY DROPS THE LAST DAY.
    # Verified 2026-08-31: every period column in play (CreatDate, CreateDate,
    # CreatedDate, ReciveTime, ApproveDate) is smalldatetime, so '2026-07-31'
    # means midnight and the 31st is lost. tblPlanMaster GIA/HRD/IGI July 2026:
    # 3,492 with BETWEEN against a true 3,692.
    # Scoped to a DATE LITERAL, so numeric ranges (weight BETWEEN 0.30 AND 0.80)
    # are untouched - that shape is load-bearing in empty_result.py.
    "date_range_exclusive": {"forbid": (
        ("BETWEEN[ ]*'[0-9]{4}-[0-9]{2}-[0-9]{2}",
         "use col >= 'START' AND col < 'NEXT_PERIOD_START' instead of BETWEEN: "
         "these are smalldatetime columns, so BETWEEN '2026-07-01' AND "
         "'2026-07-31' stops at midnight and silently drops the whole 31st "
         "(3,492 against a true 3,692). July 2026 is >= '2026-07-01' AND "
         "< '2026-08-01'"),
    )},

    # ONLY AN 'F' SEPARATES THE FINAL VALUE FROM THE PRE-FINAL ONE.
    # A lookbehind is what makes this expressible: MFGPoint is a substring of
    # FMFGPoint, so a plain alternation would reject the correct column too.
    # Measured on OQ26: FMFGPoint 6,107.39 vs MFGPoint 5,965.98.
    "final_points": {"forbid": (
        ("(?<!F)(MFGPoint|MarkerPoint|ScopePoint|HLMPoint|MKBPoint)",
         "'final point' means the F-prefixed column on tblPacketPoint - "
         "FMFGPoint, FMarkerPoint, FScopePoint, FHLMPoint, FMKBPoint. The "
         "unprefixed column is the PRE-final value and is a different number "
         "(OQ26: 5,965.98 against a final 6,107.39)"),
    )},

    # tblPacketPoint HAS NO WEIGHT COLUMN, so a weight in a query that names it
    # is necessarily restricted to the packets holding a points row - 398 of
    # OQ26's 839. Expressed as a conjunction of two lookaheads because
    # Rule.check applies each pattern independently.
    "weight_via_points_join": {"forbid": (
        ("(?s)(?=.*tblPacketPoint)(?=.*(?:CurrentWt|PolishedWt|RoughWt|EstWeight|MKBWt|ChildWt))",
         "do not sum a weight in a query that joins tblPacketPoint: it holds "
         "only the packets with a points row (398 of OQ26's 839), so the total "
         "silently covers 47% of the kapan - 197.661 against a true 378.458. "
         "Run the points query and the weight query separately, taking the "
         "weight from tblPacket joined to tblKapan"),
    )},

    # THE SUBTOTAL ROWS ARE INDISTINGUISHABLE FROM THE DETAIL ROWS.
    # GROUPING SETS is listed too: it is the general form ROLLUP and CUBE are
    # shorthand for, and carries exactly the same hazard.
    "no_rollup_totals": {"forbid": (
        ("(?:ROLLUP|CUBE|GROUPING[ ]+SETS)[ ]*[(]",
         "drop the ROLLUP/CUBE/GROUPING SETS and use a plain GROUP BY: the "
         "subtotal rows repeat each figure at several levels, so the result "
         "cannot be totalled (measured: 976 rows summing to -43,309.04 where "
         "the true total is -11,536.82). If you need the total as well, run a "
         "second query without the GROUP BY"),
    )},

    # AN INNER JOIN TO tblEmployee SILENTLY DROPS UNATTRIBUTED DAMAGE.
    # Measured 2026-08-31 for calendar 2025: INNER JOIN keeps 2,103 of the
    # 2,398 register rows and totals -10,827.26 against a true -11,536.82. The
    # 295 dropped rows are damage whose EmpID matches no employee row - real
    # money, silently excluded because the join was only there to show a name.
    # Scoped to the damage register because that is where it was measured; the
    # same trap exists wherever a dimension join is added purely for display.
    "damage": {"forbid": (
        ("(?<!LEFT )(?<!OUTER )JOIN[ ]+tblEmployee",
         "use LEFT JOIN tblEmployee, not an inner join: 295 of the 2,398 damage "
         "rows have an EmpID matching no employee, and an inner join drops them "
         "- totalling -10,827.26 instead of the true -11,536.82"),
    )},

    # A SNAPSHOT TABLE MUST BE DEDUPLICATED BEFORE IT IS SUMMED.
    # Allowed through when the query carries a windowed dedup (ROW_NUMBER over
    # a PARTITION), which is the documented way to take one row per kapan.
    "kapan_value_snapshot": {"forbid": (
        ("(?s)(?=.*tblKapanValue)(?=.*(?:SUM|AVG)[ ]*[(])(?!.*ROW_NUMBER)",
         "tblKapanValue re-writes every active kapan once a day, so summing it "
         "raw multiplies by the number of days each kapan ran - 17,469,238.68 "
         "against a true 226,631.26, a 77x inflation. Take kapan totals from "
         "tblKapan, or deduplicate first with ROW_NUMBER() OVER (PARTITION BY "
         "KapanId ORDER BY CreatedAt DESC) = 1"),
    )},

    # HALF THE PRODUCTION IS NOT IN THE ATTRIBUTION REGISTER.
    "pct_checker_join": {"forbid": (
        ("(?<!LEFT )(?<!OUTER )JOIN[ ]+tblPctChecker",
         "use LEFT JOIN tblPctChecker: it holds an attribution row for only "
         "about half the finished packets, so an inner join drops 46.7% of the "
         "production (95,920 rows against 180,066) while still looking like a "
         "complete report"),
    )},

    # SUMMING A PRICE LIST PRODUCES A PLAUSIBLE RUPEE FIGURE THAT MEANS NOTHING.
    "rate_card_not_money": {"forbid": (
        ("(?s)(?=.*(?:tblLabourRate|tblReportRate|tblBonusRate))(?=.*(?:SUM|AVG)[ ]*[(])",
         "tblLabourRate/tblReportRate/tblBonusRate are rate CARDS - one row per "
         "shape-colour-clarity-weight combination, not a payment. Summing "
         "tblLabourRate gives 64,311,533.58 where the money actually paid is "
         "3,884,709.83 in tblPointRateLabour. Use tblPointRateLabour for money, "
         "and these tables only to look up a single rate"),
    )},

    # THE LAB STAGE MUST NOT BE THE OUTER FILTER OF A PENDING QUERY.
    # (?s) so the gap may span newlines; the bounded .{0,600} keeps it to the
    # same statement rather than matching a lab stage pages away.
    "lab_pending_direction": {"forbid": (
        ("(?s)RapVer[ ]*=[ ]*'(GIA|HRD|IGI)'.{0,600}?NOT[ ]+EXISTS",
         "that anti-join is inverted: it selects FROM the GIA rows and then "
         "excludes, which returns 0 by construction. A pending packet is one "
         "whose LATEST approved plan row is its PLS row - anchor the query on "
         "RapVer='PLS' with ISNULL(IsDamagePlan,0)=0 AND IsApproved=1, and "
         "require that no LATER approved row exists for that packet. To narrow "
         "to one lab use tblPlanMaster.LAB on the PLS row, not a stage row"),
    )},

    # THE CURRENT-LOCATION COLUMN CANNOT ANSWER "WHO DID THE WORK".
    "department_did_the_work": {"forbid": (
        ("tblPacket[.]DepartMentId|[ (,][a-z][0-9]?[.]DepartMentId",
         "tblPacket.DepartMentId is where the packet is SITTING NOW, so it "
         "returns nothing for work finished earlier - it answered 0 where the "
         "true figure is 12. The department that DID the work is the "
         "department of the worker on that stage's tblPlanMaster row: JOIN "
         "tblEmployee e ON e.ID = pm.EmpId, then e.DepartMentName"),
    )},

    # A PLAN'S ATTRIBUTES ARE NOT THE PACKET'S ATTRIBUTES.
    # Both columns are forbidden because correcting either one alone still
    # returns a wrong number: 1 / 7 / 1 / 4 for the four combinations, where 4
    # is right. See the rule's comment for the measurement.
    "plan_attributes_from_the_plan_row": {"forbid": (
        ("CurrentWt",
         "size on a PLAN question is the yield the marker proposed - "
         "tblPlanMaster.PolishedWt on the plan row they authored. "
         "tblPacket.CurrentWt is the packet's present weight, and on a kapan "
         "that has not been cut it is the ROUGH weight (tblPacket.PolishedWt "
         "is NULL on every packet of QA26), so it admitted a stone whose plan "
         "proposes 0.200 into a 0.30-0.80 band and dropped four that belong"),
        (reads_grade_off_the_packet,
         "purity, shape and colour on a PLAN question come from the plan row "
         "(tblPlanMaster.Purity), not tblPacket - the packet column is the "
         "stone's CURRENT grade and the two disagree: QA26 packets 220 and "
         "232 read SI1 and VS1 on tblPacket where the Marker-2 plan for each "
         "says VVS2. Read attributes off pm.*, and join tblPacket only for "
         "PacketNo"),
    )},

    # A PER-PERSON FIGURE WITHOUT A CODE MERGES THE DUPLICATES.
    # Nine employees share the name MAIYANI VIJAYABHAI. Expressed as one
    # pattern because Rule.check applies each regex independently and this is a
    # CONJUNCTION - reads a name column AND carries no identity column. The
    # (?s) makes the lookarounds span a multi-line query; without it a newline
    # between the SELECT and the name would hide the match.
    "employee_identity": {"forbid": (
        ("(?s)^(?!.*(?<![A-Za-z])Code(?![A-Za-z]))(?=.*(?:FirstName|LastName|EmpName))",
         "carry tblEmployee.Code (the column is Code, NOT EmpCode) in a "
         "per-person figure: fifteen rows match the name MAIYANI VIJAYABHAI "
         "and nine share SUTARIYA NARESHKUMAR exactly, so grouping or "
         "filtering on the name alone sums several people into one number and "
         "reports it as a single worker's"),
    )},
}

for _rule in RULES:
    _extra = _ENFORCEMENT.get(_rule.name)
    if _extra:
        _rule.require_all = tuple(_rule.require_all) + tuple(_extra.get("require_all", ()))
        _rule.forbid = tuple(_rule.forbid) + tuple(_extra.get("forbid", ()))

# NOT ENFORCED, AND DELIBERATELY SO.
#
#   production_basis      "name the basis you used"
#   kapan_pieces_points   "name which of the three counts you used"
#
# Both ask the answer to DISCLOSE which of several legitimate definitions it
# chose. Every one of those definitions is a valid query, so there is no wrong
# SQL to reject - the requirement is about the prose, not the source. Forcing a
# single table here would reject correct work. They stay advisory until there is
# a deterministic post-hoc check on the ANSWER, the way scope_line works.


def directive(question: str) -> str:
    """The mandatory source block for this question - empty when no rule fires."""
    # An ENFORCEMENT-ONLY rule carries no directive (see
    # department_did_the_work) - skip it rather than emit a bare "- ".
    hits = [r.directive for r in RULES if r.applies(question) and r.directive]
    if not hits:
        return ""
    return "MANDATORY QUERY RULES FOR THIS QUESTION:\n" + "\n".join(
        f"- {d}" for d in hits
    ) + "\n\n"


# A SCHEMA PROBE IS NOT AN ANSWER, SO NO SOURCE RULE APPLIES TO IT.
#
# Establishing that something is NOT tracked is a legitimate - often the only
# correct - way to answer. "Kapan nu yield batavo" is answered by showing there
# is no yield or recovery column anywhere in the database, and the query that
# proves it reads INFORMATION_SCHEMA, not a business table. A require_all that
# demands a loss column then rejects the very query that answers the question.
#
# Caught by replaying the cold-case ground truths after adding the kapan_loss
# rule (CT-08, 2026-08-26). Unlike a proof query against a dead business column,
# this one IS syntactically identifiable, so it can be exempted precisely: a
# metadata query cannot produce a wrong business number, only a true statement
# about what exists.
_METADATA_QUERY_RE = re.compile(
    r"\bINFORMATION_SCHEMA\b|\bsys[.](?:tables|columns|objects|indexes|types)\b",
    re.IGNORECASE,
)


def is_metadata_query(sql: str) -> bool:
    """True for a schema probe - a query about the database, not the business."""
    return bool(_METADATA_QUERY_RE.search(sql or ""))


# A "WHEN DID THIS SOURCE LAST GET DATA" PROBE IS NOT AN ANSWER EITHER.
#
# is_metadata_query above exempts a query ABOUT the database. This is the other
# half of the same argument: a query that establishes a source is DEAD by
# reading the newest row in it. Cold case EDA-1 is exactly that - the ground
# truth for "aaje factory ma total ketla mansu chhe?" is
#     SELECT MAX(Date) AS LastHeadcountDate FROM tblEmployeeCount
# and its answer, 2021-07-23, IS the finding: the counter stopped five years
# ago. The headcount rule forbids tblEmployeeCount - correctly, it reports 420
# where 369 is true - and so it also forbade the query that PROVES it is dead,
# the same flaw the _ENFORCEMENT notes describe for tblJunk.Grede.
#
# NARROWED TO MAX/MIN DELIBERATELY. Exempting COUNT as well would re-open
#     SELECT COUNT(*) FROM tblRepairLogNew      -> 150,706 against a true 3,302
# which is the exact wrong number the repairs rule exists to stop. A lone
# MAX/MIN of a column cannot be mistaken for a business total; a COUNT can be,
# and that one already has been. A single output column with no JOIN and no
# GROUP BY leaves nothing for the figure to be broken down BY, so there is no
# shape in which it can answer a real business question.
_LIVENESS_SPLIT_RE = re.compile(r"\s*SELECT\s+(.*?)\s+FROM\b",
                                re.IGNORECASE | re.DOTALL)
_LIVENESS_AGG_RE = re.compile(r"\s*(?:MAX|MIN)\s*\(", re.IGNORECASE)
_LIVENESS_DISQUALIFY_RE = re.compile(r"\bJOIN\b|\bGROUP\s+BY\b|\bUNION\b",
                                     re.IGNORECASE)


def is_liveness_probe(sql: str) -> bool:
    """True for a 'when did this source last receive data' probe.

    One MAX/MIN, one table, no grouping. A comma anywhere in the select list
    disqualifies it, so this fails CLOSED - a probe written with a nested
    ISNULL(x, y) stays rejected rather than widening the exemption.
    """
    s = (sql or "").strip()
    if _LIVENESS_DISQUALIFY_RE.search(s):
        return False
    m = _LIVENESS_SPLIT_RE.match(s)
    if not m:
        return False
    select_list = m.group(1)
    if "," in select_list:
        return False
    return bool(_LIVENESS_AGG_RE.match(select_list))


def violations(question: str, sql: str) -> list[str]:
    """Everything wrong with `sql` for `question`, as fixes the model can apply."""
    if not sql or is_metadata_query(sql) or is_liveness_probe(sql):
        return []
    # A CURATED VIEW IS THE ENFORCEMENT, so the rule it replaces must stand
    # aside - otherwise the correct query gets rejected. See views.SUBSUMES.
    from app.schema import views as _views

    skip = _views.subsumed_rules(sql)
    out = []
    for rule in RULES:
        if rule.name in skip:
            continue
        if rule.applies(question):
            out.extend(rule.check(sql))
    return out


def rejection(problems: list[str]) -> str:
    """The tool result a violating query gets INSTEAD of data."""
    return (
        "ERROR: that query does not match how this business defines the figure, "
        "so it was not run. Re-run ONE corrected query that: "
        + "; ".join(problems)
        + ". Then answer from that result."
    )
