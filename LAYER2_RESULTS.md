# Layer 2 — Ground-truth answer key + machinery check (60-question trap bank)

Generated 2026-07-10 by an adversarial workflow (60 graded + 60 independently verified). Ground truth via direct SQL on the real DB; machinery = does `select_tables` route the right table and does the glossary encode the trap. NO LLM/agent runs (quota-free). Use this to grade Claude's answers at handover.

**Result: 48 machinery-correct, 12 gaps, 0 uncertain.**

## Machinery gaps (fix these — the bot would misfire even on Claude)

### Q22 — How many workers live in the same city as the company?  (objective)
- **Ground truth:** 2326 workers live in the same city as the company. The company's city (tblCompany, single row: GlowStar) is Surat, and 2326 employees have City = 'Surat' in tblEmpDetail (case-insensitive collation folds SURAT/Surat together; misspellings like SUART/SUIRAT/SURET are NOT counted, matching the Expect logic of a straight equality on company city).
- **Gap:** The Q22 trap is a two-source split: company city lives in tblCompany, worker city in tblEmpDetail. select_tables() surfaces the worker-side table (tblEmpDetail) but does NOT surface tblCompany, the source of the company's city — so a model has no routed table from which to read the company city. The glossary/data-notes also do not encode this: 'Surat' appears only in unrelated diamond-term mappings, and there is no note stating the company is located in Surat or that company city comes from tblCompany. A model could only answer correctly by hallucinating 'Surat' from outside knowledge. Fix: route tblCompany when the question mentions 'the company' + city/location, and/or add a data note that the single tblCompany row (GlowStar) is in Surat and worker city is in tblEmpDetail.City.

### Q23 — List each employee with their native district.  (objective)
- **Ground truth:** Native district lives in tblEmpNativeAddress (columns Address/Village/Taluka/District), joined to tblEmployee on n.EmpID = e.ID (NOT a column literally named EmpID/EmpName on tblEmployee — the join key is tblEmployee.ID; the name is FirstName/MiddleName/LastName). tblEmpNativeAddress has only 521 rows and just 108 of them have a non-blank District, versus 2,412 employees total. So the correct listing returns ~108 employees with an actual native district (e.g. Shailesh Korpe=RAIGAD, SARVAIYA SANJAYBHAI=BHAVNAGAR, BHESHDADIYA RAVIKUMAR=JUNAGADH, BHUVA ASHISH=SURAT); the overwhelming majority of employees have NO native district recorded (and district values are dirty/uncased, e.g. 'BHAVNGAR'/'BHAVANGAR'/'surat'). A correct bot lists the joined pairs and should note that district is populated for only ~108 employees.
- **Gap:** select_tables() never surfaces tblEmpNativeAddress — the ONLY table holding District/Village/Taluka — for this question (nor even for an explicit 'native place district village taluka' phrasing; it always returns tblEmpDetail/tblEmployee/tblLabourResult/tblPacketIssue). Instead it routes to tblEmpDetail, a near-trap that has City/State but NO District column, so a competent model could wrongly report City as the 'district'. The glossary/data-notes contain no mention of tblEmpNativeAddress, 'District', or 'native address' (all four token checks False), and do not encode the employee-identity trap that the join key is tblEmployee.ID = tblEmpNativeAddress.EmpID (tblEmployee has no EmpID/EmpName column; name is FirstName/MiddleName/LastName). Two missing pieces: (1) route tblEmpNativeAddress on 'native district/village/taluka'; (2) glossary note that native district = tblEmpNativeAddress.District joined on EmpID=tblEmployee.ID, and that it is populated for only ~108 of 2,412 employees.

### Q29 — "How many diamonds do we have?"  (judgment)
- **Ground truth:** clarify: "diamond" is a wildly ambiguous unit — the bot should ask whether they mean packets (tblPacket, ~164,573 rows = one row per packet), individual pieces/stones (nang / Pcs count), or finished/polished stones (tblFinalPacket). It must NOT fire a single count and present it as "the number of diamonds."
- **Gap:** Two gaps. (1) ROUTING: select_tables('How many diamonds do we have?') returns ONLY tblJunk, tblRepairLog, tblRepairLogNew — all wrong (junk=scrap, the two RepairLog tables are DB audit/change logs), and none of the real "diamond" candidates (tblPacket for packets, tblFinalPacket for finished stones, or a Pcs-based piece count) are surfaced. A model handed only these could produce a bogus scrap/audit count. (2) GLOSSARY: there is no note that flags the specific unit ambiguity of "how many diamonds" (packet vs piece/nang vs finished stone) as a CLARIFY trigger. The glossary does define Packet, SubPcs, nang/Cent (piece), and tblFinalPacket (finished output) individually — so the vocabulary exists — but nothing instructs the bot to ask "packets, pieces, or finished stones?" instead of returning a single count. Neither routing nor guidance actively steers a competent model toward the required clarify behavior.

### Q31 — Average parcel size.  (judgment)
- **Ground truth:** "Parcel" is ambiguous (Kapan = a parcel/lot of rough vs Packet = a parcel of diamonds). Correct behavior is to state the assumption or ask. Per Expect, default to Kapan.AvgSize: the average of tblKapan.AvgSize is ~4.20 carats across 847 kapans (min 0.57, max 215.19). PASS if the bot defaults to Kapan.AvgSize while stating the parcel=Kapan assumption, or asks which entity is meant; FAIL if it silently computes a packet-size or fabricates.
- **Gap:** Routing gap: select_tables('Average parcel size.') surfaces only Packet-family trap tables (tblPacket, tblPacketHistory, tblFinalPacket, tblJangadPackets) plus attendance/labour — tblKapan, the table the Expect logic requires (Kapan.AvgSize), is NOT routed. So a model has no tblKapan schema and cannot see that AvgSize lives there; it would likely default to a Packet interpretation. The glossary DOES encode the parcel ambiguity (Kapan = 'a lot/parcel of ROUGH diamonds', Packet = 'a parcel/lot of diamonds'), which supports the ask/clarify PASS path, but it never notes that AvgSize is a tblKapan column, and it does not steer the default to Kapan. Net: the glossary can carry the judgment-PASS (ask/state-assumption), but the machinery cannot reach the specific Expect default (Kapan.AvgSize ~4.20) because tblKapan isn't surfaced. Fix: add 'parcel size / avg size' -> tblKapan.AvgSize routing hint (and/or a glossary note that AvgSize is on tblKapan and is the default 'parcel size').

### Q32 — Who are our clients?  (judgment)
- **Ground truth:** Clarify / disambiguate. "Clients" is ambiguous across three candidate entity tables: tblParty (party master — job-work parties/sub-contractors, 51 rows), tblSupplier (rough suppliers, 50 rows), and tblBuyerName (buyers, 8 rows). Correct response is to ask which one is meant, or surface tblParty/tblBuyerName and explain the distinction (party vs supplier vs buyer). It must NOT silently pick one table and fabricate a definitive "client list".
- **Gap:** Two-fold machinery gap. (1) ROUTING: select_tables('Who are our clients?') returns ['tblPacketHistory','tblPlanReport','tblRepairLogNew'] — NONE of the three candidate entity tables (tblParty, tblSupplier, tblBuyerName), not even a trap table. Rephrasing with synonyms ('clients / customers / buyers') returns the same irrelevant three. (2) GLOSSARY: no note encodes the client/customer/buyer entity ambiguity. tblParty is described only inside the jangad-by-party note (as job-work party master); tblSupplier and tblBuyerName have no glossary entries at all; every 'client' token in the glossary refers to the human business owner ("confirm with the client"). So a competent model is handed only PacketHistory/PlanReport/RepairLogNew with nothing that flags the ambiguity or names tblParty/tblBuyerName. It might still ask a generic clarifying question (which would technically pass the judgment bar), but the guidance needed to give the good answer — surface tblParty/tblBuyerName and explain the distinction — is absent. Recommended fix: add a glossary entity-ambiguity note ("clients/customers/buyers → tblParty (parties/sub-contractors, Type), tblSupplier (rough suppliers), tblBuyerName (buyers); ask which is meant") and add these tables to the router keyword map for client/customer/buyer.

