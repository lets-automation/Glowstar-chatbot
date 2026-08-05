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
    # --- Industry terms added from docs/GLOWSTAR_KNOWLEDGE.md (§2.3 pipeline, §4 trade) ---
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
        "Where a packet currently sits. Live values (34 distinct): IN Stock (152k = "
        "90% — the TERMINAL state, overwhelmingly FINISHED goods: 99% have a "
        "tblFinalPacket row; NOT raw material), Rough Estimation, Galaxy, Fency "
        "(packets out with fancy job-work parties — ALL currently-on-jangad packets sit "
        "here), Marker-2/3/4 (NO plain 'Marker' exists), OUT Stock (an internal "
        "late-pipeline stage — ZERO overlap with jangad; never report it as 'goods out "
        "with parties'), Blocking, Blocking Auto, Vision 360, Laser, MFG-2..6 plus "
        "'MFG - 1' (SPACES around the hyphen — filter stage families with LIKE "
        "'Marker%' / LIKE 'MFG%'), Boil / Boil Floor 1/2 / Hard Boil, Weight Scale, "
        "Dilate, STN, 4P, Check Stock, Dhar, SDhar, M-Box, MGST, MFG Admin, Polish "
        "Checker, GIA. This is THE column for 'diamond stock / where are the stones "
        "now' - do NOT use the tblStock* tables for diamonds (those are consumables).",
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
    "(COUNT(DISTINCT EmpID)=1,960, not 607,172 rows); tblLabourResult ~6 rows per "
    "packet; tblPacketHistory & tblPlanMaster have millions of rows, many per "
    "packet. The one-row-per-item master is tblPacket (packets) / tblKapan "
    "(kapans) - count those directly; count history/labour tables with DISTINCT.",
    "DATE COLUMNS differ per table and are inconsistently named/misspelled - use "
    "the RIGHT one for 'today/this month/last year' filters: tblPacket->CreDate; "
    "tblFinalPacket->CreateDate; tblLabourResult->ProcessDate; tblPlanReport->"
    "CreatedDate; tblPlanMaster->CreatDate; tblIncentiveAmount->TransactTime; "
    "tblTimeAttendance->Time; tblPacketHistory->ReciveTime; tblJunk->CreateDate "
    "(IssueDate is 99.5% NULL and frozen at June-2023 — dead, never filter on it); "
    "tblJangad->JangadDate; tblKapan->CreatDate (created) / FinishDate; "
    "tblRepairCommentVision->CreatDate. "
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
    "KAPAN COUNT: count kapans from the kapan master table tblKapan (853 rows = "
    "one row per kapan). Do NOT use COUNT(DISTINCT Kapan_ID) on tblPacket (that "
    "misses kapans with no packets), and avoid the decoys tblKapan_BKP (a deletion log "
    "of removed kapan IDs, NOT a backup — kapans get deleted and re-created) "
    "and tblKapanValue (daily active-kapan progress snapshots, 1,041 distinct KapanIds "
    "incl. 189 deleted — useful for 'kapan progress over time' via its inline "
    "KapanName, never for counting kapans).",
    "TENSION / TANSION GRADE: the authoritative tension grade is column 'Tantion' "
    "on tblPacketCode (note that spelling). To count packets by tension grade use "
    "tblPacketCode WHERE Tantion = N. (tblPacket also has a 'Tension' column, but "
    "tblPacketCode.Tantion is the canonical packet-code grade - be consistent.)",
    "PACKET IDENTITY (PacketNo is NOT unique - avoids a merge bug): a packet is "
    "identified by the NUMERIC key tblPacket.ID (referenced elsewhere as Packet_ID/"
    "PacketID). PacketNo is only a WITHIN-KAPAN display number that repeats across "
    "kapans (there are 168,763 packets but only 2,330 distinct PacketNo values - "
    "PacketNo=1 exists in 852 different kapans). So NEVER GROUP BY, COUNT(DISTINCT "
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
    "labour each employee EARNED (SUM(FinalLabour), which already INCLUDES the bonus component) — and give that if"
    "the user wants it.",
    "PRODUCTION REPORT MUST NAME THE MAKER AND DEPARTMENT — the client's production "
    "report shows WHO made each packet and in WHICH department, and tblFinalPacket has "
    "NEITHER column, so a report built from it alone looks incomplete to them (this was "
    "a direct complaint). ALWAYS attach them via the packet's latest MFG-stage row: "
    "FROM tblFinalPacket fp WITH (NOLOCK) OUTER APPLY (SELECT TOP 1 EmpId FROM "
    "tblPlanMaster WITH (NOLOCK) WHERE Packet_ID = fp.PacketID AND RapVer='MFG' ORDER BY "
    "ID DESC) m LEFT JOIN tblEmployee e ON m.EmpId = e.ID — then select "
    "e.FirstName + ' ' + e.LastName AS Maker and e.DepartMentName AS Department "
    "alongside the packet's own columns (KapanName, PacketNo, Shape, Color, "
    "Purity=Clarity, Cut, Polish, Symmetry, Florocent, CurrentWt, Lab, CreateDate). "
    "Verified: this resolves a maker+department for 100% of finished packets (4,007/4,007 "
    "in June 2026). Use OUTER APPLY + LEFT JOIN (not an inner join) so a packet is never "
    "dropped, and take the LATEST MFG row (ORDER BY ID DESC) — joining all MFG rows "
    "duplicates packets. The same pair belongs on any per-packet listing where the user "
    "asks 'who' or 'which department'.",
    "PRODUCTION / OUTPUT — 'production' = FINISHED/polished packets in tblFinalPacket "
    "(one row per finished packet; filter CreateDate for today/this-month/date-range). "
    "tblFinalPacket has NO department column, so to scope production to ONE department "
    "filter by its packets: PacketID IN (SELECT Packet_ID FROM tblPointRateLabour WHERE "
    "DepartmentName='<dept>'). DEFAULT TO THE PACKET LIST, not a lone total: for a plain "
    "'<dept> production/output/results' (no 'how many/total/summary') LIST the finished "
    "packets — SELECT KapanName, PacketNo AS Packet, Shape, Color, CurrentWt AS Carats, "
    "CreateDate FROM tblFinalPacket WHERE PacketID IN (SELECT Packet_ID FROM "
    "tblPointRateLabour WHERE DepartmentName='<dept>') AND CreateDate in range ORDER BY "
    "KapanName, PacketNo — and open with ONE summary line (packets, total carats). "
    "DATE PLACEMENT IS CRITICAL: put the month/period filter ONLY on tblFinalPacket.CreateDate "
    "(the FINISH date). Keep the department subquery UNDATED — do NOT also filter "
    "tblPointRateLabour by ProcessDate for that period. A packet FINISHES after its department "
    "step, so a dept's labour posting lags — it typically ends weeks before its packets finish, while its "
    "packets keep finishing the next month; dating the subquery drops them and wrongly returns "
    "0 / 'no data' for a month that actually produced hundreds. For "
    "'department-WISE' break BY DepartmentName using tblPointRateLabour (GROUP BY "
    "DepartmentName — count packets, sum points, or sum FinalLabour) or by stage via "
    "tblPacketHistory.Process. Only reduce to a single COUNT/SUM when the user explicitly "
    "asked for a count/total/summary — never collapse production into a single bucket/row.",
    "PRODUCTION LOSS for MFG employees — tblPointRateLabour.LossWeight/LossAmount are "
    "populated ONLY for cutting-stage departments (Blocking, Brooter, Dilate…) and are "
    "NULL for ALL MFG departments, so you CANNOT read MFG loss from those columns. MFG "
    "weight loss = yield loss (RoughWt − PolishedWt) per packet, attributed to the MFG "
    "worker via tblPacketHistory (Process LIKE 'MFG%', EmpId, WightLoss). Say whether "
    "'loss' means weight or value, and that MFG loss is derived, not a stored column.",
    "GIA RESULTS — the client's GIA report is built ENTIRELY from tblPlanMaster (NOT "
    "tblFinalPacket, NOT the stale tblLabourResultGIA which ends mid-2024): per packet, show "
    "the in-house PLS grade NEXT TO the lab GIA grade with a change flag. Both rows are 1:1 "
    "per Packet_ID (every GIA row has exactly one PLS row). Pattern: FROM tblPlanMaster g "
    "WITH (NOLOCK) JOIN tblPlanMaster p WITH (NOLOCK) ON p.Packet_ID=g.Packet_ID AND "
    "p.RapVer='PLS' JOIN tblKapan k ON g.KapanId=k.ID WHERE g.RapVer='GIA' AND g.CreatDate >= "
    "<period> — select the DUAL 4Cs side by side (p.Color vs g.Color, p.Purity vs g.Purity, "
    "Cut/Polish/Symmetry/Florecent) plus HasChange = CASE WHEN any of the six differ (ISNULL "
    "both sides) THEN 'YES' ELSE 'NO' END, g.PolishedWt, g.CreatDate. "
    "IF THE USER MENTIONS EMPLOYEES / WORKERS / 'WHO' (e.g. 'GIA results of Fency "
    "department employees'), ALSO SELECT THE MAKER AND DEPARTMENT — OUTER APPLY (SELECT "
    "TOP 1 EmpId FROM tblPlanMaster WITH (NOLOCK) WHERE Packet_ID=g.Packet_ID AND "
    "RapVer='MFG' ORDER BY ID DESC) m LEFT JOIN tblEmployee e ON m.EmpId=e.ID, then "
    "e.FirstName+' '+e.LastName AS Maker and e.DepartMentName. The maker is what scopes "
    "the report to a department, so using it ONLY in the WHERE clause and omitting the "
    "column leaves the question half-answered (a real client complaint). The lab regrades ~42-55% "
    "of stones — HasChange is the headline number managers want; never give a thin single-grade "
    "list. CRITICAL: RapVer='GIA' is the final-grading STAGE done for ALL stones — its LAB "
    "column (GIA/HRD/IGI/NONE, agrees with tblFinalPacket.Lab ~100%) says which lab actually "
    "certified, and ~34% of GIA-stage rows are LAB='NONE' (uncertified). "
    "DEFAULT TO *ALL* LAB-STAGE ROWS — DO NOT ADD A LAB FILTER unless the user says "
    "'certified'. The client's OWN report filters only on RapVer IN ('GIA','HRD','IGI') "
    "with NO LAB condition, so their figure INCLUDES the uncertified rows: for Fency in "
    "June 2026 that is 1,024 packets across 7 firms, whereas adding AND g.LAB='GIA' gives "
    "only 120 across 4 — a 'correct' number that does not match their report and reads as "
    "wrong in a meeting. So answer with the full lab-stage set, and if certification "
    "matters, add a COLUMN (g.LAB) or a closing line ('120 of these were GIA-certified') "
    "rather than silently filtering. State which basis you used. "
    "tblFinalPacket WHERE Lab='GIA' is fine for a quick "
    "certified-output COUNT by finish month, but its 4Cs are the in-house grade (matches the "
    "lab only ~48%) — NEVER list it as 'what GIA graded'. For HRD/IGI results swap g.RapVer (a "
    "packet has exactly ONE lab row); 'plans still pending GIA' = PLS rows with NOT EXISTS a "
    "RapVer IN ('GIA','HRD','IGI') row.",
    "GIA RESULTS 'EMPLOYEE-WISE' / DEPT ATTRIBUTION — group by the MAKER: the packet's LATEST "
    "MFG-stage row worker in tblPlanMaster (the client's own convention). NEVER group by the "
    "GIA-stage worker or the upload clerk — G001 entered 150,078 of 150,080 GIA-stage rows ever "
    "and tblFinalPacket.UserID is the same single clerk, so either grouping returns ONE name. "
    "Pattern: take GIA rows in the period, JOIN m ON m.Packet_ID=g.Packet_ID AND m.RapVer='MFG' "
    "AND m.ID=(SELECT MAX(ID) FROM tblPlanMaster WITH (NOLOCK) WHERE Packet_ID=g.Packet_ID AND "
    "RapVer='MFG'), JOIN tblEmployee e ON m.EmpId=e.ID, filter/GROUP BY e.DepartMentName / e.ID "
    "with COUNT(DISTINCT g.Packet_ID) and SUM of the HasChange CASE. NEVER join ALL MFG rows "
    "(double-counts — 80% of multi-MFG packets switch worker) . "
    "PERSON NAMES — NEVER DISPLAY OR GROUP BY AN EmpName COLUMN. This applies to EVERY "
    "department, not one. Measured on this DB: tblPacketIssue.EmpName is the employee CODE on "
    "5,642,614 of 5,702,698 rows and a real name on ZERO; tblPointRateLabour.EmpName likewise "
    "(880,250 of 902,150, zero names); tblPlanMaster.EmpName is a real name ~86% of the time but "
    "still the bare code on ~12% (e.g. 'M1332'). Printing EmpName therefore shows the client "
    "codes like 'M1332' / 'Y111' / 'CL403' instead of a person. ALWAYS resolve through the ID "
    "(EmpId / Emp_ID / MfgEmpId / PolishEmpId = tblEmployee.ID) and select "
    "e.FirstName+' '+e.LastName. Use a LEFT JOIN, never an inner one: 60,084 tblPacketIssue, "
    "21,900 tblPointRateLabour, 30,728 tblPlanMaster and 14,516 tblPctChecker rows hold an EmpId "
    "with no matching employee, and an inner join silently drops them. Affected work spans the "
    "whole factory (Rough Estimation 435k, Marker-3 403k, Marker-2 398k, Weight Scale 372k, GS "
    "Jangad, Galaxy, VL Marker, Vision 360, Laser, Blocking...). WHO-DID-WHAT for any packet or "
    "stage: tblPacketIssue is the per-stage log (Process = the stage, EmpId -> the worker, "
    "IssueTime), so a packet manufactured by an outside firm STILL has named in-house people on "
    "its other stages — offer those instead of reporting 'no employee recorded'. "
    "OUTSOURCED WORK IS A PER-ROW EXCEPTION, NOT A DEPARTMENT RULE: 55 tblParty rows are "
    "Type='Job Work' (42 IsOutSideParty) and a few are mirrored into tblEmployee, so a resolved "
    "'employee' is occasionally a FIRM (e.g. SHRI HARI GEMS, party code Y130). It is rare "
    "— only 5 of 1,666 distinct MFG makers match a tblParty name — so NEVER assume a whole "
    "department is outsourced. Detect it PER ROW (resolved name matches a tblParty.Name with "
    "Type='Job Work') and label only those rows as a job-work party. Fency (dept 23, Y###) has "
    "the highest concentration — 92 employee rows, 31 active, ~23 firm-looking — but most of "
    "its roster is individual people, so do NOT describe Fency wholesale as vendor firms. A "
    "job-work firm's tblParty.empId is NULL, so there is NO route to the individual inside that "
    "firm: say that plainly rather than implying the firm name is a person. For LABOUR/EARNINGS attribution use tblPointRateLabour "
    "(Emp_ID, DepartmentName) instead; tblPctChecker is only partial corroboration (see its "
    "note). Dept traps: M#### codes span NINE departments (MFG-1..6 + Dhar/SDhar/FDhar) — filter "
    "by DepartMentName, never by code prefix; D### is ambiguous (Dilate vs Data Entry — resolve "
    "via tblEmployee); the three lab codes G001/HRD001/IGI001 are ONE human — never sum them as "
    "three people.",
    "ISSUE REPORT ('issue report', 'maker and check issue', how much work went to a "
    "department/worker in a period) — source is tblPacketIssue (the issue-OUT log): "
    "Process = the receiving DEPARTMENT/stage, EmpId -> tblEmployee.ID = the WORKER it "
    "went to, plus IssueWt and IssueTime. BOTH grains are available from the same table — "
    "GROUP BY Process for department-wise, GROUP BY EmpId (JOIN tblEmployee) for "
    "employee-wise, or both together for department + worker. Pick the grain the user "
    "asked for; if they didn't say, follow the REPORT GRAIN rule. Measures: "
    "COUNT(DISTINCT Packet_ID) AS PacketsIssued, SUM(IssueWt) AS IssuedWt, "
    "COUNT(DISTINCT EmpId) AS Workers. CRITICAL: many rows per packet (re-issued at every "
    "stage and within a stage) — COUNT(DISTINCT Packet_ID), NEVER COUNT(*): Marker-2 in "
    "June 2026 = 4,350 packets vs 16,373 raw rows (~4x inflation). VOCABULARY: 'maker' = "
    "the MFG-1..6 karigars; 'Marker' (with an R) is the separate marking/planning dept "
    "(Marker-2/3/4); 'check' covers Polish Checker, Galaxy QC, Check Stock, Rough Checker "
    "— when the word is ambiguous, include the matching departments and say which ones you "
    "used. For the separate maker fresh/check-issue flow see the MAKER ISSUE note.",
    "KAPAN MONEY IS A PER-CARAT RATE, NOT A TOTAL — tblKapan.RoughValue and EstValue hold "
    "a RATE PER CARAT (avg ~86, max 1,447 across 853 kapans). SUM(RoughValue) = 73,230 for "
    "223,052 lifetime carats, i.e. 'we bought $73k of rough in five years' — absurd but "
    "plausible-looking. TOTAL value = SUM(Weight * RoughValue) = 9,115,298, which is 124x "
    "the naive sum; average price per carat = SUM(Weight*RoughValue)/SUM(Weight), NEVER "
    "AVG(RoughValue). Same for EstValue — and EstValue is a COPY of RoughValue on 781 of "
    "804 kapans, so NEVER present the two as 'our estimate was 97% accurate'; estimation "
    "accuracy is not measurable here. tblPacket.RoughValue is 0 on all 168,763 rows, so "
    "packet-level rough money does not exist at all.",
    "tblKapanValue IS A NIGHTLY SNAPSHOT, NOT A LEDGER — one row per live kapan PER DAY "
    "(59,912 rows over 1,041 kapans; kapan 'HW' alone has 380 daily rows). The values "
    "REPEAT unchanged day after day, so ANY SUM over this table multiplies by the number "
    "of days: SUM(RoughWt) = 16,917,681 ct against a true latest-day 20,407 ct and a "
    "lifetime intake of 223,052 ct — up to 829x wrong, and absurd enough to discredit "
    "every other number on screen. RSTPoint is worse: it GROWS daily, so summing "
    "double-counts a rising cumulative. ALWAYS de-duplicate to the latest snapshot first "
    "(ROW_NUMBER() OVER (PARTITION BY KapanId ORDER BY CreatedAt DESC)=1, or restrict to "
    "MAX(CAST(CreatedAt AS date))). For lifetime rough weight use tblKapan.Weight, never "
    "this table. 189 of its KapanIds no longer exist in tblKapan — INNER JOIN tblKapan and "
    "say so.",
    "tblPlanMaster AGGREGATION — ONE ROW PER PACKET *PER STAGE*, SO NEVER SUM IT RAW. The "
    "173,353 plan rows in 2026 cover only 27,803 DISTINCT packets. A naive "
    "SUM(PolishedWt)=90,542 ct / COUNT(*)=173,353 against the truth of ~9,855 ct / 27,803 "
    "stones at the GIA stage — 9x and 6x overstated, on the client's own headline metric. "
    "ALWAYS pin ONE RapVer stage AND use COUNT(DISTINCT Packet_ID); the same trap applies "
    "to Amount/OAmount. CLV additionally repeats WITHIN its own stage (1-8 alternative "
    "plans per packet) — take the IsApproved=1 row or MAX(ID). 2026 stage volumes: CLV "
    "47,544 · MFG 22,278 · ADM 21,986 · RST 21,358 · MKB 20,872 · PLS 19,866 · GIA 18,949; "
    "tail LSO 231 · HRD 130 · BLK 110 · FourP 19 · IGI 6. NEVER INNER JOIN tblRapVer to "
    "decode stages — MKB, HRD, FourP and IGI are MISSING from that lookup, so the join "
    "silently drops 21,027 rows (12% of 2026) and loses IGI/HRD entirely; 26 of its 41 "
    "codes have never had a plan row. Get stages from SELECT DISTINCT RapVer instead.",
    "JANGAD DIRECTION — A NAIVE GROUP BY ACCUSES YOUR PARTNERS OF THEFT. Every lot is "
    "recorded TWICE: TransType='Issue' (goods out, ToParty = the sub-contractor) and "
    "TransType='Receive' (goods back, FromParty = that same sub-contractor, "
    "ToParty='GLOW STAR'). So GROUP BY ToParty over ALL rows compares a party's issues "
    "against nothing and reports, e.g., 'DIYORA & BHANDERI returned 1,083 of 48,473 "
    "carats — 97.8% loss'. THE TRUTH: issues 301,427 ct vs receives 299,670 ct — about "
    "99.4% comes back. Reporting the naive version accuses the client's largest job-work "
    "partners of losing tens of thousands of carats; it is unrecoverable in a meeting. "
    "ALWAYS split by TransType: outstanding per party = issues (TransType='Issue' GROUP BY "
    "ToParty) MINUS receives (TransType='Receive' GROUP BY FromParty), and quantity truly "
    "out = tblJangadPackets WHERE IsReceived=0 (header Pcs/Carats over-state ~2x because a "
    "header stays open until every line returns).",
    "EMPLOYEE IDENTIFIERS - DO NOT ASK WHICH KIND IT IS. A token with a LETTER PREFIX (M4117, PC012, Y126, G001, RE044, CL003, B146) is an employee CODE, full stop - 2,431 of 2,450 codes are letter-prefixed and only 19 are digits-only, so there is NO ambiguity with the numeric tblEmployee.ID. Look it up with WHERE Code='M4117' and answer. NEVER reply 'do you mean Code M4117 or ID 4117?' - that is a spurious clarification that wastes the user's turn (M4117 resolves to exactly one person, PANELIYA SANJAY, ID 6726). Only a BARE NUMBER ('employee 4117') is genuinely ambiguous: try Code first, then ID, and say which you used. The separate warning that Code is not unique applies to the handful of DUPLICATE codes (M3022, M2D003, M2128, B146) - check for >1 row and disambiguate ONLY then, never pre-emptively.",
    "BOOLEAN FLAGS THAT NEVER TOGGLE — filtering on one is a no-op or a fabricated finding. ALWAYS-OFF: tblPlanMaster.IsVerified (14 of 1.28M — the real workflow flag is IsApproved, 148,887 of 173,353 in 2026; never report '0.008% of plans verified'), IsFencyColor (0 ever — fancy here is a SHAPE, Shape LIKE 'F.%'), IsCvd (5 ever — never present '0 CVD' as a natural-vs-lab-grown split), tblPacket.IsOnHold (2 of 168,763 — HOLD IS KAPAN-LEVEL: tblKapan.IsOnHold=1 on 37 kapans covering 11,835 packets), plus IsInTempStock, RFID, SubPcs, IsRepair, PCarat, OrderNo; tblKapan.FPoint/IsMakeable (0 of 853); tblJangad.IsSkipJangad/KapanId/KapanName (0 of 16,498 — kapan is NOT tagged on jangad; trace via tblJangadPackets.PacketId); tblTask.IsComplete/IsCancel (0 of 4,719 — task completion is UNTRACKED, not 0%). ALWAYS-ON (equally dangerous — the filter looks like it narrowed and did not): tblKapan.RequireRoughEst (all 853), tblDepartMent.IsActive (all 92 — derive operating depts from staffing: 62 have an active employee), tblJunk.IsRecyleble (all 209,001 — a default, not a measurement), tblRepairCommentVision.IsApproved (all 4,413 — never report a pending-approval count). tblPacket.Priority has only two values (1 and 3) — a binary flag, not a 1-5 rank; use FifoDate for queue order.",
    "FEEDS THAT STOPPED — a 0 means the FEED died, not that the activity stopped; always state the cutoff. tblLabourResult -> 2023-04-12 (the LIVE labour table is tblPointRateLabour; the dead one has the more obvious name, so name-based table choice is wrong every time). tblPointRateLabour itself -> 2026-07-02, ~25 days behind the backup while the factory ran full-tilt: CAP any tblPointRateLabour query at 2026-06-30 and SAY SO — July returns 206 rows against a ~20,000/month baseline and reads as a 99% production collapse. tblTimeAttendance -> 2025-04-05, and its EmpId is 100% NULL on all 393,882 rows so punches can NEVER be attributed to a named employee. tblEmployeeCount (the most attractive name for 'how many workers') -> 2021-07-23, last value 420 against a true 362 actives — never use it. tblCompanySchedule (shift/holiday calendar) -> 2022-06-30: current holidays are NOT in this database. tblStockIssue/tblStockPurchage (consumables) -> March 2022. tblRepairLog -> 2022-02-19. tblKoted/tblKtdPacket -> 2019-12-09 and the parent row is corrupt — refuse Koting questions. tblAIColorPrediction has NO date column at all, so every 'this year' filter silently returns the all-time blob.",
    "DECOY TABLES — the NAME matches the question, the CONTENT does not. tblRepairLog (657k rows) is a UI CLICK log ('Download File - CLV' 127,931) and dead since 2022. tblRepairLogNew (574k rows) is a generic CRUD audit trail: 'how many repairs in 2025' from it answers 150,706 against a true 3,302 — 46x INFLATED. The ONLY repair register is tblRepairCommentVision (4,413 rows) and its data STARTS 2025-04-08, so any earlier repair volume or year-over-year trend is fabricated; its Reason column is blank — the reason IS RepairComment (Polish 1,906 / Clarity 1,872 / Natural 411). tblDeletedTask (103k rows) is NOT deleted to-dos — it is cancelled PACKET assignments. tblOriginWiseLabour.Origin means PROCESS STAGE ('MFG'/'Marker'), NOT geography — labour-cost-by-rough-origin is not recorded. tblJangadBranch's 54 'branches' are outside VENDOR FIRMS, not GlowStar locations. tblIssuedPacket is the decoy for tblIssuedPacketDetail (1,588 vs 227,143 rows). tblEmployeeTimeAttandance is a GATE-PASS register with seeded 2017 timestamps — never use it for attendance. ZERO ROWS (say the feature was never used, don't return an empty set that reads as 'none'): tblRepairLoss, tblRejection, tblBulkPacket, tblPctIssueConfig, tblJangadDetail, tblJangadMaster, tblStockInventory, tblUserMaster.",
    "INNER JOINS THAT SILENTLY SHRINK THE ANSWER — LEFT JOIN and state the coverage, or the total quietly drops with no error. tblFinalPacket->tblPctChecker covers only 7,662 of 19,263 2026 final packets (39.8%), so an employee-wise production report built on tblPctChecker alone UNDERSTATES every worker by ~60% while looking complete — use tblPacketHistory (Process + EmpId 100% on 2026 rows) or the tblPlanMaster MFG row instead. tblPacket->tblPacketDetail covers 64.7% of 2026 packets (ReportNo only 40.7%), so an inner join reports production a third too low; tblPacketDetail has NO usable date column — scope on tblPacket.CreDate. tblJangad->tblParty on NAME: 25% of Issue jangads have a ToParty with no master row — group on the inline ToParty text and say so. tblLeaveReport->tblEmployee: 13% orphan EmpIDs — join DeptID->tblDepartMent instead (0 orphans). tblKapanValue->tblKapan: 597 orphan rows across 189 KapanIds.",
    "DIMENSIONS THAT MUST BE NORMALISED BEFORE GROUPING. SHAPE: fancy/special variants are SEPARATE values, not sub-types — oval in stock is OV 2,872 + F.OV 4,398 + S.OV 50 = 7,321, so Shape='OV' UNDER-REPORTS BY 61% and F.OV outnumbers plain OV; same for PS/S.PS/F.PS and MQ/S.MQ. Roll the F./S./M variants into the base shape and say you did. tblJangad.Process is FREE TEXT: 'WATER JET' 753 + 'WATER  JET' (DOUBLE SPACE) 1,681 = 2,437, so a raw GROUP BY ranks water-jet 5th instead of 2nd; it also mixes processes with vendor COMPANY names and misspellings — group on UPPER(REPLACE(Process,'  ',' ')) and warn the dimension is dirty. tblEmployee.DepartMentName: 'MFG - 1' HAS SPACES (343 people) while its siblings are 'MFG-2'/'MFG-3', so WHERE DepartMentName='MFG-1' returns 0; and LIKE 'MFG%' misses the 229 people in 'VL MFG-1'/'VL MFG-2'. Match on REPLACE(DepartMentName,' ','') and list the matched names back to the user. tblPlanMaster.Reason: the literal ' |  | ' appears 6,910 times and passes IS NOT NULL — exclude it. tblPlanMaster.Remark: 37,214 of 44,751 non-blank 2026 remarks are machine text ('Auto Copy CLV Plan') — filter NOT LIKE '%Copy CLV Plan%' for the 7,537 genuine human remarks.",
    "STRUCTURAL ZEROS — FILTER BEFORE YOU AVERAGE. Some columns are populated only on the subset of rows where they can apply, so a company-wide AVG divides a real numerator by rows that could never have had a value. tblPacketHistory.WightLoss is recorded ONLY on cutting steps (Laser, Blocking, Blocking Auto, 4P, MFG-2/4) and is structurally 0 on IN Stock, Galaxy, Vision 360, Marker-2, Polish Checker (overall fill 17%) — a whole-table AVG ranks Laser and Blocking near the BOTTOM of 'which process loses the most weight'. Filter WightLoss<>0 or restrict to the cutting processes, or use the packet rollup tblPacket.WeightLoss/JunkLoss. tblPointRateLabour.LossWeight/LossAmount exist in only 3 of 21 departments — a loss-by-department ranking reports 18 departments as perfectly efficient; say they do not record loss rather than showing a 0. tblPointRateLabour also carries 5.04x ROW MULTIPLICITY (110,466 rows / 21,902 distinct Packet_ID in 2026, one row per packet per department per employee): use COUNT(DISTINCT Packet_ID), and de-dup to one row per packet before SUM(Weight) (naive 79,996 ct vs true ~28,904 ct). tblPlanReport.Amount/Rate exist only on the 8.5% of rows with IsDamageReport=1 — always add that filter before summing.",
    "DAMAGE IS POINTS, NOT RUPEES — tblPlanReport.Amount = Points x Rate, a penalty-POINT deduction, NOT money: quoting 'damage cost us Rs 11,537 in 2025' is indefensible in a meeting. Report damage in POINTS (SUM(Points) WHERE IsDamageReport=1: 2023 -8,722 · 2024 -12,418 · 2025 -14,816 · 2026-to-date -6,627, a clearly worsening trend) and in CARATS via WtDiff, and say plainly that a rupee value for damage is not stored. DamageTypeName is NOT a defect taxonomy — its values ('0.25','1','0.50') are penalty MULTIPLIERS; the real cause is free Gujarati text at the front of Description ('jiram padel', 'weight vek', 'purity vek'). IsHolted is NOT a hold state — it is exactly NOT(IsDamageReport) with zero exceptions; use IsPending=1 for genuinely open items (4,217). ClearDate is 100% NULL on damage rows even though 6,141 of 6,142 carry 'Cleared by: SAMD/SAMG' in Description — WHO cleared it is parseable, WHEN is not recorded. GOOD PARTS: Points, PreValue, NewValue, PreWt, NewWt are 100% populated, live to 2026-07-27.",
    "ORIGIN — TWO COLUMNS THAT DISAGREE ON 55% OF KAPANS. tblKapan.Mine (852/853) and RoughOrigin (716/853) agree on only 386 of 853. RoughOrigin is the normalised COUNTRY field; Mine is free text mixing countries (CANADA, ANGOLA), suppliers/channels (DTC, ALROSA, DE BEERS), mines (DIAWIK, EKATI) and junk buckets (OUTSIDE, MIX). CRITICAL FALSE NEGATIVE: WHERE RoughOrigin='RUSSIA' returns 0 rows, but Mine IN ('RUSSIAN','ALROSA') gives 75 kapans / 20,421.78 ct — ALROSA is the Russian state miner. NEVER answer a sanctions or provenance question from RoughOrigin alone. RoughOrigin was also backfilled late (2021 8/16, 2022 92/207, ~100% from 2023), so a multi-year origin trend shows a fake surge into 2023+ that is purely the backfill switching on — restrict RoughOrigin trends to 2023+ or use Mine for earlier years. Always name which column you used, disclose the NULL count, and call out 'MIX' (219 kapans / 69,599 ct) as an unresolved bucket.",
    "COLUMNS THAT ARE GENUINELY GOOD — do NOT refuse these merely because their neighbours are dead. tblKapan.BoilLoss (801 of 853) is the real kapan process loss even though ChapkaLoss has ONE non-zero row. tblJunk.Weight is populated on 208,998 of 209,001 rows and live to 2026-07-27 (2024 18,633 ct · 2025 20,784 ct · 2026-to-date 10,674 ct) — report scrap in CARATS; its Value is 95% zero and Grede 100% NULL. tblPacket.RunningProcess / ProcessStartTime / DepartMentId / EmpId / FifoDate are 100% filled on 2026 rows and ARE the live WIP answer ('where is packet X now', 'how many stuck at Laser', 'how long at this stage') — no need to walk the 5.7M-row tblPacketHistory; note 'IN Stock' means idle stock, so exclude it from 'how many packets are in production'. tblPacketPoint.MarkerPoint/MFGPoint/PolishPoint/GIAPoint are 99.7-100% filled and ARE the piece-rate answer. tblLeaveReport (20,186 rows, live to 2026-07-27) is the ONLY live workforce-presence feed now that biometric attendance is dead — but LeaveTypeID has NO lookup table anywhere, so report codes as NUMBERS and never invent 'sick'/'casual'/'annual'. tblEmployee.JoinDate (81%) is the hiring/tenure feed — CreatDate is NOT a hire date. tblEmployee.OriginType is the workforce SKILL MIX (MFG 1,335, Blocking 279, Marker 242), NOT rough origin.",
    "DEAD COLUMNS — NEVER ANSWER FROM THESE (verified 0-filled across ALL history). "
    "They have useful-sounding names, so querying one returns 0 / blank and reads as a "
    "real answer. Say the figure is NOT RECORDED and offer the live alternative: "
    "(a) tblJangad.RejCarats, LossCarats, RejAmount, LossAmount are ALL zero on every one "
    "of 16,498 rows — there is NO jangad rejection/loss tracking; for 'loss on jangad' say "
    "so, and offer what IS there (packets still out via tblJangadPackets.IsReceived=0). "
    "tblJangad.KapanName is also 100% blank — join tblJangadPackets.PacketId -> "
    "tblPacket.Kapan_ID for the kapan. "
    "(b) tblPacket.IsRepair is NEVER set (0 rows ever) while the real repair register "
    "tblRepairCommentVision holds 4,413 rows — 'how many repaired' from IsRepair returns a "
    "WRONG 0. (c) tblKapan.Labour, InvoiceNo, DollarRate, LabourGrade, ChapkaLoss are "
    "empty — but tblKapan.BoilLoss IS populated (801 of 853 kapans) and is the usable "
    "kapan-loss figure. (d) tblPacket.RoughValue, PCarat, OrderNo and tblPlanReport."
    "IsAutoClear/IsDeductBonus are empty. (e) SubPcs is blank on tblPacket, tblFinalPacket, "
    "tblPlanReport and tblPointRateLabour alike — never count sub-pieces from it.",
    "DEPTH % / RATIO / TABLE % — tblPlanMaster.Depth AND .Ratio ARE CONSTANTS, NOT "
    "MEASUREMENTS: every one of the 173,353 rows in 2026 holds Depth=60.0 and Ratio=1.0 "
    "(ONE distinct value each). They are 100% FILLED, which makes them look usable — they "
    "are placeholders. Averaging them returns a perfectly plausible '60.0% depth, 1.00 "
    "ratio' for EVERY shape including OV/PS/EM, which no one spots by eye. The REAL "
    "measured proportions are on tblPacketParameters (one row per packet, 2,248 distinct "
    "depth values, true average 62.93%): use DepthPer/TablePer/Ratio from THERE, joined by "
    "Packet_ID. Rule this generalises: a column being 100% populated does NOT mean it is "
    "usable — check COUNT(DISTINCT col) before averaging or grouping by anything.",
    "STONE QUALITY ATTRIBUTES on tblPlanMaster — WHICH ARE REAL AND WHICH ARE EMPTY. "
    "The table has ~29 inclusion/finish columns and MOST ARE NEVER FILLED, so a question "
    "about them must say 'not recorded' rather than return a misleading 0. Measured on "
    "June-2026 GIA rows (3,552): USABLE — CutGrade (99%, the "
    "C1..C5 internal cut grade), CrAng + PavAng (58%, crown/pavilion angle RANGES stored "
    "as text like '29.5-40.2'), Diameter (57%, also a text range), Girdle (29%). "
    "EFFECTIVELY EMPTY (<10%) — Brown, Green, Milky, SideBlack, TableBlack, SideWhite, "
    "TableWhite, OpenTable, OpenCrown, OpenPavilion, OpenGirdle, Natural, Culet, EyeClean, "
    "Luster, Tinge, Graining, Shade, HNA, RedSpot, ChipCavity, TablePer. So for 'how many "
    "milky / eye-clean / brown / black-inclusion stones', 'average table %', or any "
    "inclusion breakdown: say that attribute is not recorded in the system and offer what "
    "IS available (the 4Cs, Depth, Ratio, CutGrade, the angle ranges) — NEVER report 0 as "
    "if none exist. NOTE the angle/diameter columns are TEXT RANGES, not numbers: you "
    "cannot AVG them without parsing, so present them as-is. The free-text 'Reason' column "
    "holds the grader's remarks (polish marks, graining, naturals) and IS populated — it "
    "is the closest thing to an inclusion report, but it is prose: quote it, never count it.",
    "MAKER ISSUE — 'FRESH' vs 'CHECK' issue ('maker fresh', 'check issue', 'how many "
    "packets issued to each maker'). The real per-packet log is tblIssuedPacketDetail "
    "(227k rows: PacketID, EmpID -> tblEmployee.ID, IsFresh, CreatedDate). IsFresh=1 = a "
    "FRESH packet issued to the maker (179k rows, LIVE to the data cutoff); IsFresh=0 = a "
    "CHECK issue (48k rows) which STOPPED on 2024-11-19 — zero every month since Dec "
    "2024. So for any recent period 'check issue' is legitimately 0: say the check-issue "
    "flow was discontinued in Nov 2024 rather than reporting 0 as if none happened, and "
    "give the FRESH numbers. Maker-wise pattern: JOIN tblEmployee e ON d.EmpID=e.ID, "
    "GROUP BY e.ID with SUM(CASE WHEN d.IsFresh=1 THEN 1 ELSE 0 END) AS FreshIssued and "
    "the IsFresh=0 counterpart, filtered on d.CreatedDate. TRAP: the header table "
    "tblIssuedPacket (only 1,588 rows: EmpId, PctIssued, CheckIssued, IsLastCheck, "
    "EntryDate) is NOT the issue log and its counters are dead — CheckIssued is 0 in "
    "EVERY year and PctIssued is 0 except 29 in 2026 — never total those columns; always "
    "count rows in tblIssuedPacketDetail instead. (Do not confuse this with "
    "tblPacketIssue, which is the process-stage issue-out log used for the packet "
    "journey.)",
    "WHERE IS THIS DIAMOND / LOCATION — 'where is packet X now', 'is it in Mumbai'. The "
    "ERP tracks location OPERATIONALLY, not geographically. What IS tracked: (a) the "
    "current STAGE/DEPARTMENT inside the factory — tblPacket.RunningProcess + "
    "DepartMentId (see the WIP note); (b) whether it is OUT with a job-work party — "
    "tblJangadPackets.IsReceived=0 joined up to tblJangad.ToParty (the firm holding it) "
    "and JangadDate; (c) its full movement history — tblPacketHistory (Process, EmpId, "
    "ReciveTime) for 'where has it been'. What is NOT tracked: any CITY / BRANCH / OFFICE "
    "location of a packet. The company is Surat-only (tblCompany City='Surat'), every "
    "department is Surat, and all 54 job-work parties are Surat — 'MUMBAI' appears ONLY "
    "as a rough SUPPLIER's city (tblSupplier), never as a packet location, and "
    "tblJangadBranch holds counterparty FIRM names, not branches/cities. So for 'is the "
    "diamond in Mumbai / at the Mumbai office' say plainly that packet location is not "
    "tracked by city — then GIVE the location that IS known: its current stage/department, "
    "or the party it is out with. NEVER infer a city from a party/supplier address.",
    "WIP / IN-PROCESS REPORT ('how many diamonds are being manufactured / in process "
    "and in which department') — this is a LIVE snapshot from tblPacket, one of the "
    "client's core ERP screens. A packet's CURRENT location is tblPacket.RunningProcess "
    "and its assigned department is tblPacket.DepartMentId (both 100% populated; JOIN "
    "tblDepartMent d ON p.DepartMentId=d.ID for the department NAME). 'IN Stock' is the "
    "TERMINAL state = FINISHED goods; everything else is WORK IN PROCESS. So: finished = "
    "RunningProcess='IN Stock' (~152k packets); in process = RunningProcess<>'IN Stock' "
    "(~16.3k packets, ~6.6k ct). Answer department-wise with BOTH measures — SELECT "
    "d.Name AS Department, COUNT(*) AS Packets, SUM(p.CurrentWt) AS Carats FROM tblPacket "
    "p WITH (NOLOCK) LEFT JOIN tblDepartMent d ON p.DepartMentId=d.ID WHERE "
    "p.RunningProcess<>'IN Stock' GROUP BY d.Name ORDER BY Packets DESC — and open with "
    "the overall finished-vs-in-process split so the manager sees the whole picture. "
    "Grouping by RunningProcess instead is also valid (stage-wise rather than "
    "department-wise) and gives nearly the same numbers; say which one you used. This is "
    "a CURRENT-STATE question — do NOT date-filter it and do not ask for a period. NEVER "
    "use tblStockInventory (consumables, not diamonds).",
    "STOCK / YIELD REPORT (the client's format) — their 'stock report' is a KAPAN-WISE "
    "WEIGHT RECONCILIATION. ONE ROW PER KAPAN *IS* THE DETAIL HERE — this is the "
    "exception to 'detail by default': do NOT also list individual packets and do NOT "
    "present a packet list as the stock report (that is a different question: 'which "
    "packets are in stock'). Answer with the kapan rows only, plus a TOTAL row. Columns: "
    "stock weight | current wt | rough wt (rwt) | tops | rejection wt (rej wt) | weight "
    "loss (w loss). Build it from tblPacket (NOT tblFinalPacket, whose RoughWt/WeightLoss/"
    "Tops are 100% NULL): SELECT k.KapanName, SUM(CASE WHEN p.RunningProcess='IN Stock' "
    "THEN p.CurrentWt ELSE 0 END) AS StockWt, SUM(p.CurrentWt) AS CurrentWt, "
    "SUM(p.RoughWt) AS RoughWt, SUM(CASE WHEN p.IsRejected=1 THEN p.RoughWt ELSE 0 END) "
    "AS RejectionWt, SUM(p.WeightLoss) AS WeightLoss, SUM(p.JunkLoss) AS JunkLoss FROM "
    "tblKapan k WITH (NOLOCK) JOIN tblPacket p WITH (NOLOCK) ON p.Kapan_ID=k.ID GROUP BY "
    "k.KapanName — add k.Weight AS KapanRoughWt for the lot's booked rough, and default "
    "to ACTIVE kapans (k.IsFinished=0) for 'current stock', saying so. VERIFIED IDENTITY: "
    "k.Weight ≈ SUM(CurrentWt) + SUM(WeightLoss) + SUM(JunkLoss) (matches within ~1ct on "
    "finished kapans) — that IS the yield reconciliation, so JunkLoss (scrap) belongs in "
    "the report; quote a yield % as SUM(CurrentWt)/k.Weight. TRAPS: SUM(p.RoughWt) EXCEEDS "
    "k.Weight because re-split child packets re-count their parent's rough — for the lot's "
    "true rough always use k.Weight, never SUM(p.RoughWt). WeightLoss is NULL on ~7% and "
    "JunkLoss on ~12% of packets — wrap both in ISNULL(...,0). 'Tops' (the sawn-off top "
    "piece) has NO live weight column — tblFinalPacket.Tops is dead and tblBulkPacket is "
    "empty; the split-off pieces are child packets (tblPacket.Parent_ID set), so report "
    "their weight as the tops proxy AND say it is derived from split packets, or say tops "
    "is not separately recorded — never emit a blank Tops column.",
    "DATA CUTOFF & FRESHNESS — this DB is a RESTORED BACKUP, not live: data ends 2026-07-27 "
    "~12:30 while GETDATE() returns the real clock, so 'today/yesterday' filters can point PAST "
    "the cutoff and return 0 rows — that is staleness, NOT 'no activity'. Never answer 'nothing "
    "happened today'; state the cutoff and answer with the latest available day. Freshness "
    "differs per table — live to the cutoff: tblPacket, tblPlanMaster, tblPacketHistory, "
    "tblPlanReport, tblJunk, tblJangad, tblIncentiveAmount, tblLeaveReport. LAGGING: "
    "tblFinalPacket ends a few days early and skips Sundays (a 2-3 day gap is normal); "
    "tblPointRateLabour is posted IN ARREARS to the last COMPLETE month — a current-month "
    "earnings/bonus query returns a near-zero POSTING GAP: check MAX(ProcessDate) first, report "
    "the covered range, never present the near-zero as final. DEAD: tblTimeAttendance last punch "
    "2025-04-05 (attendance recording STOPPED — say so for any later period); tblLabourResult "
    "ends 2023-04; tblLabourResultGIA 2024-05; tblRepairLog 2022-02. History also STARTS at "
    "different dates: tblPacket/tblPlanMaster/tblKapan 2021-01, tblJangad 2021-07, "
    "tblPointRateLabour 2022-04, tblPlanReport (damage) 2023-01, tblRepairCommentVision 2025-04 "
    "— a zero before a table's start means 'not recorded then', not 'none happened'.",
    "EMPLOYEE ROSTER & IDENTITY — tblEmployee has 2,432 lifetime rows but only 362 IsActive=1: "
    "for headcount/roster DEFAULT to IsActive=1 and say so (unfiltered counts inflate ~7x; dept "
    "7 'Marker' has 134 rows and ZERO active — live markers are Marker-1..4, CL codes). DUMMY "
    "rows named 'EXTRA TRY' / 'EXTRA DUMMY' / 'EXTRA SAMPLE' (Codes 000, M1501, M2501, M3501, "
    "M4501, Y000...) are active AND carry real labour rows — EXCLUDE them from top-worker/roster "
    "answers (e.g. AND e.FirstName <> 'EXTRA') or label them dummy accounts. 'MAIYANI "
    "VIJAYABHAI' is now 10 distinct employees (incl. the sole GIA checker G001 = tblEmployee.ID "
    "5788) — any name lookup MUST disambiguate by Code/ID. One job-work party can be SEVERAL "
    "employee rows across depts (SARJU IMPEX = 4 IDs in 4 departments) — per-ID grouping splits "
    "a party's total; say when you combine them.",
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
    "DAMAGE COUNT — count RECORDS, not kapans, and ALWAYS split by type. "
    "A damage record is ONE ROW in tblPlanReport (one damaged packet/stone "
    "incident); a single kapan usually has MANY damaged packets. So 'how many "
    "damages / damage count / how many damage kapan' = COUNT of ROWS "
    "(records) WHERE IsDamageReport = 1 — NEVER COUNT(DISTINCT KapanName/"
    "KapanID) (that counts kapans, ~20/month, and massively undercounts). "
    "CRITICAL — two types: IsDamageReport = 1 rows carry InceDamageTypeName = "
    "'DAMAGE' or 'REPORT' (master tblInceDamageReportType: 1=DAMAGE, 2=REPORT). "
    "BOTH are genuine stone-damage records, but the client's official 'damage' "
    "figure usually means ONE of the two types — and which one is not yet "
    "confirmed. So for ANY damage count/total, report the OVERALL record count "
    "AND the breakdown by type, e.g. 'June 2026: 159 damage records — 86 DAMAGE"
    "+ 65 REPORT'. NEVER collapse the two into a single unlabelled number, and "
    "never SUM them without showing the split. (The type was only recorded from "
    "2025-07-08; rows before that have InceDamageTypeName NULL, so for earlier "
    "periods just report the total record count and note the split isn't "
    "available.)",
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
    "  - tblPointRateLabour = the CURRENT table (2022-04 onward) — but posted IN "
    "ARREARS, ending at the last COMPLETE month (see the DATA CUTOFF note); check "
    "MAX(ProcessDate) before any current-month figure and never report a near-zero "
    "current month as final. USE"
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
    "DIFFERENT measures: FinalLabour = the ALL-IN net pay per process (verified "
    "identity: LabourAmount + ReportAmount + BonusAmount + DamageAmount + LossAmount, "
    "deductions stored NEGATIVE) — SUM(FinalLabour) ALONE for 'earnings/wages/how much "
    "did an employee make'; BonusAmount = the bonus COMPONENT ALREADY INSIDE "
    "FinalLabour (can be negative) — SUM(BonusAmount) only for 'bonus', and NEVER add "
    "it on top of FinalLabour (double-counts). Negative rows (IsReportLabour=1 "
    "adjustments, damage/loss) are genuine — never filter FinalLabour>0. The 'top "
    "earner' and 'top bonus' lists differ. "
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
    "empty join as if it were the answer. Overall punch counts by date are OK — but "
    "ONLY up to 2025-04-05: the punch feed is DEAD after that (attendance recording "
    "STOPPED Apr 2025); for any later period say so instead of reporting zero. "
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
    "'jangad by party / to whom / which sub-contractor / branch-wise', the party column "
    "depends on TransType: on 'Issue' rows FromParty='GLOW STAR' and ToParty = the "
    "sub-contractor; on 'Receive' rows the returning party is FromParty "
    "(ToParty='GLOW STAR'). So 'jangad by party' = TransType='Issue' GROUP BY ToParty; "
    "returns = TransType='Receive' GROUP BY FromParty — a GROUP BY ToParty over ALL "
    "rows wrongly makes GLOW STAR the top party (JOIN ToPartyId = tblParty.ID for "
    "GST/city). tblJangad.TransType tells DIRECTION: 'Issue' = goods sent OUT, 'Receive' = "
    "goods coming BACK (returns, NOT sales). So header-level 'currently OUT on jangad' = "
    "tblJangad WHERE TransType='Issue' AND IsReceived=0. BUT receives are PARTIAL: a "
    "header stays IsReceived=0 until EVERY line returns, so NEVER SUM header Pcs/Carats "
    "for 'how much is out' (~2x overstatement). Quantity still out = COUNT(*) / "
    "SUM(Carat) FROM tblJangadPackets WHERE IsReceived=0. For 'how many PACKETS are "
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
    # --- Merged from docs/GLOWSTAR_KNOWLEDGE.md §6 (intent words, NEVER data values) ---
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


