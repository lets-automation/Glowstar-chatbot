"""
glossary.py
-----------
Business glossary for the Aastha diamond-manufacturing ERP.

WHY THIS EXISTS:
The AI agent reads table/column names, but those don't explain the
*business meaning*. This glossary teaches the agent diamond-industry
terms (Packet, Jangad, Point, etc.) and what each key table holds, so
it can turn a plain question into the correct SQL.

STATUS OF DEFINITIONS:
- "confirmed": grounded in industry research (safe to rely on).
- "verify":    inferred from table names - CONFIRM the column-level
               details with the client, then change to "confirmed".

These are easy to edit - just update the text as the client confirms.
"""

# ---------------------------------------------------------------------------
# 1. INDUSTRY TERMS  (term -> {definition, status})
#    Grounded in diamond-manufacturing research.
# ---------------------------------------------------------------------------
TERMS = {
    "Carat": {
        "definition": "Diamond weight unit. 1 carat = 200 milligrams.",
        "status": "confirmed",
    },
    "Point": {
        "definition": (
            "Fine weight unit. 1 carat = 100 points. A 0.25ct stone is a "
            "'25-pointer'. Labour is often paid per point of weight processed."
        ),
        "status": "confirmed",
    },
    "Kapan": {
        "definition": (
            "A lot/parcel of ROUGH diamonds bought and processed together as "
            "one batch. Most records are tagged with a Kapan_ID/KapanName. "
            "A Kapan is split into individual Packets for processing."
        ),
        "status": "confirmed",
    },
    "Lot": {
        "definition": (
            "In this business a 'lot' means a KAPAN (a parcel of rough "
            "diamonds). So 'how many lots' = how many kapans (count distinct "
            "Kapan_ID / use tblKapan). It does NOT mean junk LotNo."
        ),
        "status": "confirmed",
    },
    "Packet": {
        "definition": (
            "A parcel/lot of diamonds tracked as a single unit as it moves "
            "through the factory (planning -> cutting -> polishing -> final). "
            "Packets belong to a Kapan."
        ),
        "status": "confirmed",
    },
    "SubPcs": {
        "definition": "Sub-pieces - a packet split into smaller pieces.",
        "status": "verify",
    },
    "Tantion / Tansion": {
        "definition": (
            "Tension grade of the stone (a quality/clarity attribute used in "
            "rate calculations). Spelled both 'Tantion' and 'Tansion' in the DB."
        ),
        "status": "verify",
    },
    "Jangad": {
        "definition": (
            "An entrustment note - diamonds sent out on approval / "
            "sale-or-return basis, on trust. Tracks goods given out but not "
            "yet sold or returned (common in the Indian diamond trade)."
        ),
        "status": "confirmed",
    },
    "Plan / Planning": {
        "definition": (
            "Mapping how a rough stone will be cut to maximise value. The "
            "first manufacturing stage."
        ),
        "status": "confirmed",
    },
    "Labour Rate": {
        "definition": (
            "Piece-rate paid to a worker for processing a diamond, usually "
            "per point of weight or per process stage."
        ),
        "status": "confirmed",
    },
    "Point Rate Labour": {
        "definition": "The labour rate paid specifically per point of weight.",
        "status": "confirmed",
    },
    "Labour Result": {
        "definition": (
            "The output of a worker's processing - pieces completed and "
            "resulting yield."
        ),
        "status": "verify",
    },
    "Incentive": {
        "definition": "Extra pay earned for meeting yield/quality/output targets.",
        "status": "confirmed",
    },
    "Bonus": {
        "definition": "Additional reward pay, often rate-based.",
        "status": "confirmed",
    },
    "Repair": {
        "definition": (
            "Re-polishing or fixing a stone that did not pass quality. WARNING: "
            "the tables tblRepairLog / tblRepairLogNew are NOT this — they are "
            "database change/audit logs (row Insert/Update/Delete on the plan "
            "tables). Actual stone re-check/repair remarks live in "
            "tblRepairCommentVision. See the data notes."
        ),
        "status": "confirmed",
    },
    "Junk": {
        "definition": "Rejected or scrap diamond material.",
        "status": "verify",
    },
    "Time Attendance": {
        "definition": "Worker attendance records (in/out, present days).",
        "status": "confirmed",
    },
    "Report Rate": {
        "definition": "Rates used for reporting / valuation purposes.",
        "status": "verify",
    },
    "Fluorescence": {
        "definition": (
            "How much a diamond glows under UV. STORED IN A MISSPELLED COLUMN: "
            "'Florecent' (tblPacket, tblPacketHistory, tblPlanMaster, etc.) or "
            "'Florocent' (tblFinalPacket, tblLabourResult, rate tables). There "
            "is NO column spelled 'Fluorescent'."
        ),
        "status": "confirmed",
    },
    # --- Industry terms added from GLOWSTAR_KNOWLEDGE.md (§2.3 pipeline, §4 trade) ---
    "Ghanti": {
        "definition": (
            "The polishing wheel (Gujarati; Western term 'scaife') - a diamond-"
            "paste-charged wheel where karigars polish facets. Represents the "
            "polishing stage / its piece-rated labour tasks, not a data value."
        ),
        "status": "confirmed",
    },
    "Taliya / Talia": {
        "definition": (
            "Polishing the pavilion (bottom) facets of a stone - one of the "
            "distinct piece-rated Surat polishing tasks (alongside table, girdle, "
            "athpel, mathala)."
        ),
        "status": "confirmed",
    },
    "Mathala": {
        "definition": (
            "Polishing the upper crown facets (~24) - a piece-rated polishing "
            "task (mathu = head/top)."
        ),
        "status": "confirmed",
    },
    "Athpel": {
        "definition": (
            "Polishing the 8 main crown facets (ath = 8, pel = facet) - a piece-"
            "rated polishing task."
        ),
        "status": "confirmed",
    },
    "Cent / Nang": {
        "definition": (
            "'Cent' = 1/100 carat = a point (small goods are counted in cents; "
            "'5 cent' = 0.05 ct). 'Nang' = a piece/stone, the counting word for "
            "diamonds ('ketla nang' = how many stones = COUNT)."
        ),
        "status": "confirmed",
    },
    "Dalal / Dalali": {
        "definition": (
            "A dalal is a broker/middleman in the diamond trade; dalali is the "
            "brokerage commission (conventionally ~1% in polished goods - confirm "
            "the exact rate with the client)."
        ),
        "status": "confirmed",
    },
    "Angadia": {
        "definition": (
            "A trusted-courier network that physically carries diamond parcels and "
            "cash between Surat and Mumbai (to/from the export offices). Legal in "
            "India; a diamond-trade institution, not a data value."
        ),
        "status": "confirmed",
    },
    "Rapaport / Back": {
        "definition": (
            "The Rapaport ('Rap') Price List is the trade's weekly reference for "
            "high cash-asking prices of polished diamonds. Dealers quote a discount "
            "as '% back' ('20 back' = 20% below Rap). Cut/polish/symmetry and "
            "fluorescence are NOT in the Rap grid."
        ),
        "status": "confirmed",
    },
    "SI3": {
        "definition": (
            "A Rapaport/trade clarity grade between SI2 and I1. GIA/IGI/HRD do NOT "
            "issue SI3, but dealers (and GlowStar's stated range) use and price it."
        ),
        "status": "confirmed",
    },
    "4P / Final checking": {
        "definition": (
            "The final quality check of a stone's 'make' - Proportion, Polish, "
            "Symmetry (and overall finish) - plus a clarity/color re-check before "
            "it leaves. Corresponds to ERP checking stages (Vision 360, Polish "
            "Checker)."
        ),
        "status": "confirmed",
    },
}