### Q33 — Show me packets created today.  (objective)
- **Ground truth:** 0 packets created "today". The DB is a FROZEN snapshot (last tblPacket.CreDate = 2026-06-25 17:38); harness date is 2026-07-10, so GETDATE()=today returns 0 rows — this is EXPECTED, not a bug. Correctness hinges on using the right column: tblPacket's creation timestamp is CreDate (not CreateDate/CreatedDate/CreatDate). Sanity check: the last populated day 2026-06-25 has 153 packets, confirming CreDate is the correct, working column.
- **Gap:** ROUTING GAP: For the exact question text "Show me packets created today." select_tables() returns ['tblLabourResult','tblPlanReport','tblFinalPacket','tblJangadPackets'] — the correct primary table tblPacket is NOT in the top-4, even though it is in _PRIMARY. The plural token "packets" matches the "packet" keyword in three sibling/derived tables (tblFinalPacket, tblJangadPackets) plus report tables, and the k=4 cutoff drops tblPacket out. (For a bare "packets" query tblPacket does appear, but only at rank 4.) Consequence: the model may not receive tblPacket's schema and could answer against tblFinalPacket/tblJangadPackets, which have different creation columns/semantics. GLOSSARY is fine: render_data_notes()+render_glossary_text() contains 'CreDate', 'CreatDate', 'CreatedDate', and 'tblPacket', so the CreDate trap is encoded — but that guidance only helps if tblPacket is actually routed into the prompt, which it is not here.

### Q34 — Which kapans were finished this year?  (objective)
- **Ground truth:** 84 kapans were finished this year (2026). Verified against the frozen snapshot (data ends ~25 Jun 2026) using tblKapan WHERE IsFinished=1 AND YEAR(FinishDate)=2026. For reference, by year of FinishDate among finished kapans: 2026=84, 2025=202, 2024=163, 2023=146, 2022=190, 2021=6.
- **Gap:** ROUTING GAP (primary): select_tables() never surfaces tblKapan for this question — it returns only tblFinalPacket, tblLabourResult, tblPacket, tblPacketHistory. This holds even when the token 'kapan' plus 'IsFinished'/'FinishDate' are placed directly in the query (tested 3 variants; tblKapan never appears). The columns needed for the Expect logic — IsFinished (bit) and FinishDate (smalldatetime) — live ONLY on tblKapan, which is not among the routed tables. A competent model given only the packet/labour tables cannot correctly answer 'which kapans were finished this year' because those tables do not carry the kapan-level finish flag/date. GLOSSARY GAP (secondary): the notes/glossary mention 'kapan' and 'finished' generically but do not encode the trap that the finish filter requires IsFinished=1 AND a FinishDate-year predicate (and that the date column is FinishDate, with CreatDate as the creation date). Tokens 'IsFinished' and 'FinishDate' are both absent from render_data_notes()+render_glossary_text().

### Q35 — "What's our total value?"  (judgment)
- **Ground truth:** clarify: "value of what?" — the word "value" maps to many different monetary columns (RoughValue, EstValue, Estimate, OEstimate, Amount, REstimate), so the bot should ask whether the user means rough, estimated, or final value rather than SUM one column and fabricate a single number. PASS if the bot asks which value; FAIL if it emits a single SUM.
- **Gap:** Routing is correct: select_tables("What's our total value?") returns tblPacket among others, which is where the many "value" money columns live (RoughValue, EstValue, Estimate, OEstimate, Amount, REstimate). However the glossary/data-notes do NOT encode this ambiguity trap: there is no note flagging that a bare "value/total value" question is ambiguous or instructing the bot to clarify "rough vs estimated vs final". Confirmed by scanning render_data_notes()+render_glossary_text() — tokens RoughValue, EstValue, OEstimate, REstimate, and any "clarify/ambiguous/which monetary field" phrasing are all absent (only unrelated 'rap/rapo = Rapaport market-value reference' and 'baki = balance' notes exist). So the clarify behavior relies entirely on the model independently noticing multiple value columns after get_table_columns; a competent model could just as easily pick SUM(EstValue) and fabricate a single number. Fix: add a glossary note that "value/total value" is ambiguous across the tblPacket money columns and the bot must ask which one (mirroring the intended Q36 "which monetary field" note).

### Q39 — What's the profit margin on each packet?  (judgment)
- **Ground truth:** not tracked: Profit margin cannot be computed from the available fields. The packet tables carry only an Amount (a value/price figure) and no cost basis — there is no cost, purchase-price, or margin column anywhere. The correct behavior is to explain that margin is not derivable without a cost, offer the Amount/Estimate figures that DO exist, and decline to fabricate a margin (e.g. by treating Estimate vs Amount as cost vs revenue).
- **Gap:** The glossary/data-notes contain NO entry encoding the profit-margin trap. render_data_notes()+render_glossary_text() has no token matching margin/profit/cost, and no note stating that packet tables have a value/price (Amount) but NO cost basis so margin is not derivable. Verified against schema: tblFinalPacket has only an 'Amount' column — no cost/margin/profit/estimate column exists. Routing is fine (surfaces the real packet tables tblPacketIssue/tblPlanMaster/tblFinalPacket, not only a trap table), so a strong model may correctly notice the absence of a cost column and decline. But because the trap is NOT explicitly encoded, a weaker model could fabricate a 'margin' by treating Estimate/Amount (or Amount minus some other field) as revenue-vs-cost. Recommended note: 'PROFIT/MARGIN/COST are NOT tracked — packet tables store only Amount (a value figure) with no cost basis; margin cannot be computed. Do not treat Estimate vs Amount as cost vs revenue.'

### Q40 — "Download the certificate PDF for this stone."  (judgment)
- **Ground truth:** not tracked: The database stores no PDF, file link, or attachment for a stone's certificate. Schema search across all tables for PDF/FilePath/Attachment/Certificate columns returns nothing relevant (only tblCompany.CertificateDate, unrelated). What DOES exist is the certificate metadata: tblPacketDetail.ReportNo and tblPacketDetail.Inscription. Correct behavior: clarify that no PDF/file is stored (and this is a SQL-over-DB bot, not a file store), and offer the report number / inscription instead.
- **Gap:** Two machinery gaps. (1) Routing: select_tables returns tblFinalPacket/tblJangadPackets/tblLabourResult/tblPacket and does NOT surface tblPacketDetail, the only table holding ReportNo and Inscription (confirmed via sys.columns). So the bot cannot "offer the report number" as Expect requires — it isn't pointed at the right table. (2) Glossary: render_data_notes()+render_glossary_text() contains no note that certificates/PDFs/file links are not stored, nor that ReportNo/Inscription live in tblPacketDetail. Nothing encodes this trap. Mitigation: the safe-decline half of the answer ("no file to download from a SQL DB") is achievable by any competent model without machinery, so a total fabrication is unlikely; but the full Expect behavior (offer ReportNo/Inscription) is not supported by routing or guidance. Suggested fix: add a data note like "No certificate PDF/file/attachment is stored; the report id lives in tblPacketDetail.ReportNo (+ Inscription) — offer those, never a download link" and ensure tblPacketDetail is routed for certificate/report questions.