def render_data_notes(question: str = "") -> str:
    """
    Data notes + value codes + gujlish terms + join hints, as a text block.

    With a `question`, only the notes RELEVANT to it are included (plus the
    always-on safety notes) — see app/schema/note_router. Injecting all of them
    on every turn buried the relevant guidance in ~10k tokens of noise, which is
    what made the same question answer well once and thinly the next time.
    Without a question the full block is returned (tests, offline inspection).
    """
    from app.schema.note_router import select_mapping, select_notes

    data_notes = select_notes(list(DATA_NOTES), question) if question else list(DATA_NOTES)
    join_hints = select_notes(list(JOIN_HINTS), question) if question else list(JOIN_HINTS)
    value_codes = select_mapping(VALUE_CODES, question) if question else dict(VALUE_CODES)
    gujlish = select_mapping(GUJLISH_TERMS, question, max_items=20) if question else dict(GUJLISH_TERMS)

    lines = ["=== DATA NOTES (column spellings & how to filter) ==="]
    for note in data_notes:
        lines.append(f"- {note}")
    if value_codes:
        lines.append("\n=== VALUE CODES (what coded column values mean) ===")
        for name, meaning in value_codes.items():
            lines.append(f"- {name}: {meaning}")
    if gujlish:
        lines.append("\n=== GUJARATI/HINGLISH PHRASES (translate intent, don't match as names) ===")
        for phrase, meaning in gujlish.items():
            lines.append(f"- {phrase}: {meaning}")
    if join_hints:
        lines.append("\n=== TRICKY JOINS (how to apply filters that need another table) ===")
        for hint in join_hints:
            lines.append(f"- {hint}")
    lines.append(
        "\n(Guidance is filtered to your question. If something you need isn't "
        "here, use find_tables/get_table_columns to check the schema directly.)"
    )
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
            "CurrentWt (polished weight), Amount, Lab, "
            "CreateDate, and KapanName. Use this for 'production / output / how many "
            "polished / finished this month'. "
            "ITS WEIGHT COLUMNS RoughWt, WeightLoss AND Tops ARE 100% NULL (all "
            "175,574 rows, including 2026) — they are DEAD: never select them (the "
            "report comes back with blank columns) and never answer a yield/loss/tops "
            "question from here. Only CurrentWt is populated. For rough weight, weight "
            "loss, junk and yield use tblPacket (see the STOCK / YIELD REPORT note). "
            "CAVEATS: its 4Cs are the IN-HOUSE (PLS) grade frozen at entry — the lab "
            "regrades ~55% of certified stones and this table is NOT updated; for what "
            "the LAB said read the tblPlanMaster RapVer='GIA' row. ~24.7k pre-Nov-2023 "
            "PacketIDs have no tblPacket row — LEFT JOIN for historical listings. Lab "
            "is NULL on all pre-2020 rows = 'not recorded', not 'uncertified'. UserID "
            "is ONE data-entry clerk — never use it for 'employee-wise'. Amount is a "
            "small internal valuation unit (avg ~26/packet) — NEVER production value "
            "or revenue."
        ),
        "status": "confirmed",
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
        "note": (
            "THE GRADING PIPELINE — 1.28M rows, one row per packet per STAGE (column "
            "RapVer), keyed Packet_ID = tblPacket.ID; date column CreatDate (note "
            "spelling). Each row carries the stage WORKER (EmpId -> tblEmployee.ID; "
            "EmpName holds the CODE on ~20% of rows — never group by it), the full 4Cs "
            "at that stage (Color, Purity=clarity, Cut, Polish, Symmetry, Florecent, "
            "PolishedWt) plus Rate/Discount/Amount/OAmount, LAB and IsApproved. Stages "
            "in pipeline order (worker code prefix): RST = rough estimation (RE###); "
            "CLV = the marker's ALTERNATIVE cleave plans (CL###, ~2 rows/packet, max 8 "
            "— a bare join DUPLICATES packets; take the IsApproved=1 row or MAX(ID)); "
            "ADM = MRK Admin approval snapshot of the chosen CLV; MKB = the marker's "
            "final MAKEABLE / 'marker approved' plan (exactly 1 row per packet — its "
            "values seed MFG); MFG = the MAKER's plan (M#### = MFG-1..6 karigars, Y### "
            "= Fency job-work firms) — can repeat per packet (revision/handover; 80% of "
            "multi-row packets change worker), the maker of record is the LATEST row "
            "(MAX(ID)); PLS = the Polish Checker's in-house FINAL GRADING (PC###, 1 "
            "row/packet); GIA / HRD / IGI = the LAB RESULT entry (1 row per packet, "
            "mutually exclusive labs, ~7 days after PLS), all entered by ONE person "
            "(G001/HRD001/IGI001 = Maiyani VijayBhai). Rare stages: LSO=Laser, "
            "BLK=Blocking, BRO/DHR/GHS/FourP (<1k each); IGI has only 6 rows EVER and "
            "HRD starts 2026-03 — state the tiny volume, don't treat it as an error. "
            "TRAPS: ApproveDate is NULL on ~96% of GIA and ALL HRD/IGI rows — ALWAYS "
            "date-filter every stage by CreatDate; IsFencyColor is 100% NULL (dead); "
            "Amount = OAmount/15, a scaled internal plan value — NEVER rupees paid; "
            "PacketName IS the display PacketNo; there is NO KapanName column — JOIN "
            "KapanId = tblKapan.ID. Huge table: always WITH (NOLOCK) + a CreatDate "
            "window."
        ),
        "status": "confirmed",
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
            "use tblLabourResult/SubPcs for damage. "
            "COUNTING damages: each ROW is one damage record (one damaged "
            "packet); a kapan has many. So 'how many damages' = COUNT(*) of rows, "
            "NOT COUNT(DISTINCT KapanName/KapanID). InceDamageTypeName splits into "
            "'DAMAGE' and 'REPORT' (both real damage; tblInceDamageReportType "
            "1=DAMAGE, 2=REPORT) — for any count/total report the overall figure "
            "AND the DAMAGE-vs-REPORT split, e.g. GROUP BY InceDamageTypeName. "
            "Do not merge the two types into one unlabelled number. Type is NULL "
            "before 2025-07-08 (not recorded then)."
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
            "MfgEmpId/PolishEmpId = tblEmployee.ID for real names. "
            "WARNING: PARTIAL — covers only ~35-50% of finished packets (near-zero for "
            "uncertified goods), has occasional duplicate PacketId rows, and NEVER "
            "contains Fency workers (MfgEmpCode prefixes only M/V). A missing row is "
            "normal, not 'nobody made it'. The COMPLETE maker source is the packet's "
            "latest tblPlanMaster RapVer='MFG' row (exists for 100% of finished "
            "packets)."
        ),
        "status": "confirmed",
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
            "853 rows; count kapans here. Key columns: KapanName (unique display name — "
            "always show this, never the numeric ID); Weight = the lot's TOTAL carats and "
            "TotalPcs the rough piece count; AvgSize = Weight/TotalPcs = the AVERAGE STONE size in"
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
            "taluka'. NOTE it is sparsely populated — only ~494 of ~2,432 employees (~20%) have a"
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
def render_glossary_text(tables: list[str] | None = None, question: str = "") -> str:
    """
    Business glossary as a compact, LLM-friendly block.

    `tables` limits the per-table notes to the tables actually selected for this
    question. Describing all ~100 tables every turn added ~5k tokens of irrelevant
    text (a jangad-rate note inside an employee question), burying the guidance
    that matters. TERMS are filtered by the question the same way. Passing neither
    returns everything (tests, offline inspection).
    """
    from app.schema.note_router import select_mapping

    lines = ["=== BUSINESS GLOSSARY (diamond manufacturing) ==="]

    terms = TERMS
    if question:
        picked = select_mapping(
            {k: v["definition"] for k, v in TERMS.items()}, question, max_items=14
        )
        terms = {k: TERMS[k] for k in picked} or TERMS
    lines.append("\n-- Industry terms --")
    for term, info in terms.items():
        lines.append(f"- {term}: {info['definition']}")

    if tables:
        wanted = {t.lower() for t in tables}
        notes = {t: i for t, i in TABLE_NOTES.items() if t.lower() in wanted}
    else:
        notes = TABLE_NOTES
    if notes:
        lines.append("\n-- Key tables (business meaning) --")
        for table, info in notes.items():
            lines.append(f"- {table}: {info['note']}")

    return "\n".join(lines)


def table_note(table_name: str) -> str:
    """Return the business note for a table, or '' if we don't have one."""
    info = TABLE_NOTES.get(table_name)
    return info["note"] if info else ""


# Quick manual check: `python -m app.schema.glossary`
if __name__ == "__main__":
    print(render_glossary_text())