# ---------------------------------------------------------------------------
# VALUE CODES - what the short coded column values mean (grounded in the real
# data). Included in EVERY question's context: small but high-impact accuracy.
# ---------------------------------------------------------------------------
VALUE_CODES = {
    "Shape (column 'Shape')":
        "RD=Round, EM=Emerald, HR=Heart, PS=Pear, OV=Oval, PR=Princess, "
        "MQ=Marquise, CU=Cushion, RAD=Radiant, BG=Baguette, TRI=Trillion, "
        "SQEM=Square Emerald; 'F.xx' = Fancy and 'S.xx' = special variants. "
        "Always filter with the CODE, not the English word. This list covers the "
        "common shapes but is NOT exhaustive - the data also has rarer codes "
        "(e.g. CB, CL, DM, KIT, HEX, RS, HL) whose exact meaning isn't confirmed; "
        "for an unusual shape, first SELECT DISTINCT Shape to see the real codes "
        "rather than assuming one, and flag it if unsure.",
    "Color (column 'Color')":
        "Diamond colour grade: D, E, F, G, H, I, J, K, L, M, N "
        "(D = colourless/best, N = most tinted).",
    "Clarity (stored in the 'Purity' column!)":
        "The clarity grade is in a column NAMED 'Purity'. Values best->worst: "
        "FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1, I2, I3.",
    "Cut / Polish / Symmetry":
        "EX=Excellent, VG=Very Good, GD=Good, FR=Fair.",
    "Fluorescence (column 'Florecent' or 'Florocent')":
        "NON=None, FNT=Faint, MED=Medium, STG=Strong, VST=Very Strong. "
        "A 'fluorescent stone' = value is NOT 'NON'. No column is spelled "
        "'Fluorescent'.",
    "Process / current stage (tblPacket column 'RunningProcess')":
        "Where a packet currently sits. Values include IN Stock, OUT Stock, Check "
        "Stock, Rough Estimation, Weight Scale, Marker, Laser, Galaxy, Blocking, "
        "Vision 360, Polish Checker, MFG-1..6, 4P. This is THE column for 'diamond "
        "stock / where are the stones now' (RunningProcess = 'IN Stock' etc.) - do "
        "NOT use the tblStock* tables for diamonds (those are consumables).",
}