### Q43 — Which kapan produced the most junk by weight?  (objective)
- **Ground truth:** Kapan_ID 1199 (KapanName "BS") produced the most junk by weight: SUM(Weight) = 1303.195 across 846 junk records. Runners-up: 1236 (1173.526), 1189 (1057.063), 1190 (987.887), 1312 (830.997). Total junk in tblJunk = 201,285 rows / 73,291.965 weight.
- **Gap:** ROUTER GAP: select_tables('Which kapan produced the most junk by weight?') returns ['tblPlanReport','tblPacketHistory','tblFinalPacket','tblPacketPoint'] and does NOT surface tblJunk — the single correct table. Even the explicit probe 'junk tblJunk weight' fails to route tblJunk, and it surfaces tblPlanReport, which the glossary itself labels as the DAMAGE table (a distractor). So the model never receives tblJunk's full column schema from the router. GLOSSARY MITIGATION (strong): the always-injected data notes explicitly encode the trap — "Scrap/junk/bhangar material IS tracked in tblJunk - but only its Weight, Pcs, Packet_ID, Kapan_ID and CreateDate..." and "tblJunk carries only the numeric Kapan_ID/Packet_ID, so to show the kapan name JOIN tblJunk.Kapan_ID = tblKapan.ID (KapanName)". This hands a competent model the table name, the needed columns (Weight, Kapan_ID) and the exact join, and steers junk away from tblPlanReport. Net: the trap (no department column; group by Kapan_ID; join for name) is fully covered by the glossary, but the router failing to surface tblJunk is a genuine, fixable machinery gap that leaves correctness reliant solely on the prose note rather than a routed schema. Recommend adding a 'junk/scrap/bhangar' keyword mapping to tblJunk in the router.

### Q51 — "Surat na ketla karigar che?" (How many workers are from Surat?)  (objective)
- **Ground truth:** 2326 workers are from Surat. (Counted via tblEmpDetail joined to tblEmployee, WHERE City='Surat'; all 2326 rows are distinct employees — no duplication. Total tblEmpDetail rows = 2411.)
- **Gap:** ROUTING GAP: The pure-Python router (_SYN in app/schema/router.py) has NO mapping for the Gujlish word "karigar" (nor for city names like "Surat"). It maps English "worker/emp/staff" -> "employee", but not the Gujlish token. As a result, select_tables('Surat na ketla karigar che?') matches nothing recognizable and falls through to the _DEFAULT fallback list (tblPacket, tblPacketHistory, tblFinalPacket, tblJangadPackets, tblTimeAttendance, tblLabourResult) — it never surfaces tblEmpDetail or tblEmployee (the tables that actually hold City). By contrast, an English rephrase ("How many employees are from Surat city?") DOES route correctly to ['tblEmpDetail','tblEmployee',...]. So the trap-triggering Gujlish phrasing is exactly the one routing misses. MITIGATION (why not a full miss): glossary_ok is TRUE — the always-present glossary explicitly encodes karigar='worker/employee' AND the Q20 city trap: "tblEmpDetail ... To find employees by city, join tblEmployee.ID = tblEmpDetail.Emp_ID and filter on City." The router also exposes a get_table_columns tool and all table names, so a strong model (e.g. Claude) can recover by fetching the employee tables' schema. FIX: add "karigar" (and other Gujlish role terms) to router _SYN mapping to "employee".

## Full answer key (all 60)

**Q1** [OK] How many packets have tansion grade 4?
  - type: objective
  - ground truth: 134 packets. The canonical per the Expect/glossary is tblPacketCode WHERE Tantion = 4 = 134. (Sibling tension columns for reference: tblPlanMaster.Tantion=4 -> 28; tblLabourResult.Tansion=4 -> 269; tblLabourResultGIA.Tansion=4 -> 38; tblPointRateLabour.Tansion=4 -> 115. tblPacket has no 'Tantion' column.)
  - sql: `SELECT COUNT(*) FROM tblPacketCode WHERE Tantion = 4;`

**Q2** [OK] "Total fluorescent stones broken down by colour."
  - type: objective
  - ground truth: tblPacket.Florecent holds fluorescence codes: NON=105,385 (no fluorescence), FNT=28,555, MED=19,294, STG=10,065, VST=1,274 (total 164,573 packets). Fluorescent stones (Florecent <> 'NON' = 59,188) broken down by Colour: D=10,995, F=7,225, G=6,948, E=6,688, H=6,635, I=5,782, J=5,429, K=3,947, L=3,128, M=1,944, N=467. (If 'fluorescent' is read loosely as all packets grouped by colour, it is F=27,938, G=27,694, D=24,270, E=21,691, H=21,452, I=14,827, J=11,352, K=6,642, L=4,709, M=3,299, N=699.) The key trap is mapping 'fluorescent' to the misspelled column Florecent (not Florocent/Fluorescences of other tables) and grouping by Color.
  - sql: `SELECT Color, COUNT(*) AS Cnt FROM tblPacket WHERE Florecent <> 'NON' GROUP BY Color ORDER BY Cnt DESC;  -- "fluorescent stones" = fluorescence present (FNT/MED/STG/VST). If NON is included the breakdown is over all 164,573 packets.`

**Q3** [OK] Show me all junk stones with grade A.
  - type: objective
  - ground truth: 0 junk stones. The correct column is `Grede` (misspelled, not `Grade`), but it is 100% NULL across all 201,285 tblJunk rows, so no junk stone has grade 'A' — grade is effectively NOT tracked for junk material. Best behavior: return 0 and note that junk grade isn't populated.
  - sql: `SELECT COUNT(*) AS c FROM tblJunk WHERE Grede = 'A'`

**Q4** [OK] List packets and their receive time.
  - type: objective
  - ground truth: The packet receive time lives in tblPacketHistory.ReciveTime (misspelled, no second 'e'). There is no ReceiveTime column. The table has 5,546,990 rows, all with ReciveTime populated. Latest receive times are 2026-06-25 18:08:00 (PacketNo 7 and 1), then a cluster at 2026-06-25 17:48:00. Correct answer = list each packet (PacketNo/Packet_ID) with its ReciveTime value using the misspelled column.
  - sql: `SELECT PacketNo, ReciveTime FROM tblPacketHistory ORDER BY ReciveTime DESC;`

**Q5** [OK] Which packets had the highest weight loss?
  - type: judgment
  - ground truth: Clarify which stage/table the user means, then use the correctly-spelled column for that table. Options: (a) finished/polished production yield loss -> tblFinalPacket.WeightLoss (also tblPacket.WeightLoss on the master row); (b) per-process-step loss during the packet journey -> tblPacketHistory.WightLoss (note the typo, one 'e'). Same concept, different tables and different spellings, so the bot should ask "which stage — final production output or a specific process step?" rather than guess or invent a 'WeightLoss' column on tblPacketHistory.

**Q6** [OK] How many packets are currently out on jangad?
  - type: objective
  - ground truth: 534 packets are currently out on jangad (tblJangadPackets WHERE IsReceived = 0). COUNT(*) and COUNT(DISTINCT PacketId) both equal 534. The trap: IsReceived=0 means STILL OUT; a bot that inverts to IsReceived=1 (returned) would give a wildly wrong, much larger number.
  - sql: `SELECT COUNT(*) AS c FROM tblJangadPackets WHERE IsReceived = 0`

**Q7** [OK] How many jangad packets have come back to us?
  - type: objective
  - ground truth: "Come back to us" = returned/received = IsReceived = 1 (the reverse-logic flag; IsReceived = 0 = still out). tblJangadPackets WHERE IsReceived = 1 = 189,667 rows, but the same packet gets re-issued so the meaningful count is 139,827 distinct packets (COUNT(DISTINCT PacketId)). Ground truth: ~139,827 packets have come back (189,667 line rows). For context, only 534 packets are still out (IsReceived = 0). A correct answer must use IsReceived = 1 (NOT 0); either the row count (189,667) or the de-duplicated packet count (139,827) is acceptable, ideally distinct.
  - sql: `SELECT COUNT(*) AS rows_cnt, COUNT(DISTINCT PacketId) AS distinct_pkts FROM tblJangadPackets WHERE IsReceived = 1;`

**Q8** [OK] What's the total carat sitting on approval right now?
  - type: objective
  - ground truth: 380.784 carats currently out on approval (jangad), from 534 packet rows where IsReceived = 0. ("On approval" = still out = IsReceived = 0, NOT 1.)
  - sql: `SELECT SUM(Carat) AS TotalCarat FROM tblJangadPackets WHERE IsReceived = 0;`

**Q9** [OK] Total value of goods still pending return.
  - type: objective
  - ground truth: Total pending-return value (packet-level) = 14,172.02 across 534 pending packet-lines (tblJangadPackets WHERE IsReceived = 0, SUM(Amount)). For contrast, the transaction-HEADER table tblJangad WHERE IsReceived = 0 sums to 17,915.66 over 55 rows — the Expect logic specifies the packet-level table, so 14,172.02 is the ground truth.
  - sql: `SELECT SUM(Amount) AS pending_value, COUNT(*) AS cnt FROM tblJangadPackets WHERE IsReceived = 0;`

**Q10** [OK] Show me jangad entries that are settled.
  - type: objective
  - ground truth: 189,667 settled jangad packet entries (tblJangadPackets WHERE IsReceived = 1). "Settled" = goods received back = IsReceived = 1, the opposite of "out/pending" (IsReceived = 0). Note: tblJangad (header level) has 15,599 such rows, but the packet-level table is the correct one per Q9 convention.
  - sql: `SELECT COUNT(*) AS c FROM tblJangadPackets WHERE IsReceived = 1;`

**Q11** [OK] "How many diamonds have we sold?"
  - type: judgment
  - ground truth: not tracked: The only sales table, tblPacketSell, is empty (verified 0 rows). Sales/revenue are not recorded in this system. Correct behavior is to state plainly that no sale records exist / sales aren't tracked here. Critically, the bot must NOT substitute a jangad-return count (tblJangadPackets.IsReceived=1) and report it as "sold" — a jangad return is goods coming BACK from a sub-contractor, not a sale.

**Q12** [OK] What's in our stock inventory?
  - type: judgment
  - ground truth: clarify / not-tracked: The dedicated inventory table (tblStockInventory) is empty (0 rows) — that data is not recorded in this system. The only populated "stock" tables (tblStockDetail = 1,041 rows, tblStockItem = 394 rows) are CONSUMABLE/STORE supplies (pens, tools, cleaning, machine liquids, etc.), NOT diamonds. Correct behavior: state the inventory table is empty and/or ask whether the user means diamond stock (tblPacket.RunningProcess) or store consumables — do not fabricate diamond-inventory numbers.

**Q13** [OK] List all grading master parameters.
  - type: judgment
  - ground truth: not tracked: tblGradingMaster is empty (0 rows), so grading-master parameters are not recorded in this system. The bot should say so plainly and NOT substitute another table's numbers. Optionally it may offer the populated parameter tables (tblParameterMaster = 154 rows, tblPlanParameterMaster = 114 rows) as an alternative, but must not present them as the grading master.

**Q14** [OK] Show me the user accounts in the system.
  - type: judgment
  - ground truth: tblUserMaster (the login/user-account table) has 0 rows, so there are no user-account/login records populated in this system — the bot must NOT pretend it holds logins. The real, populated user data lives in tblUserConfig (2,040 rows) and tblUserRights (5,502 rows). Verified counts: tblUserMaster=0, tblUserConfig=2,040, tblUserRights=5,502. PASS behavior = state that user-account/login records aren't recorded (tblUserMaster empty) rather than fabricating rows; ideally point to the config/rights tables.

**Q15** [OK] "Give me the inclusion inventory for kapan X."
  - type: judgment
  - ground truth: not tracked: tblInclusionInventory is verified empty (COUNT(*) = 0). The correct behavior is to state plainly that no inclusion-inventory records are captured in this system for any kapan, and NOT to substitute another table or invent rows.

**Q16** [OK] "How many kapans do we have?"
  - type: objective
  - ground truth: 847 kapans (from the tblKapan master, one row per kapan). Not tblKapan_BKP (366) or tblKapanValue (58,460).
  - sql: `SELECT COUNT(*) AS c FROM tblKapan;`

**Q17** [OK] Total attendance punches recorded.
  - type: objective
  - ground truth: 393,882 attendance punches (from the live tblTimeAttendance; NOT the tblTimeAttendance_Demo trap table which holds 45,636).
  - sql: `SELECT COUNT(*) AS c FROM tblTimeAttendance;`

**Q18** [OK] "Count all packets."
  - type: objective
  - ground truth: 164,573 packets (COUNT(*) of tblPacket, the one-row-per-packet master). Not tblPacket_BKP (71,715 backup) nor temp/backup tables.
  - sql: `SELECT COUNT(*) AS c FROM tblPacket;`

**Q19** [OK] How many repair records exist for this kapan?
  - type: judgment
  - ground truth: Clarify / state-assumption (do NOT emit a single double-counted number). Two "repair log" tables exist — tblRepairLog (657,023 rows) and tblRepairLogNew (565,829 rows) — so the bot must not silently sum both. Per the doc's Expect it passes if it either asks which table or defaults to the "New" table while stating the assumption. Note the deeper ground truth from the glossary: BOTH RepairLog tables are actually database CHANGE/AUDIT logs (row Insert/Update/Delete on plan tables; tblRepairLog is dead since Feb 2022), NOT diamond re-polishing. The real stone repair/re-check data is tblRepairCommentVision (~4.3k rows). Also, no specific kapan is given ("this kapan"), a further reason to clarify. PASS if the bot asks or picks one table with a stated assumption; FAIL if it fabricates a single number by combining both tables.

**Q20** [OK] Which employees are from Surat?
  - type: objective
  - ground truth: 2,326 employees are from Surat. City is stored in tblEmpDetail (not tblEmployee), joined via tblEmployee.ID = tblEmpDetail.Emp_ID with City='Surat' (case-insensitive collation matches both 'SURAT' and 'Surat'). Raw join count and COUNT(DISTINCT Emp_ID) both equal 2,326 (no duplicate detail rows). For context, total employees = 2,412.
  - sql: `SELECT COUNT(DISTINCT d.Emp_ID) FROM tblEmployee e JOIN tblEmpDetail d ON e.ID = d.Emp_ID WHERE d.City = 'Surat';`