# General data-quality advice (misspellings, misleading names).
DATA_NOTES = [
    "Some columns are misspelled (e.g. fluorescence is 'Florecent'/'Florocent'). "
    "If an expected column name isn't found, call get_table_columns to find the "
    "real/misspelled variant before concluding the data is missing.",
    "Column names can be misleading: the 'Purity' column actually holds the "
    "CLARITY grade.",
    "When filtering a coded column, use the CODES below (e.g. Color='D', "
    "Florecent<>'NON'), not the full English word.",
    "COUNT DISTINCT, not COUNT(*): transactional/history tables have MANY rows "
    "per entity, so COUNT(*) OVER-COUNTS. To count PACKETS use COUNT(DISTINCT "
    "Packet_ID) (note the underscore); to count EMPLOYEES use COUNT(DISTINCT the "
    "numeric emp id); to count KAPANS use COUNT(DISTINCT Kapan_ID/KapanName). "
    "Examples of the inflation: tblIncentiveAmount has ~310 rows per employee "
    "(COUNT(DISTINCT EmpID)=1,946, not 604,055 rows); tblLabourResult ~6 rows per "
    "packet; tblPacketHistory & tblPlanMaster have millions of rows, many per "
    "packet. The one-row-per-item master is tblPacket (packets) / tblKapan "
    "(kapans) - count those directly; count history/labour tables with DISTINCT.",
    "DATE COLUMNS differ per table and are inconsistently named/misspelled - use "
    "the RIGHT one for 'today/this month/last year' filters: tblPacket->CreDate; "
    "tblFinalPacket->CreateDate; tblLabourResult->ProcessDate; tblPlanReport->"
    "CreatedDate; tblPlanMaster->CreatDate; tblIncentiveAmount->TransactTime; "
    "tblTimeAttendance->Time; tblPacketHistory->ReciveTime; tblJunk->IssueDate. "
    "If unsure, call get_table_columns first - do NOT assume a 'CreatedDate'.",
    "KNOWN-EMPTY TABLES (verified 0 rows): tblPacketSell, tblUserMaster, "
    "tblStockInventory, tblGradingMaster, tblInclusionInventory, tblRejection. "
    "If a question maps to one of these, the data is NOT recorded in this system - "
    "say so plainly. Do NOT silently substitute a different table's numbers, and "
    "NEVER invent rows.",
    "SALES / SOLD / REVENUE are NOT tracked: the only sales table (tblPacketSell) "
    "is empty. If asked how many diamonds/packets were 'sold' or about sales/"
    "revenue, state that sales are not recorded here. CRITICAL: a jangad return "
    "(tblJangadPackets.IsReceived = 1) is goods coming BACK from a sub-contractor, "
    "NOT a sale - never report returned-jangad counts as 'sold'.",
    "KAPAN COUNT: count kapans from the kapan master table tblKapan (847 rows = "
    "one row per kapan). Do NOT use COUNT(DISTINCT Kapan_ID) on tblPacket (that "
    "misses kapans with no packets), and avoid the decoys tblKapan_BKP (backup) "
    "and tblKapanValue (valuation rows, not kapans).",
    "TENSION / TANSION GRADE: the authoritative tension grade is column 'Tantion' "
    "on tblPacketCode (note that spelling). To count packets by tension grade use "
    "tblPacketCode WHERE Tantion = N. (tblPacket also has a 'Tension' column, but "
    "tblPacketCode.Tantion is the canonical packet-code grade - be consistent.)",
    "PACKET IDENTITY (PacketNo is NOT unique - avoids a merge bug): a packet is "
    "identified by the NUMERIC key tblPacket.ID (referenced elsewhere as Packet_ID/"
    "PacketID). PacketNo is only a WITHIN-KAPAN display number that repeats across "
    "kapans (there are 164,573 packets but only 2,330 distinct PacketNo values - "
    "PacketNo=1 exists in 842 different kapans). So NEVER GROUP BY, COUNT(DISTINCT "
    "...), or JOIN on PacketNo alone - that merges hundreds of different packets and "
    "gives wrong numbers. To COUNT packets use COUNT(DISTINCT Packet_ID/tblPacket.ID); "
    "to pin down one packet use its numeric id, or the pair (KapanName + PacketNo). "
    "PacketNo is fine ONLY as a display value alongside its KapanName.",
    "DIAMOND STOCK vs CONSUMABLES STOCK - two different 'stock' meanings: "
    "(a) DIAMOND stock / where stones are in the factory = tblPacket.RunningProcess "
    "(values include 'IN Stock', 'OUT Stock', 'Check Stock', and process stages like "
    "Laser, Galaxy, Blocking, MFG-2, Polish Checker, 4P). For 'how much is in stock / "
    "kaycho maal stock ma che', filter tblPacket by RunningProcess and count packets / "
    "SUM weight. (tblPacket.IsInTempStock is dead - 100% false - ignore it.) "
    "(b) The tblStock* tables (tblStockItem/StockDetail/StockCategory/StockIssue/"
    "StockPurchage/StockUnit/StockTally/StockGodown) are a CONSUMABLES / STORES "
    "inventory - pens, ink, MFG machine tools & liquids, cleaning & kitchen supplies - "
    "NOT diamonds. Only use tblStock* if the user explicitly asks about supplies/"
    "stationery/consumables. tblStockInventory is EMPTY.",
    "REPAIR is NOT in tblRepairLog / tblRepairLogNew - those are database "
    "change/audit logs (row Insert/Update/Delete on plan tables; tblRepairLog is "
    "dead since Feb 2022), NOT stone re-polishing. If asked 'how many stones were "
    "repaired', do NOT count rows in those. The real stone re-check/repair data is "
    "tblRepairCommentVision (RepairComment = the reason, one row per flagged stone). "
    "tblRepairing and tblRepairLoss are empty.",
    "REJECTION / SCRAP / JUNK: tblRejection is EMPTY (QC rejections aren't captured). "
    "Scrap/junk/bhangar material IS tracked in tblJunk - but only its Weight, Pcs, "
    "Packet_ID, Kapan_ID and CreateDate are usable (Value is 95% NULL, Grede is 100% "
    "NULL, IsRecyleble is always 1). For scrap questions use SUM(Weight) and "
    "COUNT(DISTINCT Packet_ID) by kapan/date; never report a junk 'value' or 'grade'. "
    "tblRejRules is just 4 rule-name definitions, not transactional data.",
    "RATE CARDS are CONFIG, not money paid — never SUM them for a total. "
    "tblLabourRate (3.4M rows), tblReportRate and tblBonusRate (1.5M each) are "
    "rate-CARD lookup tables: each row is a rate for a (weight-range FromWt..ToWt + "
    "Shape + Color + Clarity + Cut + Florocent + Tantion) combination keyed by "
    "CriteriaID. SUM(Amount) over them is meaningless (tblLabourRate sums to ~64M "
    "of rate cells, not rupees paid). For 'total labour / bonus PAID or EARNED' use "
    "the transactional FinalLabour / BonusAmount in tblPointRateLabour (see the "
    "BONUS/LABOUR/EARNINGS hint), NOT these rate cards. Also note tblReportRate and "
    "tblBonusRate store Shape as a COMMA-SEPARATED LIST (e.g. 'RD,PR,PS,MQ,EM'), so "
    "match with LIKE '%RD%', not Shape = 'RD'. These tables are only for a literal "
    "'what is the rate for a stone of spec X' lookup, which users rarely ask.",
    "SALARY / PAYROLL — the ERP has NO payroll data. There is NO basic salary, NO "
    "overtime, and NO deductions anywhere; this is a PIECE-RATE production system. So "
    "'salary / wages / pay' = piece-rate labour EARNED = SUM(tblPointRateLabour."
    "FinalLabour) (see the BONUS/LABOUR/EARNINGS note); 'bonus' = SUM(BonusAmount); "
    "'incentive' is separate and in POINTS (tblIncentiveAmount.CreditPoints). If asked "
    "for basic salary, overtime, deductions, gross/net payable, or a payroll slip, say "
    "PLAINLY those are not tracked in this system — NEVER invent them and never label "
    "piece-rate labour as 'basic salary'. BUT this is NOT a scope refusal: it IS a data "
    "question you can partly answer, so OFFER the available alternative — the piece-rate "
    "labour each employee EARNED (SUM(FinalLabour)) plus their bonus — and give that if "
    "the user wants it.",
    "PRODUCTION / OUTPUT — 'production' = FINISHED/polished packets in tblFinalPacket "
    "(one row per finished packet; filter CreateDate for today/this-month/date-range). "
    "tblFinalPacket has NO department column, so for 'department-wise production' break "
    "down processing activity BY DepartmentName using tblPointRateLabour (GROUP BY "
    "DepartmentName — count packets, sum points, or sum FinalLabour) or by stage via "
    "tblPacketHistory.Process. Pick a clear measure and GROUP properly — never collapse "
    "production into a single bucket/row.",
    "PRODUCTION LOSS for MFG employees — tblPointRateLabour.LossWeight/LossAmount are "
    "populated ONLY for cutting-stage departments (Blocking, Brooter, Dilate…) and are "
    "NULL for ALL MFG departments, so you CANNOT read MFG loss from those columns. MFG "
    "weight loss = yield loss (RoughWt − PolishedWt) per packet, attributed to the MFG "
    "worker via tblPacketHistory (Process LIKE 'MFG%', EmpId, WightLoss). Say whether "
    "'loss' means weight or value, and that MFG loss is derived, not a stored column.",
    "GIA RESULTS — the CURRENT GIA outcomes are GIA-certified finished packets: "
    "tblFinalPacket WHERE Lab = 'GIA' (live, one row per packet, dated by CreateDate). "
    "The plan-side GIA grade is tblPlanMaster rows WHERE RapVer = 'GIA'. Do NOT use "
    "tblLabourResultGIA for 'recent/this-month GIA' — it is STALE (ends mid-2024). "
    "tblPlanMaster.RapVer marks the plan STAGE (MKB, PLS=polish, GIA, MFG, CLV…) and "
    "IsApproved flags an approved plan. Comparing a GIA result to the 'Marker Approved "
    "Plan', or finding 'Polish plans still pending GIA', means self-joining tblPlanMaster "
    "by Packet_ID across these RapVer stages — but CONFIRM with the client exactly which "
    "RapVer value = 'Marker Approved' before trusting that comparison.",
    "AMBIGUOUS 'HOW MANY DIAMONDS' — the word 'diamonds' has no single unit here, so a "
    "bare 'how many diamonds do we have' is AMBIGUOUS: it can mean PACKETS (tblPacket, "
    "one row per packet), individual PIECES/stones (nang / Pcs counts), or FINISHED/"
    "polished stones (tblFinalPacket). Do NOT fire one COUNT and present it as 'the number "
    "of diamonds' — ASK which they mean (packets, pieces, or finished stones), or state "
    "which you counted. ('Diamonds in stock' is different and IS answerable: "
    "tblPacket.RunningProcess = 'IN Stock'.)",
    "AMBIGUOUS 'VALUE / TOTAL VALUE' — 'value' maps to SEVERAL different money columns on "
    "tblPacket/tblKapan (RoughValue, EstValue, Estimate, OEstimate, REstimate, Amount, "
    "PAmount), which mean different things (rough vs estimated vs revised vs final). A bare "
    "'what's our total value' is AMBIGUOUS — ASK whether they mean rough, estimated or "
    "final value (and which column) rather than SUM one column and present a single "
    "definitive number.",
    "PROFIT / MARGIN / COST are NOT tracked — the packet tables store only a value/price "
    "(Amount, Estimate) with NO cost basis (no purchase-cost, no cost-of-manufacture "
    "column anywhere), so profit MARGIN cannot be computed. Do NOT fabricate a margin by "
    "treating Estimate vs Amount as cost vs revenue. Explain that margin isn't derivable "
    "without a cost figure, and offer the Amount/Estimate values that DO exist.",
    "CERTIFICATE PDF / FILE — no certificate PDF, file, attachment or download link is "
    "stored anywhere in this database (it is a SQL-over-data assistant, not a file store). "
    "What DOES exist is the certificate METADATA on tblPacketDetail: ReportNo (the lab "
    "report/certificate number) and Inscription. So for 'download/give the certificate PDF "
    "for this stone', say no PDF/file is stored and OFFER the ReportNo / Inscription from "
    "tblPacketDetail instead — never invent a download link.",
]