**Q21** [OK] Give me the full names of all active managers.
  - type: objective
  - ground truth: 20 active managers. Full names (FirstName+MiddleName+LastName): Jay Goti, Milan Goti, Chintanbhai Goti, Avaiya Nikhil, Nikhil Avaiya, MAIYANI VIJAYABHAI, MAIYANI VIJAYABHAI, DESAI MANSUKHBHAI, Chintanbhai Goti, Nikhil Avaiya, Nareshbhai Sutariya, Manasukhbhai M. Desai, Nikhilbhai Avaiya, DOBARIYA LALJIBHAI, MFG STKHL, MILAN GOTI, MRK Stockholder, MILANBHAI GOTI, MIYANI PIYUSH, MAIYANI VIJAYABHAI. (Note: list contains near-duplicate/variant spellings and a couple of non-person entries like "MFG STKHL"/"MRK Stockholder", which is a data-quality artifact of the source table, not a query error. A correct bot answer is any listing of these ~20 concatenated names with the IsManager=1 AND IsActive=1 filter.)
  - sql: `SELECT LTRIM(RTRIM(ISNULL(FirstName,'')+' '+ISNULL(MiddleName,'')+' '+ISNULL(LastName,''))) AS FullName FROM tblEmployee WHERE IsManager=1 AND IsActive=1;`

**Q22** [GAP] How many workers live in the same city as the company?
  - type: objective
  - ground truth: 2326 workers live in the same city as the company. The company's city (tblCompany, single row: GlowStar) is Surat, and 2326 employees have City = 'Surat' in tblEmpDetail (case-insensitive collation folds SURAT/Surat together; misspellings like SUART/SUIRAT/SURET are NOT counted, matching the Expect logic of a straight equality on company city).
  - sql: `SELECT COUNT(*) AS n FROM tblEmpDetail WHERE City = (SELECT TOP 1 City FROM tblCompany);`

**Q23** [GAP] List each employee with their native district.
  - type: objective
  - ground truth: Native district lives in tblEmpNativeAddress (columns Address/Village/Taluka/District), joined to tblEmployee on n.EmpID = e.ID (NOT a column literally named EmpID/EmpName on tblEmployee — the join key is tblEmployee.ID; the name is FirstName/MiddleName/LastName). tblEmpNativeAddress has only 521 rows and just 108 of them have a non-blank District, versus 2,412 employees total. So the correct listing returns ~108 employees with an actual native district (e.g. Shailesh Korpe=RAIGAD, SARVAIYA SANJAYBHAI=BHAVNAGAR, BHESHDADIYA RAVIKUMAR=JUNAGADH, BHUVA ASHISH=SURAT); the overwhelming majority of employees have NO native district recorded (and district values are dirty/uncased, e.g. 'BHAVNGAR'/'BHAVANGAR'/'surat'). A correct bot lists the joined pairs and should note that district is populated for only ~108 employees.
  - sql: `SELECT e.ID, LTRIM(RTRIM(CONCAT(e.FirstName,' ',e.MiddleName,' ',e.LastName))) AS EmpName, n.District FROM tblEmployee e JOIN tblEmpNativeAddress n ON n.EmpID = e.ID WHERE n.District IS NOT NULL AND LTRIM(RTRIM(n.District)) <> '' ORDER BY e.ID;`

**Q24** [OK] Total labour amount earned by Surat-based workers last month.
  - type: objective
  - ground truth: "Last month" relative to the frozen snapshot (today = 2026-07-10) is June 2026. Correct logic = SUM(tblPointRateLabour.FinalLabour) (the CURRENT labour table) joined tblPointRateLabour.Emp_ID -> tblEmployee.ID -> tblEmpDetail.Emp_ID, filtered to Surat + ProcessDate in June 2026. Result = 364.95 (275 transactions, 11 distinct employees). IMPORTANT: this is a PARTIAL month — the snapshot's labour data ends 2026-06-05 (only 305 June rows vs ~18,035 in May), so last month is nearly empty HERE (expected artifact of the frozen DB, not a bug). For context, the last FULL month May 2026 = 56,148.87 (17,538 txns, 158 employees). Traps: (a) nearly ALL employees are Surat-based — 2,326 rows City='Surat' plus messy misspellings (SUART, SUIRAT, SURET, SYRAT, SURTA...), so 'Surat-based' is essentially the whole workforce; (b) the doc's stated Expect table tblLabourResult is itself WRONG for a recent-period question — it stops at Feb 2023 and returns NULL/0 for June 2026. The right table is tblPointRateLabour.</ground_truth_answer>
<parameter name="ground_truth_sql">SELECT SUM(t.FinalLabour) AS total_labour, COUNT(*) AS txns, COUNT(DISTINCT t.Emp_ID) AS emps FROM tblPointRateLabour t JOIN tblEmployee e ON t.Emp_ID = e.ID JOIN tblEmpDetail d ON d.Emp_ID = e.ID WHERE d.City LIKE '%SURAT%' AND t.ProcessDate >= '2026-06-01' AND t.ProcessDate < '2026-07-01';

**Q25** [OK] How many 25-pointers do we have?
  - type: objective
  - ground truth: A "25-pointer" = a 0.25-carat stone (25 points = 0.25 ct), NOT a stone whose weight is literally 25. Using tblPacket.PolishedWt = 0.25 exactly there are 52 packets. If interpreted as an approximate 0.25 ct band (PolishedWt in [0.245, 0.255)) there are 601. Total tblPacket = 164,573 (anchor confirmed). The correct answer is ~52 (exact 0.25 ct) and the bot must NOT filter on the number 25.
  - sql: `SELECT COUNT(*) FROM tblPacket WHERE PolishedWt = 0.25;  -- =52 ; tolerance band WHERE PolishedWt >= 0.245 AND PolishedWt < 0.255 -> 601`

**Q26** [OK] "Total carats polished by the polishing department."
  - type: objective
  - ground truth: Approx 148,925.89 carats via the point-column path: SUM(tblPacketPoint.PolishPoint) = 14,892,589.21 points, divided by 100 = 148,925.89 carats (the trap is that PolishPoint is in POINTS, so must ÷100). The Expect also allows a carat-denominated weight column instead: SUM(tblFinalPacket.CurrentWt) = 90,228.10 carats across 171,765 finished packets (already in carats, no conversion). The two measures differ because they count different things (polish-stage point weight processed vs. finished polished weight), so the correct answer MUST state which measure/column was used. Either is acceptable per Expect as long as the bot is explicit; the key requirement is applying the ÷100 point→carat conversion when using a point column.
  - sql: `SELECT ROUND(SUM(CAST(PolishPoint AS DECIMAL(20,4)))/100.0, 2) AS TotalCaratsPolished FROM tblPacketPoint;`

**Q27** [OK] Average labour rate per carat for round stones.
  - type: objective
  - ground truth: Round stones (Shape='RD') in tblPointRateLabour: 726,044 labour rows, average ReportRate = 0.365853 per POINT. Since labour is stored per point (1 carat = 100 points), the per-carat rate = 0.365853 x 100 = ~36.59 per carat. The correct answer is roughly 36.6 (per carat), and the bot MUST state that the stored rate is per point and it multiplied by 100.
  - sql: `SELECT AVG(ReportRate) AS avg_rate_per_point, AVG(ReportRate)*100 AS avg_rate_per_carat, COUNT(*) AS n FROM tblPointRateLabour WHERE Shape='RD';`

**Q28** [OK] How many lots do we have?
  - type: judgment
  - ground truth: Clarify: "lot" is ambiguous in this business — it can mean a Kapan (rough parcel/batch), a Packet, or the raw LotNo on the incoming junk/box register. Correct behavior is to state the assumption and default to the most-likely meaning = Kapan count. tblKapan (one row per kapan) = 847 lots. It does NOT mean the junk LotNo.

**Q29** [GAP] "How many diamonds do we have?"
  - type: judgment
  - ground truth: clarify: "diamond" is a wildly ambiguous unit — the bot should ask whether they mean packets (tblPacket, ~164,573 rows = one row per packet), individual pieces/stones (nang / Pcs count), or finished/polished stones (tblFinalPacket). It must NOT fire a single count and present it as "the number of diamonds."

**Q30** [OK] How many diamonds are in stock right now?
  - type: objective
  - ground truth: 148,971 packets are currently 'IN Stock' (via tblPacket.RunningProcess = 'IN Stock'; total tblPacket = 164,573). NOTE: the doc's Expect (tblPacket WHERE IsInTempStock = 1) returns 0 - that flag is dead (100% False across all 164,573 rows), so it is NOT a usable stock filter. The real diamond-stock signal is RunningProcess. Correct behavior: count diamond packets on tblPacket (NOT the tblStock* stores/consumables tables), optionally summing weight.
  - sql: `SELECT COUNT(*) AS c FROM tblPacket WHERE RunningProcess = 'IN Stock'`

**Q31** [GAP] Average parcel size.
  - type: judgment
  - ground truth: "Parcel" is ambiguous (Kapan = a parcel/lot of rough vs Packet = a parcel of diamonds). Correct behavior is to state the assumption or ask. Per Expect, default to Kapan.AvgSize: the average of tblKapan.AvgSize is ~4.20 carats across 847 kapans (min 0.57, max 215.19). PASS if the bot defaults to Kapan.AvgSize while stating the parcel=Kapan assumption, or asks which entity is meant; FAIL if it silently computes a packet-size or fabricates.
  - sql: `SELECT AVG(CAST(AvgSize AS FLOAT)) AS avg_parcel_size, COUNT(*) AS n_kapans FROM tblKapan;`

**Q32** [GAP] Who are our clients?
  - type: judgment
  - ground truth: Clarify / disambiguate. "Clients" is ambiguous across three candidate entity tables: tblParty (party master — job-work parties/sub-contractors, 51 rows), tblSupplier (rough suppliers, 50 rows), and tblBuyerName (buyers, 8 rows). Correct response is to ask which one is meant, or surface tblParty/tblBuyerName and explain the distinction (party vs supplier vs buyer). It must NOT silently pick one table and fabricate a definitive "client list".

**Q33** [GAP] Show me packets created today.
  - type: objective
  - ground truth: 0 packets created "today". The DB is a FROZEN snapshot (last tblPacket.CreDate = 2026-06-25 17:38); harness date is 2026-07-10, so GETDATE()=today returns 0 rows — this is EXPECTED, not a bug. Correctness hinges on using the right column: tblPacket's creation timestamp is CreDate (not CreateDate/CreatedDate/CreatDate). Sanity check: the last populated day 2026-06-25 has 153 packets, confirming CreDate is the correct, working column.
  - sql: `SELECT COUNT(*) AS c FROM tblPacket WHERE CAST(CreDate AS DATE) = CAST(GETDATE() AS DATE)`

**Q34** [GAP] Which kapans were finished this year?
  - type: objective
  - ground truth: 84 kapans were finished this year (2026). Verified against the frozen snapshot (data ends ~25 Jun 2026) using tblKapan WHERE IsFinished=1 AND YEAR(FinishDate)=2026. For reference, by year of FinishDate among finished kapans: 2026=84, 2025=202, 2024=163, 2023=146, 2022=190, 2021=6.
  - sql: `SELECT COUNT(*) AS c FROM tblKapan WHERE IsFinished=1 AND YEAR(FinishDate)=2026;`

**Q35** [GAP] "What's our total value?"
  - type: judgment
  - ground truth: clarify: "value of what?" — the word "value" maps to many different monetary columns (RoughValue, EstValue, Estimate, OEstimate, Amount, REstimate), so the bot should ask whether the user means rough, estimated, or final value rather than SUM one column and fabricate a single number. PASS if the bot asks which value; FAIL if it emits a single SUM.

**Q36** [OK] "Total amount for this packet."
  - type: judgment
  - ground truth: clarify: "this packet" is an unspecified placeholder AND "total amount" is ambiguous — tblPacket carries several monetary columns (PAmount, Amount, Estimate, OEstimate, REstimate). The correct behavior is to ask which packet is meant and which monetary field ('amount') the user wants (e.g. rough estimate OEstimate, revised REstimate, packet amount PAmount/Amount) rather than picking one and returning a number. PASS if the bot asks a clarifying question instead of fabricating a single figure.

**Q37** [OK] What's the customer's email for kapan K-123?
  - type: judgment
  - ground truth: not tracked: There is no customer email (and no customer entity) associated with a kapan in this database. A kapan is a batch of purchased rough diamonds; tblKapan has no customer or email column, and the only email that exists anywhere is EMPLOYEE email in tblEmpDetail. Correct behavior is to decline: "not available in this database."

**Q38** [OK] Give me the GPS coordinates of each worker.
  - type: judgment
  - ground truth: not tracked: No GPS coordinates (latitude/longitude) are stored for workers. The only GPS-related field is tblEmployee.IsGPSEnabled, which is a bit flag indicating whether GPS is enabled for that employee — not a location. The tblGPSLabour* tables concern pay/rates, not position. The bot should refuse to invent coordinates and explain that only a GPS-enabled flag exists.

**Q39** [GAP] What's the profit margin on each packet?
  - type: judgment
  - ground truth: not tracked: Profit margin cannot be computed from the available fields. The packet tables carry only an Amount (a value/price figure) and no cost basis — there is no cost, purchase-price, or margin column anywhere. The correct behavior is to explain that margin is not derivable without a cost, offer the Amount/Estimate figures that DO exist, and decline to fabricate a margin (e.g. by treating Estimate vs Amount as cost vs revenue).

**Q40** [GAP] "Download the certificate PDF for this stone."
  - type: judgment
  - ground truth: not tracked: The database stores no PDF, file link, or attachment for a stone's certificate. Schema search across all tables for PDF/FilePath/Attachment/Certificate columns returns nothing relevant (only tblCompany.CertificateDate, unrelated). What DOES exist is the certificate metadata: tblPacketDetail.ReportNo and tblPacketDetail.Inscription. Correct behavior: clarify that no PDF/file is stored (and this is a SQL-over-DB bot, not a file store), and offer the report number / inscription instead.

**Q41** [OK] How many diamonds were stolen last month?
  - type: judgment
  - ground truth: not tracked: theft/"stolen" is not a concept in this ERP — no table records stolen diamonds; the bot should say theft isn't tracked and must NOT map "stolen" to junk/scrap/rejection or repair-loss.