# Tricky joins / relationships - how to apply filters that need another table.
JOIN_HINTS = [
    "JANGAD by stone attributes: tblJangadPackets only has PacketId, Carat, "
    "Amount, IsReceived. To filter jangad packets by Shape, Color, Florecent, "
    "Tension or Cut, JOIN tblJangadPackets.PacketId = tblPacket.ID (those "
    "attribute columns live on tblPacket).",
    "PER-POINT LABOUR: tblPointRateLabour is the CURRENT per-packet labour table "
    "(see the BONUS/LABOUR/EARNINGS hint). It has DepartmentName, ReportRate = rate "
    "per point, Packet_ID, Shape, Tansion — but NOT fluorescence. For non/"
    "fluorescent filtering, JOIN Packet_ID = tblPacket.ID (Florecent).",
    "MANAGERS-ONLY final packets: tblFinalPacket.UserID is who created it. For "
    "'managers only', JOIN UserID = tblEmployee.ID WHERE IsManager = 1.",
    "DAMAGE REPORT: any 'damage' question uses tblPlanReport WHERE IsDamageReport "
    "= 1 (this is THE damage table — NOT tblLabourResult, NOT Junk, NOT SubPcs). "
    "A 'damage report' means a DETAIL listing (one row per damage record), NOT a "
    "GROUP BY summary. Columns to show (NO raw KapanID/PacketID, and NO "
    "repetition — client rule): KapanName, PacketNo AS Packet (just the number, "
    "NOT 'AA-1', because KapanName is already its own column), employee name + "
    "DepartMentName (JOIN EmpID = tblEmployee.ID), PreWt (rough wt before), "
    "NewWt, WtDiff, Points, Rate, Amount, InceDamageTypeName (the damage type "
    "label — DamageTypeName holds a rate number, use InceDamageTypeName for the "
    "type), CreatedDate. 'Kapan wise' means ORDER BY KapanName (detail rows "
    "grouped visually by kapan), not an aggregate. Only aggregate if the user "
    "explicitly asks for totals/summary.",
    "INCENTIVE by employee (tblIncentiveAmount) — measured in POINTS, and the money "
    "column is DEAD. The rupee 'Credit'/'Debit' columns are LEGACY: populated only up "
    "to 2019 and 100% NULL from 2020 onward — do NOT SUM(Credit) for recent incentive "
    "(it returns nothing). The LIVE measure is a POINTS ledger: CreditPoints (incentive "
    "points EARNED) and DebitPoints (points DEDUCTED, stored negative), dated by "
    "TransactTime. For 'incentive earned by employee' use SUM(CreditPoints) (gross "
    "earned); for a NET figure use SUM(CreditPoints) + SUM(DebitPoints). Report these "
    "as POINTS, never as ₹/rupees. ALWAYS JOIN EmpID = tblEmployee.ID and GROUP BY "
    "e.ID (the NUMERIC id), NEVER by name — names are shared by several people, so "
    "grouping by name merges distinct employees and inflates totals. Show the name "
    "(FirstName+LastName) and DepartMentName, never bare EmpIDs. (Company-wide it is "
    "NOT zero-sum: in 2025 deductions slightly exceeded credits.)",
    "BONUS / LABOUR / EARNINGS by employee — WHICH TABLE depends on the PERIOD "
    "(getting this wrong returns STALE / EMPTY data). The same per-packet-process "
    "labour lives in TWO tables that succeeded each other: "
    "  - tblPointRateLabour = the CURRENT table, ~mid-2022 to TODAY (live). USE "
    "THIS for any current / this-year / this-month / recent / 'now' / unspecified-"
    "period earnings or bonus question, and as the default for 'top earners / top "
    "bonus'. Date column = ProcessDate. "
    "  - tblLabourResult = the OLD/HISTORICAL table, 2020 to early 2023 ONLY (it "
    "essentially STOPS — almost no rows after Feb 2023). Use it ONLY for a period "
    "before mid-2022. "
    "  They OVERLAP mid-2022..Feb-2023 (the SAME packets, at slightly different "
    "recomputed amounts), so NEVER UNION or SUM BOTH together — that double-counts. "
    "Pick ONE table by period; for a full multi-year history use tblPointRateLabour "
    "and only add tblLabourResult for the pre-mid-2022 part. Never use the "
    "*GIA/*Edit/*_Compare copies. "
    "  Both tables have the SAME identity + measure columns: the worker is the "
    "NUMERIC Emp_ID -> JOIN tblEmployee.ID (they ALSO carry an EmpName column that "
    "is a short CODE like 'M2139' — NOT the name, NOT for grouping, IGNORE it). Two "
    "DIFFERENT measures: FinalLabour = what the worker EARNS per process (labour "
    "pay) — SUM(FinalLabour) for 'earnings/wages/salary/labour paid/how much did an "
    "employee make'; BonusAmount = a SEPARATE bonus (can be negative = deduction) — "
    "SUM(BonusAmount) only for 'bonus'. The 'top earner' and 'top bonus' lists "
    "differ. "
    "Template (swap the table name to match the period): SELECT e.FirstName + ' ' + "
    "e.LastName AS EmployeeName, e.DepartMentName, SUM(t.<FinalLabour|BonusAmount>) "
    "AS Total, COUNT(*) AS Transactions FROM tblPointRateLabour t JOIN tblEmployee "
    "e ON t.Emp_ID = e.ID GROUP BY e.ID, e.FirstName + ' ' + e.LastName, "
    "e.DepartMentName ORDER BY Total DESC. GROUP BY e.ID (the numeric id), NEVER by "
    "name — names are shared by up to 9 different people, so grouping by name "
    "merges distinct employees and inflates the totals.",
    "EMPLOYEE CONTEXT: tblEmployee.ID is the employee key used everywhere else "
    "(EmpID/Emp_ID/UserID). It carries FirstName/MiddleName/LastName, "
    "DepartMent_ID + DepartMentName, Code, IsManager, IsActive, JoinDate - one "
    "join gives name AND department.",
    "ATTENDANCE / PRESENT DAYS (DATA LIMITATION - be honest): tblTimeAttendance "
    "has one row per biometric punch, dated by the 'Time' column. BUT its EmpId "
    "column is EMPTY (100% NULL) and its UserId is a machine id that does NOT "
    "map cleanly to employees (only ~14% match tblEmployee.ID, 0% match Code). "
    "So attendance CANNOT be reliably reported per named employee. If asked for "
    "an employee's present days / attendance, say plainly that attendance is "
    "recorded as machine punches that aren't reliably linked to employee records, "
    "so per-employee attendance isn't available - do NOT invent it or return an "
    "empty join as if it were the answer. Overall punch counts by date are OK. "
    "TWO related traps/opportunities: (a) tblEmployeeTimeAttandance is NOT attendance "
    "despite the name — it's a gate-pass/receipt register (PassNo/PassCode/ReceiptName; "
    "InTime/OutTime are ~89% empty, many 'employees' are outside parties). Do NOT use it "
    "for attendance. (b) LEAVE, however, IS answerable: tblLeaveReport (EmpID, "
    "LeaveDate_From, LeaveDate_To, IsApproved, DeptID, Reason) records leaves per "
    "employee. For 'how many leaves / who was on leave / leave this month', JOIN EmpID = "
    "tblEmployee.ID, filter the dates (IsApproved=1 for approved only), and count rows or "
    "sum DATEDIFF(day, LeaveDate_From, LeaveDate_To)+1. Its LeaveTypeID is an un-decoded "
    "CODE (no lookup table) — report leave counts/dates, don't try to name the type.",
    "DEPARTMENTS: department NAMES are specific stages, so match them correctly. "
    "'MANUFACTURING' / 'MFG department' is NOT a literal name — it means the MFG "
    "stages: DepartmentName LIKE 'MFG%' (covers MFG-1..MFG-6 and the VL MFG-* branch "
    "variants). Filtering DepartmentName = 'Manufacturing' returns NOTHING. Likewise "
    "there is NO department literally named 'Cutting'. Cutting-stage "
    "departments include Marker, Blocking, Brooter, Dhar, Saw, and MFG stages. If "
    "a question says 'cutting department' with no exact match, ask which one. "
    "tblDepartMent is a FLAT list (~92 rows, no parent/child hierarchy); its "
    "'OriginType' column loosely buckets variants (e.g. Blocking + Blocking Auto share "
    "OriginType 'Blocking'; Laser + Water Jet share 'Lasser') if you need to group "
    "related departments.",
    "SCRAP/JUNK & REPAIR-COMMENT display: tblJunk carries only the numeric Kapan_ID/"
    "Packet_ID, so to show the kapan name JOIN tblJunk.Kapan_ID = tblKapan.ID "
    "(KapanName) and tblJunk.Packet_ID = tblPacket.ID (PacketNo). tblRepairCommentVision "
    "already has the stone attributes and EmpName inline, but its EmpName is a login "
    "CODE (e.g. 'PC002') - for a real person name JOIN EmpId = tblEmployee.ID and show "
    "FirstName + ' ' + LastName (same rule as everywhere: identify people by numeric id).",
    "JANGAD by PARTY / branch / who has our goods: there are TWO jangad tables. "
    "tblJangad (~15.6k rows) is the TRANSACTION HEADER — one row per issue/receive of "
    "goods to/from a party: JangadNo, JangadDate, FromParty/ToParty (party NAMES stored "
    "inline) + FromPartyId/ToPartyId, TransType ('Issue'/'Receive'), Process, KapanName, "
    "Pcs, Carats, Amount, BranchId, IsReceived. tblJangadPackets (~190k rows) is the "
    "PACKET-LINE detail (JangadId, PacketId, PacketNo, Carat, IsReceived). So: for "
    "'jangad by party / to whom / which sub-contractor / branch-wise', group tblJangad "
    "by ToParty/FromParty (or JOIN FromPartyId/ToPartyId = tblParty.ID for GST/city "
    "etc.). tblJangad.TransType tells DIRECTION: 'Issue' = goods sent OUT, 'Receive' = "
    "goods coming BACK (returns, NOT sales). So header-level 'currently OUT on jangad' = "
    "tblJangad WHERE TransType='Issue' AND IsReceived=0. For 'how many PACKETS are "
    "currently on jangad' use tblJangadPackets WHERE IsReceived=0 (use COUNT(DISTINCT "
    "PacketId) — the same packet gets re-issued, so raw rows over-count: ~190k rows but "
    "~140k distinct packets). tblParty is the party master (Name, Type='Job Work', City, "
    "GST, IsOutSideParty). A jangad is NOT a sale (see the sales note). Jangad is also "
    "how packets go OUT to sub-contractors for specific job-work PROCESSES: "
    "tblJangadProcess lists those processes + the party doing each (Green Sawing, "
    "Ghisi, Water Jet, Galaxy, Fancy…); tblJangadRate has the per-party per-process "
    "rate (PartyName, Process, FromWt/ToWt, Amount, IsPerPcs) for 'what do we pay X "
    "for process Y'.",
    "ORIGIN / MINE of the rough: tblKapan stores BOTH as TEXT names right on the kapan "
    "row — RoughOrigin = the COUNTRY (e.g. ANGOLA, CANADA, BOTSWANA, 'MIX') and Mine = "
    "the mine/source (e.g. DTC, ALROSA, DE BEERS, DIAWIK, OUTSIDE). No join needed — "
    "filter/group tblKapan.RoughOrigin or tblKapan.Mine directly (use LIKE for safety; "
    "some rows are NULL). tblRoughOriginMaster and tblMine are just the dropdown lookup "
    "lists. To roll origin/mine up to packets or labour, JOIN via Kapan_ID.",
    "PACKET JOURNEY / CURRENT vs PAST stage: a packet's CURRENT stage is "
    "tblPacket.RunningProcess (one value on the master row). Its PAST movements — 'where "
    "has this packet been / what processes has it gone through / who handled it / when' — "
    "are in tblPacketHistory (one row per completed step: Process, EmpId->ToEmpId, "
    "ReciveTime), ORDER BY ReciveTime for the timeline. These history/issue tables have "
    "~34 rows PER packet (5.5M rows), so ALWAYS COUNT(DISTINCT Packet_ID), never COUNT(*), "
    "and identify the worker by the numeric EmpId -> tblEmployee.ID (EmpName is a code).",
]