**Q42** [OK] "Top 5 employees by total incentive earned."
  - type: objective
  - ground truth: Top 5 employees by total incentive (SUM of Credit) in tblIncentiveAmount: EmpID 4370 = 1882.00; EmpID 3218 = 1285.30; EmpID 4387 = 1113.27; EmpID 4482 = 1073.49; EmpID 3215 = 1036.10.
  - sql: `SELECT TOP 5 EmpID, SUM(Credit) AS TotalIncentive FROM tblIncentiveAmount GROUP BY EmpID ORDER BY SUM(Credit) DESC`

**Q43** [GAP] Which kapan produced the most junk by weight?
  - type: objective
  - ground truth: Kapan_ID 1199 (KapanName "BS") produced the most junk by weight: SUM(Weight) = 1303.195 across 846 junk records. Runners-up: 1236 (1173.526), 1189 (1057.063), 1190 (987.887), 1312 (830.997). Total junk in tblJunk = 201,285 rows / 73,291.965 weight.
  - sql: `SELECT TOP 1 k.ID AS Kapan_ID, k.KapanName, SUM(j.Weight) AS TotWt FROM tblJunk j JOIN tblKapan k ON j.Kapan_ID = k.ID GROUP BY k.ID, k.KapanName ORDER BY SUM(j.Weight) DESC;`

**Q44** [OK] "Average present-days per employee per month."
  - type: judgment
  - ground truth: Not reliably answerable per employee. Attendance is stored as raw biometric in/out punches in tblTimeAttendance (393,882 rows, dated by the 'Time' column), NOT pre-aggregated present-days. Deriving present-days would require COUNT(DISTINCT CAST(Time AS date)) per employee per month — but the table's EmpId column is 100% NULL (0 of 393,882 rows populated) and UserId is a machine id (985 distinct) that does not map cleanly to tblEmployee. So an average present-days PER EMPLOYEE per month cannot be reliably computed. The honest answer explains this limitation; the closest best-effort figure is distinct punch-days per machine UserId per month, which is NOT the same as per named employee. (Also note this table's data ends ~Apr 2025 in the frozen snapshot.) Correct behavior = explain the derivation is non-trivial and that per-employee attendance isn't reliably linked, rather than fabricating an average.

**Q45** [OK] "Total final-packet value, managers only."
  - type: judgment
  - ground truth: Correct behavior is to recognise the join requirement and/or flag that final-packet value is not directly manager-attributable. tblFinalPacket has no manager flag; the only manager link is UserID (who CREATED the record). Following the glossary recipe (JOIN tblFinalPacket.UserID = tblEmployee.ID WHERE IsManager=1) yields SUM(Amount)=9,734,227.35 across 171,764 packets. But this is essentially the ENTIRE table (total = 9,734,244.76 across 171,765 rows) because only 2 distinct UserIDs exist and one data-entry account, UserID 3231 (a manager), created 171,764 of the 171,765 rows. So a raw "managers only" number is meaningless/misleading. Ideal answer: perform the creator-manager join OR (better) explain that final value cannot be attributed to managers directly since UserID is a single data-entry account, not the value owner.
  - sql: `SELECT COUNT(*) cnt, SUM(CAST(Amount AS float)) tot FROM tblFinalPacket WHERE UserID IN (SELECT ID FROM tblEmployee WHERE IsManager=1); -- 171764 rows, 9734227.35 (~whole table)`

**Q46** [OK] Show me the ones that failed quality.
  - type: judgment
  - ground truth: Clarify: "failed quality" is ambiguous across three distinct concepts, so the correct behavior is to ask which is meant (or default to repair-sent stones and say so explicitly). The three candidates: (1) REPAIR = stones re-checked/sent for re-polishing -> tblRepairCommentVision (the REAL repair table; NOT tblRepairLog/tblRepairLogNew, which are database CRUD audit logs); (2) REJECTION = QC rejections -> tblRejection is EMPTY, so that data is not captured; (3) JUNK/scrap/bhangar -> tblJunk (only Weight/Pcs/Packet_ID/Kapan_ID usable). PASS = the bot asks which definition or defaults to repair-sent stones (tblRepairCommentVision) and states the assumption. FAIL = silently counting tblRepairLogNew rows or inventing tblRejection numbers.

**Q47** [OK] "Who's been absent the most?"
  - type: judgment
  - ground truth: not tracked / explain limitation: There is no absence table. "Absent" would have to be derived from gaps in attendance (missing punch-days). But attendance is recorded only as raw biometric punches in tblTimeAttendance whose EmpId column is 100% NULL and whose UserId is a machine id that does not map cleanly to employees (only ~14% match tblEmployee.ID, 0% match Code). Therefore per-employee attendance — and hence per-employee absence — cannot be reliably computed. The correct behavior is to explain that absence is inferred from attendance gaps and that per-employee attendance isn't reliably linkable, so "who was absent the most" can't be honestly answered from this data; do NOT fabricate a name or return an empty join as an answer. (PASS if the bot explains/declines rather than inventing a person.)

**Q48** [OK] What did Ramesh make yesterday?
  - type: judgment
  - ground truth: clarify: "Ramesh" is ambiguous — 20+ employees match (SARVAIYA/RAMESH, DESAI/RAMESH, KAKADIYA/RAMESHBHAI, etc.), and because names are stored surname-first the token actually lives in LastName, not FirstName. Also "make" is ambiguous (labour earnings on tblLabourResult vs. packets processed) and "yesterday" (2026-07-09) returns no rows in this frozen snapshot (tblLabourResult data ends 2023). Correct behavior is to ask WHICH Ramesh and/or which metric, or to state there is no data for yesterday — NOT to fabricate a single number.

**Q49** [OK] "How's this kapan doing?"
  - type: judgment
  - ground truth: clarify

**Q50** [OK] "Give me the good stones."
  - type: judgment
  - ground truth: clarify: "Good" is not a defined attribute in the data. Ask which quality criterion the user means — e.g. highest value/rate, top color/clarity grade, not-repaired, not-rejected, or a specific quality flag — before returning any stones. PASS if the bot asks for the quality criterion rather than fabricating one.

**Q51** [GAP] "Surat na ketla karigar che?" (How many workers are from Surat?)
  - type: objective
  - ground truth: 2326 workers are from Surat. (Counted via tblEmpDetail joined to tblEmployee, WHERE City='Surat'; all 2326 rows are distinct employees — no duplication. Total tblEmpDetail rows = 2411.)
  - sql: `SELECT COUNT(*) AS c FROM tblEmpDetail d JOIN tblEmployee e ON e.ID = d.Emp_ID WHERE d.City = 'Surat';`

**Q52** [OK] "Jangad par atyare ketlo maal pending che?" (How much goods is pending on jangad right now?)
  - type: objective
  - ground truth: 534 packets are currently pending (still out) on jangad — 534 rows and 534 distinct PacketIds, totaling 380.784 carats — via tblJangadPackets WHERE IsReceived = 0. (Frozen snapshot; "atyare/right now" reflects data as of ~25 Jun 2026.)
  - sql: `SELECT COUNT(*) AS pending_packets, COUNT(DISTINCT PacketId) AS distinct_packets, SUM(Carat) AS pending_carat FROM tblJangadPackets WHERE IsReceived = 0;`