# Gujarati / Hinglish phrases employees use (this is a Surat diamond firm).
# These are MEANING words, not data values - translate intent, don't match them
# as names. Critical: "sauthi vadhare" means "the most", NOT a person/kapan name.
GUJLISH_TERMS = {
    "sauthi vadhare / sauthi vadhu": "the MOST / highest (use MAX or ORDER BY ... DESC). NOT a name.",
    "sauthi ochu / sauthi ocha": "the LEAST / lowest (use MIN or ORDER BY ... ASC).",
    "ketla / ketli / ketlo": "how many / how much (a COUNT or SUM question).",
    "karigar": "worker / employee.",
    "maal": "goods / stock / material.",
    "atyare": "right now / currently.",
    "aakha mahina ma": "in the whole month.",
    "kaya / kya": "which.",
    "che": "is / are.",
    "na / ni / no": "of (possessive).",
    "thayu / thaya / thai": "happened / done / made.",
    "malyu": "got / received.",
    "pending": "still out / not returned (for jangad, IsReceived = 0).",
    # --- Merged from GLOWSTAR_KNOWLEDGE.md §6 (intent words, NEVER data values) ---
    # §6.1 manufacturing-floor terms
    "hira": "diamond ('hira bazar' = diamond market).",
    "hira karigar": "diamond cutter-polisher (same as karigar).",
    "ghanti": "the polishing wheel (Western: scaife) / the polishing task — NOT a name or code.",
    "hiraghasu": "old slang for a diamond polisher — recognize it, do NOT use it as a filter.",
    "table / tablework": "polishing the single top facet (a piece-rated task).",
    "taliya / talia": "polishing the pavilion (bottom) facets — a labour task.",
    "mathala": "polishing the upper crown facets — a labour task.",
    "athpel": "polishing the 8 main crown facets — a labour task.",
    "pel": "a facet / a facet-polishing pass.",
    "ghat": "shape/form of a stone ('ghat aapvo' = to give shape, i.e. blocking/bruting). [verify usage with client]",
    "cent": "1/100 carat = a point ('5 cent no nang' = a 5-pointer).",
    "nang": "a piece/stone — the counting word for diamonds ('ketla nang' = how many stones, COUNT).",
    "vajan": "weight.",
    "kacho maal": "rough / unfinished goods.",
    "tayyar maal": "finished / polished goods.",
    "bhangar": "scrap / junk / rejection material (ERP: Junk).",
    "daag": "a spot → an inclusion ('kala daag' = black inclusion). [verify with client]",
    "paani": "'water' = luster/limpidity of a stone (old trade idiom).",
    "majuri": "labour charge / piece-rate wages.",
    "pagar": "salary / wages.",
    "haajar / gerhajar": "present / absent (attendance questions).",
    "raja": "leave / holiday.",
    "sagdi / mandvi / ratti": "unverified as Surat diamond-floor terms — do NOT map to data; ask the client. [verify]",
    # §6.2 trading terms
    "jangad": "goods sent out on approval/entrustment (NOT a sale); see tblJangadPackets, IsReceived=0 = still out.",
    "dalal / dalali": "broker / brokerage commission.",
    "angadia": "trusted courier carrying diamond parcels & cash (Surat ⇄ Mumbai).",
    "baki": "outstanding / remaining / balance (a pending amount or goods) — NOT the old worker-advance system.",
    "udhar": "on credit ('rokad' = cash).",
    "rokad": "cash.",
    "bhav": "price / rate ('aaj no bhav' = today's rate).",
    "back": "% discount off the Rapaport list ('20 back' = 20% below Rap).",
    "rap / rapo": "the Rapaport price list (market-value reference).",
    "seth / shethiya": "owner / boss / proprietor.",
    "vepari": "trader / merchant.",
    "hisab": "account / reckoning ('hisab aapo' = give the summary).",
    "chukvani": "payment / settlement.",
    "sight / sightholder": "De Beers term-contract rough buyer.",
    "polki": "flat uncut / rose-cut diamond (jewelry-side term).",
    # §6.3 question-word Gujlish
    "su / shu": "what.",
    "kem": "why / how ('kem che' = how are you).",
    "kyare": "when (a time filter).",
    "kone / kona": "who / whose (employee lookup).",
    "ketla nang": "how many stones (COUNT).",
    "kul": "total (SUM).",
    "sarasari": "average (AVG).",
    "aaje / kaale": "today / yesterday-or-tomorrow (by context).",
    "gaya mahine / aa mahine": "last month / this month.",
    "aa varshe / gaya varshe": "this year / last year.",
    "badha / badhu": "all / everything.",
    "navu / junu": "new / old.",
    "motu / nanu": "big / small.",
    "vadhyu / ghatyu": "increased / decreased.",
    "chalu": "active / running (IsActive = 1).",
    "band": "closed / stopped / inactive.",
    "kharab": "bad / damaged (→ damage report, repair).",
    "tutela": "broken (→ damage / repair).",
    "baki che": "is pending / outstanding (jangad IsReceived=0, or dues).",
}