**Q53** [OK] Aakha mahina ma ketla packet final thaya? (How many packets were finalized this whole month?)
  - type: objective
  - ground truth: 0 packets finalized in the current month (July 2026). The frozen snapshot's tblFinalPacket.CreateDate ends 2026-06-25, so 'this month' (July) legitimately has 0 rows. For reference, the most recent full month, June 2026, had 3,472 finalized packets. A correct bot should either report 0 or note that the latest data is from June 2026.
  - sql: `SELECT COUNT(*) AS FinalizedThisMonth FROM tblFinalPacket WHERE YEAR(CreateDate) = YEAR(GETDATE()) AND MONTH(CreateDate) = MONTH(GETDATE());`

**Q54** [OK] "Sauthi vadhare junk kaya kapan ma thayu?" (Which kapan had the most junk?) — Expect: same as Q43.
  - type: objective
  - ground truth: Kapan "BS" (Kapan_ID 1199) had the most junk by weight: SUM(Weight) = 1303.195 (846 junk rows). Runners-up: "DD" (1236) = 1173.526, "BI" (1189) = 1057.063. Answer derived by GROUP BY Kapan_ID, SUM(Weight) on tblJunk (Q43 logic).
  - sql: `SELECT TOP 1 k.KapanName, j.Kapan_ID, SUM(j.Weight) AS TotalJunkWeight FROM tblJunk j JOIN tblKapan k ON j.Kapan_ID = k.ID GROUP BY k.KapanName, j.Kapan_ID ORDER BY SUM(j.Weight) DESC;`

**Q55** [OK] "Aa packet ni labour ketli thai?" (What was the total labour for this packet?)
  - type: judgment
  - ground truth: Pick ONE source of truth and state it. The correct behavior is to compute a packet's total labour from the CURRENT live per-packet labour table tblPointRateLabour as SUM(FinalLabour) WHERE Packet_ID = <the packet> (grouped/optionally broken down by DepartmentName/Process), and to explicitly say that this is the table being used. The bot must NOT: (a) sum FinalLabour across multiple labour tables, (b) UNION tblPointRateLabour with the historical tblLabourResult (they overlap mid-2022..Feb-2023 and would double-count), or (c) use the stale tblLabourResultGIA / *Edit / *_Compare copies. tblLabourResult is acceptable only for a strictly pre-mid-2022 packet. Since no concrete packet id is supplied in the question, there is no single numeric ground truth — this is a methodology/judgment item that passes when the bot commits to one authoritative table (tblPointRateLabour) and names it rather than fabricating by conflating sources.

**Q56** [OK] "Active karigar ketla che, total nai active j?" (How many active workers — not total, only active?)
  - type: objective
  - ground truth: 352 active workers (must NOT return the full total of 2,412).
  - sql: `SELECT COUNT(*) AS c FROM tblEmployee WHERE IsActive = 1`

**Q57** [OK] Total tansion-4 fluorescent round stones currently out on approval.
  - type: objective
  - ground truth: 0. No tension-4 fluorescent round stones are currently out on approval (jangad). There ARE 24 tension-4 fluorescent round packets (12 FNT + 6 STG + 6 MED) that were sent out on jangad historically, but every one of them has IsReceived=1 (already returned/received back). Filtering for goods still OUT (IsReceived=0) yields 0. The correct answer is 0 — a bot that reports 24 is counting returned/received jangad packets and ignoring the jangad reverse-logic trap.
  - sql: `SELECT COUNT(DISTINCT jp.PacketId) AS c
FROM tblJangadPackets jp
JOIN tblPacket p ON jp.PacketId = p.ID
WHERE jp.IsReceived = 0
  AND p.Shape = 'RD'
  AND p.Florecent <> 'NON'
  AND p.Tension = 4;`

**Q58** [OK] "Average per-point labour rate for non-fluorescent stones in the cutting department, excluding any backup records."
  - type: objective
  - ground truth: The per-point labour rate lives in tblPointRateLabour.ReportRate (rate per point), and "non-fluorescent" = tblPacket.Florecent = 'NON' (misspelled column; NON = no fluorescence). Averaging ReportRate for NON stones across live processing departments gives ~0.38 rupees/point (AVG=0.3761, n=151,101 rows). Because the ERP has NO department literally named "Cutting" (departments are stages: Marker, Blocking, Blocking Auto, Brooter, Dhar, SDhar, Dilate, Fency, MFG-1..6, VL variants...), the "cutting department" scope is ambiguous: restricting to the pre-polish cutting stages (excluding MFG) gives AVG ~0.32/point (n=112,178); MFG stages alone give ~0.54/point (n=47,202). All figures use live tables (tblPointRateLabour + tblPacket) and exclude backup tables (no _BKP). A correct bot answer states ~0.32-0.38 per point and ideally flags the cutting-department ambiguity.
  - sql: `SELECT AVG(CAST(l.ReportRate AS float)) AS avg_rate_per_point, COUNT(*) AS n
FROM tblPointRateLabour l
JOIN tblPacket p ON l.Packet_ID = p.ID
WHERE p.Florecent = 'NON' AND l.ReportRate IS NOT NULL;
-- (optionally add: AND l.DepartmentName NOT LIKE '%MFG%' to restrict to pre-polish cutting stages)`

**Q59** [OK] "Sauthi vadhare incentive kaya karigar ne malyu, ne te Surat no che ke nai?" (Which worker earned the most incentive, and are they from Surat or not?)
  - type: objective
  - ground truth: Top incentive earner is EmpID 4370, KALSARIA MATHURBHAI, with total incentive (SUM of tblIncentiveAmount.Credit) = 1882.0. Their City in tblEmpDetail = SURAT, so YES — the highest-incentive worker IS from Surat. (Runner-up: SAVALIYA BHAVESHBHAI, EmpID 3218, 1285.3, also Surat.)
  - sql: `SELECT TOP 5 i.EmpID, e.FirstName, e.LastName, d.City, SUM(i.Credit) AS TotIncentive
FROM tblIncentiveAmount i
LEFT JOIN tblEmployee e ON i.EmpID = e.ID
LEFT JOIN tblEmpDetail d ON e.ID = d.Emp_ID
GROUP BY i.EmpID, e.FirstName, e.LastName, d.City
ORDER BY SUM(i.Credit) DESC;`

**Q60** [OK] "How many diamonds are sitting in stock that haven't been sold?"
  - type: judgment
  - ground truth: Sales/"sold" status is NOT tracked in this DB (the only sales table, tblPacketSell, is empty), so the "haven't been sold" filter cannot be applied — the bot must say so rather than fabricate a sold count. For the "in stock" part: the doc's literal Expect column, tblPacket.IsInTempStock=1, returns 0 because that column is DEAD (100% False across all 164,573 rows). The meaningful diamonds-in-stock count is tblPacket.RunningProcess='IN Stock' = 148,971 packets. Correct response: state that sales aren't recorded (so "not sold" can't be verified), and if giving a stock figure, use RunningProcess='IN Stock' (~148,971), NOT the stores/tblStock* tables and NOT the dead IsInTempStock column.
  - sql: `SELECT COUNT(*) AS in_stock FROM tblPacket WHERE RunningProcess = 'IN Stock'; -- =148971. (Doc's literal Expect: SELECT COUNT(*) FROM tblPacket WHERE IsInTempStock=1 => 0, dead column. tblPacketSell is empty so "not sold" is un-filterable.)`