def render_data_notes() -> str:
    """Return data notes + value codes + gujlish terms as a text block."""
    lines = ["=== DATA NOTES (column spellings & how to filter) ==="]
    for note in DATA_NOTES:
        lines.append(f"- {note}")
    lines.append("\n=== VALUE CODES (what coded column values mean) ===")
    for name, meaning in VALUE_CODES.items():
        lines.append(f"- {name}: {meaning}")
    lines.append("\n=== GUJARATI/HINGLISH PHRASES (translate intent, don't match as names) ===")
    for phrase, meaning in GUJLISH_TERMS.items():
        lines.append(f"- {phrase}: {meaning}")
    lines.append("\n=== TRICKY JOINS (how to apply filters that need another table) ===")
    for hint in JOIN_HINTS:
        lines.append(f"- {hint}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. TABLE NOTES  (table name -> {note, status})
#    Business meaning of the key tables. Inferred from names + research;
#    confirm column-level specifics with the client.
# ---------------------------------------------------------------------------
TABLE_NOTES = {
    "tblPacket": {
        "note": "Master list of packets (the central packet record other tables link to).",
        "status": "verify",
    },
    "tblPacketHistory": {
        "note": (
            "THE packet-journey table: one row per packet per process step COMPLETED "
            "(received into a stage). ~5.5M rows, ~34 per packet — so NEVER COUNT(*) "
            "for packet totals (use COUNT(DISTINCT Packet_ID)). Rich: Process, EmpId + "
            "ToEmpId (who handled it / who it went to next), ManagerId, Weight, Value, "
            "WightLoss, JunkLoss, ReciveTime (the date column, live to now). Use this "
            "for 'where has this packet been / its process history / who worked on it' "
            "— filter to one Packet_ID and ORDER BY ReciveTime. EmpName here is a CODE; "
            "join EmpId = tblEmployee.ID for names."
        ),
        "status": "confirmed",
    },
    "tblPacketIssue": {
        "note": (
            "The ISSUE-OUT log (companion to tblPacketHistory's receive side): one row "
            "per time a packet was ISSUED to a process/worker — Process, EmpId (issued "
            "to), IssueWt, IssueTime. ~5.5M rows, ~34 per packet — NEVER COUNT(*) for "
            "totals. For a packet's completed journey prefer tblPacketHistory (richer)."
        ),
        "status": "confirmed",
    },
    "tblPacketDetail": {
        "note": (
            "Per-packet detail lines — holds the certificate / lab-report METADATA: "
            "ReportNo (the certificate/report number) and Inscription. NOTE: no "
            "certificate PDF / file / attachment is stored anywhere in the DB — for a "
            "'certificate' or 'download the certificate' question, offer the ReportNo / "
            "Inscription from here and say no file is stored."
        ),
        "status": "verify",
    },
    "tblPacketPoint": {
        "note": "Weight (in points) of packets.",
        "status": "verify",
    },
    "tblFinalPacket": {
        "note": (
            "PRODUCTION OUTPUT / finished-goods table — one row per FINISHED "
            "packet (no row inflation, so COUNT(*) is safe here). Carries the final "
            "grade (Shape, Color, Purity=clarity, Cut, Polish, Symmetry, Florocent), "
            "RoughWt, CurrentWt (polished weight), WeightLoss, Tops, Amount, Lab, "
            "CreateDate, and KapanName. Use this for 'production / output / how many "
            "polished / finished this month' and yield (WeightLoss) questions."
        ),
        "status": "verify",
    },
    "tblIssuedPacketDetail": {
        "note": "Detail lines for issued packets.",
        "status": "verify",
    },
    "tblJangadPackets": {
        "note": (
            "Packets sent out on jangad (approval / sale-or-return). "
            "IsReceived=0 means still OUT ('currently on jangad'); "
            "IsReceived=1 means returned/received. To count packets CURRENTLY "
            "on jangad, filter WHERE IsReceived = 0."
        ),
        "status": "verify",
    },
    "tblPlanMaster": {
        "note": "The cutting plan for each rough stone (planning stage).",
        "status": "verify",
    },
    "tblPlanMasterOptional": {
        "note": "Optional/alternative cutting plans for a stone.",
        "status": "verify",
    },
    "tblPlanReport": {
        "note": (
            "DAMAGE REPORT table — THIS is the table for any 'damage report'. "
            "A damage record is IsDamageReport = 1. A 'damage report' = DETAIL "
            "rows (never a GROUP BY summary unless the user asks for totals). "
            "Show NO raw KapanID/PacketID and NO repetition (client rule) — "
            "KapanName is its own column so the packet column is JUST the number: "
            "SELECT KapanName, pr.PacketNo AS Packet, "
            "e.FirstName + ' ' + e.LastName AS EmployeeName, e.DepartMentName, "
            "PreWt, NewWt, WtDiff, Points, Rate, Amount, "
            "InceDamageTypeName AS DamageType, CreatedDate "
            "FROM tblPlanReport pr JOIN tblEmployee e ON pr.EmpID = e.ID "
            "WHERE IsDamageReport = 1 ORDER BY KapanName, CreatedDate. "
            "PreWt/NewWt = rough weight before/after the damage, WtDiff = loss. "
            "InceDamageTypeName is the damage-type LABEL (DamageTypeName holds a "
            "rate number, not a name). Damage is NOT the same as Junk — do NOT "
            "use tblLabourResult/SubPcs for damage."
        ),
        "status": "verify",
    },
    "tblLabourRate": {
        "note": "Piece-rates paid to labour per process/stage.",
        "status": "verify",
    },
    "tblPointRateLabour": {
        "note": (
            "The CURRENT per-packet-process labour & bonus table (~mid-2022 to now, "
            "live). One row per worker-per-packet-process with FinalLabour (earnings), "
            "BonusAmount, LabourAmount, Emp_ID, KapanName, DepartmentName, ProcessDate. "
            "This SUPERSEDED tblLabourResult — use THIS for current/recent earnings & "
            "bonus. Do NOT confuse it with the rate-CARD table tblLabourRate. See the "
            "BONUS/LABOUR/EARNINGS data note."
        ),
        "status": "confirmed",
    },
    "tblLabourResult": {
        "note": (
            "HISTORICAL per-packet-process labour & bonus (2020 to early 2023 ONLY — "
            "essentially dead after Feb 2023; tblPointRateLabour replaced it). Same "
            "columns (Emp_ID, FinalLabour, BonusAmount, ProcessDate). Use it ONLY for "
            "a pre-mid-2022 period, and NEVER union/sum it together with "
            "tblPointRateLabour (they overlap mid-2022..Feb-2023 and would double-"
            "count). See the BONUS/LABOUR/EARNINGS data note."
        ),
        "status": "confirmed",
    },
    "tblIncentiveAmount": {
        "note": (
            "Incentive ledger, measured in POINTS. The rupee Credit/Debit columns are "
            "LEGACY (only populated up to 2019, NULL from 2020 on). Live measure = "
            "CreditPoints (earned) / DebitPoints (deducted, negative), by TransactTime. "
            "See the INCENTIVE data note — report points, not ₹."
        ),
        "status": "confirmed",
    },
    "tblEmpGIABonus": {
        "note": (
            "One-time GIA-bonus RECONCILIATION batch from 2019 ONLY (all rows dated "
            "Apr–Oct 2019). Per packet it holds the MFG, PLS (polish) and GIA plan "
            "amounts (MFGAmount/PLSAmount/GIAAmount). NOT a live/ongoing bonus stream — "
            "do not use it for current bonus; for that see tblPointRateLabour."
        ),
        "status": "verify",
    },
    "tblBonusRate": {
        "note": (
            "Bonus rate-CARD (config lookup, ~1.5M rows) — a rate per (weight-range + "
            "coded attrs) keyed by CriteriaID. NOT money paid; never SUM it. Shape is "
            "stored as a comma-list. See the RATE CARDS data note."
        ),
        "status": "confirmed",
    },
    "tblOriginWiseLabour": {
        "note": (
            "Another labour rate-CARD, broken down by Origin (e.g. 'MFG') + Shape/"
            "Color/Clarity/Cut/weight-range -> Amount. Config lookup, NOT money paid — "
            "don't SUM for totals (use tblPointRateLabour.FinalLabour)."
        ),
        "status": "verify",
    },
    "tblLabour_MW": {
        "note": (
            "Monthly per-employee WORK-POINT summary (DepName, EmpId, WorkPoint, Month, "
            "Year), 2021–2024 only. WARNING: the 'Final' (final wage) and 'Adjust' "
            "columns are essentially EMPTY (NULL) — only WorkPoint is populated. Do NOT "
            "use this for monthly wages/pay; for money paid per month aggregate "
            "tblPointRateLabour.FinalLabour by month instead."
        ),
        "status": "verify",
    },
    "tblBox": {
        "note": (
            "Incoming ROUGH box/lot register (as purchased, before/around becoming a "
            "kapan): BoxNo, LotNo, TotalWeight, TotalPcs, AvgSize, Article (the rough "
            "assortment type, e.g. 'GEM MB WHIT 8GR'). Use for 'rough lots/boxes/"
            "parcels received' questions. ~539 rows."
        ),
        "status": "verify",
    },
    "tblKapanChallan": {
        "note": (
            "Simple lookup of the challan (dispatch/delivery note) number per kapan: "
            "KapanName, ChallanNo, UpdateDate. Use to answer 'which challan number was "
            "kapan X on'."
        ),
        "status": "verify",
    },
    "tblParam": {
        "note": (
            "APP CONFIG / settings key-value store (ParamType/ParamName/ParamValue, "
            "e.g. 'KapanHold', 'MKBApprove') — NOT diamond/packet data. Do NOT use it "
            "for a 'parameters' question about a stone; the stone's measured parameters "
            "are in tblPacketParameters. Ignore tblParam for business questions."
        ),
        "status": "confirmed",
    },
    "tblPacketParameters": {
        "note": (
            "Per-packet MEASURED proportions (one row per packet): DiaAvg/Min/Max, "
            "Depthmm, TablePer, DepthPer, GirdlePer, CrAng (crown angle), PavAng "
            "(pavilion angle), Ratio, StarLn. Use for 'proportions / measurements / "
            "table%/depth% / crown-pavilion angle'. NOTE the GIA/IGI/AGS/HRD columns "
            "hold that lab's CUT GRADE (e.g. 'GIA-V'), not a report id; and its "
            "Symmetry column is unreliable ('-', mixed) — use tblFinalPacket.Symmetry "
            "for the symmetry grade."
        ),
        "status": "verify",
    },
    "tblPctChecker": {
        "note": (
            "Attribution: who MADE and who POLISHED each packet — PacketId, Kapan, "
            "PacketNo, MfgEmpId/MfgEmpCode (manufacturer) and PolishEmpId/PolishEmpCode "
            "(polisher). Use for 'who made / who polished packet X' or 'which packets "
            "did worker Y make/polish'. The codes are labels — JOIN the numeric "
            "MfgEmpId/PolishEmpId = tblEmployee.ID for real names."
        ),
        "status": "verify",
    },
    "tblReportRate": {
        "note": "Rates used for reporting/valuation.",
        "status": "verify",
    },
    "tblRepairLog": {
        "note": (
            "NOT a diamond-repair table — it is a database CHANGE/AUDIT LOG and it "
            "is DEAD (last row Feb 2022). Do NOT use it to count repaired stones."
        ),
        "status": "confirmed",
    },
    "tblRepairLogNew": {
        "note": (
            "NOT diamond re-polishing — a CRUD AUDIT TRAIL. Each row logs a row "
            "Insert/Update/Delete on a plan table (Specification = Insert/Update/"
            "Delete; TableName = tblPlanMaster/tblPlanReport/tblPacket; Remark = "
            "'Plan Approved'/'Auto Report Done'). Use it ONLY for 'who changed this "
            "plan/record and when', NEVER for 'how many stones were repaired'. "
            "EmpID is ~93% empty; the user is CreatedBy."
        ),
        "status": "confirmed",
    },
    "tblRepairCommentVision": {
        "note": (
            "THE real stone re-check / repair-comment table (from the Vision "
            "checking stage). One row per flagged stone: RepairComment = the reason "
            "(e.g. 'Cut Border Line', 'Clarity', 'Natural'), plus full stone attrs "
            "(Shape, Purity/clarity, Color, Cut, Polish, Symmetry, Florecent, "
            "PolishedWt, RoughWt, Rate, Amount) and EmpId/EmpName + IsApproved. "
            "~4.3k rows. THIS is what 'stones sent for repair / re-check' means — "
            "not tblRepairLog/tblRepairLogNew."
        ),
        "status": "verify",
    },
    "tblJunk": {
        "note": (
            "Scrap / junk / bhangar diamond material (the closest thing to "
            "'rejection' data — tblRejection itself is EMPTY). One row per scrapped "
            "piece: Kapan_ID, Packet_ID, Weight (carats of scrap), Pcs, CreateDate. "
            "USABLE columns are only Weight/Pcs/Kapan_ID/Packet_ID/CreateDate — "
            "Value is 95% NULL, Grede is 100% NULL, IsRecyleble is constant (all 1), "
            "so do NOT report junk 'value' or 'grade'. For scrap totals use "
            "SUM(Weight) and COUNT(DISTINCT Packet_ID) by kapan/date."
        ),
        "status": "verify",
    },
    "tblStockItem": {
        "note": (
            "CONSUMABLES / STORES inventory — NOT diamonds. The whole tblStock* "
            "family (tblStockItem/StockDetail/StockCategory/StockIssue/StockPurchage"
            "/StockGodown/StockUnit/StockTally) tracks office & factory supplies "
            "(pens, ink, MFG machine tools & liquids, cleaning, kitchen, "
            "electronics). A question about DIAMOND stock must NOT use these tables "
            "— use tblPacket.RunningProcess (see data notes). tblStockInventory is "
            "empty."
        ),
        "status": "confirmed",
    },
    "tblTimeAttendance": {
        "note": "Worker attendance records.",
        "status": "verify",
    },
    "tblEmployee": {
        "note": (
            "Master employee records: FirstName, MiddleName, LastName, Code, "
            "department, join date, active status. The employee ID is its ID "
            "column (referenced elsewhere as Emp_ID / EmpId)."
        ),
        "status": "verify",
    },
    "tblEmpDetail": {
        "note": (
            "Employee personal details: address (City, State, Country, "
            "Address1/2), phone, mobile, email. Links to tblEmployee via "
            "Emp_ID. To find employees by city, join tblEmployee.ID = "
            "tblEmpDetail.Emp_ID and filter on City."
        ),
        "status": "verify",
    },
    "tblKapan": {
        "note": (
            "THE kapan master — one row per kapan (a parcel/lot of ROUGH diamonds), "
            "847 rows; count kapans here. Key columns: KapanName (unique display name — "
            "always show this, never the numeric ID); AvgSize = the parcel / lot SIZE in "
            "carats (this is the 'parcel size' / 'lot size' answer; default parcel=kapan); "
            "IsFinished + FinishDate (use WHERE IsFinished=1 AND YEAR(FinishDate)=… for "
            "'kapans finished this year/period'); CreatDate (creation, note the spelling); "
            "RoughOrigin + Mine (rough source, inline text); RoughValue/EstValue. To show a "
            "KAPAN NAME where another table carries only a numeric Kapan_ID, JOIN "
            "tblKapan.ID = Kapan_ID."
        ),
        "status": "verify",
    },
    "tblCompany": {
        "note": (
            "The single company-profile row (GlowStar). Holds the company's own City "
            "(= Surat), address and contact details. Use it whenever a question compares "
            "something to 'the company' itself — e.g. 'workers who live in the SAME CITY "
            "as the company': read the company City from tblCompany, then count "
            "tblEmpDetail.City = that city. Do NOT hard-code 'Surat' — read it here."
        ),
        "status": "verify",
    },
    "tblEmpNativeAddress": {
        "note": (
            "Employees' NATIVE / home-town address — the ONLY place holding District, "
            "Village and Taluka (tblEmpDetail has City/State but NO district). Join "
            "tblEmpNativeAddress.EmpID = tblEmployee.ID (name = FirstName/MiddleName/"
            "LastName on tblEmployee). Use for 'native place / native district / village / "
            "taluka'. NOTE it is sparsely populated — only ~108 of ~2,412 employees have a "
            "non-blank District (values are dirty/mixed-case), so say the district is "
            "recorded for only a minority of employees rather than implying full coverage."
        ),
        "status": "verify",
    },
    "tblParty": {
        "note": (
            "Party master — job-work PARTIES / sub-contractors we send jangad/processes to "
            "(Name, Type='Job Work', City, GST, IsOutSideParty), 51 rows. One of THREE "
            "'client/customer'-type entities — see also tblSupplier (rough suppliers) and "
            "tblBuyerName (buyers). 'Who are our clients/customers' is AMBIGUOUS across "
            "these three: ask which is meant (parties vs suppliers vs buyers) rather than "
            "picking one silently."
        ),
        "status": "verify",
    },
    "tblSupplier": {
        "note": (
            "Rough-diamond SUPPLIERS master (who we BUY rough from), ~50 rows. One of the "
            "three 'client/customer/vendor'-type entities (with tblParty = job-work parties "
            "and tblBuyerName = buyers). For 'who are our suppliers/vendors' use this; for a "
            "generic 'clients/customers' question, clarify which entity is meant."
        ),
        "status": "verify",
    },
    "tblBuyerName": {
        "note": (
            "BUYERS master (who we SELL/consign to), ~8 rows. One of the three "
            "'client/customer/buyer'-type entities (with tblParty = job-work parties and "
            "tblSupplier = rough suppliers). For 'who are our buyers/customers/clients' this "
            "is the buyer list; when the term is ambiguous, ask which entity is meant."
        ),
        "status": "verify",
    },
}


# ---------------------------------------------------------------------------
# 3. RENDERING  - turn the glossary into text the LLM can read.
#    The Phase 2 context builder will append this to the schema context.
# ---------------------------------------------------------------------------
def render_glossary_text() -> str:
    """Return the full glossary as a compact, LLM-friendly text block."""
    lines = ["=== BUSINESS GLOSSARY (diamond manufacturing) ==="]

    lines.append("\n-- Industry terms --")
    for term, info in TERMS.items():
        lines.append(f"- {term}: {info['definition']}")

    lines.append("\n-- Key tables (business meaning) --")
    for table, info in TABLE_NOTES.items():
        lines.append(f"- {table}: {info['note']}")

    return "\n".join(lines)


def table_note(table_name: str) -> str:
    """Return the business note for a table, or '' if we don't have one."""
    info = TABLE_NOTES.get(table_name)
    return info["note"] if info else ""


# Quick manual check: `python -m app.schema.glossary`
if __name__ == "__main__":
    print(render_glossary_text())
